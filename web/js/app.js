/* Cuyahoga County neighborhood indicators viewer.
   Plain JavaScript, no dependencies, no build step. All URLs are relative so the page
   works from any sub-path of a static host. */
(function () {
  'use strict';

  var PALETTES = {
    worse:   ['#ffffd4', '#fed98e', '#fe9929', '#d95f0e', '#993404'],
    better:  ['#eff3ff', '#bdd7e7', '#6baed6', '#3182bd', '#08519c'],
    neutral: ['#f2f0f7', '#cbc9e2', '#9e9ac8', '#756bb1', '#54278f']
  };
  var DIRECTION_TEXT = {
    worse: 'Darker colours mean a higher value, which is generally worse.',
    better: 'Darker colours mean a higher value, which is generally better.',
    neutral: 'Darker colours mean a higher value. Higher is not good or bad in itself.'
  };
  var REL_LABEL = {
    high: 'High', medium: 'Medium', low: 'Low',
    zero_estimate: 'Zero estimate', no_moe: 'No MOE', unavailable: 'Unavailable'
  };
  var REL_RANK = { high: 0, medium: 1, low: 2, zero_estimate: 3, no_moe: 4, unavailable: 5 };
  var SVG_NS = 'http://www.w3.org/2000/svg';
  var MAP_W = 800;

  var $ = function (id) { return document.getElementById(id); };
  var el = {
    indicator: $('indicator'), vintage: $('vintage'), reliability: $('reliability'), search: $('search'),
    download: $('download'), banner: $('geo-banner'), def: $('indicator-def'), timings: $('timings'),
    apiLine: $('api-line'), useApi: $('use-api'), apiTiming: $('api-timing'), error: $('error'),
    map: $('map'), mapWrap: $('map-wrap'), tooltip: $('tooltip'), legend: $('legend'), detail: $('detail'),
    count: $('count'), tbl: $('tbl'), tbody: $('tbl').tBodies[0], scroll: $('table-scroll')
  };

  var S = {
    meta: null, indicators: [], byId: {}, data: null, county: null, names: null,
    geo: {},            // tract vintage -> {viewBox, tracts:[{g,name,d}], byGeoid}
    paths: {},          // geoid -> svg path element for the current geography
    indicator: null, vintage: null,
    sort: { key: 'value', dir: 'desc' },
    selected: null, rows: [], breaks: [], palette: [], trMap: new Map(),
    live: null,         // values fetched from the API for the current selection
    loadLog: [],
    t: { load: null, select: null, sort: null, filter: null }
  };

  /* ---------- helpers ---------- */
  function esc(s) {
    return String(s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }
  function ms(x) { return x.toFixed(1) + ' ms'; }
  function kb(n) { return (n / 1024).toFixed(0) + ' KB'; }

  function fmt(ind, v) {
    if (v === null || v === undefined) return 'n/a';
    switch (ind.unit) {
      case 'percent': return v.toFixed(1) + '%';
      case 'dollars': return '$' + Math.round(v).toLocaleString('en-US');
      case 'years': return v.toFixed(1) + ' yrs';
      default: return Math.round(v).toLocaleString('en-US');
    }
  }
  function fmtMoe(ind, v) {
    if (v === null || v === undefined) return 'n/a';
    switch (ind.unit) {
      case 'percent': return '±' + v.toFixed(1) + ' pts';
      case 'dollars': return '±$' + Math.round(v).toLocaleString('en-US');
      case 'years': return '±' + v.toFixed(1) + ' yrs';
      default: return '±' + Math.round(v).toLocaleString('en-US');
    }
  }
  function fmtPlain(ind, v) {
    if (v === null) return 'n/a';
    return ind.unit === 'dollars' ? Math.round(v).toLocaleString('en-US') : String(v);
  }

  function getJSON(url) {
    var t0 = performance.now();
    return fetch(url).then(function (r) {
      if (!r.ok) throw new Error(url + ' returned HTTP ' + r.status);
      return r.text();
    }).then(function (txt) {
      var obj = JSON.parse(txt);
      S.loadLog.push({ url: url, bytes: txt.length, ms: performance.now() - t0 });
      return obj;
    });
  }

  function showError(msg) {
    el.error.textContent = msg;
    el.error.hidden = false;
  }

  /* ---------- geometry ---------- */
  function buildGeo(fc) {
    var minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity, sumLat = 0, n = 0;
    function walk(c, f) {
      if (typeof c[0] === 'number') { f(c); return; }
      for (var i = 0; i < c.length; i++) walk(c[i], f);
    }
    fc.features.forEach(function (ft) {
      walk(ft.geometry.coordinates, function (p) {
        if (p[0] < minX) minX = p[0]; if (p[0] > maxX) maxX = p[0];
        if (p[1] < minY) minY = p[1]; if (p[1] > maxY) maxY = p[1];
        sumLat += p[1]; n++;
      });
    });
    var k = Math.cos((sumLat / n) * Math.PI / 180);   // equirectangular, longitude scaled by cos(latitude)
    var scale = MAP_W / ((maxX - minX) * k);
    var H = Math.ceil((maxY - minY) * scale);
    function pt(p) { return ((p[0] - minX) * k * scale).toFixed(1) + ' ' + ((maxY - p[1]) * scale).toFixed(1); }
    var tracts = fc.features.map(function (ft) {
      var g = ft.geometry, polys = g.type === 'Polygon' ? [g.coordinates] : g.coordinates, d = '';
      polys.forEach(function (poly) {
        poly.forEach(function (ring) {
          d += 'M' + ring.map(pt).join('L') + 'Z';
        });
      });
      return { g: ft.properties.GEOID, name: ft.properties.NAMELSAD, d: d };
    });
    var byGeoid = {};
    tracts.forEach(function (t) { byGeoid[t.g] = t; });
    return { viewBox: '0 0 ' + MAP_W + ' ' + H, tracts: tracts, byGeoid: byGeoid };
  }

  function ensureGeo(vint) {
    var tv = vint.tract_vintage;
    if (S.geo[tv]) return Promise.resolve(S.geo[tv]);
    return getJSON(vint.tract_file).then(function (fc) {
      S.geo[tv] = buildGeo(fc);
      return S.geo[tv];
    });
  }

  function svgEl(name, attrs) {
    var e = document.createElementNS(SVG_NS, name);
    for (var k in attrs) e.setAttribute(k, attrs[k]);
    return e;
  }

  var layers = {};
  function buildMap(geo) {
    var svg = el.map;
    while (svg.firstChild) svg.removeChild(svg.firstChild);
    svg.setAttribute('viewBox', geo.viewBox);
    var defs = svgEl('defs', {});
    var hatch = svgEl('pattern', { id: 'hatch', width: 5, height: 5, patternUnits: 'userSpaceOnUse', patternTransform: 'rotate(45)' });
    hatch.appendChild(svgEl('line', { x1: 0, y1: 0, x2: 0, y2: 5, stroke: '#17222d', 'stroke-width': 1.1 }));
    var dots = svgEl('pattern', { id: 'dots', width: 5, height: 5, patternUnits: 'userSpaceOnUse' });
    dots.appendChild(svgEl('rect', { width: 5, height: 5, fill: '#ffffff' }));
    dots.appendChild(svgEl('circle', { cx: 2.5, cy: 2.5, r: 0.9, fill: '#6c7a89' }));
    defs.appendChild(hatch); defs.appendChild(dots);
    svg.appendChild(defs);
    var g = svgEl('g', {});
    S.paths = {};
    var frag = document.createDocumentFragment();
    geo.tracts.forEach(function (t) {
      var p = svgEl('path', { d: t.d, 'class': 'tract', 'data-g': t.g, 'fill-rule': 'evenodd' });
      S.paths[t.g] = p;
      frag.appendChild(p);
    });
    g.appendChild(frag);
    svg.appendChild(g);
    layers.low = svgEl('path', { 'class': 'lowrel', 'fill-rule': 'evenodd' });
    layers.hover = svgEl('path', { 'class': 'overlay hover', 'fill-rule': 'evenodd' });
    layers.sel1 = svgEl('path', { 'class': 'overlay sel', 'fill-rule': 'evenodd' });
    layers.sel2 = svgEl('path', { 'class': 'overlay sel2', 'fill-rule': 'evenodd' });
    svg.appendChild(layers.low); svg.appendChild(layers.hover);
    svg.appendChild(layers.sel1); svg.appendChild(layers.sel2);
  }

  /* ---------- data access ---------- */
  function valuesFor(indId, vintId) {
    if (S.live && S.live.key === indId + '|' + vintId) return S.live.values;
    return (S.data[vintId] || {})[indId] || {};
  }

  function currentVint() {
    return S.meta.vintages.filter(function (v) { return v.id === S.vintage; })[0];
  }

  function buildRows() {
    var vint = currentVint(), names = S.names[String(vint.tract_vintage)];
    var vals = valuesFor(S.indicator, S.vintage);
    S.rows = Object.keys(names).map(function (g) {
      var r = vals[g] || [null, null, 'unavailable'];
      return { g: g, name: names[g], value: r[0], moe: r[1], rel: r[2] || 'unavailable', hasShape: !!S.geo[vint.tract_vintage].byGeoid[g] };
    });
  }

  /* ---------- classification ---------- */
  function quantileBreaks(values, k) {
    var s = values.slice().sort(function (a, b) { return a - b; });
    var n = s.length;
    if (!n) return [];
    var br = [];
    for (var i = 1; i < k; i++) {
      var pos = (i / k) * (n - 1), lo = Math.floor(pos), f = pos - lo;
      br.push(s[lo] + (s[Math.min(lo + 1, n - 1)] - s[lo]) * f);
    }
    var uniq = [];
    br.forEach(function (b) { if (!uniq.length || b > uniq[uniq.length - 1]) uniq.push(b); });
    return { breaks: uniq, min: s[0], max: s[n - 1] };
  }

  function classOf(v) {
    var b = S.breaks, i = 0;
    while (i < b.length && v > b[i]) i++;
    return i;
  }

  function classify() {
    var ind = S.byId[S.indicator];
    var vals = S.rows.filter(function (r) { return r.value !== null; }).map(function (r) { return r.value; });
    var q = quantileBreaks(vals, 5);
    S.breaks = q.breaks || [];
    S.qmin = q.min; S.qmax = q.max;
    var n = S.breaks.length + 1, base = PALETTES[ind.higher_is] || PALETTES.neutral;
    S.palette = [];
    for (var i = 0; i < n; i++) S.palette.push(n === 1 ? base[2] : base[Math.round(i * (base.length - 1) / (n - 1))]);
  }

  /* ---------- view filter / search ---------- */
  function matches(r) {
    var f = el.reliability.value;
    if (f === 'hm' && !(r.rel === 'high' || r.rel === 'medium')) return false;
    if (f === 'low' && r.rel !== 'low') return false;
    if (f === 'avail' && r.value === null) return false;
    var q = el.search.value.trim().toLowerCase();
    if (q && r.g.indexOf(q) === -1 && r.name.toLowerCase().indexOf(q) === -1) return false;
    return true;
  }

  function viewRows() {
    var key = S.sort.key, dir = S.sort.dir === 'asc' ? 1 : -1;
    var rows = S.rows.filter(matches);
    rows.sort(function (a, b) {
      var x, y;
      if (key === 'name') return dir * a.name.localeCompare(b.name, 'en', { numeric: true });
      if (key === 'geoid') return dir * (a.g < b.g ? -1 : a.g > b.g ? 1 : 0);
      if (key === 'rel') {
        var d = REL_RANK[a.rel] - REL_RANK[b.rel];
        if (d) return dir * d;
        x = a.value; y = b.value;
      } else {
        x = a[key]; y = b[key];
      }
      if (x === null && y === null) return a.g < b.g ? -1 : 1;
      if (x === null) return 1;      // missing values always last
      if (y === null) return -1;
      return x === y ? (a.g < b.g ? -1 : 1) : dir * (x - y);
    });
    return rows;
  }

  /* ---------- rendering ---------- */
  function paintMap() {
    var lowD = '';
    S.rows.forEach(function (r) {
      var p = S.paths[r.g];
      if (!p) return;
      var fill;
      if (r.value === null) fill = 'url(#dots)';
      else fill = S.palette[classOf(r.value)];
      p.setAttribute('fill', fill);
      p.setAttribute('class', matches(r) ? 'tract' : 'tract dim');
      if (r.rel === 'low' && matches(r)) lowD += S.geo[currentVint().tract_vintage].byGeoid[r.g].d;
    });
    layers.low.setAttribute('d', lowD);
  }

  function dimOnly() {
    S.rows.forEach(function (r) {
      var p = S.paths[r.g];
      if (p) p.setAttribute('class', matches(r) ? 'tract' : 'tract dim');
    });
    var lowD = '', geo = S.geo[currentVint().tract_vintage];
    S.rows.forEach(function (r) { if (r.rel === 'low' && S.paths[r.g] && matches(r)) lowD += geo.byGeoid[r.g].d; });
    layers.low.setAttribute('d', lowD);
  }

  function renderLegend() {
    var ind = S.byId[S.indicator], b = S.breaks, n = b.length + 1, items = '';
    var counts = new Array(n).fill(0), unavailable = 0, low = 0;
    S.rows.forEach(function (r) {
      if (r.value === null) unavailable++; else counts[classOf(r.value)]++;
      if (r.rel === 'low') low++;
    });
    for (var i = 0; i < n; i++) {
      var lo = i === 0 ? S.qmin : b[i - 1], hi = i === n - 1 ? S.qmax : b[i];
      var label = n === 1 ? fmt(ind, S.qmin) : (i === 0 ? fmt(ind, lo) + ' to ' + fmt(ind, hi) : 'above ' + fmt(ind, lo) + ' to ' + fmt(ind, hi));
      items += '<li><span class="sw" style="background:' + S.palette[i] + '"></span><span>' + esc(label) +
        ' <span class="n">(' + counts[i] + ' tracts)</span></span></li>';
    }
    items += '<li><span class="sw na"></span><span>No estimate <span class="n">(' + unavailable + ' tracts)</span></span></li>';
    items += '<li><span class="sw low"></span><span>Hatched: low reliability <span class="n">(' + low + ' tracts)</span></span></li>';
    el.legend.innerHTML = '<p class="dir"><strong>Quantile classes (up to 5, equal numbers of tracts).</strong> ' +
      esc(DIRECTION_TEXT[ind.higher_is] || DIRECTION_TEXT.neutral) + '</p><ul>' + items + '</ul>';
  }

  function shortName(n) { return n.replace(/^Census Tract /, 'Tract '); }

  function badge(rel) {
    var mark = rel === 'low' ? '! ' : '';
    return '<span class="badge ' + rel + '">' + mark + esc(REL_LABEL[rel] || rel) + '</span>';
  }

  function renderTable() {
    var ind = S.byId[S.indicator], rows = viewRows(), html = '';
    S.view = rows;
    rows.forEach(function (r) {
      html += '<tr tabindex="0" data-g="' + r.g + '"' + (r.g === S.selected ? ' aria-selected="true"' : '') + '>' +
        '<td class="nm">' + esc(shortName(r.name)) + '</td><td class="geoid">' + r.g + '</td>' +
        '<td class="num">' + esc(fmt(ind, r.value)) + '</td><td class="num">' + esc(fmtMoe(ind, r.moe)) + '</td>' +
        '<td>' + badge(r.rel) + '</td></tr>';
    });
    if (!rows.length) html = '<tr><td class="empty" colspan="5">No tracts match the current filter.</td></tr>';
    el.tbody.innerHTML = html;
    S.trMap = new Map();
    for (var i = 0; i < el.tbody.rows.length; i++) {
      var tr = el.tbody.rows[i];
      if (tr.dataset.g) S.trMap.set(tr.dataset.g, tr);
    }
    el.count.textContent = 'Showing ' + rows.length + ' of ' + S.rows.length + ' tracts';
    var ths = el.tbl.tHead.rows[0].cells;
    for (var j = 0; j < ths.length; j++) {
      var k = ths[j].firstElementChild.dataset.key;
      ths[j].setAttribute('aria-sort', k === S.sort.key ? (S.sort.dir === 'asc' ? 'ascending' : 'descending') : 'none');
    }
  }

  function renderDetail() {
    var ind = S.byId[S.indicator], r = S.rows.filter(function (x) { return x.g === S.selected; })[0];
    var c = (S.county[S.vintage] || {})[S.indicator];
    var cty = c ? 'Cuyahoga County overall: ' + fmt(ind, c[0]) + ' (' + fmtMoe(ind, c[1]) + ').' : '';
    if (!r) {
      el.detail.innerHTML = '<span>Select a tract on the map or in the table. ' + esc(cty) + '</span>';
      return;
    }
    el.detail.innerHTML = '<strong>' + esc(r.name) + '</strong> (' + r.g + '): ' + esc(fmt(ind, r.value)) + ', ' +
      esc(fmtMoe(ind, r.moe)) + ' ' + badge(r.rel) + '<br><span>' + esc(cty) + '</span>';
  }

  function setOverlay(layer, g) {
    var t = g && S.geo[currentVint().tract_vintage].byGeoid[g];
    layer.setAttribute('d', t ? t.d : '');
  }

  function select(g, scrollRow) {
    S.selected = g;
    setOverlay(layers.sel1, g); setOverlay(layers.sel2, g);
    S.trMap.forEach(function (tr, k) {
      if (k === g) tr.setAttribute('aria-selected', 'true'); else tr.removeAttribute('aria-selected');
    });
    if (scrollRow && g && S.trMap.get(g)) S.trMap.get(g).scrollIntoView({ block: 'nearest' });
    renderDetail();
  }

  function renderBanner() {
    var vint = currentVint();
    el.banner.textContent = 'ACS ' + vint.id + ' uses ' + vint.tract_vintage + ' census tract boundaries (' +
      vint.n_tracts + ' tracts in the county). Switching period switches the tract map and tract IDs.';
  }

  function renderTimings() {
    var t = S.t, parts = [];
    var load = S.loadLog.map(function (l) { return l.url.split('/').pop() + ' ' + kb(l.bytes) + ' in ' + ms(l.ms); }).join('; ');
    var total = S.loadLog.reduce(function (a, l) { return a + l.ms; }, 0);
    parts.push('<b>Data load:</b> ' + ms(total) + ' (' + esc(load) + ')');
    parts.push('<b>Indicator or period change</b> (re-rank, recolour, redraw table): ' + (t.select === null ? 'not yet measured' : ms(t.select)));
    parts.push('<b>Last sort:</b> ' + (t.sort === null ? 'not yet measured' : ms(t.sort)));
    parts.push('<b>Last filter or search:</b> ' + (t.filter === null ? 'not yet measured' : ms(t.filter)));
    el.timings.innerHTML = parts.join(' | ');
    window.viewerTimings = { loadMs: total, selectMs: t.select, sortMs: t.sort, filterMs: t.filter, loadLog: S.loadLog };
  }

  /* ---------- main update paths ---------- */
  function fullUpdate() {
    var t0 = performance.now();
    var ind = S.byId[S.indicator];
    buildRows();
    classify();
    paintMap();
    renderLegend();
    renderTable();
    if (S.selected && !S.rows.some(function (r) { return r.g === S.selected; })) S.selected = null;
    setOverlay(layers.sel1, S.selected); setOverlay(layers.sel2, S.selected);
    renderDetail();
    el.def.textContent = ind.name + ': ' + ind.definition;
    el.map.setAttribute('aria-label', ind.name + ', ' + S.vintage + ', by census tract');
    S.t.select = performance.now() - t0 + (S.mapBuildMs || 0);   // includes redrawing the map when the tract geography changed
    S.mapBuildMs = 0;
    renderTimings();
  }

  function viewUpdate() {
    var t0 = performance.now();
    dimOnly();
    renderTable();
    S.t.filter = performance.now() - t0;
    renderTimings();
  }

  function sortBy(key) {
    var t0 = performance.now();
    if (S.sort.key === key) S.sort.dir = S.sort.dir === 'asc' ? 'desc' : 'asc';
    else { S.sort.key = key; S.sort.dir = (key === 'name' || key === 'geoid' || key === 'rel') ? 'asc' : 'desc'; }
    renderTable();
    S.t.sort = performance.now() - t0;
    renderTimings();
  }

  function writeHash() {
    try {
      history.replaceState(null, '', location.pathname + location.search + '#ind=' + encodeURIComponent(S.indicator) + '&v=' + encodeURIComponent(S.vintage));
    } catch (e) { /* not essential */ }
  }

  function changeSelection(opts) {
    opts = opts || {};
    var vint = currentVint();
    return ensureGeo(vint).then(function (geo) {
      var needMap = el.map.dataset.tv !== String(vint.tract_vintage);
      if (needMap) {
        var tb = performance.now();
        buildMap(geo);
        S.mapBuildMs = performance.now() - tb;
        el.map.dataset.tv = String(vint.tract_vintage);
        S.selected = opts.keepSelection ? S.selected : null;
      }
      return fetchLive();
    }).then(function () {
      renderBanner();
      fullUpdate();
      writeHash();
    }).catch(function (e) { showError('Could not update the view: ' + e.message); });
  }

  /* ---------- optional live API ---------- */
  function detectApi() {
    // The API is only probed when the page is opened with ?api=1 (the FastAPI app redirects there),
    // so static hosts never issue a failing request.
    if (location.protocol === 'file:' || !/[?&]api=1(&|$)/.test(location.search)) return;
    var ctl = typeof AbortController === 'function' ? new AbortController() : null;
    var timer = setTimeout(function () { if (ctl) ctl.abort(); }, 1500);
    fetch('api/health', ctl ? { signal: ctl.signal } : {}).then(function (r) {
      clearTimeout(timer);
      if (!r.ok) return null;
      return r.json();
    }).then(function (j) {
      if (j && j.status === 'ok') { S.apiOk = true; el.apiLine.hidden = false; }
    }).catch(function () { /* static hosting: no API, which is expected */ });
  }

  function fetchLive() {
    S.live = null;
    if (!S.apiOk || !el.useApi.checked) { el.apiTiming.textContent = ''; return Promise.resolve(); }
    var t0 = performance.now(), key = S.indicator + '|' + S.vintage;
    return fetch('api/values?indicator=' + encodeURIComponent(S.indicator) + '&vintage=' + encodeURIComponent(S.vintage))
      .then(function (r) { if (!r.ok) throw new Error('API returned HTTP ' + r.status); return r.json(); })
      .then(function (j) {
        S.live = { key: key, values: j.values };
        el.apiTiming.textContent = 'API round trip ' + ms(performance.now() - t0) + ', server query ' + j.query_ms.toFixed(2) + ' ms';
      })
      .catch(function (e) { el.apiTiming.textContent = 'API unavailable, using static data (' + e.message + ')'; });
  }

  /* ---------- static text from metadata ---------- */
  function renderNotes() {
    var m = S.meta, v10 = m.vintages[0], v20 = m.vintages[m.vintages.length - 1];
    $('rel-rules').textContent = m.reliability_classes.filter(function (c) { return /^(high|medium|low)$/.test(c.id); })
      .map(function (c) { return c.label + ' is ' + c.rule; }).join('; ') + '. ' +
      'Margins are at the ' + m.moe_level_percent + ' percent confidence level.';
    $('boundary-note').textContent = 'The ' + v10.id + ' estimates use the ' + v10.tract_vintage + ' census tract boundaries (' + v10.n_tracts +
      ' tracts), and the ' + v20.id + ' estimates use the ' + v20.tract_vintage + ' boundaries (' + v20.n_tracts +
      ' tracts). Tracts were split, merged and renumbered, so a tract ID in one period is not always the same area in the other. ' +
      'Only ' + m.stable_tracts + ' tracts have essentially unchanged boundaries (land overlap of at least 99 percent in both directions); comparisons over time should be limited to those tracts or made at the county level. ' +
      m.dollars_note;
    $('source-note').textContent = m.source;
    $('tables-note').textContent = 'ACS tables used: ' + m.acs_tables.join(', ') + '. Data generated ' + m.generated + '.';
    var dl = $('dictionary'), h = '';
    S.dictionary.forEach(function (d) { h += '<dt>' + esc(d.field) + '</dt><dd>' + esc(d.description) + '</dd>'; });
    dl.innerHTML = h;
    $('footer-line').textContent = 'Source: U.S. Census Bureau, American Community Survey 5-year estimates. Estimates are subject to sampling error; see the margins of error.';
  }

  function fillSelects() {
    var themes = {}, order = [];
    S.indicators.forEach(function (i) { if (!themes[i.theme]) { themes[i.theme] = []; order.push(i.theme); } themes[i.theme].push(i); });
    el.indicator.innerHTML = order.map(function (t) {
      return '<optgroup label="' + esc(t) + '">' + themes[t].map(function (i) {
        return '<option value="' + i.id + '">' + esc(i.name) + '</option>';
      }).join('') + '</optgroup>';
    }).join('');
    el.vintage.innerHTML = S.meta.vintages.map(function (v) {
      return '<option value="' + v.id + '">' + v.id + ' (' + v.tract_vintage + ' tracts)</option>';
    }).join('');
    el.indicator.value = S.indicator;
    el.vintage.value = S.vintage;
  }

  /* ---------- CSV ---------- */
  function csvCell(s) {
    s = String(s);
    return /[",\r\n]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s;
  }
  function downloadCsv() {
    var lines = ['geoid,indicator,vintage,value,moe,reliability'];
    (S.view || []).forEach(function (r) {
      lines.push([r.g, S.indicator, S.vintage, r.value === null ? '' : r.value, r.moe === null ? '' : r.moe, r.rel].map(csvCell).join(','));
    });
    var blob = new Blob([lines.join('\r\n') + '\r\n'], { type: 'text/csv;charset=utf-8' });
    var url = URL.createObjectURL(blob);
    var a = document.createElement('a');
    a.href = url;
    a.download = 'cuyahoga_' + S.indicator + '_' + S.vintage + '.csv';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    setTimeout(function () { URL.revokeObjectURL(url); }, 1000);
    window.lastCsvRows = lines.length - 1;
  }

  /* ---------- events ---------- */
  function bind() {
    el.indicator.addEventListener('change', function () { S.indicator = el.indicator.value; changeSelection({ keepSelection: true }); });
    el.vintage.addEventListener('change', function () { S.vintage = el.vintage.value; changeSelection({}); });
    el.reliability.addEventListener('change', viewUpdate);
    el.search.addEventListener('input', viewUpdate);
    el.useApi.addEventListener('change', function () { changeSelection({ keepSelection: true }); });
    el.download.addEventListener('click', downloadCsv);

    el.tbl.tHead.addEventListener('click', function (e) {
      var b = e.target.closest('button[data-key]');
      if (b) sortBy(b.dataset.key);
    });
    el.tbody.addEventListener('click', function (e) {
      var tr = e.target.closest('tr[data-g]');
      if (tr) select(tr.dataset.g, false);
    });
    el.tbody.addEventListener('keydown', function (e) {
      if (e.key !== 'Enter' && e.key !== ' ') return;
      var tr = e.target.closest('tr[data-g]');
      if (tr) { e.preventDefault(); select(tr.dataset.g, false); }
    });
    el.tbody.addEventListener('mouseover', function (e) {
      var tr = e.target.closest('tr[data-g]');
      setOverlay(layers.hover, tr ? tr.dataset.g : null);
    });
    el.tbody.addEventListener('mouseleave', function () { setOverlay(layers.hover, null); });

    el.map.addEventListener('pointermove', function (e) {
      var p = e.target.closest ? e.target.closest('path.tract') : null;
      if (!p) { hideTip(); return; }
      var g = p.dataset.g;
      setOverlay(layers.hover, g);
      showTip(g, e);
    });
    el.map.addEventListener('pointerleave', hideTip);
    el.map.addEventListener('click', function (e) {
      var p = e.target.closest('path.tract');
      if (p) select(p.dataset.g, true);
    });
  }

  function showTip(g, e) {
    var ind = S.byId[S.indicator], r = S.rows.filter(function (x) { return x.g === g; })[0];
    if (!r) return;
    el.tooltip.innerHTML = '<strong>' + esc(r.name) + '</strong>' + esc(ind.name) + ': ' + esc(fmt(ind, r.value)) + '<br>' +
      esc(fmtMoe(ind, r.moe)) + ' (' + esc(REL_LABEL[r.rel] || r.rel) + ' reliability)';
    el.tooltip.hidden = false;
    var box = el.mapWrap.getBoundingClientRect(), x = e.clientX - box.left + 14, y = e.clientY - box.top + 14;
    var w = el.tooltip.offsetWidth, h = el.tooltip.offsetHeight;
    if (x + w > box.width) x = Math.max(0, e.clientX - box.left - w - 14);
    if (y + h > box.height) y = Math.max(0, e.clientY - box.top - h - 14);
    el.tooltip.style.left = x + 'px';
    el.tooltip.style.top = y + 'px';
  }
  function hideTip() {
    el.tooltip.hidden = true;
    setOverlay(layers.hover, null);
  }

  /* ---------- start ---------- */
  function init() {
    getJSON('data/indicators.json').then(function (j) {
      S.meta = j.meta; S.indicators = j.indicators; S.data = j.data; S.county = j.county;
      S.names = j.tract_names; S.dictionary = j.dictionary;
      j.indicators.forEach(function (i) { S.byId[i.id] = i; });
      var h = {};
      location.hash.replace(/^#/, '').split('&').forEach(function (kv) {
        var p = kv.split('=');
        if (p[0]) h[p[0]] = decodeURIComponent(p[1] || '');
      });
      S.indicator = S.byId[h.ind] ? h.ind : (S.byId.poverty_rate ? 'poverty_rate' : S.indicators[0].id);
      var vids = S.meta.vintages.map(function (v) { return v.id; });
      S.vintage = vids.indexOf(h.v) >= 0 ? h.v : vids[vids.length - 1];
      fillSelects();
      renderNotes();
      bind();
      return changeSelection({});
    }).then(function () {
      detectApi();
    }).catch(function (e) {
      showError('Could not load the data files: ' + e.message + '. Serve this folder over HTTP, for example with "python -m http.server" inside the web folder.');
    });
  }

  init();
})();
