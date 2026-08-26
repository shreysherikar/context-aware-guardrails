"""HTTP wiring — Guardrail API entrypoint.

This module only wires the pieces together: it contains no business logic. The
risk-classifier implementation is chosen by LLM_PROVIDER, the post-ALLOW
generative gateway by LLM_GENERATION_PROVIDER, and the post-generation output
guardrail by OUTPUT_GUARDRAIL_PROVIDER (all independent); see the respective
factories in services/. Optical OCR is chosen by OPTICAL_OCR_PROVIDER.
Caller identity comes from a verified HS256 bearer token (services/auth):
/guardrail/evaluate and /guardrail/evaluate-image require it, and the role fed
to the policy engine is the verified claim, never a request field.

REWRITE (text and image) means: transform the request into a policy-compliant
representation via the unified SanitizationEngine before any LLM generation.
Sanitization failure fails closed to REVIEW — never falls back to original content.
"""

import hashlib
import logging

# Load local environment (.env) before importing anything that reads
# environment variables, so the config documented in .env.example actually works
# locally and not only under Docker (which passes env_file).
from dotenv import load_dotenv

load_dotenv()

from fastapi import (  # noqa: E402
    Depends,
    FastAPI,
    File,
    Form,
    Header,
    HTTPException,
    Request,
    UploadFile,
)
from fastapi.responses import JSONResponse  # noqa: E402
from pydantic import BaseModel  # noqa: E402

from domain.enums import PolicyAction  # noqa: E402
from domain.models import (  # noqa: E402
    AuditEvent,
    GuardrailRequest,
    LLMResult,
    OpticalAssessment,
    OpticalAuditMeta,
    OutputGuardrailResult,
    PolicyDecision,
    RiskAssessment,
    SanitizationAuditMeta,
)
from services import auth  # noqa: E402
from services.audit.audit import log_event  # noqa: E402
from services.llm import LLMRequest  # noqa: E402
from services.llm.factory import get_gateway  # noqa: E402
from services.optical_guardrail.analyzer import OpticalAnalyzer  # noqa: E402
from services.optical_guardrail.factory import get_ocr_provider  # noqa: E402
from services.optical_guardrail.normalizer import normalize_optical_assessment  # noqa: E402
from services.optical_guardrail.ocr import OCRError  # noqa: E402
from services.optical_guardrail.validation import ImageValidationError, validate_image  # noqa: E402
from services.output_guardrail.factory import get_output_guardrail  # noqa: E402
from services.policy_engine.engine import PolicyEngine  # noqa: E402
from services.risk_engine.factory import get_classifier  # noqa: E402
from services.sanitization.factory import get_sanitization_engine  # noqa: E402
from services.sanitization.models import SanitizationRequest, SanitizationResult  # noqa: E402

logger = logging.getLogger(__name__)

# Refuse to start insecurely: with AUTH_DEV_MODE off (the default) there is no
# way to verify tokens without the shared secret.
auth.ensure_startup_requirements()

app = FastAPI(title="Context-Aware Guardrail", version="0.1.0")

# The risk classifier and the deterministic policy engine are the security
# gate. The LLM gateway is reachable on ALLOW, or on REWRITE after successful
# sanitization — never for BLOCK/REVIEW, and never as a decision-maker.
classifier = get_classifier()
policy_engine = PolicyEngine()
gateway = get_gateway()
output_guardrail = get_output_guardrail()
ocr_provider = get_ocr_provider()
optical_analyzer = OpticalAnalyzer()
sanitization_engine = get_sanitization_engine()

# Safe, generic external reasons. Detailed policy reasons stay in the audit
# record only — they are not echoed to callers.
_SAFE_REASONS = {
    PolicyAction.BLOCK: "This request was blocked by policy and was not processed.",
    PolicyAction.REVIEW: "This request requires human review before it can be processed.",
}

