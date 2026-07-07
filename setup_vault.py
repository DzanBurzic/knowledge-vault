"""One-time Knowledge Vault setup (R4, R5).

Run via 'Setup Knowledge Vault.bat'. Checks/installs prerequisites, pulls the
Ollama models, creates the vault folder + database, prints the phone (Cloudflare)
guide, and optionally registers auto-start at Windows logon.
"""

import json
import os
import secrets
import shutil
import subprocess
import sys
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(APP_DIR))

# Windows consoles may default to cp1252, which can't print arrows/checkmarks.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

OK = "  [OK] "
WARN = "  [!]  "

WINGET_LINKS = Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "WinGet" / "Links"
OLLAMA_EXE = Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Ollama" / "ollama.exe"
if WINGET_LINKS.exists():
    os.environ["PATH"] = f"{WINGET_LINKS}{os.pathsep}{os.environ.get('PATH', '')}"
if OLLAMA_EXE.parent.exists():
    os.environ["PATH"] = f"{OLLAMA_EXE.parent}{os.pathsep}{os.environ.get('PATH', '')}"


def step(title: str):
    print(f"\n=== {title} ===")


def install_requirements():
    step("Step 1: Python packages")
    result = subprocess.run(
        [sys.executable, "-m", "pip", "install", "--user", "-r",
         str(APP_DIR / "requirements.txt"), "--quiet"],
        capture_output=True, text=True,
    )
    if result.returncode == 0:
        print(OK + "All Python packages are installed.")
    else:
        print(WARN + "Some packages failed to install:")
        print((result.stderr or "")[-800:])


def check_ollama(cfg: dict) -> bool:
    step("Step 2: Ollama (the local AI)")
    from app import ollama_client

    exe = shutil.which("ollama")
    if not exe and not ollama_client.is_up(cfg):
        print(WARN + "Ollama is not installed.")
        print("        1. Open https://ollama.com/download in your browser")
        print("        2. Click 'Download for Windows' and run the installer")
        print("        3. When it finishes, run this setup again")
        return False
    if not ollama_client.is_up(cfg):
        print("  Ollama is installed but not running — starting it...")
        try:
            subprocess.Popen([exe or str(OLLAMA_EXE), "serve"],
                             creationflags=subprocess.CREATE_NO_WINDOW)
            import time
            for _ in range(20):
                time.sleep(1)
                if ollama_client.is_up(cfg):
                    break
        except OSError as e:
            print(WARN + f"Could not start Ollama automatically ({e}). "
                  "Start the Ollama app from the Start menu, then run setup again.")
            return False
    if not ollama_client.is_up(cfg):
        print(WARN + "Ollama did not respond. Start it from the Start menu and rerun setup.")
        return False
    print(OK + "Ollama is running.")
    for model in (cfg["chat_model"], cfg["embedding_model"]):
        if ollama_client.has_model(cfg, model):
            print(OK + f"Model '{model}' is already downloaded.")
        else:
            print(f"  Downloading model '{model}' (this can take a while)...")
            r = subprocess.run(["ollama", "pull", model])
            if r.returncode == 0:
                print(OK + f"Model '{model}' downloaded.")
            else:
                print(WARN + f"Could not download '{model}'. "
                      f"Run 'ollama pull {model}' manually later.")
    return True


def check_tools():
    step("Step 3: Download & transcription tools")
    for tool in ("yt-dlp", "ffmpeg"):
        if shutil.which(tool):
            print(OK + f"{tool} found.")
        else:
            print(WARN + f"{tool} not found. Install it with: winget install {'yt-dlp.yt-dlp' if tool == 'yt-dlp' else 'Gyan.FFmpeg'}")
    try:
        import faster_whisper  # noqa: F401
        print(OK + "faster-whisper (transcription) is installed.")
    except ImportError:
        print(WARN + "faster-whisper missing — it was in requirements; rerun this setup.")


