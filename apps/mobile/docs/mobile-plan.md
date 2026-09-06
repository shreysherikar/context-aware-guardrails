# ContextGuard AI — React Native App: Phase-by-Phase Build Plan

This is the real, detailed plan — not a toy version. It reuses your already-deployed
AWS backend as-is (no backend changes needed for the core flow), scopes honestly for
2 days, and flags every decision that has a real trade-off instead of picking silently.
This is a checkpoint, not the end of the hackathon — the "Phase 8+ / After the 7th"
section at the bottom is exactly as real as everything above it.

---

## Phase 0 — Login strategy: `AUTH_DEV_MODE=true` (chosen)

**The trade-off, stated plainly so it doesn't get forgotten:** your production
backend currently has `AUTH_DEV_MODE=false` (correct, and what I recommended earlier
— it disables `/auth/dev-token` entirely so nobody can mint a token for any role
without real identity verification). Building the mobile app against
`AUTH_DEV_MODE=true` means **reopening that hole for as long as it's on** — anyone who
can reach the API can mint a token for any role, no identity check at all.

**You've chosen this deliberately, for a real reason: role-based access tied to your
company's actual roles matters more right now than closing this gap, and Google
Sign-In only gives you an identity + allowlist, not a role.** That's a legitimate
trade-off to make consciously — the point of flagging it isn't to relitigate the
choice, it's to make sure it's never an _accidental_ state.

**Two non-negotiable guardrails while running this way:**

1. **Set a calendar reminder or phone alarm right now** to flip `AUTH_DEV_MODE` back
   to `false` the moment the app isn't actively needed for demoing — don't rely on
   memory after a long demo day.
2. Treat this as the reason to prioritize **Phase X (real role-based auth)** in the
   "After the 7th" section at the bottom — that's the actual fix for the underlying
   need (per-user roles), not a permanent excuse to leave dev mode on.

**⚠️ Common mistake:** don't build a second login path "just in case" — commit to
`AUTH_DEV_MODE=true` for this phase and build once. If real role-based identity
becomes urgent before the 7th, come back and we'll scope that properly rather than
bolting it on under time pressure.

---

## Phase 1 — Project scaffold

**Do:**

1. Install Expo CLI tooling (no Xcode/Android Studio needed for Expo Go development):
   ```
   npx create-expo-app contextguard-mobile
   cd contextguard-mobile
   ```
2. Install the Expo Go app on your phone (App Store / Play Store) — this is how you'll
   run and see the app live, with hot reload, with zero build/signing setup.
3. Start the dev server and scan the QR code with Expo Go:
   ```
   npx expo start
   ```
4. Confirm the default template screen loads on your actual phone before writing any
   real code. This proves your phone and computer can talk to each other.

_(No Cline prompt needed for this phase — it's tooling setup, not code generation.)_

**⚠️ Careful / common mistakes:**

- **Phone and computer must be on the same Wi-Fi network** for the default connection
  mode. If they're on separate networks (phone on mobile data, restrictive office
  Wi-Fi that isolates devices, etc.), use tunnel mode: `npx expo start --tunnel`
  (slower, but works across networks — useful if venue Wi-Fi is unreliable during the
  actual demo).
- Don't install the full React Native CLI / Xcode / Android Studio toolchain unless
  you specifically need a custom native module — for this scope, Expo Go covers
  everything (AsyncStorage, image picker, fetch) with zero native build step.

---

## Phase 2 — Networking layer (the good news: CORS doesn't apply here)

**Context:** your web app needed `ALLOWED_ORIGINS` CORS configuration because
browsers enforce cross-origin restrictions. **React Native apps are not browsers** —
`fetch()` from RN code isn't subject to CORS at all. This means the RN app can call
your ECS backend directly with zero backend changes for this reason. (Your backend's
CORS config still matters for the web app — leave it as-is.)

**Do:**

1. Create `src/api.js` in the RN project, closely modeled on the web app's
   `apps/web-src/src/api.js` — same `apiFetch` shape (method, body, token, error
   normalization), so any Cline prompts referencing "the same shape as the web app"
   land correctly.
