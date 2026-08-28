/* The signing room: one document, one signature, no account.

   Everything here is deliberately self-contained. The signer arrives from an
   email with a token in the URL and nothing else - no session, no password -
   so the page asks the API for exactly one document and shows exactly that. */
(function () {
  'use strict';

  var M = window.M, api = M.api, esc = M.esc, el = M.el;
  var root = document.getElementById('root');
  var token = (location.pathname.split('/sign/')[1] || '').replace(/\/$/, '');
  var pad = null, mode = 'typed', doc = null;

  function shell(inner) { root.innerHTML = '<div class="sign-wrap">' + inner + '</div>'; }

  function fatal(message) {
    shell('<div class="sign-panel" style="max-width:520px;margin:60px auto;text-align:center">' +
      '<h3>This link cannot be opened</h3><p>' + esc(message) + '</p>' +
      '<a class="btn btn-ghost btn-block" href="/">Go to musanga.com</a></div>');
  }

  /* --- rendering the document ------------------------------------------- */
  // The body is plain text on purpose: what is displayed has to be exactly
  // what was signed, so it is escaped first and only then given structure.
  function renderBody(text) {
    var blocks = esc(text).split(/\n\s*\n/);
    return blocks.map(function (block) {
      if (block.indexOf('## ') === 0) return '<h2>' + block.slice(3).trim() + '</h2>';
      if (/^\s{4}\S/.test(block)) return '<pre>' + block.replace(/^\n+/, '') + '</pre>';
      var clause = /^\d+\.\d+\s/.test(block.trim());
      return '<p' + (clause ? ' class="clause"' : '') + '>' + block.trim().replace(/\n\s*/g, ' ') + '</p>';
    }).join('');
  }

  function signatureMark(a) {
    if (!a.signed_at) return '<div class="sign-mark empty">Not yet signed</div>';
    return '<div class="sign-mark">' + (a.signature_type === 'drawn'
      ? '<img alt="Signature of ' + esc(a.signer_name) + '" src="' + esc(a.signature) + '">'
      : '<span class="typed">' + esc(a.signature) + '</span>') + '</div>';
  }

  function signatureBlock(a, company) {
    return '<div class="sign-block"><div class="parties">' +
      '<div class="party"><b>For ' + esc(company.name) + '</b>' +
        (a.countersigned_at
          ? '<div class="sign-mark"><span class="typed">' + esc(a.countersignature) + '</span></div>'
          : '<div class="sign-mark empty">Countersigned on receipt</div>') +
        '<div class="meta">' + esc(company.name) + '<br>' + esc(company.address) + '</div></div>' +
      '<div class="party"><b>For ' + esc(a.counterparty) + '</b>' +
        signatureMark(a) +
        '<div class="meta">' +
          (a.signed_at
            ? esc(a.signer_name) + (a.signer_title ? ', ' + esc(a.signer_title) : '') + '<br>' +
              esc(a.signer_email) + '<br>Signed ' + esc(M.when(a.signed_at))
            : esc(a.counterparty)) +
        '</div></div>' +
      '</div>' +
      '<p class="hash" style="margin-top:22px">Document ' + esc(a.ref) + ' · SHA-256 ' + esc(a.body_hash) + '</p>' +
      '</div>';
  }

  /* --- the signing panel ------------------------------------------------- */
  function signPanel(a) {
    if (a.status === 'signed') {
      return '<div class="sign-panel"><h3>Signed</h3>' +
        '<p>Signed by ' + esc(a.signer_name) + ' on ' + esc(M.when(a.signed_at)) + '. ' +
        'Keep a copy for your records.</p>' +
        '<button class="btn btn-primary btn-block" id="copy">Download a copy</button>' +
        '<button class="btn btn-ghost btn-block" style="margin-top:8px" id="print">Print</button></div>';
    }
    if (a.status === 'declined') {
      return '<div class="sign-panel"><h3>Declined</h3>' +
        '<p>This document was declined. Musanga has been notified and will be in touch.</p></div>';
    }
    return '<div class="sign-panel" id="sign-panel">' +
      '<h3>Sign this document</h3>' +
      '<p>Read it, then adopt your signature. It is legally binding once submitted.</p>' +
      '<div id="err"></div>' +
      '<form id="sign-form">' +
        '<label class="field"><span>Full name</span><input class="input" name="signer_name" required autocomplete="name"></label>' +
        '<div class="row2">' +
          '<label class="field"><span>Job title</span><input class="input" name="signer_title" placeholder="Director" autocomplete="organization-title"></label>' +
          '<label class="field"><span>Email</span><input class="input" name="signer_email" type="email" required autocomplete="email" value="' + esc(a.counterparty_email || '') + '"></label>' +
        '</div>' +
        '<div class="sig-tabs">' +
          '<button type="button" data-mode="typed" aria-pressed="true">Type it</button>' +
          '<button type="button" data-mode="drawn" aria-pressed="false">Draw it</button>' +
        '</div>' +
        '<div id="typed-wrap"><div class="typed-preview" id="typed-preview"></div></div>' +
        '<div id="drawn-wrap" hidden>' +
          '<canvas id="pad"></canvas>' +
          '<div class="pad-hint"><span>Sign with a finger or a mouse</span>' +
            '<button type="button" class="btn btn-ghost btn-sm" id="clear">Clear</button></div>' +
        '</div>' +
        '<label class="consent"><input type="checkbox" name="consent">' +
          '<span>I have read this document, I am authorised to sign it for ' + esc(a.counterparty) +
          ', and I adopt the signature above as my electronic signature.</span></label>' +
        '<button class="btn btn-primary btn-block" type="submit">Sign and return</button>' +
        '<button class="btn btn-ghost btn-block" style="margin-top:8px" type="button" id="decline">Decline to sign</button>' +
      '</form></div>';
  }

  function auditPanel(events) {
    if (!events.length) return '';
    return '<div class="sign-panel"><h3>Audit trail</h3><ul class="audit">' +
      events.map(function (e) {
        return '<li><b>' + esc(e.label) + '</b><span>' + esc(M.when(e.created_at)) + '</span></li>';
      }).join('') + '</ul></div>';
  }

  /* --- drawing ----------------------------------------------------------- */
  function setupPad() {
    var canvas = el('#pad');
    if (!canvas) return;
    var ratio = window.devicePixelRatio || 1;
    canvas.width = canvas.offsetWidth * ratio;
    canvas.height = canvas.offsetHeight * ratio;
    var ctx = canvas.getContext('2d');
    ctx.scale(ratio, ratio);
    ctx.lineWidth = 2.2;
    ctx.lineCap = ctx.lineJoin = 'round';
    ctx.strokeStyle = '#000';
    var drawing = false, dirty = false;

    function point(e) {
      var box = canvas.getBoundingClientRect();
      var touch = e.touches ? e.touches[0] : e;
      return { x: touch.clientX - box.left, y: touch.clientY - box.top };
    }
    function start(e) { e.preventDefault(); drawing = true; dirty = true; var p = point(e); ctx.beginPath(); ctx.moveTo(p.x, p.y); }
    function move(e) { if (!drawing) return; e.preventDefault(); var p = point(e); ctx.lineTo(p.x, p.y); ctx.stroke(); }
    function stop() { drawing = false; }

    ['mousedown', 'touchstart'].forEach(function (n) { canvas.addEventListener(n, start, { passive: false }); });
    ['mousemove', 'touchmove'].forEach(function (n) { canvas.addEventListener(n, move, { passive: false }); });
    ['mouseup', 'mouseleave', 'touchend'].forEach(function (n) { canvas.addEventListener(n, stop); });

    el('#clear').addEventListener('click', function () {
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      dirty = false;
    });

    pad = { canvas: canvas, isDirty: function () { return dirty; } };
  }

  /* --- the page ---------------------------------------------------------- */
  function draw(data) {
    doc = data;
    var a = data.agreement;

    shell(
      '<div class="sign-head">' +
        '<div><h1>' + esc(a.title) + '</h1>' +
          '<p>' + esc(data.company.name) + ' and ' + esc(a.counterparty) +
          ' · ' + esc(a.ref) + ' · ' + esc(a.status_label) + '</p></div>' +
        '<div class="spacer"></div>' +
      '</div>' +
      '<div class="sign-grid">' +
        '<article class="paper" id="paper">' + renderBody(a.body) + signatureBlock(a, data.company) + '</article>' +
        '<aside>' + signPanel(a) + auditPanel(data.events) + '</aside>' +
      '</div>' +
      // On a phone the document comes first and the signing panel sits under
      // it, so this bar is the way back down to it - and the only thing on the
      // page that follows the thumb.
      (a.status === 'signed' || a.status === 'declined' ? '' :
        '<div class="sign-bar"><span>' + esc(a.title) + '</span>' +
        '<a class="btn btn-primary btn-sm" href="#sign-panel">Sign</a></div>')
    );

    bind(a);
  }

  function bind(a) {
    var copy = el('#copy'); if (copy) copy.addEventListener('click', downloadCopy);
    var print = el('#print'); if (print) print.addEventListener('click', function () { window.print(); });

    var form = el('#sign-form');
    if (!form) return;

    var tabs = el('.sig-tabs');
    tabs.addEventListener('click', function (e) {
      var btn = e.target.closest('[data-mode]');
      if (!btn) return;
      mode = btn.dataset.mode;
      M.els('.sig-tabs button').forEach(function (b) { b.setAttribute('aria-pressed', b === btn); });
      el('#typed-wrap').hidden = mode !== 'typed';
      el('#drawn-wrap').hidden = mode !== 'drawn';
      if (mode === 'drawn' && !pad) setupPad();
    });

    form.signer_name.addEventListener('input', function () {
      el('#typed-preview').textContent = form.signer_name.value;
    });

    el('#decline').addEventListener('click', function () {
      var reason = prompt('Tell Musanga why you are declining. This is recorded against the document.');
      if (!reason) return;
      api.post('/api/sign/' + token + '/decline', { reason: reason, signer_name: form.signer_name.value })
        .then(load).catch(showError);
    });

    form.addEventListener('submit', function (e) {
      e.preventDefault();
      var signature = mode === 'typed' ? form.signer_name.value.trim()
                                       : (pad && pad.isDirty() ? pad.canvas.toDataURL('image/png') : '');
      if (!signature) return showError(new Error(mode === 'typed' ? 'Type your name' : 'Draw your signature'));

      var btn = form.querySelector('button[type=submit]');
      btn.disabled = true; btn.textContent = 'Signing…';
      api.post('/api/sign/' + token, {
        signer_name: form.signer_name.value.trim(),
        signer_title: form.signer_title.value.trim(),
        signer_email: form.signer_email.value.trim(),
        signature: signature, signature_type: mode,
        consent: form.consent.checked
      }).then(function (data) {
        draw(data);
        window.scrollTo({ top: 0, behavior: 'smooth' });
      }).catch(function (err) {
        btn.disabled = false; btn.textContent = 'Sign and return';
        showError(err);
      });
    });
  }

  function showError(err) {
    var box = el('#err');
    if (!box) return alert(err.message);
    box.innerHTML = '<div class="notice notice-error">' + esc(err.message) + '</div>';
  }

  // The copy is the document, the signature block and the certificate of
  // completion in one self-contained HTML file - openable and printable
  // anywhere, with no dependency on this site still being up.
  function downloadCopy() {
    var a = doc.agreement;
    var html = '<!doctype html><html><head><meta charset="utf-8"><title>' + esc(a.title) + ' — ' + esc(a.ref) +
      '</title><style>body{font:14px/1.65 Helvetica,Arial,sans-serif;max-width:760px;margin:40px auto;padding:0 20px;color:#000}' +
      'h2{font-size:1rem;margin:26px 0 10px}pre{background:#f2f2f2;padding:12px;overflow-x:auto;font-size:.82rem}' +
      '.mark{border-bottom:1px solid #000;min-height:60px;margin:8px 0}.typed{font-family:cursive;font-size:1.6rem}' +
      '.meta{font-size:.78rem;color:#404040}hr{border:0;border-top:2px solid #000;margin:32px 0}</style></head><body>' +
      '<h1>' + esc(a.title) + '</h1>' + renderBody(a.body) + '<hr>' +
      '<div class="mark">' + (a.signature_type === 'drawn'
        ? '<img style="max-height:58px" src="' + esc(a.signature) + '">'
        : '<span class="typed">' + esc(a.signature || '') + '</span>') + '</div>' +
      '<p class="meta">' + esc(a.signer_name || '') + (a.signer_title ? ', ' + esc(a.signer_title) : '') +
      '<br>' + esc(a.signer_email || '') + '<br>Signed ' + esc(a.signed_at ? M.when(a.signed_at) : '') + '</p>' +
      '<pre>' + esc(doc.certificate || '') + '</pre></body></html>';

    var url = URL.createObjectURL(new Blob([html], { type: 'text/html' }));
    var link = document.createElement('a');
    link.href = url;
    link.download = a.ref + '-' + a.kind + '.html';
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    setTimeout(function () { URL.revokeObjectURL(url); }, 30000);
    api.post('/api/sign/' + token + '/downloaded', {}).catch(function () {});
  }

  function load() {
    return api.get('/api/sign/' + token).then(draw).catch(function (err) { fatal(err.message); });
  }

  if (!token) fatal('This address is missing its document token.');
  else load();
})();
