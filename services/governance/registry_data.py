"""Pre-defined pharmaceutical AI agent registry data."""

from __future__ import annotations

from domain.enums import RiskLevel
from domain.governance_enums import (
    ActionPermission,
    ComputerPermission,
    DataClassification,
    DataPermission,
    RestrictedAction,
    ToolPermission,
)
from domain.governance_models import AgentRegistryEntry

# Shared restricted actions for most agents
_STANDARD_RESTRICTED = [
    RestrictedAction.APPROVE.value,
    RestrictedAction.PUBLISH.value,
    RestrictedAction.DELETE_RECORD.value,
    RestrictedAction.CHANGE_AGENT_PERMISSIONS.value,
    RestrictedAction.DISABLE_GOVERNANCE.value,
    RestrictedAction.DISABLE_LOGGING.value,
    RestrictedAction.DELETE_AUDIT_RECORD.value,
]

_READ_ONLY_LITERATURE = [
    DataPermission.READ_LITERATURE.value,
    DataPermission.READ_PATENTS.value,
    DataPermission.READ_INTERNAL_DOCUMENTS.value,
    ToolPermission.SEARCH_LITERATURE.value,
    ToolPermission.SEARCH_PATENTS.value,
    ActionPermission.CREATE_DRAFT.value,
    ActionPermission.CREATE_REPORT.value,
]

_CU_READONLY = [
    ComputerPermission.COMPUTER_VIEW_SCREEN.value,
    ComputerPermission.COMPUTER_SCROLL.value,
    ComputerPermission.COMPUTER_BROWSER_NAVIGATION.value,
    ComputerPermission.COMPUTER_READ_FILE.value,
]

_CU_STANDARD = _CU_READONLY + [
    ComputerPermission.COMPUTER_CLICK.value,
    ComputerPermission.COMPUTER_TYPE.value,
    ComputerPermission.COMPUTER_OPEN_APPLICATION.value,
]

_CU_EXTENDED = _CU_STANDARD + [
    ComputerPermission.COMPUTER_UPLOAD_FILE.value,
    ComputerPermission.COMPUTER_DOWNLOAD_FILE.value,
    ComputerPermission.COMPUTER_SUBMIT_FORM.value,
]


def _agent(
    agent_id: str,
    name: str,
    agent_type: str,
    description: str,
    category: str,
    capabilities: list[str],
    permissions: list[str],
    *,
    restricted: list[str] | None = None,
    human_approval: list[str] | None = None,
    data_classes: list[DataClassification] | None = None,
    tools: list[str] | None = None,
    computer_perms: list[str] | None = None,
    max_risk: RiskLevel = RiskLevel.MEDIUM,
) -> AgentRegistryEntry:
    return AgentRegistryEntry(
        agent_id=agent_id,
        name=name,
        agent_type=agent_type,
        description=description,
        category=category,
        capabilities=capabilities,
        permissions=permissions,
        restricted_actions=(restricted or []) + _STANDARD_RESTRICTED,
        human_approval_required=human_approval or [],
        data_classifications_allowed=data_classes or [DataClassification.INTERNAL],
        tools_allowed=tools or [],
        computer_use_permissions=computer_perms or [],
        max_risk_level=max_risk,
    )


