# Security 

## Authentication

- Every request to `/guardrail/evaluate` requires a `Bearer` JWT, verified
  with a pinned HS256 algorithm and a shared secret (`AUTH_JWT_SECRET`); the
  algorithm is never read from the token itself (mitigates alg-confusion
  attacks). `exp` is required and checked; expired, malformed, or
  bad-signature tokens are rejected.
- The role fed to the policy engine is the **verified** claim from the token
  — never a client-supplied request field.
- Every auth failure mode (missing header, bad signature, wrong algorithm,
  expired, missing/invalid role) collapses to one generic `401
  Unauthorized`; the specific reason is logged server-side only.
- With `AUTH_DEV_MODE` off (the default), the app refuses to start if
  `AUTH_JWT_SECRET` is unset or empty, rather than starting in a state where
  tokens cannot be verified. `AUTH_DEV_MODE=true` additionally exposes `POST
  /auth/dev-token` to mint test tokens locally; that endpoint 404s otherwise.
- This is a shared-secret interim mechanism, not a full SSO/OIDC
  integration — see `decisions.md` for what remains open there.

## Secret handling

- API keys are read from environment variables (`GROQ_API_KEY`).
- `.env` holds real values locally and is gitignored; `.env.example` contains
  placeholders only.
- No secrets belong in source; treat any leaked key as compromised and rotate it.

## Sensitive data considerations

- The audit log stores the raw prompt, which may itself contain PII/PHI. It is
  a protected data asset; the SQLite file has no access control.
- The evaluate endpoint returns the decision and risk assessment; the prompt is
  retained in the audit record, not echoed to the caller.
- For policy-ALLOWed requests only, the prompt is sent to the configured
  generative LLM provider (currently Groq). BLOCKed and REVIEW-flagged requests
  never reach it. Provider choice and data-handling terms remain open
  decisions.

## Fail-closed behavior

- Classifier failure → `CRITICAL` → BLOCK (never ALLOW-by-default).
- Policy evaluation error → BLOCK.
- No matching policy rule → BLOCK.
- The policy engine is deterministic and performs no LLM call.
- LLM generation failure on an ALLOWed request → generic HTTP 503; the failure
  is logged server-side and recorded in the audit event (`attempted`,
  `succeeded`, error kind). It is never converted into a successful response,
  and raw provider errors are not exposed.
- Output guardrail flagged, or the check itself fails/times out/errors → the
  generated response is **not** returned; the request is routed to
  flagged-for-review instead. A broken output guardrail can only make the
  system stricter, never let an unchecked response through.

## Policy enforcement

- Final authority sits in `services/policy_engine`; nothing upstream
  short-circuits it. The classifier output carries no action/decision field, so
  a compromised classifier can only influence, never decide.

## Audit logging

- Every request is logged regardless of outcome, including whether generative
  LLM processing was attempted and whether it succeeded (no generated text or
  provider detail is stored — only the attempt/success signal).
- The audit DB is local SQLite (`audit.db`); no retention policy, no access
  control, no backup strategy. Treat it as untrusted for production.

## API error handling

- Unhandled exceptions return a generic `500` with
  `{"detail": "Internal server error."}` — no stack trace or provider detail;
  internals go to server logs only.
- The classifier fail-closed reasoning string is intentionally generic so raw
  provider errors and secrets do not leak into responses or the audit log.

## Target security posture (from the proposal — planned/open)

Security concepts the project aims for that do not exist yet:

| Concept | Status |
|---|---|
| Claim/evidence verification against approved sources; RAG/retrieved-content protection | Planned — approach open |
| Audit governance: role-based access control, retention policy, protected-asset handling | Planned — storage decision open |
| Transparency & appeal path (employees can contest decisions) | Planned |
| AI-agent tool/action controls | Planned |
| Full SSO/OIDC identity integration (current auth is a shared-secret HS256 interim mechanism) | Planned — open decision |
| Guardrail self-protection (classifier manipulation flagged as a signal) | Implemented (signals + BLOCK rules) |
| Output guardrail (inspect generated responses before they reach users) | Implemented — prompt-grounded only (see above); approved-source grounding still planned |

## Current limitations

- Authentication verifies a role claim cryptographically (HS256 JWT), but is
  a shared-secret interim mechanism, not full SSO/OIDC; there is no
  fine-grained permission model beyond the role string itself.
- Free-text input is evaluated by the classifier; safety depends on the model
  (or the mock rules) producing an accurate `RiskAssessment`.
- The output guardrail checks generated responses against the prompt only —
  there is no approved-source or RAG store yet, so it catches ungrounded
  claims relative to the prompt, not factual errors in general.
- No human-review workflow exists yet: REVIEW and flagged-for-review
  responses only signal that review is required.
- No rate limiting, no deployment hardening, no app-level TLS termination.
- No audit access control, retention, or rotation.
- Not GxP / 21 CFR Part 11 compliant; not production-ready.