// Album browser: facets, search, grid/list, sorting, column picker. No dependencies.
(function () {
  'use strict';
  var root = document.getElementById('browse');
  var JSON_URL = root.dataset.json;
  var PAGE = 60;

  var FACETS = [
    { key: 'genres',  label: 'Genre',        get: function (a) { return a.genres; } },
    { key: 'styles',  label: 'Style',        get: function (a) { return a.styles; } },
    { key: 'formats', label: 'Format',       get: function (a) { return a.formats; } },
    { key: 'src',     label: 'Source',       get: function (a) { return [SRC[a.src] || SRC.none]; } },
    { key: 'state',   label: 'US State',     get: function (a) { return a.state ? [a.state] : []; } },
    { key: 'country', label: 'Country',      get: function (a) { return a.country ? [a.country] : []; } },
    { key: 'labels',  label: 'Label',        get: function (a) { return a.labels; }, search: true },
    { key: 'artists', label: 'Artist',       get: function (a) { return a.artists; }, search: true }
  ];
  var COLUMNS = [
    { id: 'cover',    label: 'Cover',            sort: null },
    { id: 'artist',   label: 'Artist',           sort: 'artist' },
    { id: 'title',    label: 'Album',            sort: 'title' },
    { id: 'year',     label: 'Released',         sort: 'year' },
    { id: 'formats',  label: 'Format',           sort: 'formats' },
    { id: 'labels',   label: 'Label',            sort: 'labels' },
    { id: 'genres',   label: 'Genre',            sort: 'genres' },
    { id: 'styles',   label: 'Style',            sort: 'styles' },
    { id: 'state',    label: 'US State',         sort: 'state' },
    { id: 'country',  label: 'Country',          sort: 'country' },
    { id: 'added',    label: 'Added to collection', sort: 'added' },
    { id: 'uploaded', label: 'Uploaded',         sort: 'uploaded' },
    { id: 'links',    label: 'Links',            sort: null }
  ];
  var small = window.matchMedia('(max-width: 800px)').matches;
  var DEFAULT_COLS = small ? ['artist', 'title', 'year', 'formats']
                           : ['cover', 'artist', 'title', 'year', 'formats', 'labels', 'added'];

  var NA = 'N/A (No Discogs Page)';
  var SRC = { collection: "In BlueRoux's collection", discogs: 'On Discogs (not in his collection)', none: 'No Discogs page' };
  var $ = function (id) { return document.getElementById(id); };
  function store(k, v) { try { if (v === undefined) return localStorage.getItem(k); localStorage.setItem(k, v); } catch (e) {} return null; }
  function esc(s) { return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]; }); }
  function ytUrl(id) { return 'https://www.youtube.com/watch?v=' + id; }

  var data = null, albums = [];
  var state = {
    q: '', ymin: '', ymax: '', amin: '', amax: '',
    sel: {}, sort: 'uploaded:desc', view: store('br-view') || 'grid', shown: PAGE,
    cols: (function () { try { var c = JSON.parse(store('br-cols')); if (Array.isArray(c)) return c; } catch (e) {} return DEFAULT_COLS; })()
  };
  FACETS.forEach(function (f) { state.sel[f.key] = []; });
  var facetSearch = {};   // facet key -> text typed in its mini search
  var facetOpen = { genres: true, formats: true, state: true };

  // ---------- URL hash <-> state ----------
  function readHash() {
    var p = new URLSearchParams(location.hash.replace(/^#/, ''));
    state.q = p.get('q') || ''; state.ymin = p.get('ymin') || ''; state.ymax = p.get('ymax') || '';
    state.amin = p.get('amin') || ''; state.amax = p.get('amax') || '';
    if (p.get('sort')) state.sort = p.get('sort');
    if (p.get('view')) state.view = p.get('view');
    FACETS.forEach(function (f) { state.sel[f.key] = p.getAll(f.key); });
  }
  function writeHash() {
    var p = new URLSearchParams();
    if (state.q) p.set('q', state.q);
    ['ymin', 'ymax', 'amin', 'amax'].forEach(function (k) { if (state[k]) p.set(k, state[k]); });
    if (state.sort !== 'uploaded:desc') p.set('sort', state.sort);
    if (state.view !== 'grid') p.set('view', state.view);
    FACETS.forEach(function (f) { state.sel[f.key].forEach(function (v) { p.append(f.key, v); }); });
    var h = p.toString();
    history.replaceState(null, '', h ? '#' + h : location.pathname + location.search);
  }

  // ---------- filtering ----------
  function matches(a, skipKey) {
    if (state.q) {
      var hay = (a._hay || (a._hay = (a.artists.join(' ') + ' ' + a.title + ' ' + a.labels.join(' ') + ' ' +
        a.genres.join(' ') + ' ' + a.styles.join(' ') + ' ' + (a.gt || '')).toLowerCase()));
      var terms = state.q.toLowerCase().split(/\s+/).filter(Boolean);
      for (var i = 0; i < terms.length; i++) if (hay.indexOf(terms[i]) < 0) return false;
    }
    if (state.ymin && (!a.year || a.year < +state.ymin)) return false;
    if (state.ymax && (!a.year || a.year > +state.ymax)) return false;
    if (state.amin && a.added < state.amin) return false;
    if (state.amax && a.added > state.amax) return false;
    for (var j = 0; j < FACETS.length; j++) {
      var f = FACETS[j], sel = state.sel[f.key];
      if (f.key === skipKey || !sel.length) continue;
      var vals = f.get(a);
      if (!sel.some(function (s) { return vals.indexOf(s) >= 0; })) return false;
    }
    return true;
  }

  var SORTERS = {
    uploaded: function (a) { return a.uploaded; }, added: function (a) { return a.added; },
    year: function (a) { return a.year || 0; },
    artist: function (a) { return (a.artists[0] || '').toLowerCase().replace(/^the /, ''); },
    title: function (a) { return a.title.toLowerCase(); },
    formats: function (a) { return a.formats.join(',').toLowerCase(); },
    labels: function (a) { return a.labels.join(',').toLowerCase(); },
    genres: function (a) { return a.genres.join(',').toLowerCase(); },
    styles: function (a) { return a.styles.join(',').toLowerCase(); },
    state: function (a) { return a.state || '￿'; }, country: function (a) { return a.country || '￿'; }
  };
  function sortResults(list) {
    var parts = state.sort.split(':'), fn = SORTERS[parts[0]] || SORTERS.uploaded, dir = parts[1] === 'asc' ? 1 : -1;
    // year / date-added sorts: albums without a value always go last
    return list.slice().sort(function (a, b) {
      var x = fn(a), y = fn(b);
      if (parts[0] === 'year' || parts[0] === 'added') { if (!x && y) return 1; if (x && !y) return -1; }
      return (x < y ? -1 : x > y ? 1 : 0) * dir || (a.title < b.title ? -1 : 1);
    });
  }

  // ---------- facets UI ----------
  function buildFacetShell() {
    var host = $('facets');
    host.innerHTML = '';
    FACETS.forEach(function (f) {
      var d = document.createElement('details');
      d.className = 'facet'; d.dataset.key = f.key;
      d.open = !!facetOpen[f.key];
      d.innerHTML = '<summary>' + esc(f.label) + ' <span class="badge" hidden></span></summary><div class="facet-inner">' +
        (f.search ? '<input type="search" class="facet-search" placeholder="find ' + esc(f.label.toLowerCase()) + '…" aria-label="Search ' + esc(f.label) + '">' : '') +
        '<div class="facet-body"></div></div>';
      d.addEventListener('toggle', function () { facetOpen[f.key] = d.open; });
      var s = d.querySelector('.facet-search');
      if (s) s.addEventListener('input', function () { facetSearch[f.key] = s.value; renderFacet(f); });
      host.appendChild(d);
    });
    host.addEventListener('change', function (e) {
      var cb = e.target; if (!cb.matches('input[type=checkbox][data-f]')) return;
      var arr = state.sel[cb.dataset.f], v = cb.value, i = arr.indexOf(v);
      if (cb.checked && i < 0) arr.push(v); else if (!cb.checked && i >= 0) arr.splice(i, 1);
      state.shown = PAGE; update();
    });
  }
  function renderFacet(f) {
    var counts = {}, others = albums.filter(function (a) { return matches(a, f.key); });
    others.forEach(function (a) { f.get(a).forEach(function (v) { counts[v] = (counts[v] || 0) + 1; }); });
    var sel = state.sel[f.key];
    sel.forEach(function (v) { if (!(v in counts)) counts[v] = 0; });
    var names = Object.keys(counts), q = (facetSearch[f.key] || '').toLowerCase();
    if (q) names = names.filter(function (n) { return n.toLowerCase().indexOf(q) >= 0 || sel.indexOf(n) >= 0; });
    names.sort(function (a, b) {
      var sa = sel.indexOf(a) >= 0, sb = sel.indexOf(b) >= 0;
      if (sa !== sb) return sa ? -1 : 1;
      if ((a === NA) !== (b === NA)) return a === NA ? 1 : -1;   // N/A always last, whatever its count
      return counts[b] - counts[a] || (a < b ? -1 : 1);
    });
    var cap = q ? 200 : 80, more = names.length - cap;
    var box = document.querySelector('details[data-key="' + f.key + '"]');
    box.querySelector('.facet-body').innerHTML = names.slice(0, cap).map(function (n) {
      return '<label class="opt' + (n === NA ? ' na' : '') + '"><input type="checkbox" data-f="' + f.key + '" value="' + esc(n) + '"' +
        (sel.indexOf(n) >= 0 ? ' checked' : '') + '><span>' + esc(n) + '</span><em>' + counts[n] + '</em></label>';
    }).join('') + (more > 0 ? '<p class="muted">+' + more + ' more — use the search box</p>' : '') +
      (!names.length ? '<p class="muted">nothing here yet</p>' : '');
    var b = box.querySelector('summary .badge');
    b.hidden = !sel.length; b.textContent = sel.length;
  }

  // ---------- results UI ----------
  function cardHtml(a) {
    var yt = ytUrl(a.videos[0]);
    var place = a.state || (a.country !== NA ? a.country : '');
    var sub = [a.year, place].filter(Boolean).join(' · ');
    var artist = a.artists.join(', ');
    var fmts = a.formats.filter(function (f) { return f !== NA; });
    var links = '<a href="' + yt + '">YouTube</a> · ' + (a.discogs
      ? '<a href="' + esc(a.discogs) + '">Discogs ↗</a>'
      : '<span class="tag nd" title="No Discogs page: details come from the YouTube description">No Discogs page</span>');
    return '<article class="card"><a class="art" href="' + yt + '" tabindex="-1" aria-hidden="true">' +
      '<img loading="lazy" decoding="async" alt="" src="' + esc(a.cover) + '" data-fb="https://i.ytimg.com/vi/' + a.videos[0] + '/hqdefault.jpg">' +
      '<span class="fmt">' + fmts.map(function (f) { return '<span class="tag">' + esc(f) + '</span>'; }).join('') + '</span></a>' +
      '<div class="meta">' + (artist !== a.title ? '<div class="a">' + esc(artist) + '</div>' : '') +
      '<div class="t"><a class="title-link" href="' + yt + '">' + esc(a.title) + '</a></div>' +
      '<div class="s">' + esc(sub) + '</div><div class="links">' + links + '</div></div></article>';
  }
  var CELL = {
    cover: function (a) { return '<td class="cover"><img loading="lazy" alt="" src="' + esc(a.cover) + '" data-fb="https://i.ytimg.com/vi/' + a.videos[0] + '/default.jpg"></td>'; },
    artist: function (a) { return '<td>' + esc(a.artists.join(', ')) + '</td>'; },
    title: function (a) { return '<td><a href="' + ytUrl(a.videos[0]) + '">' + esc(a.title) + '</a></td>'; },
    year: function (a) { return '<td>' + (a.year || '') + '</td>'; },
    formats: function (a) { return '<td>' + esc(a.formats.join(', ')) + '</td>'; },
    labels: function (a) { return '<td>' + esc(a.labels.join(', ')) + '</td>'; },
    genres: function (a) { return '<td>' + esc(a.genres.join(', ')) + '</td>'; },
    styles: function (a) { return '<td>' + esc(a.styles.join(', ')) + '</td>'; },
    state: function (a) { return '<td>' + esc(a.state) + '</td>'; },
    country: function (a) { return '<td>' + esc(a.country) + '</td>'; },
    added: function (a) { return '<td>' + (a.added || '—') + '</td>'; },
    uploaded: function (a) { return '<td>' + a.uploaded + '</td>'; },
    links: function (a) {
      return '<td><a href="' + ytUrl(a.videos[0]) + '">YouTube</a> · ' +
        (a.discogs ? '<a href="' + esc(a.discogs) + '">Discogs</a>' : '<span class="muted">no Discogs page</span>') + '</td>';
    }
  };
  function listHtml(rows) {
    var cols = COLUMNS.filter(function (c) { return state.cols.indexOf(c.id) >= 0; });
    var cur = state.sort.split(':');
    var head = cols.map(function (c) {
      if (!c.sort) return '<th scope="col">' + esc(c.label) + '</th>';
      var on = cur[0] === c.sort, arrow = on ? (cur[1] === 'asc' ? ' ▲' : ' ▼') : '';
      return '<th scope="col" aria-sort="' + (on ? (cur[1] === 'asc' ? 'ascending' : 'descending') : 'none') + '"><button data-sort="' + c.sort + '">' + esc(c.label) + arrow + '</button></th>';
    }).join('');
    var body = rows.map(function (a) { return '<tr>' + cols.map(function (c) { return CELL[c.id](a); }).join('') + '</tr>'; }).join('');
    return '<div class="table-wrap"><table class="data"><thead><tr>' + head + '</tr></thead><tbody>' + body + '</tbody></table></div>';
  }

  function update() {
    var results = sortResults(albums.filter(function (a) { return matches(a); }));
    var rows = results.slice(0, state.shown);
    $('result-count').textContent = results.length + ' of ' + albums.length + ' albums';
    $('out').innerHTML = !results.length ? '<p class="empty">No albums match these filters. Try clearing some.</p>' :
      state.view === 'list' ? listHtml(rows) : '<div class="grid">' + rows.map(cardHtml).join('') + '</div>';
    $('more').hidden = results.length <= state.shown;
    $('more').textContent = 'Show more (' + (results.length - state.shown) + ' left)';
    $('view-grid').setAttribute('aria-pressed', state.view === 'grid');
    $('view-list').setAttribute('aria-pressed', state.view === 'list');
    $('cols-menu').hidden = state.view !== 'list';
    $('sort').value = state.sort;
    var active = state.q || state.ymin || state.ymax || state.amin || state.amax ||
      FACETS.some(function (f) { return state.sel[f.key].length; });
    var n = FACETS.reduce(function (t, f) { return t + state.sel[f.key].length; }, 0) +
      [state.q, state.ymin || state.ymax, state.amin || state.amax].filter(Boolean).length;
    $('filter-badge').hidden = !active; $('filter-badge').textContent = n;
    FACETS.forEach(renderFacet);
    writeHash();
  }

  // ---------- wiring ----------
  function buildColsMenu() {
    $('cols-pop').innerHTML = COLUMNS.map(function (c) {
      return '<label class="opt"><input type="checkbox" value="' + c.id + '"' + (state.cols.indexOf(c.id) >= 0 ? ' checked' : '') + '><span>' + esc(c.label) + '</span></label>';
    }).join('');
    $('cols-pop').addEventListener('change', function () {
      state.cols = Array.prototype.map.call($('cols-pop').querySelectorAll('input:checked'), function (i) { return i.value; });
      if (!state.cols.length) state.cols = ['title'];
      store('br-cols', JSON.stringify(state.cols)); update();
    });
  }
  function bindInputs() {
    var t; $('q').addEventListener('input', function () { clearTimeout(t); t = setTimeout(function () { state.q = $('q').value.trim(); state.shown = PAGE; update(); }, 150); });
    [['year-min', 'ymin'], ['year-max', 'ymax'], ['added-min', 'amin'], ['added-max', 'amax']].forEach(function (p) {
      $(p[0]).addEventListener('change', function () { state[p[1]] = $(p[0]).value; state.shown = PAGE; update(); });
    });
    $('sort').addEventListener('change', function () { state.sort = $('sort').value; update(); });
    $('view-grid').addEventListener('click', function () { state.view = 'grid'; store('br-view', 'grid'); update(); });
    $('view-list').addEventListener('click', function () { state.view = 'list'; store('br-view', 'list'); update(); });
    $('more').addEventListener('click', function () { state.shown += PAGE; update(); });
    $('clear-filters').addEventListener('click', function () {
      state.q = state.ymin = state.ymax = state.amin = state.amax = '';
      FACETS.forEach(function (f) { state.sel[f.key] = []; facetSearch[f.key] = ''; });
      syncInputs(); document.querySelectorAll('.facet-search').forEach(function (i) { i.value = ''; });
      state.shown = PAGE; update();
    });
    $('out').addEventListener('click', function (e) {
      var b = e.target.closest('button[data-sort]'); if (!b) return;
      var cur = state.sort.split(':'), k = b.dataset.sort;
      state.sort = k + ':' + (cur[0] === k && cur[1] === 'asc' ? 'desc' : 'asc'); update();
    });
    // image fallback: Discogs cover -> YouTube thumbnail (capture because error doesn't bubble)
    document.addEventListener('error', function (e) {
      var i = e.target; if (i.tagName === 'IMG' && i.dataset.fb && i.src !== i.dataset.fb) i.src = i.dataset.fb;
    }, true);
    // mobile drawer
    function drawer(open) {
      $('filters').classList.toggle('open', open); $('scrim').hidden = !open;
      $('filters-toggle').setAttribute('aria-expanded', open);
    }
    $('filters-toggle').addEventListener('click', function () { drawer(true); });
    $('filters-close').addEventListener('click', function () { drawer(false); });
    $('scrim').addEventListener('click', function () { drawer(false); });
    document.addEventListener('keydown', function (e) { if (e.key === 'Escape') drawer(false); });
    window.addEventListener('hashchange', function () { readHash(); syncInputs(); update(); });
  }
  function syncInputs() {
    $('q').value = state.q; $('year-min').value = state.ymin; $('year-max').value = state.ymax;
    $('added-min').value = state.amin; $('added-max').value = state.amax;
  }

  fetch(JSON_URL).then(function (r) { if (!r.ok) throw new Error(r.status); return r.json(); }).then(function (d) {
    data = d; albums = d.albums;
    readHash(); buildFacetShell(); buildColsMenu(); bindInputs(); syncInputs(); update();
  }).catch(function (err) {
    $('facets').innerHTML = '';
    $('out').innerHTML = '<p class="empty">Couldn\'t load the album list (' + esc(err.message) + '). Try reloading.</p>';
    $('result-count').textContent = '';
  });
})();