def create_vault_and_db(cfg: dict) -> bool:
    step("Step 4: Vault folder & database")
    from app import db
    from app.notes import ensure_vault, VaultSafetyError

    vault = Path(cfg["vault_path"])
    try:
        ensure_vault(vault)  # refuses foreign folders (R55)
    except VaultSafetyError as e:
        print(WARN + str(e))
        print("        Change 'vault_path' in config.json (or Settings) and rerun setup.")
        return False
    print(OK + f"Vault folder ready: {vault}")
    db.init_db()
    print(OK + f"Database ready: {APP_DIR / 'data' / 'vault.db'}")
    return True


def ensure_token(cfg: dict) -> dict:
    from app.config import save_config, load_config
    if not cfg.get("inbox_token"):
        save_config({"inbox_token": secrets.token_urlsafe(24)})
        cfg = load_config()
        print(OK + "Generated a new secret token for the phone inbox.")
    return cfg


PHONE_GUIDE_MANUAL = """
=== Step 5: Phone inbox (Cloudflare) — manual setup, ~10 minutes ===

Automatic setup didn't finish (see the warning above), so here's the manual
walkthrough. Everything below is free.

PART A — Create the cloud inbox (on this PC, in your browser)
  1. Go to https://dash.cloudflare.com and sign up (free) or log in.
  2. In the left menu click  "Workers & Pages".
  3. Click the blue  "Create"  button, then under Workers click  "Create Worker".
  4. Give it a name you like, e.g.  knowledge-vault-inbox  → click "Deploy".
  5. Click  "Edit code". Delete everything in the editor, then open this file
     on your PC, copy ALL of it, and paste it into the editor:
        {worker_file}
  6. Click "Deploy" (top right), then click the back arrow to leave the editor.

PART B — Create the storage (KV)
  1. In the left menu click  "Storage & Databases"  →  "KV".
  2. Click  "Create a namespace", name it  INBOX , click "Add".
  3. Go back to  Workers & Pages  → click your worker → "Settings" tab →
     "Bindings" → "Add" → choose "KV namespace".
        Variable name:  INBOX
        KV namespace:   INBOX
     Click "Deploy" / "Save".

PART C — Add the secret token
  1. Still in your worker's  Settings → "Variables and Secrets" → "Add".
        Type:  Secret
        Name:  TOKEN
        Value: {token}
     Click "Deploy" / "Save".
  2. On the PC dashboard's Settings page, fill in:
        Phone inbox URL:  https://<your-worker-name>.<your-subdomain>.workers.dev
        (it is shown on the worker's page, ends in .workers.dev)
        Inbox secret token: (already filled in — leave as is)
     Click "Save settings", then "Test inbox" — it should say reachable.
{phone_part}"""

PHONE_GUIDE_AUTO = """
=== Step 5: Phone inbox (Cloudflare) — done automatically ===

Your phone inbox is live at:
    {inbox_url}

Just the phone side is left:
{phone_part}"""

PHONE_PART = """
PART D — Install the app on your phone
  1. On your Android phone, open Chrome and go to:
        {inbox_url}/?token={token}
     (type it once — the page remembers the token afterwards)
  2. Tap the Chrome menu (three dots, top right) →  "Add to Home screen"
     → "Install". Confirm.
  3. Done! Now open Instagram, pick any reel → Share → find
     "Knowledge Vault" in the share sheet → tap it once → "Saved ✓".
     The card appears on the PC dashboard next time the app runs.

PART E — View your notes on the phone
  The phone app has three tabs at the bottom: "Library", "Graph" and "Add".
  - Library shows every note your PC has finished, newest first. You can search,
    filter by category, and tap a note to read its main points and open the
    source link. Archived/done notes are hidden until you tick "Show archived".
  - Graph shows your whole vault as a constellation — notes as stars, categories
    as the bright anchor stars, links as the lines between them. Drag to move,
    pinch to zoom, tap a star to open it. Same view as the PC's Graph page.
  - Notes are published to your phone automatically as the PC creates them.
    If the library ever looks out of date, open the PC dashboard's Settings and
    press "Sync all notes to phone".
  Note: this means your note summaries (title, points, description, tags, link)
  are stored in your Cloudflare cloud so the phone can show them even when the PC
  is off. Your transcripts and raw text never leave the PC.

  ALREADY SET THIS UP BEFORE? Rerunning setup redeploys the worker code (so it
  picks up updates) but reuses your existing storage and token — nothing else
  needs redoing.
"""


