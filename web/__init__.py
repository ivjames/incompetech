"""The web layer: a Flask app over the `incompetech` package.

One direction only — `web` imports `incompetech`, never the reverse — so the
CLI and the site are two callers of the same filters rather than two
implementations of them.
"""
