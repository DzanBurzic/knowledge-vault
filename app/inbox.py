"""Client for the Cloudflare Worker inbox (R10–R13).

Only the shared link/text/title ever lives in the cloud; the PC pulls and
deletes entries once they are durably enqueued in SQLite (R11).
"""

import requests


class InboxError(Exception):
    pass


def _configured(cfg: dict) -> bool:
    return bool(cfg.get("inbox_url") and cfg.get("inbox_token"))


def fetch_items(cfg: dict) -> list[dict]:
    """List waiting shares, oldest first (R12). Raises InboxError when unreachable."""
    if not _configured(cfg):
        raise InboxError("The phone inbox is not set up yet (see Settings).")
    url = cfg["inbox_url"].rstrip("/") + "/inbox"
    try:
        r = requests.get(url, params={"token": cfg["inbox_token"]}, timeout=15)
    except requests.RequestException as e:
        raise InboxError(f"The inbox could not be reached ({e.__class__.__name__}). "
                         "Will retry on the next poll.") from e
    if r.status_code == 401:
        raise InboxError("The inbox rejected the secret token — check Settings.")
    if r.status_code != 200:
        raise InboxError(f"The inbox returned an error (HTTP {r.status_code}).")
    items = r.json().get("items", [])
    return sorted(items, key=lambda x: x.get("ts") or x.get("key", ""))


def delete_items(cfg: dict, keys: list[str]) -> None:
    """Delete pulled entries — called only after SQLite enqueue committed (R11)."""
    if not keys:
        return
    url = cfg["inbox_url"].rstrip("/") + "/delete"
    try:
        r = requests.post(
            url, params={"token": cfg["inbox_token"]}, json={"keys": keys}, timeout=15
        )
        r.raise_for_status()
    except requests.RequestException as e:
        raise InboxError(f"Could not delete pulled items from the inbox: {e}") from e


def test(cfg: dict) -> tuple[bool, str]:
    """Settings-page 'Test inbox' button (R16)."""
    try:
        items = fetch_items(cfg)
        return True, f"Inbox reachable — {len(items)} item(s) waiting."
    except InboxError as e:
        return False, str(e)
