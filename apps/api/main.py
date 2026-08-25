"""HTTP wiring — Guardrail API entrypoint.

This module only wires the pieces together: it contains no business logic. The
risk-classifier implementation is chosen by LLM_PROVIDER, the post-ALLOW
generative gateway by LLM_GENERATION_PROVIDER, and the post-generation output
guardrail by OUTPUT_GUARDRAIL_PROVIDER (all independent); see the respective
factories in services/. Caller identity comes from a verified HS256 bearer
token (services/auth): /guardrail/evaluate requires it, and the role fed to
the policy engine is the verified claim, never a request field.
"""

import logging

# Load local environment (.env) before importing anything that reads
# environment variables, so the config documented in .env.example actually works
# locally and not only under Docker (which passes env_file).
from dotenv import load_dotenv

load_dotenv()

from fastapi import Depends, FastAPI, Header, HTTPException, Request  # noqa: E402
from fastapi.responses import JSONResponse  # noqa: E402
from pydantic import BaseModel  # noqa: E402

from domain.enums import PolicyAction  # noqa: E402
from domain.models import (  # noqa: E402
    AuditEvent,
    GuardrailRequest,
    LLMResult,
    OutputGuardrailResult,
)
from services import auth  # noqa: E402
from services.audit.audit import log_event  # noqa: E402
from services.llm import LLMRequest  # noqa: E402
from services.llm.factory import get_gateway  # noqa: E402
from services.output_guardrail.factory import get_output_guardrail  # noqa: E402
from services.policy_engine.engine import PolicyEngine  # noqa: E402
from services.risk_engine.factory import get_classifier  # noqa: E402

logger = logging.getLogger(__name__)

# Refuse to start insecurely: with AUTH_DEV_MODE off (the default) there is no
# way to verify tokens without the shared secret.
auth.ensure_startup_requirements()

app = FastAPI(title="Context-Aware Guardrail", version="0.1.0")

# The risk classifier and the deterministic policy engine are the security
# gate. The LLM gateway is ONLY reachable on a policy ALLOW — never before,
# never for BLOCK/REVIEW, and never as a decision-maker. The output guardrail
# runs after generation to inspect the response before it reaches an employee,
# and is itself a fail-closed stage.
classifier = get_classifier()
policy_engine = PolicyEngine()
gateway = get_gateway()
output_guardrail = get_output_guardrail()

# Safe, generic external reasons. Detailed policy reasons stay in the audit
# record only — they are not echoed to callers.
_SAFE_REASONS = {
    PolicyAction.BLOCK: "This request was blocked by policy and was not processed.",
    PolicyAction.REVIEW: "This request requires human review before it can be processed.",
}


def _stop_response(decision_action: PolicyAction) -> dict[str, object]:
    """Structured terminal response for any non-ALLOW decision (no LLM call)."""
    body: dict[str, object] = {
        "action": decision_action.value,
        "reason": _SAFE_REASONS.get(
            decision_action, "This request cannot be processed automatically."
        ),
        "blocked": decision_action == PolicyAction.BLOCK,
    }
    if decision_action == PolicyAction.REVIEW:
        body["review_required"] = True
    return body


def _flagged_for_review_response() -> dict[str, object]:
    """Structured response when the output guardrail flags a generated response.

    Reuses the REVIEW-style response shape / review_required flag used for
    policy-level REVIEW: the policy decision itself is ALLOW, but the response
    must not be returned because post-generation inspection did not clear it.
    """
    return {
        "action": PolicyAction.REVIEW.value,
        "reason": "The generated response was flagged for human review and was not returned.",
        "blocked": False,
        "review_required": True,
    }


# One generic 401 for every authentication failure mode (missing/malformed
# header, bad signature, wrong algorithm, expired, missing/invalid role). The
# specific reason is logged server-side only — never placed in the response
# body — mirroring the no-leak pattern used for provider failures.
_GENERIC_401 = HTTPException(status_code=401, detail="Unauthorized")


async def get_verified_role(
    authorization: str | None = Header(default=None),
) -> str:
    """FastAPI dependency: verify the bearer token and return its role claim.

    Runs before the risk classifier and policy engine; an unauthenticated
    request never reaches the pipeline.
    """
    try:
        if not authorization or not authorization.startswith("Bearer "):
            raise auth.AuthError("missing or malformed Authorization header")
        token = authorization[len("Bearer ") :].strip()
        if not token:
            raise auth.AuthError("empty bearer token")
        return auth.verify_token(token)
    except auth.AuthError as exc:
        logger.warning("Authentication failed: %s", exc)
        raise _GENERIC_401 from exc


