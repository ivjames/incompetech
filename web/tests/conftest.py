"""A real app over a real database, built from the shared fixture rows.

The web tests use no fakes: `create_app` is given a temp path, a database is
built there from `tests/fixtures.py`, and the Flask test client drives the
same code the droplet runs. There is nothing to stub — this app has no
outbound calls, no credentials and no clock.
"""

from __future__ import annotations

import pytest

from incompetech import catalog as CAT
from tests.fixtures import CATALOG
from web.app import create_app


@pytest.fixture
def db_file(tmp_path):
    path = tmp_path / "catalog.sqlite3"
    CAT.build_file(path, CATALOG, fetched_at="2026-09-05T00:00:00+00:00")
    return path


@pytest.fixture
def client(db_file):
    app = create_app(db_path=str(db_file))
    app.config.update(TESTING=True)
    return app.test_client()


@pytest.fixture
def empty_client(tmp_path):
    """An app pointed at a database nobody has built. It must still answer."""
    app = create_app(db_path=str(tmp_path / "not-built-yet.sqlite3"))
    app.config.update(TESTING=True)
    return app.test_client()
