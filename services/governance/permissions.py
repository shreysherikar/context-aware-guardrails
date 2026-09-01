"""Centralized permission engine for pharma AI agent governance."""

from __future__ import annotations

from domain.governance_enums import (
    ActionPermission,
    DataPermission,
    RestrictedAction,
    ToolPermission,
)

# Restricted actions must NEVER be implicitly granted.
RESTRICTED_ACTIONS: frozenset[str] = frozenset(a.value for a in RestrictedAction)

ALL_DATA_PERMISSIONS: frozenset[str] = frozenset(p.value for p in DataPermission)
ALL_TOOL_PERMISSIONS: frozenset[str] = frozenset(p.value for p in ToolPermission)
ALL_ACTION_PERMISSIONS: frozenset[str] = frozenset(p.value for p in ActionPermission)

# Actions that always require human approval regardless of agent config.
GLOBAL_HUMAN_APPROVAL_ACTIONS: frozenset[str] = frozenset(
    {
        RestrictedAction.RELEASE_BATCH.value,
        RestrictedAction.SUBMIT_TO_REGULATOR.value,
        RestrictedAction.CHANGE_PRODUCTION_PROCESS.value,
        RestrictedAction.MODIFY_PATIENT_RECORD.value,
        RestrictedAction.ENROLL_PATIENT.value,
        RestrictedAction.ACTIVATE_TRIAL.value,
        RestrictedAction.LABEL_APPROVAL.value,
        RestrictedAction.PRESCRIBE.value,
        RestrictedAction.CHANGE_TREATMENT.value,
        RestrictedAction.MAKE_MEDICAL_DECISION.value,
    }
)


class PermissionEngine:
    """Evaluates whether an agent holds explicit permission for an action."""

    def has_permission(self, agent_permissions: set[str], requested: str) -> bool:
        if requested in RESTRICTED_ACTIONS:
            return False
        return requested in agent_permissions

    def check_permissions(
        self,
        agent_permissions: set[str],
        requested_actions: list[str],
    ) -> tuple[bool, list[str]]:
        """Return (all_granted, missing_permissions)."""
        missing: list[str] = []
        for action in requested_actions:
            if action in RESTRICTED_ACTIONS:
                missing.append(action)
            elif action not in agent_permissions:
                missing.append(action)
        return len(missing) == 0, missing

    def requires_human_approval(
        self,
        requested_action: str,
        agent_approval_required: set[str],
    ) -> bool:
        if requested_action in GLOBAL_HUMAN_APPROVAL_ACTIONS:
            return True
        if requested_action in RESTRICTED_ACTIONS:
            return requested_action in agent_approval_required
        return requested_action in agent_approval_required

    def is_restricted_action(self, action: str) -> bool:
        return action in RESTRICTED_ACTIONS
