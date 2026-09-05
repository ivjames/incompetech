"""incompetech's catalogue, normalised into SQLite and queried.

Two modules and no more: `incompetech` holds the lookup tables the catalogue
publishes only as inline JavaScript, the URL builders and the normaliser over
the raw rows; `catalog` holds the schema, the build and the filters.

This package is the library. It imports Flask nowhere and knows nothing about
a web layer — the layering is one way, `web` → here — so the CLI
(`python -m incompetech`) and the site are two callers of the same code rather
than two implementations of it.
"""

from __future__ import annotations

__all__ = ["catalog", "incompetech"]
