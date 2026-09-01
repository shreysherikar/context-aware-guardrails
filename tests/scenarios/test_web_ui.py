"""Static UI + API route wiring for the ContextGuard dashboard."""

from pathlib import Path

from fastapi.testclient import TestClient

from apps.api.main import app

client = TestClient(app)


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


def test_built_bundle_contains_resolution_labels():
    assets_dir = Path(__file__).resolve().parents[2] / "apps" / "web" / "assets"
    js_files = sorted(assets_dir.glob("index-*.js"), key=lambda p: p.stat().st_mtime, reverse=True)
    assert js_files, "Built JS bundle missing — run npm run build in apps/web-src"
    bundle = js_files[0].read_text(encoding="utf-8", errors="ignore")
    assert "Help Me Rephrase" in bundle or "Request Human Review" in bundle
