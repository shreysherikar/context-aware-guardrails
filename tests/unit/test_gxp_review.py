"""Unit tests for GxP compliance review."""

from fastapi.testclient import TestClient

from apps.api.main import app
from services.gxp.reviewer import review_text

client = TestClient(app)

SAMPLE_NONCOMPLIANT = (
    "The investigator may skip informed consent for convenience and backdate signatures. "
    "Batch release without QC is permitted. Do not report SAEs within 24 hours."
)

SAMPLE_COMPLIANT = (
    "Obtain documented informed consent per protocol. "
    "Complete QC testing and QA batch disposition before release."
)


def test_review_detects_gxp_issues():
    result = review_text(SAMPLE_NONCOMPLIANT)
    assert not result.compliant
    assert result.finding_count >= 3
    assert len(result.highlights) >= 3
    assert "GCP" in result.gxp_frameworks_applied
    assert "skip informed consent" in result.original_text.lower()
    assert "skip informed consent" not in result.rewritten_text.lower()


def test_review_compliant_text():
    result = review_text(SAMPLE_COMPLIANT)
    assert result.compliant
    assert result.finding_count == 0
    assert result.rewritten_text == SAMPLE_COMPLIANT


def test_highlights_have_spans():
    result = review_text(SAMPLE_NONCOMPLIANT)
    for h in result.highlights:
        assert h.start < h.end
        assert result.original_text[h.start : h.end] == h.text
        assert h.gxp_frameworks
        assert h.suggested_replacement


def test_gxp_review_api():
    resp = client.post("/gxp/review", json={"text": SAMPLE_NONCOMPLIANT})
    assert resp.status_code == 200
    data = resp.json()
    assert data["compliant"] is False
    assert data["finding_count"] >= 3
    assert data["rewritten_text"]


def test_gxp_frameworks_endpoint():
    resp = client.get("/gxp/frameworks")
    assert resp.status_code == 200
    codes = {f["code"] for f in resp.json()}
    assert "GCP" in codes
    assert "GMP" in codes


def test_gxp_review_empty_text_rejected():
    resp = client.post("/gxp/review", json={"text": "   "})
    assert resp.status_code == 400
