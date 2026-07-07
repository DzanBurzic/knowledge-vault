"""Shared pytest fixtures.

Every test runs against an isolated temp SQLite DB and temp vault folder —
never the user's real data/vault.db or the real Knowledge Vault folder. This
is enforced by monkeypatching the paths the app modules read, not left to
convention alone.
"""
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import db as db_module
from app import lifecycle, notes


@pytest.fixture
def db_conn(tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    monkeypatch.setattr(db_module, "DATA_DIR", data_dir)
    monkeypatch.setattr(db_module, "DB_PATH", data_dir / "vault.db")
    db_module.init_db()
    conn = db_module.get_conn()
    yield conn
    conn.close()


@pytest.fixture
def vault_dir(tmp_path):
    vault = tmp_path / "Knowledge Vault"
    notes.ensure_vault(vault)
    return vault


@pytest.fixture
def patch_lifecycle_vault(vault_dir, monkeypatch):
    """lifecycle.py's top-level functions read the vault path from config;
    point them at the isolated test vault instead of the real config.json."""
    monkeypatch.setattr(lifecycle, "vault_path", lambda cfg=None: vault_dir)
    return vault_dir


@pytest.fixture
def make_item(db_conn):
    """Factory for inserting a minimal item row (+ optional embedding) without
    needing Ollama/yt-dlp — mirrors the columns pipeline.py itself writes."""
    def _make(title, category_id=None, tags=None, main_points=None,
              status="active", markdown_path=None, vector=None,
              platform="manual", content_type="other"):
        ts = db_module.now()
        cur = db_conn.execute(
            "INSERT INTO items (title, normalized_url, original_url, platform, "
            "content_type, category_id, short_description, main_points, tags, "
            "status, extraction_status, markdown_path, duplicate_check_summary, "
            "created_at, updated_at) "
            "VALUES (?, NULL, NULL, ?, ?, ?, ?, ?, ?, ?, 'manual', ?, '', ?, ?)",
            (title, platform, content_type, category_id, f"About {title}.",
             db_module.j(main_points or []), db_module.j(tags or []), status,
             markdown_path, ts, ts),
        )
        item_id = cur.lastrowid
        if vector is not None:
            vec = np.asarray(vector, dtype=np.float32)
            db_conn.execute(
                "INSERT INTO embeddings (item_id, vector) VALUES (?, ?)",
                (item_id, vec.tobytes()),
            )
        db_module.set_item_tags(db_conn, item_id, tags or [])
        db_module.fts_update_item(db_conn, item_id)
        db_conn.commit()
        return item_id
    return _make
