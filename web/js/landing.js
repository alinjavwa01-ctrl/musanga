/* Landing page: both live engines, the plant catalogue, the corridor table. */
(function () {
  'use strict';
  var M = window.M, api = M.api, esc = M.esc;

  // Corridors we run often enough to publish.
  var CORRIDORS = [
    { from: 'kalumbila', to: 'kasumbalesa', load: 'Copper concentrate' },
    { from: 'solwezi',   to: 'ndola',       load: 'Concentrate to smelter' },
    { from: 'kafue',     to: 'mkushi',      load: 'Fertiliser to farm block' },
    { from: 'kafue',     to: 'chingola',    load: 'Sulphuric acid' },
    { from: 'ndola',     to: 'solwezi',     load: 'Diesel to mine' },
    { from: 'mkushi',    to: 'lusaka',      load: 'Maize to terminal' },
    { from: 'kitwe',     to: 'chirundu',    load: 'Cathodes for export' }
  ];

  var state = { mode: 'freight', equipment: null, category: 'earthmoving', config: null };

  document.getElementById('year').textContent = new Date().getFullYear();

  var header = document.getElementById('header');
  var onScroll = function () { header.classList.toggle('stuck', window.scrollY > 8); };
  window.addEventListener('scroll', onScroll, { passive: true });
  onScroll();

  var out = M.el('#quote-out');

  /* --- freight ---------------------------------------------------------- */
  var fromSel = M.el('#q-from'), toSel = M.el('#q-to'), svcSel = M.el('#q-service'),
      commSel = M.el('#q-commodity'), tonnes = M.el('#q-tonnes'), strip = M.el('#equipment-strip');

  // The commodity decides which equipment may carry it, never the reverse.
  function renderStrip() {
    var commodity = commSel.value;
    var options = state.config.equipment.filter(function (eq) {
      return eq.commodities.indexOf(commodity) >= 0;
    });
    if (options.map(function (e) { return e.key; }).indexOf(state.equipment) < 0) {
      state.equipment = options.length ? options[0].key : null;
    }
    strip.innerHTML = options.map(function (eq) {
      return '<button type="button" class="chip" data-key="' + esc(eq.key) + '"' +
             ' title="' + esc(eq.blurb) + '" aria-pressed="' + (eq.key === state.equipment) + '">' +
             esc(eq.name) + '</button>';
    }).join('');
    var chosen = options.filter(function (e) { return e.key === state.equipment; })[0];
    if (chosen) {
      tonnes.max = chosen.payload_t;
      if (Number(tonnes.value) > chosen.payload_t) tonnes.value = chosen.payload_t;
    }
  }

  function freightQuery() {
    return 'equipment=' + encodeURIComponent(state.equipment) +
           '&commodity=' + encodeURIComponent(commSel.value) +
           '&service=' + encodeURIComponent(svcSel.value) +
           '&from=' + encodeURIComponent(fromSel.value) +
           '&to=' + encodeURIComponent(toSel.value) +
           '&tonnes=' + encodeURIComponent(tonnes.value || 0);
  }

  function refreshFreight() {
    if (!state.equipment) {
      return showError('Nothing on the network carries that.');
    }
    api.quote({
      equipment: state.equipment, commodity: commSel.value, service: svcSel.value,
      from_zone: fromSel.value, to_zone: toSel.value, tonnes: Number(tonnes.value) || 0
    }).then(function (q) {
      render(q.equipment_name, q.total, [
        q.distance_km + ' km', q.billed_tonnes + ' t billed',
        q.rate_per_tkm + '/tonne-km', '~' + M.duration(q.eta_minutes)
      ], q.lines, q.vat, '/app#/book?' + freightQuery(), 'Book this load');
    }).catch(function (err) { showError(err.message); });
  }

  /* --- hire ------------------------------------------------------------- */
  var plantSel = M.el('#h-plant'), siteSel = M.el('#h-site'), daysInput = M.el('#h-days'),
      opCheck = M.el('#h-operator'), fuelCheck = M.el('#h-fuel');

  function hireQuery() {
    return 'plant=' + encodeURIComponent(plantSel.value) +
           '&site=' + encodeURIComponent(siteSel.value) +
           '&days=' + encodeURIComponent(daysInput.value || 1) +
           '&operator=' + (opCheck.checked ? 1 : 0) +
           '&fuel=' + (fuelCheck.checked ? 1 : 0);
  }

  function refreshHire() {
    api.hireQuote({
      plant: plantSel.value, site: siteSel.value, days: Number(daysInput.value) || 1,
      with_operator: opCheck.checked, with_fuel: fuelCheck.checked
    }).then(function (q) {
      render(q.plant_name, q.total, [
        q.days + (q.days === 1 ? ' day' : ' days'), q.tier + ' rate',
        q.effective_day + '/day', 'from ' + q.depot_name
      ], q.lines, q.vat, '/app#/hire?' + hireQuery(), 'Book this machine');
    }).catch(function (err) { showError(err.message); });
  }

  /* --- shared rendering ------------------------------------------------- */
  function render(title, total, meta, lines, vat, href, cta) {
    var rows = lines.filter(function (l) { return l.ngwee !== 0; }).map(function (l) {
      return '<div><span>' + esc(l.label) + '</span><span>' + esc(l.amount) + '</span></div>';
    }).join('');
    out.innerHTML =
      '<div class="quote-result">' +
        '<div class="quote-price"><span>' + esc(title) + '</span><b>' + esc(total) + '</b></div>' +
        '<div class="quote-meta">' + meta.map(function (m) { return '<span>' + esc(m) + '</span>'; }).join('') + '</div>' +
        // The number is the answer; the itemisation is for whoever wants to argue
        // with it. Uber does not show you the fare breakdown before you ride.
        '<details class="more"><summary>Breakdown</summary>' +
          '<div class="quote-lines">' + rows +
            '<div class="total"><span>VAT 16%</span><span>' + esc(vat) + '</span></div>' +
          '</div>' +
        '</details>' +
      '</div>' +
      '<a class="btn btn-primary btn-block" style="margin-top:20px" href="' + href + '">' + esc(cta) + '</a>';
  }

  function showError(message) {
    out.innerHTML = '<div class="quote-result"><div class="notice notice-error" style="margin:0">' +
                    esc(message) + '</div></div>';
  }

  function refresh() {
    return state.mode === 'freight' ? refreshFreight() : refreshHire();
  }

  // Keep the number inside whatever limit the current unit imposes.
  function clamp(input) {
    var max = Number(input.max), min = Number(input.min) || 0;
    if (max && Number(input.value) > max) input.value = max;
    if (min && Number(input.value) < min) input.value = min;
  }

  var refreshSoon = M.debounce(refresh, 240);

  /* --- wiring ----------------------------------------------------------- */
  M.el('.mode-switch').addEventListener('click', function (e) {
    var btn = e.target.closest('button[data-mode]');
    if (!btn || btn.dataset.mode === state.mode) return;
    state.mode = btn.dataset.mode;
    M.els('.mode-switch button').forEach(function (b) {
      b.setAttribute('aria-pressed', String(b === btn));
    });
    M.el('#mode-freight').hidden = state.mode !== 'freight';
    M.el('#mode-hire').hidden = state.mode !== 'hire';
    refresh();
  });

  strip.addEventListener('click', function (e) {
    var btn = e.target.closest('.chip');
    if (!btn) return;
    state.equipment = btn.dataset.key;
    renderStrip();
    refresh();
  });

  commSel.addEventListener('change', function () { renderStrip(); refresh(); });
  [fromSel, toSel, svcSel, plantSel, siteSel, opCheck, fuelCheck].forEach(function (n) {
    n.addEventListener('change', refresh);
  });
  tonnes.addEventListener('input', function () { clamp(tonnes); refreshSoon(); });
  daysInput.addEventListener('input', function () { clamp(daysInput); refreshSoon(); });

  /* --- plant catalogue -------------------------------------------------- */
  function renderPlant() {
    M.els('#cat-tabs .chip').forEach(function (b) {
      b.setAttribute('aria-pressed', String(b.dataset.cat === state.category));
    });
    var shown = state.config.plant.filter(function (m) { return m.category === state.category; });
    M.el('#plant-grid').innerHTML = shown.map(function (m) {
      return '<article class="plant-card">' +
        '<h3>' + esc(m.name) + '</h3>' +
        '<p>' + esc(m.blurb) + '</p>' +
        '<div class="plant-rate"><b>' + esc(M.kwacha(m.day_ngwee)) + '</b> <span>/ day, dry</span></div>' +
        '<a class="btn btn-ghost btn-sm" href="/app#/hire?plant=' + esc(m.key) + '">Rent this</a>' +
      '</article>';
    }).join('');
  }

  /* --- boot ------------------------------------------------------------- */
  api.config().then(function (cfg) {
    state.config = cfg;

    // Group commodities by sector so mining, agri and fuel read apart.
    var sectors = {};
    cfg.commodities.forEach(function (c) { (sectors[c.sector] = sectors[c.sector] || []).push(c); });
    commSel.innerHTML = Object.keys(sectors).map(function (sector) {
      return '<optgroup label="' + esc(sector.charAt(0).toUpperCase() + sector.slice(1)) + '">' +
        sectors[sector].map(function (c) {
          return '<option value="' + esc(c.key) + '">' + esc(c.name) + '</option>';
        }).join('') + '</optgroup>';
    }).join('');
    commSel.value = 'copper_concentrate';

    fromSel.innerHTML = M.options(cfg.zones, 'key', 'name');
    toSel.innerHTML = M.options(cfg.zones, 'key', 'name');
    svcSel.innerHTML = M.options(cfg.services, 'key', 'name');
    fromSel.value = 'kalumbila';
    toSel.value = 'kasumbalesa';
    svcSel.value = 'spot';

    plantSel.innerHTML = Object.keys(sectorsOfPlant(cfg)).map(function (cat) {
      return '<optgroup label="' + esc(catName(cfg, cat)) + '">' +
        sectorsOfPlant(cfg)[cat].map(function (m) {
          return '<option value="' + esc(m.key) + '">' + esc(m.name) + '</option>';
        }).join('') + '</optgroup>';
    }).join('');
    plantSel.value = 'excavator30';
    siteSel.innerHTML = M.options(cfg.zones, 'key', 'name');
    siteSel.value = 'kalumbila';

    renderStrip();
    refresh();

    M.el('#n-nodes').textContent = cfg.zones.length;
    M.el('#n-plant').textContent = cfg.plant.length;

    M.el('#cat-tabs').innerHTML = cfg.plant_categories.map(function (c) {
      return '<button type="button" class="chip" data-cat="' + esc(c.key) + '" aria-pressed="' +
             (c.key === state.category) + '">' + esc(c.name) + '</button>';
    }).join('');
    M.el('#cat-tabs').addEventListener('click', function (e) {
      var btn = e.target.closest('.chip');
      if (!btn) return;
      state.category = btn.dataset.cat;
      renderPlant();
    });
    renderPlant();

    var names = {};
    cfg.zones.forEach(function (z) { names[z.key] = z.name; });

    // Lead with mines, farm blocks and borders - the nodes that define us.
    M.el('#node-tags').innerHTML = cfg.zones.map(function (z) {
      var key = ['mine', 'agri', 'border'].indexOf(z.kind) >= 0;
      return '<span class="node-tag' + (key ? ' key' : '') + '">' + esc(z.name) + '</span>';
    }).join('');

    // Distances come from the same measured network the rates are built on.
    Promise.all(CORRIDORS.map(function (c) {
      return api.distance({ from_zone: c.from, to_zone: c.to })
        .then(function (d) { c.km = d.distance_km; })
        .catch(function () { c.km = '—'; });
    })).then(function () {
      M.el('#corridors').innerHTML = CORRIDORS.map(function (c) {
        return '<tr><td><b>' + esc(names[c.from]) + ' &rarr; ' + esc(names[c.to]) + '</b></td>' +
               '<td><span class="sub" style="margin:0">' + esc(c.load) + '</span></td>' +
               '<td>' + esc(c.km) + ' km</td></tr>';
      }).join('');
    });
  }).catch(function () {
    showError('Could not reach the pricing service.');
  });

  function sectorsOfPlant(cfg) {
    var out = {};
    cfg.plant.forEach(function (m) { (out[m.category] = out[m.category] || []).push(m); });
    return out;
  }
  function catName(cfg, key) {
    var c = cfg.plant_categories.filter(function (x) { return x.key === key; })[0];
    return c ? c.name : key;
  }
})();

