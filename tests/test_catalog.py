"""The incompetech catalogue database: normalising it, and querying it.

No network. The rows are `tests/fixtures.py` — a handful of real catalogue
rows carrying every kind of dirt the real 1442 do — shared with the web tests
so both layers are answering questions about the same catalogue.

The one thing worth stating twice: `collection` is a **code**, and code 12 is
Hard Electronic while *id* 12 is Polka. A join written the wrong way round
still returns a name for every row, which is why it is tested rather than
eyeballed.
"""

from __future__ import annotations

import os
import pathlib
import sqlite3

import pytest

from incompetech import catalog as CAT
from incompetech import incompetech as I
from tests.fixtures import CATALOG, row


@pytest.fixture
def db():
    conn = CAT.connect(":memory:")
    CAT.build(conn, CATALOG, fetched_at="2026-09-05T00:00:00+00:00")
    yield conn
    conn.close()


# ------------------------------------------------------------- lookup tables


def test_collection_resolves_by_code_and_not_by_id():
    """The gotcha. `getCollectionName()` on the catalogue page matches `code`."""
    twelve = I.collection_for("12")
    assert (twelve.name, twelve.category) == ("Hard Electronic", "Electronic and Rock")
    by_id = [c for c in I.COLLECTIONS if c.source_id == 12]
    assert [c.name for c in by_id] == ["Polka"], "id 12 is a different collection"
    assert twelve.source_id == 1


def test_the_lookup_tables_are_the_shape_the_catalogue_publishes():
    assert len(I.GENRES) == 24
    assert len(I.COLLECTIONS) == 50 == len(I.COLLECTIONS_BY_CODE)
    assert len(I.FEELS) == 20
    assert I.genre_name("10") == I.genre_name(10) == "Horror"
    assert I.genre_name("") is None and I.genre_name(None) is None
    assert I.genre_name("17") is None, "17 is not a genre; it is a hole in the list"


def test_nothing_in_the_library_imports_flask():
    """The layering, as a test: `web` may import this package, never the reverse.

    A library that reaches for the app it is served by cannot be run from a
    CLI, and this one is run from a CLI first.
    """
    import ast

    import incompetech
    from incompetech import catalog, incompetech as lookups
    for mod in (incompetech, catalog, lookups):
        tree = ast.parse(pathlib.Path(mod.__file__).read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            names = []
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module or ""]
            for name in names:
                assert name.split(".")[0] != "flask", f"{mod.__name__} imports {name}"


LOOKUP_JS = """
const genres = [ { "id": 10, "genre": "Horror" } ];
const collections = [
  {"id":"1","collection_name":"Hard Electronic","collection_category":"Electronic and Rock","code":"12"}
];
const feelsList = ["Dark"];
"""


def test_lookup_drift_reads_the_page_and_reports_what_moved():
    parsed = I.parse_lookups(LOOKUP_JS)
    assert parsed["collections"][0]["code"] == "12"
    notes = I.lookup_drift(parsed)
    # This snippet is a subset, so everything else reads as "gone from the page".
    assert any("gone from the page" in n for n in notes)
    assert not any(n.startswith(("genre 10:", "collection code 12:")) for n in notes), \
        "what the snippet does carry agrees with the table"

    moved = I.parse_lookups(LOOKUP_JS.replace('"Horror"', '"Terror"'))
    assert any("genre 10: page says 'Terror'" in n for n in I.lookup_drift(moved))


def test_a_page_without_the_arrays_reports_instead_of_raising():
    notes = I.lookup_drift(I.parse_lookups("<html>nothing here</html>"))
    assert len(notes) == 3 and all("no longer carries" in n for n in notes)


# --------------------------------------------------------------- normalising


