"""Configure environment and wait for the local API before opening a window."""

from __future__ import annotations

import os
import socket
import time
import urllib.error
import urllib.request
from pathlib import Path

from dotenv import load_dotenv

from apps.desktop.paths import (
    bundle_root,
    ensure_user_data_dir,
    executable_dir,
    persist_jwt_secret,
)

DEFAULT_PORT = 18765
HEALTH_TIMEOUT_SECONDS = 30.0


def configure_desktop_environment() -> Path:
    """Point the API at bundled assets and writable user-data databases.

    Must run before `apps.api.main` is imported. Login is always enabled in
    the desktop build (`AUTH_DEV_MODE=true`) so testers can pick a role.
    """
    data_dir = ensure_user_data_dir()
    root = bundle_root()
    exe_dir = executable_dir()

    load_dotenv(exe_dir / ".env", override=False)
    if exe_dir != root:
        load_dotenv(root / ".env", override=False)

    os.environ["AUTH_DEV_MODE"] = "true"
    if not os.getenv("AUTH_JWT_SECRET", "").strip():
        os.environ["AUTH_JWT_SECRET"] = persist_jwt_secret(data_dir / "jwt_secret")

    os.environ.setdefault("POLICY_PATH", str(root / "policies" / "policy.yaml"))
    os.environ.setdefault("EVIDENCE_CORPUS_PATH", str(root / "evidence" / "approved_sources.yaml"))
    os.environ["AUDIT_DB_PATH"] = str(data_dir / "audit.db")
    os.environ["GOVERNANCE_AUDIT_DB_PATH"] = str(data_dir / "governance_audit.db")
    os.environ["GUARDRAIL_REVIEW_DB_PATH"] = str(data_dir / "guardrail_review.db")
    os.environ.setdefault("LLM_PROVIDER", "mock")
    os.environ.setdefault("OPTICAL_OCR_PROVIDER", "mock")
    _set_if_blank("LLM_GENERATION_PROVIDER", "ollama")
    _set_if_blank("OLLAMA_MODEL", "llama3.2:3b")
    _set_if_blank("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
    _set_if_blank("OLLAMA_TIMEOUT", "600")
    return data_dir


def _set_if_blank(name: str, value: str) -> None:
    if not os.getenv(name, "").strip():
        os.environ[name] = value


def pick_port(preferred: int = DEFAULT_PORT) -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind(("127.0.0.1", preferred))
            return preferred
        except OSError:
            sock.bind(("127.0.0.1", 0))
            return int(sock.getsockname()[1])


def wait_for_health(port: int, timeout: float = HEALTH_TIMEOUT_SECONDS) -> None:
    deadline = time.monotonic() + timeout
    url = f"http://127.0.0.1:{port}/health"
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            with opener.open(url, timeout=1) as response:
                if 200 <= response.status < 300:
                    return
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            last_error = exc
        time.sleep(0.1)
    raise RuntimeError(f"ContextGuard server did not become ready: {last_error}")
