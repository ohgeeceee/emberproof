"""SQLite storage layer.

One file, no server, no migrations framework. Schema changes are applied by
bumping SCHEMA_VERSION and adding the statements to MIGRATIONS.
"""

from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timezone

SCHEMA_VERSION = 1

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS property (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    name           TEXT NOT NULL,
    address        TEXT,
    insurer        TEXT,
    policy_number  TEXT,
    created_at     TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS room (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    property_id INTEGER NOT NULL REFERENCES property(id) ON DELETE CASCADE,
    name        TEXT NOT NULL,
    sort        INTEGER NOT NULL DEFAULT 0,
    created_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS item (
    id                     INTEGER PRIMARY KEY AUTOINCREMENT,
    room_id                INTEGER NOT NULL REFERENCES room(id) ON DELETE CASCADE,
    name                   TEXT NOT NULL,
    category               TEXT NOT NULL DEFAULT 'other',
    description            TEXT,
    brand                  TEXT,
    model                  TEXT,
    serial                 TEXT,
    quantity               INTEGER NOT NULL DEFAULT 1,
    purchase_date          TEXT,
    purchase_price_cents   INTEGER,
    replacement_value_cents INTEGER,
    value_source           TEXT NOT NULL DEFAULT 'estimate',
    notes                  TEXT,
    created_at             TEXT NOT NULL,
    updated_at             TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS photo (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    item_id    INTEGER NOT NULL REFERENCES item(id) ON DELETE CASCADE,
    filename   TEXT NOT NULL,
    sha256     TEXT NOT NULL,
    width      INTEGER,
    height     INTEGER,
    bytes      INTEGER,
    taken_at   TEXT,
    sort       INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS document (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    item_id     INTEGER REFERENCES item(id) ON DELETE CASCADE,
    property_id INTEGER REFERENCES property(id) ON DELETE CASCADE,
    kind        TEXT NOT NULL DEFAULT 'receipt',
    filename    TEXT NOT NULL,
    sha256      TEXT NOT NULL,
    bytes       INTEGER,
    created_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS export (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    property_id       INTEGER NOT NULL REFERENCES property(id) ON DELETE CASCADE,
    kind              TEXT NOT NULL,
    filename          TEXT NOT NULL,
    item_count        INTEGER NOT NULL,
    total_value_cents INTEGER NOT NULL,
    sha256            TEXT,
    created_at        TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_room_property  ON room(property_id);
CREATE INDEX IF NOT EXISTS idx_item_room      ON item(room_id);
CREATE INDEX IF NOT EXISTS idx_item_category  ON item(category);
CREATE INDEX IF NOT EXISTS idx_photo_item     ON photo(item_id);
CREATE INDEX IF NOT EXISTS idx_document_item  ON document(item_id);
CREATE INDEX IF NOT EXISTS idx_document_prop  ON document(property_id);
CREATE INDEX IF NOT EXISTS idx_export_prop    ON export(property_id);
"""


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def connect(db_path: str) -> sqlite3.Connection:
    """Open a connection with sane defaults (FKs on, dict-ish rows)."""
    os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")
    return conn


def init_db(db_path: str) -> None:
    conn = connect(db_path)
    try:
        conn.executescript(SCHEMA)
        row = conn.execute("SELECT value FROM meta WHERE key = 'schema_version'").fetchone()
        if row is None:
            conn.execute(
                "INSERT INTO meta (key, value) VALUES ('schema_version', ?)",
                (str(SCHEMA_VERSION),),
            )
        conn.commit()
    finally:
        conn.close()