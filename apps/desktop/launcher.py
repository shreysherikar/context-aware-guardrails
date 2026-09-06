"""Launch ContextGuard as a native desktop window around the local API."""

from __future__ import annotations

import logging
import multiprocessing
import sys
import threading
import webbrowser
from pathlib import Path

from apps.desktop.paths import bundle_root, ensure_user_data_dir
from apps.desktop.runtime import (
    configure_desktop_environment,
    lan_ipv4_addresses,
    pick_port,
    wait_for_health,
)

logger = logging.getLogger(__name__)


def _attach_stdio(log_path: Path) -> None:
    """Windowed PyInstaller builds set sys.stdout/stderr to None."""
    if sys.stdout is not None and sys.stderr is not None:
        return
    handle = log_path.open("a", encoding="utf-8")
    if sys.stdout is None:
        sys.stdout = handle
    if sys.stderr is None:
        sys.stderr = handle


def _fatal(message: str) -> None:
    logger.error(message)
    if sys.platform == "win32":
        import ctypes

        ctypes.windll.user32.MessageBoxW(0, message, "ContextGuard", 0x10)


def _run_server(port: int) -> None:
    try:
        import uvicorn

        from apps.api.main import app

        config = uvicorn.Config(
            app,
            host="0.0.0.0",
            port=port,
            log_level="warning",
            log_config=None,
        )
        server = uvicorn.Server(config)
        server.install_signal_handlers = False
        server.run()
    except Exception:
        logger.exception("API server thread crashed")
        raise


def _ui_index() -> Path:
    return bundle_root() / "apps" / "web" / "index.html"


def _configure_logging(data_dir: Path) -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[
            logging.FileHandler(data_dir / "contextguard.log", encoding="utf-8"),
            logging.StreamHandler(),
        ],
        force=True,
    )


def main() -> int:
    if sys.platform == "win32":
        multiprocessing.freeze_support()

    try:
        data_dir = ensure_user_data_dir()
        _attach_stdio(data_dir / "contextguard.log")
        data_dir = configure_desktop_environment()
        _configure_logging(data_dir)
        logger.info("User data directory: %s", data_dir)
        logger.info("Bundle root: %s", bundle_root())
        ui = _ui_index()
        if not ui.is_file():
            raise FileNotFoundError(f"UI assets missing at {ui}")

        port = pick_port()
        thread = threading.Thread(
            target=_run_server, args=(port,), daemon=True, name="contextguard-api"
        )
        thread.start()
        wait_for_health(port)
        url = f"http://127.0.0.1:{port}/"
        phone_urls = [f"http://{ip}:{port}/" for ip in lan_ipv4_addresses()]
        logger.info("ContextGuard is running at %s", url)
        for phone in phone_urls:
            logger.info("Phone URL: %s", phone)

        try:
            import webview
        except ImportError:
            logger.warning("pywebview is not installed; opening the system browser")
            webbrowser.open(url)
            thread.join()
            return 0

        title = "ContextGuard"
        if phone_urls:
            title = f"ContextGuard — phone {phone_urls[0]}"
        webview.create_window(
            title,
            url,
            width=1280,
            height=840,
            min_size=(960, 640),
        )
        webview.start()
        return 0
    except Exception as exc:
        _fatal(
            "ContextGuard failed to start.\n\n"
            f"{exc}\n\nSee contextguard.log in your user data folder."
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
