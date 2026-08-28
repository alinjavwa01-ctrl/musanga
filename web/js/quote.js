/* The customer's quote page — DocuSign, for freight.

   The customer arrives from an email with a token in the URL. No account,
   no session; the token is the credential. What they see is scoped to it.

   The flow is simple: Review → Sign → Confirmation. Payment is arranged
   off-platform on booking; this page never asks for money or renders
   account numbers, so nothing here can go stale before Musanga is ready. */
(function () {
  'use strict';

  var M = window.M, api = M.api, esc = M.esc, el = M.el;
  var root = document.getElementById('root');
  var token = (location.pathname.split('/quote/')[1] || '').replace(/\/$/, '');

  function shell(inner) { root.innerHTML = '<div class="sign-wrap">' + inner + '</div>'; }

  function fatal(msg) {
    shell('<div class="sign-panel" style="max-width:520px;margin:60px auto;text-align:center">' +
      '<h3>This link cannot be opened</h3><p>' + esc(msg) + '</p>' +
      '<a class="btn btn-ghost btn-block" href="/">Go to musanga.com</a></div>');
  }

  function panel(inner) {
    return '<div class="sign-panel" style="max-width:640px;margin:40px auto;padding:32px">' + inner + '</div>';
  }

  function quoteHeader(q) {
    return '<div style="text-align:center;margin-bottom:20px">' +
        '<div class="muted" style="font-size:.8rem;letter-spacing:.14em;text-transform:uppercase;margin-bottom:6px">Musanga rate ' + esc(q.ref) + '</div>' +
        '<h1 style="margin:0 0 6px;font-size:1.8rem">' + esc(q.from_name) + ' &rarr; ' + esc(q.to_name) + '</h1>' +
        '<div style="font-size:2.6rem;font-weight:700;letter-spacing:-.02em">' + esc(q.total) + '</div>' +
        '<div class="muted" style="margin-top:6px">' + esc(q.equipment_name) + ' &middot; ' + esc(q.tonnes) + ' t &middot; ' + esc(q.commodity_name) + '</div>' +
      '</div>';
  }

  function metaLine(q) {
    var bits = [
      Math.round(q.distance_km) + ' km',
      Math.round(q.eta_minutes / 60) + 'h transit'
    ];
    if (q.expires_at) {
      var days = Math.max(0, Math.round((q.expires_at * 1000 - Date.now()) / 86400000));
      bits.push('Rate held ' + days + ' more day' + (days === 1 ? '' : 's'));
    }
    return '<div class="muted" style="display:flex;flex-wrap:wrap;gap:6px 14px;justify-content:center;font-size:.85rem;margin-bottom:24px">' +
      bits.map(function (b) { return '<span>' + esc(b) + '</span>'; }).join('') + '</div>';
  }

  function docBlock(q) {
    if (!q.document) return '';
    return '<div style="border:1px dashed var(--ink-100);border-radius:12px;padding:16px 18px;margin:0 0 20px;display:flex;justify-content:space-between;align-items:center;gap:12px;flex-wrap:wrap">' +
        '<div>' +
          '<div style="font-weight:600">📎 ' + esc(q.document.name) + '</div>' +
          '<div class="muted" style="font-size:.8rem">' + esc(Math.round(q.document.size / 1024)) + ' KB · ' + esc(q.document.mime) + '</div>' +
        '</div>' +
        '<button class="btn btn-ghost btn-sm" type="button" id="doc-open">Open document</button>' +
      '</div>';
  }

  function totalsBlock(q) {
    return '<div style="border-top:1px solid var(--ink-100);padding-top:18px;margin-top:6px;margin-bottom:20px">' +
      '<div style="display:flex;justify-content:space-between;margin-bottom:6px"><span class="muted">Freight</span><b>' + esc(q.net) + '</b></div>' +
      (q.vat_ngwee ? '<div style="display:flex;justify-content:space-between;margin-bottom:6px"><span class="muted">VAT 16%</span><b>' + esc(q.vat) + '</b></div>' : '') +
      '<div style="display:flex;justify-content:space-between;margin-top:8px;font-size:1.1rem"><span>Total</span><b>' + esc(q.total) + '</b></div>' +
    '</div>';
  }

  function noteBlock(q) {
    return q.note ? '<div class="notice" style="margin-bottom:20px"><b>Note from Musanga</b><br>' + esc(q.note) + '</div>' : '';
  }

  function openDocument() {
    api.quoteDocument(token).then(function (d) {
      // The mailer keeps the content in-DB as base64; a data: URL renders it
      // without a second network hop and needs no download attribute.
      var uri = 'data:' + d.mime + ';base64,' + d.content;
      window.open(uri, '_blank');
    }).catch(function (err) { alert(err.message); });
  }

  function wireDoc() {
    var b = el('#doc-open');
    if (b) b.addEventListener('click', openDocument);
  }

  /* --- views ------------------------------------------------------------ */

  function reviewView(q) {
    shell(panel(
      quoteHeader(q) + metaLine(q) +
      (q.goods ? '<p class="muted" style="text-align:center;margin:0 0 20px">' + esc(q.goods) + '</p>' : '') +
      docBlock(q) + totalsBlock(q) + noteBlock(q) +
      '<div id="err"></div>' +
      '<button class="btn btn-primary btn-block" id="go" style="padding:14px">Review &amp; sign</button>' +
      '<p class="muted" style="text-align:center;font-size:.78rem;margin-top:14px">' +
        'Your typed signature is legally binding under the Musanga master services agreement.</p>'
    ));
    wireDoc();
    el('#go').addEventListener('click', function () {
      var b = el('#go');
      b.disabled = true; b.textContent = '…';
      api.acceptQuote(token).then(function (q2) { signView(q2); }).catch(function (err) {
        b.disabled = false; b.textContent = 'Review & sign';
        el('#err').innerHTML = '<div class="notice notice-error">' + esc(err.message) + '</div>';
      });
    });
  }

  function signView(q) {
    shell(panel(
      quoteHeader(q) + metaLine(q) +
      docBlock(q) + totalsBlock(q) + noteBlock(q) +
      '<h3 style="margin:6px 0 12px">Sign this rate</h3>' +
      '<form id="sig-form">' +
        '<label class="field"><span>Full name</span><input class="input" name="signer_name" required value="' + esc(q.counterparty || '') + '"></label>' +
        '<label class="field"><span>Email</span><input class="input" type="email" name="signer_email" required value="' + esc(q.counterparty_email || '') + '"></label>' +
        '<label class="field"><span>Type your name as your signature</span>' +
          '<input class="input" name="signature" required style="font-family:Georgia,serif;font-style:italic;font-size:1.4rem" placeholder="Your name, signed"></label>' +
        '<div id="err"></div>' +
        '<label style="display:block;font-size:.8rem;color:var(--ink-500);margin:14px 0"><input type="checkbox" id="agree" checked> ' +
          'I agree that my typed name is my electronic signature and that this signature is binding.</label>' +
        '<button class="btn btn-primary btn-block" type="submit" style="padding:14px">Sign &amp; send</button>' +
      '</form>'
    ));
    wireDoc();
    var form = el('#sig-form');
    form.signer_name.addEventListener('input', function () {
      if (!form.signature.value) form.signature.value = form.signer_name.value;
    });
    if (form.signer_name.value && !form.signature.value) form.signature.value = form.signer_name.value;
    form.addEventListener('submit', function (e) {
      e.preventDefault();
      if (!el('#agree').checked) return void (el('#err').innerHTML = '<div class="notice notice-error">Confirm the agreement before signing.</div>');
      var btn = form.querySelector('button[type=submit]');
      btn.disabled = true; btn.textContent = 'Signing…';
      api.signQuote(token, {
        signer_name: form.signer_name.value.trim(),
        signer_email: form.signer_email.value.trim(),
        signature: form.signature.value.trim()
      }).then(thanksView).catch(function (err) {
        btn.disabled = false; btn.textContent = 'Sign & send';
        el('#err').innerHTML = '<div class="notice notice-error">' + esc(err.message) + '</div>';
      });
    });
  }

  function thanksView(q) {
    shell(panel(
      '<div style="text-align:center">' +
        '<div style="font-size:2rem;margin-bottom:10px">✓</div>' +
        '<h2 style="margin:0 0 10px">Signature recorded</h2>' +
        '<p class="muted">Musanga will confirm and schedule the truck.' +
          (q.counterparty_phone ? '<br>You will get a confirmation SMS on <b>' + esc(q.counterparty_phone) + '</b>.' : '') +
        '</p>' +
        '<p class="muted" style="margin-top:20px;font-size:.85rem">Reference <b class="mono">' + esc(q.ref) + '</b>' +
          (q.order_ref ? ' · load <b class="mono">' + esc(q.order_ref) + '</b>' : '') + '</p>' +
        '<a class="btn btn-ghost btn-block" href="/" style="margin-top:20px">Back to Musanga</a>' +
      '</div>'
    ));
  }

  function render(q) {
    if (q.status === 'booked' || q.status === 'signed') return thanksView(q);
    if (q.status === 'accepted' && !q.signed_at) return signView(q);
    return reviewView(q);
  }

  if (!token) return fatal('Missing quote token.');
  api.publicQuote(token).then(render).catch(function (err) {
    fatal(err.message || 'Unknown error opening this quote.');
  });
})();
