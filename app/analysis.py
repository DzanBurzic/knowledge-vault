"""LLM analysis: one structured-output Ollama chat call per item (R25–R29)."""

import json
import re

from . import ollama_client

CONTENT_TYPES = [
    "travel", "coding", "fitness", "recipe", "business",
    "product", "advice", "article", "other",
]

ANALYSIS_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "category_path": {"type": "string"},
        "tags": {"type": "array", "items": {"type": "string"}, "minItems": 3, "maxItems": 6},
        "content_type": {"type": "string", "enum": CONTENT_TYPES},
        "short_description": {"type": "string"},
        "main_points": {
            "type": "array",
            "minItems": 3,
            "maxItems": 6,
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "description": {"type": "string"},
                },
                "required": ["name", "description"],
            },
        },
        "action_items": {"type": "array", "items": {"type": "string"}},
        "entities": {
            "type": "object",
            "properties": {
                "tools": {"type": "array", "items": {"type": "string"}},
                "people": {"type": "array", "items": {"type": "string"}},
                "products": {"type": "array", "items": {"type": "string"}},
                "locations": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["tools", "people", "products", "locations"],
        },
        "duplicate_check_summary": {"type": "string"},
        "suggested_filename": {"type": "string"},
    },
    "required": [
        "title", "category_path", "tags", "content_type", "short_description",
        "main_points", "action_items", "entities", "duplicate_check_summary",
        "suggested_filename",
    ],
}

SYSTEM_PROMPT = """You turn saved content (video transcripts, captions, articles, pasted text) into a short knowledge card. The card must make the content useful WITHOUT rewatching or rereading the source.

THE ONE RULE — SPECIFIC OVER VAGUE:
Main points must contain the ACTUAL information: real names, steps, numbers, prices, places, commands. Never describe the source.
- GOOD: "Recommends Japan, Portugal, Thailand, Italy, Mexico with a short reason each"
- BAD: "This reel discusses good travel destinations."
If the source names 5 places, your points name those 5 places.

Guidance by content type:
- travel: the specific places, costs, and tips mentioned
- coding: the tools, steps, and exact commands
- fitness: the exercises, sets/reps, form cues, and mistakes to avoid
- recipe: the ingredients, steps, and macros if given
- business: the idea, the problem it solves, and how it makes money
- product: product names, what each is for, price, alternatives
- advice: the principle, the concrete takeaway, and when to use it

FIELDS:
- title: short and specific (what the card actually contains, not "Great video about...").
- category_path: a folder path, at most 3 levels, like "Travel/Japan" or "Computer Science/AI/Claude". REUSE the existing categories listed below whenever the content fits one — only propose a new name when nothing existing fits. Reuse the exact spelling of existing names.
- tags: 3-6 lowercase tags.
- content_type: one of travel, coding, fitness, recipe, business, product, advice, article, other.
- short_description: 1-2 plain sentences saying what the card holds.
- main_points: 3-6 points; "name" is a 2-6 word label, "description" is ONE line holding the concrete information.
- action_items: concrete things the user could do with this (may be empty).
- entities: tools, people, products, locations actually named in the source (empty arrays when none).
- duplicate_check_summary: ONE dense sentence naming the concrete contents (used to detect duplicates), e.g. "Five budget travel destinations: Japan, Portugal, Thailand, Italy, Mexico, with cost reasons."
- suggested_filename: kebab-case, e.g. "five-budget-travel-destinations".

Answer with JSON only."""


class AnalysisError(Exception):
    def __init__(self, message: str, raw_output: str = ""):
        super().__init__(message)
        self.raw_output = raw_output


def _clip_text(text: str, limit: int = 24000) -> str:
    if len(text) <= limit:
        return text
    head = int(limit * 0.75)
    tail = limit - head
    return text[:head] + "\n[... middle omitted ...]\n" + text[-tail:]


