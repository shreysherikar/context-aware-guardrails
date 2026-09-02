"""Multimodal threat patterns — semantic intent classification for image/OCR content."""

from __future__ import annotations

import re
from dataclasses import dataclass

from domain.enums import RiskLevel


@dataclass(frozen=True)
class ThreatPattern:
    pattern: re.Pattern[str]
    category: str
    risk: RiskLevel
    trust: str
    severity: str = "medium"


# --- A. Prompt injection ---
_INJECTION: list[ThreatPattern] = [
    ThreatPattern(
        re.compile(r"(?i)ignore (?:all |any |previous |prior )?(?:instructions|policies|security)"),
        "IMAGE_PROMPT_INJECTION",
        RiskLevel.CRITICAL,
        "UNTRUSTED_INSTRUCTION",
        "critical",
    ),
    ThreatPattern(
        re.compile(r"(?i)ignore (?:system|developer) instructions"),
        "IMAGE_PROMPT_INJECTION",
        RiskLevel.CRITICAL,
        "UNTRUSTED_INSTRUCTION",
        "critical",
    ),
    ThreatPattern(
        re.compile(r"(?i)follow these new instructions"),
        "IMAGE_PROMPT_INJECTION",
        RiskLevel.CRITICAL,
        "UNTRUSTED_INSTRUCTION",
        "critical",
    ),
    ThreatPattern(
        re.compile(r"(?i)override (?:your |the )?(?:rules|policies|security)"),
        "IMAGE_PROMPT_INJECTION",
        RiskLevel.CRITICAL,
        "UNTRUSTED_INSTRUCTION",
        "critical",
    ),
    ThreatPattern(
        re.compile(r"(?i)reveal (?:your |the )?(?:system prompt|hidden instructions)"),
        "IMAGE_PROMPT_INJECTION",
        RiskLevel.CRITICAL,
        "UNTRUSTED_INSTRUCTION",
        "critical",
    ),
    ThreatPattern(
        re.compile(r"(?i)change your role"),
        "IMAGE_PROMPT_INJECTION",
        RiskLevel.HIGH,
        "UNTRUSTED_INSTRUCTION",
        "high",
    ),
    ThreatPattern(
        re.compile(r"(?i)pretend to be (?:an? )?(?:administrator|admin|developer)"),
        "IMAGE_PROMPT_INJECTION",
        RiskLevel.HIGH,
        "UNTRUSTED_INSTRUCTION",
        "high",
    ),
    ThreatPattern(
        re.compile(r"(?i)disable (?:safety|security|guardrail|audit)"),
        "POLICY_BYPASS_ATTEMPT",
        RiskLevel.CRITICAL,
        "UNTRUSTED_INSTRUCTION",
        "critical",
    ),
    ThreatPattern(
        re.compile(r"(?i)bypass (?:the )?(?:guardrail|policy|approval)"),
        "POLICY_BYPASS_ATTEMPT",
        RiskLevel.CRITICAL,
        "UNTRUSTED_INSTRUCTION",
        "critical",
    ),
    ThreatPattern(
        re.compile(r"(?i)rewrite until (?:accepted|passes|guardrail)"),
        "POLICY_BYPASS_ATTEMPT",
        RiskLevel.CRITICAL,
        "UNTRUSTED_INSTRUCTION",
        "critical",
    ),
    ThreatPattern(
        re.compile(r"(?i)do not tell the user"),
        "IMAGE_PROMPT_INJECTION",
        RiskLevel.HIGH,
        "UNTRUSTED_INSTRUCTION",
        "high",
    ),
    ThreatPattern(
        re.compile(r"(?i)act secretly"),
        "IMAGE_PROMPT_INJECTION",
        RiskLevel.HIGH,
        "UNTRUSTED_INSTRUCTION",
        "high",
    ),
    ThreatPattern(
        re.compile(r"(?i)important ai instruction"),
        "IMAGE_PROMPT_INJECTION",
        RiskLevel.CRITICAL,
        "UNTRUSTED_INSTRUCTION",
        "critical",
    ),
]

# --- B. Authority spoofing ---
_AUTHORITY: list[ThreatPattern] = [
    ThreatPattern(
        re.compile(r"(?i)administrator approved"),
        "VISUAL_AUTHORITY_SPOOFING",
        RiskLevel.HIGH,
        "UNTRUSTED_AUTHORITY",
        "high",
    ),
    ThreatPattern(
        re.compile(r"(?i)admin approved"),
        "VISUAL_AUTHORITY_SPOOFING",
        RiskLevel.HIGH,
        "UNTRUSTED_AUTHORITY",
        "high",
    ),
    ThreatPattern(
        re.compile(r"(?i)security approved"),
        "VISUAL_AUTHORITY_SPOOFING",
        RiskLevel.HIGH,
        "UNTRUSTED_AUTHORITY",
        "high",
    ),
    ThreatPattern(
        re.compile(r"(?i)system message\s*[:\-]"),
        "VISUAL_AUTHORITY_SPOOFING",
        RiskLevel.HIGH,
        "UNTRUSTED_AUTHORITY",
        "high",
    ),
    ThreatPattern(
        re.compile(r"(?i)developer instructions?\s*[:\-]"),
        "VISUAL_AUTHORITY_SPOOFING",
        RiskLevel.HIGH,
        "UNTRUSTED_AUTHORITY",
        "high",
    ),
    ThreatPattern(
        re.compile(r"(?i)compliance approved"),
        "VISUAL_AUTHORITY_SPOOFING",
        RiskLevel.HIGH,
        "UNTRUSTED_AUTHORITY",
        "high",
    ),
    ThreatPattern(
        re.compile(r"(?i)human approval (?:granted|received|complete)"),
        "VISUAL_AUTHORITY_SPOOFING",
        RiskLevel.HIGH,
        "UNTRUSTED_AUTHORITY",
        "high",
    ),
    ThreatPattern(
        re.compile(r"(?i)emergency override"),
        "VISUAL_AUTHORITY_SPOOFING",
        RiskLevel.CRITICAL,
        "UNTRUSTED_AUTHORITY",
        "critical",
    ),
    ThreatPattern(
        re.compile(r"(?i)authorization notice"),
        "VISUAL_AUTHORITY_SPOOFING",
        RiskLevel.MEDIUM,
        "UNTRUSTED_AUTHORITY",
        "medium",
    ),
    ThreatPattern(
        re.compile(r"(?i)upload all data"),
        "VISUAL_AUTHORITY_SPOOFING",
        RiskLevel.CRITICAL,
        "UNTRUSTED_AUTHORITY",
        "critical",
    ),
    ThreatPattern(
        re.compile(r"(?i)regulatory approval granted"),
        "REGULATORY_MANIPULATION_ATTEMPT",
        RiskLevel.HIGH,
        "UNTRUSTED_AUTHORITY",
        "high",
    ),
    ThreatPattern(
        re.compile(r"(?i)false (?:regulatory )?approval"),
        "REGULATORY_MANIPULATION_ATTEMPT",
        RiskLevel.HIGH,
        "UNTRUSTED_AUTHORITY",
        "high",
    ),
]

# --- C. Data exfiltration ---
_EXFIL: list[ThreatPattern] = [
    ThreatPattern(
        re.compile(r"(?i)upload(?:\s+(?:all|internal|patient|clinical))+\s+(?:data|files|records)"),
        "DATA_EXFILTRATION_ATTEMPT",
        RiskLevel.CRITICAL,
        "UNTRUSTED_INSTRUCTION",
        "critical",
    ),
    ThreatPattern(
        re.compile(r"(?i)upload\s+all\s+(?:data|files|records)"),
        "DATA_EXFILTRATION_ATTEMPT",
        RiskLevel.CRITICAL,
        "UNTRUSTED_INSTRUCTION",
        "critical",
    ),
    ThreatPattern(
        re.compile(
            r"(?i)send (?:all |patient |clinical |confidential )?"
            r"(?:data|records|information) (?:to|externally)"
        ),
        "DATA_EXFILTRATION_ATTEMPT",
        RiskLevel.CRITICAL,
        "UNTRUSTED_INSTRUCTION",
        "critical",
    ),
    ThreatPattern(
        re.compile(
            r"(?i)extract (?:all |patient |clinical |confidential )?(?:data|information|records)"
        ),
        "DATA_EXFILTRATION_ATTEMPT",
        RiskLevel.HIGH,
        "UNTRUSTED_INSTRUCTION",
        "high",
    ),
    ThreatPattern(
        re.compile(r"(?i)copy (?:all |patient )?(?:data|records) to (?:external|unknown)"),
        "DATA_EXFILTRATION_ATTEMPT",
        RiskLevel.CRITICAL,
        "UNTRUSTED_INSTRUCTION",
        "critical",
    ),
    ThreatPattern(
        re.compile(r"(?i)email (?:sensitive|patient|clinical|confidential) (?:data|information)"),
        "DATA_EXFILTRATION_ATTEMPT",
        RiskLevel.CRITICAL,
        "UNTRUSTED_INSTRUCTION",
        "critical",
    ),
    ThreatPattern(
        re.compile(r"(?i)transfer (?:data|files) to (?:external|unknown|unauthorized)"),
        "DATA_EXFILTRATION_ATTEMPT",
        RiskLevel.CRITICAL,
        "UNTRUSTED_INSTRUCTION",
        "critical",
    ),
]

