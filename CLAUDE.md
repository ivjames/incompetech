# incompetech catalog — working notes

A filterable database over Kevin MacLeod's royalty-free music catalogue

Served at **https://incompetech.lab980.com** from the lab980 droplet.

How work lands here — branch, PR, and the fact that merging is not deploying —
is in `.claude/rules/lab980-conventions.md`, which Claude Code loads
automatically every session. That file is owned by the lab980 scaffold and is
overwritten by it; **this** file is the site's own, and everything below is
about this site rather than about the platform. For the box itself, read the
`ivjames/lab980.com` repo's `CLAUDE.md`.

## Shape

A **proxied app**: nginx fronts a pm2-managed Node process on
`127.0.0.1:8072`.

- Repo: `ivjames/incompetech` · droplet dir: `/var/www/incompetech`
- pm2 process: `incompetech` — **fork mode** (`exec_mode: "fork"`, no
  `instances` key: setting it silently flips pm2 into cluster mode, whose
  startup crashes land in `~/.pm2/pm2.log` instead of the app's own log — a
  crash-looping app with empty logs is that trap)
- Config and data live in the app dir (`.env`, `data/`), not `/etc` or
  `/var/lib`. `.env` is **not** in git; changing it is a droplet-side edit
  followed by a restart.
- vhost: `/etc/nginx/sites-available/incompetech.lab980.com`, written by `provision-site`

## Deploying

On the droplet, as root:

```bash
incompetech deploy      # pull, npm ci, build, pm2 restart, probe
incompetech status      # HEAD, pm2 state, local + public probe, cert days
incompetech logs        # tail this app's pm2 logs
```

Full runbook, including first-time bring-up and `.env` keys: `DEPLOY.md`.

## Things worth knowing

- `.env` and `data/` are gitignored, so they survive `deploy`'s hard reset
  where everything else does not — which also means a missing key is invisible
  in the repo. Keep `.env.example` current and list every key in `DEPLOY.md`.
- Verify a **clean** clone builds, not just the working tree:

  ```bash
  d=$(mktemp -d) \
    && git archive HEAD | tar -x -C "$d" \
    && ( cd "$d" && npm ci && npm run build ) \
    && rm -rf "$d"
  ```

  `mktemp -d` is the point, not tidiness. The directory has to exist — `tar -x
  -C` into a missing one fails outright — and it has to be *empty*, or the
  extract merges over an earlier run's files and the check quietly stops
  testing a clean tree. A fixed `/tmp/x` gets both wrong, and on a shared
  `/tmp` it lets two runs race, each able to delete the other's tree
  mid-build. The subshell keeps you in the checkout, so `$d` and the `git
  ls-files` below still resolve; the trailing `rm -rf` fires only on success,
  leaving a failed build in `$d` to look at. A kitchen-sink `.gitignore`
  eating a source dir is the classic thing this catches; `git ls-files <dir>`
  confirms what is actually tracked.
- pm2 process name is `incompetech`; `incompetech logs` tails it.
