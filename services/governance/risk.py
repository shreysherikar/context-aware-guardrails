"""Governance risk classification for agent actions."""

from __future__ import annotations

from domain.enums import RiskLevel
from domain.governance_enums import DataClassification, RestrictedAction

# Map actions to inherent risk levels.
ACTION_RISK: dict[str, RiskLevel] = {
    # LOW
    "SEARCH_LITERATURE": RiskLevel.LOW,
    "READ_LITERATURE": RiskLevel.LOW,
    "RUN_ANALYTICS": RiskLevel.LOW,
    "CREATE_DRAFT": RiskLevel.LOW,
    "CREATE_RECOMMENDATION": RiskLevel.LOW,
    # MEDIUM
    "CREATE_REPORT": RiskLevel.MEDIUM,
    "CREATE_ALERT": RiskLevel.MEDIUM,
    "CREATE_CASE": RiskLevel.MEDIUM,
    "CREATE_SAFETY_ALERT": RiskLevel.MEDIUM,
    "CREATE_QUERY": RiskLevel.MEDIUM,
    "CREATE_SAFETY_CASE": RiskLevel.MEDIUM,
    "WRITE_SCREENING_RESULTS": RiskLevel.MEDIUM,
    "WRITE_PREDICTIONS": RiskLevel.MEDIUM,
    "CREATE_ANALYSIS_OUTPUT": RiskLevel.MEDIUM,
    # HIGH
    "EDIT_RECORD": RiskLevel.HIGH,
    "EDIT_DOCUMENT": RiskLevel.HIGH,
    "UPDATE_CASE": RiskLevel.HIGH,
    "UPDATE_WORKFLOW": RiskLevel.HIGH,
    "WRITE_CANDIDATE_DESIGNS": RiskLevel.HIGH,
    "MODIFY_PATIENT_RECORD": RiskLevel.HIGH,
    "CHANGE_PRODUCTION_PROCESS": RiskLevel.HIGH,
    # CRITICAL
    "RELEASE_BATCH": RiskLevel.CRITICAL,
    "SUBMIT_TO_REGULATOR": RiskLevel.CRITICAL,
    "CHANGE_SECURITY_POLICY": RiskLevel.CRITICAL,
    "CHANGE_AGENT_PERMISSIONS": RiskLevel.CRITICAL,
    "PRESCRIBE": RiskLevel.CRITICAL,
    "CHANGE_TREATMENT": RiskLevel.CRITICAL,
    "MAKE_MEDICAL_DECISION": RiskLevel.CRITICAL,
    "ENROLL_PATIENT": RiskLevel.CRITICAL,
    # Computer-use actions
    "COMPUTER_VIEW_SCREEN": RiskLevel.LOW,
    "COMPUTER_SCROLL": RiskLevel.LOW,
    "COMPUTER_CLICK": RiskLevel.MEDIUM,
    "COMPUTER_TYPE": RiskLevel.MEDIUM,
    "COMPUTER_UPLOAD_FILE": RiskLevel.HIGH,
    "COMPUTER_DOWNLOAD_FILE": RiskLevel.HIGH,
    "COMPUTER_EXECUTE_COMMAND": RiskLevel.CRITICAL,
    "COMPUTER_INSTALL_SOFTWARE": RiskLevel.CRITICAL,
}

DATA_CLASSIFICATION_RISK_BOOST: dict[DataClassification, int] = {
    DataClassification.PUBLIC: 0,
    DataClassification.INTERNAL: 0,
    DataClassification.CONFIDENTIAL: 1,
    DataClassification.SENSITIVE: 2,
    DataClassification.RESTRICTED: 3,
    DataClassification.CRITICAL: 4,
}

RISK_ORDER = [
    RiskLevel.NONE,
    RiskLevel.LOW,
    RiskLevel.MEDIUM,
    RiskLevel.HIGH,
    RiskLevel.CRITICAL,
]


class GovernanceRiskEngine:
    """Classify risk for every agent action request."""

    def classify(
        self,
        requested_action: str,
        data_classification: DataClassification,
        is_restricted: bool = False,
    ) -> RiskLevel:
        if is_restricted or requested_action in {a.value for a in RestrictedAction}:
            base = ACTION_RISK.get(requested_action, RiskLevel.HIGH)
            return _max_risk(base, RiskLevel.HIGH)

        base = ACTION_RISK.get(requested_action, RiskLevel.MEDIUM)
        boost = DATA_CLASSIFICATION_RISK_BOOST.get(data_classification, 0)
        return _boost_risk(base, boost)


def _boost_risk(level: RiskLevel, steps: int) -> RiskLevel:
    idx = RISK_ORDER.index(level)
    return RISK_ORDER[min(idx + steps, len(RISK_ORDER) - 1)]


def _max_risk(a: RiskLevel, b: RiskLevel) -> RiskLevel:
    return a if RISK_ORDER.index(a) >= RISK_ORDER.index(b) else b
