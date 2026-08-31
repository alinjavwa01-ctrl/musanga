/* The transporter's RFP page: one lane, one form, one signature.

   The link in the email carries a token. This page asks the API for what
   that token points at, shows the ask, the bidding terms, and a form that
   captures the price, the trucks and the signature that binds the bid. */
(function () {
  'use strict';

  var M = window.M, api = M.api, esc = M.esc;
  var root = document.getElementById('root');
  var token = (location.pathname.split('/rfp/')[1] || '').replace(/\/$/, '');
  var state = { rfp: null };

  function shell(inner) {
    root.innerHTML = '<div class="sign-wrap">' + inner + '</div>';
  }

  function fatal(msg) {
    shell(
      '<div class="sign-panel" style="max-width:520px;margin:60px auto;text-align:center">' +
      '<h3>This link cannot be opened</h3><p>' + esc(msg) + '</p>' +
      '<a class="btn btn-ghost btn-block" href="/">Go to musanga.com</a></div>');
  }

  function renderTerms(text) {
    var blocks = esc(text).split(/\n\s*\n/);
    return blocks.map(function (block) {
      if (block.indexOf('## ') === 0) return '<h2>' + block.slice(3).trim() + '</h2>';
      if (/^\s{4}\S/.test(block)) return '<pre>' + block.replace(/^\n+/, '') + '</pre>';
      var clause = /^\d+\.\d+\s/.test(block.trim());
      return '<p' + (clause ? ' class="clause"' : '')
        + '>' + block.trim().replace(/\n\s*/g, ' ') + '</p>';
    }).join('');
  }

  function fmtDate(unix) {
    if (!unix) return '';
    return new Date(unix * 1000).toLocaleDateString('en-ZM',
      { day: 'numeric', month: 'short', year: 'numeric' });
  }

  function askRow(label, value) {
    return '<div class="ask-row"><dt>' + esc(label) + '</dt>' +
           '<dd>' + esc(value || '—') + '</dd></div>';
  }

  function askPanel(r) {
    return '<section class="sign-panel"><h2>The load Musanga is bidding out</h2>' +
      '<dl class="ask-list">' +
        askRow('Reference', r.ref) +
        askRow('Title', r.title) +
        askRow('Corridor', r.corridor) +
        askRow('Loading point', r.from_place) +
        askRow('Discharge point', r.to_place) +
        askRow('Commodity', r.commodity) +
        askRow('Equipment', r.equipment) +
        askRow('Tonnage on offer', r.tonnes_total ? (r.tonnes_total + ' t') : 'Ask') +
        askRow('Trucks needed', r.trucks_needed || 'Ask') +
        askRow('Loading window', [r.loading_from, r.loading_to].filter(Boolean).join(' → ')) +
        askRow('RFP closes', fmtDate(r.closes_at)) +
        askRow('Cover required per load', r.cover_min || '—') +
        (r.notes ? askRow('Notes', r.notes) : '') +
      '</dl></section>';
  }

  function bidPanel(r) {
    if (r.bid) return submittedPanel(r);
    if (r.status !== 'open') {
      return '<section class="sign-panel"><h2>This RFP is ' + esc(r.status_label) + '</h2>' +
        '<p>Bids can no longer be submitted from this link. Contact Musanga if you '
        + 'believe this is a mistake.</p></section>';
    }
    if (r.invite.status === 'declined') {
      return '<section class="sign-panel"><h2>You declined this RFP</h2>' +
        '<p>If that was in error, contact contracts@musanga.com and we will reopen '
        + 'the invitation.</p></section>';
    }

    var curr = esc(r.currency || 'ZMW');
    return '<section class="sign-panel"><h2>Submit your bid</h2>' +
      '<p class="muted">The rate, the trucks and the tonnage below are what will '
      + 'bind if Musanga awards you the loads.</p>' +
      '<form id="bid-form" class="stack" autocomplete="off">' +
        '<div class="grid-2">' +
          '<label>Rate per tonne (' + curr + ')<input required type="number" step="0.01" min="0" name="rate_per_tonne" placeholder="e.g. 2450.00"></label>' +
          '<label>Trucks committed<input type="number" min="0" step="1" name="trucks_offered" placeholder="e.g. 4"></label>' +
          '<label>Tonnes you can move in the window<input type="number" min="0" step="1" name="capacity_tonnes" placeholder="e.g. 130"></label>' +
          '<label>Earliest you can load<input type="date" name="available_from"></label>' +
          '<label>Latest you can load<input type="date" name="available_to"></label>' +
        '</div>' +
        '<label>Notes for Musanga<textarea rows="3" name="notes" placeholder="Anything Musanga should know — return loads, equipment quirks, permit lead time."></textarea></label>' +

        '<h3 style="margin-top:24px">Sign the bid</h3>' +
        '<div class="grid-2">' +
          '<label>Full name<input required name="signer_name" placeholder="Authorised signatory"></label>' +
          '<label>Title<input name="signer_title" placeholder="e.g. Director"></label>' +
          '<label>Email<input type="email" name="signer_email" placeholder="you@company.com"></label>' +
        '</div>' +
        '<label class="check"><input type="checkbox" name="consent_terms"> I have read the bidding terms above and agree to them on behalf of ' + esc(r.invite.carrier_name) + '.</label>' +
        '<label class="check"><input type="checkbox" name="consent_authority"> I confirm I have authority to bind ' + esc(r.invite.carrier_name) + ' to this bid, and that our goods-in-transit and operator licences meet the requirement above.</label>' +

        '<div class="sign-actions">' +
          '<button class="btn btn-primary" type="submit">Sign and submit bid</button>' +
          '<button class="btn btn-ghost" type="button" id="decline-btn">Decline the RFP</button>' +
        '</div>' +
        '<p id="bid-err" class="notice notice-error" style="display:none"></p>' +
      '</form></section>';
  }

  function submittedPanel(r) {
    var b = r.bid;
    return '<section class="sign-panel"><h2>Bid submitted</h2>' +
      '<p>Musanga has your bid. You will be notified if the RFP is awarded to '
        + esc(r.invite.carrier_name) + '.</p>' +
      '<dl class="ask-list">' +
        askRow('Bid reference', r.ref + '/' + b.id) +
        askRow('Rate per tonne', b.rate) +
        askRow('Trucks committed', b.trucks_offered) +
        askRow('Tonnes committed', b.capacity_tonnes) +
        askRow('Available', [b.available_from, b.available_to].filter(Boolean).join(' → ')) +
        askRow('Signed by', (b.signer_name || '') + (b.signer_title ? ', ' + b.signer_title : '')) +
        askRow('Terms hash', b.terms_hash) +
      '</dl></section>';
  }

  function render() {
    var r = state.rfp;
    if (!r) return;
    shell(
      '<div class="sign-header">' +
        '<div class="sign-kicker">' + esc(r.company.name) + ' · Request for prices and capacity</div>' +
        '<h1>' + esc(r.title) + '</h1>' +
        '<p class="muted">Sent to ' + esc(r.invite.carrier_name) + '.</p>' +
      '</div>' +
      askPanel(r) +
      '<section class="sign-panel"><h2>Bidding terms</h2><div class="doc-body">' +
        renderTerms(r.terms_body) +
      '</div><p class="hash">Document hash · ' + esc(r.terms_hash) + '</p></section>' +
      bidPanel(r)
    );

    var form = document.getElementById('bid-form');
    if (form) form.addEventListener('submit', submitBid);
    var decl = document.getElementById('decline-btn');
    if (decl) decl.addEventListener('click', declineRfp);
  }

  function submitBid(e) {
    e.preventDefault();
    var f = e.target;
    var payload = {
      rate_per_tonne: f.rate_per_tonne.value,
      trucks_offered: f.trucks_offered.value,
      capacity_tonnes: f.capacity_tonnes.value,
      available_from: f.available_from.value,
      available_to: f.available_to.value,
      notes: f.notes.value,
      signer_name: f.signer_name.value,
      signer_title: f.signer_title.value,
      signer_email: f.signer_email.value,
      consent_terms: f.consent_terms.checked,
      consent_authority: f.consent_authority.checked
    };
    var err = document.getElementById('bid-err');
    err.style.display = 'none';
    var btn = f.querySelector('button[type=submit]');
    btn.disabled = true; btn.textContent = 'Submitting…';
    api.post('/api/rfp/' + token + '/bid', payload).then(function (res) {
      state.rfp = res; render();
      window.scrollTo({ top: 0, behavior: 'smooth' });
    }).catch(function (e) {
      err.textContent = e.message; err.style.display = '';
      btn.disabled = false; btn.textContent = 'Sign and submit bid';
    });
  }

  function declineRfp() {
    var reason = prompt('Optional: tell Musanga why you are declining this RFP.', '') || '';
    api.post('/api/rfp/' + token + '/decline', { reason: reason }).then(load).catch(function (e) {
      alert(e.message);
    });
  }

  function load() {
    api.get('/api/rfp/' + token).then(function (res) {
      state.rfp = res; render();
    }).catch(function (e) {
      fatal(e.message);
    });
  }

  if (!token) return fatal('The link is missing its reference.');
  load();
})();
