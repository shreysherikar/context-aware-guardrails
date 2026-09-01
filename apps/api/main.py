"""HTTP wiring — Guardrail API entrypoint.

This module only wires the pieces together: it contains no business logic. The
risk-classifier implementation is chosen by LLM_PROVIDER, the post-ALLOW
generative gateway by LLM_GENERATION_PROVIDER, the post-generation output
guardrail by OUTPUT_GUARDRAIL_PROVIDER, and the post-generation claim/evidence
verifier by CLAIM_VERIFICATION_PROVIDER (all independent); see the respective
factories in services/. Optical OCR is chosen by OPTICAL_OCR_PROVIDER. Caller
identity comes from a verified HS256 bearer token (services/auth):
/guardrail/evaluate and /guardrail/evaluate-image require it, and the role fed
to the policy engine is the verified claim, never a request field.

REWRITE (text and image) means: transform the request into a policy-compliant
representation via the unified SanitizationEngine before any LLM generation.
Sanitization failure fails closed to REVIEW — never falls back to original content.
"""

import hashlib
import logging
import os
import uuid

# Load local environment (.env) before importing anything that reads
# environment variables, so the config documented in .env.example actually works
# locally and not only under Docker (which passes env_file).
from dotenv import load_dotenv

load_dotenv()

from pathlib import Path  # noqa: E402

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
from fastapi.responses import FileResponse, JSONResponse  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402
from pydantic import BaseModel  # noqa: E402

from domain.enums import PolicyAction, ResolutionType, ReviewRequestStatus, RiskLevel  # noqa: E402
from domain.models import (  # noqa: E402
    AuditEvent,
    ClaimVerificationMeta,
    ExplainableDecision,
    GuardrailRequest,
    LLMResult,
    OpticalAssessment,
    OpticalAuditMeta,
    OutputGuardrailResult,
    PolicyDecision,
    RiskAssessment,
    SanitizationAuditMeta,
    TrajectoryAssessment,
)
from services.explanation.builder import build_explainable_decision, build_rephrase_suggestion  # noqa: E402
from services.guardrail_review.models import EvaluationSnapshot  # noqa: E402
from services.guardrail_review.store import get_review_store  # noqa: E402
from services import auth  # noqa: E402
from services.audit.audit import list_events, log_event  # noqa: E402
from services.claim_verification import build_audit_meta  # noqa: E402
from services.claim_verification.factory import get_claim_verifier  # noqa: E402
from services.claim_verification.models import unverified_failure_response  # noqa: E402
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
from services.trajectory_engine.engine import evaluate_conversation  # noqa: E402
from services.nemo_guardrail.factory import get_nemo_dialog_rail, get_nemo_input_rail  # noqa: E402
from services.agent import GuardrailAgent  # noqa: E402
from services.agent.models import AgentChatResponse  # noqa: E402
from apps.api.governance_routes import router as governance_router  # noqa: E402
from services.governance.runtime import get_runtime  # noqa: E402

logger = logging.getLogger(__name__)

# Refuse to start insecurely: with AUTH_DEV_MODE off (the default) there is no
# way to verify tokens without the shared secret.
auth.ensure_startup_requirements()

app = FastAPI(title="Context-Aware Guardrail", version="0.2.0")

# Always-active governance runtime — starts at import, independent of agent sessions.
governance_runtime = get_runtime()
app.include_router(governance_router)

# The risk classifier and the deterministic policy engine are the security
# gate. The LLM gateway is reachable on ALLOW, or on REWRITE after successful
# sanitization — never for BLOCK/REVIEW, and never as a decision-maker.
classifier = get_classifier()
policy_engine = PolicyEngine()
gateway = get_gateway()
output_guardrail = get_output_guardrail()
claim_verifier = get_claim_verifier()
ocr_provider = get_ocr_provider()
optical_analyzer = OpticalAnalyzer()
sanitization_engine = get_sanitization_engine()
nemo_input_rail = get_nemo_input_rail()
nemo_dialog_rail = get_nemo_dialog_rail()
review_store = get_review_store()
agent = GuardrailAgent(
    classifier=classifier,
    policy_engine=policy_engine,
    gateway=gateway,
    output_guardrail=output_guardrail,
    ocr_provider=ocr_provider,
    optical_analyzer=optical_analyzer,
    sanitization_engine=sanitization_engine,
    nemo_input_rail=nemo_input_rail,
    nemo_dialog_rail=nemo_dialog_rail,
)

