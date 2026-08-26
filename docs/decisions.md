# Decisions (internal)

Lightweight ADR-style record. `DECIDED` = reflected in this repository today.
`OPEN` = genuinely unresolved; nothing here picks an option for the team.

## Decided

### 1. Classifier returns structured metadata only

- Status: DECIDED
- Context: an LLM/reasoning output must not be able to authorize anything.
- Decision: `RiskAssessment` has no action/decision field; the policy engine is
  the only producer of `PolicyDecision`.
- Reason: keeps final authority deterministic and auditable.
- Consequences: every classifier must return the same `RiskAssessment` contract.

### 2. Deterministic, configuration-driven policy engine

- Status: DECIDED
- Context: policy semantics must be reproducible and reviewable.
- Decision: rules live in `policies/policy.yaml`; no rule logic in Python;
  first match wins; validated at load.
- Reason: versioned config-as-code; invalid policies fail at startup.
- Consequences: adding rules means editing YAML; ordering matters.

### 3. Fail closed by default

- Status: DECIDED
- Context: missing or invalid classification must not let requests through.
- Decision: any classifier/policy failure resolves to BLOCK (the CRITICAL risk
  profile has no ALLOW rule; no-match → BLOCK; evaluation error → BLOCK).
- Reason: in a guardrail, a silent allow is worse than a false block.
- Consequences: new failure paths must route to the most conservative action;
  this behavior is covered by the TC-09 scenario tests.

### 4. Structured LLM outputs only

- Status: DECIDED
- Context: free-form model prose must never drive decisions.
- Decision: the LLM classifier uses Groq Structured Outputs (strict JSON
  schema) validated against the domain contract.
- Reason: machine-verifiable contract; no regex parsing of prose.
- Consequences: output is parsed and validated to `RiskAssessment` before the
  policy engine sees it.

### 5. Every decision is audited

- Status: DECIDED
- Context: traceability is a core requirement.
- Decision: every request that produces a `PolicyDecision` is logged (SQLite)
  regardless of outcome.
- Reason: inspection-readiness, consistent with data-integrity expectations.
- Consequences: audit storage/retention/access remain open (see below).

### 6. Classifier is swappable behind one interface

- Status: DECIDED
- Context: the classifier must be replaceable without touching the pipeline.
- Decision: `RiskClassifier` interface plus a `get_classifier()` factory driven
  by `LLM_PROVIDER`; the default is the offline `KeywordMockClassifier`.
- Reason: tests and CI make no network calls; providers stay isolated.
- Consequences: provider SDKs remain confined to the classifier module.

### 7. Current LLM-backed classifier: Groq with structured outputs

- Status: DECIDED (current implementation) — the final provider is open (below).
- Context: a real-model classifier was needed behind the interface.
- Decision: implement `GroqRiskClassifier` using the Groq SDK, default model
  `openai/gpt-oss-20b`, strict structured outputs, 10s timeout.
- Reason: strict-schema support on Groq supports the fail-closed guarantee;
  model, key, and timeout are environment-configurable.
- Consequences: this is the prototype's LLM integration until a production
  provider decision is made.

### 8. Sensitivity precedence: highest wins

- Status: DECIDED
- Context: multiple risk categories can match a single request.
- Decision: the most sensitive classification among matched categories wins
  (PHI > PII > default); never downgraded.
- Reason: prevents accidental de-escalation of patient-identifiable data.
- Consequences: any new risk category must specify its sensitivity mapping.

### 9. Injection and disguise are separate signals

- Status: DECIDED
- Context: an injection attempt and a disguise attempt are related but distinct.
- Decision: `injection_detected` and `disguise_detected` are separate boolean
  fields, each matched by its own policy rule.
- Reason: either signal alone must be enough to BLOCK; separate rules keep the
  policy explicit.
- Consequences: classifiers and policies must handle both fields.

### 10. Generative LLM runs only after policy permits generation

- Status: DECIDED (amended by decisions 12–13)
- Context: the generative model must never see blocked or held requests, and
  must never influence whether a request is allowed.
- Decision: the API calls the LLM gateway only when `PolicyEngine` returns
  ALLOW, or REWRITE after successful sanitization. BLOCK and REVIEW return
  structured stop responses without any model call; LLM failures on permitted
  requests produce a safe error, never a fabricated success.
- Reason: keeps the deterministic policy engine fully authoritative over what
  reaches an LLM (input guardrail before the call).
- Consequences: any new pipeline stage that touches an LLM must sit behind the
  same policy gate; covered by dedicated flow tests.

### 11. Generation provider is configured independently behind a small gateway

- Status: DECIDED
- Context: risk classification and response generation are different concerns
  that may use different providers or settings.
- Decision: a small `LLMGateway` interface plus factory driven by
  `LLM_GENERATION_PROVIDER` (unset = no generation); `GroqLLMGateway` is the
  implemented provider and returns generated text only. The classifier keeps
  its own `LLM_PROVIDER` setting.
- Reason: decouples classification from generation configuration; keeps the
  provider SDK out of the app and policy layers.
- Consequences: the offline default produces ALLOW responses with a null
  generated-text field; the synchronous Groq client inside the async method is
  acceptable for now, with an async client deferred until needed.

### 12. Optical REWRITE sanitizes before generation (image path only)

