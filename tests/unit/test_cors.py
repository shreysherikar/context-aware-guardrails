"""CORS headers so a phone app can call the local API."""

from fastapi.testclient import TestClient

from apps.api.main import app

client = TestClient(app)


def test_cors_preflight_allows_mobile_origin():
    res = client.options(
        "/health",
        headers={
            "Origin": "https://localhost",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert res.status_code in {200, 204}
    assert res.headers.get("access-control-allow-origin") == "*"