class DevTokenRequest(BaseModel):
    role: str


@app.post("/auth/dev-token")
def issue_dev_token(body: DevTokenRequest) -> dict[str, str]:
    """Dev-only: mint a signed token for manual/local testing.

    Exists only when AUTH_DEV_MODE is explicitly true. Otherwise this endpoint
    answers 404 as if it did not exist. If dev mode is on but the shared secret
    is missing, minting cannot sign anything — report that configuration error
    directly, since this endpoint is unreachable in production deployments.
    """
    if not auth.is_dev_mode_enabled():
        raise HTTPException(status_code=404, detail="Not Found")
    try:
        return {"token": auth.mint_dev_token(body.role)}
    except auth.AuthConfigError as exc:
        logger.error("Dev-token issuance misconfigured: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.exception_handler(Exception)
async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
    """Never leak internals, stack traces or provider details to callers."""
    logger.exception("Unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(status_code=500, content={"detail": "Internal server error."})


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/guardrail/evaluate")
async def evaluate(
    request: GuardrailRequest,
    verified_role: str = Depends(get_verified_role),
):
    risk = classifier.classify(request)
    decision = policy_engine.evaluate(risk, verified_role)

    # Security invariant: nothing below this point runs unless policy said
    # ALLOW. BLOCK/REVIEW (and any other non-ALLOW action) stop here without
    # any LLM call.
    if decision.action != PolicyAction.ALLOW:
        log_event(
            AuditEvent(
                conversation_id=request.conversation_id,
                prompt=request.prompt,
                user_role=verified_role,
                risk_assessment=risk,
                policy_decision=decision,
                llm=LLMResult(attempted=False, succeeded=False),
            )
        )
        return {
            "decision": decision,
            "risk_assessment": risk,
            **_stop_response(decision.action),
        }

    llm_result = LLMResult(attempted=False, succeeded=False)
    output_result = OutputGuardrailResult(attempted=False, flagged=False)
    generated: str | None = None
    try:
        if gateway is None:
            # Offline/default configuration: no generative provider is wired.
            # The request was allowed by policy; generation is simply skipped.
            logger.info("Policy ALLOW but no LLM gateway configured; skipping generation.")
        else:
            llm_result.attempted = True
            response = await gateway.generate(LLMRequest(prompt=request.prompt))
            generated = response.text
            llm_result.succeeded = True
    except Exception as exc:  # noqa: BLE001 - never leak provider failures
        # Log the real failure internally with full context; return a generic
        # application-level error. An ALLOW must never silently become a
        # successful response, and provider details must never reach callers.
        llm_result.error_kind = type(exc).__name__
        logger.exception("LLM generation failed for an ALLOWed request")

    # Output guardrail: inspect the generated response BEFORE it reaches the
    # employee. It only runs after generation succeeded. This is fail-closed by
    # design: if the guardrail flags the response, or if the check itself
    # fails/times out/errors, the response is NOT returned as a normal ALLOW
    # success — it is routed to flagged-for-review. A broken output guardrail
    # must not let an unverified claim through silently, consistent with every
    # other fail-closed decision in this codebase.
    if generated is not None and llm_result.succeeded:
        try:
            if output_guardrail is None:
                # OUTPUT_GUARDRAIL_PROVIDER unset/empty -> stage skipped entirely.
                pass
            else:
                output_result.attempted = True
                assessment = await output_guardrail.check(request.prompt, generated)
                if assessment.flagged:
                    output_result.flagged = True
        except Exception as exc:  # noqa: BLE001 - fail closed on ANY guardrail failure
            output_result.attempted = True
            output_result.flagged = True
            output_result.error_kind = type(exc).__name__
            logger.exception("Output guardrail failed for an ALLOWed request")

    log_event(
        AuditEvent(
            conversation_id=request.conversation_id,
            prompt=request.prompt,
            user_role=verified_role,
            risk_assessment=risk,
            policy_decision=decision,
            llm=llm_result,
            output_guardrail=output_result,
        )
    )

    if llm_result.attempted and not llm_result.succeeded:
        return JSONResponse(
            status_code=503,
            content={
                "detail": "The request passed policy review, but response generation is "
                "temporarily unavailable.",
                "action": PolicyAction.ALLOW.value,
            },
        )

    if output_result.flagged:
        # Flagged for review: do not return the generated response.
        return {
            "decision": decision,
            "risk_assessment": risk,
            **_flagged_for_review_response(),
        }

    return {
        "decision": decision,
        "risk_assessment": risk,
        "action": PolicyAction.ALLOW.value,
        "response": generated,
    }