def test_the_dirt_comes_out_in_the_wash():
    p = I.normalize_piece(CATALOG[0])
    assert p.title == "Dungeon Descent", "no \\r\\n survives into a column"
    assert p.description == "Slow dread under a stone ceiling."
    assert p.instruments == ("Strings", "Choir"), "deduplicated, newlines gone"
    assert p.feels == ("Dark", "Eerie", "Mysterious")
    assert p.length_s == 200
    assert p.bpm == 70
    assert p.genre == "Horror" and p.genre_id == 10
    assert (p.collection, p.collection_category) == ("Hard Electronic",
                                                     "Electronic and Rock")
    assert p.video_url == "http://youtu.be/abc", "the leading space is stripped"
    assert p.sheetmusic_url == (
        "https://incompetech.com/music/royalty-free/sheetmusic/Dungeon%20Descent.pdf")
    assert p.mp3_url == (
        "https://incompetech.com/music/royalty-free/mp3-royaltyfree/Dungeon%20Descent.mp3")
    assert p.page_url.endswith("index.html?isrc=USUAN2000001")


def test_null_and_empty_string_both_mean_absent():
    p = I.normalize_piece(CATALOG[0])          # itunes "", filmmusicURL ""
    q = I.normalize_piece(CATALOG[1])          # both null
    assert p.itunes_url is None and p.filmmusic_url is None
    assert q.itunes_url is None and q.filmmusic_url is None
    assert q.wav_link is None
    assert p.wav_link, "the junk `wav` value is kept verbatim, just not as audio"


@pytest.mark.parametrize("raw,secs", [
    ("00:03:20", 200), ("00:00:06", 6), ("1:02:03", 3723), ("3:30", 210),
    ("00:00:00", None), ("", None), (None, None), ("nope", None),
])
def test_lengths_parse_and_zero_means_unknown(raw, secs):
    assert I.parse_length(raw) == secs


@pytest.mark.parametrize("raw,bpm", [
    ("70", 70), (" 128 ", 128), ("0", None), (None, None), ("", None),
    ("fast", None), ("120.0", 120),
    # These two parse as floats and then refuse to be integers, which is an
    # OverflowError and not the ValueError "fast" raises.
    ("inf", None), ("1e400", None), ("-inf", None),
])
def test_tempos_parse_and_zero_means_not_measured(raw, bpm):
    assert I.parse_bpm(raw) == bpm


def test_the_already_encoded_filename_is_not_encoded_twice():
    p = I.normalize_piece(CATALOG[5])
    assert p.mp3_url.endswith("Joey%27s%20Formal%20Waltz.mp3")
    assert "%2527" not in p.mp3_url
    assert p.sheetmusic_url.startswith("https://"), "http:// is upgraded, not followed"


def test_a_row_without_a_filename_is_not_a_piece():
    assert I.normalize_piece(CATALOG[-1]) is None
    assert len(I.normalize_catalog(CATALOG)) == len(CATALOG) - 1


def test_split_multi_keeps_order_and_drops_repeats():
    assert I.split_multi("Strings, Choir\r\n, strings") == ["Strings", "Choir"]
    assert I.split_multi(None) == []
    assert I.split_multi(" , ,") == []


def test_the_credit_is_incompetechs_own_wording():
    line = I.credit_line("Dungeon Descent")
    assert line.startswith('"Dungeon Descent" Kevin MacLeod (incompetech.com)')
    assert line.endswith("https://creativecommons.org/licenses/by/4.0/")


# --------------------------------------------------------------------- build


def test_build_ingests_every_piece_and_resolves_every_id(db):
    n = db.execute("SELECT count(*) FROM piece").fetchone()[0]
    assert n == len(CATALOG) - 1
    assert db.execute("SELECT count(*) FROM piece WHERE genre_id IS NULL").fetchone()[0] == 0
    assert db.execute(
        "SELECT count(*) FROM piece WHERE collection_code IS NULL").fetchone()[0] == 0


