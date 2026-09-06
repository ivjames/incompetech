/* The filter page. No framework, no build step, no CDN — one file that reads
   /api/facets to build its controls and /api/pieces to fill the table, plus
   playlists.js, which owns the browser-local collections and the two hooks
   this file calls into: `addCell` for a row's + button and `syncRows` after
   every render.
 *
 * Two decisions worth knowing:
 *
 *  - Nothing about the catalogue is written here. Every option in every
 *    select, every feel chip and every sort comes from /api/facets, so a
 *    collection added upstream appears after a rebuild without touching this
 *    file. The one exception is the credit line, which is in the HTML because
 *    a licence obligation must not depend on a fetch succeeding.
 *  - Previews play from incompetech.com's own mp3_url through a single
 *    <audio> element. Nothing is rehosted, and one element means starting a
 *    second preview stops the first for free.
 */
'use strict';

const $ = (id) => document.getElementById(id);
const PAGE = 50;

const state = {
  feels: new Set(),
  feelMode: 'all',      // 'all' -> ?feel= (AND); 'any' -> ?feel_any= (OR)
  offset: 0,
  total: 0,
  playing: null,
  seq: 0,               // guards against a slow response overwriting a fast one
};

/* ------------------------------------------------------------------ boot */

async function boot() {
  const health = await getJSON('/api/health');
  if (!health) {
    // Health did not answer, or did not answer JSON — a 502 from nginx, a
    // dead upstream. getJSON has already written why into #error. Saying "no
    // catalogue database yet, run incompetech build" here would send someone
    // to rebuild a database on a server that is not running.
    return;
  }
  if (!health.built) {
    // Health answered, and said there is nothing to serve yet.
    $('nodb').hidden = false;
    return;
  }
  $('app').hidden = false;
  $('built').textContent = health.pieces + ' pieces, built ' +
    (health.built_at || '').replace('T', ' ').replace('+00:00', ' UTC');

  const facets = await getJSON('/api/facets');
  if (!facets || facets.error) { showError(facets && facets.error); return; }
  buildControls(facets);
  wire();
  // Playlists come up only here, after health said there is something to
  // collect: a playlist over an unbuilt catalogue could be shown but not
  // resolved, so every credit and every URL in it would be blank.
  window.Playlists.boot(getJSON);
  search();
}

async function getJSON(url) {
  try {
    const r = await fetch(url, { headers: { Accept: 'application/json' } });
    return await r.json();
  } catch (e) {
    showError('could not reach the server: ' + e.message);
    return null;
  }
}

/* -------------------------------------------------------------- controls */

function buildControls(f) {
  fillSelect($('sort'), f.sorts.map((s) => [s, s]), 'title');
  fillSelect($('genre'), f.genres.map((g) => [g.name, `${g.name} (${g.count})`]), '');
  fillSelect($('category'), f.categories.map((c) => [c.category, c.category]), '');
  fillSelect($('instrument'),
    f.instruments.filter((i) => i.count > 0)
                 .map((i) => [i.name, `${i.name} (${i.count})`]), '');

  // Collection depends on category: choosing one narrows the other, which is
  // how the catalogue itself is organised — 50 collections in one flat list
  // is not a control anybody can use.
  state.categories = f.categories;
  fillCollections('');
  $('category').addEventListener('change', () => {
    fillCollections($('category').value);
    state.offset = 0;
    search();
  });

  const chips = $('feelchips');
  for (const feel of f.feels) {
    const b = document.createElement('button');
    b.type = 'button';
    b.className = 'chip' + (feel.canonical ? '' : ' odd');
    b.setAttribute('aria-pressed', 'false');
    b.dataset.feel = feel.name;
    // A feel outside the page's own 20-word vocabulary is italic and titled:
    // it is real data, not a typo, but it is not one of the standard chips.
    if (!feel.canonical) b.title = 'not one of the catalogue’s own feel words';
    b.innerHTML = escapeHTML(feel.name) + '<span class="n">' + feel.count + '</span>';
    b.addEventListener('click', () => {
      b.setAttribute('aria-pressed', state.feels.has(feel.name) ? 'false' : 'true');
      if (state.feels.has(feel.name)) state.feels.delete(feel.name);
      else state.feels.add(feel.name);
      state.offset = 0;
      search();
    });
    chips.appendChild(b);
  }
}

