"""NeMo input rail — augments RiskAssessment before PolicyEngine evaluation."""

from __future__ import annotations

import logging

from domain.models import GuardrailRequest, RiskAssessment
from services.nemo_guardrail.client import NeMoGuardrailsClient
from services.nemo_guardrail.normalizer import merge_nemo_into_risk

logger = logging.getLogger(__name__)


class NeMoInputRail:
    """Defense-in-depth input rail. Never bypasses the policy engine."""

    def __init__(self, client: NeMoGuardrailsClient) -> None:
        self._client = client

    def augment_risk(
        self,
        request: GuardrailRequest,
        risk: RiskAssessment,
    ) -> RiskAssessment:
        """Run NeMo input rails and merge signals into the classifier output."""
        try:
            outcome = self._client.check_input_sync(request.prompt)
        except Exception:
            logger.warning("NeMo input rail unavailable; failing closed", exc_info=True)
            from domain.enums import PolicyAction
            from services.nemo_guardrail.models import NeMoRailOutcome, NeMoRailStatus

            outcome = NeMoRailOutcome(
                status=NeMoRailStatus.INDETERMINATE,
                content=request.prompt,
                suggested_action=PolicyAction.REVIEW,
                fail_closed=True,
            )
        return merge_nemo_into_risk(risk, outcome)