# Safe, generic external reasons. Detailed policy reasons stay in the audit
# record only — they are not echoed to callers.
_SAFE_REASONS = {
    PolicyAction.BLOCK: "This request was blocked by policy and was not processed.",
    PolicyAction.REVIEW: "This request requires human review before it can be processed.",
    PolicyAction.CLARIFY: "This request requires clarification before it can be processed.",
}

_IMAGE_AUDIT_PROMPT = "[image input]"
_TEXT_SANITIZED_AUDIT_PROMPT = "[text input; sanitized]"

_REVIEWER_ROLES = frozenset({"reviewer", "admin", "compliance"})


def _classify_with_nemo(request: GuardrailRequest) -> RiskAssessment:
    """Run classifier plus optional NeMo input rails (defense-in-depth)."""
    risk = classifier.classify(request)
    if nemo_input_rail is not None:
        risk = nemo_input_rail.augment_risk(request, risk)
    return risk


def _require_reviewer_role(role: str) -> None:
    if role not in _REVIEWER_ROLES:
        raise HTTPException(status_code=403, detail="Reviewer role required.")


def _effective_action(
    decision: PolicyDecision,
    *,
    output_flagged: bool = False,
    pipeline_failure: bool = False,
) -> PolicyAction:
    if output_flagged or pipeline_failure:
        return PolicyAction.REVIEW
    if decision.action == PolicyAction.CLARIFY:
        return PolicyAction.REVIEW
    return decision.action


def _attach_explanation(
    body: dict[str, object],
    *,
    request_id: str,
    risk: RiskAssessment,
    decision: PolicyDecision,
    effective_action: PolicyAction | None = None,
    input_type: str = "text",
    optical_findings: list | None = None,
    original_prompt: str | None = None,
    sanitized_prompt: str | None = None,
    llm_result: LLMResult | None = None,
    output_result: OutputGuardrailResult | None = None,
    pipeline_failure: bool = False,
) -> ExplainableDecision:
    explanation = build_explainable_decision(
        request_id=request_id,
        risk=risk,
        decision=decision,
        effective_action=effective_action,
        input_type=input_type,
        optical_findings=optical_findings,
        original_prompt=original_prompt,
        sanitized_prompt=sanitized_prompt,
        llm_result=llm_result,
        output_result=output_result,
        pipeline_failure=pipeline_failure,
    )
    body["explanation"] = explanation.model_dump(mode="json")
    body["request_id"] = request_id
    return explanation


def _save_evaluation_snapshot(
    *,
    request_id: str,
    conversation_id: str,
    user_role: str,
    decision: PolicyDecision,
    effective: PolicyAction,
    prompt: str,
    input_type: str,
) -> None:
    review_store.save_evaluation(
        EvaluationSnapshot(
            request_id=request_id,
            conversation_id=conversation_id,
            user_role=user_role,
            effective_decision=effective,
            policy_action=decision.action,
            prompt=prompt,
            input_type=input_type,
        )
    )


def _audit_from_explanation(
    *,
    conversation_id: str,
    prompt: str,
    user_role: str,
    risk: RiskAssessment,
    decision: PolicyDecision,
    explanation: ExplainableDecision,
    llm: LLMResult | None = None,
    output_guardrail: OutputGuardrailResult | None = None,
    optical: OpticalAuditMeta | None = None,
    sanitization: SanitizationAuditMeta | None = None,
    claim_verification: ClaimVerificationMeta | None = None,
    human_review_requested: bool = False,
    human_review_outcome: str | None = None,
    report_status: str | None = None,
) -> None:
    log_event(
        AuditEvent(
            conversation_id=conversation_id,
            prompt=prompt,
            user_role=user_role,
            risk_assessment=risk,
            policy_decision=decision,
            llm=llm,
            output_guardrail=output_guardrail,
            optical=optical,
            sanitization=sanitization,
            claim_verification=claim_verification,
            request_id=explanation.request_id,
            resolution_type=explanation.resolution_type.value,
            forwarded_to_llm=explanation.forwarded_to_llm,
            sanitization_occurred=explanation.sanitized_prompt is not None,
            human_review_requested=human_review_requested,
            human_review_outcome=human_review_outcome,
            report_status=report_status,
        )
    )


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


def _claims_review_response(
    *,
    decision: PolicyDecision,
    risk: RiskAssessment,
    extra: dict[str, object] | None = None,
) -> dict[str, object]:
    """Post-generation policy outcome changed (e.g. EVIDENCE-001 claims REVIEW).

    Uses the standard terminal-stop shape: the generated content and the claim
    details stay internal — they exist only in the audit record.
    """
    body: dict[str, object] = {
        "decision": decision,
        "risk_assessment": risk,
        **_stop_response(decision.action),
    }
    if extra:
        body.update(extra)
    return body


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


