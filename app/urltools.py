"""URL platform detection (R17) and normalization for dedupe (R40)."""

import re
from urllib.parse import parse_qsl, urlencode, urlparse

URL_RE = re.compile(r"https?://[^\s<>\"']+", re.IGNORECASE)

TRACKING_PARAMS = {
    "igsh", "igshid", "si", "fbclid", "gclid", "feature", "ref", "ref_src",
    "share_id", "_r", "mc_cid", "mc_eid", "s", "t", "pp",
}

YOUTUBE_ID_RE = re.compile(r"^[A-Za-z0-9_-]{6,}$")


def extract_first_url(text: str) -> str | None:
    if not text:
        return None
    m = URL_RE.search(text)
    return m.group(0).rstrip(".,;)!?\"'") if m else None


def _youtube_video_id(parsed) -> str | None:
    host = parsed.netloc.lower().removeprefix("www.").removeprefix("m.")
    path = parsed.path
    if host == "youtu.be":
        vid = path.strip("/").split("/")[0]
        return vid or None
    if host.endswith("youtube.com"):
        if path == "/watch":
            for k, v in parse_qsl(parsed.query):
                if k == "v":
                    return v
        m = re.match(r"^/(shorts|embed|live|v)/([A-Za-z0-9_-]+)", path)
        if m:
            return m.group(2)
    return None


def detect_platform(url: str) -> tuple[str, str]:
    """Return (platform, kind).

    platform: youtube | instagram | tiktok | web
    kind: video | short | reel | post | article
    Unrecognized URLs are treated as web articles (R17).
    """
    parsed = urlparse(url)
    host = parsed.netloc.lower().removeprefix("www.").removeprefix("m.")
    path = parsed.path.lower()

    if host == "youtu.be" or host.endswith("youtube.com"):
        kind = "short" if "/shorts/" in path else "video"
        return "youtube", kind
    if host.endswith("instagram.com"):
        kind = "reel" if ("/reel" in path or "/tv/" in path) else "post"
        return "instagram", kind
    if host.endswith("tiktok.com"):
        return "tiktok", "video"
    return "web", "article"


def normalize_url(url: str) -> str:
    """Canonical form used for URL dedupe (R40).

    Lowercase host, tracking params stripped, canonical video id for
    YouTube / Instagram / TikTok.
    """
    url = url.strip()
    parsed = urlparse(url)
    host = parsed.netloc.lower().removeprefix("www.").removeprefix("m.")

    vid = _youtube_video_id(parsed)
    if vid:
        return f"https://www.youtube.com/watch?v={vid}"

    if host.endswith("instagram.com"):
        m = re.match(r"^/(?:reels?|p|tv)/([A-Za-z0-9_-]+)", parsed.path)
        if m:
            return f"https://www.instagram.com/reel/{m.group(1)}"

    if host.endswith("tiktok.com") and host not in ("vm.tiktok.com", "vt.tiktok.com"):
        m = re.search(r"/video/(\d+)", parsed.path)
        if m:
            return f"https://www.tiktok.com/video/{m.group(1)}"

    query = [
        (k, v)
        for k, v in parse_qsl(parsed.query, keep_blank_values=True)
        if not k.lower().startswith("utm_") and k.lower() not in TRACKING_PARAMS
    ]
    query.sort()
    scheme = (parsed.scheme or "https").lower()
    netloc = parsed.netloc.lower()
    path = parsed.path.rstrip("/") or "/"
    qs = f"?{urlencode(query)}" if query else ""
    return f"{scheme}://{netloc}{path}{qs}"
