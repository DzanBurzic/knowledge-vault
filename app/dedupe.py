"""Duplicate detection: URL dedupe (R40) and semantic dedupe/related (R41–R44)."""

import numpy as np

from . import db, notes


def find_saved_url(conn, normalized_url: str):
    """R40: a URL already saved (as a card or merged into one) is not reprocessed."""
    row = conn.execute(
        "SELECT * FROM items WHERE normalized_url = ?", (normalized_url,)
    ).fetchone()
    if row:
        return row
    dup = conn.execute(
        "SELECT item_id FROM duplicate_links WHERE normalized_url = ?", (normalized_url,)
    ).fetchone()
    if dup:
        return conn.execute("SELECT * FROM items WHERE id = ?", (dup["item_id"],)).fetchone()
    return None


def _all_embeddings(conn, exclude_item_id=None):
    rows = conn.execute(
        "SELECT item_id, vector FROM embeddings WHERE (? IS NULL OR item_id != ?)",
        (exclude_item_id, exclude_item_id),
    ).fetchall()
    ids = [r["item_id"] for r in rows]
    if not ids:
        return [], None
    matrix = np.vstack([np.frombuffer(r["vector"], dtype=np.float32) for r in rows])
    return ids, matrix


def similarities(conn, vector: np.ndarray, exclude_item_id=None) -> list[tuple[int, float]]:
    """Cosine similarity against every stored card embedding, best first (R41).
    Vectors are stored unit-normalized, so this is a dot product."""
    ids, matrix = _all_embeddings(conn, exclude_item_id)
    if not ids:
        return []
    sims = matrix @ vector.astype(np.float32)
    order = np.argsort(-sims)
    return [(ids[i], float(sims[i])) for i in order]


def merge_into_existing(conn, vault, existing_item_id: int, original_url: str,
                        normalized_url: str, new_tags: list[str]) -> None:
    """R41/R43: existing note gains the new link under Additional sources plus
    genuinely new tags; the merge is recorded in duplicate_links."""
    existing = conn.execute(
        "SELECT * FROM items WHERE id = ?", (existing_item_id,)
    ).fetchone()
    if not existing:
        return
    if original_url:
        already = conn.execute(
            "SELECT 1 FROM duplicate_links WHERE item_id = ? AND normalized_url = ?",
            (existing_item_id, normalized_url),
        ).fetchone()
        if not already and normalized_url != existing["normalized_url"]:
            conn.execute(
                "INSERT INTO duplicate_links (item_id, merged_source_url, normalized_url, merged_at) "
                "VALUES (?, ?, ?, ?)",
                (existing_item_id, original_url, normalized_url, db.now()),
            )
    old_tags = db.unj(existing["tags"], [])
    merged_tags = old_tags + [t for t in new_tags if t not in old_tags]
    conn.execute(
        "UPDATE items SET tags = ?, updated_at = ? WHERE id = ?",
        (db.j(merged_tags), db.now(), existing_item_id),
    )
    db.set_item_tags(conn, existing_item_id, merged_tags)
    db.fts_update_item(conn, existing_item_id)
    if existing["markdown_path"]:
        notes.write_item_note(conn, existing_item_id, vault)


MAYBE_RELATED_FLOOR = 0.60


def maybe_related(conn, item_id: int, cfg: dict, limit: int = 5) -> list[dict]:
    """Notes similar enough to be worth a look but below the auto-link
    threshold — surfaced for the user to confirm manually, never stored
    automatically (that's what keeps ## Related Notes free of false positives)."""
    row = conn.execute("SELECT vector FROM embeddings WHERE item_id = ?", (item_id,)).fetchone()
    if not row:
        return []
    vector = np.frombuffer(row["vector"], dtype=np.float32)
    ceiling = float(cfg.get("related_threshold", 0.75))
    if ceiling <= MAYBE_RELATED_FLOOR:
        return []
    already = {
        r["other"] for r in conn.execute(
            "SELECT CASE WHEN item_id = :id THEN related_item_id ELSE item_id END AS other "
            "FROM related_links WHERE item_id = :id OR related_item_id = :id", {"id": item_id},
        )
    }
    out = []
    for other_id, sim in similarities(conn, vector, exclude_item_id=item_id):
        if sim < MAYBE_RELATED_FLOOR:
            break  # similarities() is sorted descending — nothing further qualifies
        if sim >= ceiling or other_id in already:
            continue
        other = conn.execute("SELECT title FROM items WHERE id = ?", (other_id,)).fetchone()
        if other:
            out.append({"id": other_id, "title": other["title"], "similarity": round(sim, 3)})
        if len(out) >= limit:
            break
    return out


def pairwise_similarity(conn, item_a: int, item_b: int) -> float | None:
    """Cosine similarity between two stored embeddings, or None if either is missing."""
    rows = {
        r["item_id"]: np.frombuffer(r["vector"], dtype=np.float32)
        for r in conn.execute(
            "SELECT item_id, vector FROM embeddings WHERE item_id IN (?, ?)", (item_a, item_b)
        )
    }
    if item_a not in rows or item_b not in rows:
        return None
    return float(rows[item_a] @ rows[item_b])


def link_related(conn, vault, item_id: int, related: list[tuple[int, float]]) -> None:
    """R42/R44: up to 3 bidirectional Related Notes wikilinks."""
    for other_id, sim in related[:3]:
        a, b = sorted((item_id, other_id))
        conn.execute(
            "INSERT OR IGNORE INTO related_links (item_id, related_item_id, similarity) "
            "VALUES (?, ?, ?)",
            (a, b, sim),
        )
    for other_id, _sim in related[:3]:
        other = conn.execute(
            "SELECT markdown_path FROM items WHERE id = ?", (other_id,)
        ).fetchone()
        if other and other["markdown_path"]:
            notes.write_item_note(conn, other_id, vault)  # bidirectional (R42)
