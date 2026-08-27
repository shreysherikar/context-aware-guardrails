"""Unit tests for the deterministic trajectory engine (services/trajectory_engine).

Pins the exact signal definitions: the non-decreasing trend rule, repeated
non-NONE category probing, MEDIUM+ turn counting, the no-double-count window
guarantee, the fail-closed behaviour on history-lookup failure, and the
structural constraint that TrajectoryAssessment carries no policy action.
"""

from domain.enums import PolicyAction, RiskCategory, RiskLevel
from domain.models import (
    AuditEvent,
    PolicyDecision,
    RiskAssessment,
    TrajectoryAssessment,
)
from services.audit.audit import log_event
from services.trajectory_engine.engine import TrajectoryEngine, evaluate_conversation

_engine = TrajectoryEngine()


def _ra(level: RiskLevel, *categories: RiskCategory) -> RiskAssessment:
    return RiskAssessment(
        risk_level=level,
        categories=list(categories) or [RiskCategory.NONE],
    )


# --- trend definition (exact sequences from the spec) -----------------------


def test_non_decreasing_trend_exact_definition():
    # Spec: [LOW, LOW, MEDIUM, HIGH] is a trend.
    assert (
        _engine.score(
            [_ra(RiskLevel.LOW), _ra(RiskLevel.LOW), _ra(RiskLevel.MEDIUM), _ra(RiskLevel.HIGH)]
        ).non_decreasing_trend
        is True
    )
    # Spec: [LOW, MEDIUM, LOW, HIGH] is NOT a trend (decrease at MEDIUM->LOW).
    assert (
        _engine.score(
            [_ra(RiskLevel.LOW), _ra(RiskLevel.MEDIUM), _ra(RiskLevel.LOW), _ra(RiskLevel.HIGH)]
        ).non_decreasing_trend
        is False
    )
    # Spec: [MEDIUM, MEDIUM, MEDIUM] is NOT a trend (all equal, no strict increase).
    assert (
        _engine.score(
            [_ra(RiskLevel.MEDIUM), _ra(RiskLevel.MEDIUM), _ra(RiskLevel.MEDIUM)]
        ).non_decreasing_trend
        is False
    )


def test_trend_requires_at_least_two_turns():
    assert _engine.score([_ra(RiskLevel.LOW)]).non_decreasing_trend is False


def test_all_equal_high_window_is_not_a_trend():
    assert _engine.score([_ra(RiskLevel.HIGH), _ra(RiskLevel.HIGH)]).non_decreasing_trend is False


def test_two_step_strict_increase_is_a_trend():
    assert _engine.score([_ra(RiskLevel.MEDIUM), _ra(RiskLevel.HIGH)]).non_decreasing_trend is True


def test_decrease_breaks_trend():
    assert _engine.score([_ra(RiskLevel.HIGH), _ra(RiskLevel.LOW)]).non_decreasing_trend is False


# --- repeated category signal -------------------------------------------------


def test_repeated_same_category_escalates():
    result = _engine.score(
        [_ra(RiskLevel.LOW, RiskCategory.PII), _ra(RiskLevel.LOW, RiskCategory.PII)]
    )
    assert result.escalate is True
    assert result.repeated_category == RiskCategory.PII


def test_none_category_repetition_is_ignored():
    # Every harmless turn carries NONE; its repetition must not be a signal.
    result = _engine.score([_ra(RiskLevel.LOW), _ra(RiskLevel.LOW)])
    assert result.escalate is False
    assert result.repeated_category is None


def test_different_categories_across_turns_is_not_repetition():
    result = _engine.score(
        [_ra(RiskLevel.MEDIUM, RiskCategory.PII), _ra(RiskLevel.MEDIUM, RiskCategory.IP)]
    )
    assert result.repeated_category is None


def test_repetition_inside_a_single_turn_is_not_a_pattern():
    # One turn listing both PII and IP is a single occurrence of each category.
    result = _engine.score([_ra(RiskLevel.MEDIUM, RiskCategory.PII, RiskCategory.IP)])
    assert result.repeated_category is None


# --- MEDIUM-or-above counting -------------------------------------------------


def test_medium_or_above_count_accumulates():
    result = _engine.score([_ra(RiskLevel.LOW), _ra(RiskLevel.MEDIUM), _ra(RiskLevel.HIGH)])
    assert result.medium_or_above_count == 2


def test_medium_count_threshold_escalates():
    result = _engine.score([_ra(RiskLevel.MEDIUM), _ra(RiskLevel.MEDIUM)])
    assert result.escalate is True


def test_single_medium_turn_never_escalates():
    result = _engine.score([_ra(RiskLevel.MEDIUM)])
    assert result.escalate is False


# --- no double-count guarantee ------------------------------------------------


def test_window_is_prior_plus_current_exactly_once():
    prior = [_ra(RiskLevel.LOW), _ra(RiskLevel.MEDIUM)]
    current = _ra(RiskLevel.HIGH)
    window = [*prior, current]

    assert len(window) == len(prior) + 1
    # The current assessment appears exactly once, as the final element.
    assert sum(1 for item in window if item is current) == 1
    assert window[-1] is current

    result = _engine.score(window)
    assert result.medium_or_above_count == 2  # MEDIUM + HIGH; LOW excluded


def test_evaluate_conversation_counts_each_turn_once(monkeypatch, tmp_path):
    monkeypatch.setenv("AUDIT_DB_PATH", str(tmp_path / "audit.db"))
    conv = "double-count"
    for _ in range(2):
        log_event(
            AuditEvent(
                conversation_id=conv,
                prompt="prior probe",
                user_role="researcher",
                risk_assessment=_ra(RiskLevel.MEDIUM),
                policy_decision=PolicyDecision(
                    action=PolicyAction.REWRITE,
                    policy_id="PII-001",
                    policy_version="0.1.0",
                ),
            )
        )

    result = evaluate_conversation(conv, _ra(RiskLevel.MEDIUM))
    # 2 prior MEDIUM turns + 1 current MEDIUM turn, each counted exactly once.
    assert result.medium_or_above_count == 3


# --- fail-closed on history-lookup failure --------------------------------------


def test_history_lookup_failure_fails_closed(monkeypatch):
    def _boom(conversation_id: str, limit: int = 10):
        raise RuntimeError("database unavailable")

    monkeypatch.setattr("services.trajectory_engine.engine.get_recent_events", _boom)
    result = evaluate_conversation("any-conv", _ra(RiskLevel.HIGH))
    assert result.escalate is True
    assert "failed" in result.reason.lower()


# --- structural constraint: evidence only, never a decision --------------------


def test_trajectory_assessment_carries_no_policy_action():
    assessment = TrajectoryAssessment(escalate=True, reason="pattern")
    assert not hasattr(assessment, "action")
    assert not hasattr(assessment, "policy_id")
    assert not hasattr(assessment, "policy_version")
