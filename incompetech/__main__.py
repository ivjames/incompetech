"""`python -m incompetech <command>` — build the catalogue database, query it.

    build   fetch incompetech's pieces.json, normalise it, write the database
            (and check the lookup tables against the catalogue page)
    query   filter it: the axes the catalogue's own page does not offer —
            tempo, duration, collection, category, upload date — and
            --filename, which names pieces instead of describing them
    drift   re-read the catalogue page's lookup tables and report what has
            moved from the transcription in incompetech.py

The database is a build artefact and is gitignored: one command rebuilds it
from one published file. Default path `data/catalog.sqlite3`, overridden by
$INCOMPETECH_DB or `--db`. Everything in the catalogue is CC BY 4.0 to Kevin
MacLeod; `--json` puts a finished credit sentence on every row.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import catalog as CAT
from . import incompetech as I

USER_AGENT = "incompetech-catalog/1 (+https://incompetech.lab980.com)"


#: The duration parser lives in `catalog` so the CLI and the web layer share
#: one, and is re-exported here under the name the CLI's tests know it by.
_duration = CAT.parse_duration


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m incompetech", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    b = sub.add_parser("build", help="fetch the catalogue and write the database")
    b.add_argument("--db", type=Path, default=None,
                   help=f"database path (default: $INCOMPETECH_DB, else {CAT.DEFAULT_DB})")
    b.add_argument("--from-file", type=Path, default=None,
                   help="read pieces.json from disk instead of fetching it")
    b.add_argument("--no-check-lookups", action="store_true",
                   help="skip the second request that checks the genre and "
                        "collection tables against the catalogue page")

    q = sub.add_parser("query", help="filter the catalogue")
    q.add_argument("--db", type=Path, default=None)
    q.add_argument("--text", "-t", default="", help="full-text over title + description")
    q.add_argument("--filename", action="append", default=[],
                   help="an exact filename, the catalogue's only unique field "
                        "(repeatable — they OR). How a saved list of pieces is "
                        "resolved back to rows with a current credit on them")
    q.add_argument("--feel", action="append", default=[],
                   help="require this feel (repeatable — they AND)")
    q.add_argument("--feel-any", action="append", default=[],
                   help="require any one of these feels (repeatable — they OR)")
    q.add_argument("--instrument", action="append", default=[],
                   help="require this instrument, matched as a substring (repeatable — they AND)")
    q.add_argument("--genre", action="append", default=[], help="genre name or id (OR)")
    q.add_argument("--collection", action="append", default=[], help="collection name (OR)")
    q.add_argument("--category", action="append", default=[],
                   help="collection category, e.g. 'Film Scoring Moods' (OR)")
    q.add_argument("--bpm-min", type=int, default=None)
    q.add_argument("--bpm-max", type=int, default=None)
    q.add_argument("--bpm-unknown", action="store_true",
                   help="only the pieces whose tempo the catalogue never measured")
    q.add_argument("--min-length", default=None, help="e.g. 180 or 3:00")
    q.add_argument("--max-length", default=None)
    q.add_argument("--since", default="", help="uploaded on or after (YYYY-MM-DD)")
    q.add_argument("--until", default="", help="uploaded on or before (YYYY-MM-DD)")
    q.add_argument("--limit", type=int, default=25, help="0 for no limit")
    q.add_argument("--offset", type=int, default=0, help="skip this many matches")
    q.add_argument("--sort", default="title", choices=sorted(CAT.SORTS),
                   help="default: title")
    q.add_argument("--desc", action="store_true")
    q.add_argument("--json", action="store_true", help="machine-readable, with URLs and credit")

    d = sub.add_parser("drift", help="check the lookup tables against the catalogue page")
    d.add_argument("--from-file", type=Path, default=None,
                   help="read the catalogue page from disk instead of fetching it")

    args = ap.parse_args(argv)
    if args.cmd == "build":
        return _cmd_build(args)
    if args.cmd == "drift":
        return _cmd_drift(args)
    return _cmd_query(args)


def _client():
    import httpx                                    # noqa: PLC0415 — only the
    return httpx.Client(timeout=60.0, follow_redirects=True,   # fetching paths
                        headers={"User-Agent": USER_AGENT})    # need it


def _cmd_build(args) -> int:
    drift: tuple[str, ...] = ()
    if args.from_file:
        import json                                  # noqa: PLC0415
        rows = json.loads(Path(args.from_file).read_text(encoding="utf-8"))
    else:
        with _client() as client:
            rows = I.fetch_catalog(client)
            if not args.no_check_lookups:
                try:
                    drift = tuple(I.lookup_drift(I.fetch_lookups(client)))
                except Exception as exc:            # noqa: BLE001 — advisory only
                    drift = (f"could not check the lookup tables: {exc}",)

    path = CAT.db_path(args.db)
    stats = CAT.build_file(path, rows)

    print(f"wrote {path}")
    for line in stats.lines():
        print(line)
    if drift:
        print("lookup tables have drifted from the catalogue page:", file=sys.stderr)
        for note in drift:
            print(f"  {note}", file=sys.stderr)
        print("  update incompetech/incompetech.py by hand", file=sys.stderr)
    return 0


def _cmd_drift(args) -> int:
    if args.from_file:
        parsed = I.parse_lookups(Path(args.from_file).read_text(encoding="utf-8"))
    else:
        with _client() as client:
            parsed = I.fetch_lookups(client)
    notes = I.lookup_drift(parsed)
    if not notes:
        print(f"{I.LOOKUPS_URL}: the lookup tables still agree with the page "
              f"({len(I.GENRES)} genres, {len(I.COLLECTIONS)} collections, "
              f"{len(I.FEELS)} feels)")
        return 0
    print("lookup tables have drifted from the catalogue page:", file=sys.stderr)
    for note in notes:
        print(f"  {note}", file=sys.stderr)
    print("  update incompetech/incompetech.py by hand", file=sys.stderr)
    return 1


def _cmd_query(args) -> int:
    path = CAT.db_path(args.db)
    if not path.exists():
        print(f"no database at {path}; run `python -m incompetech build` first",
              file=sys.stderr)
        return 2
    try:
        f = CAT.Filters(
            text=args.text,
            filenames=tuple(args.filename),
            feels=tuple(args.feel),
            feels_any=tuple(args.feel_any),
            instruments=tuple(args.instrument),
            genres=tuple(args.genre),
            collections=tuple(args.collection),
            categories=tuple(args.category),
            bpm_min=args.bpm_min,
            bpm_max=args.bpm_max,
            bpm_unknown=args.bpm_unknown,
            length_min=_duration(args.min_length) if args.min_length else None,
            length_max=_duration(args.max_length) if args.max_length else None,
            uploaded_from=args.since,
            uploaded_to=args.until,
            limit=args.limit,
            offset=args.offset,
            sort=args.sort,
            desc=args.desc,
        )
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    conn = CAT.connect(path)
    try:
        rows = CAT.search(conn, f)
        total = CAT.count(conn, f)
        info = CAT.meta(conn)
    except ValueError as exc:       # a filter that cannot mean anything
        print(f"error: {exc}", file=sys.stderr)
        return 2
    finally:
        conn.close()

    if args.json:
        print(CAT.dump_json(rows, info))
        return 0
    print(CAT.format_rows(rows))
    shown = f"{len(rows)} of {total}" if total != len(rows) else str(total)
    print(f"\n{shown} pieces — {info.get('attribution', '')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