_IMAGE_AUDIT_PROMPT = "[image input]"
_TEXT_SANITIZED_AUDIT_PROMPT = "[text input; sanitized]"


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
    """Structured response when the output guardrail flags a generated response."""
    return {
        "action": PolicyAction.REVIEW.value,
        "reason": "The generated response was flagged for human review and was not returned.",
        "blocked": False,
        "review_required": True,
    }


_GENERIC_401 = HTTPException(status_code=401, detail="Unauthorized")


async def get_verified_role(
    authorization: str | None = Header(default=None),
) -> str:
    """FastAPI dependency: verify the bearer token and return its role claim."""
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
    """Dev-only: mint a signed token for manual/local testing."""
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


async def _generate_and_guard(
    *,
    prompt_for_llm: str,
) -> tuple[LLMResult, OutputGuardrailResult, str | None]:
    """Run post-policy generation + output guardrail (fail-closed).

    ``prompt_for_llm`` must already be the safe representation (original for
    ALLOW, sanitized for REWRITE).
    """
    llm_result = LLMResult(attempted=False, succeeded=False)
    output_result = OutputGuardrailResult(attempted=False, flagged=False)
    generated: str | None = None
    try:
        if gateway is None:
            logger.info("Policy permits generation but no LLM gateway configured; skipping.")
        else:
            llm_result.attempted = True
            response = await gateway.generate(LLMRequest(prompt=prompt_for_llm))
            generated = response.text
            llm_result.succeeded = True
    except Exception as exc:  # noqa: BLE001 - never leak provider failures
        llm_result.error_kind = type(exc).__name__
        logger.exception("LLM generation failed for a permitted request")

    if generated is not None and llm_result.succeeded:
        try:
            if output_guardrail is None:
                pass
            else:
                output_result.attempted = True
                assessment = await output_guardrail.check(prompt_for_llm, generated)
                if assessment.flagged:
                    output_result.flagged = True
        except Exception as exc:  # noqa: BLE001 - fail closed on ANY guardrail failure
            output_result.attempted = True
            output_result.flagged = True
            output_result.error_kind = type(exc).__name__
            logger.exception("Output guardrail failed for a permitted request")

    return llm_result, output_result, generated


def _generation_response(
    *,
    decision: PolicyDecision,
    risk: RiskAssessment,
    llm_result: LLMResult,
    output_result: OutputGuardrailResult,
    generated: str | None,
    action: PolicyAction,
    extra: dict[str, object] | None = None,
) -> dict[str, object] | JSONResponse:
    """Shared response shaping after generation / output-guardrail."""
    if llm_result.attempted and not llm_result.succeeded:
        return JSONResponse(
            status_code=503,
            content={
                "detail": "The request passed policy review, but response generation is "
                "temporarily unavailable.",
                "action": action.value,
            },
        )

    if output_result.flagged:
        body = {
            "decision": decision,
            "risk_assessment": risk,
            **_flagged_for_review_response(),
        }
        if extra:
            body.update(extra)
        return body

    body: dict[str, object] = {
        "decision": decision,
        "risk_assessment": risk,
        "action": action.value,
        "response": generated,
    }
    if extra:
        body.update(extra)
    return body


def _run_sanitization(request: SanitizationRequest) -> SanitizationResult:
    """Invoke the unified sanitizer. Never returns original text on failure."""
    return sanitization_engine.sanitize(request)


def _sanitization_audit_meta(
    result: SanitizationResult,
    *,
    input_type: str,
    used: bool,
) -> SanitizationAuditMeta:
    return SanitizationAuditMeta(
        attempted=True,
        succeeded=result.success,
        applied=result.success and result.sanitized,
        input_type=input_type,
        finding_count=len(result.findings),
        sanitizer_version=result.sanitizer_version,
        sanitized_context_used=used and result.success,
        failure_kind=result.failure_reason,
    )


def _fail_closed_review_response(
    *,
    decision: PolicyDecision,
    risk: RiskAssessment,
    extra: dict[str, object] | None = None,
) -> dict[str, object]:
    """Sanitization failure → REVIEW. Never expose original sensitive content."""
    body: dict[str, object] = {
        "decision": decision,
        "risk_assessment": risk,
        **_stop_response(PolicyAction.REVIEW),
        "sanitization_applied": False,
        "sanitized": False,
    }
    if extra:
        body.update(extra)
    return body


