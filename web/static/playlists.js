/* Playlists: collecting pieces out of the catalogue, for a credit block and a
 * download list.
 *
 * Where they live, and why that is not the server. Everything else on this
 * site is a GET over a build artefact — no key, no credential, no write path —
 * and a playlist is the first thing anyone has wanted to *keep*. Keeping it on
 * a public server means either that anyone on the internet can rename and
 * delete yours, or that this app grows the login it has so far not needed. So
 * a playlist lives in this browser, in localStorage, and the server stays
 * exactly as read-only as it was.
 *
 * That is a deliberate trade with two costs, worth naming rather than
 * discovering: `bin/incompetech` cannot see a playlist held here, so this is
 * the one feature the CLI and the page do not share; and a playlist does not
 * follow you to another browser except through Export/Import. The way out of
 * both is an accounted, signed-in store, and the document written here is
 * already shaped for one — see the note above `read` below.
 *
 * What is *not* kept here is the catalogue. An item stores a `filename` — the
 * only unique field the catalogue has — and a title only so there is something
 * to show before the network answers. Everything a credit or a download needs
 * is re-read from /api/pieces?filename=… on every load, because a credit
 * assembled from a stale snapshot is a licence statement about music, made
 * from a copy of the facts, and the point of the whole feature is getting that
 * line right.
 */
'use strict';

