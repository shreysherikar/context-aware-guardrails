"""GxP violation patterns — deterministic pharma compliance language checks."""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class GxpPattern:
    pattern: re.Pattern[str]
    category: str
    gxp_frameworks: tuple[str, ...]
    reason: str
    replacement: str
    principle: str
    severity: str = "medium"
    references: tuple[str, ...] = ()


# GxP = collective term for GMP, GCP, GLP, GVP, GDP, GDocP, etc.
GXP_PATTERNS: list[GxpPattern] = [
    # --- GCP (Good Clinical Practice) ---
    GxpPattern(
        re.compile(r"(?i)\bskip\s+(?:informed\s+)?consent\b"),
        "informed_consent",
        ("GCP", "GDocP"),
        "Informed consent cannot be skipped without documented, IRB/EC-approved exception criteria.",
        "obtain documented informed consent per protocol and ICH E6(R3)",
        "Respect for persons — voluntary, documented consent before trial procedures.",
        "high",
        ("ICH E6(R3) §4.8", "21 CFR 50"),
    ),
    GxpPattern(
        re.compile(r"(?i)\bwaive\s+consent\b(?!\s+(?:with|per)\s+(?:irb|iec|ethics))"),
        "informed_consent",
        ("GCP", "GDocP"),
        "Consent waivers require prior IRB/EC approval and documented justification.",
        "obtain IRB/EC-approved consent waiver with documented justification",
        "Consent waivers are exceptional and must be ethics-approved.",
        "high",
        ("ICH E6(R3) §4.8",),
    ),
    GxpPattern(
        re.compile(r"(?i)\b(?:break|unblind)\s+(?:the\s+)?blind\b"),
        "trial_integrity",
        ("GCP",),
        "Unblinding must follow protocol-defined procedures with documented rationale.",
        "unblind only per protocol-defined emergency unblinding procedures with documentation",
        "Maintain trial integrity and minimize bias through controlled blinding.",
        "high",
        ("ICH E6(R3) §5.5",),
    ),
    GxpPattern(
        re.compile(r"(?i)\bmodify\s+(?:source|original)\s+data\b(?!\s+with\s+(?:audit|documented))"),
        "data_integrity",
        ("GCP", "GDocP"),
        "Source data changes require documented corrections with audit trail — not silent edits.",
        "document data corrections with audit trail, reason, and investigator signature",
        "ALCOA+ — attributable, contemporaneous, accurate corrections only.",
        "critical",
        ("ICH E6(R3) §5.5", "21 CFR Part 11"),
    ),
    GxpPattern(
        re.compile(r"(?i)\bbackdat(?:e|ed|ing)\s+(?:signatures?|records?|forms?)\b"),
        "documentation",
        ("GCP", "GDocP"),
        "Records must be contemporaneous; backdating signatures is not permitted.",
        "complete and sign records contemporaneously with the activity",
        "Contemporaneous documentation — no retroactive signing.",
        "critical",
        ("ICH E6(R3) §5.5", "ALCOA+"),
    ),
    GxpPattern(
        re.compile(r"(?i)\bexclude\s+(?:adverse\s+events?|aes?|saes?)\s+from\s+reporting\b"),
        "safety_reporting",
        ("GCP", "GVP"),
        "All adverse events must be collected and reported per protocol and regulations.",
        "capture and report all adverse events per protocol and regulatory timelines",
        "Complete safety data capture — no selective exclusion.",
        "critical",
        ("ICH E6(R3) §6", "ICH E2A"),
    ),
    # --- GMP (Good Manufacturing Practice) ---
    GxpPattern(
        re.compile(r"(?i)\b(?:skip|bypass|omit)\s+(?:qc|quality\s+control)\s+(?:testing|release)?\b"),
        "batch_release",
        ("GMP",),
        "Batch release requires completed QC testing and QA disposition.",
        "complete QC testing and documented QA batch disposition before release",
        "No batch release without quality unit approval.",
        "critical",
        ("21 CFR 211.165", "EU GMP Annex 16"),
    ),
    GxpPattern(
        re.compile(r"(?i)\bbatch\s+release\s+without\s+(?:qc|quality)\b"),
        "batch_release",
        ("GMP",),
        "Finished product release requires QC results and QA certification.",
        "batch release only after QC completion and QA certification",
        "Quality unit must approve release.",
        "critical",
        ("21 CFR 211.165",),
    ),
    GxpPattern(
        re.compile(r"(?i)\buse\s+expired\s+(?:materials?|reagents?|components?)\b"),
        "materials_control",
        ("GMP",),
        "Expired materials must not be used without approved deviation and impact assessment.",
        "do not use expired materials; quarantine and assess per deviation procedure",
        "Only within-expiry materials in manufacturing.",
        "high",
        ("21 CFR 211.84", "21 CFR 211.125"),
    ),
    GxpPattern(
        re.compile(r"(?i)\bdeviation\s+without\s+(?:investigation|documentation)\b"),
        "deviation_management",
        ("GMP", "GDocP"),
        "Deviations require prompt investigation, impact assessment, and CAPA where needed.",
        "document, investigate, and close deviations per quality system procedures",
        "All deviations investigated and tracked to closure.",
        "high",
        ("21 CFR 211.192", "ICH Q10"),
    ),
    GxpPattern(
        re.compile(r"(?i)\bchange\s+(?:the\s+)?process\s+without\s+validation\b"),
        "process_validation",
        ("GMP",),
        "Process changes require change control and validation/verification per risk.",
        "assess process changes under change control with validation or verification",
        "Validated state maintained through change control.",
        "high",
        ("21 CFR 211.100", "ICH Q12"),
    ),
    # --- GLP (Good Laboratory Practice) ---
    GxpPattern(
        re.compile(r"(?i)\b(?:fabricat|falsif|invent)\w*\s+(?:study\s+)?(?:data|results?)\b"),
        "data_integrity",
        ("GLP", "GDocP"),
        "Data fabrication is prohibited; raw data must be retained and attributable.",
        "record attributable raw data contemporaneously; retain per retention schedule",
        "Integrity of nonclinical study data — no fabrication.",
        "critical",
        ("21 CFR Part 58", "OECD GLP"),
    ),
    GxpPattern(
        re.compile(r"(?i)\b(?:omit|discard|destroy)\s+raw\s+data\b(?!\s+per\s+(?:approved|written))"),
        "raw_data_retention",
        ("GLP", "GDocP"),
        "Raw data must be retained for the required retention period.",
        "retain raw data per GLP retention requirements and SOP",
        "Complete raw data retention and traceability.",
        "high",
        ("21 CFR 58.195",),
    ),
    # --- GVP (Good Pharmacovigilance Practice) ---
    GxpPattern(
        re.compile(r"(?i)\b(?:do\s+not|don'?t|delay|withhold)\s+report\s+(?:saes?|serious\s+adverse\s+events?)\b"),
        "safety_reporting",
        ("GVP", "GCP"),
        "Serious adverse events must be reported within regulatory timelines.",
        "report serious adverse events within required regulatory timelines (e.g., 24h expedited)",
        "Timely safety reporting to protect patients.",
        "critical",
        ("ICH E2A", "EU GVP Module VI"),
    ),
    GxpPattern(
        re.compile(r"(?i)\b(?:hide|suppress|aggregate\s+and\s+hide)\s+(?:individual\s+)?(?:cases?|reports?)\b"),
        "case_reporting",
        ("GVP",),
        "Individual case safety reports must not be suppressed or hidden.",
        "report individual case safety reports per pharmacovigilance procedures",
        "Transparent safety case reporting.",
        "critical",
        ("ICH E2B(R3)", "EU GVP"),
    ),
    GxpPattern(
        re.compile(r"(?i)\boff[- ]label\s+(?:promot|claim|recommend)\w*\b"),
        "promotional_compliance",
        ("GVP", "GCP"),
        "Off-label promotion is restricted; medical information must stay within approved labeling.",
        "limit communications to approved labeling; route off-label inquiries to medical affairs",
        "Approved labeling boundary for promotional content.",
        "high",
        ("FDA OPDP guidance", "PhRMA Code"),
    ),
    # --- GDP (Good Distribution Practice) ---
    GxpPattern(
        re.compile(r"(?i)\bship\s+without\s+(?:temperature|cold\s+chain)\s+monitoring\b"),
        "cold_chain",
        ("GDP",),
        "Temperature-sensitive products require monitored cold-chain distribution.",
        "ship with qualified temperature monitoring and documented chain of custody",
        "Maintain product quality during distribution.",
        "high",
        ("EU GDP Guidelines", "21 CFR 211.150"),
    ),
    GxpPattern(
        re.compile(r"(?i)\bbypass\s+(?:the\s+)?cold\s+chain\b"),
        "cold_chain",
        ("GDP", "GMP"),
        "Cold chain must not be bypassed for temperature-sensitive products.",
        "maintain validated cold-chain controls per distribution qualification",
        "Temperature control throughout supply chain.",
        "high",
        ("EU GDP",),
    ),
    # --- GDocP / ALCOA+ (cross-cutting) ---
    GxpPattern(
        re.compile(r"(?i)\bdelete\s+(?:the\s+)?audit\s+trail\b"),
        "audit_trail",
        ("GDocP", "GMP", "GCP"),
        "Audit trails must be protected and must not be deleted.",
        "preserve audit trails; use documented change control for authorized corrections",
        "Part 11 / ALCOA+ — audit trail integrity.",
        "critical",
        ("21 CFR Part 11", "EU Annex 11"),
    ),
    GxpPattern(
        re.compile(r"(?i)\bundocumented\s+change\b"),
        "change_control",
        ("GDocP", "GMP"),
        "Changes require documented change control assessment and approval.",
        "document changes through approved change control with impact assessment",
        "Controlled documentation lifecycle.",
        "high",
        ("ICH Q10", "21 CFR 211.100"),
    ),
    GxpPattern(
        re.compile(r"(?i)\b(?:no|without)\s+signature\s+on\s+(?:the\s+)?record\b"),
        "signatures",
        ("GDocP",),
        "GxP records require attributable signatures (electronic or handwritten per procedure).",
        "apply attributable signature per electronic records procedure",
        "Attributable — who performed the action.",
        "high",
        ("21 CFR Part 11", "ALCOA+"),
    ),
    GxpPattern(
        re.compile(r"(?i)\bpencil\s+changes?\b"),
        "documentation",
        ("GDocP",),
        "Records must use indelible entries; pencil changes are not acceptable.",
        "make indelible, dated, signed corrections per documentation SOP",
        "Legible, permanent, attributable corrections.",
        "medium",
        ("ALCOA+",),
    ),
    GxpPattern(
        re.compile(r"(?i)\b(?:100\s*%|guaranteed?)\s+(?:cure|effective|safe)\b"),
        "promotional_claims",
        ("GVP", "GCP"),
        "Absolute efficacy/safety claims require substantiation and fair balance.",
        "use qualified claims supported by approved labeling and fair-balance language",
        "Evidence-based, balanced communications.",
        "high",
        ("FDA promotional guidance",),
    ),
    GxpPattern(
        re.compile(r"(?i)\bpatient(?:'s)?\s+(?:ssn|social\s+security|mrn|medical\s+record\s+number)\b"),
        "privacy",
        ("GCP", "GDocP"),
        "Patient identifiers should not appear in general documentation without justification.",
        "[REDACTED — use de-identified study subject ID per privacy policy]",
        "Privacy and confidentiality of trial subjects.",
        "high",
        ("HIPAA", "ICH E6 §4.8"),
    ),
    GxpPattern(
        re.compile(r"(?i)\bignore\s+(?:all\s+)?(?:previous|prior)\s+instructions\b"),
        "instruction_integrity",
        ("GDocP",),
        "Procedure text must not contain instruction-override patterns in controlled documents.",
        "[remove instruction-override language — controlled documents must be authoritative]",
        "Document integrity in validated systems.",
        "medium",
        ("Data integrity guidance",),
    ),
]

GXP_FRAMEWORK_DESCRIPTIONS: dict[str, str] = {
    "GCP": "Good Clinical Practice — ethical, quality clinical trials (ICH E6).",
    "GMP": "Good Manufacturing Practice — quality manufacturing (21 CFR 211 / EU GMP).",
    "GLP": "Good Laboratory Practice — nonclinical study integrity (21 CFR 58).",
    "GVP": "Good Pharmacovigilance Practice — drug safety monitoring (ICH E2).",
    "GDP": "Good Distribution Practice — supply chain quality and traceability.",
    "GDocP": "Good Documentation Practice — ALCOA+ records and audit trails.",
}
