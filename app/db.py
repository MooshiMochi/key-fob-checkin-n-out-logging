import sqlite3
from contextlib import contextmanager
from pathlib import Path

from .config import cfg


SCHEMA = """
PRAGMA journal_mode=WAL;

CREATE TABLE IF NOT EXISTS uuid_to_encrypted_content (
    uuid TEXT (32) PRIMARY KEY NOT NULL,
    encrypted_content TEXT NOT NULL,
    registered_at TIMESTAMP DEFAULT (datetime('now','localtime'))
);

CREATE TABLE IF NOT EXISTS registered_tags (
    uid INTEGER PRIMARY KEY NOT NULL,
    text_uuid TEXT (32) NOT NULL,
    type TEXT(3) CHECK (type IN ('emp','key')) NOT NULL,
    registered_at TIMESTAMP DEFAULT (datetime('now','localtime')),
    updated_at TIMESTAMP DEFAULT (datetime('now','localtime')),
    active INTEGER DEFAULT 1 CHECK (active IN (0,1)),
    FOREIGN KEY (text_uuid) REFERENCES uuid_to_encrypted_content(uuid)
);

CREATE TABLE IF NOT EXISTS logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tag_uid INTEGER NOT NULL,
    text_uuid TEXT (32),
    employee_text_uuid TEXT (32),
    checkOutTime TIMESTAMP DEFAULT (datetime('now','localtime')),
    checkInTime TIMESTAMP,
    FOREIGN KEY (tag_uid) REFERENCES registered_tags(uid),
    FOREIGN KEY (text_uuid) REFERENCES uuid_to_encrypted_content(uuid)
);
"""


Path(cfg.db_path).parent.mkdir(parents=True, exist_ok=True)


@contextmanager
def get_conn():
    conn = sqlite3.connect(cfg.db_path, detect_types=sqlite3.PARSE_DECLTYPES)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.commit()
        conn.close()


def init_db():
    with sqlite3.connect(cfg.db_path) as conn:
        conn.executescript(SCHEMA)
        conn.commit()
