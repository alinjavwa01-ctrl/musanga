/* The customer's quote page — DocuSign for freight, on Wise's shape.

   The customer arrives from an email with a token in the URL. No account,
   no session; the token is the credential. What they see is scoped to it.

   The flow is Review → Sign → Confirmation. The link is a binding contract:
   the customer reads short, plain terms grounded in this exact movement and
   adopts a signature — typed or drawn — before it is accepted. Payment is
   arranged off-platform on booking; this page never asks for money.

   Palette and layout are the Musanga bidder system: black brand, near-white
   ground, no blue, a Wise-scale rate hero and soft filled panels. */
(function () {
  'use strict';

  var M = window.M, api = M.api, esc = M.esc, el = M.el;
  var root = document.getElementById('root');
  var token = (location.pathname.split('/quote/')[1] || '').replace(/\/$/, '');
  var viewToken = null;   // set by the server on the first open
  var pingSeconds = 15;   // interval between heartbeats
  var pingTimer = null;
  var pingLastAt = 0;
  var mode = 'typed';     // how the customer adopts their signature: typed | drawn
  var pad = null;         // the drawing surface, set up lazily on first "Draw it"

  /* --- heartbeat (DocSend-style read tracking) --------------------------- */
  function heartbeat(force) {
    if (!viewToken) return;
    if (document.hidden && !force) return;
    var now = Date.now();
    var delta = pingLastAt ? Math.round((now - pingLastAt) / 1000) : pingSeconds;
    pingLastAt = now;
    api.pingQuote(token, { view_token: viewToken, seconds: delta }).catch(function () {});
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

  /* --- shells & small helpers -------------------------------------------- */
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
  function askRow(label, value, opts) {
    if (value === null || value === undefined || value === '') return '';
    var cls = opts && opts.mono ? ' class="mono"' : '';
    return '<div class="ask-row"><dt>' + esc(label) + '</dt><dd' + cls + '>' + esc(value) + '</dd></div>';
  }
  function partyName(q) { return q.counterparty || q.signer_name || 'the Customer'; }
  function isPackage(q) { return q.slot_count > 1; }
  function headlineTotal(q) { return isPackage(q) ? q.package_total : q.total; }

  function heldDays(q) {
    if (!q.expires_at) return null;
    return Math.max(0, Math.round((q.expires_at * 1000 - Date.now()) / 86400000));
  }
  function heldUntil(q) {
    if (!q.expires_at) return 'the date stated by Musanga';
    return new Date(q.expires_at * 1000).toLocaleDateString(undefined,
      { day: 'numeric', month: 'short', year: 'numeric' });
  }

  /* --- the rate hero (Wise-scale display number) ------------------------- */
  function rateHero(q) {
    var pkg = isPackage(q);
    var days = heldDays(q);
    var held = days === null ? '' :
      '<div class="wise-hero-target"><div class="lbl">Rate held</div>' +
        '<div class="figure-sm">' + (days > 0 ? days + ' day' + (days === 1 ? '' : 's') : 'today') + '</div></div>';
    var secondary = pkg
      ? '<div class="lbl">Per truck</div><div class="figure">' + esc(q.per_slot) + '</div>'
      : '<div class="lbl">Freight excl. VAT</div><div class="figure">' + esc(q.net) + '</div>';
    return '<section class="wise-hero-card">' +
        '<div class="wise-hero-label">' + (pkg ? esc(q.slot_count) + '-truck package · all-in' : 'All-in rate') + '</div>' +
        '<div class="quote-hero-figure">' + esc(headlineTotal(q)) + '</div>' +
        '<div class="wise-hero-total"><div>' + secondary + '</div>' + held + '</div>' +
      '</section>';
  }

  /* --- movement details -------------------------------------------------- */
  function movementPanel(q) {
    var transit = Math.round(q.eta_minutes / 60) + 'h transit';
    var dist = Math.round(q.distance_km) + ' km · ' + transit;
    var load = (pkg(q) ? esc(q.slot_count) + ' × ' : '') + esc(q.tonnes) + ' t · ' + esc(q.commodity_name);
    return panel(
      '<h2>The movement</h2>' +
      '<dl class="ask-list">' +
        askRow('Collection', q.pickup_address || q.from_name) +
        askRow('Delivery', q.dropoff_address || q.to_name) +
        askRow('Equipment', q.equipment_name) +
        askRow('Load', load) +
        (q.goods ? askRow('Goods', q.goods) : '') +
        askRow('Distance', dist) +
        askRow('Payment', q.payment_label || q.payment_method) +
        (q.vat_ngwee ? askRow('VAT (16%)', q.vat) : '') +
        askRow('Total', headlineTotal(q)) +
      '</dl>'
    );
  }
  function pkg(q) { return isPackage(q); }

  /* --- payment terms (cash-first: 100% upfront to reserve) --------------- */
  // A spot reservation is money-first: paying upfront is the whole action, so
  // the card leads with what is due and by when, and nothing sits in front of
  // it. Anything to line up (paperwork, collection) is framed as what happens
  // AFTER the trucks are held — we optimise for the reservation, not for a
  // checklist. Any pre-payment conditions ops set are shown as things we sort
  // together once reserved, not as a gate.
  function paymentPanel(q) {
    if (!q.require_payment) return '';
    var pkgq = pkg(q);
    var deadline = q.reserve_by
      ? new Date(q.reserve_by * 1000).toLocaleDateString(undefined, { day: 'numeric', month: 'long', year: 'numeric' })
      : null;
    var days = q.reserve_by ? Math.max(0, Math.ceil((q.reserve_by * 1000 - Date.now()) / 86400000)) : null;
    var conds = (q.conditions || []).filter(function (c) { return !c.met; }).map(function (c) {
      return '<li style="display:flex;gap:10px;align-items:baseline;padding:5px 0">' +
        '<span style="color:var(--text-soft)">·</span><span>' + esc(c.label) + '</span></li>';
    }).join('');
    return '<section class="wise-pay-card">' +
        '<div class="wise-pay-label">Payment to reserve</div>' +
        '<div class="wise-pay-single" style="display:flex;justify-content:space-between;align-items:baseline;gap:16px;flex-wrap:wrap">' +
          '<span>100% upfront</span><b style="font-variant-numeric:tabular-nums">' + esc(headlineTotal(q)) + '</b></div>' +
        '<div class="wise-pay-foot">' +
          (deadline
            ? 'Held first come, first paid. Get cleared funds in by <b>' + esc(deadline) + '</b>' +
              (days !== null && days > 0 ? ' — ' + days + ' day' + (days === 1 ? '' : 's') + ' away' : '') +
              ' and ' + (pkgq ? 'all ' + esc(q.slot_count) + ' trucks are yours' : 'the truck is yours') +
              '. After that the ' + (pkgq ? 'slots' : 'slot') + ' simply open back up.'
            : 'Held on a first-paid basis — the ' + (pkgq ? 'trucks are' : 'truck is') + ' yours once cleared funds are in.') +
        '</div>' +
        '<div class="wise-pay-next">' +
          '<span class="wise-pay-next-mark">→</span>' +
          '<span>Once you’re reserved, we take it from there. We line up ' +
          (conds ? 'the paperwork' : 'the paperwork and collection') +
          ' with you — nothing else to sort right now.' +
          (conds ? ' That includes:' : '') + '</span>' +
        '</div>' +
        (conds ? '<ul class="wise-pay-later">' + conds + '</ul>' : '') +
      '</section>';
  }

  /* --- attached document ------------------------------------------------- */
  function docPanel(q) {
    if (!q.document) return '';
    return panel(
      '<h2>Attached document</h2>' +
      '<div style="display:flex;justify-content:space-between;align-items:center;gap:12px;flex-wrap:wrap">' +
        '<div><div style="font-weight:600">📎 ' + esc(q.document.name) + '</div>' +
          '<div class="muted" style="font-size:.8rem">' + esc(Math.round(q.document.size / 1024)) + ' KB · ' + esc(q.document.mime) + '</div></div>' +
        '<button class="btn btn-ghost btn-sm" type="button" id="doc-open">Open document</button>' +
      '</div>'
    );
  }
  function openDocument() {
    api.quoteDownloaded(token, { view_token: viewToken }).catch(function () {});
    api.quoteDocument(token).then(function (d) {
      window.open('data:' + d.mime + ';base64,' + d.content, '_blank');
    }).catch(function (err) { alert(err.message); });
  }
  function wireDoc() {
    var b = el('#doc-open');
    if (b) b.addEventListener('click', openDocument);
  }

  /* --- shared header ----------------------------------------------------- */
  function askHeader(q) {
    return '<div class="wise-header">' +
      '<div class="wise-kicker">Musanga rate · ' + esc(q.ref) + '</div>' +
      '<h1>' + esc(q.from_name) + '<br><span class="wise-arrow">→</span> ' + esc(q.to_name) + '</h1>' +
      '<p class="wise-sub">' + (pkg(q) ? esc(q.slot_count) + ' trucks · ' : '') +
        esc(q.tonnes) + ' t · ' + esc(q.commodity_name) + '</p>' +
    '</div>';
  }

  /* --- the contract ------------------------------------------------------ */
  // Short, plain, numbered, and grounded in this movement. When ops adds a
  // note it becomes a real clause here rather than a floating box — it is part
  // of what the customer is agreeing to, so that is where it belongs.
  function clauses(q) {
    var scope = pkg(q)
      ? esc(q.slot_count) + ' identical loads of ' + esc(q.equipment_name)
      : esc(q.equipment_name) + ' carrying ' + esc(q.tonnes) + ' t of ' + esc(q.commodity_name);
    var list = [
      ['Who’s who',
        'This is between Musanga Logistics Limited (“Musanga”) and ' + esc(partyName(q)) +
        ' (“the Customer”). We’ll move the load described above — ' + scope +
        ' — along the ' + esc(q.from_name) + ' to ' + esc(q.to_name) + ' corridor, and you’re happy with the rate and these terms.'],
      ['The rate',
        'The ' + esc(headlineTotal(q)) + ' is the all-in price — no add-ons later. It’s locked once you sign and held until ' +
        esc(heldUntil(q)) + '; after that we’d just need to take a fresh look.'],
      ['Payment', q.require_payment
        ? 'To hold the trucks, the full ' + esc(headlineTotal(q)) + ' is paid upfront' +
          (q.reserve_by ? ', with cleared funds in by ' + esc(heldUntil({ expires_at: q.reserve_by })) : '') +
          '. Trucks go on a first-paid basis, so if the funds don’t clear in time the reservation simply opens back up. We roll once the payment lands.'
        : 'The rate is settled by ' + esc(q.payment_label || q.payment_method || 'the method you agree with us') +
          '. We confirm the booking first, and where payment is due upfront we get moving once cleared funds are in.'],
      ['Your load',
        'You’re confirming the goods, the weight, and the collection and delivery points above are right and fine to carry — that’s what we price and plan around.'],
      ['Cover',
        'The load runs under Musanga’s master services agreement and standard trading conditions — the same terms that set out our cover and liability on every movement.']
    ];
    if (q.note) list.push(['Additional terms', esc(q.note)]);
    list.push(['Signing',
      'By signing below you’re confirming you can sign for the Customer, that your typed name or drawn mark is your signature, and that this is a binding agreement between us under the laws of Zambia.']);
    return list;
  }

  function termsPanel(q) {
    var items = clauses(q).map(function (c, i) {
      return '<li class="quote-clause"><span class="quote-clause-n">' + (i + 1) + '</span>' +
        '<span><b>' + esc(c[0]) + '.</b> ' + c[1] + '</span></li>';
    }).join('');
    return panel(
      '<h2>What we’re agreeing</h2>' +
      '<p class="muted" style="font-size:.88rem;margin:-6px 0 16px">Short and in plain English — no fine print, no surprises. Here’s the whole of it.</p>' +
      '<ul class="quote-terms">' + items + '</ul>'
    );
  }

  /* --- signature mark (shown back on confirmation) ----------------------- */
  function signatureMark(q) {
    if (q.signature_type === 'drawn') {
      return '<div class="sign-mark"><img alt="Signature of ' + esc(q.signer_name || '') + '" src="' + esc(q.signature) + '"></div>';
    }
    return '<div class="sign-mark"><span class="typed">' + esc(q.signature || q.signer_name || '') + '</span></div>';
  }

  /* --- the drawing surface (shared shape with the signing room) ---------- */
  function setupPad() {
    var canvas = el('#pad');
    if (!canvas) return;
    var ratio = window.devicePixelRatio || 1;
    canvas.width = canvas.offsetWidth * ratio;
    canvas.height = canvas.offsetHeight * ratio;
    var c = canvas.getContext('2d');
    c.scale(ratio, ratio);
    c.lineWidth = 2.2;
    c.lineCap = c.lineJoin = 'round';
    c.strokeStyle = '#000';
    var drawing = false, dirty = false;
    function point(e) {
      var box = canvas.getBoundingClientRect();
      var t = e.touches ? e.touches[0] : e;
      return { x: t.clientX - box.left, y: t.clientY - box.top };
    }
    function start(e) { e.preventDefault(); drawing = true; dirty = true; var p = point(e); c.beginPath(); c.moveTo(p.x, p.y); }
    function move(e) { if (!drawing) return; e.preventDefault(); var p = point(e); c.lineTo(p.x, p.y); c.stroke(); }
    function stop() { drawing = false; }
    ['mousedown', 'touchstart'].forEach(function (n) { canvas.addEventListener(n, start, { passive: false }); });
    ['mousemove', 'touchmove'].forEach(function (n) { canvas.addEventListener(n, move, { passive: false }); });
    ['mouseup', 'mouseleave', 'touchend'].forEach(function (n) { canvas.addEventListener(n, stop); });
    el('#clear').addEventListener('click', function () { c.clearRect(0, 0, canvas.width, canvas.height); dirty = false; });
    pad = { canvas: canvas, isDirty: function () { return dirty; } };
  }

  /* --- views ------------------------------------------------------------- */

  function reviewView(q) {
    shell(
      askHeader(q) +
      rateHero(q) +
      paymentPanel(q) +
      movementPanel(q) +
      docPanel(q) +
      panel(
        '<button class="btn btn-primary btn-block" id="go" style="padding:16px;font-size:1.05rem">Have a look at the terms</button>' +
        '<p class="muted" style="text-align:center;font-size:.8rem;margin:14px 0 0">Short and in plain English. You’ll add your signature on the next step — no rush.</p>' +
        '<div id="err" style="margin-top:12px"></div>'
      )
    );
    wireDoc();
    el('#go').addEventListener('click', function () {
      var b = el('#go');
      b.disabled = true; b.textContent = 'One moment…';
      api.acceptQuote(token).then(signView).catch(function (err) {
        b.disabled = false; b.textContent = 'Have a look at the terms';
        el('#err').innerHTML = '<div class="notice notice-error">' + esc(err.message) + '</div>';
      });
    });
  }

  function signAction(q) {
    return q.require_payment ? 'Sign &amp; reserve the trucks' : 'Sign &amp; confirm';
  }

  function signView(q) {
    mode = 'typed'; pad = null;
    shell(
      askHeader(q) +
      termsPanel(q) +
      panel(
        '<h2>Happy to go ahead?</h2>' +
        '<p class="muted" style="font-size:.88rem;margin:-6px 0 16px">Just your name, an email for your copy, and a signature — that’s all we need. Take your time; nothing is set until you sign.</p>' +
        '<form id="sig-form">' +
          '<div class="grid-2">' +
            '<label class="field"><span>Your name</span>' +
              '<input class="input" id="signer_name" required autocomplete="name" placeholder="Who’s signing?" value="' + esc(q.counterparty || '') + '"></label>' +
            '<label class="field"><span>Your email</span>' +
              '<input class="input" id="signer_email" type="email" required autocomplete="email" placeholder="For your copy" value="' + esc(q.counterparty_email || '') + '"></label>' +
          '</div>' +
          '<span class="lbl" style="margin-top:8px">Your signature</span>' +
          '<div class="sig-tabs">' +
            '<button type="button" data-mode="typed" aria-pressed="true">Type it</button>' +
            '<button type="button" data-mode="drawn" aria-pressed="false">Draw it</button>' +
          '</div>' +
          '<div id="typed-wrap">' +
            '<div class="sign-typed"><input id="sig-typed" placeholder="Type your name" autocomplete="off"></div>' +
            '<div class="sign-stamp" id="sig-stamp"></div>' +
          '</div>' +
          '<div id="drawn-wrap" hidden>' +
            '<canvas id="pad"></canvas>' +
            '<div class="pad-hint"><span>Sign with a finger or a mouse</span>' +
              '<button type="button" class="btn btn-ghost btn-sm" id="clear">Clear</button></div>' +
          '</div>' +
          '<div class="consent-list">' +
            '<label><input type="checkbox" id="consent">' +
              '<span>I’ve read the terms and I’m happy to go ahead for <strong>' + esc(partyName(q)) +
              '</strong>. My name or mark above is my signature.</span></label>' +
          '</div>' +
          '<button class="btn btn-primary btn-block" type="submit" style="padding:16px;font-size:1.05rem">' + signAction(q) + '</button>' +
          '<div style="margin-top:12px;text-align:center">' +
            '<button class="btn-link" id="back" type="button">← Back to the rate</button>' +
          '</div>' +
          '<p id="err" class="notice notice-error" style="display:none;margin-top:14px"></p>' +
        '</form>'
      )
    );

    var form = el('#sig-form');
    var typed = el('#sig-typed');
    var stamp = el('#sig-stamp');
    if (q.counterparty) { typed.value = q.counterparty; stamp.textContent = q.counterparty; }

    el('.sig-tabs').addEventListener('click', function (e) {
      var btn = e.target.closest('[data-mode]');
      if (!btn) return;
      mode = btn.dataset.mode;
      M.els('.sig-tabs button').forEach(function (b) { b.setAttribute('aria-pressed', b === btn); });
      el('#typed-wrap').hidden = mode !== 'typed';
      el('#drawn-wrap').hidden = mode !== 'drawn';
      if (mode === 'drawn' && !pad) setupPad();
    });

    el('#signer_name').addEventListener('input', function () {
      if (mode === 'typed') { typed.value = this.value; stamp.textContent = this.value; }
    });
    typed.addEventListener('input', function () { stamp.textContent = this.value; });

    el('#back').addEventListener('click', function () { reviewView(q); });

    function showErr(msg) {
      var box = el('#err');
      box.style.display = 'block';
      box.textContent = msg;
    }

    form.addEventListener('submit', function (e) {
      e.preventDefault();
      if (!el('#consent').checked) return showErr('Just tick the box to confirm you’re happy, then you’re set.');
      var signature = mode === 'typed'
        ? (typed.value || el('#signer_name').value).trim()
        : (pad && pad.isDirty() ? pad.canvas.toDataURL('image/png') : '');
      if (!signature) return showErr(mode === 'typed' ? 'Pop your name in to sign.' : 'Add your signature to sign.');
      var btn = form.querySelector('button[type=submit]');
      btn.disabled = true; btn.textContent = 'One moment…';
      api.signQuote(token, {
        signer_name: el('#signer_name').value.trim(),
        signer_email: el('#signer_email').value.trim(),
        signature: signature,
        signature_type: mode,
        esign_consent: true,
        view_token: viewToken
      }).then(thanksView).catch(function (err) {
        btn.disabled = false; btn.innerHTML = signAction(q);
        showErr(err.message);
      });
    });
  }

  function thanksView(q) {
    var firstName = (q.signer_name || '').trim().split(/\s+/)[0];
    var reserved = q.require_payment;
    shell(
      '<section class="wise-thanks">' +
        '<div class="wise-thanks-check">✓</div>' +
        '<h1>' + (firstName ? 'Thanks, ' + esc(firstName) + ' — ' : 'Thank you — ') +
          (reserved ? 'your trucks are held.' : 'you’re all set.') + '</h1>' +
        '<p class="wise-thanks-sub">We’ve got it from here. Someone from Musanga will be in touch to line up ' +
          (reserved ? 'payment and collection' : 'collection') + '.' +
          (q.counterparty_phone ? ' We’ll text <b>' + esc(q.counterparty_phone) + '</b> to confirm.' : '') +
        '</p>' +
      '</section>' +
      panel(
        '<h2>What you agreed</h2>' +
        '<div class="lbl">Signature</div>' +
        signatureMark(q) +
        '<dl class="ask-list" style="margin-top:16px">' +
          askRow('Signed by', q.signer_name) +
          askRow('Email', q.signer_email) +
          (q.signed_at ? askRow('Signed', M.when(q.signed_at)) : '') +
          askRow('Reference', q.ref, { mono: true }) +
          (q.order_ref ? askRow('Load', q.order_ref, { mono: true }) : '') +
          askRow('Rate', headlineTotal(q)) +
        '</dl>'
      ) +
      '<div style="text-align:center;margin-top:20px">' +
        '<a class="btn btn-ghost" href="/">Back to musanga.com</a>' +
      '</div>'
    );
  }

  function render(q) {
    if (q.status === 'booked' || q.status === 'signed') return thanksView(q);
    if (q.status === 'accepted' && !q.signed_at) return signView(q);
    return reviewView(q);
  }

  if (!token) return fatal('Missing quote token.');
  api.publicQuote(token).then(function (q) {
    viewToken = q.view_token || null;
    if (viewToken) startHeartbeat();
    render(q);
  }).catch(function (err) {
    fatal(err.message || 'Unknown error opening this quote.');
  });
})();
