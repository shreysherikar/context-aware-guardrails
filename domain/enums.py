from enum import StrEnum


class RiskLevel(StrEnum):
    NONE = "NONE"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class RiskCategory(StrEnum):
    NONE = "NONE"
    PII = "PII"
    PHI = "PHI"
    OFF_LABEL = "OFF_LABEL"
    IP = "IP"
    PROMPT_INJECTION = "PROMPT_INJECTION"


class DataSensitivity(StrEnum):
    PUBLIC = "PUBLIC"
    INTERNAL = "INTERNAL"
    CONFIDENTIAL = "CONFIDENTIAL"
    PATIENT_IDENTIFIABLE = "PATIENT_IDENTIFIABLE"


class PolicyAction(StrEnum):
    ALLOW = "ALLOW"
    REWRITE = "REWRITE"
    CLARIFY = "CLARIFY"
    REVIEW = "REVIEW"
    BLOCK = "BLOCK"


class VerificationStatus(StrEnum):
    """Verdict of verifying one claim against approved-source evidence.

    UNSUPPORTED and UNVERIFIABLE are deliberately distinct: "contradicted by
    the approved source" is not the same as "no applicable approved source".
    Every consumer must treat any value other than SUPPORTED as unverified,
    so a status added to this enum later resolves conservatively instead of
    silently permitting a claim (fail closed).
    """

    SUPPORTED = "SUPPORTED"
    UNSUPPORTED = "UNSUPPORTED"
    UNVERIFIABLE = "UNVERIFIABLE"


class EvidenceRelationship(StrEnum):
    """Relationship between a claim and the approved-source evidence for it.

    Coarse, auditable signal produced by the evidence-relationship assessor
    (services/evidence_relationship). SUPPORTS means every applicable passage
    agrees with the claim's polarity; CONTRADICTS means every applicable
    passage disagrees with it; CONFLICTING means applicable passages disagree
    with each other; INSUFFICIENT means nothing applicable was available to
    judge the claim.

    This is evidence metadata only: it carries no authority to allow, block,
    or rewrite anything. Every consumer must treat any value other than
    SUPPORTS as unsupported-by-evidence, so a value added to this enum later
    resolves conservatively instead of silently permitting a claim (fail
    closed). Failures inside the assessor degrade to INSUFFICIENT — never to
    SUPPORTS.
    """

    SUPPORTS = "SUPPORTS"
    CONTRADICTS = "CONTRADICTS"
    INSUFFICIENT = "INSUFFICIENT"
    CONFLICTING = "CONFLICTING"
