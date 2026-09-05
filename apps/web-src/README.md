# ContextGuard AI — Web UI

React + Vite frontend for the ContextGuard AI guardrail dashboard.

## Three run commands

### 1. Backend (prerequisite)

```bash
# From the repo root — ensure .env has AUTH_DEV_MODE=true for local dev
cp .env.example .env          # then set AUTH_DEV_MODE=true, AUTH_JWT_SECRET=<any string>
uv run uvicorn apps.api.main:app --reload
# → Backend running at http://localhost:8000
```

> `LLM_PROVIDER=mock` is the default — no external API key needed.
> `OPTICAL_OCR_PROVIDER=mock` is also the default — image uploads work offline.

### 2. Frontend dev server (hot-reload, proxied to backend)

```bash
cd apps/web-src
npm install
npm run dev
# → UI at http://localhost:5173, API calls proxied to http://localhost:8000
```

Vite's `server.proxy` forwards `/guardrail`, `/auth`, `/health`, and `/audit`
to `localhost:8000` — no CORS changes needed on the backend.

### 3. Production build (what ships)

```bash
cd apps/web-src
npm run build
# → Compiled output written to apps/web/ (emptyOutDir: true)
# With SERVE_STATIC_FRONTEND=true, FastAPI's StaticFiles mount at GET / serves
# it. Off by default — the frontend is deployed separately on S3/CloudFront.
```

After building, start the backend and visit `http://localhost:8000/` — the
new UI is served without any backend change.

## Screens

| Tab | Route | Description |
|-----|-------|-------------|
| Identity | — | Login via `POST /auth/dev-token` (dev-mode only) |
| Text Evaluate | `POST /guardrail/evaluate` | Five example prompts, full result panel |
| Image Evaluate | `POST /guardrail/evaluate-image` | File picker, preview, optical_assessment panel |
| Audit Log | `GET /audit/events` | Filterable table, expandable row detail |

## Notes

- Auth token is held in React state only — no localStorage / sessionStorage.
- Every evaluate call generates an audit event visible in the Audit Log tab.
- The Vite dev server must run alongside the backend; they are two separate processes.