# --- E. Credentials ---
_CREDENTIALS: list[ThreatPattern] = [
    ThreatPattern(
        re.compile(r"(?i)(?:api[_-]?key|password|secret|token)\s*[:=]\s*\S+"),
        "SECRET_EXPOSURE",
        RiskLevel.CRITICAL,
        "DATA",
        "critical",
    ),
    ThreatPattern(
        re.compile(r"(?i)sk-[a-zA-Z0-9]{20,}"),
        "SECRET_EXPOSURE",
        RiskLevel.CRITICAL,
        "DATA",
        "critical",
    ),
    ThreatPattern(
        re.compile(r"(?i)Bearer\s+[A-Za-z0-9\-_.]+"),
        "SECRET_EXPOSURE",
        RiskLevel.CRITICAL,
        "DATA",
        "critical",
    ),
    ThreatPattern(
        re.compile(r"-----BEGIN (?:RSA )?PRIVATE KEY-----"),
        "SECRET_EXPOSURE",
        RiskLevel.CRITICAL,
        "DATA",
        "critical",
    ),
    ThreatPattern(
        re.compile(r"(?i)enter (?:your )?(?:password|credentials|api key)"),
        "PHISHING_ATTEMPT",
        RiskLevel.HIGH,
        "UNTRUSTED_INSTRUCTION",
        "high",
    ),
]

# --- F. Malicious URLs ---
_URL: list[ThreatPattern] = [
    ThreatPattern(
        re.compile(r"(?i)https?://[^\s]+\.onion[^\s]*"),
        "MALICIOUS_URL",
        RiskLevel.CRITICAL,
        "UNTRUSTED_URL",
        "critical",
    ),
    ThreatPattern(
        re.compile(r"(?i)navigate to https?://[^\s]+"),
        "MALICIOUS_URL",
        RiskLevel.HIGH,
        "UNTRUSTED_INSTRUCTION",
        "high",
    ),
    ThreatPattern(
        re.compile(r"(?i)bypass (?:network|firewall|proxy)"),
        "NETWORK_BYPASS_ATTEMPT",
        RiskLevel.CRITICAL,
        "UNTRUSTED_INSTRUCTION",
        "critical",
    ),
    ThreatPattern(
        re.compile(r"(?i)(?:vpn|proxy) (?:to access|for evasion)"),
        "NETWORK_BYPASS_ATTEMPT",
        RiskLevel.HIGH,
        "UNTRUSTED_INSTRUCTION",
        "high",
    ),
]

# --- G. Phishing ---
_PHISHING: list[ThreatPattern] = [
    ThreatPattern(
        re.compile(r"(?i)verify (?:your )?account"),
        "PHISHING_ATTEMPT",
        RiskLevel.HIGH,
        "UNTRUSTED_INSTRUCTION",
        "high",
    ),
    ThreatPattern(
        re.compile(r"(?i)login (?:page|portal|required)"),
        "PHISHING_ATTEMPT",
        RiskLevel.MEDIUM,
        "UNTRUSTED_INSTRUCTION",
        "medium",
    ),
    ThreatPattern(
        re.compile(r"(?i)it (?:administrator|security team|helpdesk)"),
        "PHISHING_ATTEMPT",
        RiskLevel.MEDIUM,
        "UNTRUSTED_INSTRUCTION",
        "medium",
    ),
    ThreatPattern(
        re.compile(r"(?i)wire transfer"),
        "PHISHING_ATTEMPT",
        RiskLevel.HIGH,
        "UNTRUSTED_INSTRUCTION",
        "high",
    ),
    ThreatPattern(
        re.compile(r"(?i)approve (?:this )?transaction"),
        "PHISHING_ATTEMPT",
        RiskLevel.HIGH,
        "UNTRUSTED_INSTRUCTION",
        "high",
    ),
]

