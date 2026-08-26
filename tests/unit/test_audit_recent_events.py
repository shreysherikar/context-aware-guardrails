"""Regression tests for the trajectory-history window in get_recent_events().

get_recent_events() feeds the trajectory engine's analysis window. It must
return the MOST RECENT ``limit`` prior events for a conversation (a long
conversation has to be scored on its latest turns, not its earliest ones),
in chronological order so trend calculation remains correct.
"""

from domain.enums import PolicyAction, RiskLevel
from domain.models import AuditEvent, PolicyDecision, RiskAssessment
from services.audit.audit import get_recent_events, log_event

WINDOW_LIMIT = 10


def _seed(conversation_id: str, index: int) -> None:
    log_event(
        AuditEvent(
            conversation_id=conversation_id,
            prompt=f"turn-{index}",
            user_role="researcher",
            risk_assessment=RiskAssessment(risk_level=RiskLevel.LOW),
            policy_decision=PolicyDecision(
                action=PolicyAction.ALLOW, policy_id="LOW-001", policy_version="0.1.0"
            ),
        )
    )


def test_window_returns_only_latest_n_events_in_chronological_order(monkeypatch, tmp_path):
    monkeypatch.setenv("AUDIT_DB_PATH", str(tmp_path / "audit.db"))

    total = WINDOW_LIMIT + 5  # more events than the window holds
    conv = "long-conversation"
    for i in range(total):
        _seed(conv, i)

    recent = get_recent_events(conv, limit=WINDOW_LIMIT)

    # Exactly the latest ``limit`` turns — never the earliest ones — in
    # chronological order (oldest -> newest) for trend calculation.
    assert [e.prompt for e in recent] == [f"turn-{i}" for i in range(5, total)]
