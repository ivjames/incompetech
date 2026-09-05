"""A handful of real catalogue rows, with every kind of dirt the real 1442 carry.

Shared by the package tests and the web tests so both are answering questions
about the same catalogue: embedded `\\r\\n`, leading whitespace in front of a
URL, null-versus-empty-string, a tempo of "0" that means "not measured", a
length of "00:00:00" that means "unknown", a feel outside the page's
vocabulary, an already-percent-encoded filename, a repeated ISRC and a
repeated UUID, and the same instrument spelled three ways.

No network, ever. Nothing here is fetched.
"""

from __future__ import annotations

# A row as the catalogue really ships one. Anything not overridden is clean.
CLEAN = {
    "uuid": "00000000-0000-0000-0000-000000000000",
    "title": "Untitled", "filename": "Untitled.mp3", "length": "00:02:00",
    "instruments": "Piano", "genre": "22", "bpm": "100", "description": "",
    "feel": "Calm", "uploaded": "2015-05-05", "isrc": "USUAN1500001",
    "collection": "999", "sheetmusic": None, "video": None, "itunes": "",
    "wav": None, "filmmusicURL": None,
}


def row(**kw) -> dict:
    return {**CLEAN, **kw}


CATALOG = [
    # Dirty in every field that can be dirty, and in collection code 12.
    row(uuid="61123837", title="Dungeon Descent\r\n\r\n",
        filename="Dungeon Descent.mp3", length="00:03:20",
        instruments="Strings, Choir\r\n\r\n, Strings", genre="10", bpm="70",
        description="  Slow dread under a stone ceiling.\r\n",
        feel="Dark, Eerie, Mysterious", uploaded="2020-01-02",
        isrc="USUAN2000001", collection="12",
        sheetmusic="Dungeon Descent.pdf", video=" http://youtu.be/abc",
        itunes="", wav="https://incompetech.com/music/royalty-free/Downloads/x.html",
        filmmusicURL=""),
    # The one off-vocabulary feel in the catalogue, on the one piece with it.
    row(uuid="61123838", title="The Britons", filename="The Britons.mp3",
        length="00:05:07", instruments="Lute, Recorder", genre="22", bpm="180",
        description="Tavern music like from the olden days.",
        feel="Ren Faire, Medieval", uploaded="2026-06-29", isrc="USUAN2600004",
        collection="999"),
    # bpm "0" and bpm null both mean "not measured", not a tempo.
    row(title="Corncob", filename="Corncob.mp3", length="00:00:00", bpm="0",
        feel="Bouncy, Humorous", genre="24", collection="21",
        uploaded="2009-03-01", isrc="USUAN0900001"),
    row(title="Discovery Hit", filename="Discovery Hit.mp3", length="00:00:06",
        bpm=None, genre="23", feel="Epic, Intense", collection="42",
        instruments="Brass", uploaded="2011-01-01", isrc="USUAN1100003"),
    # A tempo that is not a number at all.
    row(title="Broken Tempo", filename="Broken Tempo.mp3", bpm="fast",
        feel="Dark", genre="10", collection="35", uploaded="2018-08-08",
        isrc="USUAN1800001"),
    # Already percent-encoded on the way in; an absolute sheetmusic URL.
    row(title="Joey's Formal Waltz", filename="Joey%27s Formal Waltz.mp3",
        length="00:04:00", bpm="90", feel="Bright", genre="4",
        collection="16", uploaded="2012-02-02", isrc="USUAN1200090",
        sheetmusic="http://incompetech.com/music/royalty-free/sheetmusic/Deuces.pdf",
        instruments="PIano"),
    # Two pieces, one ISRC, one of them sharing a UUID with the first row.
    row(uuid="USUAN1900054", title="A Very Brady Special",
        filename="A Very Brady Special.mp3", isrc="USUAN1900054",
        feel="Humorous", genre="13", collection="39", bpm="112",
        instruments="Piano, Drums", uploaded="2019-04-04"),
    row(uuid="USUAN1900054", title="Royal Coupling", filename="Royal Coupling.mp3",
        isrc="USUAN1900054", feel="Uplifting", genre="13", collection="39",
        bpm="112", instruments="piano", uploaded="2019-04-05"),
    # Not a piece: no filename, so no MP3 and nothing to key on.
    row(title="Ghost row", filename=""),
]
