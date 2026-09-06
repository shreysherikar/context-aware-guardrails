"""Optical analyzer — deterministic PII / PHI / injection / multimodal evidence from OCR.

Produces OpticalAssessment only. Never decides ALLOW/BLOCK/REWRITE/REVIEW.
All image content is treated as UNTRUSTED by default.
"""

from __future__ import annotations

import re

from domain.enums import RiskCategory
from domain.models import OCRResult, OpticalAssessment, OpticalFinding
from services.multimodal.classifier import assess_multimodal_content

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

_CATEGORY_MAP: dict[str, RiskCategory] = {
    "IMAGE_PROMPT_INJECTION": RiskCategory.PROMPT_INJECTION,
    "POLICY_BYPASS_ATTEMPT": RiskCategory.PROMPT_INJECTION,
    "VISUAL_AUTHORITY_SPOOFING": RiskCategory.AUTHORITY_SPOOFING,
    "DATA_EXFILTRATION_ATTEMPT": RiskCategory.DATA_EXFILTRATION,
    "SECRET_EXPOSURE": RiskCategory.MULTIMODAL_UNTRUSTED,
    "MALICIOUS_URL": RiskCategory.CYBER_SAFETY,
    "NETWORK_BYPASS_ATTEMPT": RiskCategory.CYBER_SAFETY,
    "PHISHING_ATTEMPT": RiskCategory.PHISHING,
    "MALWARE_EXECUTION_ATTEMPT": RiskCategory.MALWARE,
    "COMPUTER_USE_MANIPULATION": RiskCategory.MULTIMODAL_UNTRUSTED,
    "REGULATORY_MANIPULATION_ATTEMPT": RiskCategory.MULTIMODAL_UNTRUSTED,
    "CLINICAL_SAFETY_VIOLATION": RiskCategory.PHI,
    "MANUFACTURING_SAFETY_VIOLATION": RiskCategory.MULTIMODAL_UNTRUSTED,
    "PRIVILEGE_ESCALATION_ATTEMPT": RiskCategory.PROMPT_INJECTION,
}


def _find_spans(pattern: re.Pattern[str], text: str) -> list[tuple[str, int, int]]:
    return [(m.group(0), m.start(), m.end()) for m in pattern.finditer(text)]


def _multimodal_to_findings(assessment) -> list[OpticalFinding]:
    findings: list[OpticalFinding] = []
    for el in assessment.elements:
        cat = _CATEGORY_MAP.get(el.threat_category or "", RiskCategory.MULTIMODAL_UNTRUSTED)
        findings.append(
            OpticalFinding(
                type=el.threat_category or "multimodal_threat",
                category=cat,
                confidence=0.88,
                text=el.content,
                trust=el.trust,
                threat_category=el.threat_category,
            )
        )
    return findings


class OpticalAnalyzer:
    """Deterministic optical evidence extractor with unified multimodal classification."""

    def analyze(self, ocr: OCRResult, *, image: bytes | None = None) -> OpticalAssessment:
        _ = image  # reserved for future pixel-level vision signals
        text = ocr.text or ""
        findings: list[OpticalFinding] = []
        injection_detected = False

        # Unified multimodal threat classification (all image OCR is untrusted)
        multimodal = assess_multimodal_content(text, source="image")
        findings.extend(_multimodal_to_findings(multimodal))
        injection_detected = multimodal.injection_detected or multimodal.policy_bypass

        lower = text.lower()
        for pattern in _INJECTION_PATTERNS:
            if re.search(pattern, lower):
                injection_detected = True
                if not any(f.type == "prompt_injection" for f in findings):
                    findings.append(
                        OpticalFinding(
                            type="prompt_injection",
                            category=RiskCategory.PROMPT_INJECTION,
                            confidence=0.85,
                            text=pattern,
                            trust="UNTRUSTED_INSTRUCTION",
                            threat_category="IMAGE_PROMPT_INJECTION",
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
                    trust="DATA",
                )
            )

        for match_text, _, _ in _find_spans(_PHONE_RE, text):
            if re.search(r"\bmrn\b", text[max(0, text.find(match_text) - 20) :].lower()):
                continue
            findings.append(
                OpticalFinding(
                    type="phone",
                    category=RiskCategory.PII,
                    confidence=0.75,
                    text=match_text,
                    trust="DATA",
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
                    trust="DATA",
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
                    trust="DATA",
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
                    trust="DATA",
                )
            )

        for match_text, _, _ in _find_spans(_ADDRESS_RE, text):
            findings.append(
                OpticalFinding(
                    type="address",
                    category=RiskCategory.PII,
                    confidence=0.7,
                    text=match_text,
                    trust="DATA",
                )
            )

        for m in _NAME_LABEL_RE.finditer(text):
            findings.append(
                OpticalFinding(
                    type="name",
                    category=RiskCategory.PII,
                    confidence=0.8,
                    text=m.group(0),
                    trust="DATA",
                )
            )

        mrn = _MRN_RE.search(text)
        if mrn:
            findings.append(
                OpticalFinding(
                    type="mrn",
                    category=RiskCategory.PII,
                    confidence=0.95,
                    text=mrn.group(0),
                    trust="DATA",
                )
            )
            findings.append(
                OpticalFinding(
                    type="patient_id",
                    category=RiskCategory.PHI,
                    confidence=0.9,
                    text=mrn.group(0),
                    trust="DATA",
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
                        trust="DATA",
                    )
                )

        document_type = _infer_document_type(
            findings, clinical_hits, injection_detected, multimodal
        )
        confidence = ocr.confidence
        if findings:
            confidence = max(confidence, max(f.confidence for f in findings), multimodal.confidence)

        return OpticalAssessment(
            ocr_text=text,
            document_type=document_type,
            findings=findings,
            face_detected=False,
            injection_detected=injection_detected,
            confidence=confidence,
            trust_classification="untrusted",
            multimodal_categories=multimodal.categories,
            rewrite_mode=multimodal.rewrite_mode,
            qr_detected=multimodal.qr_detected,
            qr_payload=multimodal.qr_payload,
            authority_spoofing=multimodal.authority_spoofing,
            data_exfiltration=multimodal.data_exfiltration,
        )


def _infer_document_type(
    findings: list[OpticalFinding],
    clinical_hits: int,
    injection_detected: bool,
    multimodal,
) -> str | None:
    if injection_detected or multimodal.injection_detected:
        return "injection_attempt"
    if multimodal.phishing:
        return "phishing_attempt"
    if multimodal.qr_detected:
        return "qr_code_document"
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