@app.post("/guardrail/evaluate")
async def evaluate(
    request: GuardrailRequest,
    verified_role: str = Depends(get_verified_role),
):
    risk = classifier.classify(request)
    decision = policy_engine.evaluate(risk, verified_role)

    # BLOCK / REVIEW / CLARIFY (and any non-ALLOW/REWRITE): stop — no LLM.
    if decision.action not in (PolicyAction.ALLOW, PolicyAction.REWRITE):
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
            "input_type": "text",
            **_stop_response(decision.action),
        }

    sanitization_meta: SanitizationAuditMeta | None = None
    prompt_for_llm: str
    audit_prompt = request.prompt
    extra: dict[str, object] = {"input_type": "text"}

    if decision.action == PolicyAction.REWRITE:
        # REWRITE: sanitize first. Never send original sensitive text to the LLM.
        san_result = _run_sanitization(SanitizationRequest(text=request.prompt, source_type="text"))
        if not san_result.success:
            sanitization_meta = _sanitization_audit_meta(san_result, input_type="text", used=False)
            log_event(
                AuditEvent(
                    conversation_id=request.conversation_id,
                    prompt=_TEXT_SANITIZED_AUDIT_PROMPT,
                    user_role=verified_role,
                    risk_assessment=risk,
                    policy_decision=decision,
                    llm=LLMResult(attempted=False, succeeded=False),
                    sanitization=sanitization_meta,
                )
            )
            return _fail_closed_review_response(decision=decision, risk=risk, extra=extra)

        prompt_for_llm = san_result.sanitized_text
        sanitization_meta = _sanitization_audit_meta(san_result, input_type="text", used=True)
        audit_prompt = _TEXT_SANITIZED_AUDIT_PROMPT
        extra["sanitization_applied"] = True
        extra["sanitized"] = True
        extra["sanitized_text"] = prompt_for_llm
    else:
        # ALLOW: original safe content may proceed; do not invoke sanitizer.
        prompt_for_llm = request.prompt

    llm_result, output_result, generated = await _generate_and_guard(
        prompt_for_llm=prompt_for_llm,
    )

    log_event(
        AuditEvent(
            conversation_id=request.conversation_id,
            prompt=audit_prompt,
            user_role=verified_role,
            risk_assessment=risk,
            policy_decision=decision,
            llm=llm_result,
            output_guardrail=output_result,
            sanitization=sanitization_meta,
        )
    )

    return _generation_response(
        decision=decision,
        risk=risk,
        llm_result=llm_result,
        output_result=output_result,
        generated=generated,
        action=decision.action,
        extra=extra,
    )


