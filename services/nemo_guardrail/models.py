"""Internal NeMo rail outcome models — not exposed to API consumers."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field

from domain.enums import PolicyAction


class NeMoRailStatus(StrEnum):
    """Normalized status from a NeMo rails check."""

    PASSED = "PASSED"
    MODIFIED = "MODIFIED"
    BLOCKED = "BLOCKED"
    INDETERMINATE = "INDETERMINATE"


class NeMoRailOutcome(BaseModel):
    """Internal outcome of a NeMo input, output, or dialog rail check.

    Maps NeMo's RailStatus into ContextGuard's decision vocabulary without
    leaking Colang flow names, thresholds, or provider details.
    """

    status: NeMoRailStatus
    content: str = ""
    suggested_action: PolicyAction | None = None
    fail_closed: bool = False
    rewrite_applied: bool = False
    internal_reason: str = Field(default="", repr=False)
