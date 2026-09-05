"""The JSON API, and the one page that reads it.

Four endpoints and an index. The filters are the CLI's filters — the same
`Filters` dataclass, the same `search` — so a query typed into the page and
the same query typed at a shell cannot disagree. This module's whole job is
turning query strings into that dataclass and its `ValueError`s into 400s.

Two rules run through it:

* **A filter that cannot mean anything is a 400 with the reason in it**, never
  a 500 and never a silently dropped clause. `search` raises `ValueError` for
  the combinations that ask opposite things (`bpm_unknown` with a tempo range,
  a text that tokenises to no word, a date bound that is not a date); this
  layer adds the ones argparse would have caught, like a sort nobody defines.
* **The credit rides on every piece.** It is a licence condition, so a row
  that leaves this API carries the sentence rather than the caller being
  trusted to rebuild it.
"""

from __future__ import annotations

import re
import sqlite3

from flask import Blueprint, current_app, jsonify, request, send_from_directory

from incompetech import catalog as CAT
from incompetech import incompetech as I

from .db import open_db, stats

bp = Blueprint("api", __name__)

#: What a page may ask for at once. The whole catalogue is ~1400 rows, so this
#: is not protecting the database — it is keeping one accidental `limit=100000`
#: from building a 40 MB JSON document in memory.
MAX_LIMIT = 500
DEFAULT_LIMIT = 50

NO_DB = ("no catalogue database yet — run `python -m incompetech build` "
         "(or `incompetech build` on the droplet)")


@bp.get("/")
def index():
    return send_from_directory(current_app.static_folder, "index.html")


@bp.get("/api/health")
def health():
    """200 whether or not there is a database.

    The app has to start and answer before anyone has run a build — that is
    the state a fresh droplet is in between `deploy` and `build`, and a health
    check that fails there would report the site down when it is up and
    waiting.
    """
    return jsonify({"ok": True, **stats()})


@bp.get("/api/meta")
def meta():
    """Where the data came from, when, and under what licence."""
    doc = {
        "source": I.CATALOG_URL,
        "lookups": I.LOOKUPS_URL,
        "author": I.AUTHOR,
        "license": I.LICENSE,
        "license_url": I.LICENSE_URL,
        "license_name": "Creative Commons Attribution 4.0",
        "attribution": f"Music by {I.AUTHOR} (incompetech.com), licensed under "
                       f"Creative Commons: By Attribution 4.0",
        "fetched_at": None,
        "built": False,
    }
    conn = open_db()
    if conn is not None:
        try:
            doc.update({k: v for k, v in CAT.meta(conn).items() if v})
            doc["built"] = True
        except sqlite3.Error:
            pass
        finally:
            conn.close()
    return jsonify(doc)


@bp.get("/api/facets")
def facets():
    """Everything the controls are built from. Nothing is hardcoded in the JS."""
    conn = open_db()
    if conn is None:
        return jsonify({"error": NO_DB, "built": False}), 503
    try:
        return jsonify({"built": True, **CAT.facets(conn)})
    finally:
        conn.close()


@bp.get("/api/pieces")
def pieces():
    conn = open_db()
    if conn is None:
        return jsonify({"error": NO_DB, "built": False}), 503
    try:
        filters = _filters(request.args)
        rows = CAT.search(conn, filters)
        total = CAT.count(conn, filters)
    except ValueError as exc:
        return jsonify({"error": _as_param_names(str(exc))}), 400
    finally:
        conn.close()
    return jsonify({
        "total": total,
        "limit": filters.limit,
        "offset": filters.offset,
        "pieces": [_public(r) for r in rows],
    })


#: `catalog.search` raises its refusals in the CLI's spelling, because that is
#: where they were first read — "--bpm-unknown cannot be combined with
#: --bpm-min". Over HTTP nobody typed a flag, so the message is respelled as
#: the parameter the caller actually sent. One substitution, in the layer that
#: knows the difference, rather than a second set of messages in the library.
_CLI_FLAG = re.compile(r"--([a-z][a-z-]*)")


def _as_param_names(message: str) -> str:
    return _CLI_FLAG.sub(lambda m: m.group(1).replace("-", "_"), message)


# ------------------------------------------------------------- query parsing


def _filters(args) -> CAT.Filters:
    """A query string as `Filters`. Every complaint is a `ValueError`."""
    sort = args.get("sort", "title")
    if sort not in CAT.SORTS:
        raise ValueError(f"sort={sort!r} is not one of: {', '.join(sorted(CAT.SORTS))}")
    return CAT.Filters(
        text=args.get("text", "").strip(),
        feels=tuple(_list(args, "feel")),
        feels_any=tuple(_list(args, "feel_any")),
        instruments=tuple(_list(args, "instrument")),
        genres=tuple(_list(args, "genre")),
        collections=tuple(_list(args, "collection")),
        categories=tuple(_list(args, "category")),
        bpm_min=_int(args, "bpm_min"),
        bpm_max=_int(args, "bpm_max"),
        bpm_unknown=_bool(args, "bpm_unknown"),
        length_min=_seconds(args, "min_length"),
        length_max=_seconds(args, "max_length"),
        uploaded_from=args.get("since", "").strip(),
        uploaded_to=args.get("until", "").strip(),
        limit=_int(args, "limit", default=DEFAULT_LIMIT, lo=1, hi=MAX_LIMIT),
        offset=_int(args, "offset", default=0, lo=0),
        sort=sort,
        desc=_bool(args, "desc"),
    )


def _list(args, name: str) -> list[str]:
    """A repeated parameter, blanks dropped. `?feel=Dark&feel=Eerie`."""
    return [v.strip() for v in args.getlist(name) if v.strip()]


def _bool(args, name: str) -> bool:
    """Present-and-not-a-negative. `?bpm_unknown`, `=1`, `=true` all mean yes."""
    if name not in args:
        return False
    return args.get(name, "").strip().lower() not in ("0", "false", "no", "off")


def _int(args, name: str, *, default=None, lo: int | None = None,
         hi: int | None = None):
    raw = args.get(name, "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        raise ValueError(f"{name}={raw!r} is not a whole number") from None
    if lo is not None and value < lo:
        raise ValueError(f"{name}={value} is below the minimum of {lo}")
    if hi is not None and value > hi:
        raise ValueError(f"{name}={value} is above the maximum of {hi}")
    return value


def _seconds(args, name: str):
    raw = args.get(name, "").strip()
    if not raw:
        return None
    try:
        return CAT.parse_duration(raw)
    except ValueError as exc:
        raise ValueError(f"{name}: {exc}") from None


# ------------------------------------------------------------------ shaping


#: The columns a piece goes out with. Everything the page shows, everything a
#: script would want, and nothing that would mislead — `wav_link` is left off
#: on purpose (it is not a WAV and not a working audio URL; see
#: incompetech.py), and `genre_raw`/`collection_raw` are build diagnostics.
FIELDS = (
    "filename", "title", "uuid", "isrc", "length_s", "bpm", "description",
    "uploaded", "genre", "collection", "collection_category", "mp3_url",
    "page_url", "video_url", "sheetmusic_url", "itunes_url", "filmmusic_url",
    "feels", "instruments", "credit",
)


def _public(row: dict) -> dict:
    return {k: row.get(k) for k in FIELDS}
