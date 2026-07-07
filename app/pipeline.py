"""The processing pipeline for one queue item (R6):

queue item -> fetch/extract -> transcribe if needed -> LLM analysis ->
duplicate check -> categorize -> Markdown note + DB rows -> Recently added.

Every stage updates queue.state/stage so the dashboard shows truthful
progress. The Markdown write is the last step so a killed run never leaves a
half-written note (R57); if the DB row exists but the file is missing after a
crash, the file is re-rendered instead of duplicated.
"""

import traceback
from pathlib import Path

from . import (analysis, categories, cloudsync, db, dedupe, extraction, notes,
               ollama_client)
from .config import load_config, vault_path
from .urltools import extract_first_url, normalize_url


def _set_queue(conn, queue_id: int, **fields) -> None:
    fields["updated_at"] = db.now()
    cols = ", ".join(f"{k} = ?" for k in fields)
    conn.execute(f"UPDATE queue SET {cols} WHERE id = ?", (*fields.values(), queue_id))
    conn.commit()


def enqueue(conn, url: str | None, shared_text: str | None, source: str,
            user_notes: str | None = None, kv_key: str | None = None) -> int | None:
    """Durably add one capture to the queue. Returns queue id (None if the
    kv_key was already enqueued — safe re-pull, R11)."""
    import sqlite3

    ts = db.now()
    try:
        cur = conn.execute(
            "INSERT INTO queue (url, shared_text, source, user_notes, kv_key, "
            "state, created_at, updated_at) VALUES (?, ?, ?, ?, ?, 'queued', ?, ?)",
            (url, shared_text, source, user_notes, kv_key, ts, ts),
        )
    except sqlite3.IntegrityError:
        return None
    conn.commit()
    return cur.lastrowid


def resolve_input(queue_row) -> tuple[str | None, str]:
    """R14/R21 auto-detect: URL when one is present, otherwise pasted text.

    Phone shares often carry the link inside the text field (Instagram does
    this), so the URL is pulled out of the text for those. Dashboard-pasted
    raw text that merely contains a link stays text."""
    url = (queue_row["url"] or "").strip()
    text = (queue_row["shared_text"] or "").strip()
    if not url and queue_row["source"] == "phone":
        url = extract_first_url(text) or ""
    return (url or None), text