# ---------------------------------------------------------------------------
# Drug Discovery (8)
# ---------------------------------------------------------------------------
DRUG_DISCOVERY_AGENTS: list[AgentRegistryEntry] = [
    _agent(
        "target-discovery",
        "Target Discovery Agent",
        "discovery",
        "Identify biological targets, analyze pathways, rank hypotheses.",
        "drug_discovery",
        ["Identify targets", "Analyze pathways", "Rank targets", "Generate hypotheses"],
        [
            DataPermission.READ_SCIENTIFIC_DATABASES.value,
            DataPermission.READ_INTERNAL_RESEARCH.value,
            DataPermission.READ_GENOMIC_DATA.value,
            ToolPermission.SEARCH_LITERATURE.value,
            ToolPermission.RUN_ANALYTICS.value,
            ToolPermission.RUN_ML_MODEL.value,
            ActionPermission.CREATE_RECOMMENDATION.value,
        ],
        restricted=[
            RestrictedAction.DELETE_RESEARCH_DATA.value,
            RestrictedAction.MODIFY_SOURCE_DATABASE.value,
            RestrictedAction.INITIATE_LAB_EXPERIMENT.value,
        ],
        data_classes=[
            DataClassification.INTERNAL,
            DataClassification.CONFIDENTIAL,
            DataClassification.PUBLIC,
        ],
    ),
    _agent(
        "literature-research",
        "Literature Research Agent",
        "research",
        "Search literature, patents, clinical docs; summarize and cite evidence.",
        "drug_discovery",
        ["Search literature", "Search patents", "Summarize evidence", "Generate cited briefs"],
        _READ_ONLY_LITERATURE,
        data_classes=[DataClassification.PUBLIC, DataClassification.INTERNAL],
        max_risk=RiskLevel.LOW,
    ),
    _agent(
        "drug-design",
        "Drug Design Agent",
        "design",
        "Generate and rank candidate molecules; predict properties.",
        "drug_discovery",
        ["Generate molecules", "Modify structures", "Predict properties", "Rank candidates"],
        [
            DataPermission.READ_MOLECULAR_DATABASES.value,
            ToolPermission.RUN_COMPUTATIONAL_CHEMISTRY.value,
            ToolPermission.RUN_SIMULATION.value,
            ActionPermission.WRITE_CANDIDATE_DESIGNS.value,
            ActionPermission.CREATE_RECOMMENDATION.value,
        ],
        restricted=[
            RestrictedAction.INITIATE_LAB_EXPERIMENT.value,
            RestrictedAction.MODIFY_SOURCE_DATABASE.value,
        ],
        human_approval=[RestrictedAction.INITIATE_LAB_EXPERIMENT.value],
        data_classes=[DataClassification.CONFIDENTIAL, DataClassification.INTERNAL],
    ),
    _agent(
        "molecule-screening",
        "Molecule Screening Agent",
        "screening",
        "Screen compound libraries, predict activity, rank compounds.",
        "drug_discovery",
        ["Screen libraries", "Predict activity", "Rank compounds"],
        [
            DataPermission.READ_COMPOUND_LIBRARIES.value,
            ToolPermission.RUN_ML_MODEL.value,
            ToolPermission.RUN_COMPUTATIONAL_SCREENING.value,
            ActionPermission.WRITE_SCREENING_RESULTS.value,
        ],
        data_classes=[DataClassification.CONFIDENTIAL, DataClassification.INTERNAL],
    ),
    _agent(
        "admet",
        "ADMET Agent",
        "analysis",
        "Predict absorption, distribution, metabolism, excretion, toxicity.",
        "drug_discovery",
        ["Predict ADMET properties", "Rank by safety"],
        [
            DataPermission.READ_COMPOUND_LIBRARIES.value,
            ToolPermission.RUN_ADMET_MODEL.value,
            ActionPermission.WRITE_PREDICTIONS.value,
        ],
        data_classes=[DataClassification.CONFIDENTIAL, DataClassification.INTERNAL],
    ),
    _agent(
        "drug-repurposing",
        "Drug Repurposing Agent",
        "analysis",
        "Identify repurposing opportunities from drug databases and literature.",
        "drug_discovery",
        ["Identify repurposing candidates", "Compare mechanisms", "Rank opportunities"],
        [
            DataPermission.READ_LITERATURE.value,
            DataPermission.READ_INTERNAL_RESEARCH.value,
            ToolPermission.SEARCH_LITERATURE.value,
            ToolPermission.RUN_ANALYTICS.value,
            ActionPermission.CREATE_RECOMMENDATION.value,
        ],
        data_classes=[
            DataClassification.PUBLIC,
            DataClassification.INTERNAL,
            DataClassification.CONFIDENTIAL,
        ],
    ),
    _agent(
        "bioinformatics",
        "Bioinformatics Agent",
        "analysis",
        "Analyze genomic, transcriptomic, proteomic data; run pipelines.",
        "drug_discovery",
        ["Analyze omics data", "Run bioinformatics pipelines", "Identify patterns"],
        [
            DataPermission.READ_GENOMIC_DATA.value,
            ToolPermission.RUN_BIOINFORMATICS_PIPELINE.value,
            ToolPermission.RUN_ANALYTICS.value,
            ActionPermission.WRITE_ANALYSIS_RESULTS.value,
        ],
        data_classes=[DataClassification.CONFIDENTIAL, DataClassification.RESTRICTED],
    ),
    _agent(
        "biomarker-discovery",
        "Biomarker Discovery Agent",
        "analysis",
        "Identify candidate biomarkers; correlate with outcomes.",
        "drug_discovery",
        ["Identify biomarkers", "Correlate with outcomes", "Generate hypotheses"],
        [
            DataPermission.READ_GENOMIC_DATA.value,
            DataPermission.READ_CLINICAL_DATA.value,
            ToolPermission.RUN_STATISTICAL_MODEL.value,
            ActionPermission.WRITE_ANALYSIS_RESULTS.value,
        ],
        data_classes=[DataClassification.SENSITIVE, DataClassification.RESTRICTED],
        max_risk=RiskLevel.HIGH,
    ),
]