class AgentChatRequest(BaseModel):
    message: str
    conversation_id: str = "agent-session"
    use_web_search: bool = False


@app.post("/agent/chat", response_model=AgentChatResponse)
async def agent_chat(
    body: AgentChatRequest,
    verified_role: str = Depends(get_verified_role),
) -> AgentChatResponse:
    """Chat with the guardrail agent (text). Returns issues, corrections, and answer."""
    return await agent.chat_text(
        prompt=body.message,
        conversation_id=body.conversation_id,
        role=verified_role,
        use_web_search=body.use_web_search,
    )


@app.post("/agent/search")
async def agent_search(
    body: AgentChatRequest,
    verified_role: str = Depends(get_verified_role),
):
    """Search the web directly (still requires auth)."""
    _ = verified_role
    from services.web_bridge import search_web

    result = await search_web(body.message)
    return {
        "query": result.query,
        "succeeded": result.succeeded,
        "error": result.error,
        "sources": [s.model_dump() for s in result.sources],
    }


@app.post("/agent/chat-image", response_model=AgentChatResponse)
async def agent_chat_image(
    verified_role: str = Depends(get_verified_role),
    image: UploadFile = File(..., description="PNG, JPEG, or WEBP"),  # noqa: B008
    conversation_id: str = Form("agent-image"),  # noqa: B008
    message: str = Form(""),  # noqa: B008
) -> AgentChatResponse:
    """Chat with the guardrail agent (image). OCR + policy + corrective feedback."""
    raw = await image.read()
    return await agent.chat_image(
        image_bytes=raw,
        content_type=image.content_type,
        conversation_id=conversation_id,
        role=verified_role,
        user_message=message,
    )


@app.post("/agent/chat-file", response_model=AgentChatResponse)
async def agent_chat_file(
    verified_role: str = Depends(get_verified_role),
    file: UploadFile = File(..., description="Any supported upload"),  # noqa: B008
    conversation_id: str = Form("agent-file"),  # noqa: B008
    message: str = Form(""),  # noqa: B008
) -> AgentChatResponse:
    """Chat with any supported file — images, PDFs, Office docs, CSV, text, JSON."""
    raw = await file.read()
    return await agent.chat_file(
        file_bytes=raw,
        filename=file.filename or "upload",
        content_type=file.content_type,
        conversation_id=conversation_id,
        role=verified_role,
        user_message=message,
    )


@app.post("/agent/chat-document", response_model=AgentChatResponse)
async def agent_chat_document(
    verified_role: str = Depends(get_verified_role),
    document: UploadFile = File(..., description="PDF document"),  # noqa: B008
    conversation_id: str = Form("agent-document"),  # noqa: B008
    message: str = Form(""),  # noqa: B008
) -> AgentChatResponse:
    """Chat with the guardrail agent (PDF). Extracts text, then runs the text pipeline."""
    raw = await document.read()
    return await agent.chat_document(
        document_bytes=raw,
        filename=document.filename or "document.pdf",
        conversation_id=conversation_id,
        role=verified_role,
        user_message=message,
    )


_AGENT_PAGE = Path(__file__).resolve().parents[2] / "examples" / "agent.html"


@app.get("/agent")
def agent_page():
    """Interactive guardrail agent chat UI."""
    if not _AGENT_PAGE.is_file():
        raise HTTPException(status_code=404, detail="Agent page not found.")
    return FileResponse(_AGENT_PAGE, media_type="text/html")


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/demo/config")
def demo_config():
    """Expose active provider wiring for the interactive demo."""
    return {
        "llm_provider": os.getenv("LLM_PROVIDER", "mock"),
        "generation_provider": os.getenv("LLM_GENERATION_PROVIDER", ""),
        "ocr_provider": os.getenv("OPTICAL_OCR_PROVIDER", "mock"),
        "ollama_model": os.getenv("OLLAMA_MODEL", "qwen3.6:latest"),
        "ollama_base_url": os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434"),
    }


_DEMO_PAGE = Path(__file__).resolve().parents[2] / "examples" / "demo.html"
_OPTICAL_SAMPLES = Path(__file__).resolve().parents[2] / "examples" / "optical"


@app.get("/demo/samples/{filename}")
def demo_sample(filename: str):
    """Serve generated optical sample images for the demo UI."""
    if filename not in {"safe_brochure.png", "patient_card.png", "injection_attempt.png"}:
        raise HTTPException(status_code=404, detail="Sample not found.")
    path = _OPTICAL_SAMPLES / filename
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Sample not generated yet.")
    return FileResponse(path, media_type="image/png")


