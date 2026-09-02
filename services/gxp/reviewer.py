"""GxP compliance reviewer — detect violations, highlight spans, rewrite text."""

from __future__ import annotations

import re
from typing import NamedTuple

from services.gxp.models import GxpFinding, GxpHighlight, GxpReviewResult
from services.gxp.patterns import GXP_FRAMEWORK_DESCRIPTIONS, GXP_PATTERNS, GxpPattern


class _Match(NamedTuple):
    start: int
    end: int
    pattern: GxpPattern
    text: str


_SEVERITY_ORDER = {"low": 0, "medium": 1, "high": 2, "critical": 3}


def _resolve_overlaps(matches: list[_Match]) -> list[_Match]:
    """Prefer longer spans, then higher severity, when patterns overlap."""
    if not matches:
        return []
    ordered = sorted(
        matches,
        key=lambda m: (
            -(m.end - m.start),
            -_SEVERITY_ORDER.get(m.pattern.severity, 0),
            m.start,
        ),
    )
    kept: list[_Match] = []
    occupied: list[tuple[int, int]] = []
    for match in ordered:
        if any(not (match.end <= s or match.start >= e) for s, e in occupied):
            continue
        kept.append(match)
        occupied.append((match.start, match.end))
    return sorted(kept, key=lambda m: m.start)


def _find_matches(text: str) -> list[_Match]:
    found: list[_Match] = []
    for rule in GXP_PATTERNS:
        for m in rule.pattern.finditer(text):
            found.append(_Match(m.start(), m.end(), rule, m.group(0)))
    return _resolve_overlaps(found)


def _apply_rewrites(text: str, matches: list[_Match]) -> str:
    rewritten = text
    for match in reversed(matches):
        rewritten = rewritten[: match.start] + match.pattern.replacement + rewritten[match.end :]
    return rewritten


def _normalize_whitespace(text: str) -> str:
    return re.sub(r"[ \t]+\n", "\n", text).strip()


class GxpReviewer:
    """Deterministic GxP language review for SOPs, protocols, and agent outputs."""

    def review(self, text: str) -> GxpReviewResult:
        cleaned = text or ""
        matches = _find_matches(cleaned)
        rewritten = _apply_rewrites(cleaned, matches) if matches else cleaned

        highlights: list[GxpHighlight] = []
        findings: list[GxpFinding] = []
        frameworks: set[str] = set()

        for match in matches:
            rule = match.pattern
            frameworks.update(rule.gxp_frameworks)
            highlights.append(
                GxpHighlight(
                    start=match.start,
                    end=match.end,
                    text=match.text,
                    gxp_frameworks=list(rule.gxp_frameworks),
                    category=rule.category,
                    reason=rule.reason,
                    severity=rule.severity,
                    suggested_replacement=rule.replacement,
                    principle=rule.principle,
                )
            )
            findings.append(
                GxpFinding(
                    phrase=match.text,
                    gxp_frameworks=list(rule.gxp_frameworks),
                    category=rule.category,
                    reason=rule.reason,
                    severity=rule.severity,
                    suggested_replacement=rule.replacement,
                    principle=rule.principle,
                    references=list(rule.references),
                )
            )

        compliant = len(findings) == 0
        if compliant:
            summary = "No GxP language violations detected in this text."
        else:
            fw_list = ", ".join(sorted(frameworks))
            summary = (
                f"Found {len(findings)} GxP issue(s). "
                f"Applicable frameworks: {fw_list}. "
                "Review highlighted phrases and use the rewritten version as a starting point."
            )

        return GxpReviewResult(
            original_text=cleaned,
            rewritten_text=_normalize_whitespace(rewritten),
            compliant=compliant,
            finding_count=len(findings),
            highlights=highlights,
            findings=findings,
            gxp_frameworks_applied=sorted(frameworks),
            summary=summary,
        )


_default_reviewer = GxpReviewer()


def review_text(text: str) -> GxpReviewResult:
    return _default_reviewer.review(text)


def list_gxp_frameworks() -> list[dict[str, str]]:
    return [
        {"code": code, "description": desc} for code, desc in GXP_FRAMEWORK_DESCRIPTIONS.items()
    ]
