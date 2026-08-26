/* Public tracking page - no auth, reference only. */
(function () {
  'use strict';
  var M = window.M, esc = M.esc;
  var out = M.el('#out'), input = M.el('#ref'), form = M.el('#track-form');

  // Each kind of job has its own rail. The API tells us which one this is.
  var RAILS = {
    freight: {
      stages: ['placed', 'assigned', 'at_pickup', 'in_transit', 'delivered'],
      labels: ['Booked', 'Carrier', 'Load-out', 'In transit', 'Delivered']
    },
    hire: {
      stages: ['requested', 'confirmed', 'on_site', 'off_hire', 'returned'],
      labels: ['Requested', 'Confirmed', 'On site', 'Off hire', 'Returned']
    }
  };

  function render(o) {
    var kind = o.kind === 'hire' ? 'hire' : 'freight';
    var rails = RAILS[kind];
    var reached = rails.stages.indexOf(o.status);
    var cancelled = o.status === 'cancelled';

    var rail = cancelled ? '' :
      '<div class="rail">' + rails.stages.map(function (_, i) {
        return '<div class="' + (i <= reached ? 'on' : '') + '"></div>';
      }).join('') + '</div>' +
      '<div class="rail-labels">' + rails.labels.map(function (l) { return '<span>' + l + '</span>'; }).join('') + '</div>';

    // Where it is now, and whether paperwork is what is holding it. A
    // consignee waiting on a truck should not have to phone to find out.
    var live = '';
    if (kind === 'freight' && o.tracking && o.tracking.last) {
      var t = o.tracking;
      live = '<div class="track-live">' +
        '<div class="progress"><div style="width:' + Math.min(100, t.progress_pct || 0) + '%"></div></div>' +
        '<p><b>' + esc(t.last.place) + '</b> &middot; ' + esc(M.ago(t.last.created_at)) +
          (t.km_left !== null && t.km_left !== undefined ? ' &middot; ' + Math.round(t.km_left) + ' km to run' : '') +
          (t.eta_at ? ' &middot; due ' + esc(M.when(t.eta_at)) : '') + '</p>' +
      '</div>';
    }

    var drops = '';
    if (kind === 'freight' && o.stops && o.stops.length > 1) {
      drops = '<div class="panel" style="margin-top:16px"><h3>Drops</h3><ul class="drop-list">' +
        o.stops.map(function (s) {
          return '<li class="drop' + (s.status === 'done' ? ' drop-done' : '') + '">' +
            '<i>' + s.seq + '</i><div><b>' + esc(s.node_name) +
            (s.tonnes ? ' &middot; ' + esc(s.tonnes) + ' t' : '') + '</b>' +
            '<span>' + (s.status === 'done'
              ? 'Signed ' + esc(M.when(s.completed_at))
              : 'Awaiting delivery') + '</span></div></li>';
        }).join('') + '</ul></div>';
    }

    var paperwork = '';
    if (kind === 'freight' && o.documents && o.documents.total) {
      var d = o.documents;
      paperwork = '<div class="track-docs' + (d.complete ? ' ok' : '') + '">' +
        '<b>' + d.filed + ' of ' + d.total + ' documents filed</b>' +
        '<span>' + (d.complete
          ? 'Nothing outstanding on this load.'
          : 'Waiting on: ' + esc(d.next_due)) + '</span></div>';
    }

    var borders = '';
    if (kind === 'freight' && o.crossings && o.crossings.length) {
      borders = '<div class="border-strip"><span>Crossings</span>' +
        o.crossings.map(function (c) { return '<b>' + esc(c.post) + '</b>'; }).join('') + '</div>';
    }

    var timeline = (o.timeline || []).slice().reverse().map(function (e) {
      return '<li><b>' + esc(e.label) + '</b><span>' + esc(M.when(e.created_at)) +
             (e.note ? ' &middot; ' + esc(e.note) : '') + '</span></li>';
    }).join('');

    out.innerHTML =
      '<div class="panel">' +
        '<div style="display:flex;justify-content:space-between;align-items:center;gap:12px;flex-wrap:wrap;">' +
          '<div><span class="muted mono">' + esc(o.ref) + '</span>' +
            '<h3 style="margin:2px 0 0">' + esc(kind === 'hire'
              ? o.plant_name
              : o.commodity_name + ' \u00b7 ' + o.tonnes + ' t') + '</h3></div>' +
          '<span class="pill pill-' + esc(o.status) + '">' + esc(o.status_label) + '</span>' +
        '</div>' +
        rail + live +
        '<dl class="kv" style="margin-top:22px">' +
          (kind === 'hire'
            ? '<dt>Machine</dt><dd>' + esc(o.plant_name) + '</dd>' +
              '<dt>Site</dt><dd>' + esc(o.site_name) + '</dd>' +
              '<dt>Period</dt><dd>' + esc(o.days) + (o.days === 1 ? ' day' : ' days') + ' &middot; ' + esc(o.tier) + ' rate</dd>' +
              '<dt>Crew</dt><dd>' + (o.with_operator ? 'Musanga operator' : 'Dry hire') + '</dd>' +
              '<dt>Float from</dt><dd>' + esc(o.depot_name) + '</dd>' +
              '<dt>Purpose</dt><dd>' + esc(o.purpose) + '</dd>'
            : '<dt>Load at</dt><dd>' + esc(o.from_name) + '</dd>' +
              '<dt>Deliver to</dt><dd>' + esc(o.to_name) + '</dd>' +
              '<dt>Cargo</dt><dd>' + esc(o.goods) + '</dd>' +
              '<dt>Equipment</dt><dd>' + esc(o.equipment_name) + ' &middot; ' + esc(o.service_name) + '</dd>' +
              '<dt>Distance</dt><dd>' + esc(o.distance_km) + ' km</dd>' +
              '<dt>Transit</dt><dd>~' + esc(M.duration(o.eta_minutes)) + '</dd>' +
              (o.corridor ? '<dt>Corridor</dt><dd>' + esc(o.corridor) + '</dd>' : '') +
              (o.weights && o.weights.discharged_kg
                ? '<dt>Weighbridge</dt><dd>' + o.weights.loaded_kg.toLocaleString() + ' kg out, ' +
                  o.weights.discharged_kg.toLocaleString() + ' kg in <span class="muted">(' +
                  esc(o.weights.variance_pct) + '%)</span></dd>'
                : '') +
              (o.driver ? '<dt>Carrier</dt><dd>' + esc(o.driver.name) + '</dd>' : '')) +
        '</dl>' + borders + paperwork +
      '</div>' + drops +
      '<div class="panel" style="margin-top:16px"><h3>Timeline</h3><ul class="timeline">' + timeline + '</ul></div>';
  }

  function lookup(ref) {
    ref = String(ref || '').trim().toUpperCase();
    if (!ref) return;
    out.innerHTML = '<div class="spinner">Looking up ' + esc(ref) + '…</div>';
    M.api.track(ref).then(render).catch(function (err) {
      out.innerHTML = '<div class="notice notice-error">' + esc(err.message) + '</div>';
    });
  }

  form.addEventListener('submit', function (e) {
    e.preventDefault();
    history.replaceState(null, '', '/track?ref=' + encodeURIComponent(input.value.trim()));
    lookup(input.value);
  });

  var preset = new URLSearchParams(location.search).get('ref');
  if (preset) { input.value = preset; lookup(preset); }
})();
