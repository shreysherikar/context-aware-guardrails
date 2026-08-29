# ContextGuard AI

## Live demo

Open the hosted demo (no clone or install needed): **<https://YOUR-DEPLOYED-URL.onrender.com>** —
pick a role, click **Start session**, then send a prompt or one of the five example
buttons. Deployment is the Dockerfile at the repo root via [`render.yaml`](render.yaml)
(deployment config only — no secrets are committed; the env vars are set by name in
the Render dashboard, listed in that file's header).

## Quickstart for judges

Get the demo UI running in about two minutes — no frontend build step, no API keys.

```bash
git clone https://github.com/shreysherikar/context-aware-guardrails
cd context-aware-guardrails
uv sync
cp .env.example .env
```

Then edit `.env`: set `AUTH_DEV_MODE=true` **and** a non-empty `AUTH_JWT_SECRET`
(any value works for local demos — generate one with
`python -c "import secrets; print(secrets.token_urlsafe(32))"`). `LLM_PROVIDER=mock`
is already the default, so no network calls or credentials are needed.

```dotenv
AUTH_DEV_MODE=true
AUTH_JWT_SECRET=<any non-empty value>
```

Start the server and open the UI:

```bash
uv run uvicorn apps.api.main:app
```

Open **http://localhost:8000** → pick a role, click **Start session**, then send a
prompt — or click one of the five example buttons, one per policy outcome
(ALLOW / REWRITE / CLARIFY / REVIEW / BLOCK).

**No API key? You're still good.** The default `LLM_PROVIDER=mock` config runs
fully offline, so every policy decision works; ALLOW/REWRITE just return a null
response field (no generation provider is wired by default). That is correct
behaviour, and the UI says so instead of looking broken.

### Optional: real generated answers

To see full end-to-end generation in the demo, add these two lines to your local
`.env` (not `.env.example`) and restart uvicorn:

```dotenv
LLM_GENERATION_PROVIDER=groq
GROQ_API_KEY=<your key>
```

Get a free Groq API key in about a minute at https://console.groq.com — free
tier, no credit card required. No code change needed: the UI renders whatever
the API returns.

A context-aware AI guardrail for risk detection and deterministic policy
enforcement in front of internal AI assistants.

## Documentation

- [Architecture](docs/architecture.md) — current implementation and target architecture
- [Getting Started](docs/getting-started.md) — local setup and where new code goes
- [Engineering](docs/engineering.md) — developer conventions and workflow
- [Security](docs/security.md) — security posture and limitations
- [Decisions](docs/decisions.md) — architecture decision records
- [Contributing](CONTRIBUTING.md) — contribution process