import os
import sqlite3
import time

from app import backup
from app import db as db_module


def _isolate(monkeypatch, tmp_path):
    data_dir = tmp_path / "data"
    db_path = data_dir / "vault.db"
    monkeypatch.setattr(db_module, "DATA_DIR", data_dir)
    monkeypatch.setattr(db_module, "DB_PATH", db_path)
    db_module.init_db()  # a real, valid sqlite file to back up
    monkeypatch.setattr(backup, "DATA_DIR", data_dir)
    monkeypatch.setattr(backup, "DB_PATH", db_path)
    monkeypatch.setattr(backup, "BACKUP_DIR", data_dir / "backups")
    return data_dir


def test_create_backup_copies_a_valid_db(tmp_path, monkeypatch):
    _isolate(monkeypatch, tmp_path)
    dest = backup.create_backup(reason="test")
    assert dest.exists()
    assert dest.parent == backup.BACKUP_DIR
    conn = sqlite3.connect(dest)
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    conn.close()
    assert "items" in tables


def test_prune_backups_keeps_only_newest(tmp_path, monkeypatch):
    _isolate(monkeypatch, tmp_path)
    backup.BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    for i in range(15):
        f = backup.BACKUP_DIR / f"vault-2026010{i:02d}-000000-manual.db"
        f.write_bytes(b"x")
    backup.prune_backups(keep=10)
    remaining = list(backup.BACKUP_DIR.glob("vault-*.db"))
    assert len(remaining) == 10


def test_list_backups_returns_newest_first(tmp_path, monkeypatch):
    _isolate(monkeypatch, tmp_path)
    d1 = backup.create_backup(reason="one")
    d2 = backup.create_backup(reason="two")
    now = time.time()
    os.utime(d1, (now - 100, now - 100))
    os.utime(d2, (now, now))
    items = backup.list_backups()
    assert items[0]["name"] == d2.name
    assert items[1]["name"] == d1.name


def test_list_backups_empty_when_none_taken(tmp_path, monkeypatch):
    _isolate(monkeypatch, tmp_path)
    assert backup.list_backups() == []