/* ==========================================================================
   The network map.

   Not a picture of Zambia - the real thing. Every point is a node from geo.py
   with its true latitude and longitude, and every line is a road distance we
   have actually measured. Pick two points and the freight engine rates the
   lane, which is the same call a real booking makes.

   Plain SVG on an equirectangular projection. No mapping library: the CSP
   allows nothing off-origin, and at this scale a projection is four lines of
   arithmetic.
   ========================================================================== */
(function () {
  var svg = document.getElementById('zm-map');
  if (!svg) return;
  var M = window.M, api = M.api;

  var W = 1000, H = 640, PAD = 42;
  var lanesG = document.getElementById('zm-lanes');
  var nodesG = document.getElementById('zm-nodes');
  var pickG  = document.getElementById('zm-picked');
  var out    = document.getElementById('zm-readout');
  var pick   = { from: null, to: null };
  var byKey  = {};
  var bounds = null;

  function project(lat, lng) {
    // Latitude is compressed by cos(mean latitude) so the country is not
    // stretched sideways - at 13 degrees south that is a visible difference.
    var k = Math.cos(bounds.midLat * Math.PI / 180);
    var x = PAD + (lng - bounds.minLng) / (bounds.maxLng - bounds.minLng) * (W - PAD * 2);
    var y = PAD + (bounds.maxLat - lat) / (bounds.maxLat - bounds.minLat) * (H - PAD * 2);
    return [x, y, k];
  }

  function svgEl(name, attrs) {
    var e = document.createElementNS('http://www.w3.org/2000/svg', name);
    for (var a in attrs) if (attrs.hasOwnProperty(a)) e.setAttribute(a, attrs[a]);
    return e;
  }

  function setBounds(zones) {
    var lats = zones.map(function (z) { return z.lat; });
    var lngs = zones.map(function (z) { return z.lng; });
    var minLat = Math.min.apply(null, lats), maxLat = Math.max.apply(null, lats);
    var minLng = Math.min.apply(null, lngs), maxLng = Math.max.apply(null, lngs);
    // Keep the aspect honest rather than filling the box.
    var midLat = (minLat + maxLat) / 2;
    var spanLat = maxLat - minLat;
    var spanLng = (maxLng - minLng) * Math.cos(midLat * Math.PI / 180);
    var want = (W - PAD * 2) / (H - PAD * 2);
    var have = spanLng / spanLat;
    if (have > want) {
      var padLat = (spanLng / want - spanLat) / 2;
      minLat -= padLat; maxLat += padLat;
    } else {
      var padLng = ((spanLat * want) / Math.cos(midLat * Math.PI / 180) - (maxLng - minLng)) / 2;
      minLng -= padLng; maxLng += padLng;
    }
    bounds = { minLat: minLat, maxLat: maxLat, minLng: minLng, maxLng: maxLng, midLat: midLat };
  }

  function draw(cfg) {
    setBounds(cfg.zones);
    cfg.zones.forEach(function (z) { byKey[z.key] = z; });

    (cfg.lanes || []).forEach(function (lane) {
      var a = byKey[lane.from], b = byKey[lane.to];
      if (!a || !b) return;
      var p1 = project(a.lat, a.lng), p2 = project(b.lat, b.lng);
      lanesG.appendChild(svgEl('line', {
        x1: p1[0], y1: p1[1], x2: p2[0], y2: p2[1],
        class: 'zm-lane', 'data-km': lane.km
      }));
    });

    cfg.zones.forEach(function (z) {
      var p = project(z.lat, z.lng);
      var g = svgEl('g', {
        class: 'zm-node', 'data-key': z.key, 'data-kind': z.kind,
        tabindex: '0', role: 'button',
        'aria-label': z.name + ', ' + z.region
      });
      g.appendChild(svgEl('circle', { cx: p[0], cy: p[1], r: 16, class: 'zm-hit' }));
      g.appendChild(svgEl('circle', { cx: p[0], cy: p[1], r: z.kind === 'hub' ? 7 : 5, class: 'zm-dot' }));
      var label = svgEl('text', { x: p[0] + 11, y: p[1] + 4, class: 'zm-label' });
      label.textContent = z.name;
      g.appendChild(label);
      g.addEventListener('click', function () { choose(z.key); });
      g.addEventListener('keydown', function (e) {
        if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); choose(z.key); }
      });
      nodesG.appendChild(g);
    });
  }

  function choose(key) {
    if (!pick.from || (pick.from && pick.to)) {
      pick.from = key; pick.to = null;
    } else if (key === pick.from) {
      pick.from = null;
    } else {
      pick.to = key;
    }
    paint();
    if (pick.from && pick.to) rate();
    else if (pick.from) {
      say('<p class="map-hint"><b>' + esc(byKey[pick.from].name) + '</b> &rarr; now pick where it is going.</p>');
    } else {
      say('<p class="map-hint">Tap a point to set where the load starts.</p>');
    }
  }

  function paint() {
    Array.prototype.forEach.call(nodesG.children, function (g) {
      var k = g.getAttribute('data-key');
      g.classList.toggle('is-from', k === pick.from);
      g.classList.toggle('is-to', k === pick.to);
    });
    pickG.innerHTML = '';
    if (pick.from && pick.to) {
      var a = byKey[pick.from], b = byKey[pick.to];
      var p1 = project(a.lat, a.lng), p2 = project(b.lat, b.lng);
      pickG.appendChild(svgEl('line', {
        x1: p1[0], y1: p1[1], x2: p2[0], y2: p2[1], class: 'zm-picked-lane'
      }));
    }
  }

  function say(html) { out.innerHTML = html; }

  function esc(s) {
    return String(s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }

  function rate() {
    var a = byKey[pick.from], b = byKey[pick.to];
    say('<p class="map-hint">Rating ' + esc(a.name) + ' to ' + esc(b.name) + '&hellip;</p>');
    api.quote({
      from_zone: pick.from, to_zone: pick.to,
      commodity: 'general', equipment: 'flatbed30', service: 'spot', tonnes: 30
    }).then(function (q) {
      say(
        '<div class="map-quote">' +
          '<div class="map-lane"><b>' + esc(a.name) + '</b><span>&rarr;</span><b>' + esc(b.name) + '</b></div>' +
          '<div class="map-figure">' + esc(q.total) + '</div>' +
          '<div class="map-meta">' +
            '<span>' + esc(q.distance_km) + ' km</span>' +
            '<span>30 t on a ' + esc(q.equipment_name) + '</span>' +
            '<span>~' + esc(M.duration(q.eta_minutes)) + '</span>' +
          '</div>' +
          '<a class="link-arrow" href="#price">Price your own load</a>' +
        '</div>');
    }).catch(function (e) {
      say('<p class="map-hint">' + esc((e && e.message) || 'Could not rate that lane.') + '</p>');
    });
  }

  api.config().then(draw).catch(function () {
    say('<p class="map-hint">The network is unavailable right now.</p>');
  });
})();
