"""FastAPI dashboard: Add, Recently added, Browse, Card, Search, Settings
(R14–R16, R39, R45–R54)."""

import os
import re
from contextlib import asynccontextmanager
from pathlib import Path

import markdown as md_lib
from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from . import (backup, categories, cloudsync, db, dedupe, inbox, lifecycle,
               notes, ollama_client, pipeline, search, urltools, version)
from .config import load_config, save_config, vault_path
from .worker import WORKER

TEMPLATES = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))
STATIC_DIR = Path(__file__).parent / "static"

LONE_URL_RE = re.compile(r"^https?://\S+$")


def static_version() -> str:
    """Cache-busting token for /static assets — the newest file mtime among
    them, so a browser tab left open across a CSS/JS edit fetches the fresh
    file on next navigation instead of serving a stale cached copy."""
    try:
        newest = max(p.stat().st_mtime for p in STATIC_DIR.glob("*") if p.is_file())
    except ValueError:
        newest = 0
    return str(int(newest))


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_db()
    try:
        backup.create_backup(reason="startup")  # cheap insurance; never blocks startup
    except OSError:
        pass
    WORKER.start()
    yield
    WORKER.stop()


# Frozen at import: the stamp of the code THIS process is actually running.
# run_app.py compares it against a fresh disk computation to spot stale servers.
CODE_STAMP = version.code_stamp()

app = FastAPI(title="Notulus", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=str(Path(__file__).parent / "static")), name="static")


def render(request: Request, template: str, **ctx) -> HTMLResponse:
    ctx.setdefault("cfg", load_config())
    ctx.setdefault("static_v", static_version())
    return TEMPLATES.TemplateResponse(request, template, ctx)


# Keyword → icon symbol id (defined as an <svg><symbol> sprite in base.html).
# Categories are freeform, so we match on words in the name and fall back to a
# generic folder. Order matters: the first group that matches wins. Short keys
# (ai, ml, ux) only match as whole words; longer keys match as substrings too.
_CATEGORY_ICONS = [
    ("ic-chip", ("ai", "ml", "tech", "technology", "coding", "code", "software",
                 "developer", "dev", "programming", "computer", "data", "llm",
                 "hardware", "gadget", "digital")),
    ("ic-briefcase", ("business", "finance", "money", "invest", "investing",
                      "market", "marketing", "startup", "entrepreneur", "sales",
                      "career", "work", "economics")),
    ("ic-coffee", ("food", "recipe", "recipes", "cook", "cooking", "meal",
                   "kitchen", "baking", "drink", "coffee", "restaurant", "diet")),
    ("ic-map", ("travel", "trip", "vacation", "flight", "hotel", "destination",
                "place", "places", "city", "country", "adventure")),
    ("ic-heart", ("health", "fitness", "workout", "gym", "exercise", "wellness",
                  "medical", "nutrition", "yoga", "running", "mental")),
    ("ic-flask", ("science", "physics", "chemistry", "biology", "space",
                  "astronomy", "math", "mathematics")),
    ("ic-book", ("history", "study", "studying", "education", "learning",
                 "research", "reading", "school", "language", "book", "books",
                 "philosophy", "writing")),
    ("ic-image", ("art", "design", "creative", "photography", "photo", "drawing",
                  "fashion", "architecture")),
    ("ic-music", ("music", "podcast", "audio", "song", "songs")),
    ("ic-play", ("video", "film", "movie", "movies", "media", "entertainment",
                 "youtube", "tv", "gaming", "game", "games")),
    ("ic-home", ("home", "diy", "house", "garden", "gardening", "interior")),
    ("ic-tag", ("shopping", "product", "products", "gear", "deals", "review",
                "reviews")),
]


def category_icon(name: str) -> str:
    """Pick an icon symbol id for a freeform category name."""
    low = (name or "").lower()
    words = set(re.split(r"[^a-z0-9]+", low))
    for icon, keys in _CATEGORY_ICONS:
        for key in keys:
            if key in words or (len(key) > 3 and key in low):
                return icon
    return "ic-folder"