function fillCollections(category) {
  const groups = category
    ? state.categories.filter((c) => c.category === category)
    : state.categories;
  const opts = [];
  for (const g of groups) {
    for (const c of g.collections) {
      if (c.count > 0) opts.push([c.name, `${c.name} (${c.count})`]);
    }
  }
  fillSelect($('collection'), opts, '');
}

function fillSelect(sel, pairs, selected) {
  sel.innerHTML = '';
  const any = document.createElement('option');
  any.value = '';
  any.textContent = sel.id === 'sort' ? 'title' : 'any';
  sel.appendChild(any);
  for (const [value, label] of pairs) {
    if (sel.id === 'sort' && value === 'title') continue;
    const o = document.createElement('option');
    o.value = value;
    o.textContent = label;
    sel.appendChild(o);
  }
  if (selected) sel.value = selected;
}

function wire() {
  const rerun = () => { state.offset = 0; search(); };
  $('text').addEventListener('input', debounce(rerun, 250));
  for (const id of ['sort', 'desc', 'genre', 'collection', 'instrument',
                    'bpm_min', 'bpm_max', 'bpm_unknown', 'min_length',
                    'max_length', 'since', 'until']) {
    $(id).addEventListener('change', rerun);
  }
  // Asking for the unmeasured tempos and for a tempo range are opposite
  // questions — the API refuses the pair, so the page stops offering it.
  $('bpm_unknown').addEventListener('change', () => {
    const off = $('bpm_unknown').checked;
    $('bpm_min').disabled = off;
    $('bpm_max').disabled = off;
    if (off) { $('bpm_min').value = ''; $('bpm_max').value = ''; }
  });
  $('feelmode').addEventListener('click', () => {
    state.feelMode = state.feelMode === 'all' ? 'any' : 'all';
    const b = $('feelmode');
    b.textContent = state.feelMode === 'all' ? 'ALL' : 'ANY';
    b.setAttribute('aria-pressed', String(state.feelMode === 'all'));
    if (state.feels.size > 1) { state.offset = 0; search(); }
  });
  $('clearfeels').addEventListener('click', () => {
    state.feels.clear();
    for (const b of document.querySelectorAll('.chip')) b.setAttribute('aria-pressed', 'false');
    state.offset = 0;
    search();
  });
  $('reset').addEventListener('click', () => {
    $('filters').reset();
    state.feels.clear();
    for (const b of document.querySelectorAll('.chip')) b.setAttribute('aria-pressed', 'false');
    $('bpm_min').disabled = false;
    $('bpm_max').disabled = false;
    fillCollections('');
    state.offset = 0;
    search();
  });
  $('prev').addEventListener('click', () => {
    state.offset = Math.max(0, state.offset - PAGE);
    search();
  });
  $('next').addEventListener('click', () => {
    if (state.offset + PAGE < state.total) { state.offset += PAGE; search(); }
  });
  $('filters').addEventListener('submit', (e) => e.preventDefault());
}

/* --------------------------------------------------------------- querying */

function query() {
  const q = new URLSearchParams();
  const put = (k, v) => { if (v !== '' && v != null) q.append(k, v); };
  put('text', $('text').value.trim());
  for (const feel of state.feels) q.append(state.feelMode === 'all' ? 'feel' : 'feel_any', feel);
  put('genre', $('genre').value);
  put('collection', $('collection').value);
  put('category', $('category').value);
  put('instrument', $('instrument').value);
  if ($('bpm_unknown').checked) put('bpm_unknown', '1');
  else { put('bpm_min', $('bpm_min').value); put('bpm_max', $('bpm_max').value); }
  put('min_length', $('min_length').value.trim());
  put('max_length', $('max_length').value.trim());
  put('since', $('since').value.trim());
  put('until', $('until').value.trim());
  put('sort', $('sort').value || 'title');
  if ($('desc').checked) put('desc', '1');
  put('limit', PAGE);
  if (state.offset) put('offset', state.offset);
  return q;
}

