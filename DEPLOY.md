# Deploying the incompetech catalog

Target: **https://incompetech.lab980.com** — served from the lab980 droplet
(conventions in the `ivjames/lab980.com` repo's `CLAUDE.md`).

Shape: nginx proxies to a pm2-managed **Python 3.11 / Flask** process on
`127.0.0.1:8072`, with the app dir at `/var/www/incompetech`. Not Node: there
is no `package.json`, no `npm ci` and no build step. The install is a venv and
`pip install -r requirements.txt`.

**There are no secrets.** No API key, no credential, no write path — the app
serves GETs over a SQLite file built from a public JSON document. Nothing has
to be placed on the box before the first deploy.

## Before the first `setup`: confirm the port

8072 is **provisional** — the next free port by lab980's registry, where 8069
is the highest entry, 8070 is ffc's centeredge-mock upstream (prose-only in
lab980's `CLAUDE.md`) and 8071 is dnd-sim. What no file can settle is whether
something on the droplet is already listening on it, which is why the registry
records this site's `port` as `null` with `"port"` in `unverified` rather than
as fact. Check on the box, and if 8072 is taken, move it there in **two
places, both untracked**: `PORT` in `.env`, and the vhost's `proxy_pass`. That
is enough — `run.sh` sources `.env` after pm2 has applied
`ecosystem.config.js`, so `.env` wins, and `incompetech status` resolves the
port the same way it resolves the database (`INCOMPETECH_PORT`, then `.env`,
then its default), so its probes follow. Then `incompetech restart`.

**Do not edit `ecosystem.config.js` or `bin/incompetech` on the droplet.** Both
are tracked, and `deploy` hard-resets the checkout: the edit is destroyed on
the next deploy without saying so. They carry defaults, and a default is
changed by a commit. Either way, **fill the confirmed port into lab980's
`.claude/sites.json`** once you know it — that is the entry's one remaining
hole:

```bash
grep -rho 'proxy_pass http://127.0.0.1:[0-9]*' /etc/nginx/sites-enabled/ | sort -u
pm2 jlist | python3 -c "import json,sys;[print(p['name']) for p in json.load(sys.stdin)]"
```

## One-time bring-up (on the droplet, as root)

```bash
git clone https://github.com/ivjames/incompetech /var/www/incompetech
ln -sf /var/www/incompetech/bin/incompetech /usr/local/bin/incompetech
incompetech deploy
```

That is the whole thing. `deploy` creates the venv, installs, writes `.env`,
runs `setup` if there is no vhost yet, registers and starts the pm2 process,
builds the catalogue database because there isn't one, and probes
`/api/health` locally and publicly.

`incompetech setup` on its own is the box-outward half, and is idempotent:

- **`provision-site incompetech ivjames/incompetech --port 8072 --dir
  /var/www/incompetech`** where that tool is on PATH — DNS, vhost with the
  shared security-headers include, and certbot. **`--port` is not optional:**
  without it `provision-site` allocates the next free port from 8060 and writes
  *that* into the vhost while this repo uses 8072, and every request becomes a
  502 that looks like the app is down while it runs perfectly on the wrong
  port. `--dir` keeps it on this checkout, which it detects as an existing
  clone and leaves alone.
- Otherwise it installs `deploy/nginx-incompetech.conf` as
  `/etc/nginx/sites-available/incompetech.lab980.com`, HTTP only, and tells you
  to run `certbot --nginx -d incompetech.lab980.com --redirect` and
  `fix-security-headers --fix` yourself.

`incompetech setup --dry-run` says which of those it would do and changes
nothing.

Reboot survival needs the pm2 boot hook installed **once per droplet**
(`pm2 startup systemd -u root --hp /root`, then run the line it prints; verify
`systemctl is-enabled pm2-root` → enabled). `pm2 save` alone only writes the
dump — nothing replays it at boot without the hook. `setup` and `status` both
report whether it is there.

### `.env`

Written by `incompetech deploy` (mode 600, gitignored), seeded only where a key
is absent — an operator who changed one on the box meant it. Three keys, none
of them sensitive:

| key | default | what it is |
|---|---|---|
| `PORT` | `8072` | listen port — must match the vhost's `proxy_pass`. Sourced after pm2's env block, so it overrides `ecosystem.config.js` rather than having to agree with it |
| `HOST` | `127.0.0.1` | listen address. nginx is the only thing that should reach it; binding `0.0.0.0` would publish the app around the vhost |
| `INCOMPETECH_DB` | `/var/www/incompetech/data/catalog.sqlite3` | the catalogue database. `data/` is gitignored, so it survives a deploy |

`run.sh` sources this file before exec'ing python, so the pm2-managed process
and a hand `./run.sh` read exactly the same settings. Nothing else is read from
the environment.

## The database

It is **derived and untracked**: `python -m incompetech build` fetches
[`pieces.json`](https://incompetech.com/music/royalty-free/pieces.json),
normalises it and writes the SQLite file — two requests (the catalogue, and the
page whose genre/collection tables it is checked against), about 1 MB, no key.

```bash
incompetech build                 # rebuild from incompetech.com
incompetech deploy --rebuild      # ... as part of a deploy
```

Three things worth knowing:

- **A build is atomic and needs no downtime.** It writes beside the target and
  renames it into place; the web app opens a connection per request rather than
  holding one, so the new catalogue is visible on the very next request and a
  request in flight finishes against the old one. A build that fails leaves the
  previous database whole.
- **A plain `deploy` does not rebuild.** It builds only when there is no
  database at all, so pushing a code change does not spend two requests on
  Kevin MacLeod's server. Use `--rebuild` when he has published something new.
- **Drift is reported, not fixed.** The genre, collection and feel tables are
  transcribed into `incompetech/incompetech.py`; `build` re-reads the catalogue
  page and prints anything that has moved to **stderr**. That is a code change
  in this repo, not something the droplet can repair. `python -m incompetech
  drift` checks without building.

## Deploying updates

Land changes on `main` (via a PR — see `CLAUDE.md`), then on the droplet:

```bash
incompetech deploy
```

**How `deploy` syncs:** `git fetch` then `git reset --hard origin/main`. A
tracked file edited on the droplet is destroyed silently on the next deploy —
fix it in the repo. The gitignored state is the exception and survives on
purpose: `.env`, `data/` and `.venv/`.

A restart drops nothing. There is no session, no in-flight work and no state in
the process; the worst a restart costs is the request that was in flight.

## Confirming what is actually live

A 200 says the endpoint answered, not which build it served. Ask for the
commit:

```bash
incompetech status
```

which prints the checked-out commit and subject, the pm2 state and mode, the
`.env` settings, the database path/size/date, which loopback family answers,
the vhost, `/api/health` locally *and* publicly, and the certificate's
remaining days. Read the two probes together: a healthy local probe with a
failing public one points at nginx; the reverse points at the app.

`/api/health` answers **200 even with no database**, saying `"built": false`
and `"pieces": 0` — that is the state between `deploy` and the first `build`,
and `status` warns about it rather than calling it an outage. With one built it
carries the row count and the `built_at` stamp, which is how you tell how old
the catalogue is:

```bash
curl -s https://incompetech.lab980.com/api/health
incompetech logs                  # tail pm2 logs for this app
health-check --site incompetech   # the droplet-wide auditor
```

`health-check` only knows about sites listed in lab980's `.claude/sites.json`,
and this one is listed — so it will cover the site as soon as there is a vhost
and a DNS record for it to probe. Its `port` there is still `null` and
`unverified`; fill it in once the droplet has confirmed one.

## Overrides

- `INCOMPETECH_FQDN` — default `incompetech.lab980.com`
- `INCOMPETECH_BRANCH` — default `main`
- `INCOMPETECH_PORT` — default `8072`
- `INCOMPETECH_ENV_FILE` — default `./.env`
