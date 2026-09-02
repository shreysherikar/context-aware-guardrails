"""Unit tests for governance permission engine."""

import pytest

from domain.governance_enums import RestrictedAction
from services.governance.permissions import RESTRICTED_ACTIONS, PermissionEngine


@pytest.fixture
def engine():
    return PermissionEngine()


def test_restricted_never_implicitly_granted(engine):
    perms = {"READ_LITERATURE", "CREATE_DRAFT", RestrictedAction.APPROVE.value}
    assert not engine.has_permission(set(perms), RestrictedAction.APPROVE.value)


def test_explicit_permission_granted(engine):
    perms = {"READ_LITERATURE", "CREATE_DRAFT"}
    assert engine.has_permission(set(perms), "READ_LITERATURE")


def test_missing_permission_detected(engine):
    ok, missing = engine.check_permissions({"READ_LITERATURE"}, ["READ_LITERATURE", "CREATE_CASE"])
    assert not ok
    assert "CREATE_CASE" in missing


def test_global_human_approval_release_batch(engine):
    assert engine.requires_human_approval(RestrictedAction.RELEASE_BATCH.value, set())


def test_all_restricted_actions_in_frozen_set():
    for action in RestrictedAction:
        assert action.value in RESTRICTED_ACTIONS
