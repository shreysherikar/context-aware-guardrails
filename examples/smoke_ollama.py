"""Quick smoke test against a running server with Ollama enabled."""

from __future__ import annotations

import json
import sys
import urllib.request

BASE = "http://127.0.0.1:8000"


def post_json(path: str, body: dict, token: str | None = None) -> dict:
    data = json.dumps(body).encode()
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(f"{BASE}{path}", data=data, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=300) as resp:
        return json.loads(resp.read())


def main() -> int:
    cfg = json.loads(urllib.request.urlopen(f"{BASE}/demo/config", timeout=10).read())
    print("Config:", json.dumps(cfg, indent=2))

    token = post_json("/auth/dev-token", {"role": "researcher"})["token"]
    print("\n--- Text ALLOW + Ollama generation ---")
    result = post_json(
        "/guardrail/evaluate",
        {"prompt": "Summarize this internal document in one sentence.", "conversation_id": "smoke"},
        token,
    )
    print("action:", result.get("action"))
    print("response:", (result.get("response") or "")[:200])
    if result.get("action") != "ALLOW" or not result.get("response"):
        print("FAIL: expected ALLOW with LLM response")
        return 1

    print("\n--- Image safe brochure (Ollama vision OCR) ---")
    with open("examples/optical/safe_brochure.png", "rb") as f:
        image_bytes = f.read()

    import uuid

    boundary = f"----WebKitFormBoundary{uuid.uuid4().hex}"
    body = (
        (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="conversation_id"\r\n\r\n'
            f"smoke-image\r\n"
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="image"; filename="safe_brochure.png"\r\n'
            f"Content-Type: image/png\r\n\r\n"
        ).encode()
        + image_bytes
        + f"\r\n--{boundary}--\r\n".encode()
    )

    req = urllib.request.Request(
        f"{BASE}/guardrail/evaluate-image",
        data=body,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": f"multipart/form-data; boundary={boundary}",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=300) as resp:
        img_result = json.loads(resp.read())

    print("action:", img_result.get("action"))
    print("ocr findings:", img_result.get("optical_assessment", {}).get("finding_count"))
    print("response:", (img_result.get("response") or "")[:200])
    if img_result.get("action") not in ("ALLOW", "REWRITE"):
        print("FAIL: unexpected image action", img_result.get("action"))
        return 1

    print("\nSmoke test passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
