"""Store for evaluation snapshots, review requests, and decision reports.

SQLite local fallback by default; when DATABASE_URL is set the three tables live
in the shared PostgreSQL database (services/db.py).
"""

from __future__ import annotations

import os
import uuid
from datetime import UTC, datetime
from pathlib import Path

from domain.enums import PolicyAction, ReviewRequestStatus
from services import db
from services.guardrail_review.models import (
    DecisionReport,
    EvaluationSnapshot,
    GuardrailReviewRequest,
)

DB_PATH = Path(__file__).resolve().parents[2] / "guardrail_review.db"


_CREATE_EVALUATION_SNAPSHOTS = """
CREATE TABLE IF NOT EXISTS evaluation_snapshots (
    request_id TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL,
    user_role TEXT NOT NULL,
    effective_decision TEXT NOT NULL,
    policy_action TEXT NOT NULL,
    prompt TEXT NOT NULL,
    input_type TEXT NOT NULL,
    created_at TEXT NOT NULL
)
"""

_CREATE_REVIEW_REQUESTS = """
CREATE TABLE IF NOT EXISTS review_requests (
    review_request_id TEXT PRIMARY KEY,
    evaluation_request_id TEXT NOT NULL,
    conversation_id TEXT NOT NULL,
    user_role TEXT NOT NULL,
    effective_decision TEXT NOT NULL,
    status TEXT NOT NULL,
    note TEXT,
    approver TEXT,
    outcome TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
)
"""

_CREATE_DECISION_REPORTS = """
CREATE TABLE IF NOT EXISTS decision_reports (
    report_id TEXT PRIMARY KEY,
    evaluation_request_id TEXT NOT NULL,
    conversation_id TEXT NOT NULL,
    user_role TEXT NOT NULL,
    comment TEXT,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL
)
"""


def _get_conn() -> db.Connection:
    # GUARDRAIL_REVIEW_DB_PATH is read per connection so the location is
    # configurable (e.g. a volume path in Docker) without code changes. When
    # DATABASE_URL is set the shared PostgreSQL database replaces the local
    # file entirely.
    db_path = Path(os.getenv("GUARDRAIL_REVIEW_DB_PATH", str(DB_PATH)))
    conn = db.get_connection(db_path)
    conn.execute(_CREATE_EVALUATION_SNAPSHOTS)
    conn.execute(_CREATE_REVIEW_REQUESTS)
    conn.execute(_CREATE_DECISION_REPORTS)
    if db.is_postgres():
        # PostgreSQL DDL is transactional: persist the schema so the next
        # (separate) connection sees it. SQLite auto-commits DDL as today.
        conn.commit()
    return conn