def test_build_reports_what_it_did():
    conn = CAT.connect(":memory:")
    stats = CAT.build(conn, CATALOG)
    assert (stats.pieces, stats.skipped) == (len(CATALOG) - 1, 1)
    assert stats.unresolved_genre == stats.unresolved_collection == 0
    assert stats.with_bpm == stats.pieces - 3, "0, null and 'fast' are all unknown"
    assert stats.with_length == stats.pieces - 1, "00:00:00 is unknown"
    assert set(stats.non_canonical_feels) == {"Medieval", "Ren Faire"}
    assert "\n".join(stats.lines()).count("unresolved 0") == 2
    conn.close()


def test_neither_isrc_nor_uuid_is_unique_and_no_row_is_dropped(db):
    got = db.execute("SELECT title FROM piece WHERE isrc = 'USUAN1900054' "
                     "ORDER BY title").fetchall()
    assert [r["title"] for r in got] == ["A Very Brady Special", "Royal Coupling"]
    dupe_uuid = db.execute(
        "SELECT count(*) FROM piece WHERE uuid = 'USUAN1900054'").fetchone()[0]
    assert dupe_uuid == 2
    assert db.execute("SELECT count(DISTINCT filename) FROM piece").fetchone()[0] == \
        db.execute("SELECT count(*) FROM piece").fetchone()[0]


def test_the_same_instrument_spelled_three_ways_is_one_instrument(db):
    rows = db.execute("SELECT name, key FROM instrument WHERE key = 'piano'").fetchall()
    assert len(rows) == 1
    assert rows[0]["name"] == "Piano", "the commonest spelling wins, not 'PIano'"
    n = db.execute("SELECT count(*) FROM piece_instrument pi JOIN instrument i "
                   "ON i.instrument_id = pi.instrument_id "
                   "WHERE i.key = 'piano'").fetchone()[0]
    assert n == 5, "Piano, PIano and piano are the same filter"


def test_a_tie_between_two_spellings_goes_to_the_one_seen_first(db):
    """Not to the lexicographically greatest, which is lowercase in ASCII.

    Three real instruments are spelled both ways exactly once — Tambourine,
    Tenor Drum, Plucked Strings — and the catalogue's own capitalisation is
    the better display name of the two.
    """
    for first, second in (("Tambourine", "tambourine"), ("tambourine", "Tambourine")):
        conn = CAT.connect(":memory:")
        CAT.build(conn, [row(title="One", filename="One.mp3", instruments=first),
                         row(title="Two", filename="Two.mp3", instruments=second)])
        got = conn.execute(
            "SELECT name FROM instrument WHERE key = 'tambourine'").fetchone()["name"]
        assert got == first, "one each, so the first spelling wins"
        conn.close()


def test_off_vocabulary_feels_are_kept_and_flagged(db):
    rows = {r["name"]: r["canonical"] for r in db.execute("SELECT name, canonical FROM feel")}
    assert rows["Ren Faire"] == 0 and rows["Medieval"] == 0
    assert rows["Dark"] == 1 and rows["Humorous"] == 1


def test_the_licence_is_stored_with_the_data(db):
    m = CAT.meta(db)
    assert m["license"] == "by"
    assert m["author"] == "Kevin MacLeod"
    assert "creativecommons.org/licenses/by/4.0" in m["attribution"]
    assert m["fetched_at"] == "2026-09-05T00:00:00+00:00"
    assert m["source"] == I.CATALOG_URL


def test_every_row_carries_its_credit_out_of_the_database(db):
    for r in CAT.search(db, CAT.Filters(limit=0)):
        assert r["credit"] == I.credit_line(r["title"])


# --------------------------------------------------------------------- query


def titles(db, **kw) -> list[str]:
    return [r["title"] for r in CAT.search(db, CAT.Filters(limit=0, **kw))]


def test_feels_and_rather_than_or(db):
    """The whole point of the relation: three feels means all three."""
    assert titles(db, feels=("Dark",)) == ["Broken Tempo", "Dungeon Descent"]
    assert titles(db, feels=("Dark", "Eerie")) == ["Dungeon Descent"]
    assert titles(db, feels=("Dark", "Eerie", "Mysterious")) == ["Dungeon Descent"]
    assert titles(db, feels=("Dark", "Bouncy")) == [], "no piece carries both"
    # ... and the OR form is a separate flag, not the same one spelled twice.
    assert titles(db, feels_any=("Dark", "Bouncy")) == [
        "Broken Tempo", "Corncob", "Dungeon Descent"]