# ---------------------------------------------------------------------------
# Clinical Trial (9)
# ---------------------------------------------------------------------------
CLINICAL_TRIAL_AGENTS: list[AgentRegistryEntry] = [
    _agent(
        "clinical-trial-design",
        "Clinical Trial Design Agent",
        "clinical",
        "Recommend study designs, endpoints, population selection.",
        "clinical_trial",
        ["Recommend designs", "Analyze endpoints", "Population selection"],
        [
            DataPermission.READ_CLINICAL_DATA.value,
            DataPermission.READ_LITERATURE.value,
            ToolPermission.RUN_ANALYTICS.value,
            ActionPermission.CREATE_RECOMMENDATION.value,
        ],
        restricted=[RestrictedAction.ACTIVATE_TRIAL.value],
        human_approval=[RestrictedAction.ACTIVATE_TRIAL.value],
        data_classes=[DataClassification.SENSITIVE, DataClassification.INTERNAL],
    ),
    _agent(
        "protocol-generation",
        "Protocol Generation Agent",
        "clinical",
        "Generate draft protocols; detect missing sections.",
        "clinical_trial",
        ["Generate protocols", "Detect inconsistencies"],
        [
            DataPermission.READ_TEMPLATES.value,
            DataPermission.READ_REGULATORY_DATA.value,
            ActionPermission.CREATE_DRAFT.value,
        ],
        restricted=[RestrictedAction.FINALIZE_PROTOCOL.value, RestrictedAction.PUBLISH.value],
        human_approval=[RestrictedAction.FINALIZE_PROTOCOL.value],
        data_classes=[DataClassification.CONFIDENTIAL, DataClassification.SENSITIVE],
    ),
    _agent(
        "patient-recruitment",
        "Patient Recruitment Agent",
        "clinical",
        "Search authorized datasets; identify eligible participants.",
        "clinical_trial",
        ["Search patient datasets", "Identify eligible participants"],
        [
            DataPermission.READ_PATIENT_DATA.value,
            DataPermission.READ_CLINICAL_DATA.value,
            ActionPermission.CREATE_RECRUITMENT_CANDIDATE.value,
        ],
        restricted=[
            RestrictedAction.ENROLL_PATIENT.value,
            RestrictedAction.MAKE_MEDICAL_DECISION.value,
        ],
        human_approval=[RestrictedAction.ENROLL_PATIENT.value],
        data_classes=[DataClassification.RESTRICTED, DataClassification.SENSITIVE],
        max_risk=RiskLevel.HIGH,
    ),
    _agent(
        "patient-eligibility",
        "Patient Eligibility Agent",
        "clinical",
        "Compare patient info with inclusion/exclusion criteria.",
        "clinical_trial",
        ["Assess eligibility", "Flag uncertain cases"],
        [
            DataPermission.READ_PATIENT_DATA.value,
            DataPermission.READ_CLINICAL_DATA.value,
            ActionPermission.CREATE_ELIGIBILITY_ASSESSMENT.value,
        ],
        restricted=[
            RestrictedAction.ENROLL_PATIENT.value,
            RestrictedAction.MAKE_MEDICAL_DECISION.value,
        ],
        human_approval=[RestrictedAction.ENROLL_PATIENT.value],
        data_classes=[DataClassification.RESTRICTED],
        max_risk=RiskLevel.HIGH,
    ),
    _agent(
        "clinical-site-selection",
        "Clinical Site Selection Agent",
        "clinical",
        "Rank clinical sites by performance and enrollment history.",
        "clinical_trial",
        ["Rank sites", "Analyze enrollment history"],
        [
            DataPermission.READ_SITE_PERFORMANCE.value,
            DataPermission.READ_CTMS.value,
            ToolPermission.RUN_ANALYTICS.value,
            ActionPermission.CREATE_RECOMMENDATION.value,
        ],
        data_classes=[DataClassification.INTERNAL, DataClassification.CONFIDENTIAL],
    ),
    _agent(
        "trial-monitoring",
        "Trial Monitoring Agent",
        "clinical",
        "Monitor enrollment, detect deviations and anomalies.",
        "clinical_trial",
        ["Monitor enrollment", "Detect deviations", "Create alerts"],
        [
            DataPermission.READ_CTMS.value,
            DataPermission.READ_EDC.value,
            ToolPermission.ACCESS_CTMS.value,
            ToolPermission.ACCESS_EDC.value,
            ActionPermission.CREATE_ALERT.value,
        ],
        data_classes=[DataClassification.SENSITIVE, DataClassification.CONFIDENTIAL],
    ),
    _agent(
        "clinical-data-cleaning",
        "Clinical Data Cleaning Agent",
        "clinical",
        "Detect inconsistent data; create data-quality queries.",
        "clinical_trial",
        ["Detect inconsistencies", "Create data-quality queries"],
        [
            DataPermission.READ_EDC.value,
            ToolPermission.ACCESS_EDC.value,
            ActionPermission.CREATE_DATA_QUALITY_QUERY.value,
        ],
        restricted=[
            RestrictedAction.SILENTLY_MODIFY_PATIENT_DATA.value,
            RestrictedAction.MODIFY_PATIENT_RECORD.value,
        ],
        data_classes=[DataClassification.SENSITIVE, DataClassification.RESTRICTED],
        computer_perms=_CU_STANDARD,
        max_risk=RiskLevel.HIGH,
    ),
    _agent(
        "statistical-analysis",
        "Statistical Analysis Agent",
        "clinical",
        "Execute approved statistical analyses; generate reports.",
        "clinical_trial",
        ["Run statistical analyses", "Generate tables and figures"],
        [
            DataPermission.READ_CLINICAL_DATA.value,
            ToolPermission.RUN_STATISTICAL_MODEL.value,
            ActionPermission.CREATE_ANALYSIS_OUTPUT.value,
            ActionPermission.CREATE_REPORT.value,
        ],
        data_classes=[DataClassification.SENSITIVE, DataClassification.CONFIDENTIAL],
    ),
    _agent(
        "clinical-documentation",
        "Clinical Documentation Agent",
        "clinical",
        "Generate draft clinical documentation and report drafts.",
        "clinical_trial",
        ["Generate documentation", "Summarize study information"],
        [
            DataPermission.READ_CLINICAL_DATA.value,
            DataPermission.READ_TEMPLATES.value,
            ActionPermission.CREATE_DRAFT.value,
        ],
        restricted=[RestrictedAction.PUBLISH.value],
        data_classes=[DataClassification.SENSITIVE, DataClassification.CONFIDENTIAL],
    ),
]

