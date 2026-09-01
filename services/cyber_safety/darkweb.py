"""Dark-web access prevention — semantic intent and actionability classification.

Policy: DARKWEB_ACCESS_PREVENTION (CYBER_SAFETY)

Distinguishes educational/defensive content from operational access-enabling guidance.
Integrated into SafeRewrite, output guardrails, policy engine, tool gateway, and computer use.
"""

from __future__ import annotations

import hashlib
import re
from typing import Literal

from domain.enums import RiskLevel

from services.cyber_safety.models import DarkWebAssessment, ProcessedOutput

SAFE_DARKWEB_REDIRECT = (
    "I can provide general information about the dark web and discuss cybersecurity risks, "
    "detection, monitoring, and defensive measures, but I can't provide instructions, tools, "
    "or methods for accessing or navigating restricted dark-web services."
)

# --- Topic signals (presence alone does not block) ---
_TOPIC_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"(?i)\bdark\s*web\b"),
    re.compile(r"(?i)\bdarkweb\b"),
    re.compile(r"(?i)\bhidden\s+services?\b"),
    re.compile(r"(?i)\bonion\s+services?\b"),
    re.compile(r"(?i)\b\.onion\b"),
    re.compile(r"(?i)\btor\s+browser\b"),
    re.compile(r"(?i)\bdeep\s+web\b"),
]

# --- Educational / defensive (reduces actionability) ---
_EDUCATIONAL_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"(?i)\bwhat is (?:the )?dark\s*web\b"), "educational_definition"),
    (re.compile(r"(?i)\bdifference between\b.*\b(?:surface|deep|dark)\s*web\b"), "educational_comparison"),
    (re.compile(r"(?i)\bwhy is\b.*\bdark[- ]?web\b"), "educational_context"),
    (re.compile(r"(?i)\bcybersecurity risks?\b"), "defensive_risk_analysis"),
    (re.compile(r"(?i)\b(?:threat (?:intelligence|detection|monitoring)|defensive measures?)\b"), "defensive"),
    (re.compile(r"(?i)\bhow (?:can|do) (?:companies|organizations)\b.*\b(?:detect|monitor|defend)\b"), "defensive"),
    (re.compile(r"(?i)\bincident[- ]response\b"), "defensive"),
    (re.compile(r"(?i)\bprivacy[- ]focused communication\b"), "general_context"),
    (re.compile(r"(?i)\bnot indexed by (?:normal|conventional) search engines\b"), "educational_definition"),
    (re.compile(r"(?i)\bused by some organizations\b"), "general_context"),
]

