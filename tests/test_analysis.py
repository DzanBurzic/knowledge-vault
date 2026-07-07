import pytest

from app.analysis import _kebab, _validate


def _base():
    return {
        "title": "  My Note  ",
        "category_path": "/Travel/Japan/",
        "tags": ["Travel", " Japan "],
        "content_type": "travel",
        "short_description": "A short summary.",
        "main_points": [{"name": "Point A", "description": "Details A"}],
        "action_items": ["Book flight"],
        "entities": {"tools": [], "people": ["Alice"], "products": [], "locations": ["Tokyo"]},
        "duplicate_check_summary": "Dense summary sentence.",
        "suggested_filename": "My Great Note!",
    }


def test_validate_strips_title_and_category():
    out = _validate(_base())
    assert out["title"] == "My Note"
    assert out["category_path"] == "Travel/Japan"


def test_validate_lowercases_and_strips_tags():
    out = _validate(_base())
    assert out["tags"] == ["travel", "japan"]


def test_validate_caps_main_points_at_six():
    data = _base()
    data["main_points"] = [{"name": f"P{i}", "description": "x"} for i in range(10)]
    out = _validate(data)
    assert len(out["main_points"]) == 6


def test_validate_rejects_missing_title():
    data = _base()
    data["title"] = "   "
    with pytest.raises(ValueError):
        _validate(data)


def test_validate_rejects_empty_main_points():
    data = _base()
    data["main_points"] = []
    with pytest.raises(ValueError):
        _validate(data)


def test_validate_falls_back_to_other_content_type():
    data = _base()
    data["content_type"] = "not-a-real-type"
    out = _validate(data)
    assert out["content_type"] == "other"


def test_validate_kebabs_filename():
    out = _validate(_base())
    assert out["suggested_filename"] == "my-great-note"


def test_kebab_basic():
    assert _kebab("Hello World!") == "hello-world"


def test_kebab_empty_falls_back():
    assert _kebab("") == "untitled-note"


def test_kebab_truncates_long_input():
    assert len(_kebab("x" * 200)) == 80
