"""Card and category lifecycle: edit, Done, archive, delete (R51–R55)."""

import shutil
from pathlib import Path

from . import categories, cloudsync, db, notes
from .config import vault_path


def edit_card(conn, item_id: int, title: str, category_path: str,
              tags: list[str], short_description: str) -> None:
    """R51: update DB, rewrite the note, move the file if the category changed.
    A brand-new category name is created immediately (bypasses the threshold)."""
    vault = vault_path()
    item = conn.execute("SELECT * FROM items WHERE id = ?", (item_id,)).fetchone()
    if not item:
        raise ValueError("Card not found.")
    conn.execute(
        "UPDATE items SET title = ?, short_description = ?, tags = ?, updated_at = ? "
        "WHERE id = ?",
        (title.strip(), short_description.strip(), db.j(tags), db.now(), item_id),
    )
    db.set_item_tags(conn, item_id, tags)

    old_cat = categories.get_category(conn, item["category_id"]) if item["category_id"] else None
    new_path = "/".join(categories.sanitize_path(category_path))
    if not old_cat or old_cat["path"] != new_path:
        new_cat_id = categories.categorize_item(
            conn, {}, vault, item_id, new_path, force=True
        )
        categories.move_items(conn, vault, [item_id], new_cat_id)
    else:
        notes.write_item_note(conn, item_id, vault)
        notes.regenerate_hubs(conn, vault, {item["category_id"]})
    db.fts_update_item(conn, item_id)
    db.refresh_note_counts(conn)
    cloudsync.mark_dirty(conn, item_id, "put")  # phone copy reflects the edit
    conn.commit()


def set_done(conn, item_id: int, done: bool = True) -> None:
    """R52: Done hides the card from default browse/search; frontmatter updated."""
    vault = vault_path()
    status = "done" if done else "active"
    conn.execute(
        "UPDATE items SET status = ?, updated_at = ? WHERE id = ?",
        (status, db.now(), item_id),
    )
    notes.write_item_note(conn, item_id, vault)
    cloudsync.mark_dirty(conn, item_id, "put")  # phone hides done by default
    conn.commit()


def _subtree(conn, category_id: int) -> list:
    cats = []
    stack = [category_id]
    while stack:
        cid = stack.pop()
        cat = categories.get_category(conn, cid)
        if not cat:
            continue
        cats.append(cat)
        for child in conn.execute(
            "SELECT id FROM categories WHERE parent_id = ?", (cid,)
        ):
            stack.append(child["id"])
    return cats


def subtree_item_ids(conn, category_id: int) -> list[int]:
    return [
        r["id"]
        for cat in _subtree(conn, category_id)
        for r in conn.execute("SELECT id FROM items WHERE category_id = ?", (cat["id"],))
    ]


def done_category(conn, category_id: int) -> int:
    """R53: mark every note inside (incl. subfolders) done and move the whole
    folder under Archive/ preserving its internal structure."""
    vault = vault_path()
    cat = categories.get_category(conn, category_id)
    if not cat:
        raise ValueError("Category not found.")
    if cat["status"] == "archived":
        return 0
    old_dir = notes.category_disk_dir(vault, cat["path"], archived=False)
    new_dir = notes.category_disk_dir(vault, cat["path"], archived=True)
    notes.assert_in_vault(old_dir, vault)
    notes.assert_in_vault(new_dir, vault)

    subtree = _subtree(conn, category_id)
    item_ids = subtree_item_ids(conn, category_id)
    ts = db.now()
    for iid in item_ids:
        conn.execute("UPDATE items SET status = 'done', updated_at = ? WHERE id = ?",
                     (ts, iid))
    for c in subtree:
        conn.execute("UPDATE categories SET status = 'archived' WHERE id = ?", (c["id"],))

    if old_dir.exists():
        new_dir.parent.mkdir(parents=True, exist_ok=True)
        if new_dir.exists():  # merge into an existing archive folder
            for entry in old_dir.rglob("*"):
                if entry.is_file():
                    rel = entry.relative_to(old_dir)
                    target = new_dir / rel
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.move(str(entry), str(target))
            shutil.rmtree(old_dir, ignore_errors=True)
        else:
            shutil.move(str(old_dir), str(new_dir))

    # repoint markdown paths and rewrite frontmatter (status: done)
    for iid in item_ids:
        item = conn.execute("SELECT markdown_path FROM items WHERE id = ?", (iid,)).fetchone()
        if item and item["markdown_path"]:
            old_path = Path(item["markdown_path"])
            try:
                rel = old_path.relative_to(old_dir)
                new_path = new_dir / rel
            except ValueError:
                new_path = old_path
            conn.execute("UPDATE items SET markdown_path = ? WHERE id = ?",
                         (str(new_path), iid))
            notes.write_item_note(conn, iid, vault)
    for c in subtree:
        notes.write_hub_note(conn, c["id"], vault)
    if cat["parent_id"]:
        notes.regenerate_hubs(conn, vault, {cat["parent_id"]})
    for iid in item_ids:  # phone reflects archived status
        cloudsync.mark_dirty(conn, iid, "put")
    db.refresh_note_counts(conn)
    conn.commit()
    return len(item_ids)


