"""Push read-only card summaries to the phone via the Cloudflare Worker.

The phone can then browse the whole library even when the PC is off. Only the
card summary is uploaded (title, points, description, tags, category, source
link) — transcripts, page text and embeddings never leave the PC.

Changes are recorded in the `cloud_pending` outbox and drained by the
background worker, so nothing is lost when the cloud is unreachable.
"""

import requests

from . import db, urltools


def configured(cfg: dict) -> bool:
    return bool(cfg.get("inbox_url") and cfg.get("inbox_token"))


def _base(cfg: dict) -> str:
    return cfg["inbox_url"].rstrip("/")


class CloudError(Exception):
    pass


# --------------------------------------------------------------- outbox

def mark_dirty(conn, item_id: int, action: str = "put") -> None:
    """Queue an item for upload ('put') or removal ('delete'). A later action
    overrides an earlier one for the same item (delete wins over put)."""
    conn.execute(
        "INSERT INTO cloud_pending (item_id, action, created_at) VALUES (?, ?, ?) "
        "ON CONFLICT(item_id) DO UPDATE SET action = excluded.action, "
        "created_at = excluded.created_at",
        (item_id, action, db.now()),
    )


def mark_all_dirty(conn) -> int:
    """Queue every existing card for upload (used by 'Sync all to phone')."""
    n = 0
    for row in conn.execute("SELECT id FROM items"):
        mark_dirty(conn, row["id"], "put")
        n += 1
    return n


# --------------------------------------------------------------- payload

def build_card_payload(conn, item_id: int) -> dict | None:
    item = conn.execute("SELECT * FROM items WHERE id = ?", (item_id,)).fetchone()
    if not item:
        return None
    cat = conn.execute(
        "SELECT path FROM categories WHERE id = ?", (item["category_id"],)
    ).fetchone()
    additional = [
        {"url": r["merged_source_url"],
         "label": urltools.source_label(None, r["merged_source_url"])}
        for r in conn.execute(
            "SELECT merged_source_url FROM duplicate_links WHERE item_id = ? "
            "ORDER BY merged_at", (item_id,),
        )
    ]
    related = [
        r["title"]
        for r in conn.execute(
            "SELECT i.title FROM related_links rl "
            "JOIN items i ON i.id = CASE WHEN rl.item_id = :id "
            "THEN rl.related_item_id ELSE rl.item_id END "
            "WHERE rl.item_id = :id OR rl.related_item_id = :id "
            "ORDER BY rl.similarity DESC", {"id": item_id},
        )
    ]
    return {
        "id": item["id"],
        "title": item["title"],
        "category_path": cat["path"] if cat else "",
        "platform": item["platform"] or "manual",
        "source_url": item["original_url"] or "",
        "source_label": urltools.source_label(item["platform"], item["original_url"]),
        "date_saved": (item["created_at"] or "")[:10],
        "tags": db.unj(item["tags"], []),
        "content_type": item["content_type"] or "other",
        "status": item["status"] or "active",
        "extraction_status": item["extraction_status"] or "full",
        "short_description": item["short_description"] or "",
        "main_points": db.unj(item["main_points"], []),
        "additional_sources": additional,
        "related": related,
        "updated_at": item["updated_at"] or item["created_at"] or "",
    }


# --------------------------------------------------------------- events (R60)

# States the phone's "Recently added" tab shows (mirrors PC's home page).
TERMINAL_EVENT_STATES = ("saved", "merged", "needs_input", "failed")


def build_event_payload(conn, queue_id: int) -> dict | None:
    """Recent-activity event for the phone's "Recently added" tab (R60/R61).

    Carries the same information the PC home page shows: the state badge, the
    linked card (when one exists), and a plain-language reason for
    failed/needs_input items (no retry/paste form on phone, R62)."""
    row = conn.execute(
        "SELECT q.*, i.title AS item_title, c.path AS item_category "
        "FROM queue q LEFT JOIN items i ON i.id = q.item_id "
        "LEFT JOIN categories c ON c.id = i.category_id WHERE q.id = ?",
        (queue_id,),
    ).fetchone()
    if not row:
        return None
    return {
        "id": row["id"],
        "state": row["state"],
        "result_kind": row["result_kind"] or "",
        "item_id": row["item_id"],
        "item_title": row["item_title"] or "",
        "item_category": row["item_category"] or "",
        "source": row["source"] or "",
        "reason": row["error"] or "",
        "preview": (row["url"] or (row["shared_text"] or "")[:120] or ""),
        "updated_at": row["updated_at"] or row["created_at"] or "",
    }


