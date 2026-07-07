"""SQLite storage: one file data/vault.db holds everything internal (R2).

The Markdown vault stays clean; transcripts, embeddings, queue, categories
and logs all live here.
"""

import json
import sqlite3
from datetime import datetime, timezone

from .config import DATA_DIR, DB_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS items (
    id INTEGER PRIMARY KEY,
    title TEXT NOT NULL,
    normalized_url TEXT UNIQUE,
    original_url TEXT,
    platform TEXT,
    content_type TEXT,
    category_id INTEGER REFERENCES categories(id) ON DELETE SET NULL,
    short_description TEXT,
    main_points TEXT DEFAULT '[]',
    tags TEXT DEFAULT '[]',
    action_items TEXT DEFAULT '[]',
    entities TEXT DEFAULT '{}',
    status TEXT NOT NULL DEFAULT 'active',
    extraction_status TEXT NOT NULL DEFAULT 'full',
    markdown_path TEXT,
    duplicate_check_summary TEXT DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS raw_extractions (
    item_id INTEGER PRIMARY KEY REFERENCES items(id) ON DELETE CASCADE,
    transcript TEXT DEFAULT '',
    page_text TEXT DEFAULT '',
    caption TEXT DEFAULT '',
    description TEXT DEFAULT '',
    metadata TEXT DEFAULT '{}',
    extraction_log TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS embeddings (
    item_id INTEGER PRIMARY KEY REFERENCES items(id) ON DELETE CASCADE,
    vector BLOB NOT NULL
);

-- path is NOT unique: an archived category keeps its path under Archive/, and
-- a fresh active category with the same path can grow again (R33/R34 + R53).
CREATE TABLE IF NOT EXISTS categories (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    parent_id INTEGER REFERENCES categories(id) ON DELETE CASCADE,
    path TEXT NOT NULL,
    note_count INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'active'
);
CREATE INDEX IF NOT EXISTS idx_categories_path ON categories(path);

CREATE TABLE IF NOT EXISTS pending_subcategories (
    id INTEGER PRIMARY KEY,
    proposed_path TEXT NOT NULL UNIQUE,
    item_ids TEXT NOT NULL DEFAULT '[]'
);

CREATE TABLE IF NOT EXISTS queue (
    id INTEGER PRIMARY KEY,
    url TEXT,
    shared_text TEXT,
    source TEXT NOT NULL DEFAULT 'dashboard',
    state TEXT NOT NULL DEFAULT 'queued',
    stage TEXT,
    error TEXT,
    result_kind TEXT,
    item_id INTEGER,
    log TEXT,
    kv_key TEXT UNIQUE,
    user_notes TEXT,
    manual_text TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS tags (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS item_tags (
    item_id INTEGER NOT NULL REFERENCES items(id) ON DELETE CASCADE,
    tag_id INTEGER NOT NULL REFERENCES tags(id) ON DELETE CASCADE,
    PRIMARY KEY (item_id, tag_id)
);

CREATE TABLE IF NOT EXISTS duplicate_links (
    id INTEGER PRIMARY KEY,
    item_id INTEGER NOT NULL REFERENCES items(id) ON DELETE CASCADE,
    merged_source_url TEXT NOT NULL,
    normalized_url TEXT,
    merged_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS related_links (
    item_id INTEGER NOT NULL REFERENCES items(id) ON DELETE CASCADE,
    related_item_id INTEGER NOT NULL REFERENCES items(id) ON DELETE CASCADE,
    similarity REAL,
    PRIMARY KEY (item_id, related_item_id)
);

-- Outbox for pushing card summaries to the phone (cloud copy). One row per
-- item; 'put' uploads the current card, 'delete' removes it from the cloud.
-- Rows are drained by the background worker and survive being offline.
CREATE TABLE IF NOT EXISTS cloud_pending (
    item_id INTEGER PRIMARY KEY,
    action TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE VIRTUAL TABLE IF NOT EXISTS fts_cards USING fts5(
    item_id UNINDEXED, title, short_description, main_points, tags
);

CREATE VIRTUAL TABLE IF NOT EXISTS fts_raw USING fts5(
    item_id UNINDEXED, content
);

CREATE INDEX IF NOT EXISTS idx_items_category ON items(category_id);
CREATE INDEX IF NOT EXISTS idx_items_status ON items(status);
CREATE INDEX IF NOT EXISTS idx_queue_state ON queue(state);
CREATE INDEX IF NOT EXISTS idx_dupes_norm ON duplicate_links(normalized_url);
"""


def now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def today() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def get_conn() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db() -> None:
    with get_conn() as conn:
        conn.executescript(SCHEMA)


def j(value) -> str:
    return json.dumps(value, ensure_ascii=False)


def unj(text, default):
    if not text:
        return default
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return default


# ---------------------------------------------------------------- FTS sync

def fts_update_item(conn: sqlite3.Connection, item_id: int) -> None:
    """(Re)index one item's card fields and raw material for keyword search (R45)."""
    conn.execute("DELETE FROM fts_cards WHERE item_id = ?", (item_id,))
    conn.execute("DELETE FROM fts_raw WHERE item_id = ?", (item_id,))
    item = conn.execute("SELECT * FROM items WHERE id = ?", (item_id,)).fetchone()
    if not item:
        return
    points = unj(item["main_points"], [])
    points_text = " ".join(
        f"{p.get('name', '')} {p.get('description', '')}" for p in points
    )
    tags = " ".join(unj(item["tags"], []))
    conn.execute(
        "INSERT INTO fts_cards (item_id, title, short_description, main_points, tags) "
        "VALUES (?, ?, ?, ?, ?)",
        (item_id, item["title"] or "", item["short_description"] or "", points_text, tags),
    )
    raw = conn.execute(
        "SELECT * FROM raw_extractions WHERE item_id = ?", (item_id,)
    ).fetchone()
    if raw:
        content = " ".join(
            filter(None, [raw["transcript"], raw["page_text"], raw["caption"], raw["description"]])
        )
        if content.strip():
            conn.execute(
                "INSERT INTO fts_raw (item_id, content) VALUES (?, ?)",
                (item_id, content),
            )


def set_item_tags(conn: sqlite3.Connection, item_id: int, tag_names: list[str]) -> None:
    conn.execute("DELETE FROM item_tags WHERE item_id = ?", (item_id,))
    for name in dict.fromkeys(t.strip().lower() for t in tag_names if t.strip()):
        conn.execute("INSERT OR IGNORE INTO tags (name) VALUES (?)", (name,))
        tag_id = conn.execute("SELECT id FROM tags WHERE name = ?", (name,)).fetchone()["id"]
        conn.execute(
            "INSERT OR IGNORE INTO item_tags (item_id, tag_id) VALUES (?, ?)",
            (item_id, tag_id),
        )


def refresh_note_counts(conn: sqlite3.Connection) -> None:
    conn.execute(
        "UPDATE categories SET note_count = "
        "(SELECT COUNT(*) FROM items WHERE items.category_id = categories.id)"
    )
