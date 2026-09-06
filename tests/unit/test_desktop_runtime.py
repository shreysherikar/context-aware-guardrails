"""Desktop environment and path helpers."""

import os
from pathlib import Path

from apps.desktop.paths import persist_jwt_secret, user_data_dir
from apps.desktop.runtime import configure_desktop_environment, pick_port


def test_persist_jwt_secret_reuses_existing_file(tmp_path):
    path = tmp_path / "jwt_secret"
    first = persist_jwt_secret(path)
    second = persist_jwt_secret(path)
    assert first == second
    assert len(first) >= 32
    assert path.read_text(encoding="utf-8").strip() == first


def test_user_data_dir_uses_localappdata(monkeypatch, tmp_path):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    assert user_data_dir() == tmp_path / "ContextGuard"


def test_configure_desktop_environment_sets_writable_paths(monkeypatch, tmp_path):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setenv("AUTH_DEV_MODE", "false")
    monkeypatch.delenv("AUTH_JWT_SECRET", raising=False)
    monkeypatch.delenv("POLICY_PATH", raising=False)
    monkeypatch.delenv("EVIDENCE_CORPUS_PATH", raising=False)
    monkeypatch.setenv("AUDIT_DB_PATH", str(tmp_path / "ignored.db"))
    monkeypatch.setenv("GOVERNANCE_AUDIT_DB_PATH", str(tmp_path / "ignored-gov.db"))
    monkeypatch.setenv("GUARDRAIL_REVIEW_DB_PATH", str(tmp_path / "ignored-review.db"))
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    monkeypatch.setenv("OPTICAL_OCR_PROVIDER", "mock")
    monkeypatch.delenv("LLM_GENERATION_PROVIDER", raising=False)
    monkeypatch.delenv("OLLAMA_MODEL", raising=False)
    monkeypatch.delenv("OLLAMA_BASE_URL", raising=False)
    monkeypatch.delenv("OLLAMA_TIMEOUT", raising=False)

    data_dir = configure_desktop_environment()

    assert data_dir == tmp_path / "ContextGuard"
    assert data_dir.is_dir()
    assert os.environ["AUTH_DEV_MODE"] == "true"
    assert os.environ["AUTH_JWT_SECRET"]
    assert Path(os.environ["AUDIT_DB_PATH"]) == data_dir / "audit.db"
    assert Path(os.environ["GOVERNANCE_AUDIT_DB_PATH"]) == data_dir / "governance_audit.db"
    assert Path(os.environ["GUARDRAIL_REVIEW_DB_PATH"]) == data_dir / "guardrail_review.db"
    assert Path(os.environ["POLICY_PATH"]).name == "policy.yaml"
    assert Path(os.environ["POLICY_PATH"]).is_file()
    assert Path(os.environ["EVIDENCE_CORPUS_PATH"]).name == "approved_sources.yaml"
    assert os.environ["LLM_GENERATION_PROVIDER"] == "ollama"
    assert os.environ["OLLAMA_MODEL"] == "llama3.2:3b"
    assert os.environ["OLLAMA_BASE_URL"] == "http://127.0.0.1:11434"


def test_pick_port_returns_open_localhost_port():
    port = pick_port()
    assert 1 <= port <= 65535
