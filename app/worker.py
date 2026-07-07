"""Background worker: polls the cloud inbox and processes the queue serially
(R6, R11–R13, R31, R56, R57, R60). Runs as one thread inside the FastAPI
process; never crashes the app.
"""

import threading
import time
import traceback

from . import cloudsync, db, inbox, ollama_client, pipeline
from .config import load_config


class Worker:
    def __init__(self):
        self._thread: threading.Thread | None = None
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._status = {
            "ollama_ok": False,
            "ollama_message": "Not checked yet.",
            "inbox_ok": None,          # None = not configured
            "inbox_message": "The phone inbox is not set up yet.",
            "last_poll": None,
            "current_queue_id": None,
            "current_stage": None,
            "current_label": None,
            "paused": False,
            "cloud_ok": None,          # None = not configured
            "cloud_message": "Phone library not set up yet.",
            "cloud_pending": 0,
        }
        self._last_poll_time = 0.0

    # ------------------------------------------------------------- status

    def get_status(self) -> dict:
        with self._lock:
            return dict(self._status)

    def _set(self, **kw):
        with self._lock:
            self._status.update(kw)

    # ------------------------------------------------------------- control

    def start(self):
        self._recover_interrupted()
        self._thread = threading.Thread(target=self._run, daemon=True, name="kv-worker")
        self._thread.start()

    def stop(self):
        self._stop.set()
        self._wake.set()

    def wake(self):
        """Called when the dashboard enqueues something — process immediately (R14)."""
        self._wake.set()

    def _recover_interrupted(self):
        """R57: items stuck in 'processing' after a kill return to 'queued'."""
        with db.get_conn() as conn:
            conn.execute(
                "UPDATE queue SET state = 'queued', stage = NULL, updated_at = ? "
                "WHERE state = 'processing'",
                (db.now(),),
            )

    # --------------------------------------------------------------- loop

    def _run(self):
        first = True
        while not self._stop.is_set():
            try:
                cfg = load_config()
                # Poll the inbox at startup and every poll_interval (R11).
                interval = max(10, int(cfg.get("poll_interval", 120)))
                if first or time.time() - self._last_poll_time >= interval:
                    self._poll_inbox(cfg)
                    first = False
                self._process_next(cfg)
                self._drain_cloud(cfg)
            except Exception:  # noqa: BLE001 — the worker must never die (R13)
                traceback.print_exc()
                time.sleep(3)
            self._wake.wait(timeout=2)
            self._wake.clear()

    # --------------------------------------------------------------- inbox

    def _poll_inbox(self, cfg: dict):
        self._last_poll_time = time.time()
        if not (cfg.get("inbox_url") and cfg.get("inbox_token")):
            self._set(inbox_ok=None,
                      inbox_message="The phone inbox is not set up yet (see Settings).",
                      last_poll=db.now())
            return
        try:
            items = inbox.fetch_items(cfg)
        except inbox.InboxError as e:
            # R13: log, warn on the dashboard, retry next poll — never crash.
            print(f"[inbox] {e}")
            self._set(inbox_ok=False, inbox_message=str(e), last_poll=db.now())
            return
        pulled_keys = []
        with db.get_conn() as conn:
            for entry in items:  # oldest first (R12)
                pipeline.enqueue(
                    conn,
                    url=(entry.get("url") or "").strip() or None,
                    shared_text=(entry.get("text") or entry.get("title") or "").strip() or None,
                    source="phone",
                    kv_key=entry.get("key"),
                )
                pulled_keys.append(entry.get("key"))
        # Deleted from KV only after the durable SQLite enqueue above (R11).
        try:
            inbox.delete_items(cfg, [k for k in pulled_keys if k])
        except inbox.InboxError as e:
            print(f"[inbox] {e}")  # safe: kv_key UNIQUE makes the next pull idempotent
        self._set(inbox_ok=True, inbox_message="Inbox reachable.", last_poll=db.now())

    # ----------------------------------------------------------- cloud sync

    def _drain_cloud(self, cfg: dict):
        """Push queued card changes to the phone cloud (best-effort; retried)."""
        with db.get_conn() as conn:
            pending = conn.execute(
                "SELECT COUNT(*) AS n FROM cloud_pending"
            ).fetchone()["n"]
        if not cloudsync.configured(cfg):
            self._set(cloud_ok=None, cloud_pending=pending,
                      cloud_message="Phone library not set up yet (see Settings).")
            return
        if pending == 0:
            self._set(cloud_ok=True, cloud_pending=0,
                      cloud_message="Phone library up to date.")
            return
        ok, msg = cloudsync.drain_pending(cfg)
        with db.get_conn() as conn:
            left = conn.execute("SELECT COUNT(*) AS n FROM cloud_pending").fetchone()["n"]
        self._set(cloud_ok=ok, cloud_pending=left, cloud_message=msg)

    # --------------------------------------------------------------- queue

    def _process_next(self, cfg: dict):
        with db.get_conn() as conn:
            row = conn.execute(
                "SELECT * FROM queue WHERE state = 'queued' ORDER BY created_at, id LIMIT 1"
            ).fetchone()
        if not row:
            self._set(current_queue_id=None, current_stage=None, current_label=None)
            return

        # R31: pause while Ollama is down or models are missing.
        ok, msg = ollama_client.status(cfg)
        self._set(ollama_ok=ok, ollama_message=msg, paused=not ok)
        if not ok:
            time.sleep(5)
            return

        label = (row["url"] or (row["shared_text"] or "")[:60] or "pasted text").strip()
        self._set(current_queue_id=row["id"], current_stage="starting", current_label=label)

        def on_stage(stage: str):
            self._set(current_stage=stage)

        try:
            pipeline.process_queue_item(row["id"], on_stage=on_stage)  # serial (R60)
        except ollama_client.OllamaError as e:
            self._set(ollama_ok=False, ollama_message=str(e), paused=True)
        finally:
            self._set(current_queue_id=None, current_stage=None, current_label=None)


WORKER = Worker()