def test_feels_match_regardless_of_case(db):
    assert titles(db, feels=("dark", "EERIE")) == ["Dungeon Descent"]


def test_instruments_and_and_match_as_substrings(db):
    assert titles(db, instruments=("choir",)) == ["Dungeon Descent"]
    assert titles(db, instruments=("strings", "choir")) == ["Dungeon Descent"]
    assert titles(db, instruments=("piano", "drums")) == ["A Very Brady Special"]
    assert titles(db, instruments=("lute",)) == ["The Britons"]


def test_a_tempo_range_never_returns_an_unmeasured_tempo(db):
    """238 real rows say bpm 0. Treated as a number they head every slow query."""
    assert "Corncob" not in titles(db, bpm_max=90)
    assert "Broken Tempo" not in titles(db, bpm_max=90)
    assert titles(db, bpm_max=90) == ["Dungeon Descent", "Joey's Formal Waltz"]
    assert titles(db, bpm_min=112, bpm_max=180) == [
        "A Very Brady Special", "Royal Coupling", "The Britons"]
    # and they can still be asked for on purpose
    assert titles(db, bpm_unknown=True) == ["Broken Tempo", "Corncob", "Discovery Hit"]


def test_a_duration_range_never_returns_an_unknown_duration(db):
    assert titles(db, length_min=180) == ["Dungeon Descent", "Joey's Formal Waltz",
                                          "The Britons"]
    assert titles(db, length_max=10) == ["Discovery Hit"]
    assert "Corncob" not in titles(db, length_min=0), "00:00:00 is not a duration"


def test_the_axes_the_website_does_not_have(db):
    assert titles(db, categories=("Electronic and Rock",)) == ["Dungeon Descent"]
    assert titles(db, collections=("Hard Electronic",)) == ["Dungeon Descent"]
    assert titles(db, genres=("Horror",)) == ["Broken Tempo", "Dungeon Descent"]
    assert titles(db, genres=("10",)) == ["Broken Tempo", "Dungeon Descent"]
    assert titles(db, uploaded_from="2019-01-01", uploaded_to="2019-12-31") == [
        "A Very Brady Special", "Royal Coupling"]


def test_filters_combine(db):
    got = titles(db, feels=("Dark",), genres=("Horror",), bpm_max=90,
                 length_min=120, categories=("Electronic and Rock",))
    assert got == ["Dungeon Descent"]


def test_full_text_searches_title_and_description(db):
    assert titles(db, text="dread") == ["Dungeon Descent"], "found in the description"
    assert titles(db, text="britons") == ["The Britons"]
    assert titles(db, text="tavern olden") == ["The Britons"], "words AND"
    assert titles(db, text="tavern dread") == [], "and they really do AND"


def test_full_text_survives_punctuation_that_fts_treats_as_syntax(db):
    for text in ("stone -ceiling", 'a "quote', "NOT", "AND OR", "x:y"):
        CAT.search(db, CAT.Filters(text=text))       # must not raise


def test_a_text_filter_holding_no_word_is_refused_and_not_dropped(db):
    """"*" tokenises to nothing. Dropped, `--text '*'` reported every piece in
    the catalogue as a match for it, on either search path."""
    for fts in ("5", ""):
        db.execute("UPDATE meta SET value = ? WHERE key = 'fts'", (fts,))
        with pytest.raises(ValueError, match="no word to search for"):
            CAT.search(db, CAT.Filters(text="*"))