2. **Environment variables in Expo work differently from Vite** — this is the RN
   equivalent of the `VITE_` prefix gotcha that bit you on the web build. In Expo SDK
   49+, any variable prefixed `EXPO_PUBLIC_` in a `.env` file is automatically
   inlined at build time. Create `.env`:
   ```
   EXPO_PUBLIC_API_BASE_URL=https://co-384d94ac3210447c92a6e4e333428cbf.ecs.ap-south-1.on.aws
   ```
   (No Google Client ID needed for this phase — dev-mode login doesn't use it. Add it
   later if/when native Google Sign-In gets built.)
   Read it as `process.env.EXPO_PUBLIC_API_BASE_URL` — **not** `import.meta.env`,
   that's Vite-specific and doesn't exist in RN.
3. Reuse the exact same trailing-slash defensive strip you already fixed once on the
   web side — don't reintroduce that bug in a second codebase:
   ```js
   const baseUrl = (process.env.EXPO_PUBLIC_API_BASE_URL || '').replace(/\/+$/, '');
   ```

**Cline prompt:**

```
Create src/api.js in this Expo React Native project, modeled closely on the
existing web app's apps/web-src/src/api.js (I'll paste it below for reference).

Requirements:
- Export an async apiFetch(path, { method = 'GET', body = null, token = null,
  headers = null } = {}) function with the SAME error-shape contract as the web
  version: on non-ok responses, throw an object with { status, message, type,
  body } where type is one of 'network' | 'auth' | 'validation' | 'server' |
  'unavailable', matching the web app's status-code-to-type mapping exactly
  (401->auth, 404/400->validation, 503->unavailable, else->server, network
  errors->status 0/type 'network').
- Base URL: read process.env.EXPO_PUBLIC_API_BASE_URL (NOT import.meta.env,
  this is Expo not Vite), strip any trailing slash(es) defensively with
  .replace(/\/+$/, ''), then prepend it to `path`.
- Do NOT use fetch's default behavior for FormData content-type headers -
  match the web version's behavior of only setting Content-Type: application/json
  when body is not a FormData instance.
- This file will be imported by screens that need conversation-scoped requests
  like /guardrail/evaluate - keep the function generic and reusable, don't
  hardcode any specific endpoint.

Here is the reference web version:
[paste the contents of apps/web-src/src/api.js here]
```

**⚠️ Careful / common mistakes:**

- **Android blocks plain HTTP by default** (cleartext traffic policy) — your backend
  is HTTPS via the ALB already, so this shouldn't bite you, but if you ever test
  against a plain-`http://` local backend from a physical Android device, it will
  silently fail and this is why.
- Restart the Expo dev server after changing `.env` — like Vite, env vars are baked
  in at build/bundle time, not read live.
