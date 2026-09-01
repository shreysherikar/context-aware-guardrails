"""Append-only audit log for computer-use actions."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from domain.enums import RiskLevel
from domain.governance_enums import GovernanceDecision
from domain.governance_models import ComputerActionLog


class ComputerActionLogStore:
    def __init__(self, max_entries: int = 5000) -> None:
        self._logs: list[ComputerActionLog] = []
        self._max = max_entries

    def append(
        self,
        *,
        session_id: str,
        agent_id: str,
        request_id: str,
        action: str,
        target: str | None,
        decision: GovernanceDecision,
        risk_level: RiskLevel,
        executed: bool,
        reason: str,
        approval_id: str | None = None,
    ) -> ComputerActionLog:
        entry = ComputerActionLog(
            log_id=str(uuid.uuid4()),
            session_id=session_id,
            agent_id=agent_id,
            request_id=request_id,
            timestamp=datetime.now(timezone.utc),
            action=action,
            target=target,
            decision=decision,
            risk_level=risk_level,
            executed=executed,
            reason=reason,
            approval_id=approval_id,
        )
        self._logs.append(entry)
        if len(self._logs) > self._max:
            self._logs = self._logs[-self._max :]
        return entry

    def list_for_session(self, session_id: str, limit: int = 50) -> list[ComputerActionLog]:
        items = [l for l in self._logs if l.session_id == session_id]
        return items[-limit:]

    def list_recent(self, limit: int = 50) -> list[ComputerActionLog]:
        return self._logs[-limit:]

    def count(self) -> int:
        return len(self._logs)
