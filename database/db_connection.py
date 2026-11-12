
import sqlite3
from pathlib import Path
import os

# Find the main project folder
BASE_DIR = Path(__file__).resolve().parent.parent

# Database file location
DB_PATH = Path(os.environ.get(
    "WORKFORCEIQ_DATABASE_PATH",
    BASE_DIR / "data" / "workforceiq.db",
)).resolve()


def get_connection():
    """Create and return a database connection."""
    connection = sqlite3.connect(DB_PATH)
    connection.execute("PRAGMA foreign_keys = ON")
    return connection
