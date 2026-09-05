# incompetech catalog

A filterable database over Kevin MacLeod's royalty-free music catalogue
([incompetech.com](https://incompetech.com/music/royalty-free/music.html)).

His own page searches one lowercased substring over title, instruments and
description and ANDs a set of mood chips. It offers **no tempo, duration,
collection, category or upload-date filter at all** — which are exactly the
axes a piece gets chosen on when you are looking for something to put under
something. So the catalogue he publishes whole as
[`pieces.json`](https://incompetech.com/music/royalty-free/pieces.json) is
normalised into SQLite once and queried locally after that: 1400-odd pieces,
one row each keyed by filename, genre and collection resolved to names,
instruments and feels as relations, and full-text search over title and
description.

Live at **[incompetech.lab980.com](https://incompetech.lab980.com)**. Previews
play from incompetech.com's own URLs — this indexes the catalogue, it does not
rehost it.

## Getting it running

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python -m incompetech build        # two requests, ~1 MB, no key
.venv/bin/python -m web.app                  # http://127.0.0.1:8072
```

The database lands at `data/catalog.sqlite3` (`$INCOMPETECH_DB` or `--db`
moves it). It is a build artefact and is gitignored: one command rebuilds it,
and it is written beside the target and renamed into place, so a rebuild under
the running server is safe.

## The CLI

```bash
python -m incompetech build [--db PATH] [--from-file pieces.json] [--no-check-lookups]
python -m incompetech query [filters...]
python -m incompetech drift
```

Filters AND with each other. `--feel` repeats to mean *all of these* (which is
the point of the relation), `--feel-any` to mean *any of these*; `--instrument`
repeats and matches as a substring, so `--instrument drum` finds Drums and Log
Drums. `--genre`, `--collection` and `--category` OR within themselves.

```bash
# dark and eerie, slow, long enough to loop under a scene
python -m incompetech query --feel Dark --feel Eerie --bpm-max 90 \
    --min-length 3:00 --sort bpm

# the film-scoring shelf, chase tempo, nothing short
python -m incompetech query --category "Film Scoring Moods" --feel Suspenseful \
    --bpm-min 120 --min-length 2:00 --sort length --desc

# what has he added lately?
python -m incompetech query --since 2025-01-01 --feel-any Dark --feel-any Eerie \
    --sort uploaded --desc
```

`--json` is the scriptable form: whole rows, URLs, and a finished credit
sentence on each. `--bpm-unknown` asks for the pieces whose tempo was never
measured; `--text` is FTS5 where the interpreter has it and a LIKE scan where
it does not, and both AND their words.

A filter that cannot mean anything is refused with the reason rather than
silently dropped — `--bpm-unknown` with a tempo range, `--since 2019` (not a
date), `--text '*'` (no word in it).

## The API

Read-only, no auth, JSON, `Cache-Control: no-store`.

| route | what it gives |
|---|---|
| `GET /api/health` | `{"ok": true, "built": bool, "pieces": N, "built_at": ..., "fts": bool}`. **200 even with no database** — the app answers before the first build |
| `GET /api/pieces` | the filters above as query params: `text`, repeated `feel` (AND) and `feel_any` (OR), `instrument`, `genre`, `collection`, `category`, `bpm_min`/`bpm_max`/`bpm_unknown`, `min_length`/`max_length`, `since`/`until`, `sort`, `desc`, `limit`/`offset`. Returns `{"total": N, "pieces": [...]}`, each piece with its resolved genre, collection and category, feels, instruments, `mp3_url`, `page_url` and `credit`. A filter that cannot mean anything is a **400 with the reason**, never a 500 |
| `GET /api/facets` | the feels (counts, and whether each is one of the catalogue's own 20 words), genres, collections grouped by category, instruments with counts — what the page builds its controls from |
| `GET /api/meta` | source URLs, when it was fetched, the licence and the attribution |

```bash
curl -s 'https://incompetech.lab980.com/api/pieces?feel=Dark&feel=Eerie&bpm_max=90&min_length=180'
```

## Layout

```
incompetech/     the library — imports Flask nowhere
  incompetech.py   the lookup tables, the URL builders, the normaliser
  catalog.py       schema, build, filters, facets
  __main__.py      build | query | drift
web/             the Flask app — factory, routes, and three static files
tests/           the package tests, and the shared fixture rows
web/tests/       the routes, over a database built from those rows
bin/incompetech  the operate CLI for the droplet (see DEPLOY.md)
```

The layering is one-way: `web` → `incompetech`. The CLI and the site are two
callers of the same filters rather than two implementations of them.

## Licence

Everything in the catalogue is **CC BY 4.0** to Kevin MacLeod. Attribution is a
condition of using any of it, so the credit sentence rides on every row that
leaves the database and the credit line is on the page at all times:

> Music by Kevin MacLeod (incompetech.com), licensed under Creative Commons: By
> Attribution 4.0

The code in this repo is its own thing; the catalogue data it indexes is his.
