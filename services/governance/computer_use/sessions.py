"""Computer-use session lifecycle management."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from domain.enums import RiskLevel
from domain.governance_models import ComputerSession


class ComputerSessionStore:
    def __init__(self, default_ttl_minutes: int = 30) -> None:
        self._sessions: dict[str, ComputerSession] = {}
        self._default_ttl = timedelta(minutes=default_ttl_minutes)

    def create(
        self,
        *,
        agent_id: str,
        user_id: str | None = None,
        environment_id: str = "sandbox-default",
        allowed_domains: list[str] | None = None,
        allowed_apps: list[str] | None = None,
        allowed_directories: list[str] | None = None,
        blocked_directories: list[str] | None = None,
        allowed_actions: list[str] | None = None,
        risk_limit: RiskLevel = RiskLevel.MEDIUM,
        ttl_minutes: int | None = None,
    ) -> ComputerSession:
        now = datetime.now(UTC)
        ttl = timedelta(minutes=ttl_minutes) if ttl_minutes else self._default_ttl
        session = ComputerSession(
            session_id=str(uuid.uuid4()),
            agent_id=agent_id,
            user_id=user_id,
            environment_id=environment_id,
            start_time=now,
            expiry_time=now + ttl,
            allowed_domains=allowed_domains or [],
            allowed_apps=allowed_apps or [],
            allowed_directories=allowed_directories or [],
            blocked_directories=blocked_directories or [],
            allowed_actions=allowed_actions or [],
            risk_limit=risk_limit,
        )
        self._sessions[session.session_id] = session
        return session

    def get(self, session_id: str) -> ComputerSession | None:
        session = self._sessions.get(session_id)
        if session is None:
            return None
        if self._is_expired(session):
            self.stop(session_id)
            return None
        return session

    def stop(self, session_id: str) -> ComputerSession | None:
        session = self._sessions.get(session_id)
        if session is None:
            return None
        updated = session.model_copy(update={"active": False})
        self._sessions[session_id] = updated
        return updated

    def stop_all_for_agent(self, agent_id: str) -> int:
        count = 0
        for sid, session in list(self._sessions.items()):
            if session.agent_id == agent_id and session.active:
                self.stop(sid)
                count += 1
        return count

    def stop_all(self) -> int:
        count = 0
        for sid in list(self._sessions.keys()):
            if self._sessions[sid].active:
                self.stop(sid)
                count += 1
        return count

    def list_active(self) -> list[ComputerSession]:
        return [s for s in self._sessions.values() if s.active and not self._is_expired(s)]

    def count_active(self) -> int:
        return len(self.list_active())

    def update_state(
        self,
        session_id: str,
        *,
        current_application: str | None = None,
        current_domain: str | None = None,
        actions_executed: int | None = None,
        actions_blocked: int | None = None,
    ) -> ComputerSession | None:
        session = self.get(session_id)
        if session is None:
            return None
        updates: dict = {}
        if current_application is not None:
            updates["current_application"] = current_application
        if current_domain is not None:
            updates["current_domain"] = current_domain
        if actions_executed is not None:
            updates["actions_executed"] = actions_executed
        if actions_blocked is not None:
            updates["actions_blocked"] = actions_blocked
        updated = session.model_copy(update=updates)
        self._sessions[session_id] = updated
        return updated

    def _is_expired(self, session: ComputerSession) -> bool:
        return datetime.now(UTC) > session.expiry_time
