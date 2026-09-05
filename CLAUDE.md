# incompetech catalog — working notes

A filterable database over Kevin MacLeod's royalty-free music catalogue: the
catalogue's own published JSON, normalised into SQLite and queried on the axes
his page does not offer, from a CLI and from a small Flask app.

Served at **https://incompetech.lab980.com** from the lab980 droplet.

How work lands here — branch, PR, and the fact that merging is not deploying —
is in `.claude/rules/lab980-conventions.md`, which Claude Code loads
automatically every session. That file is owned by the lab980 scaffold and is
overwritten by it; **this** file is the site's own, and everything below is
about this site rather than about the platform. For the box itself, read the
`ivjames/lab980.com` repo's `CLAUDE.md`.

## Decisions

- The checkout dir is **`/var/www/incompetech`** (always `/var/www/<stub>` on
  this box).
- The port is **8072 — provisional.** It is the next free one by lab980's
  registry: 8069 is the highest entry there, 8070 is ffc's centeredge-mock
  upstream (prose-only in lab980's `CLAUDE.md`, not a registry entry) and 8071
  is dnd-sim. But nothing in this repo can reach the droplet, and a port is a
  fact about the box rather than about a file, so **confirm it there before the
  first `incompetech setup`**:
  `grep -rho 'proxy_pass http://127.0.0.1:[0-9]*' /etc/nginx/sites-enabled/ | sort -u`.
  **Moving it on the box is `.env` and the vhost, and nothing else.** `run.sh`
  sources `.env` after pm2 has applied `ecosystem.config.js`, so `.env`'s
  `PORT` already wins, and `bin/incompetech` resolves the port the same way
  (`INCOMPETECH_PORT`, then `.env`, then its default). The port in
  `ecosystem.config.js` and the fallback in `bin/incompetech` are repo
  defaults: change them in a commit, never on the droplet, because both files
  are tracked and `deploy` hard-resets the checkout — an edit there is undone
  silently on the next deploy.
- **The site is registered in `lab980.com`** — `.claude/sites.json` and the
  prose site list both carry it (PR #53), as shape `app`, dir
  `/var/www/incompetech`, cli `bin/incompetech`. Its `port` is recorded as
  `null` with `"port"` in `unverified`, because that registry's invariant is
  that `unverified` lists the fields left null rather than the ones somebody
  guessed; the provisional 8072 is in its `notes`. **Filling that port in, once
  the droplet confirms it, is the remaining step** — and it is a change in that
  repo, not this one. `health-check --site incompetech` will know the site as
  soon as there is a vhost for it to probe.
- **There are no platform keys and no secrets.** No API key, no credential, no
  write path: every route is a GET, and the one outbound request in the repo
  is the build fetching a public JSON document. So `bin/incompetech` carries
  none of dnd-sim's key machinery — no `/etc/environment` adoption, no
  `env -u` launch dance, no write token. `.env` holds three settings (`PORT`,
  `HOST`, `INCOMPETECH_DB`), none of them sensitive. If this app ever does need
  a secret, that is a decision to record here first.
- **The database is derived, and lives in `data/`.** One command rebuilds it
  from `pieces.json`; it is gitignored for the same reason `.env` is, and
  survives a deploy's hard reset for the same reason too. Vendoring 1442 rows
  of someone else's catalogue into git would only go stale and churn.
- **A build is atomic.** `catalog.build_file` writes beside the target and
  `os.replace`s it into place, and the web layer opens a connection per
  request rather than holding one — so `incompetech build` under a live app is
  safe, and the new catalogue is visible on the very next request.
- **Previews play from incompetech.com.** The page points a single `<audio>`
  element at the catalogue's own `mp3_url`. We index this music; we do not
  rehost it, and nothing here ever downloads an MP3.
- **The credit line is mandatory and is in the HTML**, not rendered by script:
  *Music by Kevin MacLeod (incompetech.com), licensed under Creative Commons:
  By Attribution 4.0*. Everything in the catalogue is CC BY 4.0, attribution is
  a licence condition rather than a courtesy, and it must not depend on a fetch
  succeeding. A web test asserts it is on the page.

## Shape

A **proxied app**: nginx fronts a pm2-managed **Python 3.11 / Flask** process
on `127.0.0.1:8072`. Not Node — there is no `package.json`, no `npm ci`, no
build step. The install is `python3 -m venv .venv && .venv/bin/pip install -r
requirements.txt`, and `requirements.txt` is three lines (Flask, httpx, pytest;
ranges, not pins). httpx is used by the build alone: the web layer makes no
outbound request at all.

- Repo: `ivjames/incompetech` · droplet dir: `/var/www/incompetech`
- pm2 process: **`incompetech`** (from `ecosystem.config.js`) — runs
  `./run.sh`, which sources `./.env` and execs `.venv/bin/python -m web.app`.
  **fork mode**, `exec_mode: 'fork'` explicit: setting `instances` alone flips
  pm2 into cluster mode, whose startup crashes land in `~/.pm2/pm2.log` rather
  than this app's own error log — a crash-looping app with *empty* logs is that
  trap. There is no other reason to hold it at one; the app is stateless
  between requests and would scale horizontally fine if it ever needed to.
- **Layering is strict and one-way: `web` → `incompetech`.** The package is the
  library — lookups, normaliser, schema, filters — and imports Flask nowhere;
  a test walks its imports and fails if it ever does. The CLI and the site are
  two callers of the same `Filters`, so a query typed into the page and the
  same query typed at a shell cannot come to disagree.
- vhost: `/etc/nginx/sites-available/incompetech.lab980.com`, written by
  `provision-site` (via `incompetech setup`) or, without it, from
  `deploy/nginx-incompetech.conf`. A plain proxy — no buffering, timeout or
  gzip tuning, because nothing here streams — and nothing rewrites it after
  it is installed.
- Config is process environment, loaded from `./.env` by `run.sh` (`set -a;
  . ./.env; set +a`, only if the file exists) before it execs python — so
  pm2-managed and hand runs read the same file. The app reads `os.environ`
  only; there is no `python-dotenv`. `data/`, `.env` and `.venv/` are
  gitignored and survive a deploy's hard reset.

## Deploying

On the droplet, as root. First time — no keys to place beforehand, because
there are none:

```bash
git clone https://github.com/ivjames/incompetech /var/www/incompetech \
  && ln -sf /var/www/incompetech/bin/incompetech /usr/local/bin/incompetech \
  && incompetech deploy
```

Every time after:

```bash
incompetech deploy      # reset to origin/main, venv + pip, .env, vhost via setup
                        # if missing, pm2 start/restart, save if online, build the
                        # database if there isn't one, probe
incompetech deploy --rebuild   # ... and refresh the catalogue from incompetech.com
incompetech setup       # once, idempotent: provision-site (or the HTTP-only
                        # fallback vhost), pm2-root check; --dry-run shows what it would do
incompetech build       # rebuild the database (two requests, ~1 MB, no key) —
                        # atomic, so the running app keeps answering
incompetech status      # HEAD, pm2, .env, database, upstream family, vhost,
                        # local + public /api/health, cert days
incompetech logs        # tail this app's pm2 logs
```

A restart drops nothing: there is no session, no in-flight work and no state
in the process. What each step does and how to confirm what is live:
`DEPLOY.md`.

## Things worth knowing

- **The whole point is the axes the catalogue's own page lacks.** It searches
  one lowercased substring over title, instruments and description and ANDs a
  set of feel chips, and offers **no tempo, duration, collection, category or
  date filter at all** — which are exactly the axes a piece gets chosen on. If
  a change makes those harder to ask for, it is going the wrong way.
- **The raw rows are dirty, and the normaliser is where that is dealt with.**
  `incompetech/incompetech.py` names every kind of dirt in its docstring and
  the tests carry a fixture row of each. Three traps are worth repeating:
  - **`collection` is a `code`, not an `id`.** Each collection carries both and
    they differ for all but a handful; the catalogue page's own
    `getCollectionName()` matches on `code`. Joining on `id` still returns a
    name for every row — the wrong one for 133 of them, and code 12 comes back
    as Polka rather than Hard Electronic.
  - **A tempo of 0 is not slow.** 238 rows say `bpm` 0, meaning nobody measured
    it. Kept as a number it heads every "slow" query; kept as NULL it stays out
    of a range, and `bpm_unknown` asks for those rows deliberately. Same for
    `length` "00:00:00".
  - **The `wav` field holds no WAV.** None of its 268 values end in `.wav`;
    most point at a Downloads page that 404s. It is stored verbatim as
    `wav_link`, never offered as audio, and deliberately not in the API's
    output at all.
- **The lookup tables are a transcription and can go stale.** 24 genres, 50
  collections and 20 feels live only as inline JavaScript on the catalogue
  page; `incompetech/incompetech.py` is the one copy of them in this repo.
  `incompetech build` re-reads that page and reports drift to stderr, and
  `python -m incompetech drift` does it alone. Drift is fixed by hand, in that
  file — the tables are checked in on purpose, so a build is two requests and
  works from a saved file offline.
- **A filter that cannot mean anything is refused, not dropped.** Asking for
  the unmeasured tempos *and* a tempo range, a text that tokenises to no word
  (`*`), a date bound that is not a date — each raises `ValueError` in
  `catalog.search`, which the CLI turns into an exit code and the API into a
  **400 with the reason in it**. A dropped filter answers a question nobody
  asked. Keep it that way: `ValueError` → 400, never 500.
- **Text search has two paths and they must answer the same question.** FTS5
  where the interpreter has it, a LIKE scan where it does not — both tokenise
  in `_words` and both AND their words, and the query asks `have_fts5(conn)`
  rather than trusting `meta.fts`, because a `.sqlite3` is portable and the
  FTS5 module is not. LIKE's own `%` and `_` are escaped everywhere they could
  leak out of a filter.
- **`/api/health` is 200 even with no database.** That is the state a fresh
  droplet is in between `deploy` and the first `build`, and a health check that
  failed there would report the site down when it is up and waiting for one
  command. The page reads the same flag and says which command to run.
- Tests: `.venv/bin/python -m pytest -q` (everything);
  `.venv/bin/python -m pytest web/tests -q` for the web layer alone. No test
  touches the network — `tests/fixtures.py` is a handful of real catalogue rows
  carrying every kind of dirt, shared by both suites so they are answering
  questions about the same catalogue.
- Verify a **clean** clone installs and passes, not just the working tree:

  ```bash
  d=$(mktemp -d) \
    && git archive HEAD | tar -x -C "$d" \
    && ( cd "$d" && python3 -m venv .venv \
         && .venv/bin/pip install -q -r requirements.txt \
         && .venv/bin/python -m pytest -q ) \
    && rm -rf "$d"
  ```

  `mktemp -d` is the point, not tidiness. The directory has to exist — `tar -x
  -C` into a missing one fails outright — and it has to be *empty*, or the
  extract merges over an earlier run's files and the check quietly stops
  testing a clean tree. A fixed `/tmp/x` gets both wrong, and on a shared
  `/tmp` it lets two runs race, each able to delete the other's tree
  mid-build. The subshell keeps you in the checkout; the trailing `rm -rf`
  fires only on success, leaving a failed run in `$d` to look at. A
  kitchen-sink `.gitignore` eating a source dir is the classic thing this
  catches — `*.sqlite3` and `/data/` are ignored here on purpose, and
  `git ls-files web/static` confirms the page itself is tracked.
- **The front end is three files and no framework.** `web/static/index.html`,
  `app.js`, `style.css` — no CDN, no bundler, no build step, and every option
  in every control comes from `/api/facets` rather than being written into the
  JS. Light and dark are one set of custom properties redefined once under
  `prefers-color-scheme`.
- pm2 process name is `incompetech`; `incompetech logs` tails it.
