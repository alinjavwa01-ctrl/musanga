/* The transporter's RFP page - DocuSign logic, Wise UI.

   The link in the email or WhatsApp carries a token. The token is the only
   credential; there is no account and no session. Everything the transporter
   sees is scoped to it.

   The word "bid" stays in the code and the database, because that is what
   procurement calls it. The transporter never sees it. On their side they
   are giving Musanga a rate and a set of trucks, so the copy says exactly
   that: "your rate", "your reply", "send your rate". A transporter with a
   phone at a fuel stop reads plain English, not procurement jargon.

   The layout borrows Wise's shape: one column, ~720px, big display numbers,
   generous whitespace, soft filled panels, one primary action always visible
   at the foot. Two views: Review the ask -> Send your rate. Confirmation
   replaces the second view once the reply is in. */
(function () {
  'use strict';

  var M = window.M, api = M.api, esc = M.esc, el = M.el;
  var root = document.getElementById('root');
  var rawToken = (location.pathname.split('/rfp/')[1] || '').replace(/\/$/, '');
  // /rfp/open/<open_token> is the one link ops can share to anyone - the
  // first open mints a personal invite behind it (see load()), and every
  // other function in this file just uses `token` once that's resolved,
  // same as it always has for a named invite's own link.
  var openToken = rawToken.indexOf('open/') === 0 ? rawToken.slice(5) : null;
  var token = openToken ? null : rawToken;
  var state = { rfp: null, trucks: [], form: {} };
  var viewToken = null;   // set by the server on every open
  var pingSeconds = 15;   // interval between heartbeats
  var pingTimer = null;
  var pingLastAt = 0;

  /* --- heartbeat (DocSend-style read tracking) --------------------------- */
  function heartbeat(force) {
    if (!viewToken) return;
    if (document.hidden && !force) return;
    var now = Date.now();
    var delta = pingLastAt ? Math.round((now - pingLastAt) / 1000) : pingSeconds;
    pingLastAt = now;
    api.post('/api/rfp/' + token + '/ping', { view_token: viewToken, seconds: delta }).catch(function () {});
  }

  function startHeartbeat() {
    if (pingTimer) return;
    pingLastAt = Date.now();
    pingTimer = setInterval(heartbeat, pingSeconds * 1000);
    document.addEventListener('visibilitychange', function () {
      if (!document.hidden) pingLastAt = Date.now();
    });
    window.addEventListener('pagehide', function () { heartbeat(true); });
  }

  /* --- helpers ---------------------------------------------------------- */

  function shell(inner) { root.innerHTML = '<div class="sign-wrap wise-wrap">' + inner + '</div>'; }
  function panel(inner, opts) {
    var extra = opts && opts.style ? ' style="' + opts.style + '"' : '';
    return '<section class="sign-panel wise-panel"' + extra + '>' + inner + '</section>';
  }

  function fatal(msg) {
    shell('<div class="sign-panel wise-panel" style="max-width:520px;margin:60px auto;text-align:center">' +
      '<h3>This link cannot be opened</h3><p class="muted">' + esc(msg) + '</p>' +
      '<a class="btn btn-ghost btn-block" href="/">Go to musanga.com</a></div>');
  }

  function fmtDate(unix) {
    if (!unix) return '';
    return new Date(unix * 1000).toLocaleDateString(undefined,
      { day: 'numeric', month: 'short', year: 'numeric' });
  }

  // loading_from/loading_to are plain "YYYY-MM-DD" strings, not timestamps -
  // T00:00:00 keeps the parse in local time so the date printed is the date
  // typed, not shifted a day by a UTC-midnight parse.
  function fmtDateStr(s) {
    if (!s) return '';
    var d = new Date(s + 'T00:00:00');
    if (isNaN(d.getTime())) return s;
    return d.toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric' });
  }

  function fmtNumber(value) {
    if (value === null || value === undefined || value === '') return '';
    var n = Number(String(value).replace(/[^0-9.\-]/g, ''));
    if (!isFinite(n) || n === 0) return '';
    return n.toLocaleString(undefined, { maximumFractionDigits: 0 });
  }

  function fmtBig(value) {
    // Money at K4.16M / K812K reads faster on a phone than K4,160,000.
    if (value === null || value === undefined || value === '') return '0';
    var n = Number(String(value).replace(/[^0-9.\-]/g, ''));
    if (!isFinite(n) || n === 0) return '0';
    if (n >= 1e6) return (n / 1e6).toFixed(n >= 1e7 ? 1 : 2).replace(/\.0+$/, '') + 'M';
    if (n >= 1e4) return Math.round(n / 1e3) + 'K';
    return n.toLocaleString(undefined, { maximumFractionDigits: 0 });
  }

  function askRow(label, value, opts) {
    var v = value === 0 || value ? value : '—';
    var cls = opts && opts.mono ? ' class="mono"' : '';
    return '<div class="ask-row"><dt>' + esc(label) + '</dt>' +
           '<dd' + cls + '>' + esc(v) + '</dd></div>';
  }

  function renderTerms(text) {
    return esc(text).split(/\n\s*\n/).map(function (block) {
      if (block.indexOf('## ') === 0) return '<h2>' + block.slice(3).trim() + '</h2>';
      var clause = /^\d+\.\d+\s/.test(block.trim());
      return '<p' + (clause ? ' class="clause"' : '')
        + '>' + block.trim().replace(/\n\s*/g, ' ') + '</p>';
    }).join('');
  }

  /* --- shared header ---------------------------------------------------- */

  // Musanga's own loading window - the single fastest way to rule a bid in
  // or out. If a transporter's earliest free truck is after this window
  // closes, there's no rate that fixes that.
  function loadingWindowCard(r) {
    if (!r.loading_from && !r.loading_to) return '';
    var range = [fmtDateStr(r.loading_from), fmtDateStr(r.loading_to)].filter(Boolean).join(' → ');
    return '<section class="wise-pay-card">' +
      '<div class="wise-pay-label">Musanga needs this on the road</div>' +
      '<div class="wise-pay-single">' + esc(range) + '</div>' +
      '<div class="wise-pay-foot">If your earliest free truck is after this window, you\'re probably not a fit for this one — decline below rather than guess.</div>' +
    '</section>';
  }

  // An invite from the open link has no company name until the transporter
  // types one in at bid time - copy that would otherwise read "binds  to
  // the rate" falls back to this instead.
  function carrierLabel(r) { return r.invite.carrier_name || 'your company'; }

  function askHeader(r) {
    var trucksNeeded = r.trucks_needed ? esc(r.trucks_needed) + ' trucks · ' : '';
    // The Wise-scale display heading is built for two short city names. A
    // multi-origin lane ("Central & Southern Zambia") is a much longer
    // string, and at the same font size it wraps into three heavy lines
    // before a phone reader sees anything else - so a long pair gets a
    // smaller class instead of fighting the layout with the real string.
    var long = (String(r.from_place).length + String(r.to_place).length) > 26;
    return '<div class="wise-header' + (long ? ' wise-header--long' : '') + '">' +
      '<div class="wise-kicker">' + esc(r.company.name) + ' · ' + esc(r.ref) + '</div>' +
      '<h1>' + esc(r.from_place) + '<br><span class="wise-arrow">→</span> ' + esc(r.to_place) + '</h1>' +
      '<p class="wise-sub">' + trucksNeeded + esc(r.tonnes_total || 0) + ' t · ' + esc(r.commodity) + '</p>' +
      '<p class="muted" style="margin-top:12px;font-size:.9rem">' +
        (r.invite.carrier_name ? 'For <b>' + esc(r.invite.carrier_name) + '</b> · ' : '') +
        'Reply by ' + esc(fmtDate(r.closes_at)) + '</p>' +
    '</div>';
  }

  /* --- view: review ----------------------------------------------------- */

  function reviewView(r) {
    if (r.status !== 'open') return closedView(r);
    if (r.invite.status === 'declined') return declinedView(r);
    if (r.bid) return thanksView(r);

    shell(
      askHeader(r) +

      // Payment terms stay out of the page itself - the transporter still
      // signs to them (clause 5.3 in the terms below), just not as a hero
      // card up front.
      loadingWindowCard(r) +

      // The lane, tonnage, trucks and commodity already read in the header
      // above, and the loading window has its own card - repeating them
      // here just adds scrolling before the terms and the button. This
      // panel only carries what's genuinely new: equipment, cover, notes.
      panel(
        '<h2>The details</h2>' +
        '<dl class="ask-list">' +
          askRow('Equipment', r.equipment) +
          askRow('Cover required per load', r.cover_min || '—') +
          (r.notes ? askRow('Note from Musanga', r.notes) : '')
      ) +

      panel(
        '<h2>The terms you agree to</h2>' +
        '<p class="muted" style="font-size:.88rem;margin:-6px 0 14px">Reading these once covers every load Musanga awards you in this window.</p>' +
        '<div class="doc-body">' + renderTerms(r.terms_body) + '</div>' +
        '<p class="hash" style="margin-top:10px">Document hash · ' + esc(r.terms_hash) + '</p>'
      ) +

      panel(
        '<h2>Ready?</h2>' +
        '<p class="muted" style="margin:-6px 0 16px">Next you enter your rate, the trucks you can commit, and sign for ' +
          esc(carrierLabel(r)) + '.</p>' +
        '<button class="btn btn-primary btn-block" id="go-bid" style="padding:16px;font-size:1.05rem">Reply with your rate</button>' +
        '<div style="margin-top:14px;text-align:center">' +
          '<button class="btn-link" id="decline-btn" type="button">Can\'t take this one — let Musanga know</button>' +
        '</div>'
      ) +

      mobileBar('Reply with your rate', 'go-bid-mobile', {
        summary: r.trucks_needed
          ? esc(r.trucks_needed) + ' trucks needed · ' + esc(r.tonnes_total) + ' t'
          : esc(r.tonnes_total || 0) + ' t on offer'
      })
    );
    el('#go-bid').addEventListener('click', function () { bidView(r); });
    var mobileGo = el('#go-bid-mobile');
    if (mobileGo) mobileGo.addEventListener('click', function () { bidView(r); });
    var decl = el('#decline-btn');
    if (decl) decl.addEventListener('click', declineRfp);
  }

  /* --- view: bid + sign ------------------------------------------------- */

  function bidView(r) {
    var curr = r.currency || 'ZMW';
    var symbol = curr === 'ZMW' ? 'K' : (curr === 'USD' ? '$' : curr);

    function trucksRows() {
      return state.trucks.map(function (t, i) {
        var idx = (i + 1) < 10 ? '0' + (i + 1) : String(i + 1);
        return '<div class="truck-row">' +
          '<div class="truck-idx">' + idx + '</div>' +
          '<input class="plate" data-truck="' + i + '" data-field="plate" value="' + esc(t.plate) + '" placeholder="Plate" autocapitalize="characters" autocomplete="off" spellcheck="false">' +
          '<input class="plate truck-col-hide" data-truck="' + i + '" data-field="trailer" value="' + esc(t.trailer) + '" placeholder="Trailer" autocapitalize="characters" autocomplete="off" spellcheck="false">' +
          '<input class="truck-col-hide" data-truck="' + i + '" data-field="driver" value="' + esc(t.driver) + '" placeholder="Driver" autocomplete="off">' +
          '<input class="truck-col-hide" data-truck="' + i + '" data-field="ready" type="date" value="' + esc(t.ready) + '">' +
        '</div>';
      }).join('');
    }

    function draw() {
      shell(
        askHeader(r) +

        // The rate is the whole point of the reply. It gets its own hero card
        // with a Wise-scale display number, and the total appears live on the
        // right so the transporter sees what they are committing to.
        '<section class="wise-hero-card">' +
          '<div class="wise-hero-label">Your rate per tonne</div>' +
          '<div class="wise-hero-input">' +
            '<span class="cur">' + esc(curr) + '</span>' +
            '<input id="f-rate" inputmode="decimal" placeholder="0" value="' + esc(state.form.rate || '') + '" autocomplete="off">' +
            '<span class="unit">/ t</span>' +
          '</div>' +
          '<div class="wise-hero-total">' +
            '<div>' +
              '<div class="lbl">Total if awarded</div>' +
              '<div class="figure"><span class="cur">' + esc(symbol) + '</span><span id="f-total">0</span></div>' +
            '</div>' +
            (r.target_rate
              ? '<div class="wise-hero-target"><div class="lbl">Musanga target</div><div class="figure-sm">' + esc(r.target_rate) + '/t</div></div>'
              : '') +
          '</div>' +
        '</section>' +

        panel(
          '<h2>Your capacity</h2>' +
          '<div class="grid-2">' +
            '<label class="field"><span>Tonnes you can move in the window</span>' +
              '<input class="input" id="f-cap" inputmode="numeric" placeholder="e.g. 1700" value="' + esc(state.form.cap || '') + '"></label>' +
            '<label class="field"><span>Trucks committed</span>' +
              '<input class="input" id="f-trucks" inputmode="numeric" placeholder="e.g. 10" value="' + esc(state.form.trucks || '') + '"></label>' +
          '</div>' +
          '<label class="field"><span>Vehicle type</span>' +
            '<input class="input" id="f-vehicle" placeholder="' + esc(r.equipment || 'e.g. 34t side tipper') + '" value="' + esc(state.form.vehicle || '') + '"></label>' +
          '<div class="grid-2">' +
            '<label class="field"><span>Earliest you can load</span>' +
              '<input class="input" id="f-from" type="date" value="' + esc(state.form.from || '') + '"></label>' +
            '<label class="field"><span>Latest you can load</span>' +
              '<input class="input" id="f-to" type="date" value="' + esc(state.form.to || '') + '"></label>' +
          '</div>' +
          '<p id="date-fit-warning" class="notice notice-error" style="display:none;margin:-4px 0 14px"></p>' +
          '<label class="field"><span>Note for Musanga <span class="muted" style="font-weight:400">(return loads, permits, quirks)</span></span>' +
            '<textarea class="input" id="f-notes" rows="2" placeholder="Anything Musanga should know when scoring your reply.">' + esc(state.form.notes || '') + '</textarea></label>'
        ) +

        panel(
          '<h2>Plates <span class="muted" style="font-weight:400">(optional)</span></h2>' +
          '<p class="muted" style="font-size:.88rem;margin:-6px 0 14px">Add them now if you have them, or once Musanga awards the load — the trucks count above is your bid either way.</p>' +
          '<div class="trucks-panel">' +
            '<div class="trucks-head">' +
              '<div>#</div><div>Registration plate</div><div>Trailer plate</div><div>Driver</div><div>Ready</div>' +
            '</div>' +
            '<div id="trucks">' + trucksRows() + '</div>' +
            '<div class="trucks-add">' +
              '<span class="trucks-hint" id="trucks-hint"></span>' +
              '<button type="button" id="add-truck">+ Add truck</button>' +
            '</div>' +
          '</div>'
        ) +

        panel(
          '<h2>Sign &amp; send</h2>' +
          '<p class="muted" style="font-size:.88rem;margin:-6px 0 16px">Your signature binds ' + esc(carrierLabel(r)) +
          ' to the rate and the trucks above. Musanga stamps the time, the IP and the terms hash on the record.</p>' +

          (r.invite.carrier_name ? '' :
            '<label class="field"><span>Company name</span>' +
              '<input class="input" id="f-carrier-name" required placeholder="Your transport company" value="' + esc(state.form.carrier_name || '') + '"></label>') +

          '<div class="grid-2">' +
            '<label class="field"><span>Full name</span>' +
              '<input class="input" id="f-signer-name" required autocomplete="name" placeholder="Authorised signatory" value="' + esc(state.form.signer_name || '') + '"></label>' +
            '<label class="field"><span>Title</span>' +
              '<input class="input" id="f-signer-title" placeholder="e.g. Director" value="' + esc(state.form.signer_title || '') + '"></label>' +
          '</div>' +
          '<label class="field"><span>Email</span>' +
            '<input class="input" id="f-signer-email" type="email" required autocomplete="email" placeholder="you@company.com" value="' + esc(state.form.signer_email || r.invite.carrier_email || '') + '"></label>' +

          '<span class="lbl" style="margin-top:8px">Signature</span>' +
          '<div class="sign-typed"><input id="f-sig" placeholder="Type your name to sign" value="' + esc(state.form.signer_name || '') + '"></div>' +
          '<div class="sign-stamp" id="sig-stamp"></div>' +

          '<div class="consent-list">' +
            '<label><input type="checkbox" id="f-consent-terms">' +
              '<span>I have read the terms above and agree to them on behalf of <strong>' + esc(carrierLabel(r)) + '</strong>.</span></label>' +
            '<label><input type="checkbox" id="f-consent-auth">' +
              '<span>I have authority to bind ' + esc(carrierLabel(r)) + ' to this reply, and our goods-in-transit and operator licences meet the requirement above.</span></label>' +
          '</div>' +

          '<button class="btn btn-primary btn-block" id="submit-bid" style="padding:16px;font-size:1.05rem">Sign &amp; send</button>' +
          '<div style="margin-top:12px;text-align:center">' +
            '<button class="btn-link" id="back-review" type="button">← Back to the ask</button>' +
          '</div>' +
          '<p id="bid-err" class="notice notice-error" style="display:none;margin-top:14px"></p>'
        ) +

        mobileBar('Sign &amp; send', 'submit-bid-mobile', {
          summary: '<span class="totals"><span>Your rate</span><b id="sig-bar-total">—</b></span>'
        })
      );

      wireBid(r);
    }
    draw();
  }

  function wireBid(r) {
    var rateEl = el('#f-rate'), capEl = el('#f-cap'), trucksEl = el('#f-trucks');
    var fromEl = el('#f-from'), toEl = el('#f-to');
    var totalEl = el('#f-total');
    var trucksBox = el('#trucks');
    var hint = el('#trucks-hint');
    var sigEl = el('#f-sig'), signerEl = el('#f-signer-name');
    var stamp = el('#sig-stamp');
    var mobileBtn = el('#submit-bid-mobile');
    var mobileBar = el('#sig-bar-total');
    var curr = r.currency || 'ZMW';

    function recalc() {
      var rate = Number(String(rateEl.value || '').replace(/[^0-9.\-]/g, '')) || 0;
      var cap = Number(String(capEl.value || '').replace(/[^0-9.\-]/g, '')) || 0;
      var trucks = Number(String(trucksEl.value || '').replace(/[^0-9.\-]/g, '')) || 0;
      var plates = state.trucks.filter(function (t) { return (t.plate || '').trim(); }).length;
      var total = rate * cap;
      totalEl.textContent = total > 0 ? fmtBig(total) : '0';
      // The plates panel is optional, so its hint only ever talks about
      // plates added, never "trucks committed" - that's the typed field.
      hint.textContent = plates
        ? plates + ' of ' + (trucks || plates) + ' plate' + (plates === 1 ? '' : 's') + ' added'
        : 'No plates added yet — that\'s fine, add them later.';
      if (mobileBar) {
        mobileBar.textContent = rate
          ? curr + ' ' + fmtNumber(rate) + '/t' + (trucks ? ' · ' + trucks + ' trucks' : '')
          : '—';
      }
    }

    function checkDateFit() {
      var warn = el('#date-fit-warning');
      if (!warn) return;
      var from = fromEl.value, to = toEl.value || from;
      var needFrom = r.loading_from, needTo = r.loading_to || r.loading_from;
      if (!from || !needFrom) { warn.style.display = 'none'; return; }
      var fits = from <= needTo && needFrom <= (toEl.value || from);
      if (fits) { warn.style.display = 'none'; return; }
      warn.textContent = 'Musanga needs this moving ' +
        [fmtDateStr(r.loading_from), fmtDateStr(r.loading_to)].filter(Boolean).join(' → ') +
        ' — your dates don\'t cover that. You can still send this if you think it\'s worth a conversation.';
      warn.style.display = '';
    }

    function stampSig() {
      var now = new Date();
      var date = now.toLocaleDateString(undefined, { day: '2-digit', month: 'short', year: 'numeric' });
      var time = now.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' });
      stamp.textContent = sigEl.value.trim()
        ? 'Typed · ' + date + ' · ' + time
        : 'Type your name above to sign.';
    }

    trucksBox.addEventListener('input', function (e) {
      var t = e.target;
      if (!t.dataset || t.dataset.truck === undefined) return;
      var idx = Number(t.dataset.truck);
      if (!state.trucks[idx]) state.trucks[idx] = { plate: '', trailer: '', driver: '', ready: '' };
      var val = t.value;
      if (t.dataset.field === 'plate' || t.dataset.field === 'trailer') val = val.toUpperCase();
      state.trucks[idx][t.dataset.field] = val;
      recalc();
    });
    el('#add-truck').addEventListener('click', function () {
      state.trucks.push({ plate: '', trailer: '', driver: '', ready: '' });
      var mount = el('#trucks');
      mount.innerHTML = state.trucks.map(function (t, i) {
        var idx = (i + 1) < 10 ? '0' + (i + 1) : String(i + 1);
        return '<div class="truck-row"><div class="truck-idx">' + idx + '</div>' +
          '<input class="plate" data-truck="' + i + '" data-field="plate" value="' + esc(t.plate) + '" placeholder="Plate" autocapitalize="characters" autocomplete="off" spellcheck="false">' +
          '<input class="plate truck-col-hide" data-truck="' + i + '" data-field="trailer" value="' + esc(t.trailer) + '" placeholder="Trailer" autocapitalize="characters" autocomplete="off" spellcheck="false">' +
          '<input class="truck-col-hide" data-truck="' + i + '" data-field="driver" value="' + esc(t.driver) + '" placeholder="Driver" autocomplete="off">' +
          '<input class="truck-col-hide" data-truck="' + i + '" data-field="ready" type="date" value="' + esc(t.ready) + '"></div>';
      }).join('');
      recalc();
    });

    [rateEl, capEl, trucksEl].forEach(function (n) { n.addEventListener('input', recalc); });
    [fromEl, toEl].forEach(function (n) { n.addEventListener('input', checkDateFit); });
    signerEl.addEventListener('input', function () {
      if (!sigEl.dataset.touched) sigEl.value = signerEl.value;
      stampSig();
    });
    sigEl.addEventListener('input', function () { sigEl.dataset.touched = '1'; stampSig(); });
    stampSig(); recalc(); checkDateFit();

    el('#back-review').addEventListener('click', function () {
      state.form = collect();
      reviewView(state.rfp);
    });
    var doSubmit = function () { submitBid(r); };
    el('#submit-bid').addEventListener('click', doSubmit);
    if (mobileBtn) mobileBtn.addEventListener('click', doSubmit);
  }

  function collect() {
    return {
      rate: el('#f-rate') ? el('#f-rate').value : '',
      cap: el('#f-cap') ? el('#f-cap').value : '',
      trucks: el('#f-trucks') ? el('#f-trucks').value : '',
      vehicle: el('#f-vehicle') ? el('#f-vehicle').value : '',
      from: el('#f-from') ? el('#f-from').value : '',
      to: el('#f-to') ? el('#f-to').value : '',
      notes: el('#f-notes') ? el('#f-notes').value : '',
      signer_name: el('#f-signer-name') ? el('#f-signer-name').value : '',
      signer_title: el('#f-signer-title') ? el('#f-signer-title').value : '',
      signer_email: el('#f-signer-email') ? el('#f-signer-email').value : '',
      carrier_name: el('#f-carrier-name') ? el('#f-carrier-name').value : '',
    };
  }

  function submitBid(r) {
    var f = collect();
    var err = el('#bid-err');
    err.style.display = 'none';

    var platesGiven = state.trucks.filter(function (t) { return (t.plate || '').trim(); });
    var payload = {
      rate_per_tonne: Number(String(f.rate).replace(/[^0-9.\-]/g, '')) || 0,
      capacity_tonnes: Number(String(f.cap).replace(/[^0-9.\-]/g, '')) || 0,
      // The typed trucks count is the bid; plates are optional proof that
      // can lag behind it, so they never override what was typed.
      trucks_offered: Number(String(f.trucks).replace(/[^0-9.\-]/g, '')) || platesGiven.length,
      trucks: platesGiven,
      vehicle_type: f.vehicle.trim(),
      available_from: f.from, available_to: f.to,
      notes: f.notes,
      signer_name: f.signer_name.trim(),
      signer_title: f.signer_title.trim(),
      signer_email: f.signer_email.trim(),
      carrier_name: f.carrier_name.trim(),
      consent_terms: el('#f-consent-terms').checked,
      consent_authority: el('#f-consent-auth').checked,
      view_token: viewToken,
    };

    if (!payload.rate_per_tonne) return void showErr(err, 'Enter your rate per tonne.');
    if (!payload.trucks_offered && !payload.capacity_tonnes) {
      return void showErr(err, 'State the trucks you\'re committing or the tonnes you can move.');
    }
    if (!r.invite.carrier_name && !payload.carrier_name) {
      return void showErr(err, 'Enter your company name.');
    }
    if (!payload.signer_name) return void showErr(err, 'Type your name to sign.');
    if (!payload.signer_email || payload.signer_email.indexOf('@') < 0) {
      return void showErr(err, 'Enter a real email address so Musanga can reach you about this bid.');
    }
    if (!payload.consent_terms || !payload.consent_authority) {
      return void showErr(err, 'Tick both boxes to confirm the terms and your authority.');
    }

    var btns = document.querySelectorAll('#submit-bid, #submit-bid-mobile');
    btns.forEach(function (b) { b.disabled = true; b.textContent = 'Sending…'; });

    api.post('/api/rfp/' + token + '/bid', payload).then(function (res) {
      state.rfp = res;
      state.trucks = []; state.form = {};
      window.scrollTo({ top: 0, behavior: 'smooth' });
      thanksView(res);
      // The signed PDF downloads on its own the moment the bid lands, same
      // motion as signing - "Download signed PDF" on the page is the redo,
      // not the only way to get it.
      var autoBtn = el('#download-pdf');
      if (autoBtn) downloadBidPdf(autoBtn);
    }).catch(function (e) {
      showErr(err, e.message);
      btns.forEach(function (b) { b.disabled = false; });
      var main = el('#submit-bid'); if (main) main.textContent = 'Sign & send';
      var mob = el('#submit-bid-mobile'); if (mob) mob.textContent = 'Sign & send';
    });
  }

  function showErr(box, msg) {
    box.textContent = msg; box.style.display = '';
    box.scrollIntoView({ behavior: 'smooth', block: 'center' });
  }

  /* --- view: thanks / already-replied ---------------------------------- */

  function thanksView(r) {
    var b = r.bid;
    var trucks = (b && b.trucks) || [];
    var platesList = trucks.length
      ? '<ul class="wise-plate-list">' + trucks.map(function (t, i) {
          var idx = (i + 1) < 10 ? '0' + (i + 1) : String(i + 1);
          var meta = [t.trailer, t.driver, t.ready ? 'ready ' + t.ready : ''].filter(Boolean).join(' · ');
          return '<li><span class="mono idx">' + esc(idx) + '</span>' +
            '<span class="mono">' + esc(t.plate) + '</span>' +
            (meta ? '<span class="muted">' + esc(meta) + '</span>' : '') + '</li>';
        }).join('') + '</ul>'
      : '';

    shell(
      '<section class="wise-thanks">' +
        '<div class="wise-thanks-check">✓</div>' +
        '<h1>Your rate is with Musanga.</h1>' +
        '<p class="wise-thanks-sub">If Musanga awards this to <b>' + esc(r.invite.carrier_name) + '</b> you\'ll get a rate confirmation per load through this same link.</p>' +
      '</section>' +

      (b ? panel(
        '<h2>What you sent</h2>' +
        '<div class="wise-recap">' +
          '<div><span class="lbl">Rate</span><b>' + esc(b.rate) + '<span class="unit"> / t</span></b></div>' +
          '<div><span class="lbl">Trucks</span><b>' + esc(b.trucks_offered) + '</b></div>' +
          '<div><span class="lbl">Tonnage</span><b>' + esc(b.capacity_tonnes) + '<span class="unit"> t</span></b></div>' +
        '</div>' +
        '<dl class="ask-list" style="margin-top:20px">' +
          askRow('Reference', r.ref + ' / ' + b.id, { mono: true }) +
          askRow('Vehicle type', b.vehicle_type || '—') +
          askRow('Available', [b.available_from, b.available_to].filter(Boolean).join(' → ')) +
          askRow('Signed by', (b.signer_name || '') + (b.signer_title ? ', ' + b.signer_title : '')) +
          askRow('Terms hash', (b.terms_hash || '').slice(0, 24) + '…', { mono: true }) +
        '</dl>' +
        (platesList ? '<div class="lbl" style="margin-top:20px">Plates on this reply</div>' + platesList : '') +
        '<button class="btn btn-primary btn-block" id="download-pdf" style="margin-top:20px">Download signed PDF</button>' +
        '<p id="download-err" class="notice notice-error" style="display:none;margin-top:12px"></p>'
      ) : '') +

      '<div style="text-align:center;margin-top:20px">' +
        '<a class="btn btn-ghost" href="/">Back to musanga.com</a>' +
      '</div>'
    );

    var dlBtn = el('#download-pdf');
    if (dlBtn) dlBtn.addEventListener('click', function () { downloadBidPdf(dlBtn); });
  }

  // Same base64-blob pattern the platform already uses for KYC documents -
  // the file is generated fresh from the current terms text, not a stored
  // URL anyone could guess or share on.
  function downloadBidPdf(btn) {
    var err = el('#download-err');
    if (err) err.style.display = 'none';
    btn.disabled = true;
    var original = btn.textContent;
    btn.textContent = 'Preparing…';
    api.get('/api/rfp/' + token + '/bid.pdf').then(function (doc) {
      var binary = atob(doc.content);
      var bytes = new Uint8Array(binary.length);
      for (var i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
      var url = URL.createObjectURL(new Blob([bytes], { type: doc.mime }));
      var a = document.createElement('a');
      a.href = url; a.download = doc.filename;
      document.body.appendChild(a); a.click(); document.body.removeChild(a);
      setTimeout(function () { URL.revokeObjectURL(url); }, 60000);
      btn.disabled = false; btn.textContent = original;
    }).catch(function (e) {
      btn.disabled = false; btn.textContent = original;
      if (err) { err.textContent = e.message; err.style.display = ''; }
    });
  }

  function declinedView(r) {
    shell(askHeader(r) + panel(
      '<h2>You let Musanga know you can\'t take this one</h2>' +
      '<p class="muted">If that was in error, reply to Musanga and we will reopen the invitation.</p>'));
  }

  function closedView(r) {
    shell(askHeader(r) + panel(
      '<h2>This request is ' + esc(r.status_label) + '</h2>' +
      '<p class="muted">Rates can no longer be sent from this link. Contact Musanga if you believe this is a mistake.</p>'));
  }

  /* --- mobile sticky action bar ---------------------------------------- */

  function mobileBar(cta, id, opts) {
    opts = opts || {};
    return '<div class="sign-bar sign-bar-summary">' +
      (opts.summary ? '<span class="totals">' + opts.summary + '</span>' : '') +
      '<button class="btn btn-primary" id="' + id + '">' + cta + '</button>' +
    '</div>';
  }

  /* --- decline --------------------------------------------------------- */

  function declineRfp() {
    var reason = prompt('Optional: tell Musanga why you can\'t take this one.', '') || '';
    api.post('/api/rfp/' + token + '/decline', { reason: reason }).then(load).catch(function (e) {
      alert(e.message);
    });
  }

  /* --- boot ------------------------------------------------------------ */

  function boot(res) {
    state.rfp = res;
    viewToken = res.view_token || null;
    if (viewToken) startHeartbeat();
    reviewView(res);
  }

  function load() {
    api.get('/api/rfp/' + token).then(boot).catch(function (e) {
      fatal(e.message);
    });
  }

  // The open link mints its own personal invite on first open, then swaps
  // the address bar to it - so a refresh or a bookmark goes straight back
  // to that same invite next time instead of minting a fresh one.
  function loadOpen() {
    api.get('/api/rfp/open/' + openToken).then(function (res) {
      token = res.personal_token;
      history.replaceState(null, '', '/rfp/' + token);
      boot(res);
    }).catch(function (e) {
      fatal(e.message);
    });
  }

  if (openToken) loadOpen();
  else if (token) load();
  else fatal('The link is missing its reference.');
})();