# ---------------------------------------------------------------------------
# Pharmacovigilance (8)
# ---------------------------------------------------------------------------
PHARMACOVIGILANCE_AGENTS: list[AgentRegistryEntry] = [
    _agent(
        "pv-adverse-event-detection",
        "Adverse Event Detection Agent",
        "pv",
        "Detect adverse-event candidates from safety reports and literature.",
        "pharmacovigilance",
        ["Detect AE candidates", "Extract safety info", "Create alerts"],
        [
            DataPermission.READ_SAFETY_REPORTS.value,
            DataPermission.READ_PV_DATA.value,
            DataPermission.READ_LITERATURE.value,
            ActionPermission.CREATE_ALERT.value,
            ActionPermission.CREATE_SAFETY_ALERT.value,
        ],
        data_classes=[DataClassification.SENSITIVE, DataClassification.CONFIDENTIAL],
    ),
    _agent(
        "pv-case-intake",
        "Case Intake Agent",
        "pv",
        "Extract structured info from safety reports; create PV cases.",
        "pharmacovigilance",
        ["Extract case data", "Create safety cases"],
        [DataPermission.READ_SAFETY_REPORTS.value, ActionPermission.CREATE_SAFETY_CASE.value],
        restricted=[RestrictedAction.FINALIZE_CASE.value],
        human_approval=[RestrictedAction.FINALIZE_CASE.value],
        data_classes=[DataClassification.SENSITIVE],
        max_risk=RiskLevel.HIGH,
        computer_perms=_CU_STANDARD,
    ),
    _agent(
        "pv-medical-coding",
        "Medical Coding Agent",
        "pv",
        "Suggest standardized medical codes for safety cases.",
        "pharmacovigilance",
        ["Suggest medical codes", "Classify drug/events"],
        [
            DataPermission.READ_PV_DATA.value,
            DataPermission.READ_CODING_DICTIONARIES.value,
            ActionPermission.CREATE_CODING_RECOMMENDATION.value,
        ],
        human_approval=["FINALIZE_CODING"],
        data_classes=[DataClassification.SENSITIVE],
    ),
    _agent(
        "pv-signal-detection",
        "Safety Signal Detection Agent",
        "pv",
        "Analyze safety datasets; detect unusual patterns.",
        "pharmacovigilance",
        ["Detect safety signals", "Analyze patterns"],
        [
            DataPermission.READ_PV_DATA.value,
            ToolPermission.RUN_ML_MODEL.value,
            ToolPermission.RUN_STATISTICAL_MODEL.value,
            ActionPermission.CREATE_SAFETY_ALERT.value,
        ],
        data_classes=[DataClassification.SENSITIVE, DataClassification.RESTRICTED],
        max_risk=RiskLevel.HIGH,
    ),
    _agent(
        "pv-literature-surveillance",
        "Literature Surveillance Agent",
        "pv",
        "Continuously search literature for safety-related publications.",
        "pharmacovigilance",
        ["Monitor literature", "Create safety findings"],
        [
            DataPermission.READ_LITERATURE.value,
            ToolPermission.SEARCH_LITERATURE.value,
            ActionPermission.CREATE_SAFETY_FINDING.value,
        ],
        data_classes=[DataClassification.PUBLIC, DataClassification.INTERNAL],
    ),
    _agent(
        "pv-case-narrative",
        "Case Narrative Agent",
        "pv",
        "Generate draft case narratives from structured safety data.",
        "pharmacovigilance",
        ["Generate narratives", "Summarize case data"],
        [DataPermission.READ_PV_DATA.value, ActionPermission.CREATE_DRAFT.value],
        restricted=[
            RestrictedAction.FINALIZE_CASE.value,
            RestrictedAction.SUBMIT_TO_REGULATOR.value,
        ],
        human_approval=[RestrictedAction.FINALIZE_CASE.value],
        data_classes=[DataClassification.SENSITIVE],
    ),
    _agent(
        "pv-risk-assessment",
        "Risk Assessment Agent",
        "pv",
        "Analyze safety signals; prepare risk-assessment recommendations.",
        "pharmacovigilance",
        ["Analyze signals", "Prepare risk recommendations"],
        [
            DataPermission.READ_PV_DATA.value,
            DataPermission.READ_CLINICAL_DATA.value,
            ToolPermission.RUN_ANALYTICS.value,
            ActionPermission.CREATE_RECOMMENDATION.value,
        ],
        data_classes=[DataClassification.SENSITIVE, DataClassification.RESTRICTED],
        max_risk=RiskLevel.HIGH,
    ),
    _agent(
        "pv-safety-report",
        "Safety Report Agent",
        "pv",
        "Generate draft periodic safety reports.",
        "pharmacovigilance",
        ["Generate safety reports", "Prepare supporting analysis"],
        [
            DataPermission.READ_PV_DATA.value,
            DataPermission.READ_CLINICAL_DATA.value,
            ActionPermission.CREATE_DRAFT.value,
            ActionPermission.CREATE_REPORT.value,
        ],
        restricted=[RestrictedAction.SUBMIT_TO_REGULATOR.value],
        human_approval=[RestrictedAction.SUBMIT_TO_REGULATOR.value],
        data_classes=[DataClassification.SENSITIVE, DataClassification.CRITICAL],
        max_risk=RiskLevel.CRITICAL,
    ),
]

