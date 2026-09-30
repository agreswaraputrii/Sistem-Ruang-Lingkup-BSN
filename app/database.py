import sqlite3
from pathlib import Path


# ============================================================
# PATH
# ============================================================

BASE_DIR = Path(__file__).resolve().parent.parent

DATA_DIR = BASE_DIR / "data"

DB_PATH = DATA_DIR / "bsn.db"


# ============================================================
# DATABASE CONNECTION
# ============================================================

def get_connection():

    DATA_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    conn = sqlite3.connect(
        DB_PATH,
        timeout=30,
    )

    conn.row_factory = sqlite3.Row


    # ========================================================
    # FOREIGN KEY
    # ========================================================

    conn.execute(
        "PRAGMA foreign_keys = ON"
    )


    # ========================================================
    # WAIT IF SQLITE IS TEMPORARILY BUSY
    # ========================================================

    conn.execute(
        "PRAGMA busy_timeout = 30000"
    )


    # ========================================================
    # BETTER CONCURRENT READ / WRITE
    # ========================================================

    conn.execute(
        "PRAGMA journal_mode = WAL"
    )


    return conn