"""Configure environment for the desktop shell before opening a window."""

from __future__ import annotations

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
)

DEFAULT_PORT = 18765
HEALTH_TIMEOUT_SECONDS = 30.0


def configure_desktop_environment() -> Path:
    """Point at bundled assets and a writable user-data directory.

    Must run before the desktop server starts. Sets up desktop-local user
    data and loads nearby `.env` files. No longer configures the removed
    local FastAPI backend.
    """
    data_dir = ensure_user_data_dir()
    root = bundle_root()
    exe_dir = executable_dir()

    load_dotenv(exe_dir / ".env", override=False)
    if exe_dir != root:
        load_dotenv(root / ".env", override=False)

    return data_dir


def pick_port(preferred: int = DEFAULT_PORT, host: str = "0.0.0.0") -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind((host, preferred))
            return preferred
        except OSError:
            sock.bind((host, 0))
            return int(sock.getsockname()[1])


def lan_ipv4_addresses() -> list[str]:
    """Best-effort LAN addresses a phone on the same Wi-Fi can reach."""
    ips: list[str] = []
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        try:
            sock.connect(("8.8.8.8", 80))
            ip = sock.getsockname()[0]
            if ip and not ip.startswith("127.") and ip not in ips:
                ips.append(ip)
        except OSError:
            pass
    return ips


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
