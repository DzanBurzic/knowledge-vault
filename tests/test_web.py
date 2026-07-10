from app import categories, db, web


def test_category_tree_total_note_count_includes_descendants(db_conn, vault_dir, make_item):
    """R8: total_note_count aggregates a category's own notes plus every
    descendant's notes; direct note_count is left untouched."""
    tech = categories.create_chain(db_conn, vault_dir, ["Technology"])
    ai = categories.create_chain(db_conn, vault_dir, ["Technology", "AI"])
    claude = categories.create_chain(db_conn, vault_dir, ["Technology", "AI", "Claude"])
    business = categories.create_chain(db_conn, vault_dir, ["Business"])

    make_item("t1", category_id=tech["id"])
    make_item("t2", category_id=tech["id"])
    make_item("ai1", category_id=ai["id"])
    make_item("cl1", category_id=claude["id"])
    make_item("b1", category_id=business["id"])
    db.refresh_note_counts(db_conn)
    db_conn.commit()

    cats = {c["path"]: c for c in web.category_tree(db_conn)}
    # Technology: 2 own + 1 (AI) + 1 (Claude) = 4
    assert cats["Technology"]["total_note_count"] == 4
    assert cats["Technology"]["note_count"] == 2  # direct-only preserved
    assert cats["Technology/AI"]["total_note_count"] == 2
    assert cats["Technology/AI/Claude"]["total_note_count"] == 1
    assert cats["Business"]["total_note_count"] == 1


def test_category_tree_zero_notes_still_listed(db_conn, vault_dir):
    """Edge case: a category with no notes anywhere still appears, count 0."""
    categories.create_chain(db_conn, vault_dir, ["Empty"])
    db.refresh_note_counts(db_conn)
    db_conn.commit()
    cats = {c["path"]: c for c in web.category_tree(db_conn)}
    assert cats["Empty"]["total_note_count"] == 0


def test_code_stamp_endpoint_matches_disk():
    """run_app.py restarts a running server whose /api/code-stamp differs from
    the code on disk; a freshly imported app must therefore always match."""
    from app import version
    assert web.api_code_stamp() == {"stamp": web.CODE_STAMP}
    assert web.CODE_STAMP == version.code_stamp()
    assert web.CODE_STAMP.isdigit()