def category_tree(conn, include_archived: bool = False):
    """Categories with their depth and a `total_note_count` (own notes plus
    every descendant's notes, R8). The existing `note_count` (direct-only)
    field is preserved for callers that rely on it."""
    where = "" if include_archived else "WHERE status = 'active'"
    rows = conn.execute(
        f"SELECT * FROM categories {where} ORDER BY path"
    ).fetchall()
    cats = [dict(r) | {"depth": r["path"].count("/")} for r in rows]
    for cat in cats:
        prefix = cat["path"] + "/"
        cat["total_note_count"] = sum(
            other["note_count"]
            for other in cats
            if other["path"] == cat["path"] or other["path"].startswith(prefix)
        )
    return cats


# ------------------------------------------------------------------- pages

@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    """Recently added: newest-first feed of the last 50 events (R50)."""
    with db.get_conn() as conn:
        rows = conn.execute(
            "SELECT q.*, i.title AS item_title, i.short_description AS item_desc, "
            "c.path AS item_category "
            "FROM queue q LEFT JOIN items i ON i.id = q.item_id "
            "LEFT JOIN categories c ON c.id = i.category_id "
            "ORDER BY q.updated_at DESC, q.id DESC LIMIT 50"
        ).fetchall()
        total_items = conn.execute("SELECT COUNT(*) AS n FROM items").fetchone()["n"]
    return render(request, "home.html", events=[dict(r) for r in rows],
                  total_items=total_items)


@app.get("/add", response_class=HTMLResponse)
def add_page(request: Request):
    return render(request, "add.html")


@app.get("/browse", response_class=HTMLResponse)
def browse(request: Request, include_archived: int = 0):
    """Category tree with note counts (R39)."""
    with db.get_conn() as conn:
        cats = category_tree(conn, include_archived=bool(include_archived))
        total_items = conn.execute("SELECT COUNT(*) AS n FROM items").fetchone()["n"]
    cats = [c | {"icon": category_icon(c["name"])} for c in cats]
    return render(request, "browse.html", cats=cats,
                  include_archived=include_archived, total_items=total_items)


@app.get("/category/{category_id}", response_class=HTMLResponse)
def category_page(request: Request, category_id: int, include_archived: int = 0):
    with db.get_conn() as conn:
        cat = categories.get_category(conn, category_id)
        if not cat:
            return RedirectResponse("/browse", status_code=303)
        status_clause = "" if include_archived else "AND i.status = 'active'"
        cards = conn.execute(
            f"SELECT i.*, c.path AS category_path FROM items i "
            f"LEFT JOIN categories c ON c.id = i.category_id "
            f"WHERE i.category_id = ? {status_clause} ORDER BY i.created_at DESC",
            (category_id,),
        ).fetchall()
        children = conn.execute(
            "SELECT * FROM categories WHERE parent_id = ? ORDER BY name", (category_id,)
        ).fetchall()
        note_count = len(lifecycle.subtree_item_ids(conn, category_id))
        total_items = conn.execute("SELECT COUNT(*) AS n FROM items").fetchone()["n"]
    return render(request, "category.html", cat=dict(cat),
                  cards=[dict(c) | {"tags_list": db.unj(c["tags"], []),
                                    "main_points_list": db.unj(c["main_points"], [])}
                         for c in cards],
                  children=[dict(c) | {"icon": category_icon(c["name"])} for c in children],
                  note_count=note_count, total_items=total_items,
                  include_archived=include_archived)


