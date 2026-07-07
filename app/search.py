"""Search: keyword via SQLite FTS5, semantic via embeddings (R45–R49)."""

import re

from . import db, dedupe, ollama_client


def _filter_sql(filters: dict):
    """Shared WHERE clauses for search and filtered browse (R47, R49)."""
    clauses, params = [], []
    if not filters.get("include_done"):
        clauses.append("i.status = 'active'")
    if filters.get("platform"):
        clauses.append("i.platform = ?")
        params.append(filters["platform"])
    if filters.get("category_path"):
        clauses.append("(c.path = ? OR c.path LIKE ?)")
        params.append(filters["category_path"])
        params.append(filters["category_path"] + "/%")
    if filters.get("tag"):
        clauses.append(
            "EXISTS (SELECT 1 FROM item_tags it JOIN tags t ON t.id = it.tag_id "
            "WHERE it.item_id = i.id AND t.name = ?)"
        )
        params.append(filters["tag"].lower())
    if filters.get("date_from"):
        clauses.append("substr(i.created_at, 1, 10) >= ?")
        params.append(filters["date_from"])
    if filters.get("date_to"):
        clauses.append("substr(i.created_at, 1, 10) <= ?")
        params.append(filters["date_to"])
    return (" AND ".join(clauses) or "1=1"), params


BASE_SELECT = (
    "SELECT i.id, i.title, i.platform, i.short_description, i.tags, i.status, "
    "i.content_type, i.created_at, i.extraction_status, c.path AS category_path "
    "FROM items i LEFT JOIN categories c ON c.id = i.category_id "
)


def _row_to_result(row, matched_in_transcript=False, similarity=None) -> dict:
    return {
        "id": row["id"],
        "title": row["title"],
        "category_path": row["category_path"] or "",
        "platform": row["platform"],
        "date": (row["created_at"] or "")[:10],
        "short_description": row["short_description"],
        "tags": db.unj(row["tags"], []),
        "status": row["status"],
        "matched_in_transcript": matched_in_transcript,
        "similarity": similarity,
    }


def _fts_query(q: str) -> str:
    terms = [t for t in re.findall(r"\w+", q) if t]
    return " ".join(f'"{t}"' for t in terms)


def keyword_search(conn, q: str, filters: dict) -> list[dict]:
    """R45: FTS5 over card fields plus raw transcripts/page text; transcript
    hits rank below card hits and are labeled."""
    match = _fts_query(q)
    if not match:
        return filtered_browse(conn, filters)
    where, params = _filter_sql(filters)
    results, seen = [], set()

    card_hits = conn.execute(
        BASE_SELECT + "JOIN fts_cards f ON f.item_id = i.id "
        f"WHERE fts_cards MATCH ? AND {where} ORDER BY bm25(fts_cards)",
        (match, *params),
    ).fetchall()
    for row in card_hits:
        seen.add(row["id"])
        results.append(_row_to_result(row))

    raw_hits = conn.execute(
        BASE_SELECT + "JOIN fts_raw f ON f.item_id = i.id "
        f"WHERE fts_raw MATCH ? AND {where} ORDER BY bm25(fts_raw)",
        (match, *params),
    ).fetchall()
    for row in raw_hits:
        if row["id"] not in seen:
            results.append(_row_to_result(row, matched_in_transcript=True))
    return results


def semantic_search(conn, cfg: dict, q: str, filters: dict) -> list[dict]:
    """R46: embed the query, cosine-match all cards, top 10."""
    if not q.strip():
        return filtered_browse(conn, filters)
    vector = ollama_client.embed(cfg, q.strip())
    sims = dedupe.similarities(conn, vector)
    where, params = _filter_sql(filters)
    allowed = {
        r["id"] for r in conn.execute(BASE_SELECT + f"WHERE {where}", params)
    }
    results = []
    for item_id, sim in sims:
        if item_id not in allowed:
            continue
        row = conn.execute(BASE_SELECT + "WHERE i.id = ?", (item_id,)).fetchone()
        results.append(_row_to_result(row, similarity=round(sim, 3)))
        if len(results) >= 10:
            break
    return results


def filtered_browse(conn, filters: dict) -> list[dict]:
    """R49: empty query + filters = filtered browse."""
    where, params = _filter_sql(filters)
    rows = conn.execute(
        BASE_SELECT + f"WHERE {where} ORDER BY i.created_at DESC LIMIT 200", params
    ).fetchall()
    return [_row_to_result(r) for r in rows]