def test_both_search_paths_ask_for_every_word(db):
    """FTS5 ANDs its terms, so the fallback ANDs a clause per word.

    As one substring "stone dread" is a phrase that appears nowhere, and a
    fallback that answers a different question than the index is worse than no
    fallback at all.
    """
    for text, want in (("dread", ["Dungeon Descent"]),
                       ("stone dread", ["Dungeon Descent"]),
                       ("descent ceiling", ["Dungeon Descent"]),
                       ("tavern dread", []),
                       ("olden tavern", ["The Britons"])):
        db.execute("UPDATE meta SET value = '5' WHERE key = 'fts'")
        assert titles(db, text=text) == want, f"index: {text!r}"
        db.execute("UPDATE meta SET value = '' WHERE key = 'fts'")
        assert titles(db, text=text) == want, f"fallback: {text!r}"


def test_a_wildcard_typed_into_a_filter_is_a_character_and_not_a_wildcard(db):
    """LIKE's "%" and "_" leaking out of a filter turn it into no filter."""
    db.execute("UPDATE meta SET value = '' WHERE key = 'fts'")   # the LIKE path
    assert titles(db, text="%") == []
    assert titles(db, text="d_ead") == [], "a literal underscore, not any character"
    assert titles(db, collections=("%",)) == []
    assert titles(db, categories=("%",)) == []
    assert titles(db, instruments=("%",)) == []
    # and the ordinary substring match still matches
    assert titles(db, collections=("Hard Electronic",)) == ["Dungeon Descent"]


def test_text_search_falls_back_where_the_interpreter_has_no_fts5(db):
    """Same question, LIKE instead of MATCH, for a SQLite built without FTS5."""
    db.execute("UPDATE meta SET value = '' WHERE key = 'fts'")
    assert titles(db, text="dread") == ["Dungeon Descent"]
    assert titles(db, text="Britons") == ["The Britons"]


@pytest.mark.skipif(not CAT.have_fts5(CAT.connect(":memory:")),
                    reason="needs FTS5 to build the database this one simulates")
def test_a_database_built_with_fts5_is_readable_without_the_module(db, monkeypatch):
    """`meta.fts` is what the *building* interpreter had; the file is portable.

    Dropping the index is what an absent FTS5 module amounts to for this
    query: either way MATCH cannot run, and the fallback has to.
    """
    monkeypatch.setattr(CAT, "have_fts5", lambda conn: False)
    db.execute("DROP TABLE piece_fts")
    assert CAT.meta(db)["fts"] == "5", "the file still says it was built with one"
    assert titles(db, text="dread") == ["Dungeon Descent"]


def test_a_sqlite_without_fts5_still_builds(monkeypatch):
    monkeypatch.setattr(CAT, "have_fts5", lambda conn: False)
    conn = CAT.connect(":memory:")
    stats = CAT.build(conn, CATALOG)
    assert stats.fts is False
    assert not conn.execute(
        "SELECT name FROM sqlite_master WHERE name = 'piece_fts'").fetchall()
    assert [r["title"] for r in CAT.search(conn, CAT.Filters(text="dread"))] == \
        ["Dungeon Descent"]
    conn.close()


def test_bpm_unknown_and_a_tempo_range_cannot_both_be_asked_for(db):
    """They ask opposite things, and the range used to be silently discarded."""
    for f in (CAT.Filters(bpm_unknown=True, bpm_min=200),
              CAT.Filters(bpm_unknown=True, bpm_max=90)):
        with pytest.raises(ValueError, match="bpm-unknown"):
            CAT.search(db, f)


def test_a_date_bound_has_to_be_a_date(db):
    """They compare as text, so "2019" sorts before "2019-01-01" and quietly
    excludes the whole year it looks like it asks for."""
    for f in (CAT.Filters(uploaded_from="2019-01-01", uploaded_to="2019"),
              CAT.Filters(uploaded_from="last tuesday")):
        with pytest.raises(ValueError, match="not a date"):
            CAT.search(db, f)


def test_sorting_puts_the_unknowns_last_both_ways(db):
    up = [r["bpm"] for r in CAT.search(db, CAT.Filters(sort="bpm", limit=0))]
    down = [r["bpm"] for r in CAT.search(db, CAT.Filters(sort="bpm", desc=True, limit=0))]
    assert up[:2] == [70, 90] and up[-3:] == [None, None, None]
    assert down[0] == 180 and down[-3:] == [None, None, None]


