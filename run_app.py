"""Start Knowledge Vault: server + dashboard in the default browser (R1).

Double-clicked via 'Start Knowledge Vault.bat'. If the app is already
running, it just opens the dashboard instead of failing.
"""

import socket
import sys
import threading
import time
import webbrowser

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from app.config import load_config
from app import db


def port_in_use(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(("127.0.0.1", port)) == 0


def open_browser_when_ready(url: str, port: int) -> None:
    for _ in range(120):
        if port_in_use(port):
            webbrowser.open(url)
            return
        time.sleep(0.5)


def main() -> None:
    cfg = load_config()
    port = int(cfg.get("port", 8765))
    url = f"http://localhost:{port}"
    if port_in_use(port):
        print(f"Knowledge Vault seems to be running already — opening {url}")
        webbrowser.open(url)
        return
    db.init_db()
    threading.Thread(target=open_browser_when_ready, args=(url, port), daemon=True).start()
    import uvicorn
    print(f"Starting Knowledge Vault at {url} — keep this window open.")
    print("Close this window (or press Ctrl+C) to stop the app.")
    uvicorn.run("app.web:app", host="127.0.0.1", port=port, log_level="warning")


if __name__ == "__main__":
    main()
