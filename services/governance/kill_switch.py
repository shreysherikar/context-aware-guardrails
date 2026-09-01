"""Global emergency kill switch — exists outside agent runtime."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


class KillSwitch:
    """
    EMERGENCY_STOP halts agent execution, computer-use sessions,
    tool execution, and external communication.
    Agents cannot disable this control.
    """

    def __init__(self) -> None:
        self._active = False
        self._activated_at: datetime | None = None
        self._activated_by: str | None = None
        self._reason: str | None = None

    @property
    def is_active(self) -> bool:
        return self._active

    @property
    def reason(self) -> str | None:
        return self._reason

    def activate(self, *, by: str = "system", reason: str = "EMERGENCY_STOP") -> None:
        self._active = True
        self._activated_at = datetime.now(timezone.utc)
        self._activated_by = by
        self._reason = reason
        logger.critical("KILL SWITCH ACTIVATED by=%s reason=%s", by, reason)

    def deactivate(self, *, by: str = "system") -> None:
        self._active = False
        self._activated_at = None
        self._activated_by = by
        self._reason = None
        logger.warning("Kill switch deactivated by=%s", by)

    def check(self) -> tuple[bool, str | None]:
        """Return (allowed, block_reason). False means all execution blocked."""
        if self._active:
            return False, self._reason or "EMERGENCY_STOP active"
        return True, None


# Module-level singleton — outside agent control
_kill_switch = KillSwitch()


def get_kill_switch() -> KillSwitch:
    return _kill_switch