@app.get("/card/{item_id}", response_class=HTMLResponse)
def card_page(request: Request, item_id: int):
    """Card view: rendered note + edit controls + every contributing source (R39, R43, R51)."""
    cfg = load_config()
    with db.get_conn() as conn:
        item = conn.execute("SELECT * FROM items WHERE id = ?", (item_id,)).fetchone()
        if not item:
            return RedirectResponse("/", status_code=303)
        cat = categories.get_category(conn, item["category_id"]) if item["category_id"] else None
        dupes = conn.execute(
            "SELECT * FROM duplicate_links WHERE item_id = ? ORDER BY merged_at", (item_id,)
        ).fetchall()
        related = conn.execute(
            "SELECT i.id, i.title FROM related_links rl "
            "JOIN items i ON i.id = CASE WHEN rl.item_id = :id THEN rl.related_item_id ELSE rl.item_id END "
            "WHERE rl.item_id = :id OR rl.related_item_id = :id",
            {"id": item_id},
        ).fetchall()
        maybe = dedupe.maybe_related(conn, item_id, cfg)
        cats = category_tree(conn)
        raw = conn.execute(
            "SELECT extraction_log FROM raw_extractions WHERE item_id = ?", (item_id,)
        ).fetchone()
    body_html = ""
    if item["markdown_path"] and Path(item["markdown_path"]).exists():
        text = Path(item["markdown_path"]).read_text(encoding="utf-8")
        body = re.sub(r"^---\n.*?\n---\n", "", text, flags=re.DOTALL)
        body = re.sub(r"\[\[([^\]|]+)\|([^\]]+)\]\]", r"\2", body)
        body = re.sub(r"\[\[([^\]]+)\]\]", r"\1", body)
        body_html = md_lib.markdown(body)
    return render(request, "card.html", item=dict(item),
                  tags_list=db.unj(item["tags"], []),
                  main_points_list=db.unj(item["main_points"], []),
                  category=dict(cat) if cat else None,
                  source_label=urltools.source_label(item["platform"], item["original_url"]),
                  dupes=[dict(d) | {"source_label": urltools.source_label(None, d["merged_source_url"])}
                         for d in dupes],
                  related=[dict(r) for r in related],
                  maybe=maybe, cats=cats, body_html=body_html,
                  extraction_log=(raw["extraction_log"] if raw else ""))


@app.get("/search", response_class=HTMLResponse)
def search_page(request: Request):
    with db.get_conn() as conn:
        cats = category_tree(conn)
        platforms = [r["platform"] for r in conn.execute(
            "SELECT DISTINCT platform FROM items WHERE platform IS NOT NULL ORDER BY platform"
        )]
        tags = [r["name"] for r in conn.execute("SELECT name FROM tags ORDER BY name")]
    return render(request, "search.html", cats=cats, platforms=platforms, tags=tags)


@app.get("/graph", response_class=HTMLResponse)
def graph_page(request: Request):
    """Obsidian-style knowledge graph of notes, categories and their links."""
    return render(request, "graph.html")


@app.get("/settings", response_class=HTMLResponse)
def settings_page(request: Request):
    return render(request, "settings.html")


# --------------------------------------------------------------------- API

@app.post("/api/add")
def api_add(input: str = Form(...), notes_field: str = Form("")):
    """R14: one input, URL or raw text auto-detected; processed immediately."""
    trimmed = input.strip()
    if not trimmed:
        return JSONResponse({"ok": False, "error": "Paste a link or some text first."},
                            status_code=400)
    is_url = bool(LONE_URL_RE.match(trimmed))
    with db.get_conn() as conn:
        qid = pipeline.enqueue(
            conn,
            url=trimmed if is_url else None,
            shared_text=None if is_url else trimmed,
            source="dashboard",
            user_notes=notes_field.strip() or None,
        )
    WORKER.wake()
    return {"ok": True, "queue_id": qid, "detected": "url" if is_url else "text"}


@app.get("/api/code-stamp")
def api_code_stamp():
    return {"stamp": CODE_STAMP}


@app.get("/api/status")
def api_status():
    """R15: queue count, current item + stage, Ollama/inbox health, last poll."""
    st = WORKER.get_status()
    with db.get_conn() as conn:
        st["queue_count"] = conn.execute(
            "SELECT COUNT(*) AS n FROM queue WHERE state IN ('queued', 'processing')"
        ).fetchone()["n"]
    if not st["ollama_ok"] and not st["paused"]:
        ok, msg = ollama_client.status(load_config())
        st["ollama_ok"], st["ollama_message"] = ok, msg
    return st


@app.post("/api/queue/{queue_id}/retry")
def api_retry(queue_id: int):
    """R56: failed items always have a retry button."""
    with db.get_conn() as conn:
        conn.execute(
            "UPDATE queue SET state = 'queued', error = NULL, stage = NULL, "
            "updated_at = ? WHERE id = ?", (db.now(), queue_id),
        )
    WORKER.wake()
    return {"ok": True}


