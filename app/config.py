"""Configuration: one config.json in the app folder (R3)."""

import json
import threading
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent
CONFIG_PATH = APP_DIR / "config.json"
DATA_DIR = APP_DIR / "data"
DB_PATH = DATA_DIR / "vault.db"
TMP_DIR = DATA_DIR / "tmp"

VAULT_MARKER = ".knowledge-vault"

DEFAULTS = {
    # Sibling of the app folder by default (e.g. "...\Knowledge Vault" next to
    # "...\knowledge-vault"), so this works on any PC/username, not just this one.
    "vault_path": str(APP_DIR.parent / "Knowledge Vault"),
    "ollama_url": "http://localhost:11434",
    "chat_model": "qwen3:8b",
    "embedding_model": "nomic-embed-text",
    "whisper_model": "small",
    "inbox_url": "",
    "inbox_token": "",
    "poll_interval": 120,
    "duplicate_threshold": 0.88,
    "related_threshold": 0.75,
    "subcategory_birth_threshold": 3,
    "port": 8765,
}

_lock = threading.Lock()


def load_config() -> dict:
    cfg = dict(DEFAULTS)
    if CONFIG_PATH.exists():
        try:
            cfg.update(json.loads(CONFIG_PATH.read_text(encoding="utf-8")))
        except (json.JSONDecodeError, OSError):
            pass
    return cfg


def save_config(cfg: dict) -> None:
    with _lock:
        merged = load_config()
        merged.update(cfg)
        CONFIG_PATH.write_text(
            json.dumps(merged, indent=2, ensure_ascii=False), encoding="utf-8"
        )


def vault_path(cfg: dict | None = None) -> Path:
    cfg = cfg or load_config()
    return Path(cfg["vault_path"])
