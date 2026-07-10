"""Code staleness stamp.

run_app.py compares the stamp a running server reports (frozen when that
process imported the app) against a fresh computation from disk. A mismatch
means the server is running outdated code and should be restarted.

Only .py files count: templates and static assets are re-read from disk on
every request, so they never make a running server stale.
"""

from pathlib import Path

APP_DIR = Path(__file__).parent


def code_stamp() -> str:
    """Newest mtime among the app's .py files, as an integer string."""
    try:
        newest = max(p.stat().st_mtime for p in APP_DIR.rglob("*.py"))
    except ValueError:
        newest = 0
    return str(int(newest))