@app.post("/api/queue/{queue_id}/supply")
def api_supply(queue_id: int, text: str = Form(...)):
    """R22: user pastes caption/transcript for a needs_input item; the item
    then continues through the normal pipeline."""
    if not text.strip():
        return JSONResponse({"ok": False, "error": "Paste some text first."}, status_code=400)
    with db.get_conn() as conn:
        conn.execute(
            "UPDATE queue SET manual_text = ?, state = 'queued', error = NULL, "
            "updated_at = ? WHERE id = ?", (text.strip(), db.now(), queue_id),
        )
    WORKER.wake()
    return {"ok": True}


@app.post("/api/card/{item_id}/edit")
def api_edit(item_id: int, title: str = Form(...), category: str = Form(...),
             tags: str = Form(""), short_description: str = Form("")):
    tag_list = [t.strip().lower() for t in tags.split(",") if t.strip()]
    with db.get_conn() as conn:
        try:
            lifecycle.edit_card(conn, item_id, title, category, tag_list, short_description)
        except (ValueError, notes.VaultSafetyError) as e:
            return JSONResponse({"ok": False, "error": str(e)}, status_code=400)
    return {"ok": True}


@app.post("/api/card/{item_id}/link-related/{other_id}")
def api_link_related(item_id: int, other_id: int):
    """Promote a 'maybe related' suggestion into a real bidirectional link."""
    vault = vault_path()
    with db.get_conn() as conn:
        if not conn.execute("SELECT 1 FROM items WHERE id = ?", (other_id,)).fetchone():
            return JSONResponse({"ok": False, "error": "That note no longer exists."},
                                status_code=404)
        sim = dedupe.pairwise_similarity(conn, item_id, other_id) or 0.0
        a, b = sorted((item_id, other_id))
        conn.execute(
            "INSERT OR IGNORE INTO related_links (item_id, related_item_id, similarity) "
            "VALUES (?, ?, ?)", (a, b, sim),
        )
        notes.write_item_note(conn, item_id, vault)
        notes.write_item_note(conn, other_id, vault)
        cloudsync.mark_dirty(conn, item_id, "put")
        cloudsync.mark_dirty(conn, other_id, "put")
        conn.commit()
    return {"ok": True}


@app.post("/api/card/{item_id}/done")
def api_done(item_id: int):
    """R52: sets status done, updates frontmatter, hides from default views."""
    with db.get_conn() as conn:
        lifecycle.set_done(conn, item_id)
    return {"ok": True}


@app.post("/api/card/{item_id}/delete")
def api_delete_card(item_id: int):
    with db.get_conn() as conn:
        try:
            title = lifecycle.delete_note(conn, item_id)
        except (ValueError, notes.VaultSafetyError) as e:
            return JSONResponse({"ok": False, "error": str(e)}, status_code=400)
    return {"ok": True, "deleted": title}


def _parse_ids(item_ids: str) -> list[int]:
    out = []
    for part in item_ids.split(","):
        part = part.strip()
        if part.isdigit():
            out.append(int(part))
    return out


@app.post("/api/bulk/tag")
def api_bulk_tag(item_ids: str = Form(...), tags: str = Form(...)):
    """Add tag(s) to every selected note (additive — existing tags are kept)."""
    ids = _parse_ids(item_ids)
    new_tags = [t.strip().lower() for t in tags.split(",") if t.strip()]
    if not ids or not new_tags:
        return JSONResponse({"ok": False, "error": "Select at least one note and one tag."},
                            status_code=400)
    vault = vault_path()
    updated = 0
    with db.get_conn() as conn:
        for iid in ids:
            item = conn.execute("SELECT tags FROM items WHERE id = ?", (iid,)).fetchone()
            if not item:
                continue
            merged = db.unj(item["tags"], []) + [t for t in new_tags if t not in db.unj(item["tags"], [])]
            conn.execute("UPDATE items SET tags = ?, updated_at = ? WHERE id = ?",
                        (db.j(merged), db.now(), iid))
            db.set_item_tags(conn, iid, merged)
            db.fts_update_item(conn, iid)
            cloudsync.mark_dirty(conn, iid, "put")
            notes.write_item_note(conn, iid, vault)
            updated += 1
        conn.commit()
    return {"ok": True, "updated": updated}


