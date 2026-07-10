"""Regenerate the knowledge-graph theme (label sizes + light/dark canvas
palette) and the phone PWA icon blobs from their single sources of truth,
into both app/static/graph.js (PC) and cloudflare/worker.js (phone).

Why this exists: the graph canvas draws with plain color values, not CSS, so
each platform has to hand-pick its own palette -- and the PWA icons are
base64-embedded directly in worker.js (kept that way deliberately, so the
file stays paste-able whole into the Cloudflare dashboard as a manual deploy
fallback for friends without Node -- see the file's own header comment).
Both of those are exactly the kind of thing that quietly drifts between two
hand-mirrored copies (a zoom-label sizing bug once got fixed in only one of
the two files). This script makes the *data* single-sourced even though the
*code* stays duplicated (a full de-dup of the rendering code itself would
need a build step / bundler, which would break the manual single-file-paste
deploy path -- not worth that trade for the amount of code involved).

Usage:
    py -3.12 scripts/sync_graph_theme.py            # regenerate + report
    py -3.12 scripts/sync_graph_theme.py --check     # exit 1 if anything is out of sync, change nothing

Source of truth for palette/label sizes: graph_theme.json (repo root).
Source of truth for icons: app/static/icon-192.png / icon-512.png.
"""
import argparse
import base64
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
THEME_JSON = ROOT / "graph_theme.json"
GRAPH_JS = ROOT / "app" / "static" / "graph.js"
WORKER_JS = ROOT / "cloudflare" / "worker.js"
ICON_192_PNG = ROOT / "app" / "static" / "icon-192.png"
ICON_512_PNG = ROOT / "app" / "static" / "icon-512.png"

PALETTE_KEYS = [
    "linkDim", "linkOn", "linkRelated", "linkDefault", "glowIn", "glowOut",
    "hiRing", "nodeStroke", "catFill", "noteFill", "doneFill",
    "catRingOn", "catRingDone", "labelStroke",
]


def between(text, begin_marker, end_marker):
    pattern = re.compile(re.escape(begin_marker) + r"(.*?)" + re.escape(end_marker), re.S)
    m = pattern.search(text)
    if not m:
        raise SystemExit(f"marker pair not found: {begin_marker!r} ... {end_marker!r}")
    return m, pattern


def replace_between(text, begin_marker, end_marker, new_inner):
    m, pattern = between(text, begin_marker, end_marker)
    return pattern.sub(lambda _: begin_marker + new_inner + end_marker, text, count=1)


def render_pc_palette(pal):
    def row(*keys):
        return "      " + " ".join(f'{k}: "{pal[k]}",' for k in keys)
    return (
        "\n"
        + row("linkDim", "linkOn") + "\n"
        + row("linkRelated", "linkDefault") + "\n"
        + row("glowIn", "glowOut") + "\n"
        + row("hiRing", "nodeStroke") + "\n"
        + row("catFill", "noteFill", "doneFill") + "\n"
        + row("catRingOn", "catRingDone") + "\n"
        + f'      labelStroke: "{pal["labelStroke"]}",\n    '
    )


def render_phone_palette(pal):
    def row(*keys, last=False):
        parts = [f"{k}:'{pal[k]}'" for k in keys]
        return "      " + ", ".join(parts) + ("" if last else ",")
    return (
        "\n"
        + row("linkDim", "linkOn") + "\n"
        + row("linkRelated", "linkDefault") + "\n"
        + row("glowIn", "glowOut") + "\n"
        + row("hiRing", "nodeStroke") + "\n"
        + row("catFill", "noteFill", "doneFill") + "\n"
        + row("catRingOn", "catRingDone") + "\n"
        + f"      labelStroke:'{pal['labelStroke']}'\n    "
    )


def build_graph_js(text, theme):
    sizes = theme["labelSizes"]
    text = replace_between(
        text, "  function palette() {", "\n  }",
        (
            "\n    const light = document.documentElement.dataset.theme === \"light\";\n"
            "    return light ? {" + render_pc_palette(theme["paletteLight"]) + "} : {"
            + render_pc_palette(theme["paletteDark"]) + "};"
        ),
    )
    text = replace_between(
        text, "// GRAPH-THEME:SIZES:BEGIN\n  ", "\n  // GRAPH-THEME:SIZES:END",
        "const GRAPH_LABEL_SIZES = { catBase: %d, noteBase: %d, noteFloor: %d };"
        % (sizes["catBase"], sizes["noteBase"], sizes["noteFloor"]),
    )
    return text


def build_worker_js(text, theme):
    sizes = theme["labelSizes"]
    text = replace_between(
        text, "  function gPalette(){", "\n  }",
        (
            "\n    var light = document.documentElement.dataset.theme === 'light';\n"
            "    return light ? {" + render_phone_palette(theme["paletteLight"]) + "} : {"
            + render_phone_palette(theme["paletteDark"]) + "};"
        ),
    )
    text = replace_between(
        text, "// GRAPH-THEME:SIZES:BEGIN\n  ", "\n  // GRAPH-THEME:SIZES:END",
        "var GRAPH_LABEL_SIZES = { catBase: %d, noteBase: %d, noteFloor: %d };"
        % (sizes["catBase"], sizes["noteBase"], sizes["noteFloor"]),
    )
    icon192_b64 = base64.b64encode(ICON_192_PNG.read_bytes()).decode()
    icon512_b64 = base64.b64encode(ICON_512_PNG.read_bytes()).decode()
    text = replace_between(
        text,
        "// GRAPH-THEME:ICONS:BEGIN — regenerated from app/static/icon-192.png / icon-512.png by scripts/sync_graph_theme.py\n",
        "\n// GRAPH-THEME:ICONS:END",
        f'const ICON_192 = "{icon192_b64}";\nconst ICON_512 = "{icon512_b64}";',
    )
    return text


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true",
                     help="exit 1 if regenerating would change anything; write nothing")
    args = ap.parse_args()

    theme = json.loads(THEME_JSON.read_text(encoding="utf-8"))
    for k in PALETTE_KEYS:
        assert k in theme["paletteDark"] and k in theme["paletteLight"], f"missing palette key {k}"

    graph_before = GRAPH_JS.read_text(encoding="utf-8")
    worker_before = WORKER_JS.read_text(encoding="utf-8")
    graph_after = build_graph_js(graph_before, theme)
    worker_after = build_worker_js(worker_before, theme)

    changed = []
    if graph_after != graph_before:
        changed.append("app/static/graph.js")
    if worker_after != worker_before:
        changed.append("cloudflare/worker.js")

    if args.check:
        if changed:
            print("OUT OF SYNC:", ", ".join(changed))
            sys.exit(1)
        print("in sync, nothing to do")
        return

    if "app/static/graph.js" in changed:
        GRAPH_JS.write_text(graph_after, encoding="utf-8")
    if "cloudflare/worker.js" in changed:
        WORKER_JS.write_text(worker_after, encoding="utf-8")
    print("regenerated:", ", ".join(changed) if changed else "nothing changed (already in sync)")


if __name__ == "__main__":
    main()