# ---------------------------------------------------------------------------
# Manufacturing (10)
# ---------------------------------------------------------------------------
_MANUFACTURING_PERMS = [
    DataPermission.READ_ERP.value,
    DataPermission.READ_MES.value,
    DataPermission.READ_LIMS.value,
    DataPermission.READ_SCADA.value,
    DataPermission.READ_INVENTORY.value,
    DataPermission.READ_SUPPLIER_DATA.value,
    DataPermission.READ_MANUFACTURING_DATA.value,
    ToolPermission.ACCESS_ERP.value,
    ToolPermission.ACCESS_MES.value,
    ToolPermission.ACCESS_LIMS.value,
    ToolPermission.RUN_ANALYTICS.value,
    ActionPermission.CREATE_ALERT.value,
    ActionPermission.CREATE_RECOMMENDATION.value,
]
_MANUFACTURING_RESTRICTED = [
    RestrictedAction.RELEASE_BATCH.value,
    RestrictedAction.CHANGE_PRODUCTION_PROCESS.value,
]
_MANUFACTURING_APPROVAL = [
    RestrictedAction.RELEASE_BATCH.value,
    RestrictedAction.CHANGE_PRODUCTION_PROCESS.value,
]

MANUFACTURING_AGENTS: list[AgentRegistryEntry] = [
    _agent(
        f"mfg-{slug}",
        name,
        "manufacturing",
        desc,
        "manufacturing",
        caps,
        _MANUFACTURING_PERMS,
        restricted=_MANUFACTURING_RESTRICTED,
        human_approval=_MANUFACTURING_APPROVAL,
        data_classes=[DataClassification.CONFIDENTIAL, DataClassification.CRITICAL],
        max_risk=RiskLevel.HIGH,
    )
    for slug, name, desc, caps in [
        (
            "planning",
            "Manufacturing Planning Agent",
            "Plan production schedules and capacity.",
            ["Plan production", "Optimize capacity"],
        ),
        (
            "scheduling",
            "Production Scheduling Agent",
            "Create proposed production schedules.",
            ["Schedule production", "Optimize timelines"],
        ),
        (
            "process-monitoring",
            "Process Monitoring Agent",
            "Monitor manufacturing processes in real time.",
            ["Monitor processes", "Detect anomalies"],
        ),
        (
            "quality-control",
            "Quality Control Agent",
            "Analyze QC data and flag deviations.",
            ["Analyze QC data", "Flag deviations"],
        ),
        (
            "deviation-detection",
            "Deviation Detection Agent",
            "Detect manufacturing deviations.",
            ["Detect deviations", "Create alerts"],
        ),
        (
            "predictive-maintenance",
            "Predictive Maintenance Agent",
            "Recommend maintenance actions.",
            ["Predict failures", "Recommend maintenance"],
        ),
        (
            "batch-release",
            "Batch Release Agent",
            "Prepare batch release recommendations.",
            ["Prepare release recommendations"],
        ),
        (
            "yield-optimization",
            "Yield Optimization Agent",
            "Identify yield improvement opportunities.",
            ["Optimize yield", "Analyze batch data"],
        ),
        (
            "supply-chain",
            "Supply Chain Agent",
            "Monitor and optimize supply chain.",
            ["Monitor supply chain", "Identify risks"],
        ),
        (
            "inventory-optimization",
            "Inventory Optimization Agent",
            "Optimize inventory levels.",
            ["Optimize inventory", "Forecast demand"],
        ),
    ]
]