def try_automated_cloud_setup(cfg: dict) -> tuple[bool, dict]:
    """Deploy the phone-inbox Worker via `wrangler` with zero dashboard
    clicking. Never raises — any failure falls back to the manual guide so
    setup always completes."""
    step("Step 5a: Phone inbox — trying automatic setup")
    if cfg.get("inbox_url"):
        print(OK + f"Already deployed: {cfg['inbox_url']}")
        print("        (redeploying to pick up any worker.js updates...)")
    import cloudflare_deploy
    try:
        url = cloudflare_deploy.run(cfg["inbox_token"])
    except cloudflare_deploy.DeployError as e:
        print(WARN + f"Automatic setup didn't finish: {e}")
        return False, cfg
    except Exception as e:  # noqa: BLE001 — must never crash the rest of setup
        print(WARN + f"Automatic setup hit an unexpected error: {e}")
        return False, cfg
    from app.config import load_config, save_config
    save_config({"inbox_url": url})
    print(OK + f"Phone inbox deployed automatically: {url}")
    return True, load_config()


def print_phone_guide(cfg: dict, auto_ok: bool):
    phone_part = PHONE_PART.format(inbox_url=cfg.get("inbox_url", ""), token=cfg["inbox_token"])
    if auto_ok:
        guide = PHONE_GUIDE_AUTO.format(inbox_url=cfg["inbox_url"], phone_part=phone_part)
    else:
        guide = PHONE_GUIDE_MANUAL.format(
            worker_file=APP_DIR / "cloudflare" / "worker.js",
            token=cfg["inbox_token"], phone_part=phone_part,
        )
    print(guide)
    guide_path = APP_DIR / "PHONE-SETUP.md"
    guide_path.write_text(guide, encoding="utf-8")
    print(f"(The guide above was also saved to {guide_path} so you can read it later.)")


def offer_autostart():
    step("Step 6: Start automatically with Windows? (R5)")
    answer = input("  Start Knowledge Vault automatically when you log in? [y/n] ").strip().lower()
    if answer not in ("y", "yes"):
        print("  Skipped. You can rerun setup anytime to enable it.")
        return
    bat = APP_DIR / "Start Knowledge Vault.bat"
    result = subprocess.run(
        ["schtasks", "/Create", "/F", "/SC", "ONLOGON",
         "/TN", "Knowledge Vault", "/TR", f'"{bat}"'],
        capture_output=True, text=True,
    )
    if result.returncode == 0:
        print(OK + "Task Scheduler entry 'Knowledge Vault' created.")
    else:
        print(WARN + "Could not create the scheduled task "
              f"({(result.stderr or result.stdout).strip()[:200]}).")
        print("        Try right-clicking 'Setup Knowledge Vault.bat' → Run as administrator.")


def main():
    print("Knowledge Vault — one-time setup")
    print("=" * 40)
    install_requirements()
    from app.config import load_config, save_config
    if not (APP_DIR / "config.json").exists():
        save_config({})  # write defaults
    cfg = load_config()
    ollama_ok = check_ollama(cfg)
    check_tools()
    vault_ok = create_vault_and_db(cfg)
    cfg = ensure_token(cfg)
    auto_ok, cfg = try_automated_cloud_setup(cfg)
    print_phone_guide(cfg, auto_ok)
    offer_autostart()
    print("\n" + "=" * 40)
    if ollama_ok and vault_ok:
        print("Setup complete! Double-click 'Start Knowledge Vault.bat' to begin.")
    else:
        print("Setup finished with warnings above — fix them and run setup again.")


if __name__ == "__main__":
    main()