@app.get("/demo")
def demo_page():
    """Interactive local demo UI (offline mock classifier)."""
    if not _DEMO_PAGE.is_file():
        raise HTTPException(status_code=404, detail="Demo page not found.")
    return FileResponse(_DEMO_PAGE, media_type="text/html")


async def _generate_and_guard(
    *,
    prompt_for_llm: str,
    risk: RiskAssessment,
    user_role: str,
    trajectory: TrajectoryAssessment | None,
    decision: PolicyDecision,
    input_type: str | None = None,
) -> tuple[
    LLMResult,
    OutputGuardrailResult,
    ClaimVerificationMeta | None,
    PolicyDecision,
    str | None,
]:
    """Run post-policy generation + output guardrail + claim verification.

    ``prompt_for_llm`` must already be the safe representation (original for
    ALLOW, sanitized for REWRITE).

    After a successful generation, the optional claim/evidence verifier runs and
    THE SAME deterministic policy engine re-evaluates with the claims evidence
    supplied — its EVIDENCE-001 rule routes unsupported / contradicted /
    conflicting / insufficient claims to REVIEW. The returned decision equals
    ``decision`` when no verification ran or every claim was supported, and is
    strictly more conservative otherwise; it can never become more permissive
    than the input-side decision. Callers must persist and return THIS decision.
    """
    llm_result = LLMResult(attempted=False, succeeded=False)
    output_result = OutputGuardrailResult(attempted=False, flagged=False)
    claim_meta: ClaimVerificationMeta | None = None
    effective_decision = decision
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
            output_result.attempted = True
            assessment = await output_guardrail.check(prompt_for_llm, generated)
            if assessment.safe_text:
                generated = assessment.safe_text
            if assessment.blocked:
                output_result.flagged = True
            elif assessment.flagged:
                output_result.attempted = True
                output_result.flagged = True
        except Exception as exc:  # noqa: BLE001 - fail closed on ANY guardrail failure
            output_result.attempted = True
            output_result.flagged = True
            output_result.error_kind = type(exc).__name__
            logger.exception("Output guardrail failed for a permitted request")

        if claim_verifier is not None:
            try:
                verification = claim_verifier.verify(generated)
                claim_meta = build_audit_meta(verification)
            except Exception as exc:  # noqa: BLE001 - defensive depth; verify() never raises
                logger.exception("Claim/evidence verification stage failed unexpectedly")
                failure = unverified_failure_response(
                    type(exc).__name__,
                    error_kind="verification_failed",
                )
                claim_meta = build_audit_meta(failure)
            effective_decision = policy_engine.evaluate(
                risk,
                user_role,
                input_type=input_type,
                trajectory=trajectory,
                claims=claim_meta.assessment,
            )

    return llm_result, output_result, claim_meta, effective_decision, generated


