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

Pieces you pick can be collected into **playlists**, which exist to make the
two chores after choosing easy: the credit block for everything you used, and
the list of files to fetch. They live in your browser — see below.

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
`--filename` is the odd one out — it names pieces instead of describing them,
matches exactly, and repeats to OR, which is how a list of pieces you already
chose is resolved back to rows with a current credit on each.

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
| `GET /api/pieces` | the filters above as query params: `text`, repeated `filename` (exact, OR, at most 100 per request) and `feel` (AND) and `feel_any` (OR), `instrument`, `genre`, `collection`, `category`, `bpm_min`/`bpm_max`/`bpm_unknown`, `min_length`/`max_length`, `since`/`until`, `sort`, `desc`, `limit`/`offset`. Returns `{"total": N, "pieces": [...]}`, each piece with its resolved genre, collection and category, feels, instruments, `mp3_url`, `page_url` and `credit`. A filter that cannot mean anything is a **400 with the reason**, never a 500 |
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
web/             the Flask app — factory, routes, and four static files
tests/           the package tests, and the shared fixture rows
web/tests/       the routes, over a database built from those rows
bin/incompetech  the operate CLI for the droplet (see DEPLOY.md)
```

The layering is one-way: `web` → `incompetech`. The CLI and the site are two
callers of the same filters rather than two implementations of them.

## Playlists

Collect pieces with the **+** beside any result. A playlist is a named,
ordered set, and the panel above the results does the rest of CRUD — new,
rename, duplicate, delete, reorder, remove, import.

Four exports, which are the point of the feature:

| | |
|---|---|
| **Copy credits** / **credits .txt** | one finished credit sentence per piece, under the blanket CC BY line — paste it into a video description |
| **.m3u** | a playlist file pointing at incompetech.com's own MP3s, with lengths and titles |
| **urls .txt** | the MP3 URLs and nothing else, ready for `wget -i` or `curl -K` |
| **.json** | the playlist itself, which **Import…** reads back |

Every credit line is the sentence the catalogue publishes for that piece,
re-read from `/api/pieces` when the panel opens rather than kept in a copy —
so a title corrected upstream corrects the credit. A piece the catalogue no
longer lists is named in the export rather than quietly dropped, because a
credit block one line short is a licence statement that is wrong.

Nothing here downloads an MP3, and the `.m3u` and URL list are lists of where
the music is, not copies of it.

**Playlists live in your browser** (`localStorage`), not on the server. This
site has no login and no write path — a playlist stored on it would be one
anybody could delete — so the trade is that a playlist does not follow you to
another browser except through **.json** / **Import…**, does not survive
clearing site data, and cannot be reached from `bin/incompetech`. It is the
one feature the CLI and the page do not share.

## Licence

Everything in the catalogue is **CC BY 4.0** to Kevin MacLeod. Attribution is a
condition of using any of it, so the credit sentence rides on every row that
leaves the database and the credit line is on the page at all times:

> Music by Kevin MacLeod (incompetech.com), licensed under Creative Commons: By
> Attribution 4.0

The code in this repo is its own thing; the catalogue data it indexes is his.
