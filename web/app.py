"""Flask app factory for the incompetech catalogue.

    python -m web.app

Env:
    HOST            listen address (default 127.0.0.1)
    PORT            listen port (default 8072)
    INCOMPETECH_DB  the catalogue database (default ./data/catalog.sqlite3)

Three keys, none of them a secret: this app has no API key, no credentials and
no write path. It reads one SQLite file that `python -m incompetech build`
produces, opens a connection per request, and answers.
"""

from __future__ import annotations

import logging
import os
from typing import Any

from flask import Flask, jsonify

from incompetech import catalog as CAT

from .api import bp
from .db import DB_CONFIG_KEY

STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")

DEFAULT_PORT = 8072
DEFAULT_HOST = "127.0.0.1"


def create_app(db_path: str | None = None,
               config: dict[str, Any] | None = None) -> Flask:
    """Build the app. `db_path` is for tests; the site reads $INCOMPETECH_DB.

    The path is resolved once, here, and kept in the config: no route reads
    the environment mid-request, and a test injects a temp file the same way
    the droplet injects `.env`.
    """
    app = Flask(__name__, static_folder=STATIC_DIR, static_url_path="/static")
    app.config.update(config or {})
    app.config["JSON_SORT_KEYS"] = False
    app.config.setdefault(DB_CONFIG_KEY, str(CAT.db_path(db_path)))

    app.register_blueprint(bp)

    @app.errorhandler(404)
    def not_found(_e):  # type: ignore[misc]
        return jsonify({"error": "not found"}), 404

    @app.errorhandler(500)
    def server_error(e):  # type: ignore[misc]
        app.logger.exception("unhandled error")
        return jsonify({"error": str(e)}), 500

    @app.after_request
    def no_store_api(resp):  # type: ignore[misc]
        # A build replaces the database under the running app, so a cached
        # answer is a stale catalogue nobody can flush.
        if resp.mimetype == "application/json":
            resp.headers.setdefault("Cache-Control", "no-store")
        return resp

    return app


def main() -> None:
    logging.basicConfig(
        level=os.environ.get("INCOMPETECH_LOGLEVEL", "INFO").upper(),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    host = os.environ.get("HOST", DEFAULT_HOST)
    port = int(os.environ.get("PORT", str(DEFAULT_PORT)))
    app = create_app()
    log = logging.getLogger("incompetech")
    path = app.config[DB_CONFIG_KEY]
    log.info("incompetech catalog on http://%s:%d (db=%s)", host, port, path)
    if not os.path.exists(path):
        log.warning("no database at %s — the site will say so and every filter "
                    "is empty until: incompetech build", path)
    app.run(host=host, port=port, threaded=True, debug=False, use_reloader=False)


if __name__ == "__main__":
    main()
