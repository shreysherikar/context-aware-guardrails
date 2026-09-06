# Engineering (internal)

Practical guide for working in this repository. Styled to match the main
`context-aware-guardrails` repo's `docs/engineering.md` conventions.

## Repository structure

```
src/app/                 expo-router routes (file-based routing)
src/screens/             screen implementations (EvaluateScreen, TextEvaluateScreen,
                         ImageEvaluateScreen, AuditLogScreen, LoginScreen)
src/components/ui/       shared UI kit (Badge, Card, Button, TextField, Banner, ScreenHeader)
src/components/          ResultCard + Expo-template scaffolding (themed-text, themed-view, app-tabs)
src/lib/decision.js      single source of truth for decision-action -> label/color mapping
src/context/             AuthContext (AsyncStorage-backed session)
src/api.js               centralized API client (error-shape contract, base URL handling)
src/constants/theme.ts   colors (light/dark), spacing, decision-status palette
src/__tests__/, src/**/__tests__/   unit tests (co-located per module)
docs/mobile-plan.md      original phase-by-phase build plan this app was built from
docs/KNOWN_ISSUES.md     honest list of what's unverified / open — read before deploying
```

## Local setup

Requires Node 22 (matches CI).

```
npm install --legacy-peer-deps   # --legacy-peer-deps needed: some Expo SDK 57
                                  # packages have peer ranges tools resolve strictly
cp .env.example .env             # then edit EXPO_PUBLIC_API_BASE_URL
npx expo start
```

## Environment variables

| Variable                   | Used by      | Notes                                                                                                                            |
| -------------------------- | ------------ | -------------------------------------------------------------------------------------------------------------------------------- |
| `EXPO_PUBLIC_API_BASE_URL` | `src/api.js` | Base URL of the ContextGuard backend. Public value (inlined into the client bundle) — never put secrets in `EXPO_PUBLIC_*` vars. |

`.env` is gitignored. Copy `.env.example` and fill in.

## Auth model (read before touching login)

The backend must have `AUTH_DEV_MODE=true` for `LoginScreen`'s
`POST /auth/dev-token` call to work at all — this is a **deliberate, temporary
trade-off**, not a default to leave on. See `docs/mobile-plan.md` (Phase 0)
and `docs/KNOWN_ISSUES.md` before changing anything here.

## Tests / lint / format / types

```
npm run lint            # eslint (flat config, eslint-config-expo + Prettier)
npm run format:check    # prettier --check .
npm run format          # prettier --write .
npm run typecheck       # tsc --noEmit
npm run test            # jest (jest-expo preset)
npm run test:coverage   # jest --coverage
npm run verify          # all four checks above, in order — this is what CI runs
```

CI (`.github/workflows/ci.yml`) runs `verify` plus a second job that does
`npx expo export --platform web` as a build sanity check (catches broken
imports/routes without needing EAS credentials or native toolchains). It does
**not** verify native iOS/Android builds — see `docs/KNOWN_ISSUES.md`.

One test file (`src/components/__tests__/ResultCard.test.js`) is currently
excluded from the run — see `docs/KNOWN_ISSUES.md` for why, and fix-then-
re-enable rather than deleting it.

## Conventions in use

- `eslint-config-expo` (flat config) + `eslint-plugin-react-hooks`'s strict
  rules, reconciled with Prettier via `eslint-config-prettier`.
- Prettier: single quotes, semicolons, 100 char width, trailing commas
  (es5) — see `.prettierrc.json`.
- Screens are plain `.js` (matching the ported web app's shape and the
  original plan doc); shared infra (`theme.ts`, `themed-text.tsx`,
  `use-theme.ts`) stays `.ts`/`.tsx`. `tsconfig.json` type-checks the `.ts`/
  `.tsx` files; the `.js` screens are not currently type-checked — a
  reasonable next step is migrating them to `.tsx` once the feature set
  stabilizes, rather than mixing migration with feature work.
- Decision-status color/label logic lives in exactly one place
  (`src/lib/decision.js`) — don't reintroduce a second copy in a new screen.
- All API errors flow through `src/api.js`'s `{ status, message, type, body }`
  shape; don't call `fetch` directly from a screen.