def build_user_message(source: dict, category_tree_text: str, user_notes: str = "") -> str:
    parts = ["EXISTING CATEGORIES (path — number of notes):"]
    parts.append(category_tree_text or "(none yet — this is the first note)")
    parts.append("\n--- SOURCE MATERIAL ---")
    for label, key in [
        ("Platform", "platform"), ("Title", "title"), ("Uploader/Channel", "uploader"),
    ]:
        if source.get(key):
            parts.append(f"{label}: {source[key]}")
    if source.get("hashtags"):
        parts.append("Hashtags: " + " ".join(source["hashtags"]))
    if source.get("caption"):
        parts.append("\nCaption:\n" + _clip_text(source["caption"], 4000))
    if source.get("description"):
        parts.append("\nDescription:\n" + _clip_text(source["description"], 4000))
    if source.get("transcript"):
        parts.append("\nTranscript (spoken words):\n" + _clip_text(source["transcript"]))
    if source.get("page_text"):
        parts.append("\nArticle text:\n" + _clip_text(source["page_text"]))
    if user_notes:
        parts.append("\nNotes from the user about this item:\n" + user_notes)
    parts.append("\nProduce the knowledge card JSON now.")
    return "\n".join(parts)


def _kebab(text: str) -> str:
    text = re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")
    return text[:80] or "untitled-note"


def _validate(data: dict) -> dict:
    """Normalize the model output; raise ValueError when unusable."""
    if not isinstance(data, dict):
        raise ValueError("output is not a JSON object")
    for key in ("title", "category_path", "short_description", "duplicate_check_summary"):
        if not isinstance(data.get(key), str) or not data[key].strip():
            raise ValueError(f"missing or empty field: {key}")
    points = data.get("main_points")
    if not isinstance(points, list) or not points:
        raise ValueError("main_points missing")
    clean_points = []
    for p in points[:6]:
        if isinstance(p, dict) and str(p.get("name", "")).strip():
            clean_points.append({
                "name": str(p.get("name", "")).strip(),
                "description": str(p.get("description", "")).strip(),
            })
    if not clean_points:
        raise ValueError("main_points unusable")
    data["main_points"] = clean_points

    tags = data.get("tags") or []
    if not isinstance(tags, list):
        raise ValueError("tags is not a list")
    data["tags"] = [str(t).strip().lower() for t in tags if str(t).strip()][:6]

    if data.get("content_type") not in CONTENT_TYPES:
        data["content_type"] = "other"

    items = data.get("action_items") or []
    data["action_items"] = [str(a).strip() for a in items if str(a).strip()] if isinstance(items, list) else []

    ents = data.get("entities") or {}
    if not isinstance(ents, dict):
        ents = {}
    data["entities"] = {
        k: [str(x).strip() for x in (ents.get(k) or []) if str(x).strip()]
        for k in ("tools", "people", "products", "locations")
    }

    data["suggested_filename"] = _kebab(data.get("suggested_filename") or data["title"])
    data["title"] = data["title"].strip()
    data["category_path"] = data["category_path"].strip().strip("/")
    return data


def analyze(cfg: dict, source: dict, category_tree_text: str, user_notes: str = "") -> dict:
    """Run the analysis call; one retry on invalid JSON, then AnalysisError (R25)."""
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": build_user_message(source, category_tree_text, user_notes)},
    ]
    last_raw = ""
    for attempt in (1, 2):
        raw = ollama_client.chat(cfg, messages, schema=ANALYSIS_SCHEMA)
        last_raw = raw
        try:
            return _validate(json.loads(raw))
        except (json.JSONDecodeError, ValueError) as e:
            if attempt == 2:
                raise AnalysisError(
                    f"The AI returned invalid output twice ({e}).", raw_output=last_raw
                ) from e
            messages.append({"role": "assistant", "content": raw})
            messages.append({
                "role": "user",
                "content": f"That output was invalid ({e}). Return the complete, valid JSON object again.",
            })
    raise AnalysisError("The AI returned invalid output twice.", raw_output=last_raw)


def embedding_text(analysis: dict) -> str:
    """Text embedded for dedupe/related/semantic search (R30)."""
    points = "; ".join(
        f"{p['name']}: {p['description']}" for p in analysis.get("main_points", [])
    )
    return f"{analysis['title']}. {analysis['duplicate_check_summary']} {points}"
