"""Security event store for governance violations."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from domain.governance_enums import (
    GovernanceDecision,
    SecurityEventCategory,
    SecurityEventSeverity,
)
from domain.governance_models import SecurityEvent


class SecurityEventStore:
    def __init__(self) -> None:
        self._events: list[SecurityEvent] = []

    def record(
        self,
        *,
        agent_id: str,
        category: SecurityEventCategory,
        description: str,
        request_id: str | None = None,
        policy_decision: GovernanceDecision | None = None,
        evidence: dict | None = None,
        severity: SecurityEventSeverity | None = None,
    ) -> SecurityEvent:
        sev = severity or _category_severity(category)
        event = SecurityEvent(
            event_id=str(uuid.uuid4()),
            agent_id=agent_id,
            timestamp=datetime.now(timezone.utc),
            severity=sev,
            category=category,
            request_id=request_id,
            description=description,
            policy_decision=policy_decision,
            evidence=evidence or {},
        )
        self._events.append(event)
        return event

    def list_recent(self, limit: int = 50) -> list[SecurityEvent]:
        return list(reversed(self._events[-limit:]))

    def count(self) -> int:
        return len(self._events)


def _category_severity(category: SecurityEventCategory) -> SecurityEventSeverity:
    critical = {
        SecurityEventCategory.PRIVILEGE_ESCALATION,
        SecurityEventCategory.POLICY_BYPASS,
        SecurityEventCategory.APPROVAL_BYPASS,
        SecurityEventCategory.DARKWEB_DATA_EXFILTRATION,
        SecurityEventCategory.DARKWEB_COMPUTER_USE_ATTEMPT,
        SecurityEventCategory.SECURITY_POLICY_BYPASS,
        SecurityEventCategory.GUARDRAIL_BYPASS_ATTEMPT,
        SecurityEventCategory.DATA_EXFILTRATION_ATTEMPT,
        SecurityEventCategory.MALWARE_EXECUTION_ATTEMPT,
        SecurityEventCategory.MANUFACTURING_SAFETY_VIOLATION,
    }
    high = {
        SecurityEventCategory.UNAUTHORIZED_ACCESS,
        SecurityEventCategory.RESTRICTED_DATA_ACCESS,
        SecurityEventCategory.AUDIT_FAILURE,
        SecurityEventCategory.DARKWEB_ACCESS_ATTEMPT,
        SecurityEventCategory.DARKWEB_NAVIGATION_ATTEMPT,
        SecurityEventCategory.DARKWEB_SEARCH_ATTEMPT,
        SecurityEventCategory.DARKWEB_TOOL_USE_ATTEMPT,
        SecurityEventCategory.NETWORK_CONTROL_BYPASS,
        SecurityEventCategory.PROMPT_INJECTION,
        SecurityEventCategory.IMAGE_PROMPT_INJECTION,
        SecurityEventCategory.VISUAL_AUTHORITY_SPOOFING,
        SecurityEventCategory.PHISHING_ATTEMPT,
        SecurityEventCategory.COMPUTER_USE_MANIPULATION,
        SecurityEventCategory.MALICIOUS_URL,
        SecurityEventCategory.NETWORK_BYPASS_ATTEMPT,
        SecurityEventCategory.REGULATORY_MANIPULATION_ATTEMPT,
        SecurityEventCategory.CLINICAL_SAFETY_VIOLATION,
    }
    if category in critical:
        return SecurityEventSeverity.CRITICAL
    if category in high:
        return SecurityEventSeverity.HIGH
    return SecurityEventSeverity.MEDIUM
