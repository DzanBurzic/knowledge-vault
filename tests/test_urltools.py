from app.urltools import (detect_platform, extract_first_url, normalize_url,
                          source_label)


def test_detect_platform_youtube_video():
    assert detect_platform("https://www.youtube.com/watch?v=abc123") == ("youtube", "video")


def test_detect_platform_youtube_short():
    assert detect_platform("https://www.youtube.com/shorts/abc123") == ("youtube", "short")


def test_detect_platform_instagram_reel():
    platform, kind = detect_platform("https://www.instagram.com/reel/XYZ/")
    assert (platform, kind) == ("instagram", "reel")


def test_detect_platform_tiktok():
    assert detect_platform("https://www.tiktok.com/@user/video/123")[0] == "tiktok"


def test_detect_platform_unknown_is_web_article():
    assert detect_platform("https://example.com/some/article") == ("web", "article")


def test_normalize_url_strips_tracking_params():
    a = normalize_url("https://example.com/article?utm_source=ig&id=5")
    b = normalize_url("https://example.com/article?id=5")
    assert a == b


def test_normalize_url_youtube_canonical_id():
    a = normalize_url("https://youtu.be/abc123?t=42")
    b = normalize_url("https://www.youtube.com/watch?v=abc123&list=PLxyz")
    assert a == b == "https://www.youtube.com/watch?v=abc123"


def test_normalize_url_instagram_reel_ignores_query():
    a = normalize_url("https://www.instagram.com/reel/DaYjBh1ABaZ/?igsh=abc123")
    b = normalize_url("https://www.instagram.com/reel/DaYjBh1ABaZ/")
    assert a == b


def test_normalize_url_lowercases_host():
    assert normalize_url("https://Example.COM/path") == "https://example.com/path"


def test_extract_first_url_from_text():
    text = "check this out https://example.com/x nice"
    assert extract_first_url(text) == "https://example.com/x"


def test_extract_first_url_none_when_absent():
    assert extract_first_url("just some text, no link") is None


def test_extract_first_url_strips_trailing_punctuation():
    assert extract_first_url("see https://example.com/x.") == "https://example.com/x"


# ---------------------------------------------------------------- source_label (R18)

def test_source_label_instagram_reel():
    assert source_label("instagram", "https://www.instagram.com/reel/XYZ/") == "Instagram Reel"


def test_source_label_instagram_post():
    assert source_label("instagram", "https://www.instagram.com/p/XYZ/") == "Instagram Post"


def test_source_label_youtube_video():
    assert source_label("youtube", "https://www.youtube.com/watch?v=abc123") == "YouTube Video"


def test_source_label_youtube_short():
    assert source_label("youtube", "https://www.youtube.com/shorts/abc123") == "YouTube Short"


def test_source_label_tiktok_video():
    assert source_label("tiktok", "https://www.tiktok.com/@u/video/123") == "TikTok Video"


def test_source_label_web_article():
    assert source_label("web", "https://example.com/some/article") == "Article"


def test_source_label_manual_is_pasted_text():
    assert source_label("manual", "") == "Pasted text"
    assert source_label("manual", None) == "Pasted text"


def test_source_label_no_url_falls_back_to_platform():
    assert source_label("instagram", "") == "Instagram"


def test_source_label_unknown_platform_no_url_capitalized():
    assert source_label("podcast", "") == "Podcast"


def test_source_label_from_url_only():
    # merged-duplicate sources have a URL but no stored platform (R20)
    assert source_label(None, "https://www.youtube.com/shorts/abc123") == "YouTube Short"
