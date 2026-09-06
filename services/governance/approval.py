"""Centralized human approval system."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from domain.enums import RiskLevel
from domain.governance_enums import ApprovalStatus
from domain.governance_models import ApprovalRequest


class ApprovalStore:
    def __init__(self, ttl_hours: int = 24) -> None:
        self._approvals: dict[str, ApprovalRequest] = {}
        self._ttl = timedelta(hours=ttl_hours)

    def create(
        self,
        *,
        requesting_agent: str,
        requested_action: str,
        reason: str,
        risk_level: RiskLevel,
        affected_resource: str | None = None,
        evidence: dict | None = None,
        request_id: str | None = None,
        user_id: str | None = None,
    ) -> ApprovalRequest:
        approval = ApprovalRequest(
            approval_request_id=str(uuid.uuid4()),
            requesting_agent=requesting_agent,
            requested_action=requested_action,
            reason=reason,
            affected_resource=affected_resource,
            risk_level=risk_level,
            evidence=evidence or {},
            request_id=request_id,
            user_id=user_id,
        )
        self._approvals[approval.approval_request_id] = approval
        return approval

    def get(self, approval_id: str) -> ApprovalRequest | None:
        approval = self._approvals.get(approval_id)
        if approval is None:
            return None
        self._expire_if_needed(approval)
        return self._approvals.get(approval_id)

    def approve(self, approval_id: str, approver: str) -> ApprovalRequest | None:
        approval = self.get(approval_id)
        if approval is None or approval.approval_status != ApprovalStatus.PENDING:
            return None
        updated = approval.model_copy(
            update={"approval_status": ApprovalStatus.APPROVED, "approver": approver}
        )
        self._approvals[approval_id] = updated
        return updated

    def reject(self, approval_id: str, approver: str) -> ApprovalRequest | None:
        approval = self.get(approval_id)
        if approval is None or approval.approval_status != ApprovalStatus.PENDING:
            return None
        updated = approval.model_copy(
            update={"approval_status": ApprovalStatus.REJECTED, "approver": approver}
        )
        self._approvals[approval_id] = updated
        return updated

    def is_valid(self, approval_id: str) -> bool:
        approval = self.get(approval_id)
        return approval is not None and approval.approval_status == ApprovalStatus.APPROVED

    def list_pending(self) -> list[ApprovalRequest]:
        return [a for a in self._approvals.values() if a.approval_status == ApprovalStatus.PENDING]

    def count_pending(self) -> int:
        return len(self.list_pending())

    def _expire_if_needed(self, approval: ApprovalRequest) -> None:
        if approval.approval_status != ApprovalStatus.PENDING:
            return
        age = datetime.now(UTC) - approval.timestamp
        if age > self._ttl:
            self._approvals[approval.approval_request_id] = approval.model_copy(
                update={"approval_status": ApprovalStatus.EXPIRED}
            )