# ---------------------------------------------------------------------------
# Quality / QA (7)
# ---------------------------------------------------------------------------
_QA_PERMS = [
    DataPermission.READ_QMS_DATA.value,
    ToolPermission.ACCESS_QMS.value,
    ToolPermission.RUN_ANALYTICS.value,
    ActionPermission.CREATE_DRAFT.value,
    ActionPermission.CREATE_RECOMMENDATION.value,
    ActionPermission.CREATE_ALERT.value,
]
_QA_RESTRICTED = [
    RestrictedAction.APPROVE_CAPA.value,
    RestrictedAction.APPROVE_DEVIATION.value,
    RestrictedAction.PUBLISH_SOP.value,
    RestrictedAction.CLOSE_QUALITY_EVENT.value,
    RestrictedAction.OVERRIDE_QUALITY_CONTROL.value,
]

QUALITY_AGENTS: list[AgentRegistryEntry] = [
    _agent(
        f"qa-{slug}",
        name,
        "quality",
        desc,
        "quality_assurance",
        caps,
        _QA_PERMS,
        restricted=_QA_RESTRICTED,
        data_classes=[DataClassification.CONFIDENTIAL, DataClassification.CRITICAL],
    )
    for slug, name, desc, caps in [
        (
            "sop-management",
            "SOP Management Agent",
            "Analyze and draft SOP documents.",
            ["Analyze SOPs", "Draft updates"],
        ),
        (
            "deviation-management",
            "Deviation Management Agent",
            "Analyze deviations; recommend actions.",
            ["Analyze deviations", "Recommend actions"],
        ),
        (
            "capa",
            "CAPA Agent",
            "Analyze CAPA records; generate recommendations.",
            ["Analyze CAPA", "Generate recommendations"],
        ),
        (
            "change-control",
            "Change Control Agent",
            "Analyze change requests.",
            ["Analyze changes", "Detect impacts"],
        ),
        (
            "audit-preparation",
            "Audit Preparation Agent",
            "Prepare audit findings and checklists.",
            ["Prepare audits", "Generate findings"],
        ),
        (
            "document-review",
            "Document Review Agent",
            "Review controlled documents.",
            ["Review documents", "Detect inconsistencies"],
        ),
        (
            "gxp-compliance",
            "GxP Compliance Agent",
            "Monitor GxP compliance posture.",
            ["Monitor compliance", "Generate reports"],
        ),
    ]
]