def publish_event(cfg: dict, conn, queue_id: int) -> None:
    """Best-effort push of one terminal queue event to the phone cloud. Never
    raises — recent-activity is non-critical and must not stall the pipeline or
    flip a just-saved item to 'failed'."""
    try:
        if not configured(cfg):
            return
        payload = build_event_payload(conn, queue_id)
        if not payload:
            return
        requests.post(
            f"{_base(cfg)}/events/put", params={"token": cfg["inbox_token"]},
            json=payload, timeout=10,
        )
    except Exception:  # noqa: BLE001 — the event feed is strictly best-effort
        pass  # the card outbox still syncs independently


# --------------------------------------------------------------- HTTP

def _put(cfg: dict, card: dict) -> None:
    r = requests.post(
        f"{_base(cfg)}/cards/put", params={"token": cfg["inbox_token"]},
        json=card, timeout=15,
    )
    if r.status_code == 401:
        raise CloudError("The cloud rejected the secret token — check Settings.")
    r.raise_for_status()


def _delete(cfg: dict, ids: list[int]) -> None:
    r = requests.post(
        f"{_base(cfg)}/cards/delete", params={"token": cfg["inbox_token"]},
        json={"ids": ids}, timeout=15,
    )
    if r.status_code == 401:
        raise CloudError("The cloud rejected the secret token — check Settings.")
    r.raise_for_status()


def _cloud_ids(cfg: dict) -> set[int]:
    r = requests.get(
        f"{_base(cfg)}/cards", params={"token": cfg["inbox_token"], "ids": "1"},
        timeout=15,
    )
    r.raise_for_status()
    return {int(c["id"]) for c in r.json().get("cards", [])}


# --------------------------------------------------------------- drain

def drain_pending(cfg: dict, limit: int = 50) -> tuple[bool, str]:
    """Send queued card changes to the cloud. Returns (ok, message). Leaves
    rows in the outbox for the next attempt when the cloud is unreachable."""
    if not configured(cfg):
        return None, "The phone cloud is not set up yet (see Settings)."
    with db.get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM cloud_pending ORDER BY created_at LIMIT ?", (limit,)
        ).fetchall()
        if not rows:
            return True, "Phone library up to date."
        sent = 0
        try:
            for row in rows:
                if row["action"] == "delete":
                    _delete(cfg, [row["item_id"]])
                else:
                    card = build_card_payload(conn, row["item_id"])
                    if card is None:
                        # item vanished before upload → treat as delete
                        _delete(cfg, [row["item_id"]])
                    else:
                        _put(cfg, card)
                conn.execute(
                    "DELETE FROM cloud_pending WHERE item_id = ?", (row["item_id"],)
                )
                conn.commit()
                sent += 1
        except CloudError as e:
            return False, str(e)
        except requests.RequestException as e:
            return False, (f"The phone cloud could not be reached "
                           f"({e.__class__.__name__}). Will retry.")
    return True, f"Synced {sent} change(s) to the phone."


def sync_all(cfg: dict) -> tuple[bool, str]:
    """Full reconcile for the Settings button: upload every current card and
    delete cloud cards whose notes no longer exist on the PC."""
    if not configured(cfg):
        return False, "Set the phone inbox URL and token in Settings first."
    with db.get_conn() as conn:
        n = mark_all_dirty(conn)
        conn.commit()
    ok, msg = drain_pending(cfg, limit=100000)
    if not ok:
        return ok, msg
    try:
        cloud = _cloud_ids(cfg)
        with db.get_conn() as conn:
            live = {r["id"] for r in conn.execute("SELECT id FROM items")}
        stragglers = list(cloud - live)
        if stragglers:
            _delete(cfg, stragglers)
    except (requests.RequestException, CloudError) as e:
        return False, f"Uploaded notes, but could not reconcile deletions: {e}"
    return True, f"Phone library synced — {n} note(s) available on your phone."


def test(cfg: dict) -> tuple[bool, str]:
    if not configured(cfg):
        return False, "The phone cloud is not set up yet (see Settings)."
    try:
        r = requests.get(
            f"{_base(cfg)}/cards", params={"token": cfg["inbox_token"], "ids": "1"},
            timeout=15,
        )
        if r.status_code == 401:
            return False, "The cloud rejected the secret token — check Settings."
        r.raise_for_status()
        return True, f"Phone cloud reachable — {len(r.json().get('cards', []))} note(s) published."
    except requests.RequestException as e:
        return False, f"The phone cloud could not be reached ({e.__class__.__name__})."
