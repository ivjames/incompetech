# Deploying incompetech catalog

Target: **https://incompetech.lab980.com** — served from the lab980 droplet (conventions in
the `ivjames/lab980.com` repo's `CLAUDE.md`).

Shape: nginx proxies to a pm2-managed Node process on `127.0.0.1:8072`,
with the app dir at `/var/www/incompetech`.

## One-time bring-up (on the droplet, as root)

```bash
provision-site incompetech ivjames/incompetech --port 8072
cd /var/www/incompetech
$EDITOR .env                         # provision-site seeded PORT; add the rest
npm ci && npm run build
pm2 start <entrypoint> --name incompetech && pm2 save
ln -sf /var/www/incompetech/bin/incompetech /usr/local/bin/incompetech
```

`provision-site` stops before build/run on purpose — each site is deployed its
own way afterward.

Two details in that first line matter more than they look:

- **`--port 8072` is not optional.** Without it `provision-site` picks the
  next free port from 8060 and writes *that* into the vhost, while this repo's
  CLI, `.env` and app config all use `8072`. nginx then proxies to a port
  nothing is listening on and every request is a 502 that looks like the app is
  down while it runs perfectly on the wrong port.
- **`provision-site` seeds `.env` with `PORT=` itself** (only if there isn't one
  already, mode 600). Add the remaining keys to that file — don't `cp` over it,
  or the port goes back out of sync.

Reboot survival needs the pm2 boot hook installed **once per droplet**
(`pm2 startup systemd -u root --hp /root`, then run the line it prints; verify
`systemctl is-enabled pm2-root` → enabled). `pm2 save` alone only writes the
dump — nothing replays it at boot without the hook.

### `.env` keys

| key | what it is |
|---|---|
| `PORT` | `8072` — must match the vhost's `proxy_pass` |
| _(add the rest)_ | |

## Deploying updates

Land changes on `main` (via a PR — see `CLAUDE.md`), then on the droplet:

```bash
incompetech deploy        # sync, npm ci, build, pm2 restart, probe
```

**How `deploy` syncs, since the conventions file sends you here for it:**
`git fetch` then `git reset --hard origin/<branch>`. A tracked file edited on
the droplet is destroyed silently on the next deploy — fix it in the repo. The
gitignored state is the exception and survives: `.env` and `data/` are meant to
be edited on the box.

## Check it

```bash
incompetech status              # HEAD, pm2 state, local + public probe, cert
incompetech logs                # tail pm2 logs for this app
health-check --site incompetech # the droplet-wide auditor
```

## Overrides

- `INCOMPETECH_FQDN` — default `incompetech.lab980.com`
- `INCOMPETECH_BRANCH` — default `main`
- `INCOMPETECH_PORT` — default `8072`