@app.post("/api/bulk/move")
def api_bulk_move(item_ids: str = Form(...), category: str = Form(...)):
    """Move every selected note into a category (created immediately if new)."""
    ids = _parse_ids(item_ids)
    if not ids or not category.strip():
        return JSONResponse({"ok": False, "error": "Select at least one note and a category."},
                            status_code=400)
    vault = vault_path()
    with db.get_conn() as conn:
        try:
            leaf_id = categories.categorize_item(conn, {}, vault, None, category, force=True)
            categories.move_items(conn, vault, ids, leaf_id)  # marks each note cloud-dirty
            conn.commit()
        except notes.VaultSafetyError as e:
            return JSONResponse({"ok": False, "error": str(e)}, status_code=400)
    return {"ok": True, "moved": len(ids)}


@app.post("/api/bulk/delete")
def api_bulk_delete(item_ids: str = Form(...)):
    """Permanently delete every selected note."""
    ids = _parse_ids(item_ids)
    if not ids:
        return JSONResponse({"ok": False, "error": "Select at least one note."}, status_code=400)
    deleted = 0
    with db.get_conn() as conn:
        for iid in ids:
            try:
                lifecycle.delete_note(conn, iid)
                deleted += 1
            except (ValueError, notes.VaultSafetyError):
                continue
    return {"ok": True, "deleted": deleted}


@app.post("/api/category/{category_id}/done")
def api_done_category(category_id: int):
    with db.get_conn() as conn:
        try:
            n = lifecycle.done_category(conn, category_id)
        except (ValueError, notes.VaultSafetyError) as e:
            return JSONResponse({"ok": False, "error": str(e)}, status_code=400)
    return {"ok": True, "notes_archived": n}


@app.post("/api/category/{category_id}/delete")
def api_delete_category(category_id: int):
    with db.get_conn() as conn:
        try:
            n = lifecycle.delete_category(conn, category_id)
        except (ValueError, notes.VaultSafetyError) as e:
            return JSONResponse({"ok": False, "error": str(e)}, status_code=400)
    return {"ok": True, "notes_deleted": n}


@app.get("/api/search")
def api_search(q: str = "", mode: str = "keyword", category: str = "",
               platform: str = "", tag: str = "", date_from: str = "",
               date_to: str = "", include_done: int = 0):
    filters = {
        "category_path": category or None, "platform": platform or None,
        "tag": tag or None, "date_from": date_from or None,
        "date_to": date_to or None, "include_done": bool(include_done),
    }
    cfg = load_config()
    with db.get_conn() as conn:
        try:
            if mode == "semantic" and q.strip():
                results = search.semantic_search(conn, cfg, q, filters)
            elif q.strip():
                results = search.keyword_search(conn, q, filters)
            else:
                results = search.filtered_browse(conn, filters)  # R49
        except ollama_client.OllamaError as e:
            return JSONResponse(
                {"ok": False,
                 "error": f"Semantic search needs Ollama running ({e})."},
                status_code=503,
            )
    return {"ok": True, "results": results}


@app.get("/api/categories")
def api_categories(include_archived: int = 0):
    with db.get_conn() as conn:
        return {"categories": category_tree(conn, bool(include_archived))}


