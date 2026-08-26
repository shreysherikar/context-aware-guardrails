"""Deterministic text sanitization for PII / PHI identifiers.

Conservative labeled-field and pattern redaction. Does not over-redact ordinary
scientific content (e.g. HbA1c values).
"""

from __future__ import annotations

import re

from domain.enums import RiskCategory
from services.sanitization.models import SanitizationFinding, SourceType

# Typed replacement tokens (P1).
TOKEN_PATIENT = "[PATIENT_REDACTED]"
TOKEN_DATE = "[DATE_REDACTED]"
TOKEN_MRN = "[MRN_REDACTED]"
TOKEN_EMAIL = "[EMAIL_REDACTED]"
TOKEN_PHONE = "[PHONE_REDACTED]"
TOKEN_GENERIC = "[REDACTED]"

_LABEL_TOKEN: list[tuple[re.Pattern[str], str, str, RiskCategory]] = [
    (
        re.compile(
            r"(?im)^(\s*(?:patient|name|full name)\s*[:\-]\s*)(.+)$",
        ),
        TOKEN_PATIENT,
        "name",
        RiskCategory.PII,
    ),
    (
        re.compile(
            r"(?im)^(\s*(?:dob|date of birth)\s*[:\-]\s*)(.+)$",
        ),
        TOKEN_DATE,
        "dob",
        RiskCategory.PII,
    ),
    (
        re.compile(
            r"(?im)^(\s*(?:mrn|medical record(?: number)?|patient id)\s*[:\-]\s*)(.+)$",
        ),
        TOKEN_MRN,
        "mrn",
        RiskCategory.PHI,
    ),
    (
        re.compile(
            r"(?im)^(\s*(?:ssn|social security)\s*[:\-]\s*)(.+)$",
        ),
        TOKEN_GENERIC,
        "ssn",
        RiskCategory.PII,
    ),
    (
        re.compile(
            r"(?im)^(\s*(?:email|e-mail)\s*[:\-]\s*)(.+)$",
        ),
        TOKEN_EMAIL,
        "email",
        RiskCategory.PII,
    ),
    (
        re.compile(
            r"(?im)^(\s*(?:phone|tel|mobile)\s*[:\-]\s*)(.+)$",
        ),
        TOKEN_PHONE,
        "phone",
        RiskCategory.PII,
    ),
    (
        re.compile(
            r"(?im)^(\s*(?:address|home address)\s*[:\-]\s*)(.+)$",
        ),
        TOKEN_GENERIC,
        "address",
        RiskCategory.PII,
    ),
]

_EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
_PHONE_RE = re.compile(r"(?:\+?\d{1,3}[\s.-]?)?(?:\(?\d{3}\)?[\s.-]?)\d{3}[\s.-]?\d{4}\b")
_SSN_RE = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
_DOB_BARE_RE = re.compile(
    r"(?i)\b(?:dob|date of birth)\b\s*[:\-]?\s*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})"
)
_MRN_INLINE_RE = re.compile(
    r"(?i)\b(?:mrn|medical record(?:\s+number)?|patient\s+id)\b\s*[:\-]?\s*([A-Za-z0-9\-]+)"
)


def sanitize_text(
    text: str,
    *,
    source_type: SourceType = "text",
) -> tuple[str, list[SanitizationFinding]]:
    """Return (sanitized_text, findings). Never raises for ordinary input."""
    if not text:
        return text, []

    findings: list[SanitizationFinding] = []
    result = text

    # 1) Labeled lines — preserve label, redact value with typed token.
    for pattern, token, entity_type, category in _LABEL_TOKEN:

        def _repl(
            match: re.Match[str],
            *,
            _token: str = token,
            _entity: str = entity_type,
            _cat: RiskCategory = category,
        ) -> str:
            original = match.group(2)
            findings.append(
                SanitizationFinding(
                    entity_type=_entity,
                    category=_cat,
                    replacement=_token,
                    confidence=0.9,
                    source=source_type,
                    location="labeled_field",
                    original_value=original,
                )
            )
            return f"{match.group(1)}{_token}"

        result = pattern.sub(_repl, result)

    # 2) Inline patterns not already covered by labeled redaction.
    def _sub_pattern(
        pattern: re.Pattern[str],
        token: str,
        entity_type: str,
        category: RiskCategory,
        group: int = 0,
    ) -> None:
        nonlocal result

        def _repl(match: re.Match[str]) -> str:
            original = match.group(group) if group else match.group(0)
            # Skip if already a redaction token.
            if original.startswith("[") and original.endswith("]"):
                return match.group(0)
            findings.append(
                SanitizationFinding(
                    entity_type=entity_type,
                    category=category,
                    replacement=token,
                    confidence=0.85,
                    source=source_type,
                    location="inline",
                    original_value=original,
                )
            )
            if group == 0:
                return token
            return match.group(0).replace(original, token, 1)

        result = pattern.sub(_repl, result)

    _sub_pattern(_EMAIL_RE, TOKEN_EMAIL, "email", RiskCategory.PII)
    _sub_pattern(_PHONE_RE, TOKEN_PHONE, "phone", RiskCategory.PII)
    _sub_pattern(_SSN_RE, TOKEN_GENERIC, "ssn", RiskCategory.PII)
    _sub_pattern(_DOB_BARE_RE, TOKEN_DATE, "dob", RiskCategory.PII, group=1)
    _sub_pattern(_MRN_INLINE_RE, TOKEN_MRN, "mrn", RiskCategory.PHI, group=1)

    return result, findings
