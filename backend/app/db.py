from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from typing import Any, Iterator

from .config import DB_PATH, DEFAULT_ADMIN_PASSWORD, DEFAULT_ADMIN_USERNAME
from .security import hash_password


def now() -> str:
    return datetime.utcnow().isoformat(timespec="seconds") + "Z"


@contextmanager
def get_db() -> Iterator[sqlite3.Connection]:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    data = dict(row)
    for key, value in list(data.items()):
        if key.endswith("_json") and isinstance(value, str):
            data[key[:-5]] = json.loads(value)
            del data[key]
    return data


def rows_to_list(rows: list[sqlite3.Row]) -> list[dict[str, Any]]:
    return [row_to_dict(row) for row in rows if row is not None]


def init_db() -> None:
    with get_db() as db:
        db.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              username TEXT NOT NULL UNIQUE,
              password_hash TEXT NOT NULL,
              role TEXT NOT NULL DEFAULT 'user',
              created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS weather_libraries (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              city TEXT NOT NULL,
              year INTEGER NOT NULL DEFAULT 2025,
              remark TEXT,
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL,
              UNIQUE(city, year)
            );

            CREATE TABLE IF NOT EXISTS weather_rows (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              library_id INTEGER NOT NULL REFERENCES weather_libraries(id) ON DELETE CASCADE,
              times INTEGER NOT NULL,
              month INTEGER NOT NULL,
              day INTEGER NOT NULL,
              hour INTEGER NOT NULL,
              date_text TEXT,
              dry REAL NOT NULL,
              rh REAL NOT NULL,
              wb REAL NOT NULL
            );

            CREATE TABLE IF NOT EXISTS projects (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              name TEXT NOT NULL,
              weather_library_id INTEGER NOT NULL REFERENCES weather_libraries(id),
              remark TEXT,
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS systems (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
              name TEXT NOT NULL,
              remark TEXT,
              parameters_json TEXT NOT NULL,
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS simulation_jobs (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              system_id INTEGER NOT NULL REFERENCES systems(id) ON DELETE CASCADE,
              status TEXT NOT NULL,
              progress INTEGER NOT NULL DEFAULT 0,
              message TEXT,
              result_path TEXT,
              error TEXT,
              created_by INTEGER REFERENCES users(id),
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL
            );
            """
        )
        count = db.execute("SELECT COUNT(*) AS c FROM users").fetchone()["c"]
        if count == 0:
            db.execute(
                "INSERT INTO users(username,password_hash,role,created_at) VALUES(?,?,?,?)",
                (DEFAULT_ADMIN_USERNAME, hash_password(DEFAULT_ADMIN_PASSWORD), "admin", now()),
            )
        migrate_weather_schema(db)


def migrate_weather_schema(db: sqlite3.Connection) -> None:
    weather_cols = {row["name"] for row in db.execute("PRAGMA table_info(weather_libraries)").fetchall()}
    row_cols = {row["name"] for row in db.execute("PRAGMA table_info(weather_rows)").fetchall()}
    if "year" not in weather_cols:
        db.execute("ALTER TABLE weather_libraries ADD COLUMN year INTEGER NOT NULL DEFAULT 2025")
    if "date_text" not in row_cols:
        db.execute("ALTER TABLE weather_rows ADD COLUMN date_text TEXT")

    table_sql = db.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='weather_libraries'"
    ).fetchone()["sql"]
    if "city TEXT NOT NULL UNIQUE" in table_sql:
        db.execute("PRAGMA foreign_keys = OFF")
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS weather_libraries_new (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              city TEXT NOT NULL,
              year INTEGER NOT NULL DEFAULT 2025,
              remark TEXT,
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL,
              UNIQUE(city, year)
            )
            """
        )
        db.execute(
            """
            INSERT OR IGNORE INTO weather_libraries_new(id,city,year,remark,created_at,updated_at)
            SELECT id,city,COALESCE(year,2025),remark,created_at,updated_at
            FROM weather_libraries
            """
        )
        db.execute("DROP TABLE weather_libraries")
        db.execute("ALTER TABLE weather_libraries_new RENAME TO weather_libraries")
        db.execute("PRAGMA foreign_keys = ON")
