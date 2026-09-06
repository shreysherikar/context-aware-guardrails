"""Desktop CORS defaults and phone/Capacitor preflight."""

import json
import os
import subprocess
import sys
from pathlib import Path

from apps.desktop.runtime import configure_desktop_environment


def test_configure_desktop_environment_allows_mobile_origins(monkeypatch, tmp_path):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setenv("AUTH_DEV_MODE", "false")
    monkeypatch.delenv("ALLOWED_ORIGINS", raising=False)
    monkeypatch.delenv("AUTH_JWT_SECRET", raising=False)
    monkeypatch.setenv("SERVE_STATIC_FRONTEND", "false")
    monkeypatch.delenv("LLM_GENERATION_PROVIDER", raising=False)
    monkeypatch.delenv("OLLAMA_MODEL", raising=False)
    monkeypatch.delenv("OLLAMA_BASE_URL", raising=False)
    monkeypatch.delenv("OLLAMA_TIMEOUT", raising=False)
    monkeypatch.delenv("AUTH_PASSWORD_USERS", raising=False)

    configure_desktop_environment()

    origins = os.environ["ALLOWED_ORIGINS"]
    assert "https://localhost" in origins
    assert "capacitor://localhost" in origins
    assert os.environ["SERVE_STATIC_FRONTEND"] == "true"
    assert "clinician@contextguard.local" in os.environ["AUTH_PASSWORD_USERS"]


def test_desktop_api_serves_ui_and_allows_capacitor_origin(tmp_path):
    """Phone/Capacitor clients load the UI from the desktop API over CORS."""
    env = dict(os.environ)
    env["LOCALAPPDATA"] = str(tmp_path)
    env.pop("ALLOWED_ORIGINS", None)
    env.pop("AUTH_JWT_SECRET", None)
    env["SERVE_STATIC_FRONTEND"] = "false"
    env["LLM_PROVIDER"] = "mock"
    env["LLM_GENERATION_PROVIDER"] = ""
    env["OUTPUT_GUARDRAIL_PROVIDER"] = ""
    env["DATABASE_URL"] = ""
    env["AUTH_DEV_MODE"] = "false"

    repo = Path(__file__).resolve().parents[2]
    script = r"""
import json
from apps.desktop.runtime import configure_desktop_environment

configure_desktop_environment()
from apps.api.main import app
from fastapi.testclient import TestClient

client = TestClient(app)
html = client.get("/")
assert html.status_code == 200, html.text
assert "ContextGuard" in html.text
assert "/assets/" in html.text

for origin in ("https://localhost", "capacitor://localhost", "http://localhost"):
    preflight = client.options(
        "/auth/login",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )
    assert preflight.status_code == 200, origin
    assert preflight.headers.get("access-control-allow-origin") == origin, origin

login = client.post(
    "/auth/login",
    json={"email": "clinician@contextguard.local", "password": "clinician"},
    headers={"Origin": "https://localhost"},
)
assert login.status_code == 200, login.text
body = login.json()
assert body.get("token")
assert login.headers.get("access-control-allow-origin") == "https://localhost"
print(json.dumps({"ok": True}))
"""
    proc = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        env=env,
        cwd=repo,
        timeout=120,
    )
    assert proc.returncode == 0, f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
    assert json.loads(proc.stdout.strip().splitlines()[-1])["ok"] is True
