"""Automates deploying the phone-capture Cloudflare Worker via `wrangler`.

Collapses the manual dashboard walkthrough (create Worker, paste code, create
KV, bind it, set a secret) into: install Node.js if missing, log into your
own free Cloudflare account once, then wait. Every step is idempotent-ish —
re-running after a partial success reuses what's already there instead of
creating duplicates.

Never raises to the caller except DeployError, which carries a plain-language
reason. setup_vault.py catches it and falls back to the manual walkthrough,
so a failure here never blocks the rest of setup.
"""

import datetime
import os
import re
import shutil
import subprocess
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent
CLOUDFLARE_DIR = APP_DIR / "cloudflare"
WRANGLER_TOML = CLOUDFLARE_DIR / "wrangler.toml"
WORKER_NAME = "knowledge-vault-inbox"

WINGET_LINKS = Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "WinGet" / "Links"
if WINGET_LINKS.exists():
    os.environ["PATH"] = f"{WINGET_LINKS}{os.pathsep}{os.environ.get('PATH', '')}"

URL_RE = re.compile(r"https://[\w.-]+\.workers\.dev")
KV_ID_RE = re.compile(r'id\s*=\s*"([0-9a-f]{32})"')


class DeployError(Exception):
    """Carries a plain-language reason; caller falls back to manual setup."""


def _run(cmd: list[str], **kw) -> subprocess.CompletedProcess:
    timeout = kw.pop("timeout", 120)
    return subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=timeout, **kw)


def _npx(args: list[str], **kw) -> subprocess.CompletedProcess:
    return _run(["npx", "--yes", "wrangler@latest", *args], **kw)


# --------------------------------------------------------------- prereqs

def ensure_node() -> bool:
    """Install Node.js (needed to run `wrangler`) via winget if missing."""
    if shutil.which("npm"):
        return True
    print("  Installing Node.js (needed once, to deploy your phone inbox)...")
    try:
        subprocess.run(
            ["winget", "install", "--id", "OpenJS.NodeJS.LTS", "-e", "--silent",
             "--accept-package-agreements", "--accept-source-agreements"],
            timeout=300,
        )
    except (subprocess.TimeoutExpired, OSError):
        return False
    # winget's PATH change may not be visible in this process yet.
    node_dir = Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "nodejs"
    if node_dir.exists():
        os.environ["PATH"] = f"{node_dir}{os.pathsep}{os.environ.get('PATH', '')}"
    return shutil.which("npm") is not None


def already_logged_in() -> bool:
    try:
        r = _npx(["whoami"], timeout=30)
    except (subprocess.TimeoutExpired, OSError):
        return False
    return r.returncode == 0 and "you are not authenticated" not in (r.stdout + r.stderr).lower()


def login() -> None:
    print()
    print("  Opening your browser to log into (or sign up for) a free")
    print("  Cloudflare account. This is a one-time step so your phone can")
    print("  share links to this PC even while it's off. Close the browser")
    print("  tab once it says you're logged in.")
    print()
    try:
        r = subprocess.run(["npx", "--yes", "wrangler@latest", "login"], timeout=300)
    except subprocess.TimeoutExpired as e:
        raise DeployError("The Cloudflare login page timed out.") from e
    except OSError as e:
        raise DeployError(f"Could not start the login flow ({e}).") from e
    if r.returncode != 0:
        raise DeployError("Cloudflare login did not complete.")


# --------------------------------------------------------------- deploy steps

def write_wrangler_toml() -> None:
    """Minimal config; `kv namespace create --update-config` fills in the KV
    binding below it. Re-writing an existing file is safe — it only touches
    these three lines, never the [[kv_namespaces]] block wrangler adds."""
    today = datetime.date.today().isoformat()
    existing = WRANGLER_TOML.read_text(encoding="utf-8") if WRANGLER_TOML.exists() else ""
    kv_block = ""
    if "[[kv_namespaces]]" in existing:
        kv_block = "[[kv_namespaces]]" + existing.split("[[kv_namespaces]]", 1)[1].rstrip("\n")
    CLOUDFLARE_DIR.mkdir(parents=True, exist_ok=True)
    WRANGLER_TOML.write_text(
        f'name = "{WORKER_NAME}"\n'
        f'main = "worker.js"\n'
        f'compatibility_date = "{today}"\n'
        + (f"\n{kv_block}\n" if kv_block else ""),
        encoding="utf-8",
    )


def ensure_kv_namespace() -> None:
    """Create the INBOX KV namespace and bind it, unless already bound."""
    if WRANGLER_TOML.exists() and "[[kv_namespaces]]" in WRANGLER_TOML.read_text(encoding="utf-8"):
        return  # already provisioned by a previous run
    r = _npx(
        ["kv", "namespace", "create", "INBOX", "--binding", "INBOX", "--update-config"],
        cwd=CLOUDFLARE_DIR,
    )
    if r.returncode != 0:
        raise DeployError(f"Could not create the phone inbox storage: {(r.stderr or r.stdout)[-400:]}")
    # Defensive fallback: if --update-config didn't write the binding for any
    # reason, extract the id from the command's own output and append it.
    text = WRANGLER_TOML.read_text(encoding="utf-8") if WRANGLER_TOML.exists() else ""
    if "[[kv_namespaces]]" not in text:
        m = KV_ID_RE.search(r.stdout) or KV_ID_RE.search(r.stderr)
        if not m:
            raise DeployError("Storage was created, but its id could not be read from the output.")
        with WRANGLER_TOML.open("a", encoding="utf-8") as f:
            f.write(f'\n[[kv_namespaces]]\nbinding = "INBOX"\nid = "{m.group(1)}"\n')


def set_token_secret(token: str) -> None:
    try:
        r = subprocess.run(
            ["npx", "--yes", "wrangler@latest", "secret", "put", "TOKEN"],
            cwd=CLOUDFLARE_DIR, input=token, capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=60,
        )
    except (subprocess.TimeoutExpired, OSError) as e:
        raise DeployError(f"Could not set the secret token ({e}).") from e
    if r.returncode != 0:
        raise DeployError(f"Could not set the secret token: {(r.stderr or r.stdout)[-400:]}")


def deploy() -> str:
    r = _npx(["deploy"], cwd=CLOUDFLARE_DIR, timeout=180)
    if r.returncode != 0:
        raise DeployError(f"Deploy failed: {(r.stderr or r.stdout)[-400:]}")
    m = URL_RE.search(r.stdout) or URL_RE.search(r.stderr)
    if not m:
        raise DeployError("Deployed, but the worker's URL could not be read from the output. "
                          "Check the Cloudflare dashboard for it.")
    return m.group(0)


# --------------------------------------------------------------------- entry

def run(token: str) -> str:
    """Full automated flow. Returns the deployed inbox URL, or raises
    DeployError with a plain-language reason the caller shows the user."""
    if not ensure_node():
        raise DeployError("Node.js could not be installed automatically.")
    if not already_logged_in():
        login()
    write_wrangler_toml()
    ensure_kv_namespace()
    set_token_secret(token)
    return deploy()
