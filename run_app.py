"""Start Notulus: server + dashboard in the default browser (R1).

Double-clicked via 'Start Knowledge Vault.bat'. If an up-to-date copy of the
app is already running, it just opens the dashboard instead of failing. If the
running copy is OUTDATED (its code stamp doesn't match the code on disk), it
is stopped and replaced, so restarting the .bat always serves current code —
interrupted queue items recover via R57.
"""

import json
import socket
import subprocess
import sys
import threading
import time
import urllib.request
import webbrowser

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from app.config import load_config
from app import db, version


def port_in_use(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(("127.0.0.1", port)) == 0


def server_is_current(port: int) -> bool:
    """True only if the server on the port reports the same code stamp as the
    files on disk. Old builds (no /api/code-stamp) and foreign servers fail."""
    try:
        with urllib.request.urlopen(
            f"http://127.0.0.1:{port}/api/code-stamp", timeout=3
        ) as resp:
            served = json.load(resp).get("stamp")
    except Exception:
        return False
    return served == version.code_stamp()


def stop_stale_server(port: int) -> bool:
    """Kill the Python process listening on the port (an outdated app build).
    Refuses to touch anything that isn't a python process."""
    out = subprocess.run(
        ["netstat", "-ano"], capture_output=True, text=True
    ).stdout
    pids = set()
    for line in out.splitlines():
        parts = line.split()
        # e.g.  TCP  127.0.0.1:8765  0.0.0.0:0  LISTENING  25188
        if (
            len(parts) >= 5
            and parts[0] == "TCP"
            and parts[1].endswith(f":{port}")
            and parts[3] == "LISTENING"
        ):
            pids.add(parts[4])
    for pid in pids:
        owner = subprocess.run(
            ["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
            capture_output=True, text=True,
        ).stdout
        if "python" not in owner.lower():
            print(f"Port {port} is used by another program (PID {pid}) — leaving it alone.")
            return False
        subprocess.run(["taskkill", "/PID", pid, "/F"], capture_output=True)
    for _ in range(20):
        if not port_in_use(port):
            return True
        time.sleep(0.5)
    return False


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
        if server_is_current(port):
            print(f"Notulus is already running — opening {url}")
            webbrowser.open(url)
            return
        print("An outdated Notulus server is running — restarting it...")
        if not stop_stale_server(port):
            print(f"Could not free port {port}. Close the old app window (or")
            print("python.exe in Task Manager), then run this again.")
            sys.exit(1)
    db.init_db()
    threading.Thread(target=open_browser_when_ready, args=(url, port), daemon=True).start()
    import uvicorn
    print(f"Starting Notulus at {url} — keep this window open.")
    print("Close this window (or press Ctrl+C) to stop the app.")
    uvicorn.run("app.web:app", host="127.0.0.1", port=port, log_level="warning")


if __name__ == "__main__":
    main()