# --- Operational / access-enabling (increases actionability) ---
_OPERATIONAL_PATTERNS: list[tuple[re.Pattern[str], str, RiskLevel]] = [
    (re.compile(r"(?i)\bhow (?:do|can) i\b.*\b(?:access|reach|get to|navigate|browse)\b"), "dark_web_access", RiskLevel.HIGH),
    (re.compile(r"(?i)\bhow to access\b.*\b(?:dark|hidden|onion|tor)\b"), "dark_web_access", RiskLevel.HIGH),
    (re.compile(r"(?i)\bhow to access\b"), "dark_web_access", RiskLevel.HIGH),
    (re.compile(r"(?i)\bto access the dark web\b"), "dark_web_access", RiskLevel.HIGH),
    (re.compile(r"(?i)\bmost common way to access\b.*\bdark\b"), "dark_web_access", RiskLevel.HIGH),
    (re.compile(r"(?i)\bstep[s-]?by[- ]?step\b"), "dark_web_navigation", RiskLevel.HIGH),
    (re.compile(r"(?i)\binstructions? for\b.*\b(?:finding|accessing|navigating)\b"), "dark_web_navigation", RiskLevel.HIGH),
    (re.compile(r"(?i)\bgive me instructions\b.*\b(?:finding|hidden)\b"), "hidden_service_access", RiskLevel.HIGH),
    (re.compile(r"(?i)\bwhat (?:software|tools?|browser)\b.*\b(?:install|use|download)\b.*\b(?:access|hidden|dark|onion|tor)\b"), "anonymous_access_guidance", RiskLevel.HIGH),
    (re.compile(r"(?i)\b(?:install|download)\b.*\b(?:tor|hidden service|dark web|\.onion)\b"), "anonymous_access_guidance", RiskLevel.HIGH),
    (re.compile(r"(?i)\btor browser is\b.*\b(?:most common|way to access|used to access)\b"), "dark_web_access", RiskLevel.HIGH),
    (re.compile(r"(?i)\bvpn and proxy\b"), "proxy_evasion", RiskLevel.HIGH),
    (re.compile(r"(?i)\bdark web search engines?\b"), "dark_web_search", RiskLevel.HIGH),
    (re.compile(r"(?i)\bfind(?:ing)?\b.*\bhidden services?\b"), "hidden_service_access", RiskLevel.HIGH),
    (re.compile(r"(?i)\bsearch (?:for|hidden)\b.*\b(?:hidden services?|\.onion|dark web)\b"), "dark_web_search", RiskLevel.HIGH),
    (re.compile(r"(?i)\bdiscover\b.*\b(?:illicit )?marketplaces?\b"), "dark_web_marketplace_discovery", RiskLevel.CRITICAL),
    (re.compile(r"(?i)\bnavigate to\b.*\b(?:hidden|onion|\.onion|dark)\b"), "dark_web_navigation", RiskLevel.HIGH),
    (re.compile(r"(?i)\buse (?:the )?browser\b.*\b(?:access|hidden|onion|dark)\b"), "dark_web_browser_navigation", RiskLevel.HIGH),
    (re.compile(r"(?i)\bopen (?:a )?browser\b.*\b(?:access|hidden|onion|dark)\b"), "dark_web_computer_use", RiskLevel.CRITICAL),
    (re.compile(r"(?i)\bconfigure\b.*\b(?:tor|proxy|vpn)\b.*\b(?:access|hidden|dark)\b"), "anonymous_access_guidance", RiskLevel.HIGH),
    (re.compile(r"(?i)\bbypass\b.*\b(?:firewall|network|restriction|control|organization)\b"), "network_control_bypass", RiskLevel.CRITICAL),
    (re.compile(r"(?i)\bcircumvent\b.*\b(?:network|security|restriction|control|firewall)\b"), "security_control_evasion", RiskLevel.CRITICAL),
    (re.compile(r"(?i)\bupload\b.*\bdark[- ]?web\b"), "dark_web_file_transfer", RiskLevel.CRITICAL),
    (re.compile(r"(?i)\b(?:send|upload|exfiltrat)\w*\b.*\b(?:dark[- ]?web|hidden service|\.onion)\b"), "dark_web_data_exfiltration", RiskLevel.CRITICAL),
]

# Output-specific instructional patterns
_OUTPUT_OPERATIONAL: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"(?i)\bto access the dark web,?\s+(?:use|install|download)\b"), "dark_web_access"),
    (re.compile(r"(?i)\b(?:first|then|next),?\s+(?:install|download|configure|open)\b.*\b(?:tor|browser|vpn)\b"), "dark_web_navigation"),
    (re.compile(r"(?i)\b\d+\.\s*(?:install|download|open|configure)\b"), "dark_web_navigation"),
]

# Prompt injection / fake authorization
_INJECTION_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"(?i)ignore (?:all |the )?(?:previous |prior )?(?:instructions|policies|security policy)"), "GUARDRAIL_BYPASS_ATTEMPT"),
    (re.compile(r"(?i)forget (?:previous |all )?instructions"), "GUARDRAIL_BYPASS_ATTEMPT"),
    (re.compile(r"(?i)disable (?:the )?(?:guardrail|governance|security)"), "SECURITY_POLICY_BYPASS"),
    (re.compile(r"(?i)(?:administrator|admin) (?:has |already )?approved"), "GUARDRAIL_BYPASS_ATTEMPT"),
    (re.compile(r"(?i)rewrite the request until it passes"), "GUARDRAIL_BYPASS_ATTEMPT"),
    (re.compile(r"(?i)ignore the agent'?s instructions\b.*\b(?:access|hidden|onion|dark)\b"), "PROMPT_INJECTION_ATTEMPT"),
]

