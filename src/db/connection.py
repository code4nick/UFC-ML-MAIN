from __future__ import annotations

import sqlite3
from pathlib import Path

from src.config import DEFAULT_DB_PATH
from src.db.schema import SCHEMA_SQL


def get_connection(db_path: Path | None = None) -> sqlite3.Connection:
    path = db_path or DEFAULT_DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(db_path: Path | None = None) -> Path:
    path = db_path or DEFAULT_DB_PATH
    with get_connection(path) as conn:
        conn.executescript(SCHEMA_SQL)
        conn.commit()
    return path