# ---------------------------------------------------------------------------
# Regulatory (7)
# ---------------------------------------------------------------------------
_REG_PERMS = [
    DataPermission.READ_REGULATORY_DATA.value,
    DataPermission.READ_LITERATURE.value,
    DataPermission.READ_INTERNAL_DOCUMENTS.value,
    ToolPermission.SEARCH_LITERATURE.value,
    ActionPermission.CREATE_DRAFT.value,
    ActionPermission.CREATE_REPORT.value,
    ActionPermission.CREATE_RECOMMENDATION.value,
]
_REG_RESTRICTED = [
    RestrictedAction.SUBMIT_TO_REGULATOR.value,
    RestrictedAction.LABEL_APPROVAL.value,
    RestrictedAction.PUBLISH.value,
]
_REG_APPROVAL = [RestrictedAction.SUBMIT_TO_REGULATOR.value, RestrictedAction.LABEL_APPROVAL.value]

REGULATORY_AGENTS: list[AgentRegistryEntry] = [
    _agent(
        f"reg-{slug}",
        name,
        "regulatory",
        desc,
        "regulatory",
        caps,
        _REG_PERMS,
        restricted=_REG_RESTRICTED,
        human_approval=_REG_APPROVAL,
        data_classes=[DataClassification.CONFIDENTIAL, DataClassification.CRITICAL],
        max_risk=RiskLevel.HIGH,
    )
    for slug, name, desc, caps in [
        (
            "intelligence",
            "Regulatory Intelligence Agent",
            "Monitor regulatory information.",
            ["Monitor regulations", "Generate intelligence reports"],
        ),
        (
            "submission-prep",
            "Submission Preparation Agent",
            "Prepare submission drafts.",
            ["Prepare submissions", "Identify gaps"],
        ),
        (
            "document",
            "Regulatory Document Agent",
            "Generate regulatory document drafts.",
            ["Generate documents", "Compare versions"],
        ),
        (
            "labeling",
            "Labeling Agent",
            "Compare and draft label content.",
            ["Compare labels", "Draft label updates"],
        ),
        (
            "correspondence",
            "Health Authority Correspondence Agent",
            "Prepare draft health-authority responses.",
            ["Draft responses", "Analyze correspondence"],
        ),
        (
            "change",
            "Regulatory Change Agent",
            "Analyze regulatory change impacts.",
            ["Analyze changes", "Recommend actions"],
        ),
        (
            "gap",
            "Submission Gap Agent",
            "Identify submission gaps.",
            ["Identify gaps", "Recommend remediation"],
        ),
    ]
]

# ---------------------------------------------------------------------------
# Medical Information (3)
# ---------------------------------------------------------------------------
MEDICAL_INFO_AGENTS: list[AgentRegistryEntry] = [
    _agent(
        "med-info",
        "Medical Information Agent",
        "medical_info",
        "Answer medical information requests from approved sources.",
        "medical_information",
        ["Answer MI requests", "Cite sources", "Track provenance"],
        [
            DataPermission.READ_LITERATURE.value,
            DataPermission.READ_INTERNAL_DOCUMENTS.value,
            ActionPermission.CREATE_DRAFT.value,
        ],
        restricted=[
            RestrictedAction.SEND_EXTERNAL_COMMUNICATION.value,
            RestrictedAction.MAKE_MEDICAL_DECISION.value,
        ],
        human_approval=[RestrictedAction.SEND_EXTERNAL_COMMUNICATION.value],
        data_classes=[DataClassification.PUBLIC, DataClassification.INTERNAL],
    ),
    _agent(
        "med-literature",
        "Medical Literature Agent",
        "medical_info",
        "Search and summarize medical literature with citations.",
        "medical_information",
        ["Search literature", "Summarize with citations"],
        _READ_ONLY_LITERATURE,
        data_classes=[DataClassification.PUBLIC, DataClassification.INTERNAL],
        max_risk=RiskLevel.LOW,
    ),
    _agent(
        "med-response",
        "Medical Response Agent",
        "medical_info",
        "Draft medical responses from approved information.",
        "medical_information",
        ["Draft responses", "Escalate uncertain requests"],
        [DataPermission.READ_INTERNAL_DOCUMENTS.value, ActionPermission.CREATE_DRAFT.value],
        restricted=[RestrictedAction.SEND_EXTERNAL_COMMUNICATION.value],
        human_approval=[RestrictedAction.SEND_EXTERNAL_COMMUNICATION.value],
        data_classes=[DataClassification.INTERNAL, DataClassification.CONFIDENTIAL],
    ),
]

