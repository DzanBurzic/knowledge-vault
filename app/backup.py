"""Local backups of vault.db (search index, embeddings, category tree, queue).

The Markdown notes already live safely in the vault folder; this covers the
state that only exists in SQLite. Backups are plain copies of the DB file
under data/backups/, checkpointed first so WAL contents are included.
"""

import shutil
import sqlite3
from datetime import datetime
from pathlib import Path

from .config import DATA_DIR, DB_PATH

BACKUP_DIR = DATA_DIR / "backups"
KEEP = 10


def create_backup(reason: str = "manual") -> Path:
    """Checkpoint the WAL and copy vault.db to a timestamped backup file."""
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    if DB_PATH.exists():
        conn = sqlite3.connect(DB_PATH)
        try:
            conn.execute("PRAGMA wal_checkpoint(FULL)")
        finally:
            conn.close()
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    safe_reason = "".join(c for c in reason if c.isalnum()) or "manual"
    dest = BACKUP_DIR / f"vault-{stamp}-{safe_reason}.db"
    shutil.copy2(DB_PATH, dest)
    prune_backups()
    return dest


def prune_backups(keep: int = KEEP) -> None:
    files = sorted(BACKUP_DIR.glob("vault-*.db"), key=lambda p: p.stat().st_mtime, reverse=True)
    for old in files[keep:]:
        old.unlink(missing_ok=True)


def list_backups() -> list[dict]:
    if not BACKUP_DIR.exists():
        return []
    files = sorted(BACKUP_DIR.glob("vault-*.db"), key=lambda p: p.stat().st_mtime, reverse=True)
    return [
        {
            "name": f.name,
            "size_kb": round(f.stat().st_size / 1024, 1),
            "created": datetime.fromtimestamp(f.stat().st_mtime).strftime("%Y-%m-%d %H:%M"),
        }
        for f in files
    ]
