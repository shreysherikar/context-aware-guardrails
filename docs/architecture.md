# Architecture

> Status: reflects the current hackathon prototype. **Not production-ready.**
> This document has two parts: the **current implementation** (source of truth:
> the code in this repository) and the **target architecture** (source: the
> project proposal, `Context_Aware_AI_Guardrail_Proposal.md`). Target items are
> always labelled Planned/Open and are never claimed to exist.

## Project objective

A context-aware guardrail layer between employees and internal AI tools in a
pharmaceutical setting. Every request is inspected for risk — content, data
sensitivity, and attempted manipulation — governed by deterministic,
version-controlled policy rules, and answered with the minimum necessary
friction rather than a blanket block. Every decision is auditable.

Two principles govern the whole design:

1. **Context-aware and risk-proportionate.** Identical text can carry different
   risk depending on who asks, what was asked before, and what data is
   involved. Responses are graduated — ALLOW / REWRITE / CLARIFY / REVIEW /
   BLOCK — instead of a binary allow/block.
2. **Classification is probabilistic; authorization is not.** Models reason and
   classify; only the deterministic policy engine decides, and it fails closed
   on any error.

## Current implementation

### Request flow

    POST /guardrail/evaluate
          │
          ▼
    GuardrailRequest (prompt, user_role, conversation_id, requested_action?)
          │
          ▼
    RiskClassifier.classify()          ← reasoning plane (probabilistic, swappable)
          │
          ▼
    RiskAssessment                     ← structured metadata, no decision field
          │
          ▼
    PolicyEngine.evaluate(risk, role)  ← policy plane (deterministic, YAML rules)
          │
          ├── BLOCK / REVIEW / other ──► structured stop response (no LLM call)
          │
          └── ALLOW ──► LLMGateway.generate() ──► OutputGuardrail.check() ──► response or flagged-for-review
                                 │
                                 ▼
    AuditEvent → services/audit/log_event()    ← always, regardless of outcome

Only a policy ALLOW can reach the LLM gateway. The gateway is never consulted
for BLOCK/REVIEW and never influences the decision. Every request also passes
through `get_verified_role` (HS256 JWT bearer-token verification) before any
of the above runs; the role fed to the policy engine is the verified claim,
never a request field.

## Major components

| Component | Responsibility | Location |
|---|---|---|
| HTTP API | Wire-up only: verifies the bearer token, runs classify → policy → (ALLOW-only) generation → output guardrail → audit. No business logic. | `apps/api/main.py` |
| Auth | Verifies the HS256 JWT bearer token and returns the verified role claim. | `services/auth/` |
| Risk classifier | Turns a `GuardrailRequest` into a `RiskAssessment`. | `services/risk_engine/` |
| Policy engine | Turns a `RiskAssessment` + role into a `PolicyDecision` from `policies/policy.yaml`. Deterministic, fail-closed. | `services/policy_engine/` |
| LLM gateway | Generates the response for ALLOWed requests, behind a small interface. | `services/llm/` |
| Output guardrail | Inspects the generated response against the prompt before it reaches the employee; fail-closed. | `services/output_guardrail/` |
| Audit log | Persists every `AuditEvent` — including the LLM and output-guardrail outcomes — to SQLite. | `services/audit/` |
| Domain models | Shared contracts, no framework dependencies. | `domain/` |

### Risk classification (implemented)

Two implementations behind one interface (`services/risk_engine/classifier.py`):

- `KeywordMockClassifier` — deterministic regex classifier; the default when
  `LLM_PROVIDER` is unset or `mock`. Zero network calls.
- `GroqRiskClassifier` — optional real-model classifier, selected with
  `LLM_PROVIDER=groq`. Uses Groq chat completions with Structured Outputs
  (`response_format: {type: json_schema, strict: true}`) so the model must
  emit JSON matching the `RiskAssessment` schema.

A factory (`services/risk_engine/factory.py`) picks the implementation from
`LLM_PROVIDER`; unknown values fail fast at startup.

Fail-closed behavior (implemented): any classifier failure (timeout, rate
limit, API error, malformed or schema-invalid output) is converted into
`RiskAssessment(risk_level=CRITICAL, ...)`, which the policy engine routes to
BLOCK. A broken classifier can only make the guardrail stricter.

Sensitivity precedence (implemented): when several risk categories are
detected, the highest sensitivity wins (PHI > PII > default); a more sensitive
classification is never downgraded.

Injection vs disguise (implemented): `injection_detected` and
`disguise_detected` are separate signals, each matched by its own policy rule.

### Policy engine (implemented)

