from pathlib import Path

from app import categories, db


def test_sanitize_path_caps_at_three_levels():
    assert categories.sanitize_path("A/B/C/D/E") == ["A", "B", "C"]


def test_sanitize_path_empty_defaults_to_other():
    assert categories.sanitize_path("") == ["Other"]


def test_create_chain_creates_nested_folders(db_conn, vault_dir):
    leaf = categories.create_chain(db_conn, vault_dir, ["Travel", "Japan"])
    assert leaf["path"] == "Travel/Japan"
    assert (vault_dir / "Travel" / "Japan").is_dir()
    assert (vault_dir / "Travel" / "Travel (Category).md").exists()
    assert (vault_dir / "Travel" / "Japan" / "Japan (Category).md").exists()


def test_create_chain_reuses_case_insensitive_match(db_conn, vault_dir):
    first = categories.create_chain(db_conn, vault_dir, ["Artificial Intelligence"])
    leaf = categories.create_chain(db_conn, vault_dir, ["artificial intelligence"])
    assert leaf["id"] == first["id"]
    assert leaf["name"] == "Artificial Intelligence"  # existing spelling wins
    count = db_conn.execute(
        "SELECT COUNT(*) AS n FROM categories WHERE lower(name) = 'artificial intelligence'"
    ).fetchone()
    assert count["n"] == 1  # no duplicate sibling created


def test_resolve_immediate_creates_top_level_immediately(db_conn, vault_dir):
    parent, remaining, canonical = categories.resolve_immediate(db_conn, vault_dir, "Fitness/Yoga")
    assert parent["name"] == "Fitness"
    assert remaining == ["Yoga"]
    assert canonical == "Fitness/Yoga"


def test_register_proposal_waits_for_birth_threshold(db_conn, vault_dir, make_item):
    cfg = {"subcategory_birth_threshold": 3}
    for _ in range(2):
        item_id = make_item("Yoga note")
        created = categories.register_proposal(db_conn, cfg, vault_dir, "Fitness/Yoga", item_id)
        assert created is None  # threshold not reached yet
    pending = db_conn.execute(
        "SELECT item_ids FROM pending_subcategories WHERE proposed_path = 'Fitness/Yoga'"
    ).fetchone()
    assert len(db.unj(pending["item_ids"], [])) == 2


def test_register_proposal_creates_and_moves_on_threshold(db_conn, vault_dir, make_item):
    cfg = {"subcategory_birth_threshold": 3}
    parent = categories.create_chain(db_conn, vault_dir, ["Fitness"])
    item_ids = []
    created = None
    for i in range(3):
        item_id = make_item(
            f"Yoga note {i}", category_id=parent["id"],
            markdown_path=str(vault_dir / "Fitness" / f"yoga-{i}.md"),
        )
        item_ids.append(item_id)
        created = categories.register_proposal(db_conn, cfg, vault_dir, "Fitness/Yoga", item_id)
    assert created is not None
    assert created["path"] == "Fitness/Yoga"
    for item_id in item_ids:
        row = db_conn.execute(
            "SELECT category_id, markdown_path FROM items WHERE id = ?", (item_id,)
        ).fetchone()
        assert row["category_id"] == created["id"]
        assert "Yoga" in row["markdown_path"]
        assert Path(row["markdown_path"]).exists()  # write_item_note created it fresh
    pending = db_conn.execute(
        "SELECT 1 FROM pending_subcategories WHERE proposed_path = 'Fitness/Yoga'"
    ).fetchone()
    assert pending is None  # cleared once the threshold triggers the move
