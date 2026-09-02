"""Predefined sandbox environments for governed computer use."""

from __future__ import annotations

from domain.enums import RiskLevel
from domain.governance_enums import ComputerPermission
from domain.governance_models import ComputerEnvironment

_LOW_ACTIONS = [
    ComputerPermission.COMPUTER_VIEW_SCREEN.value,
    ComputerPermission.COMPUTER_SCROLL.value,
]

_MEDIUM_ACTIONS = _LOW_ACTIONS + [
    ComputerPermission.COMPUTER_CLICK.value,
    ComputerPermission.COMPUTER_TYPE.value,
    ComputerPermission.COMPUTER_READ_FILE.value,
    ComputerPermission.COMPUTER_BROWSER_NAVIGATION.value,
    ComputerPermission.COMPUTER_OPEN_APPLICATION.value,
]

_HIGH_ACTIONS = _MEDIUM_ACTIONS + [
    ComputerPermission.COMPUTER_UPLOAD_FILE.value,
    ComputerPermission.COMPUTER_DOWNLOAD_FILE.value,
    ComputerPermission.COMPUTER_SEND_MESSAGE.value,
    ComputerPermission.COMPUTER_SUBMIT_FORM.value,
]

PHARMA_ENVIRONMENTS: dict[str, ComputerEnvironment] = {
    "sandbox-default": ComputerEnvironment(
        environment_id="sandbox-default",
        name="Default Sandbox",
        description="General-purpose isolated environment with standard pharma restrictions.",
        allowed_apps=["chrome", "firefox", "excel", "word", "notepad"],
        allowed_domains=["intranet.pharma.local", "lims.pharma.local", "edc.pharma.local"],
        allowed_directories=["/sandbox", "C:\\Sandbox"],
        blocked_directories=["/etc", "/root", "C:\\Windows\\System32", "C:\\Program Files"],
        default_risk_limit=RiskLevel.MEDIUM,
        default_actions=_MEDIUM_ACTIONS,
    ),
    "clinical-readonly": ComputerEnvironment(
        environment_id="clinical-readonly",
        name="Clinical Read-Only",
        description="View clinical systems and read files — no writes or uploads.",
        allowed_apps=["chrome", "excel"],
        allowed_domains=["edc.pharma.local", "ctms.pharma.local", "intranet.pharma.local"],
        allowed_directories=["/sandbox/clinical"],
        blocked_directories=["/etc", "/root", "C:\\Windows"],
        default_risk_limit=RiskLevel.LOW,
        default_actions=_LOW_ACTIONS
        + [
            ComputerPermission.COMPUTER_READ_FILE.value,
            ComputerPermission.COMPUTER_BROWSER_NAVIGATION.value,
        ],
    ),
    "regulatory-submission": ComputerEnvironment(
        environment_id="regulatory-submission",
        name="Regulatory Submission",
        description="Controlled environment for regulatory document workflows.",
        allowed_apps=["word", "chrome"],
        allowed_domains=["regulatory.pharma.local", "intranet.pharma.local"],
        allowed_directories=["/sandbox/regulatory"],
        blocked_directories=["/etc", "/root"],
        file_transfer_restricted=True,
        default_risk_limit=RiskLevel.HIGH,
        default_actions=_HIGH_ACTIONS,
    ),
    "pv-case-review": ComputerEnvironment(
        environment_id="pv-case-review",
        name="Pharmacovigilance Case Review",
        description="PV case intake and narrative review with restricted external access.",
        allowed_apps=["chrome", "excel", "word"],
        allowed_domains=["pv.pharma.local", "intranet.pharma.local"],
        allowed_directories=["/sandbox/pv"],
        default_risk_limit=RiskLevel.MEDIUM,
        default_actions=_MEDIUM_ACTIONS,
    ),
}


def get_environment(environment_id: str) -> ComputerEnvironment | None:
    return PHARMA_ENVIRONMENTS.get(environment_id)


def list_environments() -> list[ComputerEnvironment]:
    return list(PHARMA_ENVIRONMENTS.values())