# Data exfiltration combined with restricted destinations
_DATA_EXFIL_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"(?i)\b(?:patient|phi|pii|clinical|confidential|proprietary|credentials?|api[_-]?key)\b"),
    re.compile(r"(?i)\b(?:ssn|social security|medical record)\b"),
]

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")

_OPERATIONAL_SENTENCE = re.compile(
    r"(?i)\b(?:to access|install|download|configure|use tor|open (?:the )?browser|"
    r"navigate to|search for hidden|bypass|circumvent|step[s-]?by[- ]?step|"
    r"vpn and proxy|dark web search engine)\b"
)


def _has_topic(text: str) -> bool:
    return any(p.search(text) for p in _TOPIC_PATTERNS)


def _evidence_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def assess_darkweb_content(
    text: str,
    *,
    is_output: bool = False,
    is_computer_action: bool = False,
    is_tool_request: bool = False,
) -> DarkWebAssessment:
    """Classify content by topic, intent, actionability, and harm potential."""
    if not text or not text.strip():
        return DarkWebAssessment(decision="ALLOW", educational=True, confidence=1.0)

    categories: list[str] = []
    reasons: list[str] = []
    risk = RiskLevel.LOW
    actionable = False
    educational = False
    data_exfil = False
    injection = False
    computer_use = False
    security_event: str | None = None

    # Injection / fake authorization (escalate only when combined with dark-web intent)
    for pattern, cat in _INJECTION_PATTERNS:
        if pattern.search(text):
            injection = True
            categories.append(cat)
            reasons.append(f"Security policy bypass attempt detected ({cat})")
            security_event = cat
            if _has_topic(text) or re.search(
                r"(?i)\b(?:hidden service|access the dark|\.onion)\b", text
            ):
                risk = RiskLevel.CRITICAL
                actionable = True

    # Data exfiltration to dark web / hidden services
    has_exfil_data = any(p.search(text) for p in _DATA_EXFIL_PATTERNS)
    has_restricted_dest = bool(
        re.search(r"(?i)\b(?:dark[- ]?web|hidden service|\.onion|illicit marketplace)\b", text)
    )
    if has_exfil_data and (
        has_restricted_dest
        or re.search(r"(?i)\b(?:upload|send|exfiltrat|transfer)\b.*\b(?:external|outside)\b", text)
    ):
        data_exfil = True
        categories.append("DARKWEB_DATA_EXFILTRATION")
        reasons.append("Sensitive data transfer to restricted network destination")
        risk = RiskLevel.CRITICAL
        security_event = "DARKWEB_DATA_EXFILTRATION"
        actionable = True

    # Computer-use + dark web
    if is_computer_action or re.search(
        r"(?i)\b(?:computer use|open browser|navigate to|click|type)\b.*\b(?:hidden|onion|dark)\b",
        text,
    ):
        if _has_topic(text) or re.search(r"(?i)\b(?:hidden service|\.onion)\b", text):
            computer_use = True
            categories.append("DARKWEB_COMPUTER_USE_ATTEMPT")
            reasons.append("Computer-use request targeting restricted dark-web services")
            risk = RiskLevel.CRITICAL
            security_event = security_event or "DARKWEB_COMPUTER_USE_ATTEMPT"
            actionable = True

    # Educational signals
    for pattern, cat in _EDUCATIONAL_PATTERNS:
        if pattern.search(text):
            educational = True
            if cat not in categories:
                categories.append(cat)

    # Operational patterns
    for pattern, cat, pattern_risk in _OPERATIONAL_PATTERNS:
        if pattern.search(text):
            actionable = True
            if cat not in categories:
                categories.append(cat)
            reasons.append(f"Operational access-enabling content detected ({cat})")
            if _RISK_ORDER(pattern_risk) > _RISK_ORDER(risk):
                risk = pattern_risk
            if not security_event:
                security_event = _category_to_event(cat)

    if is_output:
        for pattern, cat in _OUTPUT_OPERATIONAL:
            if pattern.search(text):
                actionable = True
                if cat not in categories:
                    categories.append(cat)
                reasons.append(f"Output contains actionable access instructions ({cat})")
                if _RISK_ORDER(RiskLevel.HIGH) > _RISK_ORDER(risk):
                    risk = RiskLevel.HIGH
                if not security_event:
                    security_event = "DARKWEB_ACCESS_ATTEMPT"

    if is_tool_request and actionable and _has_topic(text):
        categories.append("DARKWEB_TOOL_USE_ATTEMPT")
        security_event = security_event or "DARKWEB_TOOL_USE_ATTEMPT"
        if _RISK_ORDER(RiskLevel.HIGH) > _RISK_ORDER(risk):
            risk = RiskLevel.HIGH

    # Topic-only mention without operational signals → educational allowance
    if _has_topic(text) and not actionable and educational:
        return DarkWebAssessment(
            risk_level=RiskLevel.LOW,
            decision="ALLOW",
            categories=[c for c in categories if c.startswith("educational") or c == "defensive"],
            educational=True,
            reasons=["Educational or defensive dark-web discussion"],
            confidence=0.9,
        )

    if _has_topic(text) and not actionable and not educational:
        # Benign contextual mention (e.g. "used by some organizations for privacy")
        if re.search(r"(?i)\b(?:risks?|monitoring|detection|defensive|threat)\b", text):
            return DarkWebAssessment(
                risk_level=RiskLevel.LOW,
                decision="ALLOW",
                educational=True,
                reasons=["General contextual discussion without operational guidance"],
                confidence=0.85,
            )

    # Decision mapping
    if injection and not actionable and not data_exfil and not computer_use:
        return DarkWebAssessment(
            risk_level=RiskLevel.LOW,
            decision="ALLOW",
            categories=categories,
            injection_attempt=True,
            reasons=reasons,
            security_event_category=security_event,
            confidence=0.8,
        )

    if risk == RiskLevel.CRITICAL or data_exfil or (injection and actionable):
        decision = "BLOCK"
    elif risk == RiskLevel.HIGH or (actionable and _has_topic(text)):
        decision = "BLOCK" if not is_output else "REWRITE"
    elif actionable:
        decision = "REWRITE" if is_output else "BLOCK"
    elif _has_topic(text) and educational:
        decision = "ALLOW"
    else:
        decision = "ALLOW"

    # Input access requests without explicit educational framing
    if not is_output and re.search(r"(?i)\bhow (?:do|can) i\b", text) and _has_topic(text):
        decision = "BLOCK"
        if _RISK_ORDER(RiskLevel.HIGH) > _RISK_ORDER(risk):
            risk = RiskLevel.HIGH
        actionable = True
        if "dark_web_access" not in categories:
            categories.append("dark_web_access")
        security_event = security_event or "DARKWEB_ACCESS_ATTEMPT"

    return DarkWebAssessment(
        risk_level=risk,
        decision=decision,
        categories=categories,
        actionable=actionable,
        educational=educational and not actionable,
        data_exfiltration=data_exfil,
        injection_attempt=injection,
        computer_use_attempt=computer_use,
        reasons=reasons or (["No dark-web policy violations"] if decision == "ALLOW" else []),
        security_event_category=security_event,
        confidence=0.88 if actionable else 0.8,
    )


