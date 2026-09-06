"""The playlist panel, in the ways it can be wrong without a browser to say so.

There is no JS runtime here and there is deliberately not going to be one:
this site has no Node, no `package.json` and no build step, and a test that
needed one would stop a clean clone from passing on the droplet. So what is
asserted is structure and coupling — the handful of properties that, if they
broke, would break quietly:

* the credit block is assembled from what the API said, never rebuilt in JS;
* the page's batch size still fits what the server will accept;
* a name someone typed reaches the DOM as text and not as markup;
* storage is touched only inside a guard, because it throws rather than
  returning null in a browser set to block site data.
"""

from __future__ import annotations

import re
from pathlib import Path

from web.api import MAX_FILENAMES

STATIC = Path(__file__).resolve().parent.parent / "static"
JS = (STATIC / "playlists.js").read_text(encoding="utf-8")
HTML = (STATIC / "index.html").read_text(encoding="utf-8")
APP = (STATIC / "app.js").read_text(encoding="utf-8")


def test_the_store_loads_before_the_page_that_calls_into_it():
    """app.js calls window.Playlists during boot, so order is not cosmetic."""
    store = HTML.index("/static/playlists.js")
    page = HTML.index("/static/app.js")
    assert store < page, "app.js would reach window.Playlists before it exists"
    assert "window.Playlists.boot(" in APP
    assert "window.Playlists.addCell(" in APP
    assert "window.Playlists.syncRows()" in APP


def test_the_credit_block_is_what_the_api_said_and_not_a_sentence_rebuilt_here():
    """The licence line has exactly one author, and it is `incompetech.py`.

    Every row leaves the API with a finished `credit` on it precisely so no
    caller reassembles the sentence. A second copy in JavaScript would drift
    from the first the day the wording changes, and what drifts is an
    attribution someone has already published.
    """
    block = JS[JS.index("function credits("):JS.index("function m3u(")]
    assert "r.credit" in block
    assert "Kevin MacLeod (incompetech.com) — Licensed under" not in JS, \
        "the per-piece credit sentence is being rebuilt in the browser"
    # The blanket line falls back to the page's own markup rather than to a
    # string here, which is why that sentence is in the markup at all.
    blanket = JS[JS.index("function blanket("):JS.index("function credits(")]
    assert "credit-line" in blanket


def test_a_piece_the_catalogue_lost_is_flagged_and_not_dropped():
    """Silently shortening a credit block is the one failure that under-credits.

    A piece that no longer resolves cannot be given a current credit, so it is
    carried through as `missing` and named in the export rather than quietly
    leaving the list one line shorter than the music it describes.
    """
    resolve = JS[JS.index("async function resolve("):JS.index("let attribution")]
    assert "missing: true" in resolve
    block = JS[JS.index("function credits("):JS.index("function m3u(")]
    assert "missing" in block, "the export says nothing about what it could not resolve"


def test_the_url_list_carries_no_comment_line():
    """It is meant for `wget -i` / `curl -K`, which read every line as a URL.

    A `#` credit header at the top of this one becomes a request for a file
    called "#" — so the attribution is on the page beside the button instead.
    """
    urls = JS[JS.index("function urls("):JS.index("function asJSON(")]
    assert "'#" not in urls and '"#' not in urls
    assert "blanket()" not in urls
    # The .m3u is the opposite case: `#` is that format's own comment syntax,
    # so the credit rides along in it.
    m3u = JS[JS.index("function m3u("):JS.index("function urls(")]
    assert "blanket()" in m3u


def test_the_page_batches_by_no_more_than_the_server_accepts():
    """One number on each side of an HTTP boundary, checked against each other.

    Over the server's bound the request never reaches this app: nginx answers
    414 with HTML the page cannot read. A playlist long enough to trip it is
    perfectly ordinary, so the two numbers are pinned together here.
    """
    batch = re.search(r"const BATCH = (\d+);", JS)
    assert batch, "playlists.js no longer says how it batches"
    assert int(batch.group(1)) <= MAX_FILENAMES