async function search() {
  const seq = ++state.seq;
  const doc = await getJSON('/api/pieces?' + query().toString());
  if (!doc || seq !== state.seq) return;
  if (doc.error) {
    // The count and the pager describe the results, so they have to go with
    // them: "1442 pieces match" over an empty table, with next → still live,
    // is the old answer pretending to be this one.
    state.total = 0;
    showError(doc.error);
    render([]);
    return;
  }
  showError('');
  state.total = doc.total;
  render(doc.pieces);
}

/* --------------------------------------------------------------- printing */

function render(pieces) {
  const body = $('rows');
  body.innerHTML = '';
  for (const p of pieces) body.appendChild(rowFor(p));
  window.Playlists.syncRows();

  $('count').textContent = state.total === 0
    ? 'nothing matches'
    : `${state.total} piece${state.total === 1 ? '' : 's'} match`;
  const from = state.total ? state.offset + 1 : 0;
  const to = Math.min(state.offset + PAGE, state.total);
  $('page').textContent = state.total > PAGE ? `showing ${from}–${to}` : '';
  $('prev').disabled = state.offset === 0;
  $('next').disabled = state.offset + PAGE >= state.total;
}

function rowFor(p) {
  const tr = document.createElement('tr');

  const play = document.createElement('td');
  play.className = 'play';
  const b = document.createElement('button');
  b.type = 'button';
  b.className = 'playbtn';
  b.setAttribute('aria-pressed', 'false');
  b.setAttribute('aria-label', 'Preview ' + p.title);
  b.textContent = '▶';
  b.addEventListener('click', () => toggle(p, b));
  play.appendChild(b);

  const title = document.createElement('td');
  title.className = 'title';
  const a = document.createElement('a');
  // The catalogue's own page for the piece. It resolves an ISRC client-side,
  // so a piece with no ISRC simply has no page and gets plain text.
  a.href = p.page_url || p.mp3_url;
  a.textContent = p.title;
  a.rel = 'noopener';
  a.target = '_blank';
  title.appendChild(a);
  if (p.description) {
    const d = document.createElement('span');
    d.className = 'desc';
    d.textContent = p.description;
    title.appendChild(d);
  }

  tr.appendChild(play);
  tr.appendChild(window.Playlists.addCell(p));
  tr.appendChild(title);
  tr.appendChild(cell(hms(p.length_s), 'num'));
  tr.appendChild(cell(p.bpm == null ? '—' : String(p.bpm), 'num'));
  tr.appendChild(cell(p.genre || '—'));
  tr.appendChild(cell(p.collection || '—'));
  tr.appendChild(cell((p.feels || []).join(', '), 'feels'));
  return tr;
}

function cell(text, cls) {
  const td = document.createElement('td');
  if (cls) td.className = cls;
  td.textContent = text;
  return td;
}

function toggle(p, button) {
  const player = $('player');
  const pressed = button.getAttribute('aria-pressed') === 'true';
  for (const b of document.querySelectorAll('.playbtn')) {
    b.setAttribute('aria-pressed', 'false');
    b.textContent = '▶';
  }
  if (pressed) {
    player.pause();
    $('playing').textContent = '';
    state.playing = null;
    return;
  }
  // Straight from incompetech.com. We index the catalogue; we do not host it.
  player.src = p.mp3_url;
  player.play().catch(() => { $('playing').textContent = 'could not play ' + p.title; });
  button.setAttribute('aria-pressed', 'true');
  button.textContent = '■';
  state.playing = p.filename;
  $('playing').textContent = '♪ ' + p.credit;
  player.onended = () => {
    button.setAttribute('aria-pressed', 'false');
    button.textContent = '▶';
    $('playing').textContent = '';
  };
}

/* ------------------------------------------------------------------ util */

function hms(secs) {
  if (secs == null) return '?';
  const h = Math.floor(secs / 3600);
  const m = Math.floor((secs % 3600) / 60);
  const s = secs % 60;
  const two = (n) => String(n).padStart(2, '0');
  return h ? `${h}:${two(m)}:${two(s)}` : `${m}:${two(s)}`;
}

function showError(msg) {
  const el = $('error');
  el.textContent = msg || '';
  el.hidden = !msg;
}

function escapeHTML(s) {
  return String(s).replace(/[&<>"']/g, (c) => (
    { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}

function debounce(fn, ms) {
  let t;
  return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); };
}

boot();