def _generation_response(
    *,
    request_id: str,
    decision: PolicyDecision,
    risk: RiskAssessment,
    llm_result: LLMResult,
    output_result: OutputGuardrailResult,
    generated: str | None,
    action: PolicyAction,
    conversation_id: str,
    user_role: str,
    audit_prompt: str,
    original_prompt: str | None = None,
    sanitized_prompt: str | None = None,
    input_type: str = "text",
    optical_findings: list | None = None,
    optical: OpticalAuditMeta | None = None,
    sanitization: SanitizationAuditMeta | None = None,
    claim_verification: ClaimVerificationMeta | None = None,
    extra: dict[str, object] | None = None,
) -> dict[str, object] | JSONResponse:
    """Shared response shaping after generation / output-guardrail / claims."""
    if decision.action != action:
        # Post-generation re-evaluation degraded the outcome (EVIDENCE-001 on
        # unsupported/contradicted claims): route to review instead of ever
        # returning the generated content.
        return _claims_review_response(decision=decision, risk=risk, extra=extra)

    if llm_result.attempted and not llm_result.succeeded:
        return JSONResponse(
            status_code=503,
            content={
                "detail": "The request passed policy review, but response generation is "
                "temporarily unavailable.",
                "action": action.value,
                "request_id": request_id,
            },
        )

    output_flagged = output_result.flagged
    effective = _effective_action(decision, output_flagged=output_flagged)
    pipeline_failure = decision.policy_id in {
        "ERROR-FAIL-CLOSED",
        "DEFAULT-FAIL-CLOSED",
        "CLASSIFIER-FAIL-CLOSED",
    }

    body: dict[str, object] = {
        "decision": decision,
        "risk_assessment": risk,
    }
    if output_flagged:
        body.update(_flagged_for_review_response())
    else:
        body["action"] = action.value
        body["response"] = generated
    if extra:
        body.update(extra)

    explanation = _attach_explanation(
        body,
        request_id=request_id,
        risk=risk,
        decision=decision,
        effective_action=effective,
        input_type=input_type,
        optical_findings=optical_findings,
        original_prompt=original_prompt,
        sanitized_prompt=sanitized_prompt,
        llm_result=llm_result,
        output_result=output_result,
        pipeline_failure=pipeline_failure,
    )
    _save_evaluation_snapshot(
        request_id=request_id,
        conversation_id=conversation_id,
        user_role=user_role,
        decision=decision,
        effective=effective,
        prompt=original_prompt or audit_prompt,
        input_type=input_type,
    )
    _audit_from_explanation(
        conversation_id=conversation_id,
        prompt=audit_prompt,
        user_role=user_role,
        risk=risk,
        decision=decision,
        explanation=explanation,
        llm=llm_result,
        output_guardrail=output_result,
        optical=optical,
        sanitization=sanitization,
        claim_verification=claim_verification,
    )
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
    request_id: str,
    decision: PolicyDecision,
    risk: RiskAssessment,
    conversation_id: str,
    user_role: str,
    audit_prompt: str,
    original_prompt: str | None = None,
    input_type: str = "text",
    optical: OpticalAuditMeta | None = None,
    sanitization: SanitizationAuditMeta | None = None,
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
    effective = PolicyAction.REVIEW
    explanation = _attach_explanation(
        body,
        request_id=request_id,
        risk=risk,
        decision=decision,
        effective_action=effective,
        input_type=input_type,
        original_prompt=original_prompt,
        pipeline_failure=True,
    )
    _save_evaluation_snapshot(
        request_id=request_id,
        conversation_id=conversation_id,
        user_role=user_role,
        decision=decision,
        effective=effective,
        prompt=original_prompt or audit_prompt,
        input_type=input_type,
    )
    _audit_from_explanation(
        conversation_id=conversation_id,
        prompt=audit_prompt,
        user_role=user_role,
        risk=risk,
        decision=decision,
        explanation=explanation,
        llm=LLMResult(attempted=False, succeeded=False),
        optical=optical,
        sanitization=sanitization,
    )
    return body


