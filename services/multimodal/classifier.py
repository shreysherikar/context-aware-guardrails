"""Multimodal content classifier — semantic threat detection for image/OCR/screen content."""

from __future__ import annotations

import re

from domain.enums import RiskLevel

from services.multimodal.models import ExtractedElement, MultimodalAssessment
from services.multimodal.patterns import (
    ALL_THREAT_PATTERNS,
    _EDUCATIONAL,
    _QR_HINT,
    _RISK_ORDER,
    _URL_EXTRACT,
    ThreatPattern,
)

_UNTRUSTED_INSTRUCTION_BLOCK = re.compile(
    r"(?im)^(?:IMPORTANT AI INSTRUCTION|SYSTEM MESSAGE|DEVELOPER MESSAGE|"
    r"ADMINISTRATOR APPROVED|ADMIN APPROVED|SECURITY APPROVED)[^\n]*\n?"
    r"(?:.*\n?)*?(?=\n\n|\Z)",
)


def _max_risk(a: RiskLevel, b: RiskLevel) -> RiskLevel:
    return a if _RISK_ORDER[a] >= _RISK_ORDER[b] else b


def _scan_patterns(text: str) -> tuple[list[ExtractedElement], list[str], RiskLevel, dict[str, bool]]:
    elements: list[ExtractedElement] = []
    categories: list[str] = []
    risk = RiskLevel.LOW
    flags = {
        "injection": False,
        "authority": False,
        "exfil": False,
        "credential": False,
        "malicious_url": False,
        "phishing": False,
        "malware": False,
        "computer": False,
        "policy_bypass": False,
    }

    for rule in ALL_THREAT_PATTERNS:
        for match in rule.pattern.finditer(text):
            cat = rule.category
            if cat not in categories:
                categories.append(cat)
            risk = _max_risk(risk, rule.risk)
            elements.append(
                ExtractedElement(
                    element_type=rule.trust.lower(),
                    content=match.group(0),
                    trust=rule.trust,
                    threat_category=cat,
                    start=match.start(),
                    end=match.end(),
                    severity=rule.severity,
                )
            )
            if cat == "IMAGE_PROMPT_INJECTION" or cat == "POLICY_BYPASS_ATTEMPT":
                flags["injection"] = True
                if cat == "POLICY_BYPASS_ATTEMPT":
                    flags["policy_bypass"] = True
            elif cat == "VISUAL_AUTHORITY_SPOOFING":
                flags["authority"] = True
            elif cat == "DATA_EXFILTRATION_ATTEMPT":
                flags["exfil"] = True
            elif cat == "SECRET_EXPOSURE":
                flags["credential"] = True
            elif cat in ("MALICIOUS_URL", "NETWORK_BYPASS_ATTEMPT", "DARKWEB_ACCESS_ATTEMPT"):
                flags["malicious_url"] = True
            elif cat == "PHISHING_ATTEMPT":
                flags["phishing"] = True
            elif cat == "MALWARE_EXECUTION_ATTEMPT":
                flags["malware"] = True
            elif cat == "COMPUTER_USE_MANIPULATION":
                flags["computer"] = True
            elif cat in ("POLICY_BYPASS_ATTEMPT", "PRIVILEGE_ESCALATION_ATTEMPT"):
                flags["policy_bypass"] = True

    return elements, categories, risk, flags


def _detect_qr(text: str) -> tuple[bool, str | None]:
    """Detect QR/barcode references and embedded URLs in OCR text."""
    if _QR_HINT.search(text):
        urls = _URL_EXTRACT.findall(text)
        if urls:
            return True, urls[0]
        return True, None
    # Standalone suspicious URL in image context
    onion = re.search(r"https?://[^\s]+\.onion[^\s]*", text, re.I)
    if onion:
        return True, onion.group(0)
    return False, None