const Playlists = (() => {

  /* ------------------------------------------------------------- storage */

  /* One key, versioned in its name. A future schema gets a new key rather
     than a migration that has to guess what an old document meant. */
  const KEY = 'incompetech.playlists.v1';
  const SCHEMA = 1;

  /* The stored document.
   *
   *     { schema, active, playlists: [
   *         { id, name, created, updated, items: [ {filename, title, added} ] }
   *     ] }
   *
   * Deliberately server-shaped, so that the day this moves behind a login the
   * document travels as-is: ids are random and generated here rather than
   * being array positions, so two browsers' playlists can be merged into one
   * account without renumbering; every record carries its own timestamps; and
   * `items` holds catalogue keys rather than catalogue rows, so a playlist
   * synced from anywhere resolves against whatever the catalogue says now.
   * `active` is this browser's own UI state and is the one field an export
   * drops.
   */

  let doc = null;           // the document, once read
  let broken = '';          // why storage is unusable, if it is

  function newId() {
    // crypto.randomUUID is not on http:// origins in some browsers, and this
    // id has to be stable for the life of a playlist, so there is a fallback.
    try {
      return crypto.randomUUID();
    } catch (e) {
      return 'pl-' + Date.now().toString(36) + '-' +
        Math.random().toString(36).slice(2, 10);
    }
  }

  const now = () => new Date().toISOString();

  function blank() {
    return { schema: SCHEMA, active: '', playlists: [] };
  }

  function read() {
    if (doc) return doc;
    // Every access is guarded: localStorage is absent in some embeddings and
    // *throws on read* in a browser set to block site data — not returns
    // null. An exception here would take the whole page down with it, over a
    // feature the page works fine without.
    try {
      const raw = localStorage.getItem(KEY);
      doc = raw ? sane(JSON.parse(raw)) : blank();
    } catch (e) {
      broken = 'this browser is not letting the page store anything, so ' +
               'playlists cannot be saved here';
      doc = blank();
    }
    return doc;
  }

  function write() {
    if (broken) return false;
    try {
      localStorage.setItem(KEY, JSON.stringify(doc));
      return true;
    } catch (e) {
      // Quota, or storage disabled between load and now. The in-memory copy
      // is still right, so the page keeps working for this visit and says
      // plainly that it will not survive a reload.
      broken = 'could not save: ' + (e && e.name === 'QuotaExceededError'
        ? 'this browser’s storage for the site is full'
        : (e && e.message) || 'storage refused the write');
      return false;
    }
  }

  /* A parsed document is untrusted input — it may be an old shape, or a file
     someone hand-edited and imported. Anything unrecognisable is dropped
     rather than allowed to reach the rendering code as undefined. */
  function sane(raw) {
    const out = blank();
    if (!raw || typeof raw !== 'object') return out;
    const lists = Array.isArray(raw.playlists) ? raw.playlists : [];
    for (const pl of lists) {
      const clean = sanePlaylist(pl);
      if (clean) out.playlists.push(clean);
    }
    out.active = typeof raw.active === 'string' ? raw.active : '';
    if (!out.playlists.some((p) => p.id === out.active)) {
      out.active = out.playlists.length ? out.playlists[0].id : '';
    }
    return out;
  }

  function sanePlaylist(pl) {
    if (!pl || typeof pl !== 'object') return null;
    const items = [];
    const seen = new Set();
    for (const it of (Array.isArray(pl.items) ? pl.items : [])) {
      const filename = it && typeof it.filename === 'string' ? it.filename : '';
      // A playlist is a set, not a bag: the same piece twice is a credit
      // printed twice and a download fetched twice.
      if (!filename || seen.has(filename)) continue;
      seen.add(filename);
      items.push({
        filename,
        title: typeof it.title === 'string' && it.title ? it.title : filename,
        added: typeof it.added === 'string' ? it.added : now(),
      });
    }
    return {
      id: typeof pl.id === 'string' && pl.id ? pl.id : newId(),
      name: name(pl.name),
      created: typeof pl.created === 'string' ? pl.created : now(),
      updated: typeof pl.updated === 'string' ? pl.updated : now(),
      items,
    };
  }

  const MAX_NAME = 80;

  function name(value) {
    const s = String(value == null ? '' : value).replace(/\s+/g, ' ').trim();
    return (s || 'Untitled playlist').slice(0, MAX_NAME);
  }

  /* ---------------------------------------------------------------- CRUD */

  const all = () => read().playlists;
  const find = (id) => read().playlists.find((p) => p.id === id) || null;
  const active = () => find(read().active);

  function touch(pl) {
    pl.updated = now();
    write();
  }

  function create(rawName) {
    const pl = { id: newId(), name: name(rawName), created: now(),
                 updated: now(), items: [] };
    read().playlists.push(pl);
    doc.active = pl.id;
    write();
    return pl;
  }

  function rename(id, rawName) {
    const pl = find(id);
    if (!pl) return null;
    pl.name = name(rawName);
    touch(pl);
    return pl;
  }

  function remove(id) {
    const d = read();
    d.playlists = d.playlists.filter((p) => p.id !== id);
    if (d.active === id) d.active = d.playlists.length ? d.playlists[0].id : '';
    write();
  }

  function duplicate(id) {
    const pl = find(id);
    if (!pl) return null;
    const copy = { id: newId(), name: name(pl.name + ' copy'), created: now(),
                   updated: now(), items: pl.items.map((i) => ({ ...i })) };
    read().playlists.push(copy);
    doc.active = copy.id;
    write();
    return copy;
  }

  function select(id) {
    if (!find(id)) return;
    read().active = id;
    write();
  }

  function has(id, filename) {
    const pl = find(id);
    return !!pl && pl.items.some((i) => i.filename === filename);
  }

  function add(id, piece) {
    const pl = find(id);
    if (!pl || !piece || !piece.filename) return false;
    if (pl.items.some((i) => i.filename === piece.filename)) return false;
    pl.items.push({ filename: piece.filename,
                    title: piece.title || piece.filename, added: now() });
    touch(pl);
    return true;
  }

  function drop(id, filename) {
    const pl = find(id);
    if (!pl) return;
    pl.items = pl.items.filter((i) => i.filename !== filename);
    touch(pl);
  }

  /* Order is the playlist's own and is what every export is written in, so
     moving an item is a first-class operation rather than a re-sort. */
  function move(id, filename, delta) {
    const pl = find(id);
    if (!pl) return;
    const at = pl.items.findIndex((i) => i.filename === filename);
    const to = at + delta;
    if (at < 0 || to < 0 || to >= pl.items.length) return;
    const [item] = pl.items.splice(at, 1);
    pl.items.splice(to, 0, item);
    touch(pl);
  }

  /* --------------------------------------------------------- resolving */

  /* How many names one request may carry.
   *
   * The bound is not this app's, it is the proxy's request-line buffer, and
   * the arithmetic is the whole reason for the number: a name averages a bit
   * over twenty characters, most of its spaces become `%20`, and `filename=`
   * and `&` add ten more — so fifty names is roughly two kilobytes, well
   * inside nginx's default eight, with room for the outliers. The server
   * refuses more than MAX_FILENAMES, but the page deliberately asks for less
   * than it may: past the buffer the reply is nginx's own 414 HTML, which
   * this app never sees and the page cannot read. */
  const BATCH = 50;

  /* The playlist's items as current catalogue rows, in the playlist's order.
   *
   * Returns `{rows}` or `{error}` — never a bare null. The caller has to be
   * able to *say* what went wrong: app.js's `getJSON` reports only a fetch or
   * parse that threw, so a 503 (no database yet) or a 400 comes back here
   * parsed, unreported, and looking like an ordinary answer. Handed back as
   * an error it reaches the panel, which has a line to put it on.
   *
   * Anything the catalogue no longer has comes back with `missing: true` and
   * its stored title rather than being dropped: a piece silently vanishing
   * from a credit block is the one failure that produces a wrong licence
   * statement instead of a visible problem.
   */
  async function resolve(pl, fetchJSON) {
    if (!pl || !pl.items.length) return { rows: [] };
    const byName = new Map();
    for (let i = 0; i < pl.items.length; i += BATCH) {
      const batch = pl.items.slice(i, i + BATCH);
      const q = new URLSearchParams();
      for (const it of batch) q.append('filename', it.filename);
      q.append('limit', String(batch.length));
      const doc_ = await fetchJSON('/api/pieces?' + q.toString());
      if (!doc_) return { error: 'the server did not answer' };
      if (doc_.error) return { error: doc_.error };
      for (const p of doc_.pieces || []) byName.set(p.filename, p);
    }
    return { rows: pl.items.map((it) => byName.get(it.filename) ||
      { filename: it.filename, title: it.title, missing: true,
        length_s: null, bpm: null, feels: [], instruments: [] }) };
  }

  /* ---------------------------------------------------------- exporting */

  /* The blanket credit. Taken from /api/meta where that answered, and
     otherwise from the sentence in the page's own markup — which is there
     precisely so the licence line never depends on a fetch succeeding. */
  let attribution = '';
  let licenseUrl = 'https://creativecommons.org/licenses/by/4.0/';

  function setMeta(m) {
    if (m && m.attribution) attribution = m.attribution;
    if (m && m.license_url) licenseUrl = m.license_url;
  }

  function blanket() {
    if (attribution) return attribution;
    const el = document.getElementById('credit-line');
    return (el && el.textContent.replace(/\s+/g, ' ').trim()) ||
      'Music by Kevin MacLeod (incompetech.com), licensed under ' +
      'Creative Commons: By Attribution 4.0';
  }

  /* The credit block: the thing this feature exists for. Each line is the
     `credit` the API put on the row — the sentence incompetech's own licence
     page generates — never one rebuilt here out of a title. */
  function credits(pl, rows) {
    const out = [blanket(), licenseUrl, '', pl.name, ''];
    for (const r of rows) {
      if (!r.missing) out.push(r.credit);
    }
    const missing = rows.filter((r) => r.missing);
    if (missing.length) {
      out.push('');
      out.push('# The catalogue no longer lists these, so no credit for them');
      out.push('# could be read from it. Check them before you publish:');
      for (const r of missing) out.push('#   ' + r.title + '  (' + r.filename + ')');
    }
    return out.join('\n') + '\n';
  }

  /* An .m3u pointing at incompetech.com's own files. Nothing is rehosted and
     nothing is fetched here — this is a list of where the music is, which is
     what "download ease" can honestly mean for a catalogue we only index. */
  function m3u(pl, rows) {
    const out = ['#EXTM3U', '#PLAYLIST:' + pl.name, '# ' + blanket()];
    for (const r of rows) {
      if (r.missing || !r.mp3_url) continue;
      out.push('#EXTINF:' + (r.length_s == null ? -1 : r.length_s) + ',' + r.title);
      out.push(r.mp3_url);
    }
    return out.join('\n') + '\n';
  }

  /* URLs and nothing else — no header, no comment line. This one is meant to
     be piped to `wget -i` / `curl -K`, and those read every line as a URL: a
     `#` credit line at the top would become a request for a file called "#". */
  function urls(_pl, rows) {
    return rows.filter((r) => !r.missing && r.mp3_url)
               .map((r) => r.mp3_url).join('\n') + '\n';
  }

  /* The portable form, and the import format. One playlist, without this
     browser's `active`: the same object a signed-in store would be handed. */
  function asJSON(pl) {
    return JSON.stringify({ schema: SCHEMA, playlist: pl }, null, 1) + '\n';
  }

  /* Accepts either shape — one exported playlist, or a whole document from
     another browser — and always adds rather than replaces. An import that
     silently overwrote what is already here would be the one unrecoverable
     operation in the feature. */
  function importJSON(text) {
    let raw;
    try {
      raw = JSON.parse(text);
    } catch (e) {
      return { added: 0, error: 'that file is not JSON: ' + e.message };
    }
    const incoming = raw && raw.playlist ? [raw.playlist]
      : (raw && Array.isArray(raw.playlists) ? raw.playlists : []);
    if (!incoming.length) {
      return { added: 0, error: 'no playlist in that file' };
    }
    const d = read();
    let added = 0;
    for (const pl of incoming) {
      const clean = sanePlaylist(pl);
      if (!clean) continue;
      // A fresh id always: importing a file exported from this same browser
      // must not overwrite the playlist it came from.
      clean.id = newId();
      d.playlists.push(clean);
      d.active = clean.id;
      added += 1;
    }
    write();
    return { added, error: added ? '' : 'nothing in that file was a playlist' };
  }

  return { KEY, SCHEMA, MAX_NAME, BATCH,
           read, all, find, active, create, rename, remove, duplicate, select,
           has, add, drop, move, resolve, setMeta, blanket,
           credits, m3u, urls, asJSON, importJSON,
           trouble: () => broken };
})();