# ---------------------------------------------------------------------------
# Commercial (6)
# ---------------------------------------------------------------------------
COMMERCIAL_AGENTS: list[AgentRegistryEntry] = [
    _agent(
        f"comm-{slug}",
        name,
        "commercial",
        desc,
        "commercial",
        caps,
        [
            DataPermission.READ_CRM_DATA.value,
            ToolPermission.RUN_ANALYTICS.value,
            ActionPermission.CREATE_RECOMMENDATION.value,
            ActionPermission.CREATE_REPORT.value,
        ],
        restricted=[RestrictedAction.SEND_EXTERNAL_COMMUNICATION.value],
        human_approval=[RestrictedAction.SEND_EXTERNAL_COMMUNICATION.value],
        data_classes=[DataClassification.INTERNAL, DataClassification.CONFIDENTIAL],
    )
    for slug, name, desc, caps in [
        (
            "market-intelligence",
            "Market Intelligence Agent",
            "Analyze market trends.",
            ["Analyze markets", "Identify trends"],
        ),
        (
            "sales-intelligence",
            "Sales Intelligence Agent",
            "Analyze sales performance.",
            ["Analyze sales", "Identify opportunities"],
        ),
        (
            "demand-forecast",
            "Demand Forecasting Agent",
            "Generate demand forecasts.",
            ["Forecast demand", "Analyze trends"],
        ),
        (
            "market-access",
            "Market Access Agent",
            "Analyze market access factors.",
            ["Analyze access", "Generate recommendations"],
        ),
        (
            "pricing",
            "Pricing Agent",
            "Analyze pricing scenarios.",
            ["Analyze pricing", "Generate scenarios"],
        ),
        (
            "hcp-support",
            "HCP Support Agent",
            "Support HCP engagement workflows.",
            ["Support HCP workflows", "Generate materials"],
        ),
    ]
]

# ---------------------------------------------------------------------------
# Patient Support (5)
# ---------------------------------------------------------------------------
_PATIENT_RESTRICTED = [
    RestrictedAction.DIAGNOSE.value,
    RestrictedAction.PRESCRIBE.value,
    RestrictedAction.CHANGE_TREATMENT.value,
    RestrictedAction.MAKE_MEDICAL_DECISION.value,
    RestrictedAction.SEND_EXTERNAL_COMMUNICATION.value,
]

PATIENT_SUPPORT_AGENTS: list[AgentRegistryEntry] = [
    _agent(
        f"patient-{slug}",
        name,
        "patient_support",
        desc,
        "patient_support",
        caps,
        [DataPermission.READ_INTERNAL_DOCUMENTS.value, ActionPermission.CREATE_DRAFT.value],
        restricted=_PATIENT_RESTRICTED,
        data_classes=[DataClassification.PUBLIC, DataClassification.INTERNAL],
        max_risk=RiskLevel.LOW,
    )
    for slug, name, desc, caps in [
        (
            "education",
            "Patient Education Agent",
            "Provide approved educational information.",
            ["Provide education", "Cite approved sources"],
        ),
        (
            "adherence",
            "Medication Adherence Agent",
            "Send approved adherence reminders.",
            ["Send reminders", "Track adherence workflows"],
        ),
        (
            "onboarding",
            "Patient Onboarding Agent",
            "Assist with onboarding workflows.",
            ["Assist onboarding", "Provide approved materials"],
        ),
        (
            "trial-assistant",
            "Clinical Trial Assistant",
            "Answer approved trial questions.",
            ["Answer trial questions", "Assist with admin workflows"],
        ),
        (
            "support",
            "Patient Support Agent",
            "Provide approved support information.",
            ["Provide support", "Escalate medical questions"],
        ),
    ]
]

ALL_PHARMA_AGENTS: list[AgentRegistryEntry] = (
    DRUG_DISCOVERY_AGENTS
    + CLINICAL_TRIAL_AGENTS
    + PHARMACOVIGILANCE_AGENTS
    + MANUFACTURING_AGENTS
    + QUALITY_AGENTS
    + REGULATORY_AGENTS
    + MEDICAL_INFO_AGENTS
    + COMMERCIAL_AGENTS
    + PATIENT_SUPPORT_AGENTS
    + [
        _agent(
            "computer-assistant",
            "Computer Use Assistant",
            "automation",
            "Governed desktop automation for approved pharma workflows.",
            "automation",
            ["Screen interaction", "Browser navigation", "File operations"],
            list(_CU_EXTENDED),
            computer_perms=list(_CU_EXTENDED),
            max_risk=RiskLevel.HIGH,
        ),
    ]
)
