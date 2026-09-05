"""Getting at the catalogue database from a request.

**A connection per request, never one held open.** The database is a build
artefact: `python -m incompetech build` writes a new file beside this one and
`os.replace`s it into place while the server is running. A long-lived
connection would go on reading the replaced inode for the life of the process
— serving yesterday's catalogue from a file that no longer has a name — and a
`sqlite3.Connection` is not safe to share between threads anyway. Opening one
per request costs microseconds against a local file and means a rebuild is
visible on the very next request.

The other half of the same fact: **the database may not exist**. The app has
to start and answer before anyone has ever run a build, so `open_db` returns
None rather than raising, and every route decides for itself what that means.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from flask import current_app

from incompetech import catalog as CAT

DB_CONFIG_KEY = "INCOMPETECH_DB_PATH"


def db_path() -> Path:
    """Where this app's database is — snapshotted into config at startup.

    Read from the config rather than the environment so a test can inject a
    path and so no route reads `os.environ` mid-request.
    """
    return Path(current_app.config[DB_CONFIG_KEY])


def open_db() -> sqlite3.Connection | None:
    """A fresh read connection, or None if there is no database yet."""
    path = db_path()
    if not path.exists():
        return None
    # Read-only, and `nolock` is deliberately NOT set: the file is replaced
    # whole rather than written in place, so ordinary locking is right and
    # cheap. A URI connection refuses to create the file if it vanished
    # between the check above and here.
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


#: Health with nothing behind it. The database's path is deliberately NOT in
#: here: /api/health is anonymous and unauthenticated, and where a file sits on
#: someone's server is their business, not a spectator's. `bin/incompetech`
#: resolves the path from `.env` itself and parses only the `built` flag out of
#: this document, so nothing needed it.
_EMPTY = {"built": False, "pieces": 0, "built_at": None, "fts": False}


def stats() -> dict:
    """What `/api/health` says about the database, whether or not there is one."""
    conn = open_db()
    if conn is None:
        return _EMPTY.copy()
    try:
        meta = CAT.meta(conn)
        pieces = conn.execute("SELECT count(*) FROM piece").fetchone()[0]
        return {"built": True, "pieces": pieces,
                "built_at": meta.get("fetched_at"),
                "fts": bool(meta.get("fts")) and CAT.have_fts5(conn)}
    except sqlite3.Error:
        # A file that is not a database, or one from a schema this code no
        # longer knows. Health stays 200 and says the truth: nothing usable.
        return _EMPTY.copy()
    finally:
        conn.close()