@app.post("/guardrail/evaluate")
async def evaluate(
    request: GuardrailRequest,
    verified_role: str = Depends(get_verified_role),
):
    request_id = str(uuid.uuid4())
    risk = _classify_with_nemo(request)
    trajectory = evaluate_conversation(request.conversation_id, risk)
    decision = policy_engine.evaluate(risk, verified_role, trajectory=trajectory)
    pipeline_failure = decision.policy_id in {
        "ERROR-FAIL-CLOSED",
        "DEFAULT-FAIL-CLOSED",
    }

    # BLOCK / REVIEW / CLARIFY (and any non-ALLOW/REWRITE): stop — no LLM.
    if decision.action not in (PolicyAction.ALLOW, PolicyAction.REWRITE):
        effective = _effective_action(decision, pipeline_failure=pipeline_failure)
        body: dict[str, object] = {
            "decision": decision,
            "risk_assessment": risk,
            "input_type": "text",
            **_stop_response(effective),
        }
        explanation = _attach_explanation(
            body,
            request_id=request_id,
            risk=risk,
            decision=decision,
            effective_action=effective,
            input_type="text",
            original_prompt=request.prompt,
            pipeline_failure=pipeline_failure,
        )
        _save_evaluation_snapshot(
            request_id=request_id,
            conversation_id=request.conversation_id,
            user_role=verified_role,
            decision=decision,
            effective=effective,
            prompt=request.prompt,
            input_type="text",
        )
        _audit_from_explanation(
            conversation_id=request.conversation_id,
            prompt=request.prompt,
            user_role=verified_role,
            risk=risk,
            decision=decision,
            explanation=explanation,
            llm=LLMResult(attempted=False, succeeded=False),
        )
        return body

    sanitization_meta: SanitizationAuditMeta | None = None
    prompt_for_llm: str
    audit_prompt = request.prompt
    extra: dict[str, object] = {"input_type": "text"}

    if decision.action == PolicyAction.REWRITE:
        san_result = _run_sanitization(SanitizationRequest(text=request.prompt, source_type="text"))
        if not san_result.success:
            sanitization_meta = _sanitization_audit_meta(san_result, input_type="text", used=False)
            return _fail_closed_review_response(
                request_id=request_id,
                decision=decision,
                risk=risk,
                conversation_id=request.conversation_id,
                user_role=verified_role,
                audit_prompt=_TEXT_SANITIZED_AUDIT_PROMPT,
                original_prompt=request.prompt,
                input_type="text",
                sanitization=sanitization_meta,
                extra=extra,
            )

        prompt_for_llm = san_result.sanitized_text
        sanitization_meta = _sanitization_audit_meta(san_result, input_type="text", used=True)
        audit_prompt = _TEXT_SANITIZED_AUDIT_PROMPT
        extra["sanitization_applied"] = True
        extra["sanitized"] = True
        extra["sanitized_text"] = prompt_for_llm
    else:
        prompt_for_llm = request.prompt

    initial_action = decision.action
    llm_result, output_result, claim_meta, decision, generated = await _generate_and_guard(
        prompt_for_llm=prompt_for_llm,
        risk=risk,
        user_role=verified_role,
        trajectory=trajectory,
        decision=decision,
    )

    return _generation_response(
        request_id=request_id,
        decision=decision,
        risk=risk,
        llm_result=llm_result,
        output_result=output_result,
        generated=generated,
        action=initial_action,
        conversation_id=request.conversation_id,
        user_role=verified_role,
        audit_prompt=audit_prompt,
        original_prompt=request.prompt,
        sanitized_prompt=prompt_for_llm if decision.action == PolicyAction.REWRITE else None,
        input_type="text",
        sanitization=sanitization_meta,
        claim_verification=claim_meta,
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
    if nemo_input_rail is not None:
        risk = nemo_input_rail.augment_risk(
            GuardrailRequest(prompt=optical.ocr_text, conversation_id=conversation_id),
            risk,
        )
    trajectory = evaluate_conversation(conversation_id, risk)
    decision = policy_engine.evaluate(
        risk, verified_role, input_type="image", trajectory=trajectory
    )
    from services.multimodal.policy_bridge import apply_multimodal_image_policy

    decision = apply_multimodal_image_policy(optical, risk, decision)

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
    request_id = str(uuid.uuid4())
    pipeline_failure = decision.policy_id in {
        "ERROR-FAIL-CLOSED",
        "DEFAULT-FAIL-CLOSED",
    }
    if decision.action not in (PolicyAction.ALLOW, PolicyAction.REWRITE):
        effective = _effective_action(decision, pipeline_failure=pipeline_failure)
        body: dict[str, object] = {
            "decision": decision,
            "risk_assessment": risk,
            "optical_assessment": optical_public,
            "input_type": "image",
            **_stop_response(effective),
        }
        explanation = _attach_explanation(
            body,
            request_id=request_id,
            risk=risk,
            decision=decision,
            effective_action=effective,
            input_type="image",
            optical_findings=optical.findings,
            pipeline_failure=pipeline_failure,
        )
        _save_evaluation_snapshot(
            request_id=request_id,
            conversation_id=conversation_id,
            user_role=verified_role,
            decision=decision,
            effective=effective,
            prompt=optical.ocr_text,
            input_type="image",
        )
        _audit_from_explanation(
            conversation_id=conversation_id,
            prompt=_IMAGE_AUDIT_PROMPT,
            user_role=verified_role,
            risk=risk,
            decision=decision,
            explanation=explanation,
            llm=LLMResult(attempted=False, succeeded=False),
            optical=optical_meta,
        )
        return body

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
            return _fail_closed_review_response(
                request_id=request_id,
                decision=decision,
                risk=risk,
                conversation_id=conversation_id,
                user_role=verified_role,
                audit_prompt=_IMAGE_AUDIT_PROMPT,
                original_prompt=optical.ocr_text,
                input_type="image",
                optical=optical_meta,
                sanitization=sanitization_meta,
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

    initial_action = decision.action
    llm_result, output_result, claim_meta, decision, generated = await _generate_and_guard(
        prompt_for_llm=prompt_for_llm,
        risk=risk,
        user_role=verified_role,
        trajectory=trajectory,
        decision=decision,
        input_type="image",
    )

    return _generation_response(
        request_id=request_id,
        decision=decision,
        risk=risk,
        llm_result=llm_result,
        output_result=output_result,
        generated=generated,
        action=initial_action,
        conversation_id=conversation_id,
        user_role=verified_role,
        audit_prompt=audit_prompt,
        original_prompt=optical.ocr_text,
        sanitized_prompt=prompt_for_llm if decision.action == PolicyAction.REWRITE else None,
        input_type="image",
        optical_findings=optical.findings,
        optical=optical_meta,
        sanitization=sanitization_meta,
        claim_verification=claim_meta,
        extra=extra,
    )


class RephraseRequest(BaseModel):
    request_id: str
    conversation_id: str
    prompt: str


class ReviewRequestBody(BaseModel):
    request_id: str
    conversation_id: str
    note: str | None = None


class DecisionReportBody(BaseModel):
    request_id: str
    conversation_id: str
    comment: str | None = None


@app.post("/guardrail/rephrase")
async def guardrail_rephrase(
    body: RephraseRequest,
    verified_role: str = Depends(get_verified_role),
):
    """Suggest a safer rephrasing without forwarding anything to the LLM."""
    risk = _classify_with_nemo(
        GuardrailRequest(prompt=body.prompt, conversation_id=body.conversation_id)
    )
    decision = policy_engine.evaluate(risk, verified_role)
    suggested = build_rephrase_suggestion(
        risk=risk,
        decision=decision,
        original_prompt=body.prompt,
    )
    explanation = build_explainable_decision(
        request_id=body.request_id,
        risk=risk,
        decision=decision,
        input_type="text",
        original_prompt=body.prompt,
    )
    log_event(
        AuditEvent(
            conversation_id=body.conversation_id,
            prompt="[rephrase request]",
            user_role=verified_role,
            risk_assessment=risk,
            policy_decision=decision,
            request_id=body.request_id,
            resolution_type=ResolutionType.REPHRASE.value,
            forwarded_to_llm=False,
        )
    )
    return {
        "suggested_prompt": suggested,
        "explanation": explanation.model_dump(mode="json"),
    }


@app.post("/guardrail/review-requests")
async def create_review_request(
    body: ReviewRequestBody,
    verified_role: str = Depends(get_verified_role),
):
    """Submit a guardrail decision for human review. Does not contact the LLM."""
    snapshot = review_store.get_evaluation(body.request_id)
    if snapshot is None:
        raise HTTPException(status_code=404, detail="Evaluation not found.")
    if snapshot.conversation_id != body.conversation_id:
        raise HTTPException(status_code=400, detail="Conversation mismatch.")
    if snapshot.effective_decision == PolicyAction.BLOCK:
        raise HTTPException(
            status_code=400,
            detail="Blocked requests cannot be submitted for human review.",
        )
    if snapshot.effective_decision != PolicyAction.REVIEW:
        raise HTTPException(
            status_code=400,
            detail="Only review-required decisions can be submitted for human review.",
        )
    review = review_store.create_review_request(
        evaluation_request_id=body.request_id,
        conversation_id=body.conversation_id,
        user_role=verified_role,
        effective_decision=snapshot.effective_decision,
        note=body.note,
    )
    log_event(
        AuditEvent(
            conversation_id=body.conversation_id,
            prompt="[human review requested]",
            user_role=verified_role,
            risk_assessment=RiskAssessment(risk_level=RiskLevel.MEDIUM),
            policy_decision=PolicyDecision(
                action=snapshot.policy_action,
                policy_id="REVIEW-REQUEST",
                policy_version="0.0.0",
            ),
            request_id=body.request_id,
            human_review_requested=True,
            forwarded_to_llm=False,
        )
    )
    return {
        "review_request_id": review.review_request_id,
        "status": review.status.value,
    }


@app.post("/guardrail/review-requests/{review_request_id}/approve")
async def approve_review_request(
    review_request_id: str,
    verified_role: str = Depends(get_verified_role),
):
    _require_reviewer_role(verified_role)
    updated = review_store.update_review_status(
        review_request_id,
        status=ReviewRequestStatus.APPROVED,
        approver=verified_role,
        outcome="APPROVED",
    )
    if updated is None:
        raise HTTPException(status_code=404, detail="Review request not found or not pending.")
    return {"review_request_id": review_request_id, "status": updated.status.value}


@app.post("/guardrail/review-requests/{review_request_id}/reject")
async def reject_review_request(
    review_request_id: str,
    verified_role: str = Depends(get_verified_role),
):
    _require_reviewer_role(verified_role)
    updated = review_store.update_review_status(
        review_request_id,
        status=ReviewRequestStatus.REJECTED,
        approver=verified_role,
        outcome="REJECTED",
    )
    if updated is None:
        raise HTTPException(status_code=404, detail="Review request not found or not pending.")
    return {"review_request_id": review_request_id, "status": updated.status.value}


@app.post("/guardrail/review-requests/{review_request_id}/forward")
async def forward_review_request(
    review_request_id: str,
    verified_role: str = Depends(get_verified_role),
):
    """Forward an approved review request through the full guardrail pipeline."""
    review = review_store.get_review_request(review_request_id)
    if review is None:
        raise HTTPException(status_code=404, detail="Review request not found.")
    if review.status != ReviewRequestStatus.APPROVED:
        raise HTTPException(status_code=403, detail="Review request is not approved.")

    snapshot = review_store.get_evaluation(review.evaluation_request_id)
    if snapshot is None:
        raise HTTPException(status_code=404, detail="Original evaluation not found.")

    request_id = str(uuid.uuid4())
    req = GuardrailRequest(prompt=snapshot.prompt, conversation_id=snapshot.conversation_id)
    risk = _classify_with_nemo(req)
    decision = policy_engine.evaluate(risk, verified_role)

    if decision.action == PolicyAction.BLOCK:
        raise HTTPException(
            status_code=403,
            detail="Guardrail still blocks this content; human approval does not bypass safety.",
        )

    # Approved human review may forward REVIEW/CLARIFY decisions; BLOCK never passes.
    if decision.action not in (PolicyAction.ALLOW, PolicyAction.REWRITE, PolicyAction.REVIEW):
        raise HTTPException(
            status_code=403,
            detail="Guardrail requires further review; content was not forwarded.",
        )

    prompt_for_llm = snapshot.prompt
    sanitization_meta: SanitizationAuditMeta | None = None
    audit_prompt = snapshot.prompt

    if decision.action == PolicyAction.REWRITE:
        san_result = _run_sanitization(
            SanitizationRequest(text=snapshot.prompt, source_type=snapshot.input_type)
        )
        if not san_result.success:
            raise HTTPException(
                status_code=403,
                detail="Sanitization failed; content was not forwarded.",
            )
        prompt_for_llm = san_result.sanitized_text
        audit_prompt = _TEXT_SANITIZED_AUDIT_PROMPT
        sanitization_meta = _sanitization_audit_meta(
            san_result, input_type=snapshot.input_type, used=True
        )

    initial_action = decision.action
    llm_result, output_result, claim_meta, decision, generated = await _generate_and_guard(
        prompt_for_llm=prompt_for_llm,
        risk=risk,
        user_role=verified_role,
        trajectory=evaluate_conversation(snapshot.conversation_id, risk),
        decision=decision,
        input_type=snapshot.input_type,
    )

    review_store.mark_forwarded(review_request_id)

    body = _generation_response(
        request_id=request_id,
        decision=decision,
        risk=risk,
        llm_result=llm_result,
        output_result=output_result,
        generated=generated,
        action=initial_action,
        conversation_id=snapshot.conversation_id,
        user_role=verified_role,
        audit_prompt=audit_prompt,
        original_prompt=snapshot.prompt,
        sanitized_prompt=prompt_for_llm if decision.action == PolicyAction.REWRITE else None,
        input_type=snapshot.input_type,
        sanitization=sanitization_meta,
        claim_verification=claim_meta,
        extra={"forwarded_after_review": True, "review_request_id": review_request_id},
    )
    if isinstance(body, JSONResponse):
        return body
    return body


@app.post("/guardrail/decision-reports")
async def report_decision(
    body: DecisionReportBody,
    verified_role: str = Depends(get_verified_role),
):
    """Report a potentially incorrect guardrail decision. Never forwards to LLM."""
    snapshot = review_store.get_evaluation(body.request_id)
    if snapshot is None:
        raise HTTPException(status_code=404, detail="Evaluation not found.")
    if snapshot.conversation_id != body.conversation_id:
        raise HTTPException(status_code=400, detail="Conversation mismatch.")
    report = review_store.create_report(
        evaluation_request_id=body.request_id,
        conversation_id=body.conversation_id,
        user_role=verified_role,
        comment=body.comment,
    )
    log_event(
        AuditEvent(
            conversation_id=body.conversation_id,
            prompt="[decision report]",
            user_role=verified_role,
            risk_assessment=RiskAssessment(risk_level=RiskLevel.MEDIUM),
            policy_decision=PolicyDecision(
                action=snapshot.policy_action,
                policy_id="DECISION-REPORT",
                policy_version="0.0.0",
            ),
            request_id=body.request_id,
            report_status="SUBMITTED",
            forwarded_to_llm=False,
        )
    )
    return {"report_id": report.report_id, "status": report.status}


@app.get("/audit/events")
def list_audit_events(
    conversation_id: str | None = None,
    limit: int = 50,
    verified_role: str = Depends(get_verified_role),
) -> list[AuditEvent]:
    """Read-only audit trail for the dashboard UI."""
    _ = verified_role
    return list_events(conversation_id=conversation_id, limit=limit)


# Static ContextGuard dashboard (apps/web). Mounted LAST so API routes win.
_WEB_DIR = Path(__file__).resolve().parents[1] / "web"
if _WEB_DIR.is_dir():
    app.mount(
        "/",
        StaticFiles(directory=_WEB_DIR, html=True),
        name="web",
    )

