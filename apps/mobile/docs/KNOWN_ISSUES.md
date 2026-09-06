# Known issues / open follow-ups

Kept separate from the (not-yet-written) README so the next person picking
this up sees exactly what's verified vs. not, without digging through commits.

## Open

1. **`ResultCard.test.js` is excluded from the test run** (see
   `jest.config.js`). `@testing-library/react-native@14`'s new `test-renderer`
   backend isn't completing `render()` in this environment — every assertion
   fails with `"render function has not been called"`. `api.test.js` and
   `decision.test.js` (the actual business logic those tests would exercise
   via `ResultCard`) pass and are not affected. Needs someone with a real
   device/simulator to debug the RNTL config before re-enabling; don't
   silently delete the test file, fix and re-enable it.
2. **Nothing has been run on a real device or simulator yet.** Everything in
   this repo has been verified via `npm run verify` (lint, format, typecheck,
   unit tests) and `npx expo export --platform web` (bundling sanity check —
   confirms imports/routes resolve, does NOT confirm native rendering). Before
   trusting this on a phone, run Phase 6 of `docs/mobile-plan.md`'s checklist
   (cold start, real login, all 5 policy outcomes, airplane-mode error
   handling, tunnel mode if used for a demo).
3. **`AUTH_DEV_MODE=true` is a deliberate, temporary trade-off**, not an
   oversight — see the original plan doc. Flip it back to `false` on the
   backend the moment the app isn't actively being demoed. Real role-based
   auth (Google Sign-In via `expo-auth-session`, or a proper IdP) is the
   actual fix and should be prioritized before this ships to real users.
4. **No CD / app-store distribution pipeline.** CI only lints/tests/typechecks
   and does a web-export sanity build. EAS Build, signing, and store
   submission are a separate, deliberately out-of-scope effort.
5. **Backend endpoint assumptions unverified from this environment.** This
   sandbox has no access to the live ECS backend, so `/auth/dev-token`,
   `/guardrail/evaluate`, `/guardrail/evaluate-image`, and `/audit/events`
   request/response shapes are implemented per the original plan doc and the
   web app's known behavior, but not independently confirmed against a live
   request/response here. Test on a device against the real backend before
   assuming the shapes are exactly right (e.g. `AuditLogScreen` currently
   defensively accepts either a bare array or `{ events: [...] }` from
   `/audit/events` because the exact response envelope wasn't confirmed).

## Verified working (as of this handoff)

- `npm run lint` — clean (ESLint flat config, `eslint-config-expo` + Prettier)
- `npm run format:check` — clean
- `npm run typecheck` — clean (`tsc --noEmit`)
- `npm run test` — 19/19 passing (`api.js` error-mapping, decision-metadata
  helper)
- `npx expo export --platform web` — bundles successfully, all 4 routes
  (`/`, `/audit-log`, `/_sitemap`, `/+not-found`) resolve with no broken
  imports
