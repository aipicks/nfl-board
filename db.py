import sqlite3
import config


def connect():
    config.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(config.DB_PATH)
    con.executescript((config.ROOT / "schema.sql").read_text())
    try:   # migration for databases created before the neutral-site column
        con.execute("ALTER TABLE games ADD COLUMN location TEXT")
    except sqlite3.OperationalError:
        pass
    for col in ("kickoff_utc TEXT", "desc TEXT", "extra TEXT"):   # pred_log columns added after the first release
        try:
            con.execute(f"ALTER TABLE pred_log ADD COLUMN {col}")
        except sqlite3.OperationalError:
            pass
    return con
