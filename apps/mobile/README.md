# ContextGuard mobile

Android wrapper around the existing dashboard. The phone UI talks to the
Windows/desktop ContextGuard server (and your local Llama via Ollama).

## Test without an APK

1. Start ContextGuard on the PC (`ContextGuard.exe` or `uv run python -m apps.desktop`).
2. On the same Wi-Fi, open the **phone URL** from the desktop window title
   (example: `http://192.168.1.10:18765/`).
3. In the browser menu choose **Add to Home Screen**.

## Build the Android APK

CI produces `app-debug.apk` on version tags. Locally:

```bash
cd apps/web-src && npm ci && npm run build
cd ../mobile && npm ci && npx cap add android && npx cap sync
cd android && ./gradlew assembleDebug
```

Install `android/app/build/outputs/apk/debug/app-debug.apk` on the phone.

Sign-in:

- **Start session** (hackathon) if the API has `AUTH_DEV_MODE=true`
- Dummy accounts: `demo@contextguard.local` / `demo`, or `clinician@contextguard.local` / `clinician`
- Google, if configured

On the APK, set **API server** on the login screen if the bundled host is wrong. Production API:

`https://co-384d94ac3210447c92a6e4e333428cbf.ecs.ap-south-1.on.aws`

CloudFront UI (same backend): https://d3ozo8x5pyta7s.cloudfront.net/