- Rules are loaded from `policies/policy.yaml` and validated at load time
  (`services/policy_engine/policy_models.py`); an invalid policy fails at
  startup, not mid-request.
- Rules are evaluated top to bottom; the first match wins.
- No match → BLOCK (`DEFAULT-FAIL-CLOSED`); evaluation error → BLOCK
  (`ERROR-FAIL-CLOSED`).

Current rules: disguise/injection → BLOCK; PHI → REVIEW; PII → REWRITE;
off-label → CLARIFY; IP → REVIEW; LOW risk → ALLOW.

### Controlled LLM processing (implemented)

- Generation happens strictly after a policy ALLOW, through the `LLMGateway`
  interface (`services/llm/gateway.py`) — the API layer depends on the
  abstraction, not on a provider SDK.
- `GroqLLMGateway` (`services/llm/groq_gateway.py`) is the one implemented
  generation provider; selected with `LLM_GENERATION_PROVIDER=groq`
  (independent of the classifier's `LLM_PROVIDER`). Unset → no generation is
  wired and ALLOW responses carry a null response field.
- Provider failures return a safe application-level error (HTTP 503, generic
  message); raw provider errors go to server logs only, and the attempt
  outcome (`attempted` / `succeeded` / error kind) is recorded in the audit
  event.
- REWRITE and CLARIFY remain reserved policy actions without behaviour.

### Output guardrail (implemented)

- Runs only after generation succeeds on a policy ALLOW, through the
  `OutputGuardrail` interface (`services/output_guardrail/guardrail.py`) —
  the API layer depends on the abstraction, not on a provider SDK.
- `GroqOutputGuardrail` (`services/output_guardrail/groq_guardrail.py`) is the
  one implemented provider, selected with `OUTPUT_GUARDRAIL_PROVIDER=groq`;
  it uses Groq Structured Outputs to check whether claims in the generated
  text are grounded in the original prompt. Unset/empty → the stage is
  skipped entirely and ALLOW responses are returned without post-generation
  inspection.
- Grounding is prompt-only today: there is no approved-source or RAG store to
  check claims against, so "unverified" means "not supported by the prompt
  text," not "factually false" (see Target architecture below).
- Fail-closed by design: if the guardrail flags the response, or the check
  itself fails/times out/errors, the response is **not** returned as a normal
  ALLOW success — it is routed to flagged-for-review instead.

### Authentication (implemented)

- Every request to `/guardrail/evaluate` requires a `Bearer` JWT verified
  with a pinned HS256 algorithm and a shared secret (`AUTH_JWT_SECRET`) —
  see `services/auth/core.py`. Expiry (`exp`) is required; signature,
  algorithm, and expiry failures all raise before the role is read.
- The verified role claim — never a client-supplied request field — is what
  reaches the policy engine.
- Every failure mode collapses to one generic `401 Unauthorized`; the
  specific reason is logged server-side only.
- With `AUTH_DEV_MODE` off (the default), the app refuses to start if
  `AUTH_JWT_SECRET` is unset, rather than silently accepting unverifiable
  tokens. `AUTH_DEV_MODE=true` additionally exposes `POST /auth/dev-token`
  for minting test tokens locally; it 404s otherwise.
- This is a shared-secret interim mechanism, not a full SSO/OIDC
  integration — that remains an open decision (see `decisions.md`).

### Audit logging (implemented)

- Every decision is logged regardless of outcome, including whether LLM
  generation and the output guardrail were attempted and whether each
  succeeded.
- SQLite database (`audit.db` by default, `AUDIT_DB_PATH` to override) storing
  the prompt, verified role, risk assessment, decision, LLM outcome, output
  guardrail outcome, and timestamp.

### Provider configuration (implemented)

- `LLM_PROVIDER` selects the risk classifier (`mock` default, `groq`);
  `LLM_GENERATION_PROVIDER` independently selects the post-ALLOW generative
  gateway (unset default = none). The two are deliberately decoupled.
- Default model for both Groq integrations: `openai/gpt-oss-20b`
  (`GROQ_MODEL`), key from `GROQ_API_KEY`, per-call timeout `GROQ_TIMEOUT`
  (default 10s).
- Provider SDKs are confined to `services/risk_engine/groq_classifier.py` and
  `services/llm/groq_gateway.py`; nothing in `apps/`,
  `services/policy_engine/`, or other services imports a provider SDK.
- The final production providers are open decisions (see `decisions.md`).

## Domain / application / infrastructure separation

| Layer | Contains | Must not depend on |
|---|---|---|
| Domain | `domain/models.py`, `domain/enums.py` | FastAPI, YAML, SQLite, provider SDKs |
| Application | `services/risk_engine`, `services/policy_engine`, `services/llm`, `services/audit` | `apps/`; policy engine has no LLM SDK |
| Interface | `apps/api/` | business logic |
| Infrastructure | SQLite file, Docker | — |

## Target architecture (from the proposal — planned/open)

The proposal describes the complete system this prototype is building toward:
a **reasoning plane** (probabilistic, context-aware) kept architecturally
separate from a **policy plane** (deterministic authority), with the LLM call
bracketed on both sides — an input guardrail before it and a prompt-grounded
**output guardrail** after it (both implemented; the output guardrail checks
grounding against the prompt only — approved-source/RAG grounding, listed
below, is still planned):

    TARGET — not fully implemented:

      REQUEST + CONTEXT (history, role, sensitivity, destination)
          │
          ▼
      REASONING PLANE — context engine, intent/disguise reasoning,
                        risk classification → structured metadata only
          │
          ▼
      POLICY PLANE — versioned rules, fail-closed, final authority
          │
          ├─ ALLOW ────► LLM ──► OUTPUT GUARDRAIL ──► answer or FLAG FOR REVIEW
          ├─ REWRITE ──► safer reformulation of the request
          ├─ CLARIFY ──► clarification request back to the employee
          ├─ REVIEW ───► human/security review
          └─ BLOCK ────► stop
          │
          ▼
      AUDIT & GOVERNANCE (access control, retention, transparency, appeal)

### Capability status

| Capability | Status |
|---|---|
| Input risk/semantic inspection (PII/PHI, off-label, IP, injection/disguise) | **Implemented** (single-turn, text-only) |
| Deterministic policy enforcement (versioned YAML rules, fail-closed) | **Implemented** |
| Controlled LLM processing (generation only after policy ALLOW) | **Implemented** |
| Guardrail self-protection (manipulation attempts flagged as signals) | **Implemented** (classifier signals + BLOCK rules) |
| Risk-proportionate friction (five-way decision) | **Partial** — decision enum and ALLOW/BLOCK/REVIEW behaviour exist; REWRITE/CLARIFY are reserved actions without behaviour |
| Human review | **Partial** — REVIEW action returned with `review_required`; no review workflow or tooling yet |
| Post-ALLOW response generation | **Implemented** (Groq gateway; final provider still open) |
| Output guardrail (checks generated responses before they reach users; fail-closed to flagged-for-review) | **Implemented** — grounding is prompt-only (Groq) |
| Bearer-token authentication (verified role, HS256, fail-closed startup) | **Implemented** — shared-secret interim mechanism, not full SSO/OIDC |
| Claim/evidence verification against approved sources | **Implemented** (text + image, post-generation) — deterministic offline pipeline behind CLAIM_VERIFICATION_PROVIDER (default off): sentence-level claim extraction → lexical retrieval over the version-controlled trusted corpus → support/contradict assessment; the aggregate feeds the deterministic PolicyEngine's `claims_supported` condition (EVIDENCE-001 routes unsupported/contradicted/conflicting/insufficient claims to REVIEW); no LLM involved in verification |
| RAG / retrieved-content protection (matching against approved sources) | **Planned** — approach open |
| Conversation history & risk-trajectory tracking | **Implemented** — deterministic counting/pattern-matching over prior audit events per conversation (MEDIUM+ turns, repeated sensitive category, strictly-defined non-decreasing trend); evidence feeds the `trajectory_escalate` policy condition, never a decision; no LLM involved in scoring |
| Role-aware policy conditions | **Partial** — rule fields exist and the role is now cryptographically verified; fine-grained role/permission model still open |
| Destination-aware policy (internal vs external channels) | **Planned** — not implemented |
| Multi-modal intake (documents/images normalised into the same evaluation path) | **Planned** — not implemented |
| Behavioural drift detection | **Planned** — not implemented |
| AI-agent tool/action controls (governing tool/data access requested by agents) | **Planned** — not implemented |
| Transparency & appeal path for employees | **Planned** — not implemented |
| Audit governance (access control, retention policy) | **Planned** — storage/access decisions open |
| Policy-learning loop (novel patterns → human review → new policy) | **Planned** — not implemented |
| NeMo Guardrails or similar framework | **Open** — no framework selected |
| Production hosting / cloud infrastructure | **Open** — local Docker only |

Nothing in the target section is presented as implemented or decided.
Technology names floated in the proposal (Bedrock, Comprehend/Presidio,
LangGraph, DynamoDB, Streamlit) are candidate options at most — see
`decisions.md` for what remains open.