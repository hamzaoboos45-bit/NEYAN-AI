"""
database/db.py — SQLite connection helper.

Provides a single get_db_connection() function used by all
route modules. Using context managers ensures connections
are always closed after each request.
"""

import sqlite3
import sys
import os

# Allow imports from project root
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import config


def get_db_connection():
    """
    Open and return a configured SQLite connection.

    row_factory = sqlite3.Row lets us access columns by name
    (e.g. row["booking_id"]) instead of positional index.
    """
    # The path comes from config and is absolute/resolved. Create only its
    # parent directory so a clean persistent volume can initialize itself;
    # filesystem permission failures deliberately propagate to the operator.
    config.ensure_database_directory()
    conn = sqlite3.connect(config.DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn
