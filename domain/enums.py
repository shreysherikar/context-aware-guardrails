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