def assess_multimodal_content(
    text: str,
    *,
    source: str = "image",
    is_output: bool = False,
    is_screen: bool = False,
) -> MultimodalAssessment:
    """Classify multimodal extracted text by threat category and actionability."""
    if not text or not text.strip():
        return MultimodalAssessment(decision="ALLOW", rewrite_mode="PASS")

    elements, categories, risk, flags = _scan_patterns(text)
    reasons: list[str] = []
    qr_detected, qr_payload = _detect_qr(text)
    if qr_detected:
        categories.append("MALICIOUS_URL")
        reasons.append("QR code or embedded URL detected — treated as untrusted external data")
        risk = _max_risk(risk, RiskLevel.HIGH)
        elements.append(
            ExtractedElement(
                element_type="qr_code",
                content=qr_payload or "[QR_DETECTED]",
                trust="UNTRUSTED_QR",
                threat_category="MALICIOUS_URL",
                severity="high",
            )
        )

    # Educational content without operational instructions
    if _EDUCATIONAL.search(text) and not elements:
        return MultimodalAssessment(
            risk_level=RiskLevel.LOW,
            decision="ALLOW",
            rewrite_mode="PASS",
            reasons=["Educational or informational multimodal content"],
        )

    if not elements:
        return MultimodalAssessment(
            risk_level=RiskLevel.LOW,
            decision="ALLOW",
            rewrite_mode="PASS",
        )

    for el in elements:
        reasons.append(f"{el.threat_category}: {el.content[:60]}")

    security_event: str | None = None
    if flags["injection"]:
        security_event = "IMAGE_PROMPT_INJECTION"
    elif flags["authority"]:
        security_event = "VISUAL_AUTHORITY_SPOOFING"
    elif flags["exfil"]:
        security_event = "DATA_EXFILTRATION_ATTEMPT"
    elif flags["credential"]:
        security_event = "SECRET_EXPOSURE"
    elif flags["phishing"]:
        security_event = "PHISHING_ATTEMPT"
    elif flags["malware"]:
        security_event = "MALWARE_EXECUTION_ATTEMPT"
    elif flags["computer"] or is_screen:
        security_event = "COMPUTER_USE_MANIPULATION"
    elif qr_detected:
        security_event = "MALICIOUS_URL"

    has_legitimate = bool(
        re.search(
            r"(?i)\b(?:clinical|results|study|summary|report|data shows|"
            r"experiment|findings|diagnosis|medication|lab|wellness|brochure)\b",
            text,
        )
    )

    # Decision mapping — credentials redact; exfil/malware/policy-bypass block
    if flags["exfil"] or flags["malware"]:
        decision = "BLOCK"
        rewrite_mode = "BLOCK"
    elif flags["policy_bypass"]:
        decision = "BLOCK"
        rewrite_mode = "BLOCK"
    elif flags["credential"]:
        decision = "REWRITE"
        rewrite_mode = "REDACT"
    elif flags["injection"] and not has_legitimate and not flags["authority"]:
        decision = "BLOCK"
        rewrite_mode = "BLOCK"
    elif flags["phishing"]:
        decision = "BLOCK"
        rewrite_mode = "BLOCK"
    elif flags["injection"] or flags["authority"] or flags["policy_bypass"]:
        decision = "REWRITE" if not is_output else "REWRITE"
        rewrite_mode = "SAFE_REWRITE"
    elif flags["credential"]:
        decision = "REWRITE"
        rewrite_mode = "REDACT"
    elif flags["computer"] or is_screen:
        decision = "BLOCK" if is_screen else "REWRITE"
        rewrite_mode = "SAFE_REWRITE" if decision == "REWRITE" else "BLOCK"
    elif risk == RiskLevel.HIGH:
        decision = "REWRITE" if source == "image" else "BLOCK"
        rewrite_mode = "SAFE_REWRITE"
    elif elements:
        decision = "REWRITE"
        rewrite_mode = "ANNOTATE"
    else:
        decision = "ALLOW"
        rewrite_mode = "PASS"

    # PHI + exfil combo → CRITICAL
    if flags["exfil"] and re.search(r"(?i)\b(?:patient|phi|clinical|confidential)\b", text):
        risk = RiskLevel.CRITICAL
        decision = "BLOCK"
        rewrite_mode = "BLOCK"
        security_event = "DATA_EXFILTRATION_ATTEMPT"

    return MultimodalAssessment(
        risk_level=risk,
        decision=decision,
        rewrite_mode=rewrite_mode,
        categories=categories,
        elements=elements,
        injection_detected=flags["injection"],
        authority_spoofing=flags["authority"],
        data_exfiltration=flags["exfil"],
        credential_exposure=flags["credential"],
        malicious_url=flags["malicious_url"] or qr_detected,
        phishing=flags["phishing"],
        malware_instruction=flags["malware"],
        computer_use_manipulation=flags["computer"],
        policy_bypass=flags["policy_bypass"],
        qr_detected=qr_detected,
        qr_payload=qr_payload,
        reasons=reasons,
        security_event_category=security_event,
        confidence=0.88,
    )