def test_limit_limits_and_count_does_not(db):
    f = CAT.Filters(limit=2)
    assert len(CAT.search(db, f)) == 2
    assert CAT.count(db, f) == len(CATALOG) - 1


def test_rows_come_back_with_their_lists_and_urls(db):
    r = CAT.search(db, CAT.Filters(text="dread"))[0]
    assert r["feels"] == ["Dark", "Eerie", "Mysterious"], "catalogue order, not alphabetical"
    assert r["instruments"] == ["Strings", "Choir"]
    assert r["mp3_url"].endswith("Dungeon%20Descent.mp3")
    assert r["collection_category"] == "Electronic and Rock"


def test_the_table_output_is_readable_and_says_when_nothing_matched(db):
    text = CAT.format_rows(CAT.search(db, CAT.Filters(feels=("Dark", "Eerie"))))
    assert "Dungeon Descent" in text and "Hard Electronic" in text
    assert "TITLE" in text.splitlines()[0]
    assert CAT.format_rows([]) == "no pieces match"


def test_hms_reads_as_a_duration():
    assert (CAT.hms(200), CAT.hms(3723), CAT.hms(6), CAT.hms(None)) == \
        ("3:20", "1:02:03", "0:06", "  ?  ")


def test_the_view_joins_the_same_way_the_query_does(db):
    r = db.execute("SELECT * FROM piece_full WHERE title = 'Dungeon Descent'").fetchone()
    assert (r["genre"], r["collection"]) == ("Horror", "Hard Electronic")


def test_the_cli_says_what_is_wrong_instead_of_raising(tmp_path, capsys):
    """A typo in a filter is a message and an exit code, not a traceback."""
    from incompetech.__main__ import _duration, main

    assert _duration("3:30") == 210 and _duration("210") == 210
    with pytest.raises(ValueError, match="not a duration"):
        _duration("abc")

    path = tmp_path / "catalog.sqlite3"
    CAT.build_file(path, CATALOG)

    for argv, said in ((["--min-length", "abc"], "not a duration"),
                       (["--text", "*"], "no word to search for"),
                       (["--bpm-unknown", "--bpm-min", "200"], "bpm-unknown"),
                       (["--since", "2019"], "not a date")):
        assert main(["query", "--db", str(path), *argv]) == 2
        assert said in capsys.readouterr().err

    assert main(["query", "--db", str(path), "--text", "dread"]) == 0


def test_the_cli_says_to_build_before_it_can_query(tmp_path, capsys):
    from incompetech.__main__ import main
    assert main(["query", "--db", str(tmp_path / "absent.sqlite3")]) == 2
    assert "run `python -m incompetech build` first" in capsys.readouterr().err


def test_the_schema_says_no_to_a_dangling_reference(db):
    with pytest.raises(sqlite3.IntegrityError):
        db.execute("INSERT INTO piece_feel VALUES (1, 9999, 0)")


# ------------------------------------------------------- building to a file