class GuardrailReviewStore:
    def save_evaluation(self, snapshot: EvaluationSnapshot) -> None:
        params = (
            snapshot.request_id,
            snapshot.conversation_id,
            snapshot.user_role,
            snapshot.effective_decision.value,
            snapshot.policy_action.value,
            snapshot.prompt,
            snapshot.input_type,
            snapshot.created_at.isoformat(),
        )
        conn = _get_conn()
        try:
            if db.is_postgres():
                # PostgreSQL has no INSERT OR REPLACE; ON CONFLICT updates the
                # existing row with the snapshot's (same-PK) values.
                conn.execute(
                    """INSERT INTO evaluation_snapshots
                       (request_id, conversation_id, user_role, effective_decision,
                        policy_action, prompt, input_type, created_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                       ON CONFLICT (request_id) DO UPDATE SET
                           conversation_id = EXCLUDED.conversation_id,
                           user_role = EXCLUDED.user_role,
                           effective_decision = EXCLUDED.effective_decision,
                           policy_action = EXCLUDED.policy_action,
                           prompt = EXCLUDED.prompt,
                           input_type = EXCLUDED.input_type,
                           created_at = EXCLUDED.created_at""",
                    params,
                )
            else:
                conn.execute(
                    """INSERT OR REPLACE INTO evaluation_snapshots
                       (request_id, conversation_id, user_role, effective_decision,
                        policy_action, prompt, input_type, created_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    params,
                )
            conn.commit()
        finally:
            conn.close()

    def get_evaluation(self, request_id: str) -> EvaluationSnapshot | None:
        conn = _get_conn()
        try:
            row = conn.execute(
                """SELECT request_id, conversation_id, user_role, effective_decision,
                   policy_action, prompt, input_type, created_at
                   FROM evaluation_snapshots WHERE request_id = ?""",
                (request_id,),
            ).fetchone()
        finally:
            conn.close()
        if row is None:
            return None
        return EvaluationSnapshot(
            request_id=row[0],
            conversation_id=row[1],
            user_role=row[2],
            effective_decision=PolicyAction(row[3]),
            policy_action=PolicyAction(row[4]),
            prompt=row[5],
            input_type=row[6],
            created_at=datetime.fromisoformat(row[7]),
        )

    def create_review_request(
        self,
        *,
        evaluation_request_id: str,
        conversation_id: str,
        user_role: str,
        effective_decision: PolicyAction,
        note: str | None = None,
    ) -> GuardrailReviewRequest:
        review = GuardrailReviewRequest(
            review_request_id=str(uuid.uuid4()),
            evaluation_request_id=evaluation_request_id,
            conversation_id=conversation_id,
            user_role=user_role,
            effective_decision=effective_decision,
            note=note,
        )
        conn = _get_conn()
        try:
            conn.execute(
                """INSERT INTO review_requests
                   (review_request_id, evaluation_request_id, conversation_id, user_role,
                    effective_decision, status, note, approver, outcome, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    review.review_request_id,
                    review.evaluation_request_id,
                    review.conversation_id,
                    review.user_role,
                    review.effective_decision.value,
                    review.status.value,
                    review.note,
                    review.approver,
                    review.outcome,
                    review.created_at.isoformat(),
                    review.updated_at.isoformat(),
                ),
            )
            conn.commit()
        finally:
            conn.close()
        return review

    def get_review_request(self, review_request_id: str) -> GuardrailReviewRequest | None:
        conn = _get_conn()
        try:
            row = conn.execute(
                """SELECT review_request_id, evaluation_request_id, conversation_id, user_role,
                   effective_decision, status, note, approver, outcome, created_at, updated_at
                   FROM review_requests WHERE review_request_id = ?""",
                (review_request_id,),
            ).fetchone()
        finally:
            conn.close()
        if row is None:
            return None
        return GuardrailReviewRequest(
            review_request_id=row[0],
            evaluation_request_id=row[1],
            conversation_id=row[2],
            user_role=row[3],
            effective_decision=PolicyAction(row[4]),
            status=ReviewRequestStatus(row[5]),
            note=row[6],
            approver=row[7],
            outcome=row[8],
            created_at=datetime.fromisoformat(row[9]),
            updated_at=datetime.fromisoformat(row[10]),
        )

    def update_review_status(
        self,
        review_request_id: str,
        *,
        status: ReviewRequestStatus,
        approver: str,
        outcome: str,
    ) -> GuardrailReviewRequest | None:
        review = self.get_review_request(review_request_id)
        if review is None or review.status != ReviewRequestStatus.PENDING:
            return None
        updated = review.model_copy(
            update={
                "status": status,
                "approver": approver,
                "outcome": outcome,
                "updated_at": datetime.now(UTC),
            }
        )
        conn = _get_conn()
        try:
            conn.execute(
                """UPDATE review_requests SET status = ?, approver = ?, outcome = ?,
                   updated_at = ? WHERE review_request_id = ?""",
                (
                    updated.status.value,
                    updated.approver,
                    updated.outcome,
                    updated.updated_at.isoformat(),
                    review_request_id,
                ),
            )
            conn.commit()
        finally:
            conn.close()
        return updated

    def mark_forwarded(self, review_request_id: str) -> GuardrailReviewRequest | None:
        review = self.get_review_request(review_request_id)
        if review is None or review.status != ReviewRequestStatus.APPROVED:
            return None
        updated = review.model_copy(
            update={"status": ReviewRequestStatus.FORWARDED, "updated_at": datetime.now(UTC)}
        )
        conn = _get_conn()
        try:
            conn.execute(
                "UPDATE review_requests SET status = ?, updated_at = ? WHERE review_request_id = ?",
                (updated.status.value, updated.updated_at.isoformat(), review_request_id),
            )
            conn.commit()
        finally:
            conn.close()
        return updated

    def create_report(
        self,
        *,
        evaluation_request_id: str,
        conversation_id: str,
        user_role: str,
        comment: str | None = None,
    ) -> DecisionReport:
        report = DecisionReport(
            report_id=str(uuid.uuid4()),
            evaluation_request_id=evaluation_request_id,
            conversation_id=conversation_id,
            user_role=user_role,
            comment=comment,
        )
        conn = _get_conn()
        try:
            conn.execute(
                """INSERT INTO decision_reports
                   (report_id, evaluation_request_id, conversation_id, user_role,
                    comment, status, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    report.report_id,
                    report.evaluation_request_id,
                    report.conversation_id,
                    report.user_role,
                    report.comment,
                    report.status,
                    report.created_at.isoformat(),
                ),
            )
            conn.commit()
        finally:
            conn.close()
        return report


_store: GuardrailReviewStore | None = None


def get_review_store() -> GuardrailReviewStore:
    global _store
    if _store is None:
        _store = GuardrailReviewStore()
    return _store