- Status: SUPERSEDED by decision 13
- Context: P0 optical intake supported REWRITE as sanitization of OCR text
  before generation; text REWRITE remained a terminal stop.
- Decision: superseded — both text and image REWRITE now use unified
  sanitization (decision 13).

### 13. Unified sanitization for REWRITE (text and image)

- Status: DECIDED
- Context: REWRITE must mean "transform the request into a policy-compliant
  representation before LLM generation" for both text and image/OCR inputs.
  The LLM must never receive the original sensitive context after REWRITE.
- Decision: a provider-independent `SanitizationEngine` in
  `services/sanitization/` produces sanitized text from either source. On
  policy REWRITE (text or image), the API sanitizes first, then may call the
  LLM with only the sanitized prompt. Sanitization failure fails closed to
  REVIEW — never falls back to the original content, and never silently
  upgrades REWRITE to ALLOW. ALLOW does not invoke the sanitizer. BLOCK and
  REVIEW still never reach the LLM. PolicyEngine remains the sole authority.
- Reason: one safe-context plane for both intake paths; preserves fail-closed
  security invariants.
- Consequences: FakeGateway tests assert original identifiers are absent from
  the LLM prompt after REWRITE; sanitizer exception tests assert REVIEW and
  zero LLM calls.

## Open decisions

### Guardrail framework

- Status: OPEN
- Question: adopt NeMo Guardrails or another guardrail framework, or keep the
  custom pipeline?
- Options under consideration: current custom pipeline; NeMo Guardrails.
- What needs to be evaluated: fit with the deterministic policy engine,
  structured outputs, and team effort.

### Final LLM / provider choice

- Status: OPEN
- Question: which provider/model for production classification?
- Options under consideration: Groq (current prototype); others.
- What needs to be evaluated: strict-schema support, cost/latency, data-handling
  terms, hosting.

### Production inference hosting

- Status: OPEN
- Question: where does inference run in production?
- Options under consideration: managed API; self-hosted.
- What needs to be evaluated: data residency, operational cost, reliability.

### Identity / role source

- Status: OPEN
- Question: where does `user_role` come from in a real deployment?
- Options under consideration: SSO/IdP; directory service; API token claims.
- What needs to be evaluated: integrity of the role field (currently a
  client-supplied string).

### Claim / evidence verification

- Status: OPEN
- Question: how (if at all) are generated claims verified against approved
  sources? Part of the planned output-guardrail stage.
- Options under consideration: lightweight flagging of unverified claims routed
  for review; retrieval-based matching against an approved reference source;
  RAG-based protection of retrieved content.
- What needs to be evaluated: scope, approved source data, effort, false-flag
  rates.

### Output guardrail scope

- Status: OPEN
- Question: which checks run on generated responses before they reach users
  (policy re-check, sensitive-data screening, claim flagging)?
- Options under consideration: minimal policy re-check; full output guardrail
  stage as described in the proposal.
- What needs to be evaluated: latency cost, overlap with input checks, failure
  handling (fail-closed vs flag-for-review).

### RAG / retrieved-content protection

- Status: OPEN
- Question: is a retrieval stack (approved-source store + retrieval) in scope,
  and how is retrieved content itself governed?
- Options under consideration: none (deferred); approved-source store feeding
  claim verification.
- What needs to be evaluated: source data ownership, freshness, infrastructure
  cost.

### Human review workflow

- Status: OPEN
- Question: what happens after a REVIEW/FLAG decision — who reviews, with what
  tooling, and what SLAs apply?
- Options under consideration: none yet (responses only signal review
  requirement); lightweight internal queue; full dashboard.
- What needs to be evaluated: reviewer roles, volume expectations, appeal-path
  integration.

### Conversation context store & risk-trajectory tracking

- Status: OPEN
- Question: how is conversation history and cumulative session risk stored and
  fed into classification?
- Options under consideration: none (single-turn only today); in-process
  store; external session store.
- What needs to be evaluated: privacy of retained history, storage choice,
  trajectory-scoring approach.

### Extended detection capabilities

- Status: OPEN (partially addressed by P0 optical intake)
- Question: when do multi-modal intake, behavioural drift detection, and the
  policy-learning loop get built?
- Options under consideration: optical OCR intake is implemented (P0); facial
  recognition, medical image interpretation, and policy learning remain later.
- What needs to be evaluated: value vs effort for each, data requirements,
  false-positive impact.

### Tool/action controls for AI agents

- Status: OPEN
- Question: should the guardrail also govern tool/data access requested by AI
  agents (not just prompts)?
- Options under consideration: out of scope for now; extend the policy engine
  to agent actions later.
- What needs to be evaluated: agent integration patterns, risk model for
  actions, policy-rule expressiveness.

### Data classification model

- Status: OPEN
- Question: should data sensitivity come from the classifier, from an external
  data-classification system (e.g. DLP), or both?
- Options under consideration: classifier-only (current); external DLP; hybrid.
- What needs to be evaluated: accuracy, integration effort, false-block rates.

### Audit storage / retention

- Status: OPEN
- Question: what replaces local SQLite for audit storage, and what retention and
  access policy applies?
- Options under consideration: managed Postgres; access-controlled storage.
- What needs to be evaluated: compliance requirements, backup/retention, access
  control.