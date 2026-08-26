# Getting Started (internal)

This guide gets a new contributor running locally and points to where new code
belongs. It describes the current repository only. For architecture and
rationale, see `architecture.md` and `decisions.md`.

## Prerequisites

- Python 3.12 (per `.python-version`; the dev extra also targets 3.12)
- [`uv`](https://docs.astral.sh/uv/) for dependency management and running
  commands. CI uses `uv` throughout.

## Clone and install

    git clone <repo-url>
    cd context-aware-guardrail
    uv sync            # installs dependencies including dev extras, from uv.lock

The project is installable (`pyproject.toml` with `[tool.setuptools.packages.find]`
covering `apps`, `domain`, `services`). `uv sync` is the supported path; a
`Makefile` wrapper exists (`make install`, `make test`, `make lint`) but the
`uv` commands below are authoritative.

## Environment setup

Copy the template and adjust:

    cp .env.example .env

The relevant knobs:

- `LLM_PROVIDER` — selects the risk classifier. Default `mock` runs the offline
  `KeywordMockClassifier` (no network). Set `groq` to use the real
  `GroqRiskClassifier` (requires `GROQ_API_KEY`).
- `LLM_GENERATION_PROVIDER` — selects the post-ALLOW generation gateway.
  Unset (default) means no generation is wired and ALLOW responses carry a
  null response field. Set `groq` to use `GroqLLMGateway` (requires
  `GROQ_API_KEY`).
- `GROQ_API_KEY`, `GROQ_MODEL`, `GROQ_TIMEOUT` — Groq settings, used only when a
  Groq provider is enabled.
- `POLICY_PATH`, `AUDIT_DB_PATH` — override the policy file and audit database
  locations.
- `OPTICAL_OCR_PROVIDER` — OCR for `POST /guardrail/evaluate-image`. Default
  `mock` (offline). Set `tesseract` for local Tesseract (`uv sync --extra
  optical-tesseract` plus a system Tesseract binary).
- `OPTICAL_MAX_IMAGE_BYTES` — max upload size (default 10485760 = 10 MB).

`LLM_PROVIDER=mock` is the safe default for getting the server up without
credentials.

## Running the application

    uv run uvicorn apps.api.main:app --reload

- `GET /health` — liveness check (`{"status":"ok"}`)
- `POST /guardrail/evaluate` — text evaluation endpoint

  Body:

      {
        "prompt": "...",
        "conversation_id": "abc"
      }

  (`conversation_id` required; role comes from the JWT, not the body)

- `POST /guardrail/evaluate-image` — multipart optical evaluation (`image` file
  + `conversation_id` form field). Same JWT auth as the text endpoint.

Interactive docs: `http://localhost:8000/docs`. Docker alternative:
`docker compose up --build` (mounts the repo and passes `.env` in).

## Running tests

    uv run python -m pytest

Tests must run offline. `tests/conftest.py` forces `LLM_PROVIDER=mock` and
`LLM_GENERATION_PROVIDER=""` via `setdefault` before any app import, and
`apps/api/main.py` runs `load_dotenv()` with default `override=False`, so a
local `.env` with `groq` values does not enable real clients during the test
run.

One caveat: `setdefault` only applies when the variable is not already present
in the process environment. If you `export LLM_PROVIDER=groq` (or
`LLM_GENERATION_PROVIDER=groq`) in your shell rather than only setting it in
`.env`, that export wins and tests can attempt real network calls. Run tests
from a shell that does not export these variables.

## Lint / format / type-check

    uv run ruff check .       # lint
    uv run ruff format .      # format (verify with uv run ruff format --check .)
    uv run mypy .             # static types

`pre-commit` (`.pre-commit-config.yaml`) runs `ruff` (with `--fix`) and
`ruff-format`. CI runs `ruff check`, `ruff format --check`, `mypy`, and
`pytest`.

## Where new code goes

- **New policy rule**: add YAML to `policies/policy.yaml` (first match wins;
  an invalid rule fails at startup). Do not encode new rules as Python `if`
  statements.
- **New risk category or classifier**: add to `services/risk_engine/`
  (`classifier.py` for the interface and the offline classifier, `factory.py`
  to register behind a new `LLM_PROVIDER` value, `groq_classifier.py` for the
  model-backed implementation). The `RiskAssessment` contract must not gain a
  decision field.
- **New generation provider**: implement `services/llm/gateway.py:LLMGateway`
  and register it in `services/llm/factory.py` behind `LLM_GENERATION_PROVIDER`.
- **REWRITE / sanitization**: `services/sanitization/` — unified text + optical
  safe-context production. REWRITE means transform into a policy-compliant
  representation before LLM generation. Do not put redaction rules in
  `apps/api/main.py`.
- **Not here**: `apps/api/main.py` is wiring-only and must not contain business
  or policy logic — routing rules live in `policies/` and decisions in
  `services/policy_engine/`. See the layering table in `architecture.md`.

## Recording decisions

Non-trivial design choices should be recorded in `docs/decisions.md` (status,
context, decision, reason, consequences). If a choice is not settled, record it
as an open decision rather than leaving it implicit.