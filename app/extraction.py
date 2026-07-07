"""Content extraction per platform (R17–R24).

Produces an ExtractionResult holding raw material (stored in SQLite only,
never in the vault — R24) plus a user-friendly error when the item needs
manual input (R22).
"""

import json
import os
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from .config import TMP_DIR
from .urltools import detect_platform, normalize_url

# yt-dlp / ffmpeg are winget-installed; their links dir may be missing from
# PATH in sessions started before the install.
WINGET_LINKS = Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "WinGet" / "Links"
if WINGET_LINKS.exists():
    os.environ["PATH"] = f"{WINGET_LINKS}{os.pathsep}{os.environ.get('PATH', '')}"

_whisper_model = None
_whisper_size = None


@dataclass
class ExtractionResult:
    platform: str = "manual"
    kind: str = "text"
    title: str = ""
    uploader: str = ""
    caption: str = ""
    description: str = ""
    transcript: str = ""
    page_text: str = ""
    hashtags: list = field(default_factory=list)
    metadata: dict = field(default_factory=dict)
    log: list = field(default_factory=list)
    extraction_status: str = "full"  # full | partial | caption_only | manual
    error: str | None = None  # set => item needs manual input (needs_input)

    def add_log(self, msg: str):
        self.log.append(msg)

    def has_content(self) -> bool:
        return bool(
            (self.transcript or "").strip()
            or (self.page_text or "").strip()
            or (self.caption or "").strip()
            or (self.description or "").strip()
        )

    def source_dict(self) -> dict:
        return {
            "platform": self.platform,
            "title": self.title,
            "uploader": self.uploader,
            "caption": self.caption,
            "description": self.description,
            "transcript": self.transcript,
            "page_text": self.page_text,
            "hashtags": self.hashtags,
        }


# ------------------------------------------------------------------ helpers

def _run(cmd: list[str], timeout: int = 900) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd, capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=timeout,
    )


def _ytdlp_json(url: str, download: bool) -> tuple[dict | None, str]:
    """Run yt-dlp; return (metadata, error_text). Downloads into TMP_DIR when asked."""
    TMP_DIR.mkdir(parents=True, exist_ok=True)
    cmd = ["yt-dlp", "--no-playlist"]
    if download:
        cmd += ["--no-simulate", "--print-json", "-f", "bestaudio/best",
                "-o", str(TMP_DIR / "%(id)s.%(ext)s")]
    else:
        cmd += ["--skip-download", "--dump-json"]
    cmd.append(url)
    try:
        result = _run(cmd)
    except subprocess.TimeoutExpired:
        return None, "The download took too long and was stopped."
    except FileNotFoundError:
        return None, "yt-dlp is not installed on this PC (run the setup again)."
    if result.returncode != 0:
        return None, (result.stderr or result.stdout or "unknown yt-dlp error")[-1200:]
    try:
        return json.loads(result.stdout.splitlines()[0]), ""
    except (json.JSONDecodeError, IndexError):
        return None, "yt-dlp returned no metadata."


def _downloaded_file(info: dict) -> Path | None:
    candidates = [
        info.get("requested_downloads", [{}])[0].get("filepath"),
        info.get("_filename"),
    ]
    for c in candidates:
        if c and Path(c).exists():
            return Path(c)
    matches = list(TMP_DIR.glob(f"{info.get('id', '???')}.*"))
    return matches[0] if matches else None


def _transcribe(media_path: Path, whisper_size: str, on_stage=None) -> str:
    """faster-whisper, small, English, CPU int8 (proven on this PC — R19)."""
    global _whisper_model, _whisper_size
    from faster_whisper import WhisperModel

    if _whisper_model is None or _whisper_size != whisper_size:
        _whisper_model = WhisperModel(whisper_size, device="cpu", compute_type="int8")
        _whisper_size = whisper_size
    if on_stage:
        on_stage("transcribing")
    segments, _info = _whisper_model.transcribe(
        str(media_path), vad_filter=True, language="en"
    )
    return " ".join(seg.text.strip() for seg in segments).strip()


def _friendly_download_error(raw: str) -> str:
    low = (raw or "").lower()
    if "login" in low or "cookies" in low or "rate-limit" in low or "rate limit" in low:
        return ("The platform blocked the download (login wall or rate limit). "
                "Paste the caption or transcript below and the card will still be created.")
    if "private" in low:
        return ("This video is private, so it can't be downloaded. "
                "Paste its caption or transcript below to save it anyway.")
    if "unavailable" in low or "removed" in low or "404" in low or "not exist" in low:
        return ("This video seems deleted or unavailable. "
                "Paste its caption or transcript below to save it anyway.")
    if "geo" in low or "country" in low:
        return ("This video is not available in your region. "
                "Paste its caption or transcript below to save it anyway.")
    return ("The content could not be downloaded automatically. "
            "Paste the caption, transcript or text below to save it anyway.")


def _meta_fields(res: ExtractionResult, info: dict):
    res.title = info.get("title") or res.title
    res.uploader = info.get("uploader") or info.get("channel") or ""
    res.description = info.get("description") or ""
    res.caption = res.caption or res.description  # reels/tiktok use description as caption
    res.hashtags = info.get("tags") or []
    res.metadata = {
        k: info.get(k)
        for k in ("id", "title", "uploader", "channel", "upload_date", "duration",
                  "webpage_url", "tags", "view_count")
        if info.get(k) is not None
    }


# ------------------------------------------------------------ per platform

def _extract_youtube_video(url: str, res: ExtractionResult, cfg: dict, on_stage=None):
    """R18: transcript API fast path, whisper fallback; metadata via yt-dlp."""
    from urllib.parse import urlparse

    from .urltools import _youtube_video_id

    video_id = _youtube_video_id(urlparse(normalize_url(url)))
    transcript = ""
    if video_id:
        try:
            from youtube_transcript_api import YouTubeTranscriptApi
            try:
                fetched = YouTubeTranscriptApi().fetch(video_id, languages=["en"])
                transcript = " ".join(s.text for s in fetched).strip()
            except AttributeError:  # older library versions
                data = YouTubeTranscriptApi.get_transcript(video_id, languages=["en"])
                transcript = " ".join(s["text"] for s in data).strip()
            res.add_log("YouTube transcript fetched via youtube-transcript-api (fast path).")
        except Exception as e:  # noqa: BLE001 - any failure falls back to whisper
            res.add_log(f"No ready transcript ({type(e).__name__}); falling back to audio download.")

    info, err = _ytdlp_json(url, download=False)
    if info:
        _meta_fields(res, info)
        res.add_log("Metadata captured via yt-dlp.")
    else:
        res.add_log(f"yt-dlp metadata failed: {err}")

    if transcript:
        res.transcript = transcript
        res.extraction_status = "full" if info else "partial"
        return

    if on_stage:
        on_stage("downloading")
    info2, err2 = _ytdlp_json(url, download=True)
    if not info2:
        res.add_log(f"Audio download failed: {err2}")
        if res.description or res.caption:
            res.extraction_status = "caption_only"
            res.add_log("Proceeding with caption/description only.")
        else:
            res.error = _friendly_download_error(err2)
        return
    if not res.metadata:
        _meta_fields(res, info2)
    media = _downloaded_file(info2)
    if media:
        try:
            res.transcript = _transcribe(media, cfg["whisper_model"], on_stage)
            res.add_log("Transcribed with faster-whisper.")
        finally:
            media.unlink(missing_ok=True)  # temp media deleted after transcription (R59)
    if res.transcript:
        res.extraction_status = "full"
    elif res.description or res.caption:
        res.extraction_status = "caption_only"
        res.add_log("No speech found; using caption/description.")
    else:
        res.error = ("No speech and no caption could be extracted from this video. "
                     "Paste a description below to save it anyway.")


def _extract_media(url: str, res: ExtractionResult, cfg: dict, on_stage=None):
    """R19: Instagram / TikTok / YouTube Shorts via yt-dlp + faster-whisper."""
    if on_stage:
        on_stage("downloading")
    info, err = _ytdlp_json(url, download=True)
    if not info:
        # Media failed; try metadata alone → caption-only path (R22).
        meta, _meta_err = _ytdlp_json(url, download=False)
        if meta:
            _meta_fields(res, meta)
        if res.caption or res.description:
            res.extraction_status = "caption_only"
            res.add_log(f"Download failed ({err[:200]}); caption retrieved, proceeding caption-only.")
        else:
            res.add_log(f"Download failed: {err}")
            res.error = _friendly_download_error(err)
        return
    _meta_fields(res, info)
    media = _downloaded_file(info)
    if media:
        try:
            res.transcript = _transcribe(media, cfg["whisper_model"], on_stage)
            res.add_log("Downloaded and transcribed with faster-whisper.")
        finally:
            media.unlink(missing_ok=True)  # temp media deleted after transcription (R59)
    if res.transcript:
        res.extraction_status = "full"
    elif res.caption or res.description:
        # Silent video (music only) → analyze from caption + description.
        res.extraction_status = "caption_only"
        res.add_log("No speech detected (music only?); using caption/description.")
    else:
        res.error = ("This video has no speech and no caption. "
                     "Paste what it showed below to save it anyway.")


def _extract_article(url: str, res: ExtractionResult, on_stage=None):
    """R20: readable text + title via trafilatura; < 200 chars = failure (R22)."""
    if on_stage:
        on_stage("downloading")
    try:
        import trafilatura
        downloaded = trafilatura.fetch_url(url)
        if downloaded:
            extracted = trafilatura.extract(
                downloaded, output_format="json", with_metadata=True,
                include_comments=False,
            )
            if extracted:
                data = json.loads(extracted)
                res.title = data.get("title") or ""
                res.uploader = data.get("author") or data.get("sitename") or ""
                res.page_text = (data.get("text") or "").strip()
                res.metadata = {k: data.get(k) for k in ("title", "author", "date", "sitename")
                                if data.get(k)}
    except Exception as e:  # noqa: BLE001
        res.add_log(f"Article extraction error: {e}")
    if len(res.page_text) < 200:
        res.add_log(f"Article text too short ({len(res.page_text)} chars).")
        res.error = ("The article text could not be read (it may be behind a paywall "
                     "or blocked). Paste the article text below to save it anyway.")
    else:
        res.extraction_status = "full" if res.title else "partial"
        res.add_log(f"Article extracted ({len(res.page_text)} chars).")


# ------------------------------------------------------------------- entry

def extract_from_url(url: str, cfg: dict, on_stage=None) -> ExtractionResult:
    platform, kind = detect_platform(url)
    res = ExtractionResult(platform=platform, kind=kind)
    res.add_log(f"Detected platform: {platform} ({kind}).")
    if platform == "youtube" and kind == "video":
        _extract_youtube_video(url, res, cfg, on_stage)
    elif platform in ("instagram", "tiktok") or (platform == "youtube" and kind == "short"):
        _extract_media(url, res, cfg, on_stage)
    else:
        _extract_article(url, res, on_stage)
    return res


def extract_from_text(text: str) -> ExtractionResult:
    """R21: pasted text used as-is; platform 'manual'."""
    res = ExtractionResult(platform="manual", kind="text", page_text=text.strip(),
                           extraction_status="manual")
    res.add_log("Pasted text used as source material.")
    return res