def _RISK_ORDER(level: RiskLevel) -> int:
    order = {
        RiskLevel.NONE: 0,
        RiskLevel.LOW: 1,
        RiskLevel.MEDIUM: 2,
        RiskLevel.HIGH: 3,
        RiskLevel.CRITICAL: 4,
    }
    return order.get(level, 0)


def _category_to_event(category: str) -> str:
    mapping = {
        "dark_web_access": "DARKWEB_ACCESS_ATTEMPT",
        "dark_web_navigation": "DARKWEB_NAVIGATION_ATTEMPT",
        "dark_web_search": "DARKWEB_SEARCH_ATTEMPT",
        "hidden_service_access": "DARKWEB_ACCESS_ATTEMPT",
        "dark_web_marketplace_discovery": "DARKWEB_SEARCH_ATTEMPT",
        "network_control_bypass": "NETWORK_CONTROL_BYPASS",
        "security_control_evasion": "SECURITY_POLICY_BYPASS",
        "dark_web_computer_use": "DARKWEB_COMPUTER_USE_ATTEMPT",
        "dark_web_browser_navigation": "DARKWEB_NAVIGATION_ATTEMPT",
        "dark_web_file_transfer": "DARKWEB_DATA_EXFILTRATION",
        "dark_web_data_exfiltration": "DARKWEB_DATA_EXFILTRATION",
        "anonymous_access_guidance": "DARKWEB_ACCESS_ATTEMPT",
        "proxy_evasion": "NETWORK_CONTROL_BYPASS",
    }
    return mapping.get(category, "DARKWEB_ACCESS_ATTEMPT")