@app.get("/api/graph")
def api_graph(include_archived: int = 0):
    """Nodes (notes + category hubs) and links (membership, hierarchy, related)
    for the knowledge graph. Done/archived hidden unless include_archived."""
    with db.get_conn() as conn:
        cat_where = "" if include_archived else "WHERE status = 'active'"
        cats = conn.execute(f"SELECT * FROM categories {cat_where}").fetchall()
        cat_ids = {c["id"] for c in cats}
        nodes, links = [], []
        for c in cats:
            nodes.append({"id": f"c{c['id']}", "type": "category", "label": c["name"],
                          "sub": c["path"], "url": f"/category/{c['id']}"})
            if c["parent_id"] in cat_ids:
                links.append({"source": f"c{c['parent_id']}", "target": f"c{c['id']}",
                              "kind": "hier"})
        item_where = "" if include_archived else "AND i.status = 'active'"
        items = conn.execute(
            "SELECT i.id, i.title, i.platform, i.status, i.category_id, c.path AS cat "
            "FROM items i LEFT JOIN categories c ON c.id = i.category_id "
            f"WHERE 1=1 {item_where}"
        ).fetchall()
        item_ids = {i["id"] for i in items}
        for it in items:
            nodes.append({"id": f"n{it['id']}", "type": "note", "label": it["title"],
                          "sub": it["cat"] or "", "platform": it["platform"] or "",
                          "status": it["status"], "url": f"/card/{it['id']}"})
            if it["category_id"] in cat_ids:
                links.append({"source": f"c{it['category_id']}", "target": f"n{it['id']}",
                              "kind": "member"})
        for r in conn.execute("SELECT item_id, related_item_id FROM related_links"):
            if r["item_id"] in item_ids and r["related_item_id"] in item_ids:
                links.append({"source": f"n{r['item_id']}", "target": f"n{r['related_item_id']}",
                              "kind": "related"})
    return {"nodes": nodes, "links": links}


@app.post("/api/settings")
async def api_settings(request: Request):
    """R16: Settings edits config.json; the vault path is safety-checked (R55)."""
    data = await request.json()
    cfg = load_config()
    new_vault = str(data.get("vault_path", cfg["vault_path"])).strip()
    if new_vault != cfg["vault_path"]:
        ok, msg = notes.vault_is_safe(Path(new_vault))
        if not ok:
            return JSONResponse({"ok": False, "error": msg}, status_code=400)
    numeric = {"poll_interval": int, "subcategory_birth_threshold": int,
               "duplicate_threshold": float, "related_threshold": float, "port": int}
    clean = {}
    for key in ("vault_path", "ollama_url", "chat_model", "embedding_model",
                "whisper_model", "inbox_url", "inbox_token", "poll_interval",
                "duplicate_threshold", "related_threshold",
                "subcategory_birth_threshold", "port"):
        if key in data:
            try:
                clean[key] = numeric[key](data[key]) if key in numeric else str(data[key]).strip()
            except (TypeError, ValueError):
                return JSONResponse({"ok": False, "error": f"'{key}' has an invalid value."},
                                    status_code=400)
    save_config(clean)
    return {"ok": True}


@app.post("/api/test/ollama")
def api_test_ollama():
    ok, msg = ollama_client.status(load_config())
    return {"ok": ok, "message": msg}


@app.post("/api/test/inbox")
def api_test_inbox():
    ok, msg = inbox.test(load_config())
    return {"ok": ok, "message": msg}


@app.post("/api/test/cloud")
def api_test_cloud():
    ok, msg = cloudsync.test(load_config())
    return {"ok": ok, "message": msg}


@app.post("/api/sync-phone")
def api_sync_phone():
    """Publish the whole library to the phone (Settings button)."""
    ok, msg = cloudsync.sync_all(load_config())
    return {"ok": ok, "message": msg}


@app.post("/api/open-vault")
def api_open_vault():
    path = vault_path()
    path.mkdir(parents=True, exist_ok=True)
    os.startfile(str(path))  # noqa: S606 — local desktop app
    return {"ok": True}


@app.get("/api/backups")
def api_backups():
    return {"backups": backup.list_backups()}


@app.post("/api/backup")
def api_backup():
    """Manual 'Back up now' button (a fresh one is also taken on every startup)."""
    try:
        path = backup.create_backup(reason="manual")
    except OSError as e:
        return JSONResponse({"ok": False, "error": f"Backup failed: {e}"}, status_code=500)
    return {"ok": True, "message": f"Backup saved: {path.name}"}


@app.post("/api/open-backups")
def api_open_backups():
    backup.BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    os.startfile(str(backup.BACKUP_DIR))  # noqa: S606 — local desktop app
    return {"ok": True}
