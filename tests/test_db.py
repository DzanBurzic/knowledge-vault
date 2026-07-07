from app import db


def test_init_db_creates_expected_tables(db_conn):
    names = {r["name"] for r in db_conn.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table'"
    )}
    for expected in ("items", "raw_extractions", "embeddings", "categories",
                     "pending_subcategories", "queue", "tags", "item_tags",
                     "duplicate_links", "related_links", "cloud_pending"):
        assert expected in names


def test_j_and_unj_roundtrip():
    data = {"a": 1, "b": ["x", "y"]}
    assert db.unj(db.j(data), None) == data


def test_unj_returns_default_on_bad_json():
    assert db.unj("not json", ["fallback"]) == ["fallback"]


def test_unj_returns_default_on_empty():
    assert db.unj(None, []) == []
    assert db.unj("", []) == []


def test_set_item_tags_dedupes_and_lowercases(db_conn):
    ts = db.now()
    cur = db_conn.execute(
        "INSERT INTO items (title, status, extraction_status, main_points, tags, "
        "created_at, updated_at) VALUES ('t', 'active', 'manual', '[]', '[]', ?, ?)",
        (ts, ts),
    )
    item_id = cur.lastrowid
    db.set_item_tags(db_conn, item_id, ["Travel", "travel", " Japan "])
    rows = db_conn.execute(
        "SELECT t.name FROM item_tags it JOIN tags t ON t.id = it.tag_id "
        "WHERE it.item_id = ? ORDER BY t.name", (item_id,)
    ).fetchall()
    assert [r["name"] for r in rows] == ["japan", "travel"]


def test_fts_update_item_indexes_card_fields(db_conn):
    ts = db.now()
    cur = db_conn.execute(
        "INSERT INTO items (title, short_description, status, extraction_status, "
        "main_points, tags, created_at, updated_at) "
        "VALUES ('Budget Travel', 'Cheap places to go', 'active', 'manual', '[]', '[]', ?, ?)",
        (ts, ts),
    )
    item_id = cur.lastrowid
    db.fts_update_item(db_conn, item_id)
    hit = db_conn.execute(
        "SELECT item_id FROM fts_cards WHERE fts_cards MATCH 'budget'"
    ).fetchone()
    assert hit and hit["item_id"] == item_id


def test_refresh_note_counts(db_conn):
    cur = db_conn.execute(
        "INSERT INTO categories (name, parent_id, path) VALUES ('Travel', NULL, 'Travel')"
    )
    cat_id = cur.lastrowid
    ts = db.now()
    for i in range(3):
        db_conn.execute(
            "INSERT INTO items (title, category_id, status, extraction_status, "
            "main_points, tags, created_at, updated_at) "
            "VALUES (?, ?, 'active', 'manual', '[]', '[]', ?, ?)",
            (f"note {i}", cat_id, ts, ts),
        )
    db.refresh_note_counts(db_conn)
    count = db_conn.execute(
        "SELECT note_count FROM categories WHERE id = ?", (cat_id,)
    ).fetchone()
    assert count["note_count"] == 3