window.Playlists = Playlists;


/* ======================================================================
 * The panel.
 *
 * Separate from the store above on purpose: the store is the part a
 * signed-in backend would replace, and it does not touch the DOM. This half
 * does nothing but render it, and reads the catalogue through the `fetchJSON`
 * the page hands it rather than fetching on its own — so there is one place
 * where a dead server is reported, and it is app.js's.
 * ====================================================================== */

(() => {
  const P = window.Playlists;
  const $ = (id) => document.getElementById(id);

  let getJSON = null;       // app.js's fetch-and-report-errors
  let rows = [];            // the active playlist, resolved, in its order
  let seq = 0;              // a slow resolve must not overwrite a fast one

  /* Rows already read from the catalogue this sitting, by filename.
   *
   * Re-reading is what keeps a credit current, but *reordering* a playlist
   * does not change which pieces are in it — and going back to the server on
   * every ↑ made a click that only moves a row wait on a round trip, and
   * redraw a beat after the press. So a resolve asks only for the names it
   * has not seen, and the cache is emptied at the two moments the answer can
   * have changed under it: opening the panel, and switching playlist. A build
   * that lands mid-sitting is picked up by the next of those, which is also
   * the next time anyone looks.
   */
  let seen = new Map();
  let failure = '';         // why the last resolve could not answer
  let shownFor = '';        // the playlist the table on screen belongs to

  /* ------------------------------------------------------------- render */

  /* Two things can go wrong and both belong on one line: the browser refusing
     to store anything, and the catalogue refusing to answer. */
  function showTrouble() {
    const msg = P.trouble() || failure;
    $('pl_trouble').textContent = msg;
    $('pl_trouble').hidden = !msg;
  }

  function refresh() {
    // The lists first: `P.trouble()` only has an answer once the store has
    // been read, and reading it is what discovers that it cannot be read. Ask
    // the other way round and the very first render — the one where someone
    // is about to start collecting into a browser that will not keep any of
    // it — is the one render that says nothing.
    const lists = P.all();
    const cur = P.active();
    showTrouble();

    const sel = $('pl_select');
    sel.innerHTML = '';
    if (!lists.length) {
      const o = document.createElement('option');
      o.value = '';
      o.textContent = 'none yet';
      sel.appendChild(o);
    }
    for (const pl of lists) {
      const o = document.createElement('option');
      o.value = pl.id;
      // textContent, never innerHTML: the name is whatever someone typed.
      o.textContent = `${pl.name} (${pl.items.length})`;
      sel.appendChild(o);
    }
    if (cur) sel.value = cur.id;

    for (const id of ['pl_rename', 'pl_dup', 'pl_delete', 'pl_toggle']) {
      $(id).disabled = !cur;
    }
    sel.disabled = !lists.length;

    $('pl_summary').textContent = cur
      ? `${cur.items.length} piece${cur.items.length === 1 ? '' : 's'}`
      : 'no playlist yet — press New, or + on any result below';

    syncRows();
    if (!$('pl_panel').hidden) load();
  }

  /* Re-read the active playlist from the catalogue and draw it. */
  async function load() {
    const cur = P.active();
    const mine = ++seq;
    const body = $('pl_rows');
    if (!cur || !cur.items.length) {
      rows = [];
      shownFor = cur ? cur.id : '';
      failure = '';
      showTrouble();
      body.innerHTML = '';
      $('pl_table').hidden = true;
      $('pl_empty').hidden = false;
      $('pl_total').textContent = '';
      setExportsEnabled(false);
      return;
    }
    $('pl_empty').hidden = true;
    const wanted = { items: cur.items.filter((i) => !seen.has(i.filename)) };
    if (wanted.items.length) {
      // Before yielding: `rows` still holds whatever was resolved last, and
      // an export reads `rows` for its content and the *active* playlist for
      // its name. Left enabled across the await, one click in that window
      // writes a file named after this playlist carrying the last one's
      // credits — a wrong attribution, produced by the feature whose whole
      // job is getting attribution right. So the exports go with the rows.
      rows = [];
      setExportsEnabled(false);
      // Rows on screen from another playlist are cleared too; rows from this
      // one are left up, because blanking the table for a round trip every
      // time a piece is added would be worse than a moment of staleness.
      if (shownFor !== cur.id) {
        body.innerHTML = '';
        $('pl_table').hidden = true;
      }
      const out = await P.resolve(wanted, getJSON);
      if (mine !== seq) return;             // a newer load has started
      if (out.error) {
        // Not every refusal reaches app.js's error line — a 503 or a 400 comes
        // back parsed rather than thrown — so the panel says it itself, rather
        // than showing an empty table with no rows, no empty-state and no
        // reason.
        failure = 'could not read the playlist: ' + out.error;
        showTrouble();
        $('pl_empty').hidden = true;
        return;
      }
      for (const r of out.rows) seen.set(r.filename, r);
    }
    failure = '';
    showTrouble();
    rows = cur.items.map((i) => seen.get(i.filename));
    shownFor = cur.id;
    body.innerHTML = '';
    for (const r of rows) body.appendChild(itemRow(cur, r));
    $('pl_table').hidden = false;
    setExportsEnabled(true);

    const known = rows.filter((r) => !r.missing && r.length_s != null);
    const secs = known.reduce((n, r) => n + r.length_s, 0);
    const missing = rows.filter((r) => r.missing).length;
    const unknown = rows.length - known.length - missing;
    $('pl_total').textContent =
      `${rows.length} piece${rows.length === 1 ? '' : 's'}, ${hms(secs)} total` +
      (unknown ? ` (${unknown} of unknown length)` : '') +
      (missing ? ` — ${missing} no longer in the catalogue` : '');
  }

  function itemRow(pl, r) {
    const tr = document.createElement('tr');
    if (r.missing) tr.className = 'gone';

    const ord = document.createElement('td');
    ord.className = 'ord';
    const up = smallButton('↑', 'Move up', () => { P.move(pl.id, r.filename, -1); refresh(); });
    const down = smallButton('↓', 'Move down', () => { P.move(pl.id, r.filename, 1); refresh(); });
    ord.appendChild(up);
    ord.appendChild(down);

    const title = document.createElement('td');
    title.className = 'title';
    if (r.missing) {
      title.textContent = r.title;
    } else {
      // The catalogue's own page for the piece, as in the results table:
      // checking what you are about to credit should not mean finding the
      // row again in the list below.
      const a = document.createElement('a');
      a.href = r.page_url || r.mp3_url;
      a.textContent = r.title;
      a.rel = 'noopener';
      a.target = '_blank';
      title.appendChild(a);
    }
    if (r.missing) {
      const note = document.createElement('span');
      note.className = 'desc';
      note.textContent = 'not in the current catalogue — ' + r.filename;
      title.appendChild(note);
    }

    const cut = document.createElement('td');
    cut.className = 'play';
    cut.appendChild(smallButton('×', 'Remove from playlist',
      () => { P.drop(pl.id, r.filename); refresh(); }));

    tr.appendChild(ord);
    tr.appendChild(title);
    tr.appendChild(cell(hms(r.length_s), 'num'));
    tr.appendChild(cell(r.bpm == null ? '—' : String(r.bpm), 'num'));
    tr.appendChild(cell(r.genre || '—'));
    tr.appendChild(cut);
    return tr;
  }

  function cell(text, cls) {
    const td = document.createElement('td');
    if (cls) td.className = cls;
    td.textContent = text;
    return td;
  }

  function smallButton(glyph, label, onClick) {
    const b = document.createElement('button');
    b.type = 'button';
    b.className = 'mini';
    b.textContent = glyph;
    b.title = label;
    b.setAttribute('aria-label', label);
    b.addEventListener('click', onClick);
    return b;
  }

  function setExportsEnabled(on) {
    for (const id of ['pl_copy', 'pl_credits', 'pl_m3u', 'pl_urls', 'pl_json']) {
      $(id).disabled = !on;
    }
  }

  /* ------------------------------------------------- the results table */

  /* The add/remove button for one row of the search results. app.js calls
     this while building the row, so the two tables stay one page rather than
     two views that can disagree about what is in a playlist. */
  function addCell(piece) {
    const td = document.createElement('td');
    td.className = 'add';
    const b = document.createElement('button');
    b.type = 'button';
    b.className = 'addbtn';
    b.dataset.filename = piece.filename;
    b.addEventListener('click', () => {
      let cur = P.active();
      // No playlist yet: the first + makes one rather than refusing. It is
      // one click to undo (Delete) and refusing would be a dead button with
      // no explanation of what to press first.
      if (!cur) cur = P.create('My playlist');
      if (P.has(cur.id, piece.filename)) P.drop(cur.id, piece.filename);
      else P.add(cur.id, piece);
      refresh();
    });
    markAdd(b);
    td.appendChild(b);
    return td;
  }

  function markAdd(b) {
    const cur = P.active();
    const inList = !!cur && P.has(cur.id, b.dataset.filename);
    b.setAttribute('aria-pressed', String(inList));
    b.textContent = inList ? '✓' : '+';
    const where = cur ? '“' + cur.name + '”' : 'a new playlist';
    b.title = inList ? 'Remove from ' + where : 'Add to ' + where;
    b.setAttribute('aria-label', b.title);
  }

  function syncRows() {
    for (const b of document.querySelectorAll('.addbtn')) markAdd(b);
  }

  /* ------------------------------------------------------------ exports */

  function stem() {
    const cur = P.active();
    // A playlist name is free text and is about to become a filename.
    const base = (cur ? cur.name : 'playlist')
      .replace(/[^\w \-.]+/g, '').replace(/\s+/g, '-').replace(/^[-.]+/, '');
    return base || 'playlist';
  }

  function save(text, suffix, mime) {
    const blob = new Blob([text], { type: mime + ';charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = stem() + suffix;
    document.body.appendChild(a);
    a.click();
    a.remove();
    // Revoked on the next turn: revoking synchronously can beat the click
    // through in some browsers and save a zero-byte file.
    setTimeout(() => URL.revokeObjectURL(url), 0);
  }

  function say(msg) {
    $('pl_note').textContent = msg;
    if (msg) setTimeout(() => { $('pl_note').textContent = ''; }, 4000);
  }

  async function copyCredits() {
    const cur = P.active();
    if (!cur) return;
    const text = P.credits(cur, rows);
    try {
      await navigator.clipboard.writeText(text);
      say('credits copied');
    } catch (e) {
      // Clipboard is refused without a secure context or a user gesture the
      // browser recognises. Saying so beats a button that does nothing.
      say('this browser would not let the page write to the clipboard — ' +
          'use “credits .txt” instead');
    }
  }

  /* -------------------------------------------------------------- wiring */

  function wire() {
    $('pl_select').addEventListener('change', () => {
      P.select($('pl_select').value);
      seen = new Map();             // another playlist, read afresh
      refresh();
    });
    $('pl_new').addEventListener('click', () => {
      const n = prompt('Name for the new playlist:', 'My playlist');
      if (n === null) return;
      P.create(n);
      openPanel(true);
    });
    $('pl_rename').addEventListener('click', () => {
      const cur = P.active();
      if (!cur) return;
      const n = prompt('Rename the playlist:', cur.name);
      if (n === null) return;
      P.rename(cur.id, n);
      refresh();
    });
    $('pl_dup').addEventListener('click', () => {
      const cur = P.active();
      if (cur) { P.duplicate(cur.id); refresh(); }
    });
    $('pl_delete').addEventListener('click', () => {
      const cur = P.active();
      if (!cur) return;
      // The one irreversible thing here: there is no server copy to restore
      // from, so it asks, and it says what it is about to lose.
      if (!confirm(`Delete “${cur.name}” and its ${cur.items.length} ` +
                   `piece${cur.items.length === 1 ? '' : 's'}? ` +
                   'Playlists are stored in this browser only, so this ' +
                   'cannot be undone.')) return;
      P.remove(cur.id);
      refresh();
    });
    $('pl_toggle').addEventListener('click', () => openPanel($('pl_panel').hidden));
    $('pl_import').addEventListener('click', () => $('pl_file').click());
    $('pl_file').addEventListener('change', async () => {
      const file = $('pl_file').files[0];
      if (!file) return;
      const result = P.importJSON(await file.text());
      $('pl_file').value = '';      // so the same file can be chosen again
      openPanel(true);
      say(result.error || `imported ${result.added} playlist` +
                          `${result.added === 1 ? '' : 's'}`);
    });

    $('pl_copy').addEventListener('click', copyCredits);
    $('pl_credits').addEventListener('click', () => {
      const cur = P.active();
      if (cur) save(P.credits(cur, rows), '-credits.txt', 'text/plain');
    });
    $('pl_m3u').addEventListener('click', () => {
      const cur = P.active();
      if (cur) save(P.m3u(cur, rows), '.m3u', 'audio/x-mpegurl');
    });
    $('pl_urls').addEventListener('click', () => {
      const cur = P.active();
      if (cur) save(P.urls(cur, rows), '-urls.txt', 'text/plain');
    });
    $('pl_json').addEventListener('click', () => {
      const cur = P.active();
      if (cur) save(P.asJSON(cur), '.json', 'application/json');
    });
  }

  function openPanel(open) {
    if (open) seen = new Map();     // opening it is a request for current facts
    $('pl_panel').hidden = !open;
    $('pl_toggle').setAttribute('aria-expanded', String(open));
    $('pl_toggle').textContent = open ? 'Hide' : 'Show';
    refresh();
  }

  function hms(secs) {
    if (secs == null) return '?';
    const h = Math.floor(secs / 3600);
    const m = Math.floor((secs % 3600) / 60);
    const s = secs % 60;
    const two = (n) => String(n).padStart(2, '0');
    return h ? `${h}:${two(m)}:${two(s)}` : `${m}:${two(s)}`;
  }

  /* Called by app.js once /api/health has said there is a catalogue to
     collect from. `fetch` is app.js's, so a dead server is reported once. */
  function boot(fetchJSON) {
    getJSON = fetchJSON;
    wire();
    $('playlists').hidden = false;
    refresh();
    // The blanket credit for the exports, from the authority rather than from
    // this file. Deliberately not awaited: the results table is not waiting on
    // a line that is only read when someone presses Copy credits, and if this
    // never answers `blanket()` falls back to the sentence in the page's own
    // markup — which is why that sentence is in the markup.
    fetchJSON('/api/meta').then((m) => { if (m) P.setMeta(m); });
  }

  Object.assign(P, { boot, addCell, syncRows, refresh });
})();
