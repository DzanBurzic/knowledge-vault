"""Markdown note rendering and vault file operations (R28, R35–R38, R55).

Notes are always rendered from DB state, so every rewrite (merge, edit,
archive) produces a consistent file. Cards are short: main points, short
description, sources, related links — never transcripts (R28).
"""

import re
from pathlib import Path

from . import db
from .config import VAULT_MARKER

PLATFORM_LABELS = {
    "youtube": "YouTube", "instagram": "Instagram", "tiktok": "TikTok",
    "web": "Web", "manual": "Pasted text",
}

INVALID_FS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


class VaultSafetyError(Exception):
    pass


# ------------------------------------------------------------------ safety

def assert_in_vault(path: Path, vault: Path) -> Path:
    """R55/R59: refuse any file operation outside the configured vault folder."""
    resolved = Path(path).resolve()
    vault_resolved = Path(vault).resolve()
    if vault_resolved != resolved and vault_resolved not in resolved.parents:
        raise VaultSafetyError(f"Refusing to touch a path outside the vault: {resolved}")
    return resolved


def vault_is_safe(vault: Path) -> tuple[bool, str]:
    """R55: only operate on a folder Notulus created (marker file),
    an empty folder, or one that doesn't exist yet."""
    vault = Path(vault)
    if not vault.exists():
        return True, ""
    if (vault / VAULT_MARKER).exists():
        return True, ""
    foreign = [p.name for p in vault.iterdir()]
    if not foreign:
        return True, ""
    return False, (
        f"The vault folder '{vault}' already exists and contains files that "
        f"Notulus did not create ({', '.join(foreign[:5])}...). "
        "Pick an empty or new folder to keep your files safe."
    )


def ensure_vault(vault: Path) -> None:
    ok, msg = vault_is_safe(vault)
    if not ok:
        raise VaultSafetyError(msg)
    vault.mkdir(parents=True, exist_ok=True)
    (vault / VAULT_MARKER).touch(exist_ok=True)


# -------------------------------------------------------------- file names

def sanitize_segment(name: str) -> str:
    name = INVALID_FS.sub(" ", name).strip().strip(".")
    name = re.sub(r"\s+", " ", name)
    return name[:60] or "Other"


def unique_filename(conn, base: str, vault: Path, keep_item_id: int | None = None) -> str:
    """R37: kebab-case filename; on collision append -2, -3, ...
    Uniqueness is vault-wide so Obsidian wikilinks stay unambiguous."""
    base = re.sub(r"[^a-z0-9-]+", "-", base.lower()).strip("-")[:80] or "untitled-note"
    taken = {
        Path(r["markdown_path"]).stem.lower()
        for r in conn.execute(
            "SELECT markdown_path FROM items WHERE markdown_path IS NOT NULL "
            "AND (? IS NULL OR id != ?)", (keep_item_id, keep_item_id),
        )
    }
    if vault.exists():
        taken |= {p.stem.lower() for p in vault.rglob("*.md")}
        if keep_item_id is not None:
            row = conn.execute(
                "SELECT markdown_path FROM items WHERE id = ?", (keep_item_id,)
            ).fetchone()
            if row and row["markdown_path"]:
                taken.discard(Path(row["markdown_path"]).stem.lower())
    candidate, n = base, 1
    while candidate.lower() in taken:
        n += 1
        candidate = f"{base}-{n}"
    return candidate


# ---------------------------------------------------------------- YAML

def _yaml_value(value) -> str:
    s = "" if value is None else str(value)
    if s == "" or re.search(r'[:#{}\[\]&*!|>\'"%@`,\n\t]', s) or s != s.strip():
        return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'
    return s


def render_frontmatter(item: dict, category_path: str) -> str:
    """R38: exactly these keys, in this order."""
    tags = item.get("tags") or []
    lines = ["---"]
    lines.append(f"title: {_yaml_value(item['title'])}")
    lines.append(f"category: {_yaml_value(category_path)}")
    lines.append(f"platform: {_yaml_value(item.get('platform') or 'manual')}")
    lines.append(f"source_url: {_yaml_value(item.get('original_url') or '')}")
    lines.append(f"date_saved: {(item.get('created_at') or '')[:10]}")
    if tags:
        lines.append("tags:")
        lines += [f"  - {_yaml_value(t)}" for t in tags]
    else:
        lines.append("tags: []")
    lines.append(f"content_type: {_yaml_value(item.get('content_type') or 'other')}")
    lines.append(f"status: {item.get('status') or 'active'}")
    lines.append(f"extraction_status: {item.get('extraction_status') or 'full'}")
    lines.append("---")
    return "\n".join(lines)


# ---------------------------------------------------------------- rendering

def hub_basename(category_name: str) -> str:
    return f"{sanitize_segment(category_name)} (Category)"


