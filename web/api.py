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

#: Upper bounds on the numbers a caller may send. They are domain bounds, not
#: machine ones — no piece is a day long and nothing is played at ten thousand
#: beats per minute — but the reason they have to exist is machine: Python
#: integers are unbounded and SQLite's are int64, so a `bpm_min` of twenty
#: digits binds fine here and raises `OverflowError` down in the driver, which
#: is not the `ValueError` this layer turns into a 400. Bounded up here, the
#: caller gets told which parameter was wrong instead of a 500.
MAX_BPM = 10_000
MAX_OFFSET = 1_000_000
MAX_LENGTH_S = 86_400

#: How many `filename` parameters one request may carry. This one is not a
#: domain bound at all — it is nginx's. A saved list resolves by naming every
#: piece in it, and each name costs about forty bytes once `%20`-escaped and
#: prefixed with `filename=`, so a long enough list overruns the proxy's
#: request-line buffer and comes back 414 from nginx with nothing from this
#: app in it: an error the page cannot read and the operator cannot find.
#: Bounded here, an over-long list is a 400 that says so, and the caller's job
#: is to ask in batches.
#:
#: The number has to leave the *documented* limit usable, which is why it is
#: not larger: nginx's default request-line buffer is 8 KB, this app's vhost
#: tunes it nowhere, and the vhost a provisioned box actually runs is written
#: by lab980's `provision-site` rather than by anything in this repo — so the
#: bound cannot lean on a proxy setting this repo does not control. A hundred
#: names is about 4 KB, half the buffer, with room for the long ones; two
#: hundred was not, and told callers a number that could still 414 on them.
MAX_FILENAMES = 100

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
    except sqlite3.Error:
        # The file is there and is not a usable database — a truncated build
        # from an older design, or something else entirely under the name.
        # `/api/health` already reports that as "not built"; this route has to
        # agree with it rather than 500 while health says all is well.
        return jsonify({"error": NO_DB, "built": False}), 503
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
    except sqlite3.Error:
        return jsonify({"error": NO_DB, "built": False}), 503   # see facets()
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
#: What a message quotes is the caller's own string, echoed back by `!r`, and
#: rewriting inside it would report a value nobody sent: `since=--foo-bar` came
#: back as "since 'foo_bar' is not a date". So the substitution runs on the
#: prose between the quoted runs and never on the runs themselves.
_CLI_FLAG = re.compile(r"--([a-z][a-z-]*)")
_QUOTED = re.compile(r"'[^']*'")


def _as_param_names(message: str) -> str:
    def flags(text: str) -> str:
        return _CLI_FLAG.sub(lambda m: m.group(1).replace("-", "_"), text)

    out: list[str] = []
    last = 0
    for quoted in _QUOTED.finditer(message):
        out.append(flags(message[last:quoted.start()]))
        out.append(quoted.group(0))         # the caller's value, verbatim
        last = quoted.end()
    out.append(flags(message[last:]))
    return "".join(out)


# ------------------------------------------------------------- query parsing


def _filters(args) -> CAT.Filters:
    """A query string as `Filters`. Every complaint is a `ValueError`."""
    sort = args.get("sort", "title")
    if sort not in CAT.SORTS:
        raise ValueError(f"sort={sort!r} is not one of: {', '.join(sorted(CAT.SORTS))}")
    names = _list(args, "filename")
    if len(names) > MAX_FILENAMES:
        raise ValueError(f"filename was given {len(names)} times, more than the "
                         f"maximum of {MAX_FILENAMES}; ask in batches")
    return CAT.Filters(
        text=args.get("text", "").strip(),
        filenames=tuple(names),
        feels=tuple(_list(args, "feel")),
        feels_any=tuple(_list(args, "feel_any")),
        instruments=tuple(_list(args, "instrument")),
        genres=tuple(_list(args, "genre")),
        collections=tuple(_list(args, "collection")),
        categories=tuple(_list(args, "category")),
        bpm_min=_int(args, "bpm_min", lo=0, hi=MAX_BPM),
        bpm_max=_int(args, "bpm_max", lo=0, hi=MAX_BPM),
        bpm_unknown=_bool(args, "bpm_unknown"),
        length_min=_seconds(args, "min_length"),
        length_max=_seconds(args, "max_length"),
        uploaded_from=args.get("since", "").strip(),
        uploaded_to=args.get("until", "").strip(),
        limit=_int(args, "limit", default=DEFAULT_LIMIT, lo=1, hi=MAX_LIMIT),
        offset=_int(args, "offset", default=0, lo=0, hi=MAX_OFFSET),
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
        value = CAT.parse_duration(raw)
    except ValueError as exc:
        raise ValueError(f"{name}: {exc}") from None
    # `parse_duration` multiplies out to an unbounded Python integer, so
    # "1:99999999999999999999" parses happily and then cannot be bound. Same
    # reason as MAX_BPM above.
    if value > MAX_LENGTH_S:
        raise ValueError(f"{name}={raw!r} is longer than {MAX_LENGTH_S} seconds")
    return value


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
