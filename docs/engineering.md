# Engineering (internal)

Practical guide for working in this repository.

## Repository structure

    apps/api/main.py          FastAPI wiring (health + /guardrail/evaluate)
    domain/                   shared pydantic models and enums (framework-free)
    services/risk_engine/     RiskClassifier contract, mock + Groq classifiers, factory
    services/llm/             LLMGateway contract, Groq generation gateway, factory
    services/policy_engine/   PolicyEngine + policy validation models
    services/audit/           SQLite audit logging
    policies/policy.yaml      versioned policy rules
    tests/unit/               unit tests
    tests/scenarios/          end-to-end scenario tests (API level)
    pyproject.toml            project metadata, dependencies, tool config
    uv.lock                   locked dependency versions
    .env.example              documented environment variables (copy to .env)

## Local setup

Requires Python and `uv` (repo pins 3.12 in `.python-version`; CI uses 3.12).

    uv python install 3.12   # only if needed
    uv sync                  # install deps incl. dev extras, from uv.lock
    cp .env.example .env     # then edit values

## Environment variables

| Variable | Used by | Default | Notes |
|---|---|---|---|
| `LLM_PROVIDER` | risk-classifier factory | `mock` | `mock` or `groq`; unknown fails at startup |
| `LLM_GENERATION_PROVIDER` | generation factory | unset (= none) | post-ALLOW response generation; `groq` enables the gateway |
| `GROQ_API_KEY` | Groq classifier / gateway | — | required when either provider is `groq` |
| `GROQ_MODEL` | Groq classifier / gateway | `openai/gpt-oss-20b` | |
| `GROQ_TIMEOUT` | Groq classifier / gateway | `10` | seconds |
| `POLICY_PATH` | policy engine | `policies/policy.yaml` | |
| `AUDIT_DB_PATH` | audit log | `audit.db` | |

The two provider variables are independent: the risk classifier and the
post-ALLOW generative gateway are configured separately. With
`LLM_GENERATION_PROVIDER` unset, ALLOW responses return a null response field.

`.env` is loaded automatically by `apps/api/main.py` (python-dotenv). Existing
process environment takes precedence. `.env` is gitignored.

## Run the application

    uv run uvicorn apps.api.main:app --reload

Endpoints:
- `GET /health`
- `POST /guardrail/evaluate`

  Body:

      {
        "prompt": "...",
        "user_role": "researcher",
        "conversation_id": "abc"
      }

  (both `conversation_id` and `user_role` are required; `requested_action` optional)

Interactive docs at `http://localhost:8000/docs`.

## Tests / lint / format / types

    uv run python -m pytest        # full suite (tests/scenarios + tests/unit)
    uv run ruff check .            # lint
    uv run ruff format .           # format (then: uv run ruff format --check .)
    uv run mypy .                  # type check

CI (`.github/workflows/ci.yml`) runs `ruff check`, `ruff format --check`,
`mypy`, and `pytest`; all four must be green before merge. A make wrapper is
also available (`make test`, `make lint`, `make typecheck`, `make ci`) but the
uv commands above are authoritative.

Tests never make live external calls: the default classifier is the offline
mock, Groq tests use stubbed clients, LLM-flow tests use an in-process fake
gateway, and `tests/conftest.py` forces `LLM_PROVIDER=mock` for API-level
tests.

## Docker

    docker compose up --build      # build image, mount repo, expose :8000

- The image installs the package with `.[dev]`; dependency install failures
  fail the build.
- `env_file: .env` is passed to the container.

## Policies

Policies live in `policies/policy.yaml` and are validated at startup by
`services/policy_engine/policy_models.py` (invalid policies fail fast).

- Rules are evaluated top to bottom; **the first match wins** — order matters,
  put the most specific/severe rules first.
- A request with no matching rule is blocked (fail-closed).

Add a rule by appending YAML:

```yaml
  - id: EXAMPLE-001
    description: "Short description"
    category: PII
    action: REWRITE
```

Rule fields (as modelled in `policy_models.py`): `id` (required),
`description`, `action` (required: ALLOW / REWRITE / CLARIFY / REVIEW /
BLOCK), `risk_level`, `category`, `sensitivity`, `disguise_detected`,
`injection_detected`, `require_roles`, `exclude_roles`, `required_controls`.

## Adding / changing a risk classifier

1. Implement `services/risk_engine/classifier.py:RiskClassifier`:
   `classify(request: GuardrailRequest) -> RiskAssessment`.
2. Keep the contract: return a `RiskAssessment`; never an action/decision field.
3. Fail closed: any internal failure must produce `risk_level=CRITICAL` (or an
   equivalent conservative fallback), never raise into the policy engine, and
   never allow by default.
4. Register the implementation in `services/risk_engine/factory.py` behind a
   new `LLM_PROVIDER` value.
5. Keep provider SDKs inside the classifier module — nothing in `apps/` or
   `services/policy_engine/` imports them.

## Adding / changing a generation provider

1. Implement `services/llm/gateway.py:LLMGateway`:
   `async generate(request: LLMRequest) -> LLMResponse`.
2. Register it in `services/llm/factory.py` behind a new
   `LLM_GENERATION_PROVIDER` value (independent of `LLM_PROVIDER`).
3. The gateway is only ever called for policy-ALLOWed requests; failures must
   raise so the API can fail safely — do not return fabricated text on error.
4. Keep provider SDKs inside `services/llm/`.

## Conventions in use

- `ruff` (rules E/F/I/UP/B) + `ruff format`, line length 100, target py312.
- `mypy` over the repo.
- pydantic for domain models and policy validation.
- Business logic is tested without live external services (stubbed clients).