"""
Trajectory engine — deterministic conversation-level risk scoring
(services/trajectory_engine).

Detects multi-turn "slow boil" patterns — repeated sensitive-category probing,
a non-decreasing risk trend, or several MEDIUM+ risk turns — even when each
individual turn alone would not escalate. Deterministic counting /
pattern-matching over the stored audit log only; no LLM / classifier is ever
invoked to evaluate history.

STRUCTURAL CONSTRAINT: this component is incapable of producing a
PolicyDecision. It returns TrajectoryAssessment (evidence: an escalate flag +
reason, exactly like OpticalAssessment), and only the PolicyEngine decides.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence

from domain.enums import RiskCategory, RiskLevel
from domain.models import RiskAssessment, TrajectoryAssessment
from services.audit.audit import get_recent_events

logger = logging.getLogger(__name__)

# How many prior turns (plus the current turn) the window considers.
DEFAULT_WINDOW_LIMIT = 10
# Trajectory escalates once this many turns in the window sit at MEDIUM+.
MIN_MEDIUM_OR_ABOVE_TURNS = 2

_RISK_RANK = {
    RiskLevel.LOW: 0,
    RiskLevel.MEDIUM: 1,
    RiskLevel.HIGH: 2,
    RiskLevel.CRITICAL: 3,
}


def _is_non_decreasing_trend(levels: Sequence[RiskLevel]) -> bool:
    """Precise trend definition over the enum ordering.

    A window is a "non-decreasing trend" iff every successive turn's risk_level
    is >= the previous turn's (using LOW < MEDIUM < HIGH < CRITICAL) AND at
    least one comparison is a strict increase. All-equal windows are not a
    trend. Windows of length < 2 are not a trend.
    """
    if len(levels) < 2:
        return False
    strict_increase_seen = False
    previous = levels[0]
    for current in levels[1:]:
        if _RISK_RANK[current] < _RISK_RANK[previous]:
            return False
        if _RISK_RANK[current] > _RISK_RANK[previous]:
            strict_increase_seen = True
        previous = current
    return strict_increase_seen


class TrajectoryEngine:
    """Deterministic trajectory scorer. Evidence only — never a decision."""

    def score(self, window: Sequence[RiskAssessment]) -> TrajectoryAssessment:
        """Score the combined window (prior turns + current turn, each once)."""
        levels = [assessment.risk_level for assessment in window]

        medium_or_above = sum(
            1 for level in levels if _RISK_RANK[level] >= _RISK_RANK[RiskLevel.MEDIUM]
        )

        # Repeated category: any real (non-NONE) category appearing in more than
        # one turn. NONE is excluded because every harmless turn carries it.
        repeated_category: RiskCategory | None = None
        seen: set[RiskCategory] = set()
        for assessment in window:
            for category in assessment.categories:
                if category is RiskCategory.NONE:
                    continue
                if category in seen:
                    repeated_category = category
                seen.add(category)

        trend = _is_non_decreasing_trend(levels)

        reasons: list[str] = []
        if medium_or_above >= MIN_MEDIUM_OR_ABOVE_TURNS:
            reasons.append(f"{medium_or_above} turns in this conversation at MEDIUM risk or above")
        if repeated_category is not None:
            reasons.append(f"category {repeated_category.value} appears in multiple turns")
        if trend:
            reasons.append("risk levels are non-decreasing with at least one increase")

        escalate = (
            medium_or_above >= MIN_MEDIUM_OR_ABOVE_TURNS or repeated_category is not None or trend
        )
        return TrajectoryAssessment(
            escalate=escalate,
            reason="; ".join(reasons) if reasons else "no trajectory escalation signals",
            medium_or_above_count=medium_or_above,
            repeated_category=repeated_category,
            non_decreasing_trend=trend,
        )


def evaluate_conversation(
    conversation_id: str,
    current_assessment: RiskAssessment,
    *,
    window_limit: int = DEFAULT_WINDOW_LIMIT,
) -> TrajectoryAssessment:
    """Load prior audit history and score prior + current exactly once.

    The window passed to the scorer is ``prior_events + [current_assessment]``
    — the current turn is appended exactly once and is never re-fetched from
    the audit store (it cannot be there yet: log_event runs after the policy
    decision).

    Fail-closed on history-lookup failure: if the audit-history lookup throws,
    trajectory escalates to REVIEW rather than silently degrading to
    single-turn policy. This ensures the fail-closed principle applies across
    all authoritative gates, not just the primary policy engine.
    """
    try:
        prior_events = get_recent_events(conversation_id, limit=window_limit)
    except Exception:  # noqa: BLE001 - deliberate fail-closed with logged warning
        logger.warning(
            "Trajectory history lookup failed for conversation %r; failing closed to REVIEW",
            conversation_id,
            exc_info=True,
        )
        return TrajectoryAssessment(
            escalate=True,
            reason="trajectory history lookup failed; failing closed to REVIEW",
        )

    prior_assessments = [event.risk_assessment for event in prior_events]
    window = [*prior_assessments, current_assessment]
    return TrajectoryEngine().score(window)
