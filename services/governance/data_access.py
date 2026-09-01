"""Data access control — agents may only access permitted classifications."""

from __future__ import annotations

from domain.governance_enums import DataClassification


class DataAccessController:
    def is_allowed(
        self,
        allowed: set[DataClassification],
        requested: DataClassification,
    ) -> bool:
        return requested in allowed

    def check(
        self,
        allowed: list[DataClassification],
        requested: DataClassification,
    ) -> tuple[bool, str | None]:
        allowed_set = set(allowed)
        if self.is_allowed(allowed_set, requested):
            return True, None
        return False, (
            f"Agent not permitted to access {requested.value} data "
            f"(allowed: {[c.value for c in allowed]})"
        )
