"""Static demo UI wiring: GET / serves apps/web/index.html; API routes intact.

apps/api/main.py mounts the static demo page at "/" via FastAPI StaticFiles,
mounted AFTER every API route so it can never shadow them. This test guards
both halves of that wiring: the root path serves the demo page, and the
existing API surface still routes as before.
"""

from fastapi.testclient import TestClient

from apps.api.main import app

client = TestClient(app)


def test_root_serves_demo_ui():
    resp = client.get("/")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/html")
    body = resp.text
    # Marker content from apps/web/index.html.
    assert "ContextGuard AI" in body
    assert "/auth/dev-token" in body
    assert "/guardrail/evaluate" in body
    # Role dropdown values used by the demo UI.
    assert 'value="employee"' in body
    assert 'value="manager"' in body
    assert 'value="compliance_officer"' in body


def test_static_mount_does_not_shadow_api_routes():
    # Liveness route still reachable (not swallowed by the "/" mount).
    assert client.get("/health").status_code == 200

    # Guardrail route still reachable — missing auth must yield 401 (the API's
    # own handling), never a static 404/200 from the mount.
    resp = client.post(
        "/guardrail/evaluate",
        json={"prompt": "Summarize this internal document.", "conversation_id": "web-ui-test"},
    )
    assert resp.status_code == 401
