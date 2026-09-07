# ContextGuard AI

## Desktop app (Windows)

Download **ContextGuard-windows-x64.zip** from
[Releases](https://github.com/shreysherikar/context-aware-guardrails/releases),
unzip it, and double-click `ContextGuard.exe`. Sign in with email and password
(local demo: `clinician@contextguard.local` / `clinician`), then send a prompt.

The app talks to your local **Llama** through Ollama (`llama3.2:3b`). Keep
`ollama serve` running before you open the exe.

## Mobile app

Install **app-debug.apk** from the same Releases page (Android sideload), or open
the **phone URL** from the desktop window title on the same Wi-Fi and choose
**Add to Home Screen**. Sign in with **Start session**, dummy accounts
(`clinician@contextguard.local` / `clinician` or `demo@contextguard.local` /
`demo`), or Google.

Optional: place a `.env` file next to the exe to override the model or switch
providers. Logs and the audit database live in `%LOCALAPPDATA%\ContextGuard`.

From source: `uv sync --extra desktop` then `uv run python -m apps.desktop`.

## Live demo

Open **https://d3ozo8x5pyta7s.cloudfront.net/** (no clone needed). Click **Start session** (hackathon token) or sign in with `demo@contextguard.local` / `demo`, then use **Prompt Lab** for the five canned examples.

API: **https://co-384d94ac3210447c92a6e4e333428cbf.ecs.ap-south-1.on.aws** — `GET /health` → `{"status":"ok"}`.

Full judge script, ECS env checklist, and curl examples: [docs/demo-runbook.md](docs/demo-runbook.md).

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
prompt — or open **Prompt Lab** and click one of the five example buttons, one per
policy outcome (ALLOW / REWRITE / CLARIFY / REVIEW / BLOCK). Each Prompt Lab check
starts a new conversation id.

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
- [Demo runbook](docs/demo-runbook.md) — live URLs, ECS env vars, five judge prompts
- [Engineering](docs/engineering.md) — developer conventions and workflow
- [Security](docs/security.md) — security posture and limitations
- [Decisions](docs/decisions.md) — architecture decision records
- [Contributing](CONTRIBUTING.md) — contribution process