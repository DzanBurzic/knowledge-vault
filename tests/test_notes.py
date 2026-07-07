import pytest

from app import notes


def test_sanitize_segment_strips_invalid_chars():
    assert notes.sanitize_segment("A/B:C*D?") == "A B C D"


def test_sanitize_segment_empty_defaults_to_other():
    assert notes.sanitize_segment("   ") == "Other"


def test_vault_is_safe_for_new_folder(tmp_path):
    ok, _msg = notes.vault_is_safe(tmp_path / "New Vault")
    assert ok


def test_vault_is_safe_for_own_marked_folder(tmp_path):
    vault = tmp_path / "Vault"
    notes.ensure_vault(vault)
    ok, _msg = notes.vault_is_safe(vault)
    assert ok


def test_vault_is_safe_rejects_foreign_folder_with_files(tmp_path):
    foreign = tmp_path / "Existing"
    foreign.mkdir()
    (foreign / "something.txt").write_text("hi", encoding="utf-8")
    ok, msg = notes.vault_is_safe(foreign)
    assert not ok
    assert "Existing" in msg


def test_assert_in_vault_raises_outside_vault(tmp_path):
    vault = tmp_path / "Vault"
    vault.mkdir()
    outside = tmp_path / "Elsewhere" / "file.md"
    with pytest.raises(notes.VaultSafetyError):
        notes.assert_in_vault(outside, vault)


def test_assert_in_vault_allows_inside(tmp_path):
    vault = tmp_path / "Vault"
    vault.mkdir()
    inside = vault / "Sub" / "file.md"
    notes.assert_in_vault(inside, vault)  # should not raise


def test_render_frontmatter_has_exact_keys_in_order():
    item = {
        "title": "My Note", "platform": "web", "original_url": "https://x.com",
        "created_at": "2026-07-07T10:00:00", "tags": ["a", "b"],
        "content_type": "article", "status": "active", "extraction_status": "full",
    }
    fm = notes.render_frontmatter(item, "Travel/Japan")
    keys = [line.split(":")[0].strip() for line in fm.splitlines() if ":" in line]
    assert keys == ["title", "category", "platform", "source_url", "date_saved",
                     "tags", "content_type", "status", "extraction_status"]


def test_render_note_has_no_transcript_only_sections():
    item = {
        "title": "My Note", "platform": "web", "original_url": "https://x.com",
        "created_at": "2026-07-07T10:00:00", "tags": ["a"],
        "content_type": "article", "status": "active", "extraction_status": "full",
        "short_description": "A summary.",
        "main_points": [{"name": "Point", "description": "Detail"}],
    }
    text = notes.render_note(item, "Travel", "Travel", [], [])
    assert "## Main Points" in text
    assert "## Short Description" in text
    assert "## Source" in text
    assert "## Related Notes" in text
    assert "[[Travel (Category)]]" in text
    assert "transcript" not in text.lower()


def test_unique_filename_appends_suffix_on_collision(db_conn, vault_dir):
    base = "my-note"
    first = notes.unique_filename(db_conn, base, vault_dir)
    assert first == base
    (vault_dir / f"{base}.md").write_text("x", encoding="utf-8")
    second = notes.unique_filename(db_conn, base, vault_dir)
    assert second == f"{base}-2"


def test_unique_filename_allows_rewriting_own_file(db_conn, vault_dir, make_item):
    path = vault_dir / "my-note.md"
    path.write_text("x", encoding="utf-8")
    item_id = make_item("Existing", markdown_path=str(path))
    same = notes.unique_filename(db_conn, "my-note", vault_dir, keep_item_id=item_id)
    assert same == "my-note"
