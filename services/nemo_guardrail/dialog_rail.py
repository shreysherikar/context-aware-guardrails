"""NeMo dialog/conversation rail — multi-turn safety checks."""

from __future__ import annotations

import logging
from collections import defaultdict

from domain.models import GuardrailRequest, RiskAssessment
from services.nemo_guardrail.client import NeMoGuardrailsClient
from services.nemo_guardrail.normalizer import merge_nemo_into_risk

logger = logging.getLogger(__name__)

_MAX_TURNS = 20


class NeMoDialogRail:
    """Conversation-aware rail for agent multi-turn flows."""

    def __init__(self, client: NeMoGuardrailsClient) -> None:
        self._client = client
        self._history: dict[str, list[dict[str, str]]] = defaultdict(list)

    def record_assistant_turn(self, conversation_id: str, content: str) -> None:
        history = self._history[conversation_id]
        history.append({"role": "assistant", "content": content})
        if len(history) > _MAX_TURNS * 2:
            self._history[conversation_id] = history[-(_MAX_TURNS * 2) :]

    async def augment_risk_async(
        self,
        request: GuardrailRequest,
        risk: RiskAssessment,
    ) -> RiskAssessment:
        history = self._history[request.conversation_id]
        messages = [*history, {"role": "user", "content": request.prompt}]
        try:
            outcome = await self._client.check_dialog_async(messages)
        except Exception:
            logger.warning("NeMo dialog rail unavailable; failing closed", exc_info=True)
            from domain.enums import PolicyAction
            from services.nemo_guardrail.models import NeMoRailOutcome, NeMoRailStatus

            outcome = NeMoRailOutcome(
                status=NeMoRailStatus.INDETERMINATE,
                content=request.prompt,
                suggested_action=PolicyAction.REVIEW,
                fail_closed=True,
            )
        return merge_nemo_into_risk(risk, outcome)

    def augment_risk(
        self,
        request: GuardrailRequest,
        risk: RiskAssessment,
    ) -> RiskAssessment:
        """Sync wrapper for agent paths that are not async."""
        import asyncio

        return asyncio.run(self.augment_risk_async(request, risk))
