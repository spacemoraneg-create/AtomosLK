"""
Database connection manager and schema initializer for Atomos.
"""

import sqlite3
from pathlib import Path
from typing import Optional

DEFAULT_DB_PATH = Path("data/atomos.db")
SCHEMA_PATH = Path(__file__).parent / "schema.sql"


def get_connection(db_path: Optional[Path] = None, check_same_thread: bool = True) -> sqlite3.Connection:
    """
    Get a SQLite database connection with foreign keys enabled and Row factory configured.
    """
    target_path = db_path or DEFAULT_DB_PATH
    target_path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(str(target_path), check_same_thread=check_same_thread)
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.row_factory = sqlite3.Row
    return conn


def initialize_database(db_path: Optional[Path] = None) -> sqlite3.Connection:
    """
    Create the SQLite database and run the initial schema DDL.
    """
    conn = get_connection(db_path)
    schema_sql = SCHEMA_PATH.read_text(encoding="utf-8")
    conn.executescript(schema_sql)
    conn.commit()
    return conn
