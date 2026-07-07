from app import categories, cloudsync, db


def _add_queue(conn, **fields):
    ts = db.now()
    cols = "state, source, created_at, updated_at"
    vals = [fields.get("state", "saved"), fields.get("source", "phone"), ts, ts]
    extra = {k: v for k, v in fields.items() if k not in ("state", "source")}
    for k, v in extra.items():
        cols += f", {k}"
        vals.append(v)
    placeholders = ", ".join("?" for _ in vals)
    cur = conn.execute(
        f"INSERT INTO queue ({cols}) VALUES ({placeholders})", vals
    )
    conn.commit()
    return cur.lastrowid


def test_build_event_payload_links_saved_card(db_conn, vault_dir, make_item):
    """R60/R61: a saved event carries the card link, title and category."""
    cat = categories.create_chain(db_conn, vault_dir, ["Technology"])
    item_id = make_item("A note", category_id=cat["id"])
    qid = _add_queue(db_conn, state="saved", result_kind="new", item_id=item_id)

    payload = cloudsync.build_event_payload(db_conn, qid)
    assert payload["state"] == "saved"
    assert payload["item_id"] == item_id
    assert payload["item_title"] == "A note"
    assert payload["item_category"] == "Technology"
    assert payload["result_kind"] == "new"


def test_build_event_payload_failed_carries_reason(db_conn):
    """R62: failed events carry a plain-language reason, no card link."""
    qid = _add_queue(db_conn, state="failed", url="https://x.example/reel",
                     error="Something broke.")
    payload = cloudsync.build_event_payload(db_conn, qid)
    assert payload["state"] == "failed"
    assert payload["item_id"] is None
    assert payload["reason"] == "Something broke."
    assert payload["preview"] == "https://x.example/reel"


def test_build_event_payload_missing_queue_is_none(db_conn):
    assert cloudsync.build_event_payload(db_conn, 99999) is None