def process_queue_item(queue_id: int, on_stage=None) -> None:
    """Run one item through the whole pipeline. Always leaves the queue row in
    a terminal or needs_input state (R56)."""
    cfg = load_config()
    vault = vault_path(cfg)
    conn = db.get_conn()
    try:
        row = conn.execute("SELECT * FROM queue WHERE id = ?", (queue_id,)).fetchone()
        if not row:
            return
        _set_queue(conn, queue_id, state="processing", stage="starting", error=None)

        def stage(name: str):
            _set_queue(conn, queue_id, stage=name)
            if on_stage:
                on_stage(name)

        url, text = resolve_input(row)
        norm = normalize_url(url) if url else None

        # ---- URL dedupe before any processing (R40)
        if norm:
            existing = dedupe.find_saved_url(conn, norm)
            if existing:
                md = existing["markdown_path"]
                if md and not Path(md).exists():
                    notes.write_item_note(conn, existing["id"], vault)  # heal after crash (R57)
                _set_queue(conn, queue_id, state="saved", stage=None,
                           result_kind="already_saved", item_id=existing["id"])
                return

        # ---- extraction (R17–R22)
        manual_text = (row["manual_text"] or "").strip()
        if manual_text:
            result = extraction.extract_from_text(manual_text)
            if url:
                result.platform = extraction.detect_platform(url)[0]
            result.extraction_status = "manual"
            result.add_log("User supplied the text manually after an extraction failure.")
        elif url:
            stage("downloading")
            result = extraction.extract_from_url(url, cfg, on_stage=stage)
        else:
            if not text:
                _set_queue(conn, queue_id, state="failed", stage=None,
                           error="This share contained no link and no text.")
                return
            result = extraction.extract_from_text(text)

        if result.error:
            _set_queue(conn, queue_id, state="needs_input", stage=None, error=result.error)
            return
        if not result.has_content():
            _set_queue(conn, queue_id, state="needs_input", stage=None,
                       error="Nothing readable was found in this item. "
                             "Paste its caption or text below to save it.")
            return

        # ---- LLM analysis (R25–R29)
        stage("analyzing")
        try:
            card = analysis.analyze(
                cfg, result.source_dict(), categories.tree_text(conn),
                user_notes=row["user_notes"] or "",
            )
        except analysis.AnalysisError as e:
            result.add_log("RAW LLM OUTPUT:\n" + (e.raw_output or "")[-4000:])
            _set_queue(conn, queue_id, state="failed", stage=None,
                       log="\n".join(result.log),
                       error=str(e) + " Press Retry to try again.")
            return

        vector = ollama_client.embed(cfg, analysis.embedding_text(card))

        # ---- semantic dedupe (R41)
        sims = dedupe.similarities(conn, vector)
        if sims and sims[0][1] >= float(cfg["duplicate_threshold"]):
            existing_id = sims[0][0]
            dedupe.merge_into_existing(
                conn, vault, existing_id, url or "", norm or "", card["tags"]
            )
            cloudsync.mark_dirty(conn, existing_id, "put")  # cloud copy updated
            conn.commit()
            _set_queue(conn, queue_id, state="merged", stage=None,
                       result_kind="merged", item_id=existing_id)
            return

        # ---- save: DB rows first, Markdown file last (R57)
        stage("saving")
        notes.ensure_vault(vault)
        cat_row, remaining, canonical = categories.resolve_immediate(
            conn, vault, card["category_path"]
        )
        ts = db.now()
        cur = conn.execute(
            "INSERT INTO items (title, normalized_url, original_url, platform, "
            "content_type, category_id, short_description, main_points, tags, "
            "action_items, entities, status, extraction_status, "
            "duplicate_check_summary, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'active', ?, ?, ?, ?)",
            (
                card["title"], norm, url, result.platform, card["content_type"],
                cat_row["id"], card["short_description"], db.j(card["main_points"]),
                db.j(card["tags"]), db.j(card["action_items"]), db.j(card["entities"]),
                result.extraction_status, card["duplicate_check_summary"], ts, ts,
            ),
        )
        item_id = cur.lastrowid
        conn.execute(
            "INSERT INTO raw_extractions (item_id, transcript, page_text, caption, "
            "description, metadata, extraction_log) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                item_id, result.transcript, result.page_text, result.caption,
                result.description, db.j(result.metadata), "\n".join(result.log),
            ),
        )
        conn.execute(
            "INSERT INTO embeddings (item_id, vector) VALUES (?, ?)",
            (item_id, vector.tobytes()),
        )
        db.set_item_tags(conn, item_id, card["tags"])

        # ---- categorize: birth threshold for sub-levels (R33/R34)
        final_cat_id = cat_row["id"]
        if remaining:
            created = categories.register_proposal(conn, cfg, vault, canonical, item_id)
            if created:
                final_cat_id = created["id"]
        conn.execute("UPDATE items SET category_id = ? WHERE id = ?", (final_cat_id, item_id))

        # ---- filename decided before related links so reciprocal wikilinks
        # can point at the new note (R37/R42)
        final_cat = categories.get_category(conn, final_cat_id)
        folder = notes.category_disk_dir(vault, final_cat["path"], archived=False)
        filename = notes.unique_filename(conn, card["suggested_filename"], vault)
        md_path = folder / f"{filename}.md"
        conn.execute("UPDATE items SET markdown_path = ? WHERE id = ?", (str(md_path), item_id))

        # ---- related notes, bidirectional (R42/R44)
        threshold = float(cfg["related_threshold"])
        related = [(i, s) for i, s in sims if s >= threshold][:3]
        if related:
            dedupe.link_related(conn, vault, item_id, related)

        db.fts_update_item(conn, item_id)
        db.refresh_note_counts(conn)
        conn.commit()

        notes.write_item_note(conn, item_id, vault)
        notes.regenerate_hubs(conn, vault, {final_cat_id})
        cloudsync.mark_dirty(conn, item_id, "put")  # publish to the phone
        conn.commit()
        _set_queue(conn, queue_id, state="saved", stage=None,
                   result_kind="new", item_id=item_id)
    except notes.VaultSafetyError as e:
        _set_queue(conn, queue_id, state="failed", stage=None, error=str(e))
    except ollama_client.OllamaError as e:
        # Ollama died mid-call: keep the item queued; the worker pauses (R31).
        _set_queue(conn, queue_id, state="queued", stage=None, error=None)
        raise
    except Exception as e:  # noqa: BLE001 — R56: nothing silently disappears
        _set_queue(conn, queue_id, state="failed", stage=None,
                   error=f"Unexpected error: {e}")
        traceback.print_exc()
    finally:
        conn.close()
