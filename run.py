"""Arca — desktop app launcher.

Starts the local Flask server and opens the UI in a native PyWebView
window when possible, falling back to the default browser.
"""

from __future__ import annotations

import os
import socket
import sys
import threading
import time
import webbrowser

from server.app import create_app

DEFAULT_HOST = os.environ.get("ARCA_HOST", "127.0.0.1")
DEFAULT_PORT = int(os.environ.get("ARCA_PORT", "8765"))


def _wait_for_server(port: int, timeout: float = 8.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                return True
        except OSError:
            time.sleep(0.1)
    return False


def _serve(port: int, host: str = DEFAULT_HOST) -> None:
    create_app().run(
        host=host, port=port, threaded=True, use_reloader=False, debug=False
    )


def _hold() -> None:
    """Keep the process alive in browser mode until Ctrl+C."""
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass


class _Api:
    """Bridge exposed to the frontend as ``window.pywebview.api``."""

    def __init__(self):
        self._window = None

    def set_window(self, window):
        self._window = window

    def open_external(self, url: str) -> None:
        webbrowser.open(url)


def main() -> None:
    port = DEFAULT_PORT
    host = DEFAULT_HOST
    url = f"http://{host}:{port}"

    thread = threading.Thread(target=_serve, kwargs={"port": port, "host": host}, daemon=True)
    thread.start()
    if not _wait_for_server(port):
        print(f"[arca] Server did not start on {url}", file=sys.stderr)
        sys.exit(1)
    print(f"[arca] Server ready at {url}")

    if os.environ.get("ARCA_BROWSER") == "1":
        webbrowser.open(url)
        _hold()
        return

    try:
        import webview

        api = _Api()
        window = webview.create_window(
            "Arca",
            url,
            width=1280,
            height=820,
            min_size=(900, 620),
            background_color="#0a0a0c",
            js_api=api,
        )
        api.set_window(window)
        webview.start(debug=False)
    except Exception as exc:  # noqa: BLE001 - fall back to the browser
        print(f"[arca] Webview unavailable ({exc}); opening browser instead.")
        webbrowser.open(url)
        _hold()


if __name__ == "__main__":
    main()
