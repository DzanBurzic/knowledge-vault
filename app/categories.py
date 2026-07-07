"""Self-growing category tree (R32–R34) and item moves between categories.

- max 3 levels, mirrored 1:1 as vault folders
- top-level categories are created immediately (R33)
- deeper levels wait for the birth threshold in pending_subcategories (R34)
"""

import shutil
from pathlib import Path

from . import cloudsync, db, notes


def tree_text(conn) -> str:
    """Category tree rendered for the analysis prompt (R27)."""
    rows = conn.execute(
        "SELECT path, note_count FROM categories WHERE status = 'active' ORDER BY path"
    ).fetchall()
    return "\n".join(f"{r['path']} — {r['note_count']} notes" for r in rows)


def sanitize_path(proposed: str) -> list[str]:
    """Split, clean and truncate a proposed path to max 3 levels (R32)."""
    segs = [notes.sanitize_segment(s) for s in (proposed or "").split("/") if s.strip()]
    return segs[:3] or ["Other"]


def find_child(conn, parent_id, name: str):
    """Case-insensitive match against existing names (R33, naming-drift edge case)."""
    if parent_id is None:
        return conn.execute(
            "SELECT * FROM categories WHERE parent_id IS NULL AND status='active' "
            "AND lower(name) = lower(?)", (name,),
        ).fetchone()
    return conn.execute(
        "SELECT * FROM categories WHERE parent_id = ? AND status='active' "
        "AND lower(name) = lower(?)", (parent_id, name),
    ).fetchone()


def get_category(conn, category_id: int):
    return conn.execute("SELECT * FROM categories WHERE id = ?", (category_id,)).fetchone()


def create_chain(conn, vault: Path, segs: list[str]):
    """Create every missing level of the path; returns the leaf category row."""
    parent = None
    for seg in segs:
        parent_id = parent["id"] if parent else None
        existing = find_child(conn, parent_id, seg)
        if existing:
            parent = existing
            continue
        path = f"{parent['path']}/{seg}" if parent else seg
        cur = conn.execute(
            "INSERT INTO categories (name, parent_id, path) VALUES (?, ?, ?)",
            (seg, parent_id, path),
        )
        parent = get_category(conn, cur.lastrowid)
        folder = notes.category_disk_dir(vault, path, archived=False)
        notes.assert_in_vault(folder, vault)
        folder.mkdir(parents=True, exist_ok=True)
        notes.write_hub_note(conn, parent["id"], vault)
        if parent_id:
            notes.write_hub_note(conn, parent_id, vault)
    return parent


def resolve_immediate(conn, vault: Path, proposed_path: str):
    """Phase 1 of categorization, before the item row exists.

    Returns (category_row_to_file_into, remaining_new_segments, full_target_path).
    Top-level categories are created immediately (R33); deeper new levels are
    left for the birth threshold (R34).
    """
    segs = sanitize_path(proposed_path)
    matched = []
    parent = None
    idx = 0
    for seg in segs:
        row = find_child(conn, parent["id"] if parent else None, seg)
        if not row:
            break
        matched.append(row)
        parent = row
        idx += 1
    if idx == 0:
        parent = create_chain(conn, vault, segs[:1])
        matched = [parent]
        idx = 1
    remaining = segs[idx:]
    canonical = "/".join([m["name"] for m in matched] + remaining)
    return matched[-1], remaining, canonical


def register_proposal(conn, cfg: dict, vault: Path, target_path: str, item_id: int):
    """Phase 2 (item row exists): record the proposal; when the birth threshold
    is reached, create the folder chain and move every pending note in (R34).

    Returns the new leaf category row when created, else None.
    """
    threshold = int(cfg.get("subcategory_birth_threshold", 3))
    row = conn.execute(
        "SELECT * FROM pending_subcategories WHERE lower(proposed_path) = lower(?)",
        (target_path,),
    ).fetchone()
    item_ids = db.unj(row["item_ids"], []) if row else []
    # Notes deleted since they voted no longer count toward the threshold.
    item_ids = [
        i for i in item_ids
        if conn.execute("SELECT 1 FROM items WHERE id = ?", (i,)).fetchone()
    ]
    if item_id not in item_ids:
        item_ids.append(item_id)
    if len(item_ids) < threshold:
        if row:
            conn.execute(
                "UPDATE pending_subcategories SET item_ids = ? WHERE id = ?",
                (db.j(item_ids), row["id"]),
            )
        else:
            conn.execute(
                "INSERT INTO pending_subcategories (proposed_path, item_ids) VALUES (?, ?)",
                (target_path, db.j(item_ids)),
            )
        return None
    # Threshold reached: create the chain, move the pending notes (R34).
    leaf = create_chain(conn, vault, sanitize_path(target_path))
    if row:
        conn.execute("DELETE FROM pending_subcategories WHERE id = ?", (row["id"],))
    move_items(conn, vault, item_ids, leaf["id"])
    return leaf


def move_items(conn, vault: Path, item_ids: list[int], category_id: int) -> None:
    """Move items into a category: files moved on disk, DB + frontmatter +
    hub notes updated (R34, R51)."""
    leaf = get_category(conn, category_id)
    if not leaf:
        return
    target_dir = notes.category_disk_dir(vault, leaf["path"], leaf["status"] == "archived")
    notes.assert_in_vault(target_dir, vault)
    target_dir.mkdir(parents=True, exist_ok=True)
    touched = {category_id}
    for iid in item_ids:
        item = conn.execute("SELECT * FROM items WHERE id = ?", (iid,)).fetchone()
        if not item:
            continue
        if item["category_id"]:
            touched.add(item["category_id"])
        old_path = Path(item["markdown_path"]) if item["markdown_path"] else None
        conn.execute(
            "UPDATE items SET category_id = ?, updated_at = ? WHERE id = ?",
            (category_id, db.now(), iid),
        )
        if old_path:
            new_path = target_dir / old_path.name
            if old_path.exists() and old_path.resolve() != new_path.resolve():
                notes.assert_in_vault(old_path, vault)
                shutil.move(str(old_path), str(new_path))
            conn.execute(
                "UPDATE items SET markdown_path = ? WHERE id = ?", (str(new_path), iid)
            )
            notes.write_item_note(conn, iid, vault)  # frontmatter category updated
        cloudsync.mark_dirty(conn, iid, "put")  # phone copy gets the new category
    db.refresh_note_counts(conn)
    notes.regenerate_hubs(conn, vault, touched)


def categorize_item(conn, cfg: dict, vault: Path, item_id: int, proposed_path: str,
                    force: bool = False) -> int:
    """Full categorization for an existing item row. Returns final category id.

    force=True (user edits) creates the whole path immediately, bypassing the
    birth threshold (R51 edge case)."""
    if force:
        leaf = create_chain(conn, vault, sanitize_path(proposed_path))
        return leaf["id"]
    parent, remaining, canonical = resolve_immediate(conn, vault, proposed_path)
    if not remaining:
        return parent["id"]
    created = register_proposal(conn, cfg, vault, canonical, item_id)
    return created["id"] if created else parent["id"]
