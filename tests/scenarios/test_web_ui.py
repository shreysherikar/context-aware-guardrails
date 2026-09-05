"""Static UI + API route wiring for the ContextGuard dashboard."""

import json
import os
import subprocess
import sys
from pathlib import Path

from fastapi.testclient import TestClient

from apps.api.main import app

client = TestClient(app)


def _route_names(serve_static: str) -> list[str]:
    """Import apps/api/main in a clean subprocess and return route names.

    The subprocess inherits the offline test environment (tests/conftest.py) so
    no real provider is constructed; only SERVE_STATIC_FRONTEND and
    ALLOWED_ORIGINS are overridden to drive the static-mount gate deterministically.
    SERVE_STATIC_FRONTEND is set to an explicit value (not popped) so a developer's
    local .env cannot inject a different value via load_dotenv() in the child.
    """
    env = dict(os.environ)
    env["SERVE_STATIC_FRONTEND"] = serve_static
    env["ALLOWED_ORIGINS"] = "https://d123abc.cloudfront.net"
    script = (
        "from apps.api.main import app; "
        "import json; "
        "print(json.dumps(sorted(r.name for r in app.routes if hasattr(r, 'name'))))"
    )
    proc = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        env=env,
        cwd=Path(__file__).resolve().parents[2],
        timeout=120,
    )
    assert proc.returncode == 0, f"subprocess failed:\n{proc.stderr}"
    return json.loads(proc.stdout.strip().splitlines()[-1])


def test_root_serves_dashboard_html():
    res = client.get("/")
    assert res.status_code == 200
    assert res.headers["content-type"].startswith("text/html")
    assert "ContextGuard" in res.text
    assert "root" in res.text


def test_health_not_shadowed_by_static():
    res = client.get("/health")
    assert res.status_code == 200
    assert res.json()["status"] == "ok"


def test_evaluate_requires_auth():
    res = client.post(
        "/guardrail/evaluate",
        json={"prompt": "hello", "conversation_id": "ui-test"},
    )
    assert res.status_code == 401


def test_cors_preflight_echoes_allowed_origin():
    res = client.options(
        "/guardrail/evaluate",
        headers={
            "Origin": "https://d123abc.cloudfront.net",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "authorization, content-type",
        },
    )
    assert res.status_code == 200
    assert res.headers["access-control-allow-origin"] == "https://d123abc.cloudfront.net"
    assert res.headers["access-control-allow-credentials"] == "true"
    assert "POST" in res.headers.get("access-control-allow-methods", "")


def test_cors_preflight_rejects_unknown_origin():
    res = client.options(
        "/guardrail/evaluate",
        headers={
            "Origin": "https://evil.example.com",
            "Access-Control-Request-Method": "POST",
        },
    )
    assert res.status_code == 400
    assert "access-control-allow-origin" not in res.headers


def test_cors_simple_get_echoes_allowed_origin():
    res = client.get("/health", headers={"Origin": "http://localhost:5173"})
    assert res.status_code == 200
    assert res.headers["access-control-allow-origin"] == "http://localhost:5173"


def test_static_mount_off_by_default_without_serve_flag():
    assert "web" not in _route_names("")


def test_static_mount_off_when_serve_flag_is_false():
    assert "web" not in _route_names("false")


def test_static_mount_opt_in_when_serve_flag_is_true():
    assert "web" in _route_names("true")  # apps/web exists in the repo


def test_built_bundle_contains_resolution_labels():
    assets_dir = Path(__file__).resolve().parents[2] / "apps" / "web" / "assets"
    js_files = sorted(assets_dir.glob("index-*.js"), key=lambda p: p.stat().st_mtime, reverse=True)
    assert js_files, "Built JS bundle missing — run npm run build in apps/web-src"
    bundle = js_files[0].read_text(encoding="utf-8", errors="ignore")
    assert "Help Me Rephrase" in bundle or "Request Human Review" in bundle
