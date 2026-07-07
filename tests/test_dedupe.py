import numpy as np
import pytest

from app import dedupe


def _unit(vec):
    v = np.asarray(vec, dtype=np.float32)
    return v / np.linalg.norm(v)


def test_similarities_orders_by_cosine_descending(db_conn, make_item):
    a = make_item("A", vector=_unit([1, 0, 0]))
    b = make_item("B", vector=_unit([0.9, 0.1, 0]))
    c = make_item("C", vector=_unit([0, 1, 0]))
    sims = dedupe.similarities(db_conn, _unit([1, 0, 0]), exclude_item_id=a)
    ids = [s[0] for s in sims]
    assert ids[0] == b  # closest to [1,0,0] after excluding a
    assert ids[-1] == c


def test_similarities_excludes_given_item(db_conn, make_item):
    a = make_item("A", vector=_unit([1, 0, 0]))
    make_item("B", vector=_unit([1, 0, 0]))
    sims = dedupe.similarities(db_conn, _unit([1, 0, 0]), exclude_item_id=a)
    assert a not in [s[0] for s in sims]


def test_pairwise_similarity_identical_vectors_is_one(db_conn, make_item):
    a = make_item("A", vector=_unit([1, 2, 3]))
    b = make_item("B", vector=_unit([1, 2, 3]))
    sim = dedupe.pairwise_similarity(db_conn, a, b)
    assert sim == pytest.approx(1.0, abs=1e-5)


def test_pairwise_similarity_missing_embedding_is_none(db_conn, make_item):
    a = make_item("A", vector=_unit([1, 0, 0]))
    b = make_item("B")  # no vector
    assert dedupe.pairwise_similarity(db_conn, a, b) is None


def test_maybe_related_band_excludes_above_and_below(db_conn, make_item):
    cfg = {"related_threshold": 0.75}
    origin = make_item("Origin", vector=_unit([1, 0, 0]))
    close = make_item("Too close", vector=_unit([1, 0.01, 0]))  # ~1.0 sim, above ceiling
    mid = make_item("Maybe", vector=_unit([1, 1, 0]))            # ~0.707 sim, in band
    far = make_item("Unrelated", vector=_unit([0, 0, 1]))        # 0 sim, below floor
    out = dedupe.maybe_related(db_conn, origin, cfg)
    ids = [m["id"] for m in out]
    assert mid in ids
    assert close not in ids
    assert far not in ids


def test_maybe_related_excludes_already_linked(db_conn, make_item):
    cfg = {"related_threshold": 0.75}
    origin = make_item("Origin", vector=_unit([1, 0, 0]))
    mid = make_item("Maybe", vector=_unit([1, 1, 0]))
    a, b = sorted((origin, mid))
    db_conn.execute(
        "INSERT INTO related_links (item_id, related_item_id, similarity) VALUES (?, ?, 0.7)",
        (a, b),
    )
    out = dedupe.maybe_related(db_conn, origin, cfg)
    assert mid not in [m["id"] for m in out]


def test_merge_into_existing_unions_tags(db_conn, vault_dir, make_item):
    from app import db as db_mod

    existing = make_item("Existing", tags=["a", "b"],
                         markdown_path=str(vault_dir / "existing.md"))
    dedupe.merge_into_existing(db_conn, vault_dir, existing, "https://x.com/y",
                              "https://x.com/y", ["b", "c"])
    row = db_conn.execute("SELECT tags FROM items WHERE id = ?", (existing,)).fetchone()
    assert db_mod.unj(row["tags"], []) == ["a", "b", "c"]
    dupe = db_conn.execute(
        "SELECT * FROM duplicate_links WHERE item_id = ?", (existing,)
    ).fetchone()
    assert dupe["merged_source_url"] == "https://x.com/y"