def delete_note(conn, item_id: int) -> str:
    """R54: permanently remove the file and every DB row; other notes lose
    their Related Notes references to it."""
    vault = vault_path()
    item = conn.execute("SELECT * FROM items WHERE id = ?", (item_id,)).fetchone()
    if not item:
        raise ValueError("Card not found.")
    related_ids = [
        r["other"] for r in conn.execute(
            "SELECT CASE WHEN item_id = :id THEN related_item_id ELSE item_id END AS other "
            "FROM related_links WHERE item_id = :id OR related_item_id = :id",
            {"id": item_id},
        )
    ]
    if item["markdown_path"]:
        p = Path(item["markdown_path"])
        if p.exists():
            notes.assert_in_vault(p, vault)
            p.unlink()
    cat_id = item["category_id"]
    conn.execute("DELETE FROM fts_cards WHERE item_id = ?", (item_id,))
    conn.execute("DELETE FROM fts_raw WHERE item_id = ?", (item_id,))
    conn.execute("DELETE FROM related_links WHERE item_id = ? OR related_item_id = ?",
                 (item_id, item_id))
    conn.execute("DELETE FROM items WHERE id = ?", (item_id,))  # cascades raw/embeddings/tags/dupes
    conn.execute("UPDATE queue SET item_id = NULL WHERE item_id = ?", (item_id,))
    cloudsync.mark_dirty(conn, item_id, "delete")  # remove from the phone
    for rid in related_ids:  # their Related Notes sections drop this card
        row = conn.execute("SELECT markdown_path FROM items WHERE id = ?", (rid,)).fetchone()
        if row and row["markdown_path"]:
            notes.write_item_note(conn, rid, vault)
            cloudsync.mark_dirty(conn, rid, "put")
    db.refresh_note_counts(conn)
    if cat_id:
        notes.regenerate_hubs(conn, vault, {cat_id})
    conn.commit()
    return item["title"]


def delete_category(conn, category_id: int) -> int:
    """R54: delete a category folder, all notes inside (incl. subfolders) and
    every related DB row. Returns the number of deleted notes."""
    vault = vault_path()
    cat = categories.get_category(conn, category_id)
    if not cat:
        raise ValueError("Category not found.")
    item_ids = subtree_item_ids(conn, category_id)
    for iid in item_ids:
        delete_note(conn, iid)
    folder = notes.category_disk_dir(vault, cat["path"], cat["status"] == "archived")
    subtree = _subtree(conn, category_id)
    conn.execute("DELETE FROM categories WHERE id = ?", (category_id,))  # cascades children
    for c in subtree:
        conn.execute(
            "DELETE FROM pending_subcategories WHERE proposed_path = ? "
            "OR proposed_path LIKE ?",
            (c["path"], c["path"] + "/%"),
        )
    if folder.exists():
        notes.assert_in_vault(folder, vault)
        shutil.rmtree(folder)
    if cat["parent_id"]:
        notes.regenerate_hubs(conn, vault, {cat["parent_id"]})
    db.refresh_note_counts(conn)
    conn.commit()
    return len(item_ids)