def test_the_exports_are_disabled_before_the_panel_yields():
    """The window between asking the catalogue and hearing back.

    `rows` still holds the previous playlist's pieces across that await, and
    an export takes its content from `rows` and its *name* from the active
    playlist. Left live, one click there writes a file named after the new
    playlist carrying the old one's credit lines — a wrong attribution,
    produced by the feature whose whole job is getting attribution right.
    """
    load = JS[JS.index("async function load()"):JS.index("function itemRow(")]
    yields = load.index("await P.resolve(")
    guarded = load[:yields]
    assert "setExportsEnabled(false)" in guarded, \
        "the exports stay live over the await, pointing at the previous rows"
    assert "rows = [];" in guarded, "and `rows` is still the previous playlist's"


def test_a_refusal_the_fetch_helper_swallows_is_still_reported():
    """app.js reports a throw; a 503 or a 400 comes back parsed.

    `resolve` therefore hands back a reason rather than a bare null, and the
    panel puts it on the line it keeps for exactly this — otherwise the reader
    gets an empty table with no rows, no empty-state and nothing said.
    """
    resolve = JS[JS.index("async function resolve("):JS.index("let attribution")]
    assert "return { error:" in resolve, "resolve has no way to say what went wrong"
    assert "return null" not in resolve
    load = JS[JS.index("async function load()"):JS.index("function itemRow(")]
    assert "out.error" in load and "showTrouble()" in load


def test_the_store_is_read_before_it_is_asked_whether_it_works():
    """`trouble()` only has an answer once a read has been attempted.

    Asked first, the very first render — the one where someone is about to
    start collecting into a browser that will keep none of it — is the one
    render that says nothing.
    """
    refresh = JS[JS.index("function refresh()"):JS.index("/* Re-read the active")]
    assert refresh.index("P.all()") < refresh.index("showTrouble()"), \
        "the panel asks whether storage works before it has touched storage"


def test_a_name_someone_typed_is_never_written_as_markup():
    """Playlist names are free text and go straight into the page."""
    for match in re.finditer(r"\.innerHTML\s*=\s*(.+)", JS):
        assert match.group(1).startswith("''"), \
            f"innerHTML is being assigned something other than a clear: {match.group(1)}"
    assert "textContent" in JS


def test_every_storage_access_is_guarded():
    """localStorage throws — not returns null — where site data is blocked.

    Unguarded, that exception escapes into boot and takes the catalogue down
    with it, over a feature the page is perfectly usable without.
    """
    for call in ("localStorage.getItem", "localStorage.setItem"):
        at = JS.index(call)
        before = JS[:at]
        # The nearest enclosing block back from the call is a `try {`.
        assert before.rindex("try {") > before.rindex("function "), \
            f"{call} is outside a try/catch"
    assert "trouble" in JS, "nothing reports storage being unusable to the reader"


def test_the_stored_key_is_versioned_and_the_export_is_a_playlist_not_a_browser():
    """The document is shaped for the signed-in store this may later become.

    Ids are generated rather than positional so two browsers' playlists can be
    merged under one account, and `active` — which browser tab is looking at
    what — is the one field the portable form drops.
    """
    assert re.search(r"const KEY = 'incompetech\.playlists\.v\d+';", JS)
    export = JS[JS.index("function asJSON("):JS.index("function importJSON(")]
    assert "active" not in export
    assert "playlist: pl" in export
    # An import adds; it never overwrites what is already here, and it never
    # keeps an incoming id that could collide with one of ours.
    imp = JS[JS.index("function importJSON("):JS.index("return { KEY,")]
    assert "clean.id = newId();" in imp
    assert "d.playlists.push(clean);" in imp


def test_the_panel_has_every_control_the_script_reaches_for():
    """A typo in an id is a button that silently does nothing.

    The script addresses the panel entirely by id, so the two files have to
    agree about every one of them.
    """
    used = set(re.findall(r"\$\('(pl_[a-z_]+|playlists)'\)", JS))
    assert used, "the panel no longer addresses anything by id"
    present = set(re.findall(r'id="((?:pl_[a-z_]+|playlists))"', HTML))
    assert used <= present, f"addressed but not in the markup: {sorted(used - present)}"
