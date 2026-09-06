"""Guardrail agent — runs the pipeline and returns explanatory feedback."""

from __future__ import annotations

import hashlib
import logging
from typing import TYPE_CHECKING, Any

from domain.enums import PolicyAction
from domain.models import (
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
from services.agent.feedback import (
    build_corrections,
    build_issues,
    build_pharma_remediation,
    build_prompt_highlights,
    compose_deterministic_message,
    guardrail_was_triggered,
    issues_for_display,
)
from services.agent.messenger import compose_agent_message
from services.agent.models import AgentChatResponse, AgentCorrection
from services.agent.pharma_context import prompt_class_label
from services.agent.router import route_request
from services.agent.specialists.base import RoutingContext
from services.audit.audit import log_event
from services.document.intake import FileIntakeError, intake_file
from services.llm import LLMRequest
from services.optical_guardrail.normalizer import normalize_optical_assessment
from services.optical_guardrail.ocr import OCRError
from services.optical_guardrail.validation import (
    ImageValidationError,
    validate_chat_image,
)
from services.sanitization.models import SanitizationRequest, SanitizationResult
from services.web_bridge import augment_prompt_with_web_context, search_web
from services.web_bridge.models import WebSearchResult

if TYPE_CHECKING:
    from services.llm.gateway import LLMGateway
    from services.nemo_guardrail.dialog_rail import NeMoDialogRail
    from services.nemo_guardrail.input_rail import NeMoInputRail
    from services.optical_guardrail.analyzer import OpticalAnalyzer
    from services.optical_guardrail.ocr import OCRProvider
    from services.output_guardrail.guardrail import OutputGuardrail
    from services.policy_engine.engine import PolicyEngine
    from services.risk_engine.classifier import RiskClassifier
    from services.sanitization.engine import SanitizationEngine

logger = logging.getLogger(__name__)

_IMAGE_AUDIT_PROMPT = "[image input]"
_TEXT_SANITIZED_AUDIT_PROMPT = "[text input; sanitized]"


class GuardrailAgent:
    """Policy-gated assistant that explains outcomes and suggests corrections."""

    def __init__(
        self,
        *,
        classifier: RiskClassifier,
        policy_engine: PolicyEngine,
        gateway: LLMGateway | None,
        output_guardrail: OutputGuardrail | None,
        ocr_provider: OCRProvider,
        optical_analyzer: OpticalAnalyzer,
        sanitization_engine: SanitizationEngine,
        nemo_input_rail: NeMoInputRail | None = None,
        nemo_dialog_rail: NeMoDialogRail | None = None,
    ) -> None:
        self._classifier = classifier
        self._policy = policy_engine
        self._gateway = gateway
        self._output_guardrail = output_guardrail
        self._ocr = ocr_provider
        self._optical = optical_analyzer
        self._sanitizer = sanitization_engine
        self._nemo_input = nemo_input_rail
        self._nemo_dialog = nemo_dialog_rail

    async def chat_text(
        self,
        *,
        prompt: str,
        conversation_id: str,
        role: str,
        use_web_search: bool = False,
    ) -> AgentChatResponse:
        request = GuardrailRequest(prompt=prompt, conversation_id=conversation_id)
        risk = self._classifier.classify(request)
        risk = self._apply_nemo_rails(request, risk)
        decision = self._policy.evaluate(risk, role)
        routing = route_request(
            RoutingContext(prompt=prompt, input_type="text", use_web_search=use_web_search)
        )

        if decision.action not in (PolicyAction.ALLOW, PolicyAction.REWRITE):
            return await self._terminal_response(
                risk=risk,
                decision=decision,
                conversation_id=conversation_id,
                input_type="text",
                audit_prompt=prompt,
                role=role,
                original_prompt=prompt,
                routing=routing,
            )

        sanitized_text: str | None = None
        prompt_for_llm = prompt
        audit_prompt = prompt
        sanitization_meta: SanitizationAuditMeta | None = None

        if decision.action == PolicyAction.REWRITE:
            san = self._sanitize(SanitizationRequest(text=prompt, source_type="text"))
            if not san.success:
                sanitization_meta = self._san_meta(san, input_type="text", used=False)
                log_event(
                    AuditEvent(
                        conversation_id=conversation_id,
                        prompt=_TEXT_SANITIZED_AUDIT_PROMPT,
                        user_role=role,
                        risk_assessment=risk,
                        policy_decision=decision,
                        llm=LLMResult(attempted=False, succeeded=False),
                        sanitization=sanitization_meta,
                    )
                )
                review_decision = decision.model_copy(
                    update={"action": PolicyAction.REVIEW, "policy_id": "SANITIZATION-FAIL"}
                )
                return await self._terminal_response(
                    risk=risk,
                    decision=review_decision,
                    conversation_id=conversation_id,
                    input_type="text",
                    audit_prompt=audit_prompt,
                    role=role,
                    routing=routing,
                )
            prompt_for_llm = san.sanitized_text
            sanitized_text = san.sanitized_text
            audit_prompt = _TEXT_SANITIZED_AUDIT_PROMPT
            sanitization_meta = self._san_meta(san, input_type="text", used=True)

        web_result: WebSearchResult | None = None
        if routing.needs_web_search:
            web_result = await search_web(prompt_for_llm)
            if web_result.succeeded:
                prompt_for_llm = augment_prompt_with_web_context(
                    user_prompt=prompt_for_llm, web=web_result
                )

        llm_result, output_result, answer, output_flagged = await self._generate(
            prompt_for_llm, system_prompt=routing.system_prompt
        )

        log_event(
            AuditEvent(
                conversation_id=conversation_id,
                prompt=audit_prompt,
                user_role=role,
                risk_assessment=risk,
                policy_decision=decision,
                llm=llm_result,
                output_guardrail=output_result,
                sanitization=sanitization_meta,
            )
        )

        action = PolicyAction.REVIEW if output_flagged else decision.action
        if output_flagged:
            answer = None
        elif answer and self._nemo_dialog is not None:
            self._nemo_dialog.record_assistant_turn(conversation_id, answer)

        return await self._build_response(
            risk=risk,
            decision=decision
            if not output_flagged
            else decision.model_copy(update={"action": PolicyAction.REVIEW}),
            conversation_id=conversation_id,
            input_type="text",
            action=action,
            answer=answer,
            sanitized_text=sanitized_text,
            output_flagged=output_flagged,
            original_prompt=prompt,
            llm_failed=llm_result.attempted and not llm_result.succeeded,
            no_gateway=self._gateway is None,
            web_result=web_result,
            routing=routing,
        )

    async def chat_image(
        self,
        *,
        image_bytes: bytes,
        content_type: str | None,
        conversation_id: str,
        role: str,
        user_message: str = "",
    ) -> AgentChatResponse:
        image_sha256 = hashlib.sha256(image_bytes).hexdigest() if image_bytes else None

        try:
            validated = validate_chat_image(image_bytes, declared_content_type=content_type)
        except ImageValidationError as exc:
            return AgentChatResponse(
                conversation_id=conversation_id,
                action=PolicyAction.BLOCK,
                message=f"Image rejected: {exc.message}",
                issues=[],
                corrections=[
                    AgentCorrection(
                        title="Use a valid image",
                        description="Upload a readable image under the size limit.",
                    )
                ],
                input_type="image",
                blocked=True,
            )

        try:
            ocr_result = await self._ocr.extract(validated.data)
        except OCRError:
            return AgentChatResponse(
                conversation_id=conversation_id,
                action=PolicyAction.BLOCK,
                message=(
                    "Could not read text from the image. Try a clearer photo or use the text tab."
                ),
                input_type="image",
                blocked=True,
            )

        optical: OpticalAssessment = self._optical.analyze(ocr_result, image=validated.data)
        risk = normalize_optical_assessment(optical)
        ocr_request = GuardrailRequest(prompt=optical.ocr_text, conversation_id=conversation_id)
        risk = self._apply_nemo_rails(ocr_request, risk)
        decision = self._policy.evaluate(risk, role, input_type="image")
        from services.multimodal.policy_bridge import apply_multimodal_image_policy

        decision = apply_multimodal_image_policy(optical, risk, decision)
        combined_prompt = self._combine_image_prompt(optical.ocr_text, user_message)
        routing = route_request(RoutingContext(prompt=combined_prompt, input_type="image"))

        optical_meta = OpticalAuditMeta(
            input_type="image",
            ocr_used=True,
            optical_analysis_used=True,
            document_type=optical.document_type,
            finding_count=len(optical.findings),
            sanitization_applied=False,
            image_sha256=image_sha256,
        )

        if decision.action not in (PolicyAction.ALLOW, PolicyAction.REWRITE):
            log_event(
                AuditEvent(
                    conversation_id=conversation_id,
                    prompt=_IMAGE_AUDIT_PROMPT,
                    user_role=role,
                    risk_assessment=risk,
                    policy_decision=decision,
                    llm=LLMResult(attempted=False, succeeded=False),
                    optical=optical_meta,
                )
            )
            return await self._terminal_response(
                risk=risk,
                decision=decision,
                conversation_id=conversation_id,
                input_type="image",
                audit_prompt=_IMAGE_AUDIT_PROMPT,
                role=role,
                optical_findings=optical.findings,
                original_prompt=combined_prompt,
                routing=routing,
            )

        sanitized_text: str | None = None
        prompt_for_llm = combined_prompt
        audit_prompt = _IMAGE_AUDIT_PROMPT
        sanitization_meta: SanitizationAuditMeta | None = None

        if decision.action == PolicyAction.REWRITE:
            san = self._sanitize(
                SanitizationRequest(
                    text=optical.ocr_text,
                    source_type="image",
                    optical_findings=optical.findings,
                )
            )
            if not san.success:
                sanitization_meta = self._san_meta(san, input_type="image", used=False)
                log_event(
                    AuditEvent(
                        conversation_id=conversation_id,
                        prompt=_IMAGE_AUDIT_PROMPT,
                        user_role=role,
                        risk_assessment=risk,
                        policy_decision=decision,
                        llm=LLMResult(attempted=False, succeeded=False),
                        optical=optical_meta,
                        sanitization=sanitization_meta,
                    )
                )
                review_decision = decision.model_copy(
                    update={"action": PolicyAction.REVIEW, "policy_id": "SANITIZATION-FAIL"}
                )
                return await self._terminal_response(
                    risk=risk,
                    decision=review_decision,
                    conversation_id=conversation_id,
                    input_type="image",
                    audit_prompt=audit_prompt,
                    role=role,
                    optical_findings=optical.findings,
                    routing=routing,
                )
            prompt_for_llm = self._combine_image_prompt(san.sanitized_text, user_message)
            sanitized_text = san.sanitized_text
            audit_prompt = "[image input; sanitized]"
            sanitization_meta = self._san_meta(san, input_type="image", used=True)
            optical_meta = optical_meta.model_copy(update={"sanitization_applied": True})

        llm_result, output_result, answer, output_flagged = await self._generate(
            prompt_for_llm, system_prompt=routing.system_prompt
        )

        log_event(
            AuditEvent(
                conversation_id=conversation_id,
                prompt=audit_prompt,
                user_role=role,
                risk_assessment=risk,
                policy_decision=decision,
                llm=llm_result,
                output_guardrail=output_result,
                optical=optical_meta,
                sanitization=sanitization_meta,
            )
        )

        action = PolicyAction.REVIEW if output_flagged else decision.action
        if output_flagged:
            answer = None
        elif answer and self._nemo_dialog is not None:
            self._nemo_dialog.record_assistant_turn(conversation_id, answer)

        return await self._build_response(
            risk=risk,
            decision=decision
            if not output_flagged
            else decision.model_copy(update={"action": PolicyAction.REVIEW}),
            conversation_id=conversation_id,
            input_type="image",
            action=action,
            answer=answer,
            sanitized_text=sanitized_text,
            output_flagged=output_flagged,
            optical_findings=optical.findings,
            original_prompt=combined_prompt,
            llm_failed=llm_result.attempted and not llm_result.succeeded,
            no_gateway=self._gateway is None,
            routing=routing,
        )

    async def chat_document(
        self,
        *,
        document_bytes: bytes,
        filename: str,
        conversation_id: str,
        role: str,
        user_message: str = "",
    ) -> AgentChatResponse:
        """Chat with a document attachment (legacy PDF endpoint)."""
        return await self.chat_file(
            file_bytes=document_bytes,
            filename=filename,
            content_type="application/pdf",
            conversation_id=conversation_id,
            role=role,
            user_message=user_message,
        )

    async def chat_file(
        self,
        *,
        file_bytes: bytes,
        filename: str,
        content_type: str | None,
        conversation_id: str,
        role: str,
        user_message: str = "",
    ) -> AgentChatResponse:
        """Chat with any supported upload — images via OCR, documents via text extraction."""
        try:
            intake = intake_file(file_bytes, filename=filename, content_type=content_type)
        except FileIntakeError as exc:
            return AgentChatResponse(
                conversation_id=conversation_id,
                action=PolicyAction.BLOCK,
                message=f"File rejected: {exc.message}",
                issues=[],
                corrections=[
                    AgentCorrection(
                        title="Use a readable file",
                        description=(
                            "Upload an image, PDF, Word (.docx), Excel (.xlsx), CSV, "
                            "plain text, or JSON under 10 MB."
                        ),
                    )
                ],
                input_type="file",
                blocked=True,
                guardrail_triggered=True,
            )

        if intake.kind == "image" and intake.image_bytes is not None:
            result = await self.chat_image(
                image_bytes=intake.image_bytes,
                content_type=intake.content_type,
                conversation_id=conversation_id,
                role=role,
                user_message=user_message,
            )
            return result.model_copy(update={"input_type": "file"})

        combined = self._combine_document_prompt(intake.text or "", user_message, intake.filename)
        result = await self.chat_text(
            prompt=combined,
            conversation_id=conversation_id,
            role=role,
        )
        return result.model_copy(update={"input_type": "file"})

    async def _terminal_response(
        self,
        *,
        risk: RiskAssessment,
        decision: PolicyDecision,
        conversation_id: str,
        input_type: str,
        audit_prompt: str,
        role: str,
        optical_findings: list | None = None,
        original_prompt: str | None = None,
        routing: Any | None = None,
    ) -> AgentChatResponse:
        log_event(
            AuditEvent(
                conversation_id=conversation_id,
                prompt=audit_prompt,
                user_role=role,
                risk_assessment=risk,
                policy_decision=decision,
                llm=LLMResult(attempted=False, succeeded=False),
            )
        )
        return await self._build_response(
            risk=risk,
            decision=decision,
            conversation_id=conversation_id,
            input_type=input_type,
            action=decision.action,
            optical_findings=optical_findings,
            original_prompt=original_prompt,
            routing=routing,
        )

    async def _build_response(
        self,
        *,
        risk: RiskAssessment,
        decision: PolicyDecision,
        conversation_id: str,
        input_type: str,
        action: PolicyAction,
        answer: str | None = None,
        sanitized_text: str | None = None,
        output_flagged: bool = False,
        optical_findings: list | None = None,
        original_prompt: str | None = None,
        llm_failed: bool = False,
        no_gateway: bool = False,
        web_result: WebSearchResult | None = None,
        routing: Any | None = None,
    ) -> AgentChatResponse:
        issues = build_issues(
            risk,
            input_type=input_type,
            optical_findings=optical_findings or None,
            original_prompt=original_prompt,
        )
        for issue in issues:
            if issue.why is None:
                issue.why = issue.description

        display_issues = issues_for_display(action, issues, output_flagged=output_flagged)
        highlights = build_prompt_highlights(original_prompt, display_issues)
        triggered = guardrail_was_triggered(
            action,
            display_issues,
            output_flagged=output_flagged,
            blocked=action == PolicyAction.BLOCK,
            review_required=action == PolicyAction.REVIEW or output_flagged,
        )

        corrections = build_corrections(action, display_issues, decision=decision)
        clarify_q, suggested = build_pharma_remediation(original_prompt or "")
        message = await compose_agent_message(
            action=action,
            issues=display_issues,
            corrections=corrections,
            answer=answer,
            sanitized_text=sanitized_text,
            output_flagged=output_flagged,
            input_type=input_type,
            gateway=self._gateway,
            clarification_questions=clarify_q,
            suggested_rewrite=suggested,
        )
        if not message or not message.strip():
            message = compose_deterministic_message(
                action=action,
                issues=display_issues,
                corrections=corrections,
                answer=answer,
                sanitized_text=sanitized_text,
                output_flagged=output_flagged,
                clarification_questions=clarify_q,
                suggested_rewrite=suggested,
            )
        if action == PolicyAction.ALLOW and not answer and not output_flagged:
            if no_gateway:
                message = (
                    "No AI model is configured. Set LLM_GENERATION_PROVIDER=ollama in your "
                    ".env file and restart the server."
                )
            elif llm_failed:
                message = (
                    "I couldn't reach the local AI model. Open a terminal and run:\n"
                    "  ollama serve\n"
                    "  ollama pull llama3.2:3b\n"
                    "Then try again."
                )
        return AgentChatResponse(
            conversation_id=conversation_id,
            action=action,
            message=message,
            issues=display_issues,
            corrections=corrections if triggered else [],
            clarification_questions=clarify_q if triggered else [],
            suggested_rewrite=suggested if triggered else None,
            prompt_class=prompt_class_label(action.value, risk.risk_level) if triggered else None,
            answer=answer,
            sanitized_text=sanitized_text if triggered else None,
            input_type=input_type,
            policy_id=decision.policy_id if triggered else None,
            blocked=action == PolicyAction.BLOCK,
            review_required=action == PolicyAction.REVIEW or output_flagged,
            web_search_used=bool(web_result and web_result.succeeded),
            web_sources=[
                {"title": s.title, "url": s.url, "snippet": s.snippet}
                for s in (web_result.sources if web_result else [])
            ],
            active_agents=routing.active_agents if routing else [],
            primary_agent=routing.primary_name if routing else None,
            guardrail_triggered=triggered,
            highlights=highlights if triggered else [],
        )

    async def _generate(
        self, prompt_for_llm: str, *, system_prompt: str | None = None
    ) -> tuple[LLMResult, OutputGuardrailResult, str | None, bool]:
        llm_result = LLMResult(attempted=False, succeeded=False)
        output_result = OutputGuardrailResult(attempted=False, flagged=False)
        generated: str | None = None
        output_flagged = False

        try:
            if self._gateway is not None:
                llm_result.attempted = True
                response = await self._gateway.generate(
                    LLMRequest(prompt=prompt_for_llm, system_prompt=system_prompt)
                )
                generated = response.text
                llm_result.succeeded = True
        except Exception:  # noqa: BLE001
            logger.exception("Agent LLM generation failed")

        if generated and llm_result.succeeded and self._output_guardrail is not None:
            try:
                output_result.attempted = True
                assessment = await self._output_guardrail.check(prompt_for_llm, generated)
                if assessment.safe_text:
                    generated = assessment.safe_text
                if assessment.blocked:
                    output_result.flagged = True
                    output_flagged = not bool(assessment.safe_text)
                elif assessment.flagged:
                    output_result.flagged = True
                    output_flagged = True
            except Exception as exc:  # noqa: BLE001
                output_result.attempted = True
                output_result.flagged = True
                output_result.error_kind = type(exc).__name__
                output_flagged = True

        return llm_result, output_result, generated, output_flagged

    def _apply_nemo_rails(
        self,
        request: GuardrailRequest,
        risk: RiskAssessment,
    ) -> RiskAssessment:
        """Apply NeMo dialog (preferred) or input rails before policy evaluation."""
        if self._nemo_dialog is not None:
            return self._nemo_dialog.augment_risk(request, risk)
        if self._nemo_input is not None:
            return self._nemo_input.augment_risk(request, risk)
        return risk

    def _sanitize(self, request: SanitizationRequest) -> SanitizationResult:
        return self._sanitizer.sanitize(request)

    @staticmethod
    def _combine_document_prompt(
        extracted_text: str, user_message: str = "", filename: str = ""
    ) -> str:
        msg = (user_message or "").strip()
        body = (extracted_text or "").strip()
        label = (filename or "document").strip()
        doc_block = f"[Text from PDF: {label}]\n{body}"
        if msg and body:
            return f"{msg}\n\n{doc_block}"
        if msg:
            return msg
        return doc_block

    @staticmethod
    def _combine_image_prompt(ocr_text: str, user_message: str = "") -> str:
        msg = (user_message or "").strip()
        ocr = (ocr_text or "").strip()
        if msg and ocr:
            return f"{msg}\n\n[Text from image]\n{ocr}"
        if msg:
            return msg
        return ocr

    @staticmethod
    def _san_meta(
        result: SanitizationResult, *, input_type: str, used: bool
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
