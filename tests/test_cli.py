"""`bin/incompetech`, where it can be tested without a droplet.

The script is sourced rather than run (`INCOMPETECH_SOURCE_ONLY=1` defines the
functions and stops before dispatching), so the pure resolvers can be asked
questions directly. Nothing here needs pm2, nginx, root or the network.

It is bash (the lab980 app template: `START_CMD` is an array), so it is
sourced with bash and parsed with `bash -n`.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

CLI = Path(__file__).resolve().parent.parent / "bin" / "incompetech"


def call(func: str, env_file: Path, **env: str) -> str:
    out = subprocess.run(
        ["bash", "-c", f"source {CLI}; {func}"],
        capture_output=True, text=True, check=True,
        env={"PATH": "/usr/bin:/bin", "HOME": "/tmp",
             "INCOMPETECH_SOURCE_ONLY": "1",
             "INCOMPETECH_ENV_FILE": str(env_file), **env})
    return out.stdout.strip()


def test_the_script_parses(tmp_path):
    subprocess.run(["bash", "-n", str(CLI)], check=True)


def test_the_port_comes_from_env_the_way_the_database_does(tmp_path):
    """`ensure_env` seeds .env once and never overwrites it, so an operator who
    moved the port there is the authority on it.

    Reading `INCOMPETECH_PORT` alone meant `status` probing 8072 and reporting
    the site down while it answered perfectly one port over.
    """
    env = tmp_path / ".env"
    env.write_text("PORT=9099\nHOST=127.0.0.1\n", encoding="utf-8")
    assert call("port", env) == "9099"

    # An explicit override still wins — it is the documented escape hatch.
    assert call("port", env, INCOMPETECH_PORT="8123") == "8123"

    # And with no .env at all, the built-in default.
    assert call("port", tmp_path / "absent.env") == "8072"


def test_the_database_path_resolves_the_same_way(tmp_path):
    env = tmp_path / ".env"
    env.write_text("INCOMPETECH_DB=/srv/elsewhere.sqlite3\n", encoding="utf-8")
    assert call("db_path", env) == "/srv/elsewhere.sqlite3"
    assert call("db_path", tmp_path / "absent.env").endswith("/data/catalog.sqlite3")


@pytest.mark.parametrize("quoting", ['PORT=9099', 'PORT="9099"', "PORT='9099'",
                                     "export PORT=9099", "  PORT=9099  ",
                                     "# PORT=1\nPORT=9099"])
def test_env_is_read_the_way_a_shell_would_read_it(tmp_path, quoting):
    env = tmp_path / ".env"
    env.write_text(quoting + "\n", encoding="utf-8")
    assert call("port", env) == "9099"


def test_the_first_start_is_the_ecosystem_file(tmp_path):
    """`deploy` registers the app through the ecosystem file, picked out by
    name — that is what makes the first start and every restart the same
    registration."""
    assert call('printf "%s " "${START_CMD[@]}"', tmp_path / "absent.env") \
        == "ecosystem.config.js --only incompetech"
