"""SQLite persistence: datasets and their ordered cleaning steps."""
from __future__ import annotations

import json
import os
import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path

DATA_DIR = Path(os.environ.get("FIXMYCSV_DATA", Path(__file__).resolve().parent.parent / "data"))
DB_PATH = DATA_DIR / "fixmycsv.db"
UPLOAD_DIR = DATA_DIR / "uploads"
_lock = threading.Lock()

SCHEMA = """
CREATE TABLE IF NOT EXISTS datasets (
    id TEXT PRIMARY KEY, name TEXT NOT NULL, filename TEXT NOT NULL, file_path TEXT NOT NULL,
    kind TEXT NOT NULL, sheet TEXT, rows INTEGER, cols INTEGER,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS steps (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    dataset_id TEXT NOT NULL REFERENCES datasets(id) ON DELETE CASCADE,
    position INTEGER NOT NULL, op TEXT NOT NULL, params TEXT NOT NULL, reason TEXT DEFAULT '',
    enabled INTEGER NOT NULL DEFAULT 1, created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_steps_dataset ON steps(dataset_id, position);
"""


def init():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    with connect() as c:
        c.executescript(SCHEMA)


@contextmanager
def connect():
    with _lock:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()


def add_dataset(id_, name, filename, file_path, kind, sheet, rows, cols):
    with connect() as c:
        c.execute("INSERT INTO datasets (id,name,filename,file_path,kind,sheet,rows,cols) VALUES (?,?,?,?,?,?,?,?)",
                  (id_, name, filename, str(file_path), kind, sheet, rows, cols))


def get_dataset(id_):
    with connect() as c:
        row = c.execute("SELECT * FROM datasets WHERE id=?", (id_,)).fetchone()
    return dict(row) if row else None


def list_datasets():
    with connect() as c:
        return [dict(r) for r in c.execute("SELECT * FROM datasets ORDER BY created_at DESC, rowid DESC")]


def delete_dataset(id_):
    ds = get_dataset(id_)
    with connect() as c:
        c.execute("DELETE FROM datasets WHERE id=?", (id_,))
    if ds:
        Path(ds["file_path"]).unlink(missing_ok=True)


def _step(row):
    d = dict(row)
    d["params"] = json.loads(d["params"])
    d["enabled"] = bool(d["enabled"])
    return d


def list_steps(dataset_id):
    with connect() as c:
        return [_step(r) for r in c.execute("SELECT * FROM steps WHERE dataset_id=? ORDER BY position, id", (dataset_id,))]


def add_step(dataset_id, op, params, reason=""):
    with connect() as c:
        pos = c.execute("SELECT COALESCE(MAX(position), -1) + 1 FROM steps WHERE dataset_id=?", (dataset_id,)).fetchone()[0]
        cur = c.execute("INSERT INTO steps (dataset_id, position, op, params, reason) VALUES (?,?,?,?,?)",
                        (dataset_id, pos, op, json.dumps(params), reason))
        return cur.lastrowid


def set_step_enabled(dataset_id, step_id, enabled):
    with connect() as c:
        cur = c.execute("UPDATE steps SET enabled=? WHERE id=? AND dataset_id=?", (int(enabled), step_id, dataset_id))
        return cur.rowcount > 0


def delete_step(dataset_id, step_id):
    with connect() as c:
        cur = c.execute("DELETE FROM steps WHERE id=? AND dataset_id=?", (step_id, dataset_id))
        return cur.rowcount > 0