def render_note(item: dict, category_path: str, category_name: str,
                additional_sources: list[str], related: list[dict]) -> str:
    """Body per R38: # Title, ## Main Points, ## Short Description, ## Source
    (+ ### Additional sources), ## Related Notes, final category hub link."""
    label = PLATFORM_LABELS.get(item.get("platform") or "manual", "Web")
    out = [render_frontmatter(item, category_path), ""]
    out.append(f"# {item['title']}")
    out.append("")
    out.append("## Main Points")
    for i, p in enumerate(item.get("main_points") or [], 1):
        desc = (p.get("description") or "").strip()
        name = (p.get("name") or "").strip()
        out.append(f"{i}. **{name}** — {desc}" if desc else f"{i}. **{name}**")
    out.append("")
    out.append("## Short Description")
    out.append(item.get("short_description") or "")
    out.append("")
    out.append("## Source")
    url = item.get("original_url") or ""
    out.append(f"{label} — {url}" if url else label)
    if additional_sources:
        out.append("")
        out.append("### Additional sources")
        out += [f"- {u}" for u in additional_sources]
    out.append("")
    out.append("## Related Notes")
    if related:
        out += [f"- [[{r['filename']}|{r['title']}]]" for r in related]
    else:
        out.append("_None yet._")
    out.append("")
    out.append(f"[[{hub_basename(category_name)}]]")
    out.append("")
    return "\n".join(out)


def category_disk_dir(vault: Path, category_path: str, archived: bool) -> Path:
    parts = [sanitize_segment(p) for p in category_path.split("/") if p]
    base = vault / "Archive" if archived else vault
    return base.joinpath(*parts) if parts else base


def write_item_note(conn, item_id: int, vault: Path) -> Path:
    """Render an item's note from DB state and write it to its markdown_path."""
    item = conn.execute("SELECT * FROM items WHERE id = ?", (item_id,)).fetchone()
    if not item:
        raise ValueError(f"item {item_id} not found")
    cat = conn.execute(
        "SELECT * FROM categories WHERE id = ?", (item["category_id"],)
    ).fetchone()
    category_path = cat["path"] if cat else "Inbox"
    category_name = cat["name"] if cat else "Inbox"
    dupes = [
        r["merged_source_url"]
        for r in conn.execute(
            "SELECT merged_source_url FROM duplicate_links WHERE item_id = ? ORDER BY merged_at",
            (item_id,),
        )
    ]
    related = []
    for r in conn.execute(
        "SELECT i.id, i.title, i.markdown_path FROM related_links rl "
        "JOIN items i ON i.id = CASE WHEN rl.item_id = :id THEN rl.related_item_id ELSE rl.item_id END "
        "WHERE rl.item_id = :id OR rl.related_item_id = :id "
        "ORDER BY rl.similarity DESC",
        {"id": item_id},
    ):
        if r["markdown_path"]:
            related.append({
                "filename": Path(r["markdown_path"]).stem,
                "title": r["title"],
            })
    data = dict(item)
    data["main_points"] = db.unj(item["main_points"], [])
    data["tags"] = db.unj(item["tags"], [])
    text = render_note(data, category_path, category_name, dupes, related)
    path = Path(item["markdown_path"])
    assert_in_vault(path, vault)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


# ---------------------------------------------------------------- hub notes

def write_hub_note(conn, category_id: int, vault: Path) -> None:
    """R35: hub note listing parent link, child categories and all cards."""
    cat = conn.execute("SELECT * FROM categories WHERE id = ?", (category_id,)).fetchone()
    if not cat:
        return
    archived = cat["status"] == "archived"
    folder = category_disk_dir(vault, cat["path"], archived)
    lines = [f"# {cat['name']} (Category)", ""]
    if cat["parent_id"]:
        parent = conn.execute(
            "SELECT name FROM categories WHERE id = ?", (cat["parent_id"],)
        ).fetchone()
        if parent:
            lines.append(f"Parent: [[{hub_basename(parent['name'])}]]")
            lines.append("")
    children = conn.execute(
        "SELECT * FROM categories WHERE parent_id = ? AND status = 'active' ORDER BY name",
        (category_id,),
    ).fetchall()
    if archived:  # archived hubs keep listing their (archived) children
        children = conn.execute(
            "SELECT * FROM categories WHERE parent_id = ? ORDER BY name", (category_id,)
        ).fetchall()
    if children:
        lines.append("## Subcategories")
        lines += [f"- [[{hub_basename(c['name'])}|{c['name']}]]" for c in children]
        lines.append("")
    notes = conn.execute(
        "SELECT title, markdown_path FROM items WHERE category_id = ? ORDER BY title",
        (category_id,),
    ).fetchall()
    lines.append("## Notes")
    if notes:
        lines += [
            f"- [[{Path(n['markdown_path']).stem}|{n['title']}]]"
            for n in notes if n["markdown_path"]
        ]
    else:
        lines.append("_No notes yet._")
    lines.append("")
    path = folder / f"{hub_basename(cat['name'])}.md"
    assert_in_vault(path, vault)
    folder.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def regenerate_hubs(conn, vault: Path, category_ids) -> None:
    """Regenerate the given hubs plus their parents (contents changed — R35)."""
    seen = set()
    stack = [c for c in category_ids if c]
    while stack:
        cid = stack.pop()
        if cid in seen:
            continue
        seen.add(cid)
        row = conn.execute("SELECT parent_id FROM categories WHERE id = ?", (cid,)).fetchone()
        if row and row["parent_id"]:
            stack.append(row["parent_id"])
    for cid in seen:
        write_hub_note(conn, cid, vault)
