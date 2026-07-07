from pathlib import Path

from app import categories, lifecycle, notes


def test_set_done_updates_status_and_frontmatter(db_conn, vault_dir, make_item,
                                                  patch_lifecycle_vault):
    item_id = make_item("Note", markdown_path=str(vault_dir / "note.md"))
    lifecycle.set_done(db_conn, item_id)
    row = db_conn.execute("SELECT status FROM items WHERE id = ?", (item_id,)).fetchone()
    assert row["status"] == "done"
    text = (vault_dir / "note.md").read_text(encoding="utf-8")
    assert "status: done" in text


def test_delete_note_removes_file_and_db_rows(db_conn, vault_dir, make_item,
                                              patch_lifecycle_vault):
    item_id = make_item("Note", markdown_path=str(vault_dir / "note.md"), vector=[1, 0, 0])
    notes.write_item_note(db_conn, item_id, vault_dir)
    assert (vault_dir / "note.md").exists()
    lifecycle.delete_note(db_conn, item_id)
    assert not (vault_dir / "note.md").exists()
    assert db_conn.execute("SELECT 1 FROM items WHERE id = ?", (item_id,)).fetchone() is None
    assert db_conn.execute(
        "SELECT 1 FROM embeddings WHERE item_id = ?", (item_id,)
    ).fetchone() is None


def test_delete_note_removes_reference_from_related_notes(db_conn, vault_dir, make_item,
                                                           patch_lifecycle_vault):
    a = make_item("A", markdown_path=str(vault_dir / "a.md"))
    b = make_item("B", markdown_path=str(vault_dir / "b.md"))
    db_conn.execute(
        "INSERT INTO related_links (item_id, related_item_id, similarity) VALUES (?, ?, 0.8)",
        tuple(sorted((a, b))),
    )
    notes.write_item_note(db_conn, a, vault_dir)
    notes.write_item_note(db_conn, b, vault_dir)
    assert "[[b" in (vault_dir / "a.md").read_text(encoding="utf-8")
    lifecycle.delete_note(db_conn, b)
    assert "[[b" not in (vault_dir / "a.md").read_text(encoding="utf-8")


def test_done_category_archives_folder(db_conn, vault_dir, make_item, patch_lifecycle_vault):
    leaf = categories.create_chain(db_conn, vault_dir, ["Travel", "Japan"])
    item_id = make_item("Note", category_id=leaf["id"],
                        markdown_path=str(vault_dir / "Travel" / "Japan" / "note.md"))
    notes.write_item_note(db_conn, item_id, vault_dir)
    n = lifecycle.done_category(db_conn, leaf["id"])
    assert n == 1
    row = db_conn.execute(
        "SELECT status, markdown_path FROM items WHERE id = ?", (item_id,)
    ).fetchone()
    assert row["status"] == "done"
    assert "Archive" in row["markdown_path"]
    assert Path(row["markdown_path"]).exists()
    assert not (vault_dir / "Travel" / "Japan").exists()


def test_delete_category_removes_notes_and_folder(db_conn, vault_dir, make_item,
                                                   patch_lifecycle_vault):
    leaf = categories.create_chain(db_conn, vault_dir, ["Travel"])
    item_id = make_item("Note", category_id=leaf["id"],
                        markdown_path=str(vault_dir / "Travel" / "note.md"))
    notes.write_item_note(db_conn, item_id, vault_dir)
    n = lifecycle.delete_category(db_conn, leaf["id"])
    assert n == 1
    assert db_conn.execute("SELECT 1 FROM items WHERE id = ?", (item_id,)).fetchone() is None
    assert not (vault_dir / "Travel").exists()
