"""
Database connection manager and schema initializer for Atomos.
"""

import sqlite3
from pathlib import Path
from typing import Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
DEFAULT_DB_PATH = PROJECT_ROOT / "data" / "atomos.db"
SCHEMA_PATH = Path(__file__).parent / "schema.sql"


def _apply_migrations(conn: sqlite3.Connection) -> None:
    """Ensure database schema is up-to-date with non-breaking migrations."""
    cur = conn.cursor()
    try:
        cur.execute("PRAGMA table_info(tournaments);")
        columns = [row["name"] for row in cur.fetchall()]
        if columns and "hosting_dates" not in columns:
            cur.execute("ALTER TABLE tournaments ADD COLUMN hosting_dates TEXT;")
            conn.commit()

        # Seed canonical hosting dates if column is empty for existing tournaments
        canonical_dates = {
            1: "June 5–8, 2026",
            2: "Jan 2–5, 2026",
            3: "July 17–20, 2026",
            4: "Aug 22–31, 2026",
            7: "March 13–16, 2026",
            10: "June 19–22, 2026",
            16: "July 3–6, 2026",
            18: "July 31 – Aug 3, 2026",
            44: "Sept 18–21, 2026",
        }
        for tid, dates in canonical_dates.items():
            cur.execute(
                "UPDATE tournaments SET hosting_dates = ? WHERE id = ? AND (hosting_dates IS NULL OR hosting_dates = '');",
                (dates, tid),
            )
        conn.commit()
    except Exception:
        # If tournaments table doesn't exist yet, initialize_database will create it
        pass


def get_connection(db_path: Optional[Path] = None, check_same_thread: bool = True) -> sqlite3.Connection:
    """
    Get a SQLite database connection with foreign keys enabled and Row factory configured.
    Configures WAL mode and a 5000ms busy timeout for concurrent multi-threaded access.
    """
    target_path = db_path or DEFAULT_DB_PATH
    target_path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(str(target_path), check_same_thread=check_same_thread)
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA busy_timeout = 5000;")
    conn.row_factory = sqlite3.Row
    _apply_migrations(conn)
    return conn


def initialize_database(db_path: Optional[Path] = None) -> sqlite3.Connection:
    """
    Create the SQLite database and run the initial schema DDL.
    """
    conn = get_connection(db_path)
    schema_sql = SCHEMA_PATH.read_text(encoding="utf-8")
    conn.executescript(schema_sql)
    conn.commit()
    _apply_migrations(conn)
    return conn
