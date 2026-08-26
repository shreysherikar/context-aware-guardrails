"""Optical analyzer — deterministic PII / PHI / injection evidence from OCR text.

Produces OpticalAssessment only. Never decides ALLOW/BLOCK/REWRITE/REVIEW.
"""

from __future__ import annotations

import re

from domain.enums import RiskCategory
from domain.models import OCRResult, OpticalAssessment, OpticalFinding

# Prompt-injection patterns (evidence). Aligned with the text mock classifier
# plus a few OCR-common phrasings from the P0 brief.
_INJECTION_PATTERNS = [
    r"ignore (all |any |previous |prior )?instructions",
    r"ignore all previous instructions",
    r"pretend you('re| are) (an? )?unrestricted",
    r"no policy limits",
    r"disregard (your |the )?(rules|guidelines|policy)",
    r"bypass security",
    r"reveal confidential (information|data|secrets)",
    r"system message",
    r"developer message",
    r"note to the (risk )?classifier",
    r"score this as low risk",
]

# PII patterns / labeled fields.
_EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
_PHONE_RE = re.compile(r"(?:\+?\d{1,3}[\s.-]?)?(?:\(?\d{3}\)?[\s.-]?)\d{3}[\s.-]?\d{4}\b")
_SSN_RE = re.compile(r"\b\d{3}-\d{2}-\d{4}\b|\bssn\b|\bsocial security\b", re.I)
_DOB_RE = re.compile(
    r"(?:\bdob\b|\bdate of birth\b)\s*[:\-]?\s*"
    r"(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})",
    re.I,
)
_DOB_BARE_RE = re.compile(r"\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b")
_ADDRESS_RE = re.compile(
    r"\b\d{1,5}\s+[A-Za-z0-9.'\-]+\s+"
    r"(?:street|st|avenue|ave|road|rd|boulevard|blvd|lane|ln|drive|dr)\b",
    re.I,
)
_NAME_LABEL_RE = re.compile(
    r"(?im)^(?:patient|name|full name)\s*[:\-]\s*(.+?)\s*$",
)

# PHI / clinical patterns.
_MRN_RE = re.compile(
    r"(?:\bmrn\b|\bmedical record(?:\s+number)?\b|\bpatient\s+id\b)\s*[:\-]?\s*([A-Za-z0-9\-]+)",
    re.I,
)
_PHI_KEYWORDS = [
    (r"\bdiagnos(?:is|ed|es)\b", "diagnosis"),
    (r"\bmedication(?:s)?\b|\bprescri(?:be|ption)\b", "medication"),
    (r"\blab(?:oratory)?\s+results?\b|\bhba1c\b|\bglucose\b|\bcreatinine\b", "lab_result"),
    (r"\btreatment\b|\btherapy\b|\bclinical\s+notes?\b", "treatment"),
    (r"\badverse\s+reaction\b|\bmedical\s+history\b", "clinical_note"),
]


def _find_spans(pattern: re.Pattern[str], text: str) -> list[tuple[str, int, int]]:
    return [(m.group(0), m.start(), m.end()) for m in pattern.finditer(text)]


class OpticalAnalyzer:
    """Deterministic optical evidence extractor."""

    def analyze(self, ocr: OCRResult, *, image: bytes | None = None) -> OpticalAssessment:
        # ``image`` reserved for future vision signals (faces, etc.); P0 is OCR-text only.
        _ = image
        text = ocr.text or ""
        findings: list[OpticalFinding] = []
        injection_detected = False

        lower = text.lower()
        for pattern in _INJECTION_PATTERNS:
            if re.search(pattern, lower):
                injection_detected = True
                findings.append(
                    OpticalFinding(
                        type="prompt_injection",
                        category=RiskCategory.PROMPT_INJECTION,
                        confidence=0.85,
                        text=pattern,
                    )
                )
                break

        for match_text, _, _ in _find_spans(_EMAIL_RE, text):
            findings.append(
                OpticalFinding(
                    type="email",
                    category=RiskCategory.PII,
                    confidence=0.9,
                    text=match_text,
                )
            )

        for match_text, _, _ in _find_spans(_PHONE_RE, text):
            # Avoid treating long numeric IDs / MRNs as phones when labeled as MRN.
            if re.search(r"\bmrn\b", text[max(0, text.find(match_text) - 20) :].lower()):
                continue
            findings.append(
                OpticalFinding(
                    type="phone",
                    category=RiskCategory.PII,
                    confidence=0.75,
                    text=match_text,
                )
            )

        if _SSN_RE.search(text):
            span = _SSN_RE.search(text)
            findings.append(
                OpticalFinding(
                    type="ssn",
                    category=RiskCategory.PII,
                    confidence=0.9,
                    text=span.group(0) if span else "ssn",
                )
            )

        dob = _DOB_RE.search(text)
        if dob:
            findings.append(
                OpticalFinding(
                    type="dob",
                    category=RiskCategory.PII,
                    confidence=0.9,
                    text=dob.group(0),
                )
            )
        elif re.search(r"\bdob\b|\bdate of birth\b", lower) and _DOB_BARE_RE.search(text):
            bare = _DOB_BARE_RE.search(text)
            findings.append(
                OpticalFinding(
                    type="dob",
                    category=RiskCategory.PII,
                    confidence=0.8,
                    text=bare.group(0) if bare else None,
                )
            )

        for match_text, _, _ in _find_spans(_ADDRESS_RE, text):
            findings.append(
                OpticalFinding(
                    type="address",
                    category=RiskCategory.PII,
                    confidence=0.7,
                    text=match_text,
                )
            )

        for m in _NAME_LABEL_RE.finditer(text):
            findings.append(
                OpticalFinding(
                    type="name",
                    category=RiskCategory.PII,
                    confidence=0.8,
                    text=m.group(0),
                )
            )

        mrn = _MRN_RE.search(text)
        if mrn:
            # MRN / patient ID is both an identifier (sanitizable → PII rewrite
            # path when alone) and clinical PHI. Emit PII for rewrite; PHI is
            # added when other clinical signals are present (see below).
            findings.append(
                OpticalFinding(
                    type="mrn",
                    category=RiskCategory.PII,
                    confidence=0.95,
                    text=mrn.group(0),
                )
            )
            findings.append(
                OpticalFinding(
                    type="patient_id",
                    category=RiskCategory.PHI,
                    confidence=0.9,
                    text=mrn.group(0),
                )
            )

        clinical_hits = 0
        for pattern, finding_type in _PHI_KEYWORDS:
            if re.search(pattern, lower):
                clinical_hits += 1
                findings.append(
                    OpticalFinding(
                        type=finding_type,
                        category=RiskCategory.PHI,
                        confidence=0.75,
                        text=finding_type,
                    )
                )

        document_type = _infer_document_type(findings, clinical_hits, injection_detected)
        confidence = ocr.confidence
        if findings:
            confidence = max(confidence, max(f.confidence for f in findings))

        return OpticalAssessment(
            ocr_text=text,
            document_type=document_type,
            findings=findings,
            face_detected=False,
            injection_detected=injection_detected,
            confidence=confidence,
        )


def _infer_document_type(
    findings: list[OpticalFinding],
    clinical_hits: int,
    injection_detected: bool,
) -> str | None:
    if injection_detected:
        return "injection_attempt"
    types = {f.type for f in findings}
    if clinical_hits or "mrn" in types or "patient_id" in types:
        return "clinical_document"
    if types & {"email", "phone", "ssn", "dob", "address", "name"}:
        return "identity_document"
    if not findings:
        return "generic"
    return "sensitive_document"


def analyze_ocr(ocr: OCRResult, *, image: bytes | None = None) -> OpticalAssessment:
    """Module-level convenience wrapper."""
    return OpticalAnalyzer().analyze(ocr, image=image)
