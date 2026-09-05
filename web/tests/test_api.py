"""Every route, over a real database built from the shared fixture rows.

The filters themselves are tested against SQL in `tests/test_catalog.py`; what
is tested here is the layer between a query string and them — that a repeated
`feel` ANDs and a repeated `feel_any` ORs, that a filter which cannot mean
anything is a 400 carrying the reason, and that the app answers before anyone
has built a database at all.
"""

from __future__ import annotations

import json

from incompetech import incompetech as I
from tests.fixtures import CATALOG


def get(client, path):
    r = client.get(path)
    return r.status_code, r.get_json()


# ------------------------------------------------------------------ health


def test_health_counts_what_was_built(client):
    code, doc = get(client, "/api/health")
    assert code == 200
    assert doc["ok"] is True and doc["built"] is True
    assert doc["pieces"] == len(CATALOG) - 1
    assert doc["built_at"] == "2026-09-05T00:00:00+00:00"
    assert isinstance(doc["fts"], bool)


def test_health_is_200_before_anything_has_been_built(empty_client):
    """The app has to start and answer between `deploy` and the first `build`.

    A health check that failed there would report the site down when it is up
    and waiting for one command.
    """
    code, doc = get(empty_client, "/api/health")
    assert code == 200
    assert doc == {"ok": True, "built": False, "pieces": 0, "built_at": None,
                   "fts": False, "db": doc["db"]}


def test_a_file_that_is_not_a_database_is_reported_rather_than_raised(tmp_path):
    from web.app import create_app
    path = tmp_path / "catalog.sqlite3"
    path.write_text("this is not a database", encoding="utf-8")
    client = create_app(db_path=str(path)).test_client()
    code, doc = get(client, "/api/health")
    assert code == 200 and doc["built"] is False and doc["pieces"] == 0


def test_the_page_is_served_and_carries_the_credit(client):
    r = client.get("/")
    body = r.get_data(as_text=True)
    assert r.status_code == 200
    assert "Music by Kevin MacLeod (incompetech.com), licensed under" in body
    assert "Creative Commons: By Attribution 4.0" in body


def test_the_page_is_served_without_a_database_too(empty_client):
    """... and says which command to run."""
    body = empty_client.get("/").get_data(as_text=True)
    assert "python -m incompetech build" in body or "incompetech build" in body


# ------------------------------------------------------------------- meta


def test_meta_says_where_it_came_from_and_under_what_licence(client):
    code, doc = get(client, "/api/meta")
    assert code == 200
    assert doc["source"] == I.CATALOG_URL
    assert doc["lookups"] == I.LOOKUPS_URL
    assert doc["author"] == "Kevin MacLeod"
    assert doc["license"] == "by"
    assert "creativecommons.org/licenses/by/4.0" in doc["license_url"]
    assert doc["fetched_at"] == "2026-09-05T00:00:00+00:00"
    assert doc["built"] is True


def test_meta_still_states_the_licence_with_no_database(empty_client):
    code, doc = get(empty_client, "/api/meta")
    assert code == 200 and doc["built"] is False
    assert "Creative Commons" in doc["attribution"]


# ------------------------------------------------------------------ facets


def test_facets_carry_everything_the_controls_need(client):
    code, doc = get(client, "/api/facets")
    assert code == 200
    feels = {f["name"]: f for f in doc["feels"]}
    assert feels["Dark"]["count"] == 2 and feels["Dark"]["canonical"] == 1
    assert feels["Ren Faire"]["canonical"] == 0
    assert {g["name"] for g in doc["genres"]} == set(I.GENRES.values())
    cats = {c["category"] for c in doc["categories"]}
    assert "Film Scoring Moods" in cats and "World" in cats
    assert any(c["name"] == "Hard Electronic"
               for g in doc["categories"] for c in g["collections"])
    assert {i["name"] for i in doc["instruments"]} >= {"Piano", "Choir", "Lute"}
    assert "bpm" in doc["sorts"]


def test_facets_say_so_rather_than_500_with_no_database(empty_client):
    code, doc = get(empty_client, "/api/facets")
    assert code == 503 and doc["built"] is False
    assert "incompetech build" in doc["error"]


# ------------------------------------------------------------------ pieces


def titles(client, qs):
    code, doc = get(client, "/api/pieces?" + qs)
    assert code == 200, doc
    return [p["title"] for p in doc["pieces"]]


