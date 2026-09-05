# incompetech catalog

A filterable database over Kevin MacLeod's royalty-free music catalogue
([incompetech.com](https://incompetech.com/music/royalty-free/music.html)). His
own page searches one substring and ANDs a few mood chips; it offers no tempo,
duration, collection, category or date filter, which are the axes a piece is
actually chosen on. So the published `pieces.json` is normalised into SQLite
once — 1400-odd pieces, keyed by filename, with genre and collection resolved
and instruments and feels as relations — and queried from a CLI or a small
Flask app at [incompetech.lab980.com](https://incompetech.lab980.com). Previews
play from incompetech.com; nothing is rehosted here. Everything in the
catalogue is CC BY 4.0 to Kevin MacLeod, and the credit line rides on every row
that leaves the database.
