"""Resolve bundled assets vs writable user-data paths for the desktop app."""

from __future__ import annotations

import os
import secrets
import sys
from pathlib import Path

APP_NAME = "ContextGuard"


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def bundle_root() -> Path:
    """Directory that contains `policies/`, `evidence/`, and `apps/web`."""
    if is_frozen():
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parents[2]


def executable_dir() -> Path:
    """Directory of the `.exe` (frozen) or the repository root (source)."""
    if is_frozen():
        return Path(sys.executable).resolve().parent
    return bundle_root()


def user_data_dir() -> Path:
    local = os.environ.get("LOCALAPPDATA") or os.environ.get("XDG_DATA_HOME")
    if local:
        return Path(local) / APP_NAME
    return Path.home() / ".contextguard"


def ensure_user_data_dir() -> Path:
    path = user_data_dir()
    path.mkdir(parents=True, exist_ok=True)
    return path


def persist_jwt_secret(path: Path) -> str:
    if path.exists():
        value = path.read_text(encoding="utf-8").strip()
        if value:
            return value
    value = secrets.token_urlsafe(32)
    path.write_text(value, encoding="utf-8")
    return value