@app.post("/guardrail/evaluate-image")
async def evaluate_image(
    verified_role: str = Depends(get_verified_role),
    image: UploadFile = File(  # noqa: B008 - FastAPI dependency injection
        ..., description="PNG, JPEG, or WEBP image to evaluate"
    ),
    conversation_id: str = Form(  # noqa: B008 - FastAPI dependency injection
        ..., description="Conversation / request correlation id"
    ),
):
    """Optical intake: validate → OCR → analyze → RiskAssessment → PolicyEngine.

    REWRITE uses the unified SanitizationEngine. Raw images are not persisted.
    """
    raw = await image.read()
    image_sha256 = hashlib.sha256(raw).hexdigest() if raw else None

    try:
        validated = validate_image(raw, declared_content_type=image.content_type)
    except ImageValidationError as exc:
        raise HTTPException(status_code=400, detail=exc.message) from exc

    try:
        ocr_result = await ocr_provider.extract(validated.data)
    except OCRError as exc:
        logger.warning("OCR failed for image request: %s", exc)
        raise HTTPException(status_code=503, detail=exc.message) from exc
    except Exception:  # noqa: BLE001 - never leak provider details
        logger.exception("Unexpected OCR failure")
        raise HTTPException(
            status_code=503,
            detail="Optical text extraction is temporarily unavailable.",
        ) from None

    optical: OpticalAssessment = optical_analyzer.analyze(ocr_result, image=validated.data)
    risk = normalize_optical_assessment(optical)
    decision = policy_engine.evaluate(risk, verified_role, input_type="image")

    optical_meta = OpticalAuditMeta(
        input_type="image",
        ocr_used=True,
        optical_analysis_used=True,
        document_type=optical.document_type,
        finding_count=len(optical.findings),
        sanitization_applied=False,
        image_sha256=image_sha256,
    )

    optical_public = {
        "document_type": optical.document_type,
        "injection_detected": optical.injection_detected,
        "face_detected": optical.face_detected,
        "confidence": optical.confidence,
        "finding_count": len(optical.findings),
        "findings": [
            {
                "type": f.type,
                "category": f.category.value,
                "confidence": f.confidence,
            }
            for f in optical.findings
        ],
    }

    # Terminal stop: BLOCK / REVIEW / CLARIFY — never call the LLM.
    if decision.action not in (PolicyAction.ALLOW, PolicyAction.REWRITE):
        log_event(
            AuditEvent(
                conversation_id=conversation_id,
                prompt=_IMAGE_AUDIT_PROMPT,
                user_role=verified_role,
                risk_assessment=risk,
                policy_decision=decision,
                llm=LLMResult(attempted=False, succeeded=False),
                optical=optical_meta,
            )
        )
        return {
            "decision": decision,
            "risk_assessment": risk,
            "optical_assessment": optical_public,
            "input_type": "image",
            **_stop_response(decision.action),
        }

    sanitization_meta: SanitizationAuditMeta | None = None
    prompt_for_llm: str
    audit_prompt = _IMAGE_AUDIT_PROMPT
    extra: dict[str, object] = {
        "input_type": "image",
        "optical_assessment": optical_public,
    }

    if decision.action == PolicyAction.REWRITE:
        san_result = _run_sanitization(
            SanitizationRequest(
                text=optical.ocr_text,
                source_type="image",
                optical_findings=optical.findings,
            )
        )
        if not san_result.success:
            sanitization_meta = _sanitization_audit_meta(san_result, input_type="image", used=False)
            log_event(
                AuditEvent(
                    conversation_id=conversation_id,
                    prompt=_IMAGE_AUDIT_PROMPT,
                    user_role=verified_role,
                    risk_assessment=risk,
                    policy_decision=decision,
                    llm=LLMResult(attempted=False, succeeded=False),
                    optical=optical_meta,
                    sanitization=sanitization_meta,
                )
            )
            return _fail_closed_review_response(
                decision=decision,
                risk=risk,
                extra=extra,
            )

        prompt_for_llm = san_result.sanitized_text
        sanitization_meta = _sanitization_audit_meta(san_result, input_type="image", used=True)
        optical_meta = optical_meta.model_copy(update={"sanitization_applied": True})
        audit_prompt = "[image input; sanitized]"
        extra["sanitization_applied"] = True
        extra["sanitized"] = True
        extra["sanitized_text"] = prompt_for_llm
    else:
        # ALLOW: OCR text is already low-risk; do not sanitize unnecessarily.
        prompt_for_llm = optical.ocr_text

    llm_result, output_result, generated = await _generate_and_guard(
        prompt_for_llm=prompt_for_llm,
    )

    log_event(
        AuditEvent(
            conversation_id=conversation_id,
            prompt=audit_prompt,
            user_role=verified_role,
            risk_assessment=risk,
            policy_decision=decision,
            llm=llm_result,
            output_guardrail=output_result,
            optical=optical_meta,
            sanitization=sanitization_meta,
        )
    )

    return _generation_response(
        decision=decision,
        risk=risk,
        llm_result=llm_result,
        output_result=output_result,
        generated=generated,
        action=decision.action,
        extra=extra,
    )