def rewrite_darkweb_content(text: str) -> str:
    """Remove operational access-enabling sentences; preserve educational content."""
    if not text.strip():
        return text

    sentences = _SENTENCE_SPLIT.split(text.strip())
    kept: list[str] = []
    for sentence in sentences:
        if _OPERATIONAL_SENTENCE.search(sentence):
            continue
        if re.search(r"(?i)\b(?:install|download)\b.*\b(?:tor|specific software|vpn)\b", sentence):
            continue
        kept.append(sentence)

    if not kept or len(" ".join(kept)) < 40:
        return SAFE_DARKWEB_REDIRECT

    rewritten = " ".join(kept).strip()
    # Append safe boundary if we removed operational content
    if len(kept) < len(sentences):
        rewritten += (
            " I can't provide instructions, tools, or methods for accessing or navigating "
            "restricted dark-web services."
        )
    return rewritten


def process_llm_output(prompt: str, generated: str) -> ProcessedOutput:
    """Output pipeline: classify → rewrite if needed → mandatory re-classify (fail-closed)."""
    initial = assess_darkweb_content(generated, is_output=True)

    if initial.decision == "ALLOW":
        return ProcessedOutput(text=generated, assessment=initial)

    if initial.decision == "BLOCK":
        return ProcessedOutput(
            text=SAFE_DARKWEB_REDIRECT,
            original_blocked=True,
            flagged=True,
            assessment=initial,
        )

    # REWRITE path
    rewritten = rewrite_darkweb_content(generated)
    recheck = assess_darkweb_content(rewritten, is_output=True)

    if recheck.decision in ("BLOCK", "REWRITE") and recheck.actionable:
        return ProcessedOutput(
            text=SAFE_DARKWEB_REDIRECT,
            original_blocked=True,
            rewrite_applied=True,
            flagged=True,
            assessment=recheck,
        )

    return ProcessedOutput(
        text=rewritten,
        rewrite_applied=True,
        flagged=False,
        assessment=recheck,
    )


def extract_text_for_assessment(arguments: dict, **extra: str) -> str:
    """Pull assessable text from governed request arguments."""
    parts: list[str] = []
    for key in ("text", "content", "prompt", "message", "query", "input", "command", "url", "domain"):
        val = arguments.get(key)
        if isinstance(val, str) and val.strip():
            parts.append(val)
    for val in extra.values():
        if val and val.strip():
            parts.append(val)
    return " ".join(parts)