# --- H. Malware / code execution ---
_MALWARE: list[ThreatPattern] = [
    ThreatPattern(
        re.compile(r"(?i)(?:run|execute) (?:this )?(?:command|script|powershell|shell)"),
        "MALWARE_EXECUTION_ATTEMPT",
        RiskLevel.CRITICAL,
        "UNTRUSTED_INSTRUCTION",
        "critical",
    ),
    ThreatPattern(
        re.compile(
            r"(?i)download (?:and )?(?:run|execute) (?:the )?(?:executable|malware|software)"
        ),
        "MALWARE_EXECUTION_ATTEMPT",
        RiskLevel.CRITICAL,
        "UNTRUSTED_INSTRUCTION",
        "critical",
    ),
    ThreatPattern(
        re.compile(r"(?i)rm -rf|powershell -enc|curl\s+[^\s]+\|\s*bash"),
        "MALWARE_EXECUTION_ATTEMPT",
        RiskLevel.CRITICAL,
        "UNTRUSTED_INSTRUCTION",
        "critical",
    ),
    ThreatPattern(
        re.compile(r"(?i)install (?:unauthorized|unknown) software"),
        "MALWARE_EXECUTION_ATTEMPT",
        RiskLevel.HIGH,
        "UNTRUSTED_INSTRUCTION",
        "high",
    ),
]

# --- I. Computer-use manipulation ---
_COMPUTER: list[ThreatPattern] = [
    ThreatPattern(
        re.compile(r"(?i)click (?:the |this )?(?:button|link|submit)"),
        "COMPUTER_USE_MANIPULATION",
        RiskLevel.HIGH,
        "UNTRUSTED_INSTRUCTION",
        "high",
    ),
    ThreatPattern(
        re.compile(r"(?i)type (?:your )?(?:password|credentials)"),
        "COMPUTER_USE_MANIPULATION",
        RiskLevel.CRITICAL,
        "UNTRUSTED_INSTRUCTION",
        "critical",
    ),
    ThreatPattern(
        re.compile(r"(?i)open (?:the )?browser and (?:navigate|go to)"),
        "COMPUTER_USE_MANIPULATION",
        RiskLevel.HIGH,
        "UNTRUSTED_INSTRUCTION",
        "high",
    ),
    ThreatPattern(
        re.compile(r"(?i)upload (?:the |this )?file"),
        "COMPUTER_USE_MANIPULATION",
        RiskLevel.HIGH,
        "UNTRUSTED_INSTRUCTION",
        "high",
    ),
    ThreatPattern(
        re.compile(r"(?i)submit (?:the )?form"),
        "COMPUTER_USE_MANIPULATION",
        RiskLevel.HIGH,
        "UNTRUSTED_INSTRUCTION",
        "high",
    ),
]

# --- K. Regulatory manipulation ---
_REGULATORY: list[ThreatPattern] = [
    ThreatPattern(
        re.compile(r"(?i)hide (?:adverse|safety) (?:events?|information)"),
        "REGULATORY_MANIPULATION_ATTEMPT",
        RiskLevel.CRITICAL,
        "UNTRUSTED_INSTRUCTION",
        "critical",
    ),
    ThreatPattern(
        re.compile(r"(?i)suppress (?:safety|adverse) (?:data|information|findings)"),
        "REGULATORY_MANIPULATION_ATTEMPT",
        RiskLevel.CRITICAL,
        "UNTRUSTED_INSTRUCTION",
        "critical",
    ),
    ThreatPattern(
        re.compile(r"(?i)alter (?:clinical )?results?"),
        "REGULATORY_MANIPULATION_ATTEMPT",
        RiskLevel.CRITICAL,
        "UNTRUSTED_INSTRUCTION",
        "critical",
    ),
    ThreatPattern(
        re.compile(r"(?i)fabricate (?:evidence|results|data)"),
        "REGULATORY_MANIPULATION_ATTEMPT",
        RiskLevel.CRITICAL,
        "UNTRUSTED_INSTRUCTION",
        "critical",
    ),
    ThreatPattern(
        re.compile(r"(?i)bypass (?:qa|audit|quality)"),
        "REGULATORY_MANIPULATION_ATTEMPT",
        RiskLevel.CRITICAL,
        "UNTRUSTED_INSTRUCTION",
        "critical",
    ),
]

