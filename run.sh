#!/bin/sh
# Start the incompetech catalogue web server. Used by PM2
# (ecosystem.config.js) and by hand.
#
#   ./run.sh
#
# Config is ./.env (gitignored, mode 600, written by `incompetech deploy`): it
# is sourced here, so the pm2-managed process and a hand run read the same
# file. Three settings, none of them a secret — PORT, HOST, INCOMPETECH_DB.
set -eu

cd "$(dirname "$0")"

if [ -f ./.env ]; then
    set -a
    . ./.env
    set +a
fi

PORT="${PORT:-8072}"
export PORT
export PYTHONUNBUFFERED=1

if [ -x ".venv/bin/python" ]; then
    PY=".venv/bin/python"
else
    PY="$(command -v python3 || command -v python)"
fi

exec "$PY" -m web.app