def test_pieces_come_back_whole_with_their_credit(client):
    code, doc = get(client, "/api/pieces?text=dread")
    assert code == 200 and doc["total"] == 1
    p = doc["pieces"][0]
    assert p["title"] == "Dungeon Descent"
    assert p["genre"] == "Horror"
    assert (p["collection"], p["collection_category"]) == ("Hard Electronic",
                                                           "Electronic and Rock")
    assert p["feels"] == ["Dark", "Eerie", "Mysterious"]
    assert p["instruments"] == ["Strings", "Choir"]
    assert p["mp3_url"].endswith("Dungeon%20Descent.mp3")
    assert p["page_url"].endswith("index.html?isrc=USUAN2000001")
    assert p["credit"] == I.credit_line("Dungeon Descent")
    assert "wav_link" not in p, "not a WAV and not a working audio URL"


def test_feel_ands_and_feel_any_ors(client):
    """The distinction the whole database exists for, over query strings."""
    assert titles(client, "feel=Dark") == ["Broken Tempo", "Dungeon Descent"]
    assert titles(client, "feel=Dark&feel=Eerie") == ["Dungeon Descent"]
    assert titles(client, "feel=Dark&feel=Eerie&feel=Mysterious") == ["Dungeon Descent"]
    assert titles(client, "feel=Dark&feel=Bouncy") == []
    assert titles(client, "feel_any=Dark&feel_any=Bouncy") == [
        "Broken Tempo", "Corncob", "Dungeon Descent"]


def test_the_filters_the_website_does_not_have(client):
    assert titles(client, "bpm_max=90") == ["Dungeon Descent", "Joey's Formal Waltz"]
    assert titles(client, "bpm_unknown=1") == ["Broken Tempo", "Corncob", "Discovery Hit"]
    assert titles(client, "min_length=3:00") == [
        "Dungeon Descent", "Joey's Formal Waltz", "The Britons"]
    assert titles(client, "max_length=10") == ["Discovery Hit"]
    assert titles(client, "category=Electronic and Rock") == ["Dungeon Descent"]
    assert titles(client, "collection=Hard Electronic") == ["Dungeon Descent"]
    assert titles(client, "genre=Horror") == ["Broken Tempo", "Dungeon Descent"]
    assert titles(client, "instrument=choir") == ["Dungeon Descent"]
    assert titles(client, "since=2019-01-01&until=2019-12-31") == [
        "A Very Brady Special", "Royal Coupling"]


def test_sorting_and_paging(client):
    every = titles(client, "limit=100")
    code, doc = get(client, "/api/pieces?limit=3")
    assert [p["title"] for p in doc["pieces"]] == every[:3]
    assert (doc["total"], doc["limit"], doc["offset"]) == (len(every), 3, 0)
    code, doc = get(client, "/api/pieces?limit=3&offset=3")
    assert [p["title"] for p in doc["pieces"]] == every[3:6]
    assert doc["total"] == len(every), "the total is the match count, not the page"
    assert titles(client, "sort=bpm&desc=1&limit=1") == ["The Britons"]


def test_a_filter_that_cannot_mean_anything_is_a_400_with_the_reason(client):
    for qs, said in (
        ("bpm_unknown=1&bpm_min=200", "bpm_unknown"),
        ("since=2019", "not a date"),
        ("text=*", "no word to search for"),
        ("min_length=abc", "not a duration"),
        ("bpm_min=fast", "not a whole number"),
        ("sort=loudness", "is not one of"),
        ("limit=0", "below the minimum"),
        ("limit=99999", "above the maximum"),
        ("offset=-1", "below the minimum"),
    ):
        code, doc = get(client, "/api/pieces?" + qs)
        assert code == 400, f"{qs} -> {code} {doc}"
        assert said in doc["error"], f"{qs} -> {doc['error']}"
        assert "Traceback" not in json.dumps(doc)
        # The message names the query parameter the caller sent, not the CLI
        # flag the library phrased its refusal in.
        assert "--" not in doc["error"], doc["error"]


def test_pieces_say_so_rather_than_500_with_no_database(empty_client):
    code, doc = get(empty_client, "/api/pieces?text=dread")
    assert code == 503 and doc["built"] is False
    assert "incompetech build" in doc["error"]


def test_a_rebuild_under_the_running_app_is_seen_by_the_next_request(client, db_file):
    """The connection-per-request rule, as a test.

    `build_file` replaces the file; an app holding a connection open would go
    on serving the replaced inode for the life of the process.
    """
    from incompetech import catalog as CAT
    assert get(client, "/api/health")[1]["pieces"] == len(CATALOG) - 1
    CAT.build_file(db_file, CATALOG[:3])
    assert get(client, "/api/health")[1]["pieces"] == 3
    assert titles(client, "limit=100") == ["Corncob", "Dungeon Descent", "The Britons"]


def test_json_is_never_cached(client):
    r = client.get("/api/pieces?limit=1")
    assert r.headers["Cache-Control"] == "no-store"


def test_an_unknown_route_is_json_not_html(client):
    code, doc = get(client, "/api/nope")
    assert code == 404 and doc == {"error": "not found"}