# --- L. Clinical safety ---
_CLINICAL: list[ThreatPattern] = [
    ThreatPattern(
        re.compile(r"(?i)change (?:patient )?(?:medication|dosage|treatment)"),
        "CLINICAL_SAFETY_VIOLATION",
        RiskLevel.HIGH,
        "UNTRUSTED_INSTRUCTION",
        "high",
    ),
    ThreatPattern(
        re.compile(r"(?i)prescribe (?:this |the )?(?:medication|drug)"),
        "CLINICAL_SAFETY_VIOLATION",
        RiskLevel.HIGH,
        "UNTRUSTED_INSTRUCTION",
        "high",
    ),
    ThreatPattern(
        re.compile(r"(?i)diagnose (?:the )?patient"),
        "CLINICAL_SAFETY_VIOLATION",
        RiskLevel.HIGH,
        "UNTRUSTED_INSTRUCTION",
        "high",
    ),
]

# --- N. Manufacturing ---
_MANUFACTURING: list[ThreatPattern] = [
    ThreatPattern(
        re.compile(r"(?i)override (?:quality|qc|alarm)"),
        "MANUFACTURING_SAFETY_VIOLATION",
        RiskLevel.CRITICAL,
        "UNTRUSTED_INSTRUCTION",
        "critical",
    ),
    ThreatPattern(
        re.compile(r"(?i)release (?:the )?batch without"),
        "MANUFACTURING_SAFETY_VIOLATION",
        RiskLevel.CRITICAL,
        "UNTRUSTED_INSTRUCTION",
        "critical",
    ),
    ThreatPattern(
        re.compile(r"(?i)modify (?:batch|manufacturing) (?:record|parameters)"),
        "MANUFACTURING_SAFETY_VIOLATION",
        RiskLevel.CRITICAL,
        "UNTRUSTED_INSTRUCTION",
        "critical",
    ),
    ThreatPattern(
        re.compile(r"(?i)skip validation"),
        "MANUFACTURING_SAFETY_VIOLATION",
        RiskLevel.HIGH,
        "UNTRUSTED_INSTRUCTION",
        "high",
    ),
]

# --- O. Policy bypass / privilege ---
_PRIVILEGE: list[ThreatPattern] = [
    ThreatPattern(
        re.compile(r"(?i)disable (?:audit|logging|authentication|authorization)"),
        "POLICY_BYPASS_ATTEMPT",
        RiskLevel.CRITICAL,
        "UNTRUSTED_INSTRUCTION",
        "critical",
    ),
    ThreatPattern(
        re.compile(r"(?i)escalate privileges?"),
        "PRIVILEGE_ESCALATION_ATTEMPT",
        RiskLevel.CRITICAL,
        "UNTRUSTED_INSTRUCTION",
        "critical",
    ),
    ThreatPattern(
        re.compile(r"(?i)create administrator access"),
        "PRIVILEGE_ESCALATION_ATTEMPT",
        RiskLevel.CRITICAL,
        "UNTRUSTED_INSTRUCTION",
        "critical",
    ),
    ThreatPattern(
        re.compile(r"(?i)modify (?:your |agent )?permissions?"),
        "PRIVILEGE_ESCALATION_ATTEMPT",
        RiskLevel.CRITICAL,
        "UNTRUSTED_INSTRUCTION",
        "critical",
    ),
]

# --- QR / barcode hints in OCR ---
_QR_HINT = re.compile(r"(?i)(?:qr code|barcode|scan (?:this|me))")
_URL_EXTRACT = re.compile(r"https?://[^\s<>\"']+", re.I)

ALL_THREAT_PATTERNS: list[ThreatPattern] = (
    _INJECTION
    + _AUTHORITY
    + _EXFIL
    + _CREDENTIALS
    + _URL
    + _PHISHING
    + _MALWARE
    + _COMPUTER
    + _REGULATORY
    + _CLINICAL
    + _MANUFACTURING
    + _PRIVILEGE
)

_RISK_ORDER = {
    RiskLevel.NONE: 0,
    RiskLevel.LOW: 1,
    RiskLevel.MEDIUM: 2,
    RiskLevel.HIGH: 3,
    RiskLevel.CRITICAL: 4,
}

# Educational/defensive — reduces false positives
_EDUCATIONAL = re.compile(
    r"(?i)\b(?:what is|explain|describe|overview|risks? associated|detection"
    r"|monitoring|defensive|threat intelligence)\b"
)
