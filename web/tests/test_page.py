"""The static page, in the two structural ways it can be wrong.

There is no browser here and no JS harness, so this asserts shape rather than
behaviour: the one thing that must be true of the markup for the error path to
be visible at all, and that the script says what the page needs it to say.
"""

from __future__ import annotations

import re
from html.parser import HTMLParser
from pathlib import Path

STATIC = Path(__file__).resolve().parent.parent / "static"


class Nesting(HTMLParser):
    """Records the id-stack each element with an id was found under."""

    VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input",
            "link", "meta", "source", "track", "wbr"}

    def __init__(self):
        super().__init__()
        self.stack: list[str | None] = []
        self.ancestors: dict[str, list[str]] = {}

    def handle_starttag(self, tag, attrs):
        ident = dict(attrs).get("id")
        if ident:
            self.ancestors[ident] = [a for a in self.stack if a]
        if tag not in self.VOID:
            self.stack.append(ident)

    def handle_endtag(self, tag):
        if tag not in self.VOID and self.stack:
            self.stack.pop()


def test_the_error_line_is_not_inside_the_panel_it_reports_on():
    """#app stays hidden until /api/health answers.

    With #error inside it, a server that does not answer at all wrote its
    reason into an invisible element and the reader was shown "no catalogue
    database yet — run incompetech build" instead: a rebuild prescribed for a
    dead server.
    """
    page = Nesting()
    page.feed((STATIC / "index.html").read_text(encoding="utf-8"))
    assert "error" in page.ancestors, "the page has no #error at all"
    assert "app" not in page.ancestors["error"], \
        "#error is inside #app, which is hidden exactly when it matters"
    assert "app" not in page.ancestors.get("nodb", []), "and so is #nodb"


def test_the_credit_is_in_the_markup_and_outside_every_hidden_panel():
    """A licence condition must not depend on a fetch succeeding."""
    page = Nesting()
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    page.feed(html)
    assert "Music by Kevin MacLeod (incompetech.com), licensed under" in html
    assert "credit-line" in page.ancestors, "the credit must be findable to be held"
    assert "app" not in page.ancestors["credit-line"], "it is inside a hidden panel"
    assert "nodb" not in page.ancestors["credit-line"]


def test_the_script_separates_a_dead_server_from_an_unbuilt_database():
    js = (STATIC / "app.js").read_text(encoding="utf-8")
    boot = js[js.index("async function boot()"):js.index("async function getJSON")]
    # Two branches, not one `!health || !health.built`: the first returns
    # without prescribing a build, the second is what shows the #nodb panel.
    assert not re.search(r"!health\s*\|\|\s*!health\.built", boot), \
        "a server that did not answer is being reported as an unbuilt database"
    assert boot.index("if (!health)") < boot.index("if (!health.built)")
    assert boot.count("$('nodb').hidden = false") == 1
    assert "$('nodb')" not in boot[:boot.index("if (!health.built)")]


def test_a_refused_query_clears_the_total_above_the_empty_table():
    js = (STATIC / "app.js").read_text(encoding="utf-8")
    search = js[js.index("async function search()"):js.index("function render(")]
    assert "state.total = 0" in search, \
        "'1442 pieces match' would sit above an empty table with next → live"
