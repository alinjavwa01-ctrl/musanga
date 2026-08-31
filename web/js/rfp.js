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
  var token = (location.pathname.split('/rfp/')[1] || '').replace(/\/$/, '');
  var state = { rfp: null, trucks: [], form: {} };

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

  function paymentHero(r) {
    // Break "33% on loading, 33% on delivery, 34% on POD received" into a
    // milestone strip so each payment point reads on its own. If we can't
    // split it cleanly we render the sentence as-is: some terms don't fit
    // the milestone shape (e.g. "Net 30 from POD received").
    var parts = String(r.payment_terms).split(/\s*,\s*/);
    var milestones = parts.map(function (p) {
      var m = p.match(/^(\d+%)\s+(.*)$/);
      return m ? { pct: m[1], when: m[2] } : null;
    }).filter(Boolean);
    var body;
    if (milestones.length >= 2) {
      body = '<div class="wise-pay-strip">' + milestones.map(function (m) {
        return '<div class="wise-pay-step">' +
          '<div class="pct">' + esc(m.pct) + '</div>' +
          '<div class="when">' + esc(m.when) + '</div>' +
        '</div>';
      }).join('<div class="wise-pay-sep">→</div>') + '</div>';
    } else {
      body = '<div class="wise-pay-single">' + esc(r.payment_terms) + '</div>';
    }
    return '<section class="wise-pay-card">' +
      '<div class="wise-pay-label">You get paid</div>' + body +
      '<div class="wise-pay-foot">Same schedule for every load Musanga awards you in this window.</div>' +
    '</section>';
  }

  function askHeader(r) {
    var trucksNeeded = r.trucks_needed ? esc(r.trucks_needed) + ' trucks · ' : '';
    return '<div class="wise-header">' +
      '<div class="wise-kicker">' + esc(r.company.name) + ' · ' + esc(r.ref) + '</div>' +
      '<h1>' + esc(r.from_place) + '<br><span class="wise-arrow">→</span> ' + esc(r.to_place) + '</h1>' +
      '<p class="wise-sub">' + trucksNeeded + esc(r.tonnes_total || 0) + ' t · ' + esc(r.commodity) + '</p>' +
      '<p class="muted" style="margin-top:12px;font-size:.9rem">For <b>' + esc(r.invite.carrier_name) + '</b> · Reply by ' + esc(fmtDate(r.closes_at)) + '</p>' +
    '</div>';
  }

  /* --- view: review ----------------------------------------------------- */

  function reviewView(r) {
    if (r.status !== 'open') return closedView(r);
    if (r.invite.status === 'declined') return declinedView(r);
    if (r.bid) return thanksView(r);

    shell(
      askHeader(r) +

      // Payment terms as a dedicated hero. A transporter's whole rate depends
      // on when they get paid, so the settlement schedule reads before the ask
      // does - and reads plainly, not buried in the terms body.
      (r.payment_terms ? paymentHero(r) : '') +

      panel(
        '<h2>What Musanga is moving</h2>' +
        '<dl class="ask-list">' +
          askRow('Loading point', r.from_place) +
          askRow('Discharge point', r.to_place) +
          askRow('Commodity', r.commodity) +
          askRow('Equipment', r.equipment) +
          askRow('Tonnage on offer', r.tonnes_total ? (r.tonnes_total + ' t') : '—') +
          askRow('Trucks needed', r.trucks_needed || '—') +
          askRow('Loading window', [r.loading_from, r.loading_to].filter(Boolean).join(' → ')) +
          askRow('Cover required per load', r.cover_min || '—') +
          askRow('Reply by', fmtDate(r.closes_at)) +
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
          esc(r.invite.carrier_name) + '.</p>' +
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
    var needed = Number(r.trucks_needed || 0);
    if (!state.trucks.length) {
      var seed = Math.max(1, Math.min(needed || 4, 12));
      for (var i = 0; i < seed; i++) state.trucks.push({ plate: '', trailer: '', driver: '', ready: '' });
    }

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
            '<label class="field"><span>Trucks committed <span class="muted" style="font-weight:400">(from plates)</span></span>' +
              '<input class="input" id="f-trucks-display" value="0" readonly></label>' +
          '</div>' +
          '<div class="grid-2">' +
            '<label class="field"><span>Earliest you can load</span>' +
              '<input class="input" id="f-from" type="date" value="' + esc(state.form.from || '') + '"></label>' +
            '<label class="field"><span>Latest you can load</span>' +
              '<input class="input" id="f-to" type="date" value="' + esc(state.form.to || '') + '"></label>' +
          '</div>' +
          '<label class="field"><span>Note for Musanga <span class="muted" style="font-weight:400">(return loads, permits, quirks)</span></span>' +
            '<textarea class="input" id="f-notes" rows="2" placeholder="Anything Musanga should know when scoring your reply.">' + esc(state.form.notes || '') + '</textarea></label>'
        ) +

        panel(
          '<h2>Your trucks &amp; plates</h2>' +
          '<p class="muted" style="font-size:.88rem;margin:-6px 0 14px">Plates lock the units for the window — Musanga cross-checks against the operator licence on file.</p>' +
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
          '<p class="muted" style="font-size:.88rem;margin:-6px 0 16px">Your signature binds ' + esc(r.invite.carrier_name) +
          ' to the rate and the trucks above. Musanga stamps the time, the IP and the terms hash on the record.</p>' +

          '<div class="grid-2">' +
            '<label class="field"><span>Full name</span>' +
              '<input class="input" id="f-signer-name" required autocomplete="name" placeholder="Authorised signatory" value="' + esc(state.form.signer_name || '') + '"></label>' +
            '<label class="field"><span>Title</span>' +
              '<input class="input" id="f-signer-title" placeholder="e.g. Director" value="' + esc(state.form.signer_title || '') + '"></label>' +
          '</div>' +
          '<label class="field"><span>Email</span>' +
            '<input class="input" id="f-signer-email" type="email" autocomplete="email" placeholder="you@company.com" value="' + esc(state.form.signer_email || r.invite.carrier_email || '') + '"></label>' +

          '<span class="lbl" style="margin-top:8px">Signature</span>' +
          '<div class="sign-typed"><input id="f-sig" placeholder="Type your name to sign" value="' + esc(state.form.signer_name || '') + '"></div>' +
          '<div class="sign-stamp" id="sig-stamp"></div>' +

          '<div class="consent-list">' +
            '<label><input type="checkbox" id="f-consent-terms">' +
              '<span>I have read the terms above and agree to them on behalf of <strong>' + esc(r.invite.carrier_name) + '</strong>.</span></label>' +
            '<label><input type="checkbox" id="f-consent-auth">' +
              '<span>I have authority to bind ' + esc(r.invite.carrier_name) + ' to this reply, and our goods-in-transit and operator licences meet the requirement above.</span></label>' +
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
    var rateEl = el('#f-rate'), capEl = el('#f-cap');
    var trucksDisp = el('#f-trucks-display');
    var totalEl = el('#f-total');
    var trucksBox = el('#trucks');
    var hint = el('#trucks-hint');
    var sigEl = el('#f-sig'), signerEl = el('#f-signer-name');
    var stamp = el('#sig-stamp');
    var mobileBtn = el('#submit-bid-mobile');
    var mobileBar = el('#sig-bar-total');
    var needed = Number(r.trucks_needed || 0);
    var tonnesAsk = Number(r.tonnes_total || 0);
    var curr = r.currency || 'ZMW';

    function recalc() {
      var rate = Number(String(rateEl.value || '').replace(/[^0-9.\-]/g, '')) || 0;
      var cap = Number(String(capEl.value || '').replace(/[^0-9.\-]/g, '')) || 0;
      var count = state.trucks.filter(function (t) { return (t.plate || '').trim(); }).length;
      trucksDisp.value = count;
      var total = rate * cap;
      totalEl.textContent = total > 0 ? fmtBig(total) : '0';
      if (needed) {
        var pctT = tonnesAsk ? Math.round(100 * cap / tonnesAsk) : 0;
        hint.textContent = count + ' of ' + needed + ' trucks · '
          + (cap ? (cap + ' t of ' + tonnesAsk + ' t (' + pctT + '%)') : ('need ' + tonnesAsk + ' t'));
      } else {
        hint.textContent = count + ' truck' + (count === 1 ? '' : 's') + ' committed';
      }
      if (mobileBar) {
        mobileBar.textContent = rate
          ? curr + ' ' + fmtNumber(rate) + '/t · ' + count + ' trucks'
          : '—';
      }
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

    [rateEl, capEl].forEach(function (n) { n.addEventListener('input', recalc); });
    signerEl.addEventListener('input', function () {
      if (!sigEl.dataset.touched) sigEl.value = signerEl.value;
      stampSig();
    });
    sigEl.addEventListener('input', function () { sigEl.dataset.touched = '1'; stampSig(); });
    stampSig(); recalc();

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
      from: el('#f-from') ? el('#f-from').value : '',
      to: el('#f-to') ? el('#f-to').value : '',
      notes: el('#f-notes') ? el('#f-notes').value : '',
      signer_name: el('#f-signer-name') ? el('#f-signer-name').value : '',
      signer_title: el('#f-signer-title') ? el('#f-signer-title').value : '',
      signer_email: el('#f-signer-email') ? el('#f-signer-email').value : '',
    };
  }

  function submitBid(r) {
    var f = collect();
    var err = el('#bid-err');
    err.style.display = 'none';

    var payload = {
      rate_per_tonne: Number(String(f.rate).replace(/[^0-9.\-]/g, '')) || 0,
      capacity_tonnes: Number(String(f.cap).replace(/[^0-9.\-]/g, '')) || 0,
      trucks: state.trucks.filter(function (t) { return (t.plate || '').trim(); }),
      trucks_offered: state.trucks.filter(function (t) { return (t.plate || '').trim(); }).length,
      available_from: f.from, available_to: f.to,
      notes: f.notes,
      signer_name: f.signer_name.trim(),
      signer_title: f.signer_title.trim(),
      signer_email: f.signer_email.trim(),
      consent_terms: el('#f-consent-terms').checked,
      consent_authority: el('#f-consent-auth').checked,
    };

    if (!payload.rate_per_tonne) return void showErr(err, 'Enter your rate per tonne.');
    if (!payload.trucks.length && !payload.capacity_tonnes) {
      return void showErr(err, 'Add at least one truck plate or state the tonnes you can move.');
    }
    if (!payload.signer_name) return void showErr(err, 'Type your name to sign.');
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
          askRow('Available', [b.available_from, b.available_to].filter(Boolean).join(' → ')) +
          askRow('Signed by', (b.signer_name || '') + (b.signer_title ? ', ' + b.signer_title : '')) +
          askRow('Terms hash', (b.terms_hash || '').slice(0, 24) + '…', { mono: true }) +
        '</dl>' +
        (platesList ? '<div class="lbl" style="margin-top:20px">Plates on this reply</div>' + platesList : '')
      ) : '') +

      '<div style="text-align:center;margin-top:20px">' +
        '<a class="btn btn-ghost" href="/">Back to musanga.com</a>' +
      '</div>'
    );
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

  function load() {
    api.get('/api/rfp/' + token).then(function (res) {
      state.rfp = res;
      reviewView(res);
    }).catch(function (e) {
      fatal(e.message);
    });
  }

  if (!token) return fatal('The link is missing its reference.');
  load();
})();
