"""Unauthorized cyber-offense patterns for the text risk classifier.

Catches hacking, malware, phishing-kit, and data-theft requests that should
never be ALLOW. Everyday uses of "hack" (hackathon, life hack, hack together)
and defensive/educational wording stay allowed.

Labeled examples in data/offensive_cyber_prompts.csv are loaded as an
exact-match table so newly added training rows are detected immediately.
"""

from __future__ import annotations

import csv
import re
from functools import lru_cache
from pathlib import Path

from domain.enums import RiskCategory

_DATASET_PATH = (
    Path(__file__).resolve().parents[2] / "data" / "offensive_cyber_prompts.csv"
)

_CATEGORY_BY_NAME = {
    "MALWARE": RiskCategory.MALWARE,
    "PHISHING": RiskCategory.PHISHING,
    "DATA_EXFILTRATION": RiskCategory.DATA_EXFILTRATION,
    "PROMPT_INJECTION": RiskCategory.PROMPT_INJECTION,
}

_HACKING: list[str] = [
    r"\bhack (this|that|it|them|him|her)\b",
    (
        r"\bhack (the )?(system|website|site|server|network|account|"
        r"wifi|wi-fi|computer|phone|email|database|db|app|application)\b"
    ),
    r"\bhack (?:someone(?:'s)?|my (?:ex|girlfriend|boyfriend|wife|husband)|their)\b",
    (
        r"\bhack (?:instagram|facebook|gmail|whatsapp|snapchat|"
        r"twitter|tiktok|icloud|paypal)\b"
    ),
    r"\bhack .{0,60} for me\b",
    r"\bhack into\b",
    r"\bplease hack\b",
    r"\bhelp me hack\b",
    r"\b(?:can|could) you hack\b",
    r"\b(?:i )?(?:want|need) you to hack\b",
    r"\bi (?:want|wanna|need) to hack\b",
    r"\btry to hack\b",
    r"\bhow (?:do|can|to) (?:i |you |we )?hack\b",
    r"\bteach me (?:how )?to hack\b",
    r"\bshow me how to hack\b",
    r"\bhacking into\b",
    r"\bhacking (?:a |the |this )?(?:system|account|network|wifi|website|server|database)\b",
    r"\bexploit (this|that|it)\b",
    (
        r"\bexploit (the )?(vulnerability|cve|zero-?day|system|server|"
        r"network|database|website|site|app|application|account)\b"
    ),
    (
        r"\b(?:write|create|build|generate|make|craft|give me|drop|deploy|spread) "
        r"(?:me )?(?:an? |some )?(?:exploit|ransomware|malware|virus|worm|"
        r"trojan|rootkit|backdoor|botnet|spyware|keylogger)\b"
    ),
    (
        r"\b(?:i need|send me|give me) (?:a |an )?"
        r"(?:virus|malware|ransomware|keylogger|trojan)\b"
    ),
    (
        r"\bhow to (?:make|write|create) (?:a )?"
        r"(?:virus|malware|ransomware|keylogger|worm|trojan)\b"
    ),
    (
        r"\b(?:install|plant) (?:a |an |the )?(?:keylogger|backdoor|rootkit|"
        r"trojan|ransomware|spyware)\b"
    ),
    r"\b(?:ransomware|keylogger) (?:payload|encrypt|builder|note)\b",
    r"\bkeylog(?:ging)?\b",
    r"\breverse ?shell\b",
    r"\bbind ?shell\b",
    r"\b(?:web ?shell|drop (?:a )?(?:web)?shell)\b",
    r"\bremote access trojan\b",
    r"\b(?:info ?stealer|cookie stealer|browser stealer)\b",
    r"\bcommand and control\b|\bc2 server\b",
    r"\bprivilege escalation (?:exploit|payload|poc)\b",
    r"\b(?:zero-?day|0day) (?:exploit|payload)\b",
    r"\bcrack (?:this |the |a )?(?:password|hash|wifi|wi-fi|account|login|pin)\b",
    r"\bbrute[- ]force (?:the |this |a )?(?:password|login|account|hash|wifi)\b",
    (
        r"\bsteal (?:this |the |a |all )?(?:password|passwords|credential|"
        r"credentials|cookie|cookies|token|session|account)\b"
    ),
    r"\bdump (?:the )?(?:database|db|hashes|password)\b",
    r"\bsql injection (?:payload|poc|attack)\b",
    r"\b(?:give me|write|craft) (?:a |an |me )?sql injection\b",
    r"\bxss (?:payload|poc|attack)\b",
    (
        r"\bbreak into (?:the )?(?:account|system|server|network|"
        r"computer|wifi|database|email|phone)\b"
    ),
    (
        r"\bget (?:me )?into (?:their|his|her|someone's) "
        r"(?:account|email|phone)\b"
    ),
    (
        r"\bhow (?:can|do) i (?:get|break) into (?:someone(?:'s)? |their |"
        r"this |the )?(?:account|email|system|server|wifi|computer|phone)\b"
    ),
    r"\bbypass (?:the )?(?:authentication|login|password|mfa|2fa|access control)\b",
    r"\bgain unauthorized access\b",
    r"\b(?:launch|perform|run) (?:a )?(?:ddos|dos) attack\b",
    r"\bhow (?:do i |to )?ddos\b",
    r"\bddos (?:this|the (?:site|server|network))\b",
    r"\b(?:take down|knock offline) (?:the |this |their )?(?:website|site|server)\b",
    r"\bflood (?:the |this )?(?:server|site|website)\b",
    r"\bclone (?:this |the |a )?login page\b",
    r"\bharvest (?:passwords|credentials|logins)\b",
    r"\b(?:pwn|pwning)\b",
    r"\bdownload (?:and )?(?:run|execute) (?:the )?(?:executable|malware)\b",
    r"\binfect (?:this |the |their )?(?:computer|pc|phone|device|system)\b",
    (
        r"\bspy on (?:my |their |someone's )?(?:phone|computer|webcam|"
        r"girlfriend|boyfriend|wife|husband|ex|coworker)\b"
    ),
    r"\bencrypt (?:their |the |all )(?:files|disk).{0,30}ransom",
    r"\b(?:credential stuffing|password spraying)\b",
    r"\bsim[- ]swap\b",
    (
        r"\bsocial engineer (?:the |a |their )?"
        r"(?:password|credential|login|employee)\b"
    ),
    r"\b(?:use|run|give me) (?:mimikatz|hashcat|hydra|sqlmap)\b",
    r"\bpowershell -enc\b",
    r"curl\s+\S+\s*\|\s*bash",
]