def test_a_build_replaces_the_database_in_one_step(tmp_path, monkeypatch):
    """The web app opens a connection per request, so a rebuild under it is
    safe only if no request can ever open a half-written file.

    `build_file` writes beside the target and `os.replace`s it in, which is
    one rename on one filesystem. The proof is that the path the server would
    open does not exist until the build is finished — so the replace is
    watched rather than assumed.
    """
    path = tmp_path / "catalog.sqlite3"
    seen: list[bool] = []
    real_replace = os.replace

    def watched(src, dst):
        seen.append(pathlib.Path(dst).exists())     # False on a first build
        assert pathlib.Path(src).exists(), "the built file is there before the rename"
        return real_replace(src, dst)

    monkeypatch.setattr(CAT.os, "replace", watched)
    stats = CAT.build_file(path, CATALOG)
    assert seen == [False] and stats.pieces == len(CATALOG) - 1

    # ... and a second build swaps a live file out from under whatever has it
    # open. The old connection keeps reading the old inode; the next one gets
    # the new file.
    conn = CAT.connect(path)
    assert conn.execute("SELECT count(*) FROM piece").fetchone()[0] == len(CATALOG) - 1
    CAT.build_file(path, CATALOG[:3])
    assert conn.execute("SELECT count(*) FROM piece").fetchone()[0] == len(CATALOG) - 1, \
        "the open connection still sees the database it opened"
    conn.close()
    fresh = CAT.connect(path)
    assert fresh.execute("SELECT count(*) FROM piece").fetchone()[0] == 3
    fresh.close()
    assert sorted(p.name for p in tmp_path.iterdir()) == ["catalog.sqlite3"], \
        "no temporary file is left behind"


def test_a_failed_build_leaves_the_old_database_alone(tmp_path):
    path = tmp_path / "catalog.sqlite3"
    CAT.build_file(path, CATALOG)
    before = path.read_bytes()
    class Exploding(dict):
        def get(self, *a, **kw):
            raise RuntimeError("the catalogue fetch handed us something else")

    with pytest.raises(RuntimeError):
        CAT.build_file(path, [Exploding()])
    assert path.read_bytes() == before
    assert [p.name for p in tmp_path.iterdir()] == ["catalog.sqlite3"]


def test_where_the_database_lives_is_decided_in_one_place(tmp_path, monkeypatch):
    monkeypatch.delenv(CAT.DB_ENV, raising=False)
    assert CAT.db_path() == CAT.DEFAULT_DB == pathlib.Path("data/catalog.sqlite3")
    monkeypatch.setenv(CAT.DB_ENV, str(tmp_path / "elsewhere.sqlite3"))
    assert CAT.db_path() == tmp_path / "elsewhere.sqlite3"
    assert CAT.db_path("/explicit.sqlite3") == pathlib.Path("/explicit.sqlite3"), \
        "an explicit path beats the environment"


# --------------------------------------------------------- paging and facets


def test_offset_pages_through_the_same_order(db):
    every = titles(db)
    assert [r["title"] for r in CAT.search(db, CAT.Filters(limit=3))] == every[:3]
    assert [r["title"] for r in CAT.search(db, CAT.Filters(limit=3, offset=3))] == \
        every[3:6]
    # An unlimited query with an offset is still a page: SQLite needs a LIMIT
    # before an OFFSET, and -1 is how "all the rest" is spelled.
    assert [r["title"] for r in CAT.search(db, CAT.Filters(limit=0, offset=3))] == \
        every[3:]
    assert CAT.count(db, CAT.Filters(limit=3, offset=3)) == len(every), \
        "the total is what matched, not what this page holds"


def test_the_facets_are_what_a_control_can_be_built_from(db):
    f = CAT.facets(db)
    feels = {x["name"]: x for x in f["feels"]}
    assert feels["Dark"]["count"] == 2 and feels["Dark"]["canonical"] == 1
    assert feels["Ren Faire"]["canonical"] == 0
    assert [x["name"] for x in f["feels"][:3]] == sorted(
        [x["name"] for x in f["feels"] if x["canonical"]])[:3], "canonical first"
    instruments = {x["name"]: x["count"] for x in f["instruments"]}
    assert instruments["Piano"] == 5, "one instrument, three spellings"
    genres = {x["name"]: x["count"] for x in f["genres"]}
    assert genres["Horror"] == 2 and genres["Polka"] == 0, "an empty shelf is still a shelf"
    assert len(f["genres"]) == len(I.GENRES)
    cats = {c["category"]: [x["name"] for x in c["collections"]] for c in f["categories"]}
    assert "Hard Electronic" in cats["Electronic and Rock"]
    assert sum(len(v) for v in cats.values()) == len(I.COLLECTIONS)
    assert "bpm" in f["sorts"]