- Don't forget `.env` in `.gitignore` if it ever contains anything more sensitive
  than a public API URL and a Client ID (both are fine to expose, same as the web
  app's `.env.production`).

---

## Phase 3 — Auth screen (`AUTH_DEV_MODE=true`)

**Do:**

1. Confirm `AUTH_DEV_MODE=true` is actually set on your ECS backend (the app will
   get a 404 on `/auth/dev-token` otherwise — that endpoint literally doesn't exist
   when dev mode is off, by design).
2. Port the role-picker pattern from `apps/web-src/src/pages/LoginPage.jsx`: a simple
   text input or dropdown for role (`employee`, `clinician`, `reviewer`, `admin`,
   etc. — same free-form role strings the web app already uses), POST to
   `/auth/dev-token` with `{ role }`, store the returned token.
3. Install AsyncStorage — React Native has no `localStorage`:
   ```
   npx expo install @react-native-async-storage/async-storage
   ```
   Use it to persist `{ token, role }` so users aren't logged out every time the app
   reloads, mirroring the web app's `AuthContext` shape but backed by AsyncStorage
   instead of in-memory React state.

**Cline prompt:**

```
Create a login screen and an AuthContext for this Expo React Native app, using
AUTH_DEV_MODE-based login (a role picker, not Google Sign-In).

1. Create src/context/AuthContext.js, modeled on the web app's
   apps/web-src/src/context/AuthContext.jsx (same shape: { auth: {token, role} |
   null, login(token, role), logout() }), but backed by
   @react-native-async-storage/async-storage instead of in-memory React state so
   the session survives app restarts. Load the persisted value on mount (async,
   show a brief loading state), and write to storage on every login/logout.

2. Create src/screens/LoginScreen.js:
   - A text input or simple picker for "role" (free-form string, e.g. employee,
     clinician, reviewer, admin - same free-form roles the web app uses)
   - A "Log in" button that calls apiFetch('/auth/dev-token', { method: 'POST',
     body: { role } }) from src/api.js
   - On success, call the AuthContext's login(data.token, role) - check the
     actual response shape from apps/api/main.py's /auth/dev-token endpoint
     first and match it exactly, don't assume
   - On failure (e.g. 404 if AUTH_DEV_MODE is off), show a clear error message,
     not a silent failure
   - Wrap the screen in SafeAreaView and use KeyboardAvoidingView around the
     input so the keyboard doesn't cover it

Show me the diff for both files before I run it.
```

**⚠️ Careful / common mistakes:**

- **`localStorage` doesn't exist in RN** — code copied from the web app that
  references it will crash silently or throw `ReferenceError`. Use AsyncStorage.
- **If `/auth/dev-token` 404s**, the first thing to check is whether
  `AUTH_DEV_MODE=true` actually made it into the ECS task's live environment
  variables — a redeploy that didn't pick up the env change is the most common cause,
  not a code bug.
- Since anyone reaching this endpoint can request _any_ role right now (that's the
  whole trade-off from Phase 0), don't be surprised if a teammate accidentally picks
  `admin` while testing — that's expected, not a bug, while dev mode is on.

---

## Phase 4 — Core screen: Text Evaluate

This is the one screen that must work. Everything else is bonus.

**Do:**

1. A single screen: text input for the prompt, a submit button, calling
   `POST /guardrail/evaluate` with `{ prompt, conversation_id }` and the bearer
   token — same request shape as `apps/web-src/src/pages/TextEvaluatePage.jsx`.
2. Generate a `conversation_id` client-side the same way the web app does
   (`convo-${Date.now()}`).
3. Handle loading state (disable the button, show a spinner) and error state
   (network error, 401, etc.) — reuse the same error-shape handling pattern from
   `api.js`.

**Cline prompt:**

```
Create src/screens/TextEvaluateScreen.js for this Expo React Native app, the
core screen of the whole app.

Requirements:
- A text input (multiline, wrapped in KeyboardAvoidingView + SafeAreaView) for
  the prompt, and a submit button
- Generate a conversation_id client-side the same way the web app does:
  `convo-${Date.now()}` - create a new one each time the screen mounts, with a
  "New conversation" button to reset it, matching
  apps/web-src/src/pages/TextEvaluatePage.jsx's pattern
- On submit, call apiFetch('/guardrail/evaluate', { method: 'POST', token,
  body: { prompt, conversation_id } }) from src/api.js, using the token from
  AuthContext
- Show a loading spinner and disable the submit button while the request is in
  flight
- On error, show a clear message using the error's `.message` field from the
  api.js error shape - don't just show "an error occurred"
- On success, store the full response and pass it to a separate ResultCard
  component (to be built next) rather than rendering it inline in this file
- Include the same 5 example prompts (one per policy outcome: ALLOW, REWRITE,
  CLARIFY, REVIEW, BLOCK) as quick-fill buttons, copied from the `Hh` array in
  apps/web-src/src/pages/TextEvaluatePage.jsx, so testing all 5 outcomes is fast

Show me the diff before I run it.
```

**⚠️ Careful / common mistakes:**

- Wrap text input screens in `KeyboardAvoidingView` (RN-specific) — otherwise the
  on-screen keyboard covers the input field on smaller phones, a very common RN
  first-timer issue.
- Use `SafeAreaView` at the screen root so content doesn't render under the phone's
  notch/status bar.
- Don't block on getting every field right first try — get the request/response
  cycle working end-to-end with a raw `console.log` of the response before building
  the pretty result UI in Phase 5. Prove connectivity first.

---

## Phase 5 — Result display

**Do:**

1. A simplified version of the web's `ExplainableDecisionPanel.jsx` — don't port the
   whole nested collapsible debug-details tree, that's a lot of RN layout work for
   low demo value. Show: the decision badge (ALLOW/REWRITE/CLARIFY/REVIEW/BLOCK,
   color-coded same as web), the reason text, and the LLM response if present.
2. Reuse the same color mapping the web app uses for decision badges, so the demo
   looks visually consistent between web and mobile.

**Cline prompt:**

```
Create src/components/ResultCard.js for this Expo React Native app - a
simplified version of the web app's decision display, NOT the full nested
debug-details tree from apps/web-src/src/components/ExplainableDecisionPanel.jsx.

Requirements:
- Accept the full /guardrail/evaluate response object as a prop
- Render a color-coded decision badge for the top-level decision
  (ALLOW/REWRITE/CLARIFY/REVIEW/BLOCK) - use the same color mapping as the web
  app's DecisionBadge.jsx (check that file for the exact color-to-action map,
  don't invent new colors)
- Show the reason/explanation text below the badge
- If the response includes an LLM-generated response field, show it in a
  distinct bordered box below the reason
- Use React Native's StyleSheet.create() for styling - do NOT try to reuse or
  reference any .css file, RN has no CSS
- Keep this component simple: badge + reason + optional LLM response. Do not
  attempt to port the nested collapsible risk_assessment/policy_decision debug
  panels from the web version - that's explicitly out of scope for this pass

Show me the diff before I run it.
```

**⚠️ Careful / common mistakes:**

- RN has no CSS — styling is done via the `StyleSheet` API or inline style objects.
  Don't try to reuse the web app's `.css` files directly; the concepts (colors,
  spacing) port over, the syntax doesn't.
- Keep this screen simple. A clean, working ALLOW/BLOCK badge with reason text beats
  a half-finished attempt at the full debug panel every time in a live demo.

---

## Phase 6 — On-device testing checklist

Go through this **on your actual phone**, not just in a simulator, before you
consider Phase 1–5 "done":

1. Cold-start the app (fully close Expo Go, reopen) — confirm login state behaves as
   expected (logged out, or persisted via AsyncStorage if you implemented that).
2. Log in for real.
3. Submit a prompt for each of the 5 policy outcomes (reuse the example prompts from
   `apps/web-src/src/pages/TextEvaluatePage.jsx`'s `Hh` example array — ALLOW,
   REWRITE, CLARIFY, REVIEW, BLOCK) and confirm each renders correctly.
4. Turn on airplane mode mid-request once, on purpose — confirm you get a handled
   error state, not a crash. Judges will not be gentle with live demos.
5. If using tunnel mode for the demo, test the whole flow once over tunnel mode
   specifically — it's slower and occasionally flakier than direct LAN mode, and you
   want to know that _before_ you're in front of judges.

---

## Phase 7 — Stretch: Audit Log screen (only if Phase 1–6 are rock solid)

Read-only screen, `GET /audit/events`, rendered as a scrollable list (RN `FlatList`,
not a raw `.map()` — `FlatList` is the performant, correct way to render lists in RN
and handles the same "prompts stored redacted" backend behavior the web app already
handles).

**Cline prompt:**

```
Create src/screens/AuditLogScreen.js for this Expo React Native app.

Requirements:
- On mount, call apiFetch('/audit/events?limit=50', { token }) from src/api.js
- Render results using React Native's FlatList component (NOT .map() over a
  ScrollView - FlatList is required for performant list rendering in RN),
  showing timestamp, conversation ID (truncated), role, and the decision badge
  (reuse the ResultCard's badge color logic, extract it into a shared component
  if it isn't already)
- Add pull-to-refresh (FlatList's refreshControl prop) to re-fetch
- Handle the empty state (no events yet) and error state clearly, matching the
  patterns already used in TextEvaluateScreen.js
- Note: prompts may come back redacted (e.g. "[text input; sanitized]") for
  REWRITE-outcome events - this is expected backend privacy-preserving
  behavior, not a bug, don't try to work around it

Show me the diff before I run it.
```

## Phase 8 — Stretch: Image Evaluate screen (only if Phase 7 is solid)

Uses `expo-image-picker` instead of a web `<input type="file">` — different API,
same concept. Multipart upload to `POST /guardrail/evaluate-image` needs RN's
specific `FormData` shape for file uploads:

```js
formData.append('image', { uri: asset.uri, name: 'photo.jpg', type: 'image/jpeg' });
```

This is a real RN-specific gotcha — the `{ uri, name, type }` object shape is
different from how the web app appends a `File` object directly.

**Cline prompt:**

```
Create src/screens/ImageEvaluateScreen.js for this Expo React Native app.

First run: npx expo install expo-image-picker

Requirements:
- A button to pick an image from the device library using expo-image-picker's
  launchImageLibraryAsync (images only, no video)
- Show a preview of the selected image before submitting
- On submit, build a FormData object using React Native's file-upload shape:
  formData.append('image', { uri: asset.uri, name: 'photo.jpg', type:
  'image/jpeg' }) - this is DIFFERENT from how a web File object is appended,
  do not copy the web app's approach directly
  formData.append('conversation_id', conversationId)
- POST to /guardrail/evaluate-image via apiFetch, passing the FormData as body
  with no explicit Content-Type header (let fetch set the multipart boundary
  automatically, matching how apps/web-src/src/pages/ImageEvaluatePage.jsx
  handles this on the web side)
- Pass the response to the same ResultCard component used in TextEvaluateScreen
- Match the same 10MB size limit and PNG/JPEG/WEBP-only validation the web app
  enforces client-side (see Jc and Vh constants in the web app's built bundle,
  or check services/optical_guardrail/validation.py for the backend's actual
  accepted types/size limit and match those exactly)

Show me the diff before I run it.
```

---

## Common mistakes cheat-sheet (all in one place)

| Mistake                                       | What happens                                               | Fix                                                            |
| --------------------------------------------- | ---------------------------------------------------------- | -------------------------------------------------------------- |
| Using `localStorage`                          | Crashes or silently fails                                  | Use `AsyncStorage`                                             |
| Using `import.meta.env.VITE_*`                | `undefined`, silent failure                                | Use `process.env.EXPO_PUBLIC_*`                                |
| Forgetting `EXPO_PUBLIC_` prefix              | Env var is `undefined` in the app                          | Prefix must be exact                                           |
| Not restarting dev server after `.env` change | Old value keeps being used                                 | Restart `expo start`                                           |
| Testing only in simulator                     | Network/device issues don't show up until a real device    | Test on your actual phone early and often                      |
| Copying web `.css` files                      | Doesn't work, RN has no CSS                                | Use `StyleSheet.create()`                                      |
| No `KeyboardAvoidingView`                     | Keyboard covers input fields                               | Wrap text-entry screens                                        |
| No `SafeAreaView`                             | Content renders under notch/status bar                     | Wrap screen roots                                              |
| Plain `http://` on Android                    | Silently blocked (cleartext policy)                        | Use HTTPS (you already do)                                     |
| `/auth/dev-token` returns 404                 | `AUTH_DEV_MODE` isn't actually `true` on the live ECS task | Redeploy after confirming the env var, don't assume it applied |
| Forgetting to flip `AUTH_DEV_MODE` back off   | Security hole stays open indefinitely                      | Set the alarm from Phase 0, actually use it                    |
| Reintroducing the trailing-slash bug          | Same double-slash 404 as the web app had                   | Reuse the `.replace(/\/+$/, '')` guard                         |

---

## After the 7th — this is a checkpoint, not the end

If you stop after Phase 4–6 (a working login + core evaluate screen on a real phone
hitting your real backend), that's a legitimate, demoable native app — don't feel
pressure to rush Phases 7–8 in just to say you did everything. Natural next steps
after the 7th, in priority order, whenever the team picks this back up:

1. **Real role-based identity, replacing `AUTH_DEV_MODE=true`.** This is the actual
   priority item, not optional polish — it's the fix for the trade-off made in
   Phase 0. Two realistic paths once there's real time: (a) native Google Sign-In
   via `expo-auth-session`, reusing your already-verified `/auth/google` endpoint,
   with role assigned the same way the web app does (default role + allowlist); or
   (b) if company-specific roles genuinely need to come from somewhere other than a
   Google-verified email, a proper identity provider (Okta/Azure AD/etc.) issuing
   role claims — bigger scope, worth a dedicated planning pass rather than bolting on.
2. Phases 7–8 above, if not done.
3. Governance Dashboard / Audit Log with real-time polling (the web app already
   polls every 15s — same pattern ports over).
4. Voice input via `expo-av` — a different API from the web's `MediaRecorder`-based
   `useVoiceInput` hook, but conceptually the same feature.
5. Push notifications for pending human-approval items (a genuinely new capability
   mobile enables that the web app doesn't have) — this is a good "what's next"
   talking point for a follow-up pitch even before it's built.
6. Real app-store distribution (`expo build` / EAS Build), which is its own multi-day
   process with developer accounts, signing, and review time — correctly out of
   scope for any hackathon timeline.