_EXFIL: list[str] = [
    r"\bexfiltrat(?:e|ion)\b",
    (
        r"\bsend (?:all |the )?(?:data|files|records) "
        r"(?:externally|to (?:external|unknown|unauthorized))\b"
    ),
    (
        r"\bupload all (?:data|files|records) "
        r"(?:externally|to (?:external|unknown|unauthorized))\b"
    ),
    r"\bdump all (?:data|records|files)\b",
    r"\bsteal (?:all |the |this )*(?:data|files|records|database)\b",
    r"\bleak (?:all |the )?(?:data|database|credentials)\b",
]

_PHISHING: list[str] = [
    r"\bwrite (?:a |me )?(?:an? )?phishing (?:email|message|page|kit)\b",
    r"\bphishing (?:email|kit|page|campaign) for me\b",
    r"\bspoof (?:this |the |a )?(?:login|bank|it helpdesk|help ?desk) page\b",
    r"\bmake (?:a |an |me )?(?:fake |spoofed )?(?:login page|phishing page)\b",
    r"\b(?:draft|compose|create|send|write) (?:a |an |me )?(?:spear[- ]?)?phishing\b",
    r"\bspear[- ]phish",
    r"\b(?:vishing|smishing) (?:script|template|message|call|text)\b",
    r"\bbusiness email compromise\b",
    r"\bcredential(?:s)? harvest",
]

_INJECTION: list[str] = [
    r"\bjailbreak (?:the |this )?(?:ai|model|llm|chat|gpt|guardrail)\b",
    r"\bdan mode\b",
    r"\breveal (?:your |the )?(?:system prompt|hidden instructions)\b",
    r"\bdisable (?:the )?(?:safety|security|guardrail)s?\b",
]

_SAFE_HACK_CONTEXT = re.compile(
    r"(?i)\b(hackathon|life[- ]hack|hack together|hacky|hacker news)\b"
)

_EXPLICIT_HACK = re.compile(
    r"(?i)\b(hack this|hack that|hack it|hack into|hack the|please hack|help me hack)\b"
)

_COMPILED: list[tuple[re.Pattern[str], RiskCategory]] = [
    *((re.compile(p, re.I), RiskCategory.MALWARE) for p in _HACKING),
    *((re.compile(p, re.I), RiskCategory.DATA_EXFILTRATION) for p in _EXFIL),
    *((re.compile(p, re.I), RiskCategory.PHISHING) for p in _PHISHING),
    *((re.compile(p, re.I), RiskCategory.PROMPT_INJECTION) for p in _INJECTION),
]


def _normalize(text: str) -> str:
    return " ".join(text.lower().split())


@lru_cache(maxsize=1)
def load_offensive_cyber_rows() -> tuple[dict[str, str], ...]:
    """Labeled training/eval rows from data/offensive_cyber_prompts.csv."""
    if not _DATASET_PATH.is_file():
        return ()
    with _DATASET_PATH.open(encoding="utf-8", newline="") as handle:
        return tuple(dict(row) for row in csv.DictReader(handle))


@lru_cache(maxsize=1)
def _dataset_unsafe_lookup() -> dict[str, RiskCategory]:
    lookup: dict[str, RiskCategory] = {}
    for row in load_offensive_cyber_rows():
        if (row.get("label") or "").strip().lower() != "unsafe":
            continue
        category = _CATEGORY_BY_NAME.get((row.get("category") or "").strip().upper())
        prompt = (row.get("prompt") or "").strip()
        if category is None or not prompt:
            continue
        lookup[_normalize(prompt)] = category
    return lookup


def match_offensive_cyber(text: str) -> list[tuple[RiskCategory, str, int, int]]:
    """Return (category, matched text, start, end) for unauthorized cyber asks."""
    if not text:
        return []

    hits: list[tuple[RiskCategory, str, int, int]] = []
    seen: set[tuple[int, int, str]] = set()
    for pattern, category in _COMPILED:
        for match in pattern.finditer(text):
            key = (match.start(), match.end(), category.value)
            if key in seen:
                continue
            seen.add(key)
            hits.append((category, match.group(0), match.start(), match.end()))

    dataset_category = _dataset_unsafe_lookup().get(_normalize(text))
    if dataset_category is not None:
        key = (0, len(text), dataset_category.value)
        if key not in seen:
            seen.add(key)
            hits.append((dataset_category, text.strip(), 0, len(text)))

    if _SAFE_HACK_CONTEXT.search(text) and not _EXPLICIT_HACK.search(text):
        hits = [hit for hit in hits if "hack" not in hit[1].lower()]

    return hits


def offensive_categories(text: str) -> set[RiskCategory]:
    return {category for category, _, _, _ in match_offensive_cyber(text)}


def is_benign_hack_context(text: str) -> bool:
    """True for everyday 'hack' wording that is not an attack request."""
    return bool(_SAFE_HACK_CONTEXT.search(text) and not _EXPLICIT_HACK.search(text))
