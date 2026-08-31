/* Musanga platform: a hash-routed single page app over the JSON API.
   One shell, three role-specific navigations - shipper, driver, ops. */
(function () {
  'use strict';

  var M = window.M, api = M.api, esc = M.esc, el = M.el;
  var root = document.getElementById('root');

  var state = { user: null, vehicle: null, config: null, kyc: null };

  /* --- icons (inline so the app has no external asset dependency) -------- */
  var ICON = {
    grid:  '<path d="M3 3h7v7H3zM14 3h7v7h-7zM14 14h7v7h-7zM3 14h7v7H3z"/>',
    plus:  '<path d="M12 5v14M5 12h14"/>',
    list:  '<path d="M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01"/>',
    truck: '<path d="M3 17V7a1 1 0 0 1 1-1h10v11M14 10h4l3 4v3"/><circle cx="7.5" cy="17.5" r="2.5"/><circle cx="17.5" cy="17.5" r="2.5"/>',
    cash:  '<rect x="2" y="6" width="20" height="12" rx="2"/><circle cx="12" cy="12" r="2.5"/>',
    users: '<path d="M16 20v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M22 20v-2a4 4 0 0 0-3-3.87"/>',
    plant: '<path d="M3 20h18M6 20v-5l4-6 4 2v9"/><path d="M14 11l6-4M20 7v4"/><circle cx="7.5" cy="17.5" r="1"/>',
    out:   '<path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4M16 17l5-5-5-5M21 12H9"/>',
    fuel:  '<path d="M4 20V5a2 2 0 0 1 2-2h5a2 2 0 0 1 2 2v15M3 20h12"/><path d="M13 9h3l2 2v6a2 2 0 0 0 2-2V8l-3-3"/><path d="M6 8h5"/>',
    shield:'<path d="M12 3l8 3v6c0 4.4-3.2 7.9-8 9-4.8-1.1-8-4.6-8-9V6z"/><path d="M9 12l2 2 4-4"/>',
    pen:   '<path d="M4 20h4L20 8a2.8 2.8 0 0 0-4-4L4 16z"/><path d="M14 6l4 4"/>',
    globe: '<circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3c2.5 2.7 2.5 15.3 0 18M12 3c-2.5 2.7-2.5 15.3 0 18"/>'
  };
  function icon(name) {
    return '<svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" ' +
           'stroke-width="2" stroke-linecap="round" stroke-linejoin="round">' + ICON[name] + '</svg>';
  }

  /* --- navigation per role ---------------------------------------------- */
  var NAV = {
    shipper: [
      { path: '#/', label: 'Overview', icon: 'grid' },
      { path: '#/book', label: 'Move a load', icon: 'plus' },
      { path: '#/hire', label: 'Rent a machine', icon: 'plant' },
      { path: '#/orders', label: 'My loads', icon: 'list' },
      { path: '#/contracts', label: 'Contracts', icon: 'list' },
      { path: '#/hires', label: 'My hires', icon: 'truck' },
      { path: '#/agreements', label: 'Agreements', icon: 'pen' },
      { path: '#/verify', label: 'Verification', icon: 'shield' }
    ],
    driver: [
      { path: '#/', label: 'Load board', icon: 'grid' },
      { path: '#/my', label: 'My loads', icon: 'truck' },
      { path: '#/fuel', label: 'Fuel & cover', icon: 'fuel' },
      { path: '#/earnings', label: 'Earnings', icon: 'cash' },
      { path: '#/agreements', label: 'Agreements', icon: 'pen' },
      { path: '#/verify', label: 'Verification', icon: 'shield' }
    ],
    ops: [
      { path: '#/', label: 'Control', icon: 'grid' },
      { path: '#/orders', label: 'All loads', icon: 'list' },
      { path: '#/hires', label: 'Plant hire', icon: 'plant' },
      { path: '#/drivers', label: 'Carriers', icon: 'users' },
      { path: '#/contracts', label: 'Contracts', icon: 'list' },
      { path: '#/book', label: 'Rate for a client', icon: 'plus' },
      { path: '#/quotes', label: 'Quotes', icon: 'pen' },
      { path: '#/rfps', label: 'RFPs', icon: 'pen' },
      { path: '#/network', label: 'Network', icon: 'globe' },
      { path: '#/agreements', label: 'Agreements', icon: 'pen' },
      { path: '#/kyc', label: 'Compliance', icon: 'shield' }
    ]
  };

  /* --- shared fragments -------------------------------------------------- */
  function statusPill(o) {
    return '<span class="pill pill-' + esc(o.status) + '">' + esc(o.status_label) + '</span>';
  }

  // What each role is called in the interface, as distinct from its key.
  var ROLE_LABEL = { shipper: 'Shipper', driver: 'Carrier', ops: 'Control' };

  // Limited mode is visible on every screen until the file is cleared, because
  // the worst version of this is a customer who only discovers the block at
  // the moment they try to book.
  function verifyBanner() {
    if (!state.user || state.user.role === 'ops' || state.user.verified) return '';
    var k = state.kyc || {};
    var copy = {
      unverified: ['Your account is in limited mode',
                   'You can rate loads and look around. Verify your business to book, hire and draw fuel.',
                   'Start verification'],
      in_review: ['Verification in review',
                  'Your file is with our compliance team. Most are cleared within one working day.',
                  'View file'],
      rejected: ['Verification needs attention',
                 k.note || 'Our compliance team sent your file back. Open it to see what to fix.',
                 'Fix and resubmit']
    }[k.status || 'unverified'];
    var done = k.documents_filed || 0, need = k.documents_required || 0;
    return '<div class="kyc-banner kyc-banner-' + esc(k.status || 'unverified') + '">' +
      '<div><b>' + esc(copy[0]) + '</b><span>' + esc(copy[1]) + '</span></div>' +
      (need ? '<span class="kyc-count">' + done + '/' + need + ' documents</span>' : '') +
      '<a class="btn btn-primary btn-sm" href="#/verify">' + esc(copy[2]) + '</a></div>';
  }

  function shell(bodyHtml) {
    var nav = NAV[state.user.role].map(function (item) {
      var active = (location.hash || '#/') === item.path;
      return '<a href="' + item.path + '" class="' + (active ? 'active' : '') + '">' +
             icon(item.icon) + '<span>' + esc(item.label) + '</span></a>';
    }).join('');

    root.innerHTML =
      '<div class="shell">' +
        '<aside class="sidebar">' +
          '<div class="sidebar-top">' +
            '<a class="logo" href="/">Musanga</a>' +
            '<span class="side-role">' + esc(ROLE_LABEL[state.user.role]) + '</span>' +
          '</div>' +
          '<nav class="side-nav">' + nav + '</nav>' +
          '<div class="side-foot">' +
            '<b>' + esc(state.user.name) + '</b>' +
            '<span class="muted">' + esc(state.user.company || state.user.phone) + '</span>' +
            '<a href="#/logout" style="display:flex;gap:8px;align-items:center;margin-top:10px;color:var(--ink-400)">' +
              icon('out') + '<span>Sign out</span></a>' +
          '</div>' +
        '</aside>' +
        '<main class="main">' + verifyBanner() + bodyHtml + '</main>' +
      '</div>';
  }

  function pageHead(title, sub, actions) {
    return '<div class="page-head"><div><h1>' + esc(title) + '</h1>' +
           (sub ? '<p>' + esc(sub) + '</p>' : '') + '</div>' +
           (actions ? '<div class="spacer"></div>' + actions : '') + '</div>';
  }

  function empty(title, sub) {
    return '<div class="table-wrap"><div class="empty"><b>' + esc(title) + '</b>' + esc(sub || '') + '</div></div>';
  }

  function orderTable(orders, columns) {
    if (!orders.length) return empty('Nothing here yet', 'Orders will appear as soon as they are placed.');
    var head = columns.map(function (c) {
      return '<th' + (c.num ? ' class="num"' : '') + '>' + esc(c.label) + '</th>';
    }).join('');
    var body = orders.map(function (o) {
      return '<tr data-ref="' + esc(o.ref) + '">' + columns.map(function (c) {
        return '<td' + (c.num ? ' class="num"' : '') + '>' + c.cell(o) + '</td>';
      }).join('') + '</tr>';
    }).join('');
    return '<div class="table-wrap"><table><thead><tr>' + head + '</tr></thead><tbody>' + body + '</tbody></table></div>';
  }

  // Clicking any table row opens that order.
  document.addEventListener('click', function (e) {
    if (!e.target.closest || e.target.closest('button, select, a')) return;
    var order = e.target.closest('tr[data-ref]');
    if (order) return void (location.hash = '#/orders/' + order.dataset.ref);
    var hire = e.target.closest('tr[data-hire]');
    if (hire) location.hash = '#/hires/' + hire.dataset.hire;
  });

  var COL = {
    ref:      { label: 'Reference', cell: function (o) { return '<b class="mono">' + esc(o.ref) + '</b><span class="sub">' + esc(M.ago(o.created_at)) + '</span>'; } },
    route:    { label: 'Corridor', cell: function (o) { return esc(o.from_name) + ' &rarr; ' + esc(o.to_name) + '<span class="sub">' + esc(o.distance_km) + ' km</span>'; } },
    cargo:    { label: 'Cargo', cell: function (o) { return esc(o.commodity_name) + '<span class="sub">' + esc(o.tonnes) + ' t &middot; ' + esc(o.goods) + '</span>'; } },
    vehicle:  { label: 'Equipment', cell: function (o) { return esc(o.equipment_name) + '<span class="sub">' + esc(o.service_name) + '</span>'; } },
    driver:   { label: 'Carrier', cell: function (o) { return o.driver ? esc(o.driver.name) + '<span class="sub mono">' + esc((o.driver_vehicle || {}).plate || '') + '</span>' : '<span class="muted">Unassigned</span>'; } },
    status:   { label: 'Status', cell: statusPill },
    total:    { label: 'Total', num: true, cell: function (o) { return esc(o.total) + '<span class="sub">' + esc(o.payment_label) + '</span>'; } },
    payout:   { label: 'Payout', num: true, cell: function (o) { return esc(o.payout); } }
  };

  /* ====================================================================== */
  /* AUTH                                                                   */
  /* ====================================================================== */

  function authShell(inner) {
    root.innerHTML = '<div class="auth-wrap"><div class="auth-card">' +
      '<a class="logo" href="/">Musanga</a>' + inner + '</div></div>';
  }

  function viewLogin() {
    authShell(
      '<h2>Welcome back</h2><p class="muted">Sign in to your Musanga account.</p>' +
      '<div id="err"></div>' +
      '<form id="f">' +
        '<label class="field"><span>Phone number</span><input class="input" name="phone" required autocomplete="username" placeholder="+2609…"></label>' +
        '<label class="field"><span>Password</span><input class="input" name="password" type="password" required autocomplete="current-password"></label>' +
        '<button class="btn btn-primary btn-block" type="submit">Sign in</button>' +
      '</form>' +
      '<p class="auth-alt">New to Musanga? <a href="#/register">Create an account</a></p>'
    );

    el('#f').addEventListener('submit', function (e) {
      e.preventDefault();
      var f = e.target;
      submit(f, api.login({ phone: f.phone.value.trim(), password: f.password.value }));
    });
  }

  // Signup asks for the four things needed to open an account and nothing
  // else. Company registration, tax numbers and the document file are
  // collected later, inside the app, once there is an account to attach
  // them to.
  function viewRegister() {
    var wanted = new URLSearchParams((location.hash.split('?')[1] || '')).get('role');
    var role = ['shipper', 'driver', 'ops'].indexOf(wanted) >= 0 ? wanted : 'shipper';

    function draw() {
      authShell(
        '<h2>Create your account</h2>' +
        '<p class="muted">Takes a minute. You can rate loads straight away and verify your business afterwards.</p>' +
        '<div class="role-picker">' +
          ['shipper', 'driver', 'ops'].map(function (r) {
            var label = { shipper: 'I ship', driver: 'I haul', ops: 'Musanga control' }[r];
            return '<button type="button" data-role="' + r + '" aria-pressed="' + (r === role) + '">' + label + '</button>';
          }).join('') +
        '</div>' +
        '<div id="err"></div>' +
        '<form id="f">' +
          '<label class="field"><span>Full name</span><input class="input" name="name" required autocomplete="name"></label>' +
          '<div class="row2">' +
            '<label class="field"><span>Phone number</span><input class="input" name="phone" required placeholder="+2609…" autocomplete="tel"></label>' +
            '<label class="field"><span>Work email</span><input class="input" name="email" type="email" autocomplete="email"></label>' +
          '</div>' +
          '<label class="field"><span>' + (role === 'driver' ? 'Transporter name' : 'Company') +
            ' <span class="muted">(optional)</span></span><input class="input" name="company" autocomplete="organization"></label>' +
          '<label class="field"><span>Password <span class="muted">(8+ characters)</span></span>' +
            '<input class="input" name="password" type="password" required minlength="8" autocomplete="new-password"></label>' +
          '<button class="btn btn-primary btn-block" type="submit">Create account</button>' +
        '</form>' +
        '<p class="auth-fine">No card, no documents up front. Booking loads, hiring plant and drawing fuel open once your business is verified — you can do all of that from inside the app.</p>' +
        '<p class="auth-alt">Already have an account? <a href="#/login">Sign in</a></p>'
      );

      el('.role-picker').addEventListener('click', function (e) {
        if (!e.target.dataset.role) return;
        role = e.target.dataset.role;
        draw();
      });

      el('#f').addEventListener('submit', function (e) {
        e.preventDefault();
        var f = e.target;
        submit(f, api.register({
          role: role, name: f.name.value.trim(), phone: f.phone.value.trim(),
          email: f.email.value.trim(), company: f.company.value.trim(),
          password: f.password.value
        }));
      });
    }
    draw();
  }

  function submit(form, promise) {
    var btn = form.querySelector('button[type=submit]');
    var label = btn.textContent;
    btn.disabled = true;
    btn.textContent = 'Please wait…';
    el('#err').innerHTML = '';
    promise.then(function (res) {
      api.setToken(res.token);
      state.user = res.user;
      return refreshMe().then(function () {
        location.hash = (state.user.role !== 'ops' && !state.user.verified) ? '#/verify' : '#/';
        route();
      });
    }).catch(function (err) {
      el('#err').innerHTML = '<div class="notice notice-error">' + esc(err.message) + '</div>';
      btn.disabled = false;
      btn.textContent = label;
    });
  }

  /* ====================================================================== */
  /* SHIPPER                                                                */
  /* ====================================================================== */

  function viewShipperHome() {
    Promise.all([api.orders(), api.hires()]).then(function (r) {
      var res = r[0], hires = r[1].hires;
      var orders = res.orders;
      var live = orders.filter(function (o) { return ['placed', 'assigned', 'at_pickup', 'in_transit'].indexOf(o.status) >= 0; });
      var done = orders.filter(function (o) { return o.status === 'delivered'; });
      var spend = orders.reduce(function (sum, o) { return o.status === 'cancelled' ? sum : sum + o.total_ngwee; }, 0);

      var tonnes = orders.reduce(function (sum, o) { return o.status === 'delivered' ? sum + o.tonnes : sum; }, 0);
      var liveHires = hires.filter(function (h) {
        return ['requested', 'confirmed', 'on_site', 'off_hire'].indexOf(h.status) >= 0;
      });
      var hireSpend = hires.reduce(function (sum, h) { return h.status === 'cancelled' ? sum : sum + h.total_ngwee; }, 0);

      shell(
        pageHead('Overview', 'Everything you have running right now.',
          '<a class="btn btn-ghost btn-sm" href="#/hire">Rent a machine</a>' +
          '<a class="btn btn-primary btn-sm" style="margin-left:8px" href="#/book">Move a load</a>') +
        '<div class="tiles">' +
          '<div class="tile accent"><span>On the road</span><b>' + live.length + '</b><small>loads in transit</small></div>' +
          '<div class="tile accent"><span>On hire</span><b>' + liveHires.length + '</b><small>machines out</small></div>' +
          '<div class="tile"><span>Tonnage moved</span><b>' + tonnes.toFixed(0) + ' t</b><small>delivered</small></div>' +
          '<div class="tile"><span>Freight spend</span><b>' + esc(M.kwacha(spend)) + '</b><small>VAT included</small></div>' +
          '<div class="tile"><span>Hire spend</span><b>' + esc(M.kwacha(hireSpend)) + '</b><small>VAT included</small></div>' +
        '</div>' +
        '<h3 style="margin:8px 0 16px">Active loads</h3>' +
        (live.length
          ? orderTable(live, [COL.ref, COL.route, COL.cargo, COL.vehicle, COL.driver, COL.status, COL.total])
          : empty('Nothing on the road', 'Book a load and it will show up here.')) +
        '<h3 style="margin:32px 0 16px">Machines on hire</h3>' +
        (liveHires.length ? hireTable(liveHires)
                          : empty('No machines out', 'Rent one and it will show up here.'))
      );
    }).catch(fail);
  }

  function viewShipperOrders() {
    api.orders().then(function (res) {
      shell(
        pageHead('My loads', res.orders.length + ' loads with Musanga',
          '<a class="btn btn-primary" href="#/book">Rate a load</a>') +
        orderTable(res.orders, [COL.ref, COL.route, COL.cargo, COL.vehicle, COL.driver, COL.status, COL.total])
      );
    }).catch(fail);
  }

  /* --- booking ---------------------------------------------------------- */
  function viewBook() {
    var params = new URLSearchParams(location.hash.split('?')[1] || '');
    var cfg = state.config;

    // Commodities are grouped by sector so mining, agri and fuel read apart.
    var sectors = {};
    cfg.commodities.forEach(function (c) { (sectors[c.sector] = sectors[c.sector] || []).push(c); });
    var commodityOptions = Object.keys(sectors).map(function (sector) {
      return '<optgroup label="' + esc(sector.charAt(0).toUpperCase() + sector.slice(1)) + '">' +
        sectors[sector].map(function (c) {
          return '<option value="' + esc(c.key) + '">' + esc(c.name) + '</option>';
        }).join('') + '</optgroup>';
    }).join('');

    shell(
      pageHead('Rate a load', 'Tonne-kilometre pricing, itemised before you commit.') +
      '<div class="book">' +
        '<form class="panel" id="f">' +
          '<fieldset><legend>The lane</legend>' +
            '<div class="row2">' +
              '<label class="field"><span>From</span><select class="input" name="from_zone">' + M.zoneOptions(cfg.zones, cfg.countries) + '</select></label>' +
              '<label class="field"><span>To</span><select class="input" name="to_zone">' + M.zoneOptions(cfg.zones, cfg.countries) + '</select></label>' +
            '</div>' +
            '<div class="row2">' +
              '<label class="field"><span>Commodity</span><select class="input" name="commodity">' + commodityOptions + '</select></label>' +
              '<label class="field"><span>Equipment</span><select class="input" name="equipment"></select></label>' +
            '</div>' +
            '<div class="row2">' +
              '<label class="field"><span>Tonnes</span><input class="input" name="tonnes" type="number" min="0.5" step="0.5" value="30" inputmode="decimal" required></label>' +
              '<label class="field"><span>Contract type</span><select class="input" name="service">' + M.options(cfg.services, 'key', 'name') + '</select></label>' +
            '</div>' +
          '</fieldset>' +

          '<details class="book-more" id="book-more"' + (state.user.role === 'ops' ? '' : ' open') + '>' +
            '<summary>Load-out details — addresses, drops, cover, contract</summary>' +
          '<fieldset><legend>Load-out</legend>' +
            '<label class="field"><span>Description for the carrier</span><input class="input" name="goods" required placeholder="Compound D fertiliser, 50 kg bags"></label>' +
            '<label class="field"><span>Pickup site address</span><input class="input" name="pickup_address" required placeholder="Nitrogen Chemicals of Zambia, Kafue"></label>' +
            '<label class="field"><span>Dropoff site address</span><input class="input" name="dropoff_address" required placeholder="Mkushi Farm Block, central store"></label>' +
            '<div class="row2">' +
              '<label class="field"><span>Site contact</span><input class="input" name="recipient_name" required></label>' +
              '<label class="field"><span>Contact phone</span><input class="input" name="recipient_phone" required placeholder="+2609…"></label>' +
            '</div>' +
          '</fieldset>' +

          '<fieldset><legend>Extra drops</legend>' +
            '<p class="muted" style="margin:0 0 12px;font-size:.83rem">' +
              'One truck, several consignees. Add the stops it makes before the final delivery; ' +
              'each one is signed for and weighed on its own.</p>' +
            '<div id="drops"></div>' +
            '<button class="btn btn-ghost btn-sm" type="button" id="add-drop">Add a drop</button>' +
          '</fieldset>' +

          '<fieldset><legend>Cargo cover</legend>' +
            '<label class="field"><span>Declared value of the cargo (kwacha) — leave blank for no cover</span>' +
              '<input class="input" name="declared_value" type="number" min="0" step="1000" inputmode="numeric" placeholder="e.g. 850000"></label>' +
            '<div id="cover" class="muted" style="font-size:.83rem">Goods-in-transit cover, placed with a licensed insurer. Musanga arranges it; the insurer carries it.</div>' +
          '</fieldset>' +

          '<fieldset><legend>Settlement</legend>' +
            '<label class="field" id="ctr-field" hidden><span>Call off against a contract</span>' +
              '<select class="input" name="contract_ref"><option value="">No — price this load on its own</option></select></label>' +
            '<label class="field"><span>How is this load paid?</span><select class="input" name="payment_method">' +
              M.options(cfg.payment_methods, 'key', 'name') + '</select></label>' +
          '</fieldset>' +
          '</details>' +

          '<div id="err"></div>' +
          (state.user.role === 'ops'
            ? '<button class="btn btn-ghost btn-block" type="submit">Book directly (skip customer sign-off)</button>'
            : '<button class="btn btn-primary btn-block" type="submit">Book this load</button>') +
          (state.user.role === 'ops'
            ? '<div id="send-panel" style="margin-top:24px;padding-top:20px;border-top:1px solid var(--ink-100)">' +
                '<h3 style="margin:0 0 6px">Send this rate to the customer</h3>' +
                '<p class="muted" style="margin:0 0 14px;font-size:.83rem">' +
                  'They accept and sign the link; the load lands in dispatch after you confirm.</p>' +
                '<div class="row2">' +
                  '<label class="field"><span>Customer name / company</span>' +
                    '<input class="input" name="counterparty" list="recent-customers" autocomplete="off" required></label>' +
                  '<label class="field"><span>Customer email</span>' +
                    '<input class="input" name="counterparty_email" type="email" autocomplete="off" required></label>' +
                '</div>' +
                '<datalist id="recent-customers"></datalist>' +
                '<div class="row2">' +
                  '<label class="field"><span>Customer phone <span class="muted">(optional)</span></span><input class="input" name="counterparty_phone" placeholder="+2609…"></label>' +
                  '<label class="field"><span>Quote holds for</span><select class="input" name="expires_in_days">' +
                    ['3','7','14','30'].map(function (d) { return '<option value="' + d + '"' + (d === '7' ? ' selected' : '') + '>' + d + ' days</option>'; }).join('') +
                  '</select></label>' +
                '</div>' +
                '<fieldset style="margin:6px 0 20px"><legend>Reminders</legend>' +
                  '<div class="chip-row" id="reminder-chips">' +
                    '<label class="chip"><input type="checkbox" name="rem" value="after1"> 1 day after send</label>' +
                    '<label class="chip"><input type="checkbox" name="rem" value="halfway" checked> Halfway to expiry</label>' +
                    '<label class="chip"><input type="checkbox" name="rem" value="before1" checked> Day before expiry</label>' +
                    '<label class="chip"><input type="checkbox" name="rem" value="onexpiry"> Expiry day</label>' +
                  '</div>' +
                  '<p class="muted" id="reminder-preview" style="margin:10px 0 0;font-size:.78rem"></p>' +
                '</fieldset>' +
                '<fieldset style="margin:6px 0 20px"><legend>Package &amp; Profit First</legend>' +
                  '<div class="row2">' +
                    '<label class="field"><span>Slots in this package <span class="muted">(1 = single load)</span></span>' +
                      '<input class="input" type="number" name="slot_count" min="1" max="100" step="1" value="1" inputmode="numeric"></label>' +
                    '<label class="field"><span>Reserve by <span class="muted">(optional, cash-first)</span></span>' +
                      '<input class="input" type="date" name="reserve_by"></label>' +
                  '</div>' +
                  '<div class="row2">' +
                    '<label class="field"><span>Carrier ask <span class="muted">(per slot, quote currency)</span></span>' +
                      '<input class="input" type="number" name="carrier_amount" min="0" step="1" placeholder="1000" inputmode="decimal"></label>' +
                    '<label class="field"><span>Pass-throughs <span class="muted">(borders, YC, docs)</span></span>' +
                      '<input class="input" type="number" name="pass_through" min="0" step="1" placeholder="230" inputmode="decimal"></label>' +
                  '</div>' +
                  '<p class="muted" id="profit-lock-preview" style="margin:8px 0 0;font-size:.82rem">Enter carrier ask and pass-throughs to see the profit lock.</p>' +
                  '<label class="chip" style="margin-top:12px"><input type="checkbox" name="require_payment"> Cash-first: no dispatch until money in</label>' +
                '</fieldset>' +
                '<fieldset style="margin:6px 0 20px"><legend>Pre-payment conditions <span class="muted">(consignee must satisfy before we take cash)</span></legend>' +
                  '<div id="cond-list"></div>' +
                  '<div class="row2" style="align-items:end">' +
                    '<label class="field" style="margin:0"><span>Add a condition</span>' +
                      '<input class="input" name="cond_new" placeholder="e.g. Zimbabwe import permit number provided"></label>' +
                    '<button class="btn btn-ghost btn-sm" type="button" id="cond-add">Add</button>' +
                  '</div>' +
                '</fieldset>' +
                '<details style="margin:0 0 16px"><summary>Add a note or attachment</summary>' +
                  '<label class="field" style="margin-top:10px"><span>Note to the customer</span>' +
                    '<textarea class="input" name="note" rows="2" placeholder="e.g. Rate assumes weighbridge to weighbridge, discharge within 24 hours."></textarea></label>' +
                  '<label class="field"><span>Attach a document <span class="muted">(PDF or photo — they sign whatever you attach)</span></span>' +
                    '<input class="input" type="file" name="document" accept=".pdf,.jpg,.jpeg,.png,.heic,.webp"></label>' +
                '</details>' +
                '<div id="send-err"></div>' +
                '<button class="btn btn-primary btn-block btn-lg" type="button" id="send-quote">Send this rate</button>' +
                '<p class="muted" style="margin:10px 0 0;font-size:.78rem;text-align:center">Every rate goes out for signature. Payment is arranged off-line on booking.</p>' +
                '<div id="send-out" style="margin-top:12px"></div>' +
              '</div>'
            : '') +
        '</form>' +

        '<div class="panel book-summary">' +
          '<h3>Rate</h3>' +
          '<div id="quote"><p class="muted">Choose a corridor to see the rate.</p></div>' +
        '</div>' +
      '</div>'
    );

    var f = el('#f');

    // The commodity determines which equipment may legally carry it, so the
    // equipment list is rebuilt from the commodity rather than chosen freely.
    function syncEquipment(preferred) {
      var commodity = f.commodity.value;
      var eligible = cfg.equipment.filter(function (eq) { return eq.commodities.indexOf(commodity) >= 0; });
      f.equipment.innerHTML = eligible.map(function (eq) {
        return '<option value="' + esc(eq.key) + '">' + esc(eq.name) + ' — up to ' + eq.payload_t + ' t</option>';
      }).join('');
      if (preferred && eligible.some(function (eq) { return eq.key === preferred; })) f.equipment.value = preferred;
      var chosen = eligible.filter(function (eq) { return eq.key === f.equipment.value; })[0];
      if (chosen) {
        f.tonnes.max = chosen.payload_t;
        if (Number(f.tonnes.value) > chosen.payload_t) f.tonnes.value = chosen.payload_t;
      }
      f.querySelector('button[type=submit]').disabled = !eligible.length;
    }

    // Sensible starting corridor so the rate panel is never a same-node no-op.
    f.from_zone.value = 'kafue';
    f.to_zone.value = 'mkushi';
    if (params.get('commodity')) f.commodity.value = params.get('commodity');
    if (params.get('service')) f.service.value = params.get('service');
    if (params.get('from')) f.from_zone.value = params.get('from');
    if (params.get('to')) f.to_zone.value = params.get('to');
    if (params.get('tonnes')) f.tonnes.value = params.get('tonnes');
    syncEquipment(params.get('equipment'));

    function refreshQuote() {
      if (!f.equipment.value) {
        el('#quote').innerHTML = '<div class="notice notice-error">Nothing on the network carries that commodity.</div>';
        return;
      }
      api.quote({
        equipment: f.equipment.value, commodity: f.commodity.value, service: f.service.value,
        from_zone: f.from_zone.value, to_zone: f.to_zone.value, tonnes: Number(f.tonnes.value) || 0,
        stops: dropList().length
      }).then(function (q) {
        var lines = q.lines.filter(function (l) { return l.ngwee !== 0; }).map(function (l) {
          return '<div><span>' + esc(l.label) + '</span><span>' + esc(l.amount) + '</span></div>';
        }).join('');
        var crossings = q.crossings.length
          ? '<div class="border-strip"><span>Crossings</span>' +
              q.crossings.map(function (c) { return '<b>' + esc(c.post) + '</b>'; }).join('') + '</div>'
          : '';
        el('#quote').innerHTML =
          '<div class="summary-total"><span class="muted">' + esc(q.equipment_name) + '</span><b>' + esc(q.total) + '</b></div>' +
          '<div class="quote-meta muted" style="font-size:.8rem;display:flex;flex-wrap:wrap;gap:4px 14px">' +
            '<span>' + q.distance_km + ' km</span><span>' + q.billed_tonnes + ' t billed</span>' +
            '<span>' + esc(q.rate_per_tonne) + '/tonne</span>' +
            '<span>' + esc(q.transit_days) + ' days</span>' +
            (q.corridor ? '<span>' + esc(q.corridor) + '</span>' : '') +
          '</div>' + crossings +
          '<div class="summary-lines">' + lines +
            (q.vat_ngwee
              ? '<div class="total"><span>VAT 16%</span><span>' + esc(q.vat) + '</span></div>'
              : '<div class="total"><span>VAT</span><span>Zero-rated export</span></div>') +
          '</div>' +
          '<p class="muted" style="margin:14px 0 0;font-size:.81rem">' +
            'The empty leg back is costed in: ' + esc(q.empty_km) + ' km at this lane\'s backload odds. ' +
            '<b>' + q.document_count + ' documents</b> are needed to move it, and the checklist is ' +
            'raised the moment you book.</p>';
      }).catch(function (err) {
        el('#quote').innerHTML = '<div class="notice notice-error">' + esc(err.message) + '</div>';
      });
    }

    // Cover is priced on the declared value, the commodity and where it is
    // going - a border crossing and hazardous goods both load the rate.
    function refreshCover() {
      var declared = Number(f.declared_value.value) || 0;
      if (declared <= 0) {
        el('#cover').innerHTML = 'Goods-in-transit cover, placed with a licensed insurer. ' +
          'Musanga arranges it; the insurer carries it.';
        return;
      }
      api.coverQuote({
        commodity: f.commodity.value, declared_value: declared, to_zone: f.to_zone.value
      }).then(function (q) {
        el('#cover').innerHTML = 'Premium <b>' + esc(q.premium) + '</b> at ' + esc(q.rate_pct) + '% of declared value' +
          (q.at_minimum ? ' <span class="muted">(minimum premium)</span>' : '') +
          '. Added to this load when you book it.';
      }).catch(function (err) {
        el('#cover').innerHTML = '<span style="color:var(--stop)">' + esc(err.message) + '</span>';
      });
    }

    // Keep tonnage inside the selected unit's payload as it is typed, so the
    // form can never reach a state the rate engine will reject.
    function clampTonnes() {
      var max = Number(f.tonnes.max);
      if (max && Number(f.tonnes.value) > max) f.tonnes.value = max;
    }

    // Extra drops. Each row is a consignee on the way to the final one, and
    // the rate re-prices as they are added: another stop is another handling
    // window, another weighbridge and another delay.
    var dropSeq = 0;
    function addDrop() {
      dropSeq += 1;
      var row = document.createElement('div');
      row.className = 'drop-row';
      row.innerHTML =
        '<div class="row2">' +
          '<label class="field"><span>Drop ' + dropSeq + ' location</span>' +
            '<select class="input" data-k="node_key">' + M.zoneOptions(cfg.zones, cfg.countries) + '</select></label>' +
          '<label class="field"><span>Tonnes at this drop</span>' +
            '<input class="input" type="number" min="0" step="0.5" data-k="tonnes" value="10" inputmode="decimal"></label>' +
        '</div>' +
        '<label class="field"><span>Site address</span><input class="input" data-k="address"></label>' +
        '<div class="row2">' +
          '<label class="field"><span>Site contact</span><input class="input" data-k="recipient_name"></label>' +
          '<label class="field"><span>Contact phone</span><input class="input" data-k="recipient_phone"></label>' +
        '</div>' +
        '<button class="btn btn-ghost btn-sm" type="button" data-remove>Remove this drop</button>';
      el('#drops').appendChild(row);
      row.querySelector('[data-remove]').addEventListener('click', function () {
        row.parentNode.removeChild(row);
        refreshQuote();
      });
      row.querySelectorAll('select,input').forEach(function (n) {
        n.addEventListener('change', refreshQuote);
      });
      refreshQuote();
    }

    function dropList() {
      return M.els('.drop-row').map(function (row) {
        var out = {};
        row.querySelectorAll('[data-k]').forEach(function (n) { out[n.dataset.k] = n.value; });
        return out;
      }).filter(function (d) { return d.node_key; });
    }

    el('#add-drop').addEventListener('click', addDrop);

    // Contracts the signed-in shipper can draw this load down against.
    api.contracts().then(function (res) {
      var live = res.contracts.filter(function (c) { return c.status === 'active' && c.tonnes_remaining > 0; });
      if (!live.length) return;
      var sel = f.contract_ref;
      sel.innerHTML += live.map(function (c) {
        return '<option value="' + esc(c.ref) + '">' + esc(c.name) + ' — ' +
               esc(c.tonnes_remaining) + ' t left</option>';
      }).join('');
      el('#ctr-field').hidden = false;
      if (params.get('contract')) {
        sel.value = params.get('contract');
        var chosen = live.filter(function (c) { return c.ref === sel.value; })[0];
        if (chosen) {
          f.commodity.value = chosen.commodity_key;
          syncEquipment(chosen.equipment_key);
          f.from_zone.value = chosen.from_zone;
          f.to_zone.value = chosen.to_zone;
          f.service.value = 'contract';
          refreshQuote();
        }
      }
    }).catch(function () { /* a carrier or a signed-out rate check has none */ });

    var soon = M.debounce(function () { clampTonnes(); refreshQuote(); }, 220);
    var coverSoon = M.debounce(refreshCover, 260);
    f.declared_value.addEventListener('input', coverSoon);
    f.commodity.addEventListener('change', function () { syncEquipment(); refreshQuote(); refreshCover(); });
    f.equipment.addEventListener('change', function () { syncEquipment(f.equipment.value); refreshQuote(); });
    [f.service, f.from_zone].forEach(function (n) { n.addEventListener('change', refreshQuote); });
    f.to_zone.addEventListener('change', function () { refreshQuote(); refreshCover(); });
    f.tonnes.addEventListener('input', soon);
    f.tonnes.addEventListener('blur', function () { clampTonnes(); refreshQuote(); });
    refreshQuote();

    // If a required field inside the collapsed More options tries to fire native
    // validation, expand the details first so the user can see what to fix.
    f.addEventListener('invalid', function (e) {
      var more = el('#book-more');
      if (more && !more.open && more.contains(e.target)) more.open = true;
    }, true);

    f.addEventListener('submit', function (e) {
      e.preventDefault();
      var btn = f.querySelector('button[type=submit]');
      btn.disabled = true;
      btn.textContent = 'Booking…';
      el('#err').innerHTML = '';
      api.createOrder({
        equipment: f.equipment.value, commodity: f.commodity.value, service: f.service.value,
        from_zone: f.from_zone.value, to_zone: f.to_zone.value,
        pickup_address: f.pickup_address.value, dropoff_address: f.dropoff_address.value,
        recipient_name: f.recipient_name.value, recipient_phone: f.recipient_phone.value,
        goods: f.goods.value, tonnes: Number(f.tonnes.value) || 0,
        payment_method: f.payment_method.value,
        declared_value: Number(f.declared_value.value) || null,
        contract_ref: f.contract_ref.value || null,
        stops: dropList()
      }).then(function (o) {
        location.hash = '#/orders/' + o.ref;
      }).catch(function (err) {
        el('#err').innerHTML = '<div class="notice notice-error">' + esc(err.message) + '</div>';
        btn.disabled = false;
        btn.textContent = 'Book this load';
      });
    });

    if (state.user.role === 'ops') {
      // Expiry-relative reminder triggers → concrete "days after send" offsets,
      // resolved against the current "holds for" value so shifting the hold
      // shifts the reminders with it.
      function reminderDays() {
        var hold = Number(f.expires_in_days && f.expires_in_days.value) || 7;
        var picks = M.els('#reminder-chips input:checked').map(function (n) { return n.value; });
        var out = {};
        picks.forEach(function (p) {
          var d = 0;
          if (p === 'after1') d = 1;
          else if (p === 'halfway') d = Math.max(1, Math.round(hold / 2));
          else if (p === 'before1') d = hold - 1;
          else if (p === 'onexpiry') d = hold;
          if (d > 0 && d <= hold) out[d] = true;
        });
        return Object.keys(out).map(Number).sort(function (a, b) { return a - b; });
      }
      function refreshReminderPreview() {
        var hold = Number(f.expires_in_days && f.expires_in_days.value) || 7;
        var days = reminderDays();
        var preview = el('#reminder-preview');
        if (!preview) return;
        if (!days.length) {
          preview.textContent = 'No reminders — the quote will still expire after ' + hold + ' days.';
          return;
        }
        preview.textContent = 'Reminder on day ' + days.join(', day ') + ' after send (quote expires day ' + hold + ').';
      }
      M.els('#reminder-chips input').forEach(function (n) { n.addEventListener('change', refreshReminderPreview); });
      f.expires_in_days.addEventListener('change', refreshReminderPreview);
      refreshReminderPreview();

      // Recent counterparties, so the common case is one tap not typing.
      api.quotes().then(function (r) {
        var seen = {};
        var list = [];
        (r.quotes || []).forEach(function (q) {
          if (!q.counterparty || seen[q.counterparty.toLowerCase()]) return;
          seen[q.counterparty.toLowerCase()] = true;
          list.push(q);
        });
        el('#recent-customers').innerHTML = list.slice(0, 20).map(function (q) {
          return '<option value="' + esc(q.counterparty) + '"' +
                 (q.counterparty_email ? ' data-email="' + esc(q.counterparty_email) + '"' : '') +
                 (q.counterparty_phone ? ' data-phone="' + esc(q.counterparty_phone) + '"' : '') + '></option>';
        }).join('');
        // When a suggestion is picked, fill in the email/phone we already know.
        f.counterparty.addEventListener('input', function () {
          var picked = list.filter(function (q) { return q.counterparty === f.counterparty.value; })[0];
          if (!picked) return;
          if (!f.counterparty_email.value && picked.counterparty_email) f.counterparty_email.value = picked.counterparty_email;
          if (!f.counterparty_phone.value && picked.counterparty_phone) f.counterparty_phone.value = picked.counterparty_phone;
        });
      }).catch(function () { /* first-time users have no recent list */ });

      // Pre-payment conditions the ops user builds up on the send form; each
      // becomes a checklist item on the quote that ops later ticks off from
      // the quote row before payment is recorded.
      var pendingConds = [];
      function renderConds() {
        var host = el('#cond-list');
        if (!pendingConds.length) {
          host.innerHTML = '<p class="muted" style="margin:0 0 10px;font-size:.8rem">No conditions - add the ones the consignee must satisfy (import permits, TPINs, permits).</p>';
          return;
        }
        host.innerHTML = pendingConds.map(function (label, i) {
          return '<div style="display:flex;justify-content:space-between;align-items:center;gap:8px;padding:6px 0;border-bottom:1px dashed var(--ink-100)">' +
            '<span>' + esc(label) + '</span>' +
            '<button class="btn btn-ghost btn-sm" type="button" data-cond-rm="' + i + '">Remove</button>' +
          '</div>';
        }).join('');
        host.querySelectorAll('[data-cond-rm]').forEach(function (btn) {
          btn.addEventListener('click', function () {
            pendingConds.splice(Number(btn.dataset.condRm), 1);
            renderConds();
          });
        });
      }
      renderConds();
      el('#cond-add').addEventListener('click', function () {
        var v = (f.cond_new.value || '').trim();
        if (!v) return;
        pendingConds.push(v);
        f.cond_new.value = '';
        renderConds();
      });
      f.cond_new.addEventListener('keydown', function (e) {
        if (e.key === 'Enter') { e.preventDefault(); el('#cond-add').click(); }
      });

      // Live profit-lock preview so ops sees where the quote sits versus the
      // 30% floor before sending it.
      function refreshLockPreview() {
        var preview = el('#profit-lock-preview');
        if (!preview) return;
        var carrier = Number(f.carrier_amount.value) || 0;
        var pass = Number(f.pass_through.value) || 0;
        if (carrier <= 0) {
          preview.textContent = 'Enter carrier ask and pass-throughs to see the profit lock.';
          preview.style.color = '';
          return;
        }
        // Read the current per-slot total from the rate panel.
        var totalNode = document.querySelector('.summary-total b');
        if (!totalNode) return;
        var perSlot = Number(totalNode.textContent.replace(/[^0-9.]/g, '')) || 0;
        if (!perSlot) return;
        var take = perSlot - carrier - pass;
        var pct = perSlot ? (take / perSlot * 100) : 0;
        var slots = Number(f.slot_count.value) || 1;
        var badge = pct >= 30 ? '✓' : (pct >= 20 ? '⚠' : '✗');
        var color = pct >= 30 ? 'var(--go)' : (pct >= 20 ? 'var(--warn, #a06600)' : 'var(--stop)');
        preview.style.color = color;
        preview.innerHTML = badge + ' Profit lock <b>' + pct.toFixed(1) + '%</b> per slot · broker take ' +
          '<b>' + perSlot.toLocaleString() + ' - ' + carrier.toLocaleString() + ' - ' + pass.toLocaleString() +
          ' = ' + take.toLocaleString() + '</b> · ' + slots + '-slot package total ' +
          '<b>' + (perSlot * slots).toLocaleString() + '</b>';
      }
      ['carrier_amount', 'pass_through', 'slot_count'].forEach(function (n) {
        f[n].addEventListener('input', refreshLockPreview);
      });
      // Recompute when the underlying rate refreshes too.
      var lockObserver = new MutationObserver(refreshLockPreview);
      var quoteHost = el('#quote');
      if (quoteHost) lockObserver.observe(quoteHost, { childList: true, subtree: true });

      el('#send-quote').addEventListener('click', function () {
        var sb = el('#send-quote');
        var out = el('#send-out');
        var errBox = el('#send-err');
        errBox.innerHTML = '';
        out.innerHTML = '';
        var reminder = reminderDays();
        var reserveBy = null;
        if (f.reserve_by && f.reserve_by.value) {
          reserveBy = Math.round(new Date(f.reserve_by.value + 'T18:00:00Z').getTime() / 1000);
        }
        var body = {
          equipment: f.equipment.value, commodity: f.commodity.value, service: f.service.value,
          from_zone: f.from_zone.value, to_zone: f.to_zone.value,
          pickup_address: f.pickup_address.value, dropoff_address: f.dropoff_address.value,
          goods: f.goods.value, tonnes: Number(f.tonnes.value) || 0,
          payment_method: f.payment_method.value,
          stops: dropList(),
          counterparty: (f.counterparty && f.counterparty.value || '').trim(),
          counterparty_email: (f.counterparty_email && f.counterparty_email.value || '').trim(),
          counterparty_phone: (f.counterparty_phone && f.counterparty_phone.value || '').trim(),
          expires_in_days: Number(f.expires_in_days && f.expires_in_days.value) || 7,
          note: (f.note && f.note.value || '').trim(),
          reminder_days: reminder,
          slot_count: Math.max(1, Number(f.slot_count.value) || 1),
          carrier_amount: Number(f.carrier_amount.value) || 0,
          pass_through: Number(f.pass_through.value) || 0,
          reserve_by: reserveBy,
          require_payment: !!f.require_payment.checked,
          conditions: pendingConds.slice()
        };
        if (!body.counterparty) return void (errBox.innerHTML = '<div class="notice notice-error">Add a customer name.</div>');
        if (!body.counterparty_email) return void (errBox.innerHTML = '<div class="notice notice-error">Add a customer email so we can send the link.</div>');
        sb.disabled = true;
        sb.textContent = 'Sending…';
        (function loadFile() {
          var input = f.document;
          if (!input || !input.files || !input.files[0]) return Promise.resolve();
          var file = input.files[0];
          return new Promise(function (resolve, reject) {
            var reader = new FileReader();
            reader.onload = function () {
              body.file = reader.result;
              body.mime = file.type;
              body.filename = file.name;
              resolve();
            };
            reader.onerror = function () { reject(new Error('Could not read that file')); };
            reader.readAsDataURL(file);
          });
        })().then(function () {
        return api.sendQuote(body); }).then(function (res) {
          sb.disabled = false;
          sb.textContent = 'Send another';
          var mail = res.mail || {};
          var pill = mail.ok
            ? '<span class="pill pill-delivered">Emailed</span>'
            : '<span class="pill pill-placed">Copy the link below</span>';
          out.innerHTML =
            '<div class="notice"><b>' + esc(res.quote.ref) + '</b> sent to ' +
              esc(res.quote.counterparty_email || 'customer') + ' &middot; ' + pill +
              (mail.note ? '<div class="muted" style="margin-top:6px;font-size:.8rem">' + esc(mail.note) + '</div>' : '') +
              '<div style="margin-top:10px;display:flex;gap:8px;flex-wrap:wrap;align-items:center">' +
                '<code style="flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;padding:6px 10px;background:var(--ink-50);border-radius:6px;font-size:.78rem">' +
                  esc(res.url) + '</code>' +
                '<button class="btn btn-ghost btn-sm" type="button" data-copy="' + esc(res.url) + '">Copy link</button>' +
                '<a class="btn btn-ghost btn-sm" href="#/quotes">Open Quotes</a>' +
              '</div></div>';
          var copyBtn = out.querySelector('[data-copy]');
          if (copyBtn) copyBtn.addEventListener('click', function () {
            var url = copyBtn.getAttribute('data-copy');
            if (navigator.clipboard) navigator.clipboard.writeText(url);
            copyBtn.textContent = 'Copied';
          });
        }).catch(function (err) {
          sb.disabled = false;
          sb.textContent = 'Send this rate';
          errBox.innerHTML = '<div class="notice notice-error">' + esc(err.message) + '</div>';
        });
      });
    }
  }

  /* ====================================================================== */
  /* DRIVER                                                                 */
  /* ====================================================================== */

  function jobCard(o, action) {
    return '<article class="job">' +
      '<div class="job-top">' +
        '<div><span class="muted mono">' + esc(o.ref) + '</span>' +
          '<div style="font-weight:600">' + esc(o.commodity_name) + '</div>' +
          '<div class="muted" style="font-size:.81rem">' + esc(o.goods) + '</div></div>' +
        '<div class="job-pay">' + esc(o.payout) + '</div>' +
      '</div>' +
      '<div class="job-route">' +
        '<div class="leg"><i></i><div><b>' + esc(o.from_name) + '</b><span>' + esc(o.pickup_address || '') + '</span></div></div>' +
        '<div class="leg to"><i></i><div><b>' + esc(o.to_name) + '</b><span>' + esc(o.dropoff_address || '') + '</span></div></div>' +
      '</div>' +
      '<div class="job-meta"><span>' + esc(o.distance_km) + ' km</span><span>' + esc(o.tonnes) + ' t</span>' +
        '<span>' + esc(o.equipment_name) + '</span><span>~' + esc(M.duration(o.eta_minutes)) + '</span>' +
        '<span>' + esc(o.service_name) + '</span></div>' +
      action +
    '</article>';
  }

  function viewDriverBoard() {
    api.jobs().then(function (res) {
      var online = state.vehicle && state.vehicle.is_online;
      var cm = state.carrierMaster || {};
      var contracted = cm.status === 'signed';
      var acceptCta = function (o) {
        if (!contracted) return '<button class="btn btn-primary btn-block" disabled>Sign your carrier agreement first</button>';
        return '<button class="btn btn-primary btn-block" data-accept="' + esc(o.ref) + '">Accept &amp; sign &middot; ' + esc(o.payout) + '</button>';
      };
      shell(
        pageHead('Load board', 'Open loads for your ' + (res.vehicle ? equipmentName(res.vehicle.equipment_key) : 'unit') + '.',
          '<label class="switch"><input type="checkbox" id="online"' + (online ? ' checked' : '') + '><i></i>' +
          '<span id="online-label">' + (online ? 'Available' : 'Off duty') + '</span></label>') +
        (!contracted
          ? '<div class="notice notice-error" style="margin-bottom:16px">Your carrier agreement must be signed before you can take loads. ' +
            'It carries the terms every load runs on, and once it is signed every load you accept is confirmed in one tap.' +
            (cm.sign_url ? ' <a href="' + esc(cm.sign_url) + '">Sign it now &rarr;</a>'
                         : ' Musanga will send it to your authorised signatory.') + '</div>'
          : '') +
        (res.jobs.length
          ? '<div class="job-grid">' + res.jobs.map(function (o) {
              return jobCard(o, acceptCta(o));
            }).join('') + '</div>'
          : empty('No open loads right now', 'Loads matching your equipment appear here the moment they are booked.'))
      );

      el('#online').addEventListener('change', function (e) {
        var on = e.target.checked;
        api.setOnline(on).then(function () {
          state.vehicle.is_online = on ? 1 : 0;
          el('#online-label').textContent = on ? 'Available' : 'Off duty';
        });
      });

      M.els('[data-accept]').forEach(function (btn) {
        btn.addEventListener('click', function () {
          btn.disabled = true;
          btn.textContent = 'Accepting…';
          api.accept(btn.dataset.accept).then(function (o) {
            location.hash = '#/orders/' + o.ref;
          }).catch(function (err) {
            alert(err.message);
            route();
          });
        });
      });
    }).catch(fail);
  }

  function equipmentName(key) {
    var eq = state.config.equipment.filter(function (x) { return x.key === key; })[0];
    return eq ? eq.name : 'unit';
  }

  function viewDriverJobs() {
    api.orders().then(function (res) {
      var live = res.orders.filter(function (o) { return ['assigned', 'at_pickup', 'in_transit'].indexOf(o.status) >= 0; });
      var past = res.orders.filter(function (o) { return ['delivered', 'cancelled'].indexOf(o.status) >= 0; });
      shell(
        pageHead('My loads', live.length + ' active, ' + past.length + ' completed') +
        (live.length
          ? '<div class="job-grid">' + live.map(function (o) {
              return jobCard(o, '<a class="btn btn-dark btn-block" href="#/orders/' + esc(o.ref) + '">' + esc(o.status_label) + ' &middot; open</a>');
            }).join('') + '</div>'
          : empty('No active loads', 'Take one from the load board to get going.')) +
        '<h3 style="margin:30px 0 14px">History</h3>' +
        orderTable(past, [COL.ref, COL.route, COL.cargo, COL.vehicle, COL.status, COL.payout])
      );
    }).catch(fail);
  }

  /* --- fuel credit and cover -------------------------------------------- */
  /* Musanga advances diesel, never cash: an entitlement is issued against a
     load the carrier has already been assigned, and the balance comes off the
     settlement Musanga is already holding. Both ceilings are shown here so a
     refusal at the pump is never a surprise. */

  function entitlementCard(e, price) {
    var full = e.litres_remaining <= 0;
    return '<article class="job" data-ent="' + esc(e.order_ref) + '">' +
      '<div class="job-top">' +
        '<div><span class="muted mono">' + esc(e.order_ref) + '</span>' +
          '<div style="font-weight:600">' + esc(e.from_name) + ' &rarr; ' + esc(e.to_name) + '</div>' +
          '<div class="muted" style="font-size:.81rem">' + esc(e.distance_km) + ' km each way, fuelled out and back</div></div>' +
        '<div class="job-pay">' + e.litres_remaining + ' L</div>' +
      '</div>' +
      '<div class="job-meta"><span>' + e.litres + ' L issued</span><span>' + e.litres_drawn + ' L drawn</span>' +
        '<span>' + esc(M.kwacha(price)) + '/L</span><span>worth ' + esc(e.value) + '</span></div>' +
      (full
        ? '<p class="muted" style="margin:12px 0 0">Fully drawn. The balance is netted off this load\u2019s settlement.</p>'
        : '<div class="row2" style="margin-top:12px;align-items:end">' +
            '<label class="field" style="margin:0"><span>Litres at the pump</span>' +
              '<input class="input" type="number" min="1" step="1" max="' + e.litres_remaining + '" ' +
              'value="' + e.litres_remaining + '" data-litres="' + esc(e.order_ref) + '" inputmode="numeric"></label>' +
            '<button class="btn btn-primary" data-draw="' + esc(e.order_ref) + '">Draw diesel</button>' +
          '</div>' +
          '<label class="field" style="margin-top:10px"><span>Station (optional)</span>' +
            '<input class="input" data-station="' + esc(e.order_ref) + '" placeholder="Puma, Kitwe"></label>') +
    '</article>';
  }

  function viewFuel() {
    Promise.all([api.fuel(), api.settlements()]).then(function (r) {
      var f = r[0].facility, price = r[0].diesel_ngwee_per_litre;
      var ents = f.entitlements || [], settlements = r[1].settlements;
      var used = f.limit_ngwee ? Math.round(f.outstanding_ngwee / f.limit_ngwee * 100) : 0;

      shell(
        pageHead('Fuel & cover',
          'Diesel against loads you already hold. Musanga pays the pump, and takes it off your settlement.') +
        '<div class="tiles">' +
          '<div class="tile accent"><span>Available to draw</span><b>' + esc(f.available) + '</b>' +
            '<small>' + Math.floor(f.available_ngwee / price) + ' litres at ' + esc(M.kwacha(price)) + '/L</small></div>' +
          '<div class="tile"><span>Outstanding</span><b>' + esc(f.outstanding) + '</b>' +
            '<small>' + used + '% of your limit</small></div>' +
          '<div class="tile"><span>Facility limit</span><b>' + esc(f.limit) + '</b>' +
            '<small>' + f.completed_loads + ' completed loads on file</small></div>' +
        '</div>' +

        '<h3 style="margin:30px 0 14px">Diesel issued to your live loads</h3>' +
        '<div id="err"></div>' +
        (ents.length
          ? '<div class="job-grid">' + ents.map(function (e) { return entitlementCard(e, price); }).join('') + '</div>'
          : empty('No diesel issued right now',
                  'Every load you accept comes with the litres that corridor needs, at ' +
                  M.kwacha(price) + ' a litre.')) +

        '<h3 style="margin:30px 0 14px">Settlements</h3>' +
        (settlements.length
          ? '<div class="table-wrap"><table><thead><tr><th>Load</th><th>Settled</th>' +
              '<th class="num">Gross</th><th class="num">Fuel netted</th><th class="num">Paid to you</th>' +
            '</tr></thead><tbody>' +
            settlements.map(function (x) {
              return '<tr data-ref="' + esc(x.ref) + '"><td><b class="mono">' + esc(x.ref) + '</b></td>' +
                '<td>' + esc(M.when(x.settled_at)) + '</td>' +
                '<td class="num">' + esc(x.gross) + '</td>' +
                '<td class="num">' + (x.fuel_deduction_ngwee ? '&minus;' + esc(x.fuel_deduction) : '&mdash;') + '</td>' +
                '<td class="num"><b>' + esc(x.net) + '</b></td></tr>';
            }).join('') +
            '</tbody></table></div>' +
            '<p class="muted" style="margin-top:12px">Never more than half a load\u2019s payout goes to fuel. ' +
            'The rest of the balance rolls to your next settlement.</p>'
          : empty('Nothing settled yet', 'Deliver a load and the settlement, less any diesel, shows here.'))
      );

      M.els('[data-draw]').forEach(function (btn) {
        btn.addEventListener('click', function () {
          var ref = btn.dataset.draw;
          var litres = M.el('[data-litres="' + ref + '"]').value;
          var station = M.el('[data-station="' + ref + '"]').value;
          btn.disabled = true;
          btn.textContent = 'Drawing…';
          api.fuelDraw(ref, { litres: litres, station: station || null }).then(function () {
            route();
          }).catch(function (err) {
            el('#err').innerHTML = '<div class="notice notice-error">' + esc(err.message) + '</div>';
            btn.disabled = false;
            btn.textContent = 'Draw diesel';
            window.scrollTo(0, 0);
          });
        });
      });
    }).catch(fail);
  }

  function viewEarnings() {
    api.earnings().then(function (res) {
      var rows = res.jobs.map(function (j) {
        return '<tr data-ref="' + esc(j.ref) + '"><td><b class="mono">' + esc(j.ref) + '</b></td>' +
               '<td>' + esc(M.when(j.created_at)) + '</td>' +
               '<td><span class="pill pill-' + esc(j.status) + '">' + esc(j.status) + '</span></td>' +
               '<td class="num">' + esc(j.payout) + '</td></tr>';
      }).join('');
      shell(
        pageHead('Earnings', 'Musanga keeps 15% of the net freight. The rest is yours.') +
        '<div class="tiles">' +
          '<div class="tile accent"><span>Paid to you</span><b>' + esc(res.net_paid) + '</b><small>' + res.completed + ' delivered loads, after fuel</small></div>' +
          '<div class="tile"><span>In progress</span><b>' + esc(res.pending) + '</b><small>settles on delivery</small></div>' +
          '<div class="tile"><span>Fuel netted off</span><b>' + esc(res.fuel_netted) + '</b><small>' + esc(res.fuel_outstanding) + ' still outstanding</small></div>' +
          '<div class="tile"><span>Gross earned</span><b>' + esc(res.paid) + '</b><small>before diesel</small></div>' +
        '</div>' +
        (res.jobs.length
          ? '<div class="table-wrap"><table><thead><tr><th>Reference</th><th>Date</th><th>Status</th><th class="num">Payout</th></tr></thead><tbody>' + rows + '</tbody></table></div>'
          : empty('No earnings yet', 'Accept your first load to start earning.'))
      );
    }).catch(fail);
  }

  /* ====================================================================== */
  /* OPS                                                                    */
  /* ====================================================================== */

  function viewOpsDispatch() {
    Promise.all([api.summary(), api.orders(), api.drivers(), api.hires()]).then(function (r) {
      var s = r[0], orders = r[1].orders, drivers = r[2].drivers, hires = r[3].hires;
      var unassigned = orders.filter(function (o) { return o.status === 'placed' && !o.driver_id; });

      // Only offer drivers whose vehicle matches the job's vehicle class.
      function driverOptionsFor(equipmentKey) {
        var eligible = drivers.filter(function (d) { return d.equipment_key === equipmentKey; });
        if (!eligible.length) return '';
        eligible.sort(function (a, b) { return (b.is_online - a.is_online) || (a.active_jobs - b.active_jobs); });
        return eligible.map(function (d) {
          return '<option value="' + d.id + '">' + esc(d.name) + ' — ' + esc(d.plate || '—') +
                 (d.is_online ? ' · available' : ' · off duty') + ' · ' + d.active_jobs + ' active</option>';
        }).join('');
      }

      var queue = unassigned.length
        ? '<div class="table-wrap"><table><thead><tr><th>Reference</th><th>Corridor</th><th>Cargo</th><th>Equipment</th><th class="num">Value</th><th>Dispatch to</th></tr></thead><tbody>' +
          unassigned.map(function (o) {
            return '<tr data-ref="' + esc(o.ref) + '">' +
              '<td><b class="mono">' + esc(o.ref) + '</b><span class="sub">' + esc(M.ago(o.created_at)) + '</span></td>' +
              '<td>' + esc(o.from_name) + ' &rarr; ' + esc(o.to_name) + '<span class="sub">' + esc(o.distance_km) + ' km</span></td>' +
              '<td>' + esc(o.commodity_name) + '<span class="sub">' + esc(o.tonnes) + ' t</span></td>' +
              '<td>' + esc(o.equipment_name) + '</td><td class="num">' + esc(o.total) + '</td>' +
              '<td>' + (function () {
                var opts = driverOptionsFor(o.equipment_key);
                if (!opts) return '<span class="muted">No ' + esc(o.equipment_name) + ' carrier registered</span>';
                return '<div style="display:flex;gap:6px">' +
                  '<select class="input" style="padding:6px 10px;font-size:.82rem" data-driver-for="' + esc(o.ref) + '">' + opts + '</select>' +
                  '<button class="btn btn-primary btn-sm" data-assign="' + esc(o.ref) + '">Assign</button></div>';
              })() + '</td></tr>';
          }).join('') + '</tbody></table></div>'
        : empty('Dispatch queue is clear', 'Every booked load has a carrier.');

      shell(
        pageHead('Control', 'Live view of the whole network.',
          '<a class="btn btn-ghost btn-sm" href="#/orders">All loads</a>') +
        '<div class="tiles">' +
          '<div class="tile accent"><span>Awaiting carrier</span><b>' + s.unassigned + '</b><small>needs dispatch now</small></div>' +
          '<div class="tile"><span>Loads open</span><b>' + s.open_jobs + '</b><small>on the corridors</small></div>' +
          '<div class="tile"><span>Carriers available</span><b>' + s.drivers_online + '</b><small>of ' + drivers.length + ' registered</small></div>' +
          '<div class="tile"><span>Tonnage delivered</span><b>' + s.tonnes_moved.toFixed(0) + ' t</b><small>all time</small></div>' +
          '<div class="tile"><span>Tonne-kilometres</span><b>' + Math.round(s.tonne_km / 1000) + 'k</b><small>booked to date</small></div>' +
          '<div class="tile"><span>On-time</span><b>' + s.on_time_pct + '%</b><small>delivered within transit estimate</small></div>' +
          '<div class="tile"><span>Machines on hire</span><b>' + s.hires_open + '</b><small>' + s.hires_pending + ' awaiting confirmation</small></div>' +
          '<div class="tile' + ((s.quotes_signed || 0) > 0 ? ' accent' : '') + '"><span>Quotes out</span><b>' + (s.quotes_pending || 0) + '</b><small>' + (s.quotes_signed || 0) + ' signed, need booking · <a href="#/quotes">open</a></small></div>' +
          '<div class="tile"><span>Freight GMV</span><b>' + esc(M.kwacha(s.gmv_ngwee)) + '</b><small>gross booked</small></div>' +
          '<div class="tile"><span>Hire GMV</span><b>' + esc(M.kwacha(s.hire_gmv_ngwee)) + '</b><small>gross booked</small></div>' +
          '<div class="tile"><span>Net revenue</span><b>' + esc(M.kwacha(s.revenue_ngwee)) + '</b><small>freight, after carrier payouts</small></div>' +
        '</div>' +
        '<h3 style="margin:8px 0 16px">Dispatch queue</h3>' + queue +
        (function () {
          var pending = hires.filter(function (h) { return h.status === 'requested'; });
          if (!pending.length) return '';
          return '<h3 style="margin:32px 0 16px">Hires awaiting confirmation</h3>' + hireTable(pending);
        })()
      );

      M.els('[data-assign]').forEach(function (btn) {
        btn.addEventListener('click', function (e) {
          e.stopPropagation();
          var ref = btn.dataset.assign;
          var sel = el('[data-driver-for="' + ref + '"]');
          btn.disabled = true;
          btn.textContent = '…';
          api.assign(ref, Number(sel.value)).then(route).catch(function (err) {
            alert(err.message);
            route();
          });
        });
      });
    }).catch(fail);
  }

  function viewOpsOrders() {
    api.orders().then(function (res) {
      var filter = (location.hash.split('?')[1] || '').replace('status=', '') || 'all';
      var shown = filter === 'all' ? res.orders : res.orders.filter(function (o) { return o.status === filter; });
      var tabs = ['all', 'placed', 'assigned', 'in_transit', 'delivered', 'cancelled'].map(function (k) {
        return '<button data-filter="' + k + '" aria-pressed="' + (k === filter) + '">' +
               esc(k === 'all' ? 'All' : k.replace('_', ' ')) + '</button>';
      }).join('');
      shell(
        pageHead('All loads', res.orders.length + ' loads across the network') +
        '<div class="toolbar">' + tabs + '</div>' +
        orderTable(shown, [COL.ref, COL.route, COL.cargo, COL.vehicle, COL.driver, COL.status, COL.total])
      );
      M.els('[data-filter]').forEach(function (b) {
        b.addEventListener('click', function () { location.hash = '#/orders?status=' + b.dataset.filter; });
      });
    }).catch(fail);
  }

  function viewOpsDrivers() {
    api.drivers().then(function (res) {
      var rows = res.drivers.map(function (d) {
        return '<tr><td><b>' + esc(d.name) + '</b><span class="sub">' + esc(d.phone) + '</span></td>' +
          '<td>' + esc(d.equipment_name) + '<span class="sub mono">' + esc(d.plate || '—') + '</span></td>' +
          '<td>' + esc(d.zone_name) + '</td>' +
          '<td><span class="pill ' + (d.is_online ? 'pill-delivered' : 'pill-placed') + '">' + (d.is_online ? 'Available' : 'Off duty') + '</span></td>' +
          '<td class="num">' + d.active_jobs + '</td><td class="num">' + d.completed + '</td></tr>';
      }).join('');
      shell(
        pageHead('Carriers', res.drivers.length + ' registered transport partners') +
        (res.drivers.length
          ? '<div class="table-wrap"><table><thead><tr><th>Carrier</th><th>Equipment</th><th>Home base</th><th>Status</th><th class="num">Active</th><th class="num">Completed</th></tr></thead><tbody>' + rows + '</tbody></table></div>'
          : empty('No carriers yet', 'Transport partners appear here once they register.'))
      );
    }).catch(fail);
  }

  function viewOpsQuotes() {
    api.quotes().then(function (res) {
      var quotes = res.quotes || [];
      var buckets = { signed: [], pending: [], booked: [], closed: [] };
      quotes.forEach(function (q) {
        if (q.status === 'signed') buckets.signed.push(q);
        else if (q.status === 'booked') buckets.booked.push(q);
        else if (q.status === 'void' || q.status === 'expired' || q.status === 'declined') buckets.closed.push(q);
        else buckets.pending.push(q);
      });

      function statusPill(q) {
        var color = ({sent:'placed', viewed:'placed', accepted:'assigned', signed:'delivered',
                      booked:'delivered', void:'cancelled', expired:'cancelled'}[q.status] || 'placed');
        return '<span class="pill pill-' + color + '">' + esc(q.status_label || q.status) + '</span>';
      }
      function reqPills(q) {
        var bits = [];
        if (q.require_signature) {
          bits.push('<span class="pill ' + (q.signed_at ? 'pill-delivered' : 'pill-placed') + '" style="font-size:.7rem">' + (q.signed_at ? '✓ signed' : 'awaiting sig') + '</span>');
        }
        if (q.require_payment) {
          bits.push('<span class="pill ' + (q.paid_at ? 'pill-delivered' : 'pill-placed') + '" style="font-size:.7rem">' + (q.paid_at ? '✓ paid' : 'awaiting payment') + '</span>');
        }
        if (q.conditions && q.conditions.length) {
          var met = q.conditions_met || 0, tot = q.conditions.length;
          bits.push('<span class="pill ' + (met === tot ? 'pill-delivered' : 'pill-placed') + '" style="font-size:.7rem">' +
                    (met === tot ? '✓' : '') + ' ' + met + '/' + tot + ' conditions</span>');
        }
        if (q.slot_count > 1) {
          bits.push('<span class="pill pill-assigned" style="font-size:.7rem">' + q.slot_count + '-truck pkg</span>');
        }
        if (typeof q.profit_lock_pct === 'number' && q.carrier_ngwee) {
          var pct = q.profit_lock_pct;
          var cls = pct >= 30 ? 'pill-delivered' : (pct >= 20 ? 'pill-placed' : 'pill-cancelled');
          bits.push('<span class="pill ' + cls + '" style="font-size:.7rem" title="Broker take: ' + esc(q.broker_take) + ' per slot">lock ' + pct.toFixed(1) + '%</span>');
        }
        if (q.document) bits.push('<span class="pill pill-placed" style="font-size:.7rem">📎 doc</span>');
        var eng = q.engagement || {};
        if (eng.count) {
          var mins = Math.max(1, Math.round((eng.seconds || 0) / 60));
          var opened = eng.last_opened_at ? M.ago(eng.last_opened_at) : '';
          var label = '👁 ' + eng.count + ' open' + (eng.count === 1 ? '' : 's');
          if (eng.readers > 1) label += ' · ' + eng.readers + ' readers';
          if (eng.seconds) label += ' · ' + mins + 'm read';
          if (eng.downloads) label += ' · 📎 ' + eng.downloads;
          bits.push('<span class="pill pill-assigned" style="font-size:.7rem" title="Last opened ' + esc(opened) + '">' + esc(label) + '</span>');
        } else if (q.status !== 'void' && q.status !== 'expired') {
          bits.push('<span class="pill pill-cancelled" style="font-size:.7rem">Never opened</span>');
        }
        return '<div style="display:flex;gap:4px;margin-top:4px;flex-wrap:wrap">' + bits.join('') + '</div>';
      }

      function condRow(q) {
        if (!q.conditions || !q.conditions.length) return '';
        var pending = q.conditions.filter(function (c) { return !c.met; });
        if (!pending.length) return '';
        return '<tr><td colspan="6" style="background:var(--ink-50);padding:8px 12px">' +
          '<div style="display:flex;gap:8px;flex-wrap:wrap;align-items:center">' +
            '<span class="muted" style="font-size:.78rem">Conditions on ' + esc(q.ref) + ':</span>' +
            pending.map(function (c) {
              return '<button class="btn btn-ghost btn-sm" data-cond-tick="' + esc(q.ref) + '" data-cond-label="' + esc(c.label) + '">' +
                '☐ ' + esc(c.label) + '</button>';
            }).join('') +
          '</div></td></tr>';
      }
      function canMarkPaid(q) {
        if (q.paid_at) return false;
        if (q.status === 'booked' || q.status === 'void' || q.status === 'expired') return false;
        return q.require_payment && q.conditions_pending === 0;
      }
      function table(list, showActions) {
        if (!list.length) return empty('None here', 'Quotes will appear as soon as they are sent.');
        var rows = list.map(function (q) {
          var valueCell = (q.slot_count > 1)
            ? esc(q.package_total) + '<span class="sub">' + q.slot_count + ' × ' + esc(q.per_slot) + ' · ' + esc(q.payment_label) + '</span>'
            : esc(q.total) + '<span class="sub">' + esc(q.payment_label) + '</span>';
          var actions = '';
          if (showActions) {
            var canConfirm = (q.status === 'signed') || (q.require_payment && q.paid_at && q.conditions_pending === 0);
            actions =
              '<div style="display:flex;gap:6px;flex-wrap:wrap;justify-content:flex-end">' +
              (canConfirm
                ? '<button class="btn btn-primary btn-sm" data-confirm="' + esc(q.ref) + '">Confirm &amp; book</button>' : '') +
              (canMarkPaid(q)
                ? '<button class="btn btn-primary btn-sm" data-paid="' + esc(q.ref) + '">Mark paid</button>' : '') +
              (q.status !== 'booked' && q.status !== 'void'
                ? '<button class="btn btn-ghost btn-sm" data-remind="' + esc(q.ref) + '">Remind' +
                    (q.reminder_count ? ' <span class="muted">(' + q.reminder_count + ')</span>' : '') + '</button>' : '') +
              (q.order_ref
                ? '<a class="btn btn-ghost btn-sm" href="#/orders/' + esc(q.order_ref) + '">Open load</a>'
                : '<a class="btn btn-ghost btn-sm" href="' + esc(q.url) + '" target="_blank">Preview</a>') +
              (q.status !== 'booked' && q.status !== 'void'
                ? '<button class="btn btn-ghost btn-sm" data-void-q="' + esc(q.ref) + '">Void</button>' : '') +
              '</div>';
          }
          return '<tr data-ref-quote="' + esc(q.ref) + '">' +
            '<td><b class="mono">' + esc(q.ref) + '</b><span class="sub">' + esc(M.ago(q.created_at)) + '</span></td>' +
            '<td>' + esc(q.counterparty) + '<span class="sub">' + esc(q.counterparty_email || q.counterparty_phone || '') + '</span></td>' +
            '<td>' + esc(q.from_name) + ' &rarr; ' + esc(q.to_name) + '<span class="sub">' + esc(q.commodity_name) + ' · ' + esc(q.tonnes) + ' t</span></td>' +
            '<td class="num">' + valueCell + '</td>' +
            '<td>' + statusPill(q) + reqPills(q) + '</td>' +
            '<td>' + actions + '</td>' +
          '</tr>' + condRow(q);
        }).join('');
        return '<div class="table-wrap"><table><thead><tr>' +
          '<th>Reference</th><th>Customer</th><th>Corridor</th><th class="num">Value</th><th>Status</th><th></th>' +
          '</tr></thead><tbody>' + rows + '</tbody></table></div>';
      }

      shell(
        pageHead('Quotes', 'Sent to a customer; not yet a load.',
          '<a class="btn btn-primary btn-sm" href="#/book">New rate</a>') +
        (buckets.signed.length
          ? '<h3 style="margin:8px 0 16px">Signed — ready to book</h3>' + table(buckets.signed, true)
          : '') +
        '<h3 style="margin:32px 0 16px">Out with a customer</h3>' + table(buckets.pending, true) +
        (buckets.booked.length
          ? '<h3 style="margin:32px 0 16px">Booked</h3>' + table(buckets.booked, true) : '') +
        (buckets.closed.length
          ? '<h3 style="margin:32px 0 16px">Closed</h3>' + table(buckets.closed, false) : '')
      );

      M.els('[data-confirm]').forEach(function (btn) {
        btn.addEventListener('click', function () {
          btn.disabled = true;
          btn.textContent = 'Booking…';
          api.confirmQuote(btn.dataset.confirm).then(function (q) {
            if (q.order_ref) location.hash = '#/orders/' + q.order_ref;
            else route();
          }).catch(function (err) { alert(err.message); route(); });
        });
      });
      M.els('[data-void-q]').forEach(function (btn) {
        btn.addEventListener('click', function () {
          if (!confirm('Void quote ' + btn.dataset.voidQ + '?')) return;
          api.voidQuote(btn.dataset.voidQ).then(route).catch(function (err) { alert(err.message); });
        });
      });
      M.els('[data-remind]').forEach(function (btn) {
        btn.addEventListener('click', function () {
          btn.disabled = true;
          btn.textContent = 'Reminding…';
          api.remindQuote(btn.dataset.remind).then(function (r) {
            var msg = r.mail && r.mail.ok ? 'Reminder sent' : ('Reminder logged; email: ' + (r.mail && r.mail.note || 'off'));
            btn.textContent = '✓';
            setTimeout(route, 500);
            alert(msg);
          }).catch(function (err) { alert(err.message); route(); });
        });
      });
      M.els('[data-cond-tick]').forEach(function (btn) {
        btn.addEventListener('click', function () {
          var note = prompt('Reference / note for "' + btn.dataset.condLabel + '" (optional)') || '';
          btn.disabled = true;
          api.tickCondition(btn.dataset.condTick, {
            label: btn.dataset.condLabel, met: true, note: note
          }).then(function () { route(); })
            .catch(function (err) { alert(err.message); btn.disabled = false; });
        });
      });
      M.els('[data-paid]').forEach(function (btn) {
        btn.addEventListener('click', function () {
          var ref = prompt('Payment reference (wire trace / receipt no.):');
          if (ref === null) return;
          var proof = prompt('Note (bank, account, anything for the audit trail):') || '';
          btn.disabled = true;
          btn.textContent = 'Recording…';
          api.markPaidQuote(btn.dataset.paid, {
            payment_ref: (ref || '').trim(), proof_note: proof.trim()
          }).then(function () { route(); })
            .catch(function (err) { alert(err.message); route(); });
        });
      });
      // A row opens the full trail; clicks on its own buttons/links are left
      // to their own handlers.
      M.els('[data-ref-quote]').forEach(function (tr) {
        tr.style.cursor = 'pointer';
        tr.addEventListener('click', function (e) {
          if (e.target.closest('button, a, input')) return;
          location.hash = '#/quotes/' + tr.dataset.refQuote;
        });
      });
    }).catch(fail);
  }

  /* ====================================================================== */
  /* QUOTE DETAIL (ops) — the DocSend-style trail behind a single rate      */
  /* ====================================================================== */

  // Event codes the API logs against a quote, in plain words for the trail.
  var QUOTE_EVENT_LABELS = {
    sent: 'Rate sent', opened: 'Opened the link', reminded: 'Reminder sent',
    signed: 'Signed', paid: 'Payment recorded', downloaded: 'Downloaded the document',
    condition_met: 'Condition met', condition_unmet: 'Condition reopened',
    released: 'Reservation released', accepted: 'Accepted', booked: 'Booked as a load',
    void: 'Voided'
  };
  function quoteEventLabel(code) {
    return QUOTE_EVENT_LABELS[code] || (code || '').replace(/_/g, ' ');
  }

  function quoteStatusPill(q) {
    var color = ({sent:'placed', viewed:'placed', accepted:'assigned', signed:'delivered',
                  booked:'delivered', void:'cancelled', expired:'cancelled', declined:'cancelled'}[q.status] || 'placed');
    return '<span class="pill pill-' + color + '">' + esc(q.status_label || q.status) + '</span>';
  }

  function quoteEngagementPanel(q) {
    var e = q.engagement || { views: [], count: 0 };
    if (!e.count) {
      return '<section class="panel"><h3>Engagement</h3>' +
        '<p class="muted">' + (q.status === 'sent'
          ? 'Sent, but not opened yet.'
          : 'Not opened yet.') + '</p></section>';
    }
    var rows = (e.views || []).map(function (v) {
      var last = v.signed ? 'signed' : (v.downloaded ? 'copied' : '');
      return '<tr>' +
        '<td>' + esc(v.viewer_email || 'Anonymous') +
          '<span class="sub mono">' + esc(v.ip || '') + '</span></td>' +
        '<td>' + esc(M.ago(v.opened_at)) + '</td>' +
        '<td class="num">' + esc(minutes(v.seconds)) + '</td>' +
        '<td class="num">' + esc(last) + '</td>' +
      '</tr>';
    }).join('');
    return '<section class="panel"><h3>Engagement</h3>' +
      '<div class="tiles tiles-tight">' +
        '<div class="tile"><span>Opens</span><b>' + e.count + '</b><small>' +
          e.readers + ' reader' + (e.readers === 1 ? '' : 's') + '</small></div>' +
        '<div class="tile"><span>Time on it</span><b>' + esc(minutes(e.seconds)) + '</b><small>total</small></div>' +
        '<div class="tile"><span>Copies</span><b>' + (e.downloads || 0) + '</b><small>document taken</small></div>' +
      '</div>' +
      '<div class="table-wrap"><table><thead><tr><th>Reader</th><th>Opened</th>' +
        '<th class="num">Time</th><th class="num"></th>' +
      '</tr></thead><tbody>' + rows + '</tbody></table></div></section>';
  }

  // Broker take, pass-throughs and where the rate lands against the 30% floor.
  function quoteMoneyPanel(q) {
    var rows = [];
    if (q.slot_count > 1) {
      rows.push(['Per load', esc(q.per_slot)]);
      rows.push(['Package (' + q.slot_count + ' loads)', '<b>' + esc(q.package_total) + '</b>']);
    } else {
      rows.push(['Shipper price', '<b>' + esc(q.total) + '</b>']);
    }
    if (q.carrier) rows.push(['Carrier ask', esc(q.carrier)]);
    if (q.pass_through) rows.push(['Pass-throughs', esc(q.pass_through)]);
    rows.push(['Broker take (per load)', '<b>' + esc(q.broker_take) + '</b>']);
    var lock = '';
    if (typeof q.profit_lock_pct === 'number' && q.carrier_ngwee) {
      var pct = q.profit_lock_pct;
      var cls = pct >= 30 ? 'pill-delivered' : (pct >= 20 ? 'pill-placed' : 'pill-cancelled');
      lock = '<div style="margin-top:10px"><span class="pill ' + cls + '">Profit lock ' + pct.toFixed(1) + '%</span> ' +
        '<span class="muted" style="font-size:.8rem">against the 30% floor</span></div>';
    }
    return '<section class="panel"><h3>Rate &amp; margin</h3>' +
      '<dl class="kv">' + rows.map(function (r) {
        return '<dt>' + r[0] + '</dt><dd class="num">' + r[1] + '</dd>';
      }).join('') + '</dl>' + lock + '</section>';
  }

  function quoteGatePanel(q) {
    var bits = [];
    if (q.require_signature) {
      bits.push('<div class="gate-row">' +
        '<span class="pill ' + (q.signed_at ? 'pill-delivered' : 'pill-placed') + '">' +
        (q.signed_at ? '✓ signed' : 'awaiting signature') + '</span>' +
        (q.signed_at ? '<span class="sub">' + esc(q.signer_name || '') +
          (q.signer_email ? ' · ' + esc(q.signer_email) : '') + '</span>' : '') + '</div>');
    }
    if (q.require_payment) {
      bits.push('<div class="gate-row">' +
        '<span class="pill ' + (q.paid_at ? 'pill-delivered' : 'pill-placed') + '">' +
        (q.paid_at ? '✓ paid' : 'awaiting payment') + '</span>' +
        (q.paid_at ? '<span class="sub">' + esc(M.when(q.paid_at)) +
          (q.payment_ref ? ' · ' + esc(q.payment_ref) : '') + '</span>' : '') + '</div>');
    }
    if (q.reserve_by && !q.paid_at && q.status !== 'void' && q.status !== 'booked') {
      bits.push('<div class="gate-row"><span class="muted">Reserved until ' + esc(M.when(q.reserve_by)) + '</span></div>');
    }
    if (q.released_at) {
      bits.push('<div class="gate-row"><span class="pill pill-cancelled">reservation released</span>' +
        '<span class="sub">' + esc(M.when(q.released_at)) + '</span></div>');
    }
    // Conditions checklist with inline tick buttons.
    if (q.conditions && q.conditions.length) {
      bits.push('<div style="margin-top:10px"><div class="muted" style="font-size:.8rem;margin-bottom:6px">Pre-payment conditions</div>' +
        q.conditions.map(function (c) {
          return '<div class="gate-row" style="justify-content:space-between">' +
            '<span>' + (c.met ? '✓' : '☐') + ' ' + esc(c.label) +
              (c.met && c.met_by ? ' <span class="sub">· ' + esc(c.met_by) + (c.met_at ? ' · ' + esc(M.ago(c.met_at)) : '') + '</span>' : '') +
            '</span>' +
            (c.met
              ? ''
              : '<button class="btn btn-ghost btn-sm" data-cond-tick="' + esc(q.ref) + '" data-cond-label="' + esc(c.label) + '">Tick</button>') +
          '</div>';
        }).join('') + '</div>');
    }
    if (!bits.length) return '';
    return '<section class="panel"><h3>Gate</h3>' + bits.join('') + '</section>';
  }

  function quoteActions(q) {
    var acts = [];
    var canConfirm = (q.require_signature ? q.signed_at : true) &&
                     (q.require_payment ? (q.paid_at && q.conditions_pending === 0) : true) &&
                     q.status !== 'booked' && q.status !== 'void' && q.status !== 'expired' && !q.order_ref;
    if (canConfirm) acts.push('<button class="btn btn-primary" data-q-confirm="' + esc(q.ref) + '">Confirm &amp; book</button>');
    if (!q.paid_at && q.require_payment && q.conditions_pending === 0 &&
        q.status !== 'booked' && q.status !== 'void' && q.status !== 'expired') {
      acts.push('<button class="btn btn-primary" data-q-paid="' + esc(q.ref) + '">Mark paid</button>');
    }
    if (q.order_ref) acts.push('<a class="btn btn-ghost" href="#/orders/' + esc(q.order_ref) + '">Open load</a>');
    else acts.push('<a class="btn btn-ghost" href="' + esc(q.url) + '" target="_blank">Preview customer view</a>');
    if (q.status !== 'booked' && q.status !== 'void') {
      acts.push('<button class="btn btn-ghost" data-q-remind="' + esc(q.ref) + '">Remind' +
        (q.reminder_count ? ' <span class="muted">(' + q.reminder_count + ')</span>' : '') + '</button>');
      acts.push('<button class="btn btn-ghost" data-q-void="' + esc(q.ref) + '">Void</button>');
    }
    return '<div style="display:flex;gap:8px;flex-wrap:wrap;margin-top:6px">' + acts.join('') + '</div>';
  }

  function viewOpsQuote(ref) {
    api.quoteRow(ref).then(function (q) {
      function refresh() { viewOpsQuote(ref); }
      shell(
        pageHead('Rate ' + q.ref, q.from_name + ' → ' + q.to_name + ' · ' + q.counterparty,
          quoteStatusPill(q) + ' <a class="btn btn-ghost btn-sm" style="margin-left:8px" href="#/quotes">Back</a>') +
        '<div class="kyc-grid">' +
          '<div>' +
            '<section class="panel">' +
              '<div class="muted" style="font-size:.8rem">' + esc(q.equipment_name) + ' · ' + esc(q.tonnes) + ' t · ' + esc(q.commodity_name) + '</div>' +
              (q.note ? '<p style="margin:10px 0 0">' + esc(q.note) + '</p>' : '') +
              (q.document ? '<p class="muted" style="margin:10px 0 0;font-size:.85rem">📎 ' + esc(q.document.name) + '</p>' : '') +
              quoteActions(q) +
            '</section>' +
            quoteEngagementPanel(q) +
          '</div>' +
          '<aside>' +
            quoteMoneyPanel(q) +
            quoteGatePanel(q) +
            '<section class="panel"><h3>Audit trail</h3>' +
              ((q.events && q.events.length)
                ? '<ol class="timeline">' + q.events.map(function (e) {
                    return '<li><b>' + esc(quoteEventLabel(e.event)) + '</b>' +
                      (e.actor ? '<span>' + esc(e.actor) + '</span>' : '') +
                      (e.note ? '<span class="sub">' + esc(e.note) + '</span>' : '') +
                      (e.ip ? '<span class="sub mono">' + esc(e.ip) + '</span>' : '') +
                      '<span class="sub">' + esc(M.when(e.created_at)) + '</span></li>';
                  }).join('') + '</ol>'
                : '<p class="muted">Nothing logged yet.</p>') +
            '</section>' +
          '</aside>' +
        '</div>'
      );

      var cb = el('[data-q-confirm]');
      if (cb) cb.addEventListener('click', function () {
        cb.disabled = true; cb.textContent = 'Booking…';
        api.confirmQuote(ref).then(function (r) {
          if (r.order_ref) location.hash = '#/orders/' + r.order_ref; else refresh();
        }).catch(function (err) { alert(err.message); refresh(); });
      });
      var pb = el('[data-q-paid]');
      if (pb) pb.addEventListener('click', function () {
        var pref = prompt('Payment reference (wire trace / receipt no.):');
        if (pref === null) return;
        var proof = prompt('Note (bank, account, anything for the audit trail):') || '';
        pb.disabled = true; pb.textContent = 'Recording…';
        api.markPaidQuote(ref, { payment_ref: (pref || '').trim(), proof_note: proof.trim() })
          .then(refresh).catch(function (err) { alert(err.message); refresh(); });
      });
      var rb = el('[data-q-remind]');
      if (rb) rb.addEventListener('click', function () {
        rb.disabled = true; rb.textContent = 'Reminding…';
        api.remindQuote(ref).then(function (r) {
          alert(r.mail && r.mail.ok ? 'Reminder sent' : ('Reminder logged; email: ' + (r.mail && r.mail.note || 'off')));
          refresh();
        }).catch(function (err) { alert(err.message); refresh(); });
      });
      var vb = el('[data-q-void]');
      if (vb) vb.addEventListener('click', function () {
        if (!confirm('Void quote ' + ref + '?')) return;
        api.voidQuote(ref).then(refresh).catch(function (err) { alert(err.message); });
      });
      M.els('[data-cond-tick]').forEach(function (btn) {
        btn.addEventListener('click', function () {
          var note = prompt('Reference / note for "' + btn.dataset.condLabel + '" (optional)') || '';
          btn.disabled = true;
          api.tickCondition(btn.dataset.condTick, { label: btn.dataset.condLabel, met: true, note: note })
            .then(refresh).catch(function (err) { alert(err.message); btn.disabled = false; });
        });
      });
    }).catch(fail);
  }

  /* ====================================================================== */
  /* ORDER DETAIL (all roles)                                               */
  /* ====================================================================== */

  var NEXT_ACTION = {
    assigned:   { status: 'at_pickup',  label: 'Arrived at load-out' },
    at_pickup:  { status: 'in_transit', label: 'Loaded — depart' },
    in_transit: { status: 'delivered',  label: 'Offloaded — mark delivered' }
  };

  function fuelPanel(o, role) {
    // Only the carrier running the load can draw against it, and only while
    // the entitlement is open - once the load settles, the diesel is netted.
    var f = o.fuel;
    if (!f || role !== 'driver' || o.driver_id !== state.user.id) return '';
    var open = f.status === 'open' && f.litres_remaining > 0;
    return '<div class="panel" style="margin-top:18px">' +
      '<h3>Diesel for this load</h3>' +
      '<dl class="kv">' +
        '<dt>Issued</dt><dd>' + f.litres + ' L &middot; ' + esc(f.value) + '</dd>' +
        '<dt>Drawn</dt><dd>' + f.litres_drawn + ' L &middot; ' + esc(f.drawn_value) + '</dd>' +
        '<dt>Left</dt><dd>' + f.litres_remaining + ' L</dd>' +
      '</dl>' +
      (open
        ? '<div id="fuel-err"></div>' +
          '<div class="row2" style="margin-top:12px;align-items:end">' +
            '<label class="field" style="margin:0"><span>Litres at the pump</span>' +
              '<input class="input" type="number" id="fuel-litres" min="1" step="1" max="' + f.litres_remaining + '" value="' + f.litres_remaining + '" inputmode="numeric"></label>' +
            '<button class="btn btn-primary" id="fuel-draw">Draw diesel</button>' +
          '</div>'
        : '<p class="muted" style="margin:0">' +
            (f.status === 'open' ? 'Fully drawn.' : 'Closed and netted off your settlement.') +
          '</p>') +
      '<p class="muted" style="margin:12px 0 0;font-size:.81rem">' +
        'What this corridor burns in your equipment, out and back. Nothing is advanced in cash.</p>' +
    '</div>';
  }

  // The per-load contract. Acceptance on the platform is itself the carrier's
  // signature to it, under the carrier agreement, so this reads as a receipt of
  // a binding document rather than a to-do.
  function rateConfirmationPanel(o, role) {
    var rc = o.rate_confirmation;
    if (!rc || (role !== 'driver' && role !== 'ops')) return '';
    return '<div class="panel" style="margin-top:18px">' +
      '<h3>Rate confirmation</h3>' +
      '<dl class="kv">' +
        '<dt>Reference</dt><dd class="mono">' + esc(rc.ref) + '</dd>' +
        '<dt>Status</dt><dd>Accepted on the platform</dd>' +
        (rc.body_hash ? '<dt>Document hash</dt><dd class="mono" style="font-size:.72rem;word-break:break-all">' + esc(rc.body_hash.slice(0, 32)) + '&hellip;</dd>' : '') +
      '</dl>' +
      '<p class="muted" style="margin:8px 0 0;font-size:.81rem">' +
        'Payout and terms for this load, bound under your carrier agreement. ' +
        'The time, account and address of acceptance are its signature.</p>' +
      '<a class="btn btn-ghost btn-sm" style="margin-top:12px" href="#/agreements/' + esc(rc.ref) + '">View document</a>' +
    '</div>';
  }

  /* ====================================================================== */
  /* DOCUMENTS, DROPS, WEIGHTS AND TRACKING                                 */
  /* ====================================================================== */

  // The document register. This is the panel that decides whether a truck
  // moves, so it leads with what is outstanding rather than what is done.
  function documentPanel(o, role) {
    var d = o.documents;
    if (!d || !d.total) return '';
    var canFile = role === 'ops' ||
                  (role === 'shipper' && o.shipper_id === state.user.id) ||
                  (role === 'driver' && o.driver_id === state.user.id);

    var byStage = {};
    d.items.forEach(function (item) {
      (byStage[item.stage] = byStage[item.stage] || []).push(item);
    });

    var groups = ['booking', 'loading', 'border', 'delivery'].filter(function (s) {
      return byStage[s];
    }).map(function (stage) {
      var rows = byStage[stage].map(function (item) {
        var filed = item.status === 'filed' || item.status === 'waived';
        return '<li class="doc' + (filed ? ' doc-filed' : '') + '">' +
          '<i></i>' +
          '<div>' +
            '<b>' + esc(item.name) + '</b>' +
            '<span>' + esc(item.owner_label) +
              (item.reference ? ' &middot; ' + esc(item.reference) : '') +
              (item.status === 'waived' ? ' &middot; waived' : '') +
              (item.note && !filed ? '<br>' + esc(item.note) : '') +
            '</span>' +
          '</div>' +
          (filed || !canFile ? ''
            : '<button class="btn btn-ghost btn-sm" data-doc="' + esc(item.doc_key) + '">File</button>') +
        '</li>';
      }).join('');
      return '<div class="doc-stage"><h4>' + esc(byStage[stage][0].stage_label) + '</h4>' +
             '<ul class="doc-list">' + rows + '</ul></div>';
    }).join('');

    return '<div class="panel" style="margin-top:18px">' +
      '<div class="panel-head">' +
        '<h3>Documents</h3>' +
        '<span class="pill ' + (d.complete ? 'pill-delivered' : 'pill-at_pickup') + '">' +
          d.filed + ' of ' + d.total + ' filed</span>' +
      '</div>' +
      (d.complete
        ? '<p class="muted" style="margin:0 0 16px">Everything this lane needs is on file.</p>'
        : '<p class="muted" style="margin:0 0 16px">Next due: <b>' + esc(d.next_due.name) +
          '</b> &mdash; ' + esc(d.next_due.owner_label) + ', ' +
          esc(d.next_due.stage_label.toLowerCase()) + '.</p>') +
      '<div id="doc-err"></div>' + groups +
    '</div>';
  }

  // The drop sequence. One stop is a plain delivery; several is a run, and
  // each one is signed for on its own.
  function stopsPanel(o, role) {
    var stops = o.stops || [];
    if (stops.length < 2) return '';
    var canSign = role === 'ops' || (role === 'driver' && o.driver_id === state.user.id);
    var rows = stops.map(function (s) {
      var done = s.status === 'done';
      return '<li class="drop' + (done ? ' drop-done' : '') + '">' +
        '<i>' + s.seq + '</i>' +
        '<div>' +
          '<b>' + esc(s.node_name) + (s.tonnes ? ' &middot; ' + esc(s.tonnes) + ' t' : '') + '</b>' +
          '<span>' + esc(s.address) + '<br>' + esc(s.recipient_name) + ' &middot; ' + esc(s.recipient_phone) +
            (done && s.completed_at ? '<br>Signed ' + esc(M.when(s.completed_at)) : '') +
            (s.proof_note ? ' &middot; ' + esc(s.proof_note) : '') +
          '</span>' +
        '</div>' +
        (done || !canSign ? '' : '<button class="btn btn-ghost btn-sm" data-stop="' + s.seq + '">Sign off</button>') +
      '</li>';
    }).join('');
    var doneCount = stops.filter(function (s) { return s.status === 'done'; }).length;
    return '<div class="panel" style="margin-top:18px">' +
      '<div class="panel-head"><h3>Drops</h3>' +
        '<span class="pill pill-assigned">' + doneCount + ' of ' + stops.length + ' signed</span></div>' +
      '<div id="stop-err"></div><ul class="drop-list">' + rows + '</ul>' +
    '</div>';
  }

  // Weighbridge in, weighbridge out, and the gap between them. On grain and
  // concentrate that gap is the whole commercial argument.
  function weightPanel(o, role) {
    var w = o.weights || {};
    var weighed = ['maize', 'soya', 'wheat', 'sugar'].indexOf(o.commodity_key) >= 0 ||
                  o.sector === 'mining';
    if (!weighed) return '';
    var canWeigh = role === 'ops' || (role === 'driver' && o.driver_id === state.user.id) ||
                   (role === 'shipper' && o.shipper_id === state.user.id);
    var variance = '';
    if (w.variance_kg !== undefined && w.variance_kg !== null) {
      variance = '<div class="variance' + (w.within_tolerance ? '' : ' variance-out') + '">' +
        '<b>' + (w.variance_kg > 0 ? '+' : '') + esc(w.variance_kg.toLocaleString()) + ' kg</b>' +
        '<span>' + esc(w.variance_pct) + '% against a ' + esc(w.tolerance_pct) + '% tolerance &mdash; ' +
          (w.within_tolerance ? 'within contract.' : 'outside contract. Raise a claim before settlement.') +
        '</span></div>';
    }
    return '<div class="panel" style="margin-top:18px">' +
      '<h3>Weighbridge</h3>' +
      '<dl class="kv">' +
        '<dt>Loaded</dt><dd>' + (w.loaded_kg ? esc(w.loaded_kg.toLocaleString()) + ' kg' : '<span class="muted">Not yet weighed</span>') + '</dd>' +
        '<dt>Discharged</dt><dd>' + (w.discharged_kg ? esc(w.discharged_kg.toLocaleString()) + ' kg' : '<span class="muted">Not yet weighed</span>') + '</dd>' +
      '</dl>' + variance +
      (canWeigh
        ? '<div id="weigh-err"></div><div class="row2" style="margin-top:14px;align-items:end">' +
            '<label class="field" style="margin:0"><span>Loaded, kg</span>' +
              '<input class="input" type="number" id="w-loaded" inputmode="numeric" value="' + (w.loaded_kg || '') + '"></label>' +
            '<label class="field" style="margin:0"><span>Discharged, kg</span>' +
              '<input class="input" type="number" id="w-discharged" inputmode="numeric" value="' + (w.discharged_kg || '') + '"></label>' +
          '</div>' +
          '<button class="btn btn-ghost btn-block" style="margin-top:10px" id="weigh-save">Record weights</button>'
        : '') +
    '</div>';
  }

  // Where the truck is. A regional lane runs for days through places with no
  // telematics, so a ping is either a coordinate or a named point.
  function trackingPanel(o, role) {
    var t = o.tracking || {};
    var running = ['assigned', 'at_pickup', 'in_transit'].indexOf(o.status) >= 0;
    if (!t.route || !t.route.length) return '';
    var lastKey = t.last ? t.last.node_key : null;
    var reached = true;
    var marks = t.route.map(function (n) {
      var here = n.key === lastKey;
      var cls = here ? 'here' : (reached ? 'past' : '');
      if (here) reached = false;
      return '<li class="' + cls + '"><i></i><div><b>' + esc(n.name) + '</b>' +
        '<span>' + esc(n.country) + (n.kind === 'border' ? ' &middot; border post' : '') + '</span></div></li>';
    }).join('');

    var bar = '';
    if (t.progress_pct !== undefined && t.progress_pct !== null) {
      bar = '<div class="progress"><div style="width:' + Math.min(100, t.progress_pct) + '%"></div></div>' +
        '<p class="muted" style="margin:8px 0 18px">' +
          esc(Math.round(t.km_done || 0)) + ' km run, ' + esc(Math.round(t.km_left || 0)) + ' km left' +
          (t.eta_at ? ' &middot; due ' + esc(M.when(t.eta_at)) : '') + '</p>';
    }

    var canPing = role === 'ops' || (role === 'driver' && o.driver_id === state.user.id);
    var pinger = '';
    if (canPing && running) {
      pinger = '<div id="ping-err"></div><div class="row2" style="margin-top:14px;align-items:end">' +
        '<label class="field" style="margin:0"><span>Report position</span>' +
          '<select class="input" id="ping-node">' +
            t.route.map(function (n) {
              return '<option value="' + esc(n.key) + '"' + (n.key === lastKey ? ' selected' : '') + '>' + esc(n.name) + '</option>';
            }).join('') +
          '</select></label>' +
        '<button class="btn btn-ghost" id="ping-send">Send</button>' +
      '</div>' +
      '<button class="btn btn-ghost btn-block" style="margin-top:8px" id="ping-gps">Use my location</button>';
    }

    return '<div class="panel" style="margin-top:18px">' +
      '<div class="panel-head"><h3>Where it is</h3>' +
        (t.last ? '<span class="muted">' + esc(t.last.place) + ' &middot; ' + esc(M.ago(t.last.created_at)) + '</span>' : '') +
      '</div>' + bar +
      '<ul class="route-line">' + marks + '</ul>' + pinger +
    '</div>';
  }

  function borderStrip(o) {
    if (!o.crossings || !o.crossings.length) return '';
    return '<div class="border-strip"><span>Crossings</span>' +
      o.crossings.map(function (c) { return '<b>' + esc(c.post) + '</b>'; }).join('') +
      '</div>';
  }

  // Wires up every control the panels above put on the page.
  function bindLoadPanels(o) {
    M.els('[data-doc]').forEach(function (btn) {
      btn.addEventListener('click', function () {
        var reference = prompt('Reference or number for "' + btn.parentNode.querySelector('b').textContent + '"');
        if (reference === null) return;
        btn.disabled = true;
        api.fileDocument(o.ref, { doc_key: btn.dataset.doc, reference: reference }).then(route)
          .catch(function (err) {
            el('#doc-err').innerHTML = '<div class="notice notice-error">' + esc(err.message) + '</div>';
            btn.disabled = false;
          });
      });
    });

    M.els('[data-stop]').forEach(function (btn) {
      btn.addEventListener('click', function () {
        var note = prompt('Who signed for this drop, and any note?');
        if (note === null) return;
        btn.disabled = true;
        api.completeStop(o.ref, btn.dataset.stop, { proof_note: note }).then(route)
          .catch(function (err) {
            el('#stop-err').innerHTML = '<div class="notice notice-error">' + esc(err.message) + '</div>';
            btn.disabled = false;
          });
      });
    });

    var weighBtn = el('#weigh-save');
    if (weighBtn) {
      weighBtn.addEventListener('click', function () {
        weighBtn.disabled = true;
        api.weigh(o.ref, { loaded_kg: el('#w-loaded').value || null,
                           discharged_kg: el('#w-discharged').value || null }).then(route)
          .catch(function (err) {
            el('#weigh-err').innerHTML = '<div class="notice notice-error">' + esc(err.message) + '</div>';
            weighBtn.disabled = false;
          });
      });
    }

    var pingBtn = el('#ping-send');
    if (pingBtn) {
      pingBtn.addEventListener('click', function () {
        pingBtn.disabled = true;
        api.ping(o.ref, { node_key: el('#ping-node').value }).then(route)
          .catch(function (err) {
            el('#ping-err').innerHTML = '<div class="notice notice-error">' + esc(err.message) + '</div>';
            pingBtn.disabled = false;
          });
      });
    }

    var gpsBtn = el('#ping-gps');
    if (gpsBtn) {
      gpsBtn.addEventListener('click', function () {
        if (!navigator.geolocation) {
          el('#ping-err').innerHTML = '<div class="notice notice-error">This device cannot report a location.</div>';
          return;
        }
        gpsBtn.disabled = true;
        gpsBtn.textContent = 'Locating…';
        navigator.geolocation.getCurrentPosition(function (pos) {
          api.ping(o.ref, { lat: pos.coords.latitude, lng: pos.coords.longitude }).then(route)
            .catch(function (err) {
              el('#ping-err').innerHTML = '<div class="notice notice-error">' + esc(err.message) + '</div>';
              gpsBtn.disabled = false;
              gpsBtn.textContent = 'Use my location';
            });
        }, function () {
          el('#ping-err').innerHTML = '<div class="notice notice-error">Could not read this device\'s location.</div>';
          gpsBtn.disabled = false;
          gpsBtn.textContent = 'Use my location';
        });
      });
    }
  }

  function viewOrder(ref) {
    api.order(ref).then(function (o) {
      var role = state.user.role;
      var actions = '';

      if (role === 'driver' && o.driver_id === state.user.id && NEXT_ACTION[o.status]) {
        var a = NEXT_ACTION[o.status];
        actions = '<button class="btn btn-primary btn-block" data-next="' + esc(a.status) + '">' + esc(a.label) + '</button>';
        if (a.status === 'delivered') {
          actions = '<label class="field"><span>Proof of delivery — weighbridge ticket or signature</span>' +
                    '<input class="input" id="proof" placeholder="Ticket 44821, signed by…"></label>' + actions;
        }
      }
      if (role === 'ops' && NEXT_ACTION[o.status]) {
        actions += '<button class="btn btn-ghost btn-block" style="margin-top:8px" data-next="' + esc(NEXT_ACTION[o.status].status) + '">' +
                   'Force: ' + esc(NEXT_ACTION[o.status].label) + '</button>';
      }
      if (['placed', 'assigned', 'at_pickup'].indexOf(o.status) >= 0 &&
          (role === 'ops' || (role === 'shipper' && o.shipper_id === state.user.id))) {
        actions += '<button class="btn btn-ghost btn-block" style="margin-top:8px;color:var(--stop)" data-next="cancelled">Cancel this load</button>';
      }

      var timeline = (o.timeline || []).slice().reverse().map(function (e) {
        return '<li><b>' + esc(e.label) + '</b><span>' + esc(M.when(e.created_at)) +
               (e.note ? ' &middot; ' + esc(e.note) : '') + '</span></li>';
      }).join('');

      shell(
        pageHead(o.ref, o.commodity_name + ' · ' + o.tonnes + ' t · ' + o.from_name + ' → ' + o.to_name,
          '<a class="btn btn-ghost btn-sm" href="/track?ref=' + esc(o.ref) + '" target="_blank" rel="noopener">Public tracking link</a>') +
        '<div class="detail">' +
          '<div>' +
            '<div class="panel">' +
              '<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:18px">' +
                '<h3 style="margin:0">Load details</h3>' + statusPill(o) +
              '</div>' +
              '<div class="job-route" style="margin-bottom:20px">' +
                '<div class="leg"><i></i><div><b>' + esc(o.from_name) + '</b><span>' + esc(o.pickup_address) + '</span></div></div>' +
                '<div class="leg to"><i></i><div><b>' + esc(o.to_name) + '</b><span>' + esc(o.dropoff_address) + '</span></div></div>' +
              '</div>' +
              '<dl class="kv">' +
                '<dt>Commodity</dt><dd>' + esc(o.commodity_name) + '</dd>' +
                '<dt>Tonnage</dt><dd>' + esc(o.tonnes) + ' t' + (o.billed_tonnes > o.tonnes ? ' <span class="muted">(' + esc(o.billed_tonnes) + ' t billed minimum)</span>' : '') + '</dd>' +
                '<dt>Equipment</dt><dd>' + esc(o.equipment_name) + ' &middot; ' + esc(o.service_name) + '</dd>' +
                '<dt>Description</dt><dd>' + esc(o.goods) + '</dd>' +
                '<dt>Transit</dt><dd>' + esc(o.distance_km) + ' km &middot; ~' + esc(M.duration(o.eta_minutes)) +
                  (o.corridor ? '<span class="sub">' + esc(o.corridor) + '</span>' : '') + '</dd>' +
                '<dt>Site contact</dt><dd>' + esc(o.recipient_name) + ' &middot; ' + esc(o.recipient_phone) + '</dd>' +
                '<dt>Carrier</dt><dd>' + (o.driver ? esc(o.driver.name) + ' &middot; ' + esc(o.driver.phone) : '<span class="muted">Not yet assigned</span>') + '</dd>' +
                '<dt>Settlement</dt><dd>' + esc(o.payment_label) + ' &middot; ' + esc(o.payment_status) + '</dd>' +
                (role === 'driver' ? '<dt>Your payout</dt><dd>' + esc(o.payout) + '</dd>'
                                   : '<dt>Total</dt><dd>' + esc(o.total) + '</dd>') +
                (o.cover ? '<dt>Cargo cover</dt><dd>' + esc(o.cover.declared_value) + ' declared &middot; premium ' + esc(o.cover.premium) + ' <span class="muted">(' + esc(o.cover.rate_pct) + '%)</span></dd>' : '') +
                (o.settlement ? '<dt>Settled</dt><dd>' + esc(o.settlement.net) + (o.settlement.fuel_deduction_ngwee ? ' <span class="muted">after ' + esc(o.settlement.fuel_deduction) + ' fuel</span>' : '') + '</dd>' : '') +
                (o.proof_note ? '<dt>Proof</dt><dd>' + esc(o.proof_note) + '</dd>' : '') +
              '</dl>' +
              borderStrip(o) +
              (actions ? '<div id="err" style="margin-top:20px"></div>' + actions : '') +
            '</div>' +
            stopsPanel(o, role) +
            documentPanel(o, role) +
            weightPanel(o, role) +
            fuelPanel(o, role) +
          '</div>' +
          '<div class="detail-side">' +
            trackingPanel(o, role) +
            rateConfirmationPanel(o, role) +
            '<div class="panel"><h3>Timeline</h3><ul class="timeline">' + timeline + '</ul></div>' +
          '</div>' +
        '</div>'
      );

      bindLoadPanels(o);

      var drawBtn = el('#fuel-draw');
      if (drawBtn) {
        drawBtn.addEventListener('click', function () {
          drawBtn.disabled = true;
          drawBtn.textContent = 'Drawing…';
          api.fuelDraw(o.ref, { litres: el('#fuel-litres').value }).then(function () {
            route();
          }).catch(function (err) {
            el('#fuel-err').innerHTML = '<div class="notice notice-error">' + esc(err.message) + '</div>';
            drawBtn.disabled = false;
            drawBtn.textContent = 'Draw diesel';
          });
        });
      }

      M.els('[data-next]').forEach(function (btn) {
        btn.addEventListener('click', function () {
          var target = btn.dataset.next;
          if (target === 'cancelled' && !confirm('Cancel load ' + o.ref + '? This cannot be undone.')) return;
          btn.disabled = true;
          var proof = el('#proof');
          api.setStatus(o.ref, { status: target, proof_note: proof ? proof.value : null }).then(function () {
            route();
          }).catch(function (err) {
            el('#err').innerHTML = '<div class="notice notice-error">' + esc(err.message) + '</div>';
            btn.disabled = false;
          });
        });
      });
    }).catch(fail);
  }

  /* ====================================================================== */
  /* PLANT HIRE                                                             */
  /* ====================================================================== */

  var HIRE_COL = {
    ref:     { label: 'Reference', cell: function (h) { return '<b class="mono">' + esc(h.ref) + '</b><span class="sub">' + esc(M.ago(h.created_at)) + '</span>'; } },
    machine: { label: 'Machine', cell: function (h) { return esc(h.plant_name) + '<span class="sub">' + (h.with_operator ? 'With operator' : 'Dry hire') + (h.with_fuel ? ' · fuelled' : '') + '</span>'; } },
    site:    { label: 'Site', cell: function (h) { return esc(h.site_name) + '<span class="sub">' + esc(h.site_address) + '</span>'; } },
    period:  { label: 'Period', cell: function (h) { return h.days + (h.days === 1 ? ' day' : ' days') + '<span class="sub">' + esc(h.tier) + ' rate</span>'; } },
    status:  { label: 'Status', cell: function (h) { return '<span class="pill pill-' + esc(h.status) + '">' + esc(h.status_label) + '</span>'; } },
    total:   { label: 'Total', num: true, cell: function (h) { return esc(h.total) + '<span class="sub">' + esc(h.payment_label) + '</span>'; } }
  };

  function hireTable(hires) {
    if (!hires.length) return empty('No hires yet', 'Rent a machine and it will show up here.');
    var cols = [HIRE_COL.ref, HIRE_COL.machine, HIRE_COL.site, HIRE_COL.period, HIRE_COL.status, HIRE_COL.total];
    return '<div class="table-wrap"><table><thead><tr>' +
      cols.map(function (c) { return '<th' + (c.num ? ' class="num"' : '') + '>' + esc(c.label) + '</th>'; }).join('') +
      '</tr></thead><tbody>' + hires.map(function (h) {
        return '<tr data-hire="' + esc(h.ref) + '">' + cols.map(function (c) {
          return '<td' + (c.num ? ' class="num"' : '') + '>' + c.cell(h) + '</td>';
        }).join('') + '</tr>';
      }).join('') + '</tbody></table></div>';
  }

  function viewHires() {
    api.hires().then(function (res) {
      var live = res.hires.filter(function (h) {
        return ['requested', 'confirmed', 'on_site', 'off_hire'].indexOf(h.status) >= 0;
      });
      shell(
        pageHead('Plant hire', live.length + ' active, ' + res.hires.length + ' all time',
          '<a class="btn btn-primary" href="#/hire">Rent a machine</a>') +
        hireTable(res.hires)
      );
    }).catch(fail);
  }

  function viewHireBook() {
    var params = new URLSearchParams(location.hash.split('?')[1] || '');
    var cfg = state.config;

    var byCategory = {};
    cfg.plant.forEach(function (m) { (byCategory[m.category] = byCategory[m.category] || []).push(m); });
    var catName = function (key) {
      var c = cfg.plant_categories.filter(function (x) { return x.key === key; })[0];
      return c ? c.name : key;
    };
    var plantOptions = Object.keys(byCategory).map(function (cat) {
      return '<optgroup label="' + esc(catName(cat)) + '">' +
        byCategory[cat].map(function (m) {
          return '<option value="' + esc(m.key) + '">' + esc(m.name) + '</option>';
        }).join('') + '</optgroup>';
    }).join('');

    shell(
      pageHead('Rent a machine', 'Day, week or month — we quote whichever works out cheaper.') +
      '<div class="book">' +
        '<form class="panel" id="f">' +
          '<fieldset><legend>The machine</legend>' +
            '<label class="field"><span>What do you need?</span><select class="input" name="plant">' + plantOptions + '</select></label>' +
            '<p class="muted" id="blurb" style="font-size:.88rem;margin:-8px 0 18px"></p>' +
            '<div class="row2">' +
              '<label class="field"><span>How many days?</span><input class="input" name="days" type="number" min="1" max="365" value="14" inputmode="numeric" required></label>' +
              '<label class="field"><span>Site</span><select class="input" name="site">' + M.zoneOptions(cfg.zones, cfg.countries) + '</select></label>' +
            '</div>' +
            '<label class="check"><input type="checkbox" name="with_operator" checked>' +
              '<span><b>With an operator</b><span>Our crew runs the machine on your site.</span></span></label>' +
            '<label class="check"><input type="checkbox" name="with_fuel">' +
              '<span><b>Fuel included</b><span>Diesel billed at cost, nine hours a day.</span></span></label>' +
            '<label class="check"><input type="checkbox" name="with_waiver" checked>' +
              '<span><b>Damage waiver</b><span>Caps your liability for damage on site.</span></span></label>' +
          '</fieldset>' +

          '<fieldset><legend>Where it goes</legend>' +
            '<label class="field"><span>Site address</span><input class="input" name="site_address" required placeholder="Kalumbila Mine, west pit"></label>' +
            '<div class="row2">' +
              '<label class="field"><span>Site contact</span><input class="input" name="site_contact" required></label>' +
              '<label class="field"><span>Contact phone</span><input class="input" name="site_phone" required placeholder="+2609…"></label>' +
            '</div>' +
            '<label class="field"><span>What is it for?</span><input class="input" name="purpose" required placeholder="Bench stripping, west pit extension"></label>' +
          '</fieldset>' +

          '<fieldset><legend>Settlement</legend>' +
            '<label class="field"><span>How is this hire paid?</span><select class="input" name="payment_method">' +
              M.options(cfg.payment_methods, 'key', 'name') + '</select></label>' +
          '</fieldset>' +

          '<div id="err"></div>' +
          '<button class="btn btn-primary btn-block" type="submit">Book this machine</button>' +
        '</form>' +

        '<div class="panel book-summary">' +
          '<h3>Rate</h3>' +
          '<div id="quote"><p class="muted">Pick a machine to see the rate.</p></div>' +
        '</div>' +
      '</div>'
    );

    var f = el('#f');
    if (params.get('plant')) f.plant.value = params.get('plant');
    if (params.get('site')) f.site.value = params.get('site');
    if (params.get('days')) f.days.value = params.get('days');
    if (params.get('operator') === '0') f.with_operator.checked = false;
    if (params.get('fuel') === '1') f.with_fuel.checked = true;

    function syncBlurb() {
      var m = cfg.plant.filter(function (x) { return x.key === f.plant.value; })[0];
      el('#blurb').textContent = m ? m.blurb : '';
      // Unmanned units have no crew to bill for.
      var crewed = m && m.operator_day_ngwee > 0;
      f.with_operator.disabled = !crewed;
      if (!crewed) f.with_operator.checked = false;
    }

    function refreshQuote() {
      api.hireQuote({
        plant: f.plant.value, site: f.site.value, days: Number(f.days.value) || 1,
        with_operator: f.with_operator.checked, with_fuel: f.with_fuel.checked,
        with_waiver: f.with_waiver.checked
      }).then(function (q) {
        var lines = q.lines.filter(function (l) { return l.ngwee !== 0; }).map(function (l) {
          return '<div><span>' + esc(l.label) + '</span><span>' + esc(l.amount) + '</span></div>';
        }).join('');
        el('#quote').innerHTML =
          '<div class="summary-total"><span>' + esc(q.plant_name) + '</span><b>' + esc(q.total) + '</b></div>' +
          '<div class="quote-meta muted" style="font-size:.85rem;display:flex;flex-wrap:wrap;gap:4px 14px">' +
            '<span>' + q.days + (q.days === 1 ? ' day' : ' days') + '</span>' +
            '<span>' + esc(q.tier) + ' rate</span>' +
            '<span>' + esc(q.effective_day) + '/day</span>' +
            '<span>float from ' + esc(q.depot_name) + '</span>' +
          '</div>' +
          '<div class="summary-lines">' + lines +
            '<div class="total"><span>VAT 16%</span><span>' + esc(q.vat) + '</span></div></div>';
      }).catch(function (err) {
        el('#quote').innerHTML = '<div class="notice notice-error">' + esc(err.message) + '</div>';
      });
    }

    var soon = M.debounce(refreshQuote, 240);
    f.plant.addEventListener('change', function () { syncBlurb(); refreshQuote(); });
    [f.site, f.with_operator, f.with_fuel, f.with_waiver].forEach(function (n) {
      n.addEventListener('change', refreshQuote);
    });
    f.days.addEventListener('input', soon);
    syncBlurb();
    refreshQuote();

    f.addEventListener('submit', function (e) {
      e.preventDefault();
      var btn = f.querySelector('button[type=submit]');
      btn.disabled = true;
      btn.textContent = 'Booking…';
      el('#err').innerHTML = '';
      api.createHire({
        plant: f.plant.value, site: f.site.value, days: Number(f.days.value) || 1,
        with_operator: f.with_operator.checked, with_fuel: f.with_fuel.checked,
        with_waiver: f.with_waiver.checked,
        site_address: f.site_address.value, site_contact: f.site_contact.value,
        site_phone: f.site_phone.value, purpose: f.purpose.value,
        payment_method: f.payment_method.value
      }).then(function (h) {
        location.hash = '#/hires/' + h.ref;
      }).catch(function (err) {
        el('#err').innerHTML = '<div class="notice notice-error">' + esc(err.message) + '</div>';
        btn.disabled = false;
        btn.textContent = 'Book this machine';
      });
    });
  }

  var HIRE_NEXT = {
    requested: { status: 'confirmed', label: 'Confirm this hire' },
    confirmed: { status: 'on_site',   label: 'Machine delivered to site' },
    on_site:   { status: 'off_hire',  label: 'End the hire' },
    off_hire:  { status: 'returned',  label: 'Back at depot — close it' }
  };

  function viewHire(ref) {
    api.hire(ref).then(function (h) {
      var role = state.user.role;
      var actions = '';
      var next = HIRE_NEXT[h.status];

      // Control drives the hire; the customer can only end or cancel it.
      if (role === 'ops' && next) {
        actions = '<button class="btn btn-primary btn-block" data-hire-next="' + esc(next.status) + '">' + esc(next.label) + '</button>';
        if (next.status === 'returned') {
          actions = '<label class="field"><span>Return condition — meter hours, damage</span>' +
                    '<input class="input" id="meter" placeholder="1,284 h, no damage"></label>' + actions;
        }
      }
      if (role === 'shipper' && h.status === 'on_site') {
        actions = '<button class="btn btn-primary btn-block" data-hire-next="off_hire">I am finished — collect it</button>';
      }
      if (['requested', 'confirmed'].indexOf(h.status) >= 0 &&
          (role === 'ops' || h.hirer_id === state.user.id)) {
        actions += '<button class="btn btn-ghost btn-block" style="margin-top:10px;color:var(--stop);border-color:var(--stop)" data-hire-next="cancelled">Cancel this hire</button>';
      }

      var timeline = (h.timeline || []).slice().reverse().map(function (e) {
        return '<li><b>' + esc(e.label) + '</b><span>' + esc(M.when(e.created_at)) +
               (e.note ? ' &middot; ' + esc(e.note) : '') + '</span></li>';
      }).join('');

      shell(
        pageHead(h.ref, h.plant_name + ' · ' + h.days + (h.days === 1 ? ' day' : ' days') + ' · ' + h.site_name) +
        '<div class="detail">' +
          '<div class="panel">' +
            '<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:18px">' +
              '<h3 style="margin:0">Hire details</h3>' +
              '<span class="pill pill-' + esc(h.status) + '">' + esc(h.status_label) + '</span>' +
            '</div>' +
            '<dl class="kv">' +
              '<dt>Machine</dt><dd>' + esc(h.plant_name) + '</dd>' +
              '<dt>Period</dt><dd>' + h.days + (h.days === 1 ? ' day' : ' days') + ' &middot; ' + esc(h.tier) + ' rate</dd>' +
              '<dt>Site</dt><dd>' + esc(h.site_name) + '<br><span class="muted">' + esc(h.site_address) + '</span></dd>' +
              '<dt>Purpose</dt><dd>' + esc(h.purpose) + '</dd>' +
              '<dt>Float from</dt><dd>' + esc(h.depot_name) + ' &middot; ' + esc(h.float_km) + ' km each way</dd>' +
              '<dt>Crew</dt><dd>' + (h.with_operator ? 'Musanga operator' : 'Dry hire, your operator') + '</dd>' +
              '<dt>Fuel</dt><dd>' + (h.with_fuel ? 'Included, billed at cost' : 'Your account') + '</dd>' +
              '<dt>Waiver</dt><dd>' + (h.with_waiver ? 'Damage waiver taken' : 'No waiver') + '</dd>' +
              '<dt>Site contact</dt><dd>' + esc(h.site_contact) + ' &middot; ' + esc(h.site_phone) + '</dd>' +
              '<dt>Settlement</dt><dd>' + esc(h.payment_label) + ' &middot; ' + esc(h.payment_status) + '</dd>' +
              '<dt>Total</dt><dd>' + esc(h.total) + '</dd>' +
              (h.meter_note ? '<dt>Returned</dt><dd>' + esc(h.meter_note) + '</dd>' : '') +
            '</dl>' +
            (actions ? '<div id="err" style="margin-top:22px"></div>' + actions : '') +
          '</div>' +
          '<div class="panel"><h3>Timeline</h3><ul class="timeline">' + timeline + '</ul></div>' +
        '</div>'
      );

      M.els('[data-hire-next]').forEach(function (btn) {
        btn.addEventListener('click', function () {
          var target = btn.dataset.hireNext;
          if (target === 'cancelled' && !confirm('Cancel hire ' + h.ref + '? This cannot be undone.')) return;
          btn.disabled = true;
          var meter = el('#meter');
          api.setHireStatus(h.ref, { status: target, meter_note: meter ? meter.value : null })
            .then(route)
            .catch(function (err) {
              el('#err').innerHTML = '<div class="notice notice-error">' + esc(err.message) + '</div>';
              btn.disabled = false;
            });
        });
      });
    }).catch(fail);
  }

  /* ====================================================================== */
  /* ROUTER                                                                 */
  /* ====================================================================== */

  function fail(err) {
    if (err.status === 401) {
      api.setToken(null);
      state.user = null;
      location.hash = '#/login';
      return route();
    }
    var gated = err.status === 403 && /verif/i.test(err.message);
    root.innerHTML = '<div class="auth-wrap"><div class="auth-card">' +
      '<div class="notice notice-error">' + esc(err.message) + '</div>' +
      (gated ? '<a class="btn btn-primary btn-block" href="#/verify">Open verification</a>' : '') +
      '<a class="btn btn-ghost btn-block" href="#/">Back</a></div></div>';
  }

  /* ====================================================================== */
  /* CONTRACTS                                                              */
  /* ====================================================================== */

  // Committed tonnage at an agreed rate, drawn down load by load. Without
  // this, "contract rate" is just a discount nobody can reconcile.
  function viewContracts() {
    api.contracts().then(function (res) {
      var cards = res.contracts.map(function (c) {
        var pct = Math.min(100, c.used_pct);
        return '<div class="panel contract">' +
          '<div class="panel-head">' +
            '<h3>' + esc(c.name) + '</h3>' +
            '<span class="pill pill-' + esc(c.status === 'active' ? 'in_transit' : 'delivered') + '">' + esc(c.status) + '</span>' +
          '</div>' +
          '<p class="muted" style="margin:0 0 14px">' + esc(c.from_name) + ' &rarr; ' + esc(c.to_name) +
            ' &middot; ' + esc(c.commodity_name) + ' &middot; ' + esc(c.equipment_name) + '</p>' +
          '<div class="progress"><div style="width:' + pct + '%"></div></div>' +
          '<p class="muted" style="margin:8px 0 16px">' +
            esc(c.tonnes_called_off) + ' t called off of ' + esc(c.tonnes_committed) + ' t &middot; ' +
            '<b>' + esc(c.tonnes_remaining) + ' t left</b> &middot; ' + c.loads + ' loads</p>' +
          '<dl class="kv">' +
            '<dt>Rate</dt><dd>' + esc(c.rate) + ' per tonne</dd>' +
            '<dt>Contract value</dt><dd>' + esc(c.value) + '</dd>' +
            '<dt>Weight tolerance</dt><dd>' + esc(c.tolerance_pct) + '%</dd>' +
            '<dt>Period</dt><dd>' + esc(M.when(c.starts_on)) + ' &ndash; ' + esc(M.when(c.ends_on)) + '</dd>' +
            '<dt>Reference</dt><dd class="mono">' + esc(c.ref) + '</dd>' +
          '</dl>' +
          '<a class="btn btn-ghost btn-block" style="margin-top:14px" href="#/book?contract=' + esc(c.ref) + '">Call off a load</a>' +
        '</div>';
      }).join('');

      shell(
        pageHead('Contracts', res.contracts.length + ' on the book') +
        (res.contracts.length
          ? '<div class="grid-cards">' + cards + '</div>'
          : empty('No contracts yet', 'Committed tonnage at an agreed rate, drawn down load by load.')) +
        '<div class="panel" style="margin-top:22px">' +
          '<h3>Open a contract</h3>' +
          '<p class="muted">The rate is our own rate for the lane at contract terms, so what you are quoted is what you are billed.</p>' +
          '<div id="ctr-err"></div>' +
          '<label class="field"><span>What is it for?</span>' +
            '<input class="input" id="ctr-name" placeholder="Fertiliser distribution, 2026 season"></label>' +
          '<div class="row2">' +
            '<label class="field"><span>Commodity</span><select class="input" id="ctr-commodity">' +
              M.options(state.config.commodities, 'key', 'name') + '</select></label>' +
            '<label class="field"><span>Equipment</span><select class="input" id="ctr-equipment">' +
              M.options(state.config.equipment, 'key', 'name') + '</select></label>' +
          '</div>' +
          '<div class="row2">' +
            '<label class="field"><span>From</span><select class="input" id="ctr-from">' +
              M.zoneOptions(state.config.zones, state.config.countries) + '</select></label>' +
            '<label class="field"><span>To</span><select class="input" id="ctr-to">' +
              M.zoneOptions(state.config.zones, state.config.countries) + '</select></label>' +
          '</div>' +
          '<label class="field"><span>Committed tonnage over the period</span>' +
            '<input class="input" id="ctr-tonnes" type="number" min="1" step="100" value="5000" inputmode="numeric"></label>' +
          '<button class="btn btn-primary btn-block" id="ctr-save">Open the contract</button>' +
        '</div>'
      );

      var save = el('#ctr-save');
      save.addEventListener('click', function () {
        save.disabled = true;
        api.createContract({
          name: el('#ctr-name').value,
          commodity: el('#ctr-commodity').value,
          equipment: el('#ctr-equipment').value,
          from_zone: el('#ctr-from').value,
          to_zone: el('#ctr-to').value,
          tonnes_committed: el('#ctr-tonnes').value
        }).then(route).catch(function (err) {
          el('#ctr-err').innerHTML = '<div class="notice notice-error">' + esc(err.message) + '</div>';
          save.disabled = false;
        });
      });
    }).catch(fail);
  }

  /* ====================================================================== */
  /* VERIFICATION (KYC)                                                     */
  /* ====================================================================== */

  function refreshMe() {
    return api.me().then(function (res) {
      state.user = res.user;
      state.vehicle = res.vehicle || null;
      state.kyc = res.kyc || null;
      state.carrierMaster = res.carrier_master || null;
    }).catch(function () {});
  }

  var KYC_PILL = { unverified: 'placed', in_review: 'at_pickup', verified: 'delivered', rejected: 'cancelled' };

  function kycPill(status, label) {
    return '<span class="pill pill-' + esc(KYC_PILL[status] || 'placed') + '">' + esc(label || status) + '</span>';
  }

  // Reads a chosen file as a data URL, so the document can be posted as JSON
  // alongside its reference. 4 MB ceiling, matched to the API.
  function readFile(input) {
    return new Promise(function (resolve, reject) {
      var file = input.files && input.files[0];
      if (!file) return resolve(null);
      if (file.size > 4 * 1024 * 1024) return reject(new Error('That file is larger than 4 MB'));
      var reader = new FileReader();
      reader.onload = function () { resolve({ file: reader.result, filename: file.name }); };
      reader.onerror = function () { reject(new Error('Could not read that file')); };
      reader.readAsDataURL(file);
    });
  }

  function kycProgress(k) {
    var pct = k.documents_required ? Math.round(100 * k.documents_filed / k.documents_required) : 0;
    return '<div class="kyc-progress"><div class="kyc-progress-bar"><i style="width:' + pct + '%"></i></div>' +
           '<span>' + k.documents_filed + ' of ' + k.documents_required + ' required documents on file</span></div>';
  }

  function businessPanel(k) {
    var cfg = state.config.kyc;
    var p = k.profile || {};
    var fields = k.profile_fields;
    var labels = cfg.field_labels;

    function field(name, extra) {
      if (fields.indexOf(name) < 0 && name !== 'trading_name' && name !== 'vat_number') return '';
      var value = p[name] == null ? '' : p[name];
      var optional = fields.indexOf(name) < 0;
      return '<label class="field"><span>' + esc(labels[name] || name) +
        (optional ? ' <span class="muted">(optional)</span>' : '') + '</span>' +
        (name === 'address'
          ? '<textarea class="input" name="' + name + '" rows="2">' + esc(value) + '</textarea>'
          : '<input class="input" name="' + name + '" value="' + esc(value) + '"' + (extra || '') + '>') +
        '</label>';
    }

    return '<section class="panel kyc-step" id="step-business">' +
      '<div class="panel-head"><h3>1. Your business</h3>' +
        '<span class="muted">' + esc(k.missing_fields.length ? k.missing_fields.length + ' still needed' : 'Complete') + '</span></div>' +
      '<div class="entity-picker">' + cfg.entities.map(function (e) {
        return '<button type="button" data-entity="' + esc(e.key) + '" aria-pressed="' +
          (e.key === k.entity_type) + '"><b>' + esc(e.name) + '</b>' +
          (e.note ? '<span>' + esc(e.note) + '</span>' : '') + '</button>';
      }).join('') + '</div>' +
      '<form id="business-form">' +
        field('legal_name') + field('trading_name') +
        '<div class="row2">' + field('reg_number') + field('tin') + '</div>' +
        '<div class="row2">' +
          '<label class="field"><span>Country of registration</span><select class="input" name="country">' +
            [['ZM', 'Zambia']].concat(state.config.countries.filter(function (c) { return c.key !== 'ZM'; })
              .map(function (c) { return [c.key, c.name]; }))
              .map(function (c) {
                return '<option value="' + esc(c[0]) + '"' + ((p.country || 'ZM') === c[0] ? ' selected' : '') + '>' + esc(c[1]) + '</option>';
              }).join('') + '</select></label>' +
          field('sector') +
        '</div>' +
        field('address') +
        '<label class="check"><input type="checkbox" name="vat_registered"' + (p.vat_registered ? ' checked' : '') + '>' +
          '<span>Registered for VAT</span></label>' +
        '<div id="vat-line" ' + (p.vat_registered ? '' : 'hidden') + '>' + field('vat_number') + '</div>' +
        (state.user.role === 'driver'
          ? '<label class="check"><input type="checkbox" name="cross_border"' + (p.cross_border ? ' checked' : '') + '>' +
            '<span>We run the export corridors (DRC, Zimbabwe, Tanzania)</span></label>' : '') +
        '<button class="btn btn-primary" type="submit">Save business details</button>' +
      '</form></section>';
  }

  function peoplePanel(k) {
    var rows = k.people.map(function (person) {
      return '<tr><td><b>' + esc(person.full_name) + '</b>' +
        '<span class="sub">' + esc(person.position) + (person.is_control ? ' · control person' : '') + '</span></td>' +
        '<td class="mono">' + esc(person.id_number) + '<span class="sub">' + esc(person.id_type.toUpperCase()) + '</span></td>' +
        '<td class="num">' + (person.ownership_pct ? esc(person.ownership_pct) + '%' : '—') + '</td>' +
        '<td class="num"><button class="btn btn-ghost btn-sm" data-drop-person="' + person.id + '">Remove</button></td></tr>';
    }).join('');

    return '<section class="panel kyc-step" id="step-people">' +
      '<div class="panel-head"><h3>2. The people behind it</h3>' +
        '<span class="muted">' + esc(k.people.length + (k.people.length === 1 ? ' person' : ' people') + ' named') + '</span></div>' +
      '<p class="muted" style="margin-bottom:16px">' + esc(k.people_rule.note) + '</p>' +
      (k.people.length
        ? '<div class="table-wrap"><table><thead><tr><th>Name</th><th>Identity</th>' +
          '<th class="num">Owns</th><th></th></tr></thead><tbody>' + rows + '</tbody></table></div>'
        : '') +
      '<form id="person-form" class="kyc-add">' +
        '<div class="row2">' +
          '<label class="field"><span>Full name, as on the ID</span><input class="input" name="full_name" required></label>' +
          '<label class="field"><span>Position</span><input class="input" name="position" value="Director"></label>' +
        '</div>' +
        '<div class="row2">' +
          '<label class="field"><span>Identity document</span><select class="input" name="id_type">' +
            '<option value="nrc">NRC</option><option value="passport">Passport</option>' +
            '<option value="drivers_licence">Driving licence</option></select></label>' +
          '<label class="field"><span>Number</span><input class="input" name="id_number" required placeholder="123456/78/9"></label>' +
        '</div>' +
        (k.people_rule.ownership
          ? '<div class="row2">' +
              '<label class="field"><span>Ownership %</span><input class="input" name="ownership_pct" type="number" min="0" max="100" step="1" value="0"></label>' +
              '<label class="check" style="align-self:center"><input type="checkbox" name="is_control">' +
                '<span>This is the control person</span></label>' +
            '</div>' : '') +
        '<button class="btn btn-ghost" type="submit">Add person</button>' +
      '</form></section>';
  }

  function documentRow(item) {
    var doc = item.document;
    var state_ = doc ? doc.status : 'outstanding';
    var pill = { filed: 'at_pickup', accepted: 'delivered', rejected: 'cancelled', outstanding: 'placed' }[state_];
    return '<div class="doc-row' + (doc ? ' is-filed' : '') + '" data-doc="' + esc(item.key) + '">' +
      '<div class="doc-name"><b>' + esc(item.name) + '</b>' +
        (item.mandatory ? '' : '<span class="tag">Optional</span>') +
        (item.note ? '<span class="sub">' + esc(item.note) + '</span>' : '') +
        (doc && doc.note ? '<span class="sub warn">' + esc(doc.note) + '</span>' : '') +
      '</div>' +
      '<div class="doc-state"><span class="pill pill-' + pill + '">' +
        esc({ filed: 'Filed', accepted: 'Accepted', rejected: 'Rejected', outstanding: 'Outstanding' }[state_]) + '</span>' +
        (doc ? '<span class="sub">' + esc(doc.filename || doc.reference || '') + '</span>' : '') +
      '</div>' +
      '<div class="doc-actions">' +
        (doc && doc.has_file ? '<button class="btn btn-ghost btn-sm" data-view="' + doc.id + '">View</button>' : '') +
        (doc ? '<button class="btn btn-ghost btn-sm" data-drop-doc="' + doc.id + '">Remove</button>' : '') +
        '<button class="btn btn-sm ' + (doc ? 'btn-ghost' : 'btn-primary') + '" data-file="' + esc(item.key) + '">' +
          (doc ? 'Replace' : 'Upload') + '</button>' +
      '</div>' +
      '<form class="doc-form" hidden>' +
        '<label class="field"><span>File <span class="muted">(PDF or photo, up to 4 MB)</span></span>' +
          '<input class="input" type="file" name="file" accept="application/pdf,image/*"></label>' +
        '<div class="row2">' +
          '<label class="field"><span>Reference number <span class="muted">(optional)</span></span>' +
            '<input class="input" name="reference" value="' + esc((doc || {}).reference || '') + '"></label>' +
          (item.expires
            ? '<label class="field"><span>Expires on</span><input class="input" type="date" name="expires_on" value="' +
              esc((doc || {}).expires_on || '') + '"></label>' : '<span></span>') +
        '</div>' +
        '<button class="btn btn-primary btn-sm" type="submit">File document</button>' +
      '</form></div>';
  }

  function documentsPanel(k) {
    var groups = {};
    k.checklist.forEach(function (item) { (groups[item.group] = groups[item.group] || []).push(item); });
    var body = state.config.kyc.groups.filter(function (g) { return groups[g.key]; }).map(function (g) {
      return '<h4 class="doc-group">' + esc(g.name) + '</h4>' +
             groups[g.key].map(documentRow).join('');
    }).join('');

    return '<section class="panel kyc-step" id="step-documents">' +
      '<div class="panel-head"><h3>3. Documents</h3>' +
        '<span class="muted">' + k.documents_filed + ' of ' + k.documents_required + ' filed</span></div>' +
      body + '</section>';
  }

  function submitPanel(k) {
    if (k.status === 'in_review') {
      return '<section class="panel kyc-step"><h3>4. In review</h3>' +
        '<div class="notice notice-ok">Submitted ' + esc(M.ago(k.submitted_at)) +
        '. Our compliance team reviews files in the order they arrive; you will be able to book as soon as it clears.</div></section>';
    }
    if (k.status === 'verified') {
      return '<section class="panel kyc-step"><h3>Verified</h3>' +
        '<div class="notice notice-ok">This account is verified. Loads, plant hire, fuel and invoice terms are all open.</div></section>';
    }
    return '<section class="panel kyc-step" id="step-submit">' +
      '<h3>4. Submit for verification</h3>' +
      (k.blockers.length
        ? '<p class="muted">Still outstanding:</p><ul class="blockers">' +
          k.blockers.map(function (b) { return '<li>' + esc(b) + '</li>'; }).join('') + '</ul>'
        : '<p class="muted">Everything is on file. Most submissions are cleared within one working day.</p>') +
      '<div id="submit-err"></div>' +
      '<button class="btn btn-primary btn-block" id="kyc-submit"' + (k.can_submit ? '' : ' disabled') + '>' +
        'Submit for verification</button></section>';
  }

  function viewVerify() {
    api.kyc().then(function (k) {
      state.kyc = k;
      var locked = k.status === 'in_review' || k.status === 'verified';

      shell(
        pageHead('Verification', 'Everything a bank, an insurer or a regulator would ask of you — filed once, here.',
          kycPill(k.status, k.status_label)) +
        (k.status === 'rejected' && k.note
          ? '<div class="notice notice-error"><b>Sent back by compliance:</b> ' + esc(k.note) + '</div>' : '') +
        kycProgress(k) +
        '<div class="kyc-grid">' +
          '<div>' + businessPanel(k) + peoplePanel(k) + documentsPanel(k) + '</div>' +
          '<aside>' + submitPanel(k) +
            '<section class="panel"><h3>What opens up</h3><ul class="gate-list">' +
              Object.keys(k.gates).map(function (key) {
                return '<li>' + (state.user.can[key] ? '<i class="on">✓</i>' : '<i>•</i>') +
                       esc(k.gates[key].replace(/^Verify your (business|operation) before /, '')
                                       .replace(/^Invoice terms open once your business is verified$/, 'Invoice terms')) + '</li>';
              }).join('') + '</ul></section>' +
            (k.events.length
              ? '<section class="panel"><h3>History</h3><ol class="timeline">' + k.events.map(function (e) {
                  return '<li><b>' + esc(kycStatusLabel(e.status)) + '</b><span>' + esc(e.note || '') + '</span>' +
                         '<span class="sub">' + esc(M.when(e.created_at)) + (e.actor ? ' · ' + esc(e.actor) : '') + '</span></li>';
                }).join('') + '</ol></section>' : '') +
          '</aside>' +
        '</div>'
      );

      if (locked) {
        M.els('#step-business input, #step-business select, #step-business textarea, #step-business button, ' +
              '#step-people input, #step-people select, #step-people button, .doc-row button, .doc-row input')
          .forEach(function (node) { node.disabled = true; });
      }
      bindVerify(k);
    }).catch(fail);
  }

  function kycStatusLabel(status) {
    return { unverified: 'Account opened', in_review: 'Submitted', verified: 'Verified',
             rejected: 'Sent back' }[status] || status;
  }

  function saved(k) {
    state.kyc = k;
    return refreshMe().then(function () { viewVerify(); });
  }

  function bindVerify(k) {
    var picker = el('.entity-picker');
    if (picker) picker.addEventListener('click', function (e) {
      var btn = e.target.closest('[data-entity]');
      if (!btn) return;
      api.kycProfile({ entity_type: btn.dataset.entity }).then(saved).catch(fail);
    });

    var business = el('#business-form');
    if (business) {
      var vat = business.vat_registered;
      if (vat) vat.addEventListener('change', function () { el('#vat-line').hidden = !vat.checked; });
      business.addEventListener('submit', function (e) {
        e.preventDefault();
        var payload = {};
        ['legal_name', 'trading_name', 'reg_number', 'tin', 'vat_number', 'country', 'address', 'sector']
          .forEach(function (name) { if (business[name]) payload[name] = business[name].value.trim(); });
        payload.vat_registered = !!(business.vat_registered && business.vat_registered.checked);
        if (business.cross_border) payload.cross_border = business.cross_border.checked;
        var btn = business.querySelector('button[type=submit]');
        btn.disabled = true; btn.textContent = 'Saving…';
        api.kycProfile(payload).then(saved).catch(function (err) {
          btn.disabled = false; btn.textContent = 'Save business details';
          alert(err.message);
        });
      });
    }

    var person = el('#person-form');
    if (person) person.addEventListener('submit', function (e) {
      e.preventDefault();
      api.kycAddPerson({
        full_name: person.full_name.value.trim(), position: person.position.value.trim(),
        id_type: person.id_type.value, id_number: person.id_number.value.trim(),
        ownership_pct: person.ownership_pct ? person.ownership_pct.value : 0,
        is_control: !!(person.is_control && person.is_control.checked)
      }).then(saved).catch(function (err) { alert(err.message); });
    });

    el('.main').addEventListener('click', function (e) {
      var drop = e.target.closest('[data-drop-person]');
      if (drop) return void api.kycRemovePerson(drop.dataset.dropPerson).then(saved).catch(fail);

      var toggle = e.target.closest('[data-file]');
      if (toggle) {
        var form = toggle.closest('.doc-row').querySelector('.doc-form');
        form.hidden = !form.hidden;
        return;
      }
      var dropDoc = e.target.closest('[data-drop-doc]');
      if (dropDoc) return void api.kycRemoveDocument(dropDoc.dataset.dropDoc).then(saved).catch(fail);

      var view = e.target.closest('[data-view]');
      if (view) return void openDocument(view.dataset.view);
    });

    M.els('.doc-row .doc-form').forEach(function (form) {
      form.addEventListener('submit', function (e) {
        e.preventDefault();
        var key = form.closest('.doc-row').dataset.doc;
        var btn = form.querySelector('button[type=submit]');
        btn.disabled = true; btn.textContent = 'Filing…';
        readFile(form.file).then(function (upload) {
          var payload = { doc_key: key, reference: form.reference.value.trim() };
          if (form.expires_on) payload.expires_on = form.expires_on.value;
          if (upload) { payload.file = upload.file; payload.filename = upload.filename; }
          return api.kycFile(payload).then(saved);
        }).catch(function (err) {
          btn.disabled = false; btn.textContent = 'File document';
          alert(err.message);
        });
      });
    });

    var submitBtn = el('#kyc-submit');
    if (submitBtn) submitBtn.addEventListener('click', function () {
      submitBtn.disabled = true; submitBtn.textContent = 'Submitting…';
      api.kycSubmit().then(saved).catch(function (err) {
        submitBtn.disabled = false; submitBtn.textContent = 'Submit for verification';
        el('#submit-err').innerHTML = '<div class="notice notice-error">' + esc(err.message) + '</div>';
      });
    });
  }

  // Documents come back as base64 and are opened from a blob, so the file is
  // never a URL anyone can guess or share.
  function openDocument(id) {
    api.kycDownload(id).then(function (doc) {
      var binary = atob(doc.content);
      var bytes = new Uint8Array(binary.length);
      for (var i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
      var url = URL.createObjectURL(new Blob([bytes], { type: doc.mime }));
      window.open(url, '_blank');
      setTimeout(function () { URL.revokeObjectURL(url); }, 60000);
    }).catch(function (err) { alert(err.message); });
  }

  /* --- compliance queue (ops) ------------------------------------------- */
  function viewOpsKyc() {
    api.kycQueue().then(function (res) {
      var rows = res.applicants.map(function (a) {
        return '<tr data-applicant="' + a.id + '">' +
          '<td><b>' + esc(a.company || a.legal_name || a.name) + '</b><span class="sub">' + esc(a.name) + '</span></td>' +
          '<td>' + esc(ROLE_LABEL[a.role]) + '</td>' +
          '<td class="mono">' + esc(a.reg_number || '—') + '<span class="sub">' + esc(a.tin || '') + '</span></td>' +
          '<td>' + kycPill(a.status, a.status_label) + '</td>' +
          '<td class="num">' + esc(a.submitted_at ? M.ago(a.submitted_at) : '—') + '</td></tr>';
      }).join('');

      shell(
        pageHead('Compliance', res.waiting + ' file' + (res.waiting === 1 ? '' : 's') + ' waiting on review') +
        (res.applicants.length
          ? '<div class="table-wrap"><table><thead><tr><th>Account</th><th>Side</th><th>Registration</th>' +
            '<th>Status</th><th class="num">Submitted</th></tr></thead><tbody>' + rows + '</tbody></table></div>'
          : empty('No accounts yet', 'Signups appear here the moment they are created.'))
      );

      M.els('tr[data-applicant]').forEach(function (tr) {
        tr.addEventListener('click', function () { location.hash = '#/kyc/' + tr.dataset.applicant; });
      });
    }).catch(fail);
  }

  function viewOpsKycOne(id) {
    api.kycApplicant(id).then(function (k) {
      var p = k.profile || {};
      var rows = k.checklist.map(function (item) {
        var doc = item.document;
        return '<tr><td><b>' + esc(item.name) + '</b>' + (item.mandatory ? '' : '<span class="sub">Optional</span>') + '</td>' +
          '<td class="mono">' + esc((doc || {}).reference || '—') + '</td>' +
          '<td>' + esc(doc && doc.expires_on ? doc.expires_on : '—') + '</td>' +
          '<td>' + (doc ? kycPill(doc.status === 'accepted' ? 'verified' : (doc.status === 'rejected' ? 'rejected' : 'in_review'),
                                  doc.status) : kycPill('unverified', 'outstanding')) + '</td>' +
          '<td class="num">' + (doc && doc.has_file ? '<button class="btn btn-ghost btn-sm" data-view="' + doc.id + '">Open</button>' : '') +
            (doc ? '<label class="check reject-check"><input type="checkbox" name="reject" value="' + esc(item.key) + '"><span>Reject</span></label>' : '') +
          '</td></tr>';
      }).join('');

      shell(
        pageHead(k.applicant.company || p.legal_name || k.applicant.name,
                 ROLE_LABEL[k.applicant.role] + ' · ' + esc(k.applicant.phone),
                 kycPill(k.status, k.status_label) + ' <a class="btn btn-ghost btn-sm" style="margin-left:8px" href="#/kyc">Back to queue</a>') +
        '<div class="kyc-grid">' +
          '<div>' +
            '<section class="panel"><h3>Business</h3>' +
              '<dl class="facts">' +
                [['Legal name', p.legal_name], ['Trading as', p.trading_name],
                 ['Type', k.entity_name], ['Registration', p.reg_number], ['TPIN', p.tin],
                 ['VAT', p.vat_registered ? (p.vat_number || 'Registered') : 'Not registered'],
                 ['Country', p.country], ['Sector', p.sector], ['Address', p.address]]
                  .map(function (f) {
                    return '<dt>' + esc(f[0]) + '</dt><dd>' + esc(f[1] || '—') + '</dd>';
                  }).join('') +
              '</dl></section>' +
            '<section class="panel"><h3>People</h3>' +
              (k.people.length
                ? '<div class="table-wrap"><table><thead><tr><th>Name</th><th>Position</th><th>Identity</th>' +
                  '<th class="num">Owns</th></tr></thead><tbody>' + k.people.map(function (person) {
                    return '<tr><td><b>' + esc(person.full_name) + '</b>' +
                      (person.is_control ? '<span class="sub">Control person</span>' : '') + '</td>' +
                      '<td>' + esc(person.position) + '</td>' +
                      '<td class="mono">' + esc(person.id_number) + '<span class="sub">' + esc(person.id_type.toUpperCase()) + '</span></td>' +
                      '<td class="num">' + (person.ownership_pct ? esc(person.ownership_pct) + '%' : '—') + '</td></tr>';
                  }).join('') + '</tbody></table></div>'
                : '<p class="muted">Nobody named yet.</p>') + '</section>' +
            '<section class="panel"><h3>Documents</h3>' +
              '<div class="table-wrap"><table><thead><tr><th>Document</th><th>Reference</th><th>Expires</th>' +
              '<th>Status</th><th class="num">Review</th></tr></thead><tbody>' + rows + '</tbody></table></div></section>' +
          '</div>' +
          '<aside>' +
            '<section class="panel"><h3>Decision</h3>' +
              (k.blockers.length
                ? '<div class="notice notice-error">Incomplete file: ' + esc(k.blockers.slice(0, 3).join('; ')) + '</div>'
                : '') +
              '<div id="decision-err"></div>' +
              '<label class="field"><span>Note to the applicant</span>' +
                '<textarea class="input" id="decision-note" rows="3" placeholder="Required when sending a file back"></textarea></label>' +
              '<button class="btn btn-primary btn-block" data-decision="verified">Verify this account</button>' +
              '<button class="btn btn-ghost btn-block" style="margin-top:8px" data-decision="rejected">Send back for fixes</button>' +
            '</section>' +
            (k.events.length
              ? '<section class="panel"><h3>History</h3><ol class="timeline">' + k.events.map(function (e) {
                  return '<li><b>' + esc(kycStatusLabel(e.status)) + '</b><span>' + esc(e.note || '') + '</span>' +
                         '<span class="sub">' + esc(M.when(e.created_at)) + (e.actor ? ' · ' + esc(e.actor) : '') + '</span></li>';
                }).join('') + '</ol></section>' : '') +
          '</aside>' +
        '</div>'
      );

      el('.main').addEventListener('click', function (e) {
        var view = e.target.closest('[data-view]');
        if (view) return void openDocument(view.dataset.view);
        var decide = e.target.closest('[data-decision]');
        if (!decide) return;
        var rejected = M.els('input[name=reject]:checked').map(function (input) { return input.value; });
        decide.disabled = true;
        api.kycDecide(id, {
          decision: decide.dataset.decision,
          note: el('#decision-note').value.trim(),
          reject_documents: rejected
        }).then(function () { viewOpsKycOne(id); }).catch(function (err) {
          decide.disabled = false;
          el('#decision-err').innerHTML = '<div class="notice notice-error">' + esc(err.message) + '</div>';
        });
      });
    }).catch(fail);
  }

  /* ====================================================================== */
  /* AGREEMENTS                                                             */
  /* ====================================================================== */

  var AGR_PILL = { draft: 'placed', sent: 'assigned', viewed: 'at_pickup',
                   signed: 'delivered', declined: 'cancelled', void: 'cancelled' };

  function agreementPill(a) {
    return '<span class="pill pill-' + esc(AGR_PILL[a.status] || 'placed') + '">' + esc(a.status_label) + '</span>';
  }

  function agreementRows(list) {
    return list.map(function (a) {
      return '<tr data-agreement="' + esc(a.ref) + '">' +
        '<td><b>' + esc(a.title) + '</b><span class="sub mono">' + esc(a.ref) + '</span></td>' +
        '<td>' + esc(a.counterparty) + '<span class="sub">' + esc(a.counterparty_email || a.counterparty_phone || '') + '</span></td>' +
        '<td>' + esc(a.kind_label) + (a.order_ref ? '<span class="sub mono">' + esc(a.order_ref) + '</span>' : '') + '</td>' +
        '<td>' + agreementPill(a) + (a.expired ? '<span class="sub">Link expired</span>' : '') + '</td>' +
        '<td class="num">' + esc(a.signed_at ? M.ago(a.signed_at) : (a.sent_at ? M.ago(a.sent_at) : M.ago(a.created_at))) + '</td>' +
        '</tr>';
    }).join('');
  }

  function bindAgreementRows() {
    M.els('tr[data-agreement]').forEach(function (tr) {
      tr.addEventListener('click', function () { location.hash = '#/agreements/' + tr.dataset.agreement; });
    });
  }

  // The customer's own view: what they have signed, and what is waiting.
  function viewAgreements() {
    api.agreements().then(function (res) {
      var open = res.agreements.filter(function (a) { return a.status === 'sent' || a.status === 'viewed'; });
      shell(
        pageHead('Agreements', 'Master terms, rate schedules and per-load agreements between you and Musanga.',
          state.user.role === 'ops' ? '<a class="btn btn-primary" href="#/agreements/new">Draft an agreement</a>' : '') +
        (open.length && state.user.role !== 'ops'
          ? '<div class="notice notice-error">' + open.length + ' document' + (open.length === 1 ? '' : 's') +
            ' waiting on your signature. Open one to sign it.</div>' : '') +
        (res.agreements.length
          ? '<div class="table-wrap"><table><thead><tr><th>Document</th><th>Counterparty</th><th>Type</th>' +
            '<th>Status</th><th class="num">Updated</th></tr></thead><tbody>' + agreementRows(res.agreements) +
            '</tbody></table></div>'
          : empty('No agreements yet', state.user.role === 'ops'
              ? 'Draft one and send it for signature.'
              : 'Anything Musanga sends you to sign will appear here.'))
      );
      bindAgreementRows();
    }).catch(fail);
  }

  function viewAgreement(ref) {
    api.agreement(ref).then(function (a) {
      var ops = state.user.role === 'ops';
      var link = location.origin + a.link;

      shell(
        pageHead(a.title, a.kind_label + ' · ' + a.counterparty,
          agreementPill(a) + ' <a class="btn btn-ghost btn-sm" style="margin-left:8px" href="#/agreements">Back</a>') +
        '<div class="kyc-grid">' +
          '<div><section class="panel"><div class="doc-preview">' + esc(a.body) + '</div></section></div>' +
          '<aside>' +
            (ops ? opsAgreementPanel(a, link) + linkPanel(a, link) + engagementPanel(a)
                 : signerPanel(a)) +
            '<section class="panel"><h3>Audit trail</h3><ol class="timeline">' +
              (a.events || []).map(function (e) {
                return '<li><b>' + esc(e.label) + '</b>' +
                  (e.actor ? '<span>' + esc(e.actor) + '</span>' : '') +
                  (e.ip ? '<span class="sub mono">' + esc(e.ip) + '</span>' : '') +
                  '<span class="sub">' + esc(M.when(e.created_at)) + '</span></li>';
              }).join('') + '</ol>' +
              '<p class="hash">SHA-256 ' + esc(a.body_hash) + '</p></section>' +
          '</aside>' +
        '</div>'
      );
      bindAgreement(a, link);
    }).catch(fail);
  }


  // What a sender actually wants to know before they pick up the phone: did it
  // land, did they read past the price, did they come back, did they forward
  // it. The signature is the last line of that story, not the whole of it.
  function minutes(seconds) {
    if (!seconds) return '0s';
    if (seconds < 60) return seconds + 's';
    var m = Math.floor(seconds / 60), s = seconds % 60;
    return m + 'm' + (s ? ' ' + s + 's' : '');
  }

  function engagementPanel(a) {
    var e = a.engagement || { views: [], count: 0 };
    if (!e.count) {
      return '<section class="panel"><h3>Engagement</h3>' +
        '<p class="muted">' + (a.status === 'draft'
          ? 'Nothing to see until this is sent.'
          : 'Sent, but not opened yet.') + '</p></section>';
    }

    var depth = e.sections ? Math.round(100 * e.furthest_section / e.sections) : 0;
    var rows = e.views.map(function (v) {
      return '<tr>' +
        '<td>' + esc(v.viewer_email || 'Anonymous') +
          '<span class="sub mono">' + esc(v.ip || '') + '</span></td>' +
        '<td>' + esc(M.ago(v.opened_at)) + '</td>' +
        '<td class="num">' + esc(minutes(v.seconds)) + '</td>' +
        '<td class="num">' + (v.sections ? Math.round(100 * v.max_section / v.sections) + '%' : '—') + '</td>' +
        '<td class="num">' + (v.signed ? 'signed' : (v.downloaded ? 'copied' : '')) + '</td>' +
      '</tr>';
    }).join('');

    return '<section class="panel"><h3>Engagement</h3>' +
      '<div class="tiles tiles-tight">' +
        '<div class="tile"><span>Opens</span><b>' + e.count + '</b><small>' +
          e.readers + ' reader' + (e.readers === 1 ? '' : 's') + '</small></div>' +
        '<div class="tile"><span>Time on it</span><b>' + esc(minutes(e.seconds)) + '</b><small>total</small></div>' +
        '<div class="tile"><span>Read to</span><b>' + depth + '%</b><small>of the document</small></div>' +
      '</div>' +
      '<div class="table-wrap"><table><thead><tr><th>Reader</th><th>Opened</th>' +
        '<th class="num">Time</th><th class="num">Depth</th><th class="num"></th>' +
      '</tr></thead><tbody>' + rows + '</tbody></table></div></section>';
  }

  function linkPanel(a, link) {
    if (a.status === 'draft') return '';
    return '<section class="panel"><h3>Link</h3>' +
      '<label class="field"><span>Anyone with this link</span>' +
        '<input class="input mono" id="sign-link" readonly value="' + esc(link) + '"></label>' +
      '<button class="btn btn-ghost btn-block" id="copy-link">Copy link</button>' +
      '<div class="link-toggles">' +
        '<label class="check"><input type="checkbox" data-link="require_email"' +
          (a.require_email ? ' checked' : '') + '><span>Ask for an email before opening</span></label>' +
        '<label class="check"><input type="checkbox" data-link="allow_download"' +
          (a.allow_download ? ' checked' : '') + '><span>Allow a copy to be downloaded</span></label>' +
        '<label class="check"><input type="checkbox" data-link="link_disabled"' +
          (a.link_disabled ? ' checked' : '') + '><span>Switch this link off</span></label>' +
      '</div>' +
      (a.expired ? '<p class="muted">The link expired. Reissue it to reopen.</p>' : '') +
      '</section>';
  }

  function signerPanel(a) {
    if (a.status === 'signed') {
      return '<section class="panel"><h3>Signed</h3>' +
        '<p class="muted">Signed by ' + esc(a.signer_name || '') + ' on ' + esc(M.when(a.signed_at)) + '.</p>' +
        '<a class="btn btn-ghost btn-block" href="' + esc(a.link) + '" target="_blank" rel="noopener">Open the signed copy</a></section>';
    }
    return '<section class="panel"><h3>Waiting on your signature</h3>' +
      '<p class="muted">Opens in the signing room. No password needed — the link is the key.</p>' +
      '<a class="btn btn-primary btn-block" href="' + esc(a.link) + '" target="_blank" rel="noopener">Read and sign</a></section>';
  }

  function opsAgreementPanel(a, link) {
    var sendable = a.status === 'draft' || a.status === 'sent' || a.status === 'viewed';
    return '<section class="panel"><h3>Send for signature</h3>' +
      '<div id="agr-err"></div>' +
      (a.status === 'draft'
        ? '<p class="muted">The text is frozen and hashed the moment this is sent. To change it after that, draft a new one.</p>'
        : '') +
      (sendable
        ? '<button class="btn btn-primary btn-block" style="margin-top:8px" data-send="1">' +
          (a.status === 'draft' ? 'Send for signature' : 'Reissue the link') + '</button>'
        : '') +
      (a.status === 'signed' && !a.countersigned_at
        ? '<button class="btn btn-primary btn-block" style="margin-top:8px" id="countersign">Countersign for Musanga</button>' : '') +
      (a.status === 'signed'
        ? '<p class="muted" style="margin-top:12px">Signed by ' + esc(a.signer_name || '') +
          (a.signer_title ? ', ' + esc(a.signer_title) : '') + ' on ' + esc(M.when(a.signed_at)) + '.</p>' +
          '<a class="btn btn-ghost btn-block" href="' + esc(a.link) + '" target="_blank" rel="noopener">Open the signed copy</a>'
        : '') +
      (a.status !== 'signed' && a.status !== 'void'
        ? '<button class="btn btn-ghost btn-block" style="margin-top:8px" id="void">Void this document</button>' : '') +
      '</section>';
  }

  function bindAgreement(a, link) {
    var copy = el('#copy-link');
    if (copy) copy.addEventListener('click', function () {
      var field = el('#sign-link');
      field.select();
      if (navigator.clipboard) navigator.clipboard.writeText(link);
      else document.execCommand('copy');
      copy.textContent = 'Copied';
      setTimeout(function () { copy.textContent = 'Copy link'; }, 1800);
    });

    var main = el('.main');
    main.addEventListener('click', function (e) {
      function done() { viewAgreement(a.ref); }
      function oops(err) { el('#agr-err').innerHTML = '<div class="notice notice-error">' + esc(err.message) + '</div>'; }

      if (e.target.closest('[data-send]')) {
        return void api.sendAgreement(a.ref, { reissue: a.status !== 'draft' }).then(done).catch(oops);
      }
      if (e.target.closest('#countersign')) {
        return void api.countersign(a.ref, { signature: state.user.name }).then(done).catch(oops);
      }
      var toggle = e.target.closest('[data-link]');
      if (toggle) {
        var change = {};
        change[toggle.dataset.link] = toggle.checked;
        return void api.agreementLink(a.ref, change).then(done).catch(oops);
      }
      if (e.target.closest('#void')) {
        var reason = prompt('Why is this being voided? Recorded against the document.');
        if (reason === null) return;
        return void api.voidAgreement(a.ref, { reason: reason }).then(done).catch(oops);
      }
    });
  }

  // Drafting: pick a template, name the counterparty, fill what the template
  // asks for. Anything derived from a booking fills itself in.
  function viewAgreementNew() {
    Promise.all([api.agreementTemplates(), api.network()]).then(function (r) {
      var templates = r[0].templates, network = r[1];
      var accounts = network.shippers.concat(network.carriers);
      var params = new URLSearchParams(location.hash.split('?')[1] || '');
      var chosen = templates.filter(function (t) { return t.key === (params.get('template') || 'master'); })[0] || templates[0];

      function draw() {
        var fields = chosen.fields.filter(function (f) {
          return ['company_name', 'company_reg', 'company_tpin', 'company_address', 'ref',
                  'counterparty', 'dated'].indexOf(f) < 0;
        });

        shell(
          pageHead('Draft an agreement', 'Pick the paper, name the counterparty, send the link.',
            '<a class="btn btn-ghost btn-sm" href="#/agreements">Cancel</a>') +
          '<div class="kyc-grid"><div>' +
            '<section class="panel"><h3>1. Template</h3><div class="entity-picker">' +
              templates.map(function (t) {
                return '<button type="button" data-template="' + esc(t.key) + '" aria-pressed="' + (t.key === chosen.key) + '">' +
                  '<b>' + esc(t.name) + '</b><span>' + esc(t.note) + '</span></button>';
              }).join('') + '</div></section>' +
            '<section class="panel"><h3>2. Counterparty and terms</h3>' +
              '<div id="draft-err"></div>' +
              '<form id="draft-form">' +
                '<label class="field"><span>Account on the network <span class="muted">(optional)</span></span>' +
                  '<select class="input" name="account_id"><option value="">Not an account yet</option>' +
                  accounts.map(function (acc) {
                    return '<option value="' + acc.id + '">' + esc((acc.company || acc.name) + ' · ' + ROLE_LABEL[acc.role]) + '</option>';
                  }).join('') + '</select></label>' +
                '<label class="field"><span>Counterparty, as it should appear on the contract</span>' +
                  '<input class="input" name="counterparty" required placeholder="ZamGrain Agri Limited"></label>' +
                '<div class="row2">' +
                  '<label class="field"><span>Signer email</span><input class="input" name="counterparty_email" type="email"></label>' +
                  '<label class="field"><span>Signer phone</span><input class="input" name="counterparty_phone"></label>' +
                '</div>' +
                (chosen.kind === 'shipment'
                  ? '<label class="field"><span>Booking reference</span><input class="input" name="order_ref" placeholder="MSG-A1B2C3">' +
                    '<span class="sub">The load’s rate, lane and tonnage fill themselves in.</span></label>' : '') +
                // A quotation is priced by the same engine that would charge
                // for the load, so the lane is typed once and the numbers in
                // the document are the numbers on the platform.
                (chosen.kind === 'quotation'
                  ? '<h4 class="doc-group">The lane</h4>' +
                    '<div class="row2">' +
                      '<label class="field"><span>From</span><select class="input" name="q_from">' +
                        M.zoneOptions(state.config.zones, state.config.countries) + '</select></label>' +
                      '<label class="field"><span>To</span><select class="input" name="q_to">' +
                        M.zoneOptions(state.config.zones, state.config.countries) + '</select></label>' +
                    '</div>' +
                    '<div class="row2">' +
                      '<label class="field"><span>Commodity</span><select class="input" name="q_commodity">' +
                        M.options(state.config.commodities, 'key', 'name') + '</select></label>' +
                      '<label class="field"><span>Equipment</span><select class="input" name="q_equipment">' +
                        M.options(state.config.equipment, 'key', 'name') + '</select></label>' +
                    '</div>' +
                    '<div class="row2">' +
                      '<label class="field"><span>Tonnes per load</span>' +
                        '<input class="input" name="q_tonnes" type="number" min="1" step="0.5" value="34"></label>' +
                      '<label class="field"><span>Number of loads</span>' +
                        '<input class="input" name="q_loads" type="number" min="1" step="1" value="1"></label>' +
                    '</div>' +
                    '<div class="row2">' +
                      '<label class="field"><span>Terms</span><select class="input" name="q_service">' +
                        M.options(state.config.services, 'key', 'name') + '</select></label>' +
                      '<label class="field"><span>Valid for (days)</span>' +
                        '<input class="input" name="q_valid" type="number" min="1" max="90" value="14"></label>' +
                    '</div>' +
                    '<div class="row2">' +
                      '<label class="field"><span>Loading point <span class="muted">(optional)</span></span>' +
                        '<input class="input" name="q_pickup" placeholder="Mkushi, Chisomo Farm weighbridge"></label>' +
                      '<label class="field"><span>Discharge point <span class="muted">(optional)</span></span>' +
                        '<input class="input" name="q_dropoff" placeholder="Harare, Willowvale mill"></label>' +
                    '</div>' +
                    '<div id="lane-preview" class="lane-preview"></div>' : '') +
                (chosen.kind === 'hire'
                  ? '<label class="field"><span>Hire reference</span><input class="input" name="hire_ref" placeholder="HIR-A1B2C3"></label>' : '') +
                '<h4 class="doc-group">Terms in this template</h4>' +
                '<div class="row2">' + fields.map(function (f) {
                  var value = chosen.defaults[f] || '';
                  var label = f.replace(/_/g, ' ').replace(/^./, function (c) { return c.toUpperCase(); });
                  return '<label class="field"><span>' + esc(label) + '</span>' +
                    (f === 'rate_lines'
                      ? '<textarea class="input" name="f_' + esc(f) + '" rows="4">' + esc(value) + '</textarea>'
                      : '<input class="input" name="f_' + esc(f) + '" value="' + esc(value) + '">') + '</label>';
                }).join('') + '</div>' +
                '<button class="btn btn-primary" type="submit">Create draft</button>' +
              '</form></section>' +
          '</div><aside><section class="panel"><h3>How this works</h3>' +
            '<ol class="how"><li>You draft it here and read it through.</li>' +
            '<li>Sending freezes the text and hashes it.</li>' +
            '<li>The counterparty gets a link — no account, no password.</li>' +
            '<li>They read, sign, and get a copy.</li>' +
            '<li>Every open, signature and download is recorded.</li></ol></section></aside></div>'
        );

        el('.entity-picker').addEventListener('click', function (e) {
          var btn = e.target.closest('[data-template]');
          if (!btn) return;
          chosen = templates.filter(function (t) { return t.key === btn.dataset.template; })[0];
          draw();
        });

        var form = el('#draft-form');
        bindLanePreview(form);
        var accountSelect = form.account_id;
        accountSelect.addEventListener('change', function () {
          var acc = accounts.filter(function (a) { return String(a.id) === accountSelect.value; })[0];
          if (!acc) return;
          form.counterparty.value = acc.company || acc.name;
          form.counterparty_email.value = acc.email || '';
          form.counterparty_phone.value = acc.phone || '';
        });

        form.addEventListener('submit', function (e) {
          e.preventDefault();
          var payload = {
            template: chosen.key,
            counterparty: form.counterparty.value.trim(),
            counterparty_email: form.counterparty_email.value.trim(),
            counterparty_phone: form.counterparty_phone.value.trim(),
            account_id: accountSelect.value || null,
            order_ref: form.order_ref ? form.order_ref.value.trim() : '',
            hire_ref: form.hire_ref ? form.hire_ref.value.trim() : '',
            fields: {}
          };
          M.els('#draft-form [name^=f_]').forEach(function (input) {
            payload.fields[input.name.slice(2)] = input.value;
          });
          if (form.q_from) payload.quote = laneFromForm(form);
          var btn = form.querySelector('button[type=submit]');
          btn.disabled = true; btn.textContent = 'Drafting…';
          api.draftAgreement(payload).then(function (a) {
            location.hash = '#/agreements/' + a.ref;
          }).catch(function (err) {
            btn.disabled = false; btn.textContent = 'Create draft';
            el('#draft-err').innerHTML = '<div class="notice notice-error">' + esc(err.message) + '</div>';
          });
        });
      }
      draw();
    }).catch(fail);
  }


  // The lane fields, in the shape the rate engine wants them.
  function laneFromForm(form) {
    return {
      from_zone: form.q_from.value, to_zone: form.q_to.value,
      commodity: form.q_commodity.value, equipment: form.q_equipment.value,
      service: form.q_service.value,
      tonnes: parseFloat(form.q_tonnes.value) || 0,
      loads: parseInt(form.q_loads.value, 10) || 1,
      valid_days: parseInt(form.q_valid.value, 10) || 14,
      pickup: form.q_pickup.value.trim(), dropoff: form.q_dropoff.value.trim()
    };
  }

  // Price the lane as it is typed, so nobody sends a quotation without having
  // seen the number it carries.
  function bindLanePreview(form) {
    if (!form.q_from) return;
    var out = el('#lane-preview');
    var price = M.debounce(function () {
      var lane = laneFromForm(form);
      api.quote({
        equipment: lane.equipment, service: lane.service, commodity: lane.commodity,
        from_zone: lane.from_zone, to_zone: lane.to_zone, tonnes: lane.tonnes
      }).then(function (q) {
        var perTonne = q.billed_tonnes ? q.total_ngwee / q.billed_tonnes : 0;
        out.innerHTML =
          '<b>' + esc(q.from_name) + ' &rarr; ' + esc(q.to_name) + '</b>' +
          '<span>' + esc(q.distance_km) + ' km' +
            (q.crossings && q.crossings.length
              ? ' · ' + esc(q.crossings.map(function (c) { return c.post; }).join(', '))
              : '') +
            ' · ' + esc(q.billed_tonnes) + ' t billed</span>' +
          '<div class="lane-price">' + esc(q.total) +
            '<small>' + esc(money(perTonne, q)) + ' per tonne' +
            (lane.loads > 1 ? ' · ' + esc(money(q.total_ngwee * lane.loads, q)) +
             ' for ' + lane.loads + ' loads' : '') + '</small></div>';
      }).catch(function (err) {
        out.innerHTML = '<span class="muted">' + esc(err.message) + '</span>';
      });
    }, 250);

    M.els('#draft-form [name^=q_]').forEach(function (input) {
      input.addEventListener('change', price);
      input.addEventListener('input', price);
    });
    price();
  }

  // Money on an export lane is quoted in USD but carried in ngwee, the way it
  // is everywhere else in the platform - the quote response brings the rate it
  // was converted at. Dividing by 100 alone would be out by a factor of 27.
  function money(ngwee, quote) {
    var amount = ngwee / 100;
    if (quote.currency === 'USD') {
      return '$' + (amount / (quote.fx_zmw_per_usd || 1)).toLocaleString('en-ZM',
        { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    }
    return 'K' + amount.toLocaleString('en-ZM',
      { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  }

  /* ====================================================================== */
  /* NETWORK — every counterparty, in one place                             */
  /* ====================================================================== */

  function accountRows(list) {
    return list.map(function (a) {
      return '<tr data-account="' + a.id + '">' +
        '<td><b>' + esc(a.company || a.name) + '</b><span class="sub">' + esc(a.name) + ' · ' + esc(a.phone) + '</span></td>' +
        '<td>' + kycPill(a.kyc_status, a.kyc_status_label) +
          (a.account_status === 'suspended' ? '<span class="sub warn">Suspended</span>' : '') + '</td>' +
        '<td class="num">' + a.live_loads + '<span class="sub">' + a.loads + ' all time</span></td>' +
        '<td class="num">' + esc(a.value) + '</td>' +
        '<td class="num">' + a.agreements_signed +
          (a.agreements_waiting ? '<span class="sub">' + a.agreements_waiting + ' out</span>' : '') + '</td>' +
        '</tr>';
    }).join('');
  }

  /* --- RFPs: request for prices and capacity ---------------------------- */

  function rfpStatusPill(r) {
    var map = { open: 'placed', closed: 'delivered', void: 'cancelled' };
    return '<span class="pill pill-' + (map[r.status] || 'placed') + '">' +
           esc(r.status_label || r.status) + '</span>';
  }

  function viewOpsRfps() {
    api.rfps().then(function (res) {
      var rfps = res.rfps || [];
      var rows = rfps.map(function (r) {
        var c = r.counts || {};
        return '<tr data-rfp="' + esc(r.ref) + '" style="cursor:pointer">' +
          '<td><b class="mono">' + esc(r.ref) + '</b><span class="sub">' + esc(M.ago(r.created_at)) + '</span></td>' +
          '<td>' + esc(r.title) + '<span class="sub">' + esc(r.corridor) + '</span></td>' +
          '<td>' + esc(r.commodity) + '<span class="sub">' + esc(r.equipment) + '</span></td>' +
          '<td class="num">' + esc(r.tonnes_total || 0) + ' t<span class="sub">' + esc(r.trucks_needed || 0) + ' trucks</span></td>' +
          '<td class="num">' + esc(c.invited || 0) + '<span class="sub">' + esc(c.submitted || 0) + ' bid, ' + esc(c.declined || 0) + ' no</span></td>' +
          '<td>' + rfpStatusPill(r) + '</td>' +
          '</tr>';
      }).join('');
      shell(
        pageHead('RFPs', 'Send a lane out to transporters for firm prices and firm capacity. The bid signs our terms.',
          '<a class="btn btn-primary btn-sm" href="#/rfps/new">Draft an RFP</a>') +
        (rfps.length
          ? '<div class="table-wrap"><table><thead><tr>' +
            '<th>Reference</th><th>Lane</th><th>Commodity</th><th class="num">Ask</th>' +
            '<th class="num">Invited</th><th>Status</th></tr></thead><tbody>' +
            rows + '</tbody></table></div>'
          : empty('No RFPs yet', 'Draft one to send a lane out to a set of transporters.'))
      );
      document.querySelectorAll('tr[data-rfp]').forEach(function (tr) {
        tr.addEventListener('click', function () {
          location.hash = '#/rfps/' + tr.dataset.rfp;
        });
      });
    }).catch(function (e) { alert(e.message); });
  }

  function viewOpsRfpNew() {
    var invRows = [{}, {}, {}];
    function renderInv() {
      return invRows.map(function (r, i) {
        return '<div class="grid-3" style="gap:8px;align-items:end">' +
          '<label><span class="lbl">Transporter name</span><input data-inv="' + i + '" data-field="name" value="' + esc(r.name || '') + '"></label>' +
          '<label><span class="lbl">Email</span><input data-inv="' + i + '" data-field="email" type="email" value="' + esc(r.email || '') + '"></label>' +
          '<label><span class="lbl">Phone</span><input data-inv="' + i + '" data-field="phone" value="' + esc(r.phone || '') + '"></label>' +
        '</div>';
      }).join('<div style="height:8px"></div>');
    }
    function draw() {
      shell(
        pageHead('Draft an RFP', 'One link per transporter. Submitting a bid signs our terms.') +
        '<form id="rfp-form" class="panel stack" autocomplete="off">' +
          '<div class="grid-2">' +
            '<label>Title<input required name="title" placeholder="e.g. Copper concentrate — Solwezi to Dar es Salaam, Sep"></label>' +
            '<label>Corridor label<input name="corridor" placeholder="Optional — defaults to loading → discharge"></label>' +
            '<label>Loading point<input required name="from_place" placeholder="e.g. Kalumbila mine gate"></label>' +
            '<label>Discharge point<input required name="to_place" placeholder="e.g. TICTS, Dar es Salaam"></label>' +
            '<label>Commodity<input required name="commodity" placeholder="e.g. Copper concentrate in sealed bags"></label>' +
            '<label>Equipment<input required name="equipment" placeholder="e.g. Sidetipper 34t"></label>' +
            '<label>Tonnage to move<input name="tonnes_total" type="number" min="0" step="1" placeholder="e.g. 2500"></label>' +
            '<label>Trucks needed<input name="trucks_needed" type="number" min="0" step="1" placeholder="e.g. 12"></label>' +
            '<label>Loading window from<input name="loading_from" type="date"></label>' +
            '<label>Loading window to<input name="loading_to" type="date"></label>' +
            '<label>Currency<select name="currency"><option value="ZMW">ZMW (Kwacha)</option><option value="USD">USD</option><option value="TZS">TZS</option></select></label>' +
            '<label>Target rate per tonne <span class="muted">(optional, in the currency above)</span><input name="target_rate" type="number" step="0.01" min="0"></label>' +
            '<label>Minimum GIT cover per load<input name="cover_min" value="K500,000" placeholder="e.g. K500,000"></label>' +
            '<label>Bids close in <span class="muted">days</span><input name="closes_in_days" type="number" min="1" step="1" value="7"></label>' +
          '</div>' +
          '<label>Notes for transporters<textarea name="notes" rows="3" placeholder="Loading times, escort requirement, permit lead time — anything they need to price honestly."></textarea></label>' +

          '<h3 style="margin:24px 0 6px">Send to</h3>' +
          '<p class="muted">Each transporter gets their own link. Add as many as you need.</p>' +
          '<div id="invitees">' + renderInv() + '</div>' +
          '<div><button type="button" class="btn btn-ghost btn-sm" id="add-inv">+ another transporter</button></div>' +

          '<div class="sign-actions"><button class="btn btn-primary" type="submit">Send RFP</button>' +
            '<a class="btn btn-ghost" href="#/rfps">Cancel</a></div>' +
          '<p id="rfp-err" class="notice notice-error" style="display:none"></p>' +
        '</form>'
      );

      var box = document.getElementById('invitees');
      box.addEventListener('input', function (e) {
        var t = e.target;
        if (t.dataset && t.dataset.inv !== undefined) {
          var idx = Number(t.dataset.inv);
          if (!invRows[idx]) invRows[idx] = {};
          invRows[idx][t.dataset.field] = t.value;
        }
      });
      document.getElementById('add-inv').addEventListener('click', function () {
        invRows.push({});
        box.innerHTML = renderInv();
      });
      document.getElementById('rfp-form').addEventListener('submit', function (e) {
        e.preventDefault();
        var f = e.target;
        var target = f.target_rate.value ? Math.round(Number(f.target_rate.value) * 100) : null;
        var payload = {
          title: f.title.value, corridor: f.corridor.value,
          from_place: f.from_place.value, to_place: f.to_place.value,
          commodity: f.commodity.value, equipment: f.equipment.value,
          tonnes_total: f.tonnes_total.value, trucks_needed: f.trucks_needed.value,
          loading_from: f.loading_from.value, loading_to: f.loading_to.value,
          currency: f.currency.value, target_ngwee_per_tonne: target,
          cover_min: f.cover_min.value, closes_in_days: f.closes_in_days.value,
          notes: f.notes.value,
          invitees: invRows.filter(function (r) { return r && r.name; })
        };
        if (!payload.invitees.length) {
          var err = document.getElementById('rfp-err');
          err.textContent = 'Add at least one transporter to send to.';
          err.style.display = '';
          return;
        }
        var btn = f.querySelector('button[type=submit]');
        btn.disabled = true; btn.textContent = 'Sending…';
        api.createRfp(payload).then(function (r) {
          location.hash = '#/rfps/' + r.ref;
        }).catch(function (e) {
          var err = document.getElementById('rfp-err');
          err.textContent = e.message; err.style.display = '';
          btn.disabled = false; btn.textContent = 'Send RFP';
        });
      });
    }
    draw();
  }

  function viewOpsRfp(ref) {
    api.rfp(ref).then(function (r) {
      var invites = r.invites || [], bids = r.bids || [];
      var invRows = invites.map(function (i) {
        return '<tr>' +
          '<td>' + esc(i.carrier_name) + '<span class="sub">' + esc(i.carrier_email || i.carrier_phone || '') + '</span></td>' +
          '<td>' + esc(i.status_label) + '</td>' +
          '<td>' + esc(i.sent_at ? M.ago(i.sent_at) : '') + '</td>' +
          '<td>' + esc(i.opened_at ? M.ago(i.opened_at) : '—') + '</td>' +
          '<td>' + esc(i.submitted_at ? M.ago(i.submitted_at) : (i.declined_at ? 'Declined ' + M.ago(i.declined_at) : '—')) + '</td>' +
          '<td><button class="btn btn-ghost btn-sm" data-copy="' + esc(i.link) + '">Copy link</button></td>' +
        '</tr>';
      }).join('');
      var bidRows = bids.map(function (b) {
        var actions = (r.status === 'open' && b.status !== 'awarded')
          ? '<button class="btn btn-primary btn-sm" data-award="' + b.id + '">Award</button>'
          : (b.status === 'awarded' ? '<span class="pill pill-delivered">Awarded</span>' : '');
        return '<tr>' +
          '<td><b>' + esc(b.carrier_name) + '</b><span class="sub">Signed by ' + esc(b.signer_name) + (b.signer_title ? ', ' + esc(b.signer_title) : '') + '</span></td>' +
          '<td class="num"><b>' + esc(b.rate) + '</b>/t</td>' +
          '<td class="num">' + esc(b.trucks_offered) + ' trucks<span class="sub">' + esc(b.capacity_tonnes) + ' t</span></td>' +
          '<td>' + esc([b.available_from, b.available_to].filter(Boolean).join(' → ') || '—') + '</td>' +
          '<td class="mono" style="font-size:.72rem">' + esc((b.terms_hash || '').slice(0, 16)) + '…</td>' +
          '<td>' + actions + '</td>' +
        '</tr>';
      }).join('');

      shell(
        pageHead(r.title, r.corridor + ' · ' + r.commodity,
          r.status === 'open'
            ? '<button class="btn btn-ghost btn-sm" id="close-rfp">Close RFP</button>'
            : '') +
        '<section class="panel"><h3>The ask</h3>' +
          '<dl class="ask-list">' +
            '<div class="ask-row"><dt>Reference</dt><dd class="mono">' + esc(r.ref) + '</dd></div>' +
            '<div class="ask-row"><dt>Status</dt><dd>' + rfpStatusPill(r) + '</dd></div>' +
            '<div class="ask-row"><dt>Tonnage</dt><dd>' + esc(r.tonnes_total || 0) + ' t across ' + esc(r.trucks_needed || 0) + ' trucks</dd></div>' +
            '<div class="ask-row"><dt>Loading window</dt><dd>' + esc([r.loading_from, r.loading_to].filter(Boolean).join(' → ') || '—') + '</dd></div>' +
            '<div class="ask-row"><dt>Currency</dt><dd>' + esc(r.currency) + (r.target_rate ? ' (target ' + esc(r.target_rate) + '/t)' : '') + '</dd></div>' +
            '<div class="ask-row"><dt>Cover required</dt><dd>' + esc(r.cover_min || '—') + '</dd></div>' +
            '<div class="ask-row"><dt>Closes</dt><dd>' + esc(r.closes_at ? M.when(r.closes_at) : '—') + '</dd></div>' +
            (r.notes ? '<div class="ask-row"><dt>Notes</dt><dd>' + esc(r.notes) + '</dd></div>' : '') +
          '</dl>' +
        '</section>' +

        '<section class="panel"><h3>Invited transporters (' + invites.length + ')</h3>' +
          (invites.length
            ? '<div class="table-wrap"><table><thead><tr><th>Transporter</th><th>Status</th>' +
              '<th>Sent</th><th>Opened</th><th>Bid</th><th></th></tr></thead><tbody>' +
              invRows + '</tbody></table></div>'
            : '<p class="muted">Nobody invited yet.</p>') +
        '</section>' +

        '<section class="panel"><h3>Bids received (' + bids.length + ')</h3>' +
          (bids.length
            ? '<div class="table-wrap"><table><thead><tr><th>Bidder</th><th class="num">Rate</th>' +
              '<th class="num">Capacity</th><th>Available</th><th>Terms hash</th><th></th>' +
              '</tr></thead><tbody>' + bidRows + '</tbody></table></div>'
            : '<p class="muted">No bids submitted yet.</p>') +
        '</section>' +

        '<section class="panel"><h3>Bidding terms signed by each bidder</h3>' +
          '<p class="muted mono" style="font-size:.72rem">SHA-256 ' + esc(r.terms_hash) + '</p>' +
          '<pre class="doc-body" style="white-space:pre-wrap;font-family:inherit">' + esc(r.terms_body) + '</pre>' +
        '</section>'
      );

      document.querySelectorAll('[data-copy]').forEach(function (btn) {
        btn.addEventListener('click', function () {
          navigator.clipboard && navigator.clipboard.writeText(btn.dataset.copy);
          btn.textContent = 'Copied';
          setTimeout(function () { btn.textContent = 'Copy link'; }, 1500);
        });
      });
      document.querySelectorAll('[data-award]').forEach(function (btn) {
        btn.addEventListener('click', function () {
          if (!confirm('Award this RFP to this bidder?')) return;
          api.awardBid(r.ref, { bid_id: Number(btn.dataset.award) })
            .then(function () { viewOpsRfp(ref); })
            .catch(function (e) { alert(e.message); });
        });
      });
      var closeBtn = document.getElementById('close-rfp');
      if (closeBtn) closeBtn.addEventListener('click', function () {
        if (!confirm('Close this RFP? Transporters will no longer be able to bid.')) return;
        api.closeRfp(r.ref).then(function () { viewOpsRfp(ref); })
          .catch(function (e) { alert(e.message); });
      });
    }).catch(function (e) { alert(e.message); location.hash = '#/rfps'; });
  }

  function viewNetwork() {
    api.network().then(function (net) {
      function table(list, label) {
        return '<h3 style="margin:28px 0 14px">' + label + ' <span class="muted">' + list.length + '</span></h3>' +
          (list.length
            ? '<div class="table-wrap"><table><thead><tr><th>Account</th><th>Verification</th>' +
              '<th class="num">Live</th><th class="num">Value</th><th class="num">Signed</th></tr></thead><tbody>' +
              accountRows(list) + '</tbody></table></div>'
            : empty('Nobody here yet', ''));
      }

      shell(
        pageHead('Network', 'Every shipper and carrier on the platform, and where each one stands.',
          '<a class="btn btn-primary btn-sm" href="#/agreements/new">Draft an agreement</a>') +
        '<div class="tiles">' +
          '<div class="tile accent"><span>Accounts</span><b>' + net.totals.accounts + '</b><small>shippers and carriers</small></div>' +
          '<div class="tile"><span>Awaiting review</span><b>' + net.totals.awaiting_review + '</b><small>KYC files submitted</small></div>' +
          '<div class="tile"><span>Never started</span><b>' + net.totals.unverified + '</b><small>limited mode</small></div>' +
          '<div class="tile"><span>Paper out</span><b>' + net.totals.paper_out + '</b><small>awaiting signature</small></div>' +
          '<div class="tile"><span>Suspended</span><b>' + net.totals.suspended + '</b><small>blocked from trading</small></div>' +
        '</div>' +
        table(net.shippers, 'Shippers') + table(net.carriers, 'Carriers')
      );

      M.els('tr[data-account]').forEach(function (tr) {
        tr.addEventListener('click', function () { location.hash = '#/network/' + tr.dataset.account; });
      });
    }).catch(fail);
  }

  function viewAccount(id) {
    api.account(id).then(function (d) {
      var a = d.account, k = d.kyc;
      var suspended = a.account_status === 'suspended';

      shell(
        pageHead(a.company || a.name, ROLE_LABEL[a.role] + ' · ' + a.phone + (a.email ? ' · ' + a.email : ''),
          kycPill(a.kyc_status, a.kyc_status_label) +
          ' <a class="btn btn-ghost btn-sm" style="margin-left:8px" href="#/network">Back</a>') +
        (suspended ? '<div class="notice notice-error">This account is suspended and cannot book, accept or draw.</div>' : '') +
        '<div class="tiles">' +
          '<div class="tile accent"><span>Live loads</span><b>' + a.live_loads + '</b><small>on the road now</small></div>' +
          '<div class="tile"><span>All loads</span><b>' + a.loads + '</b><small>' + a.tonnes + ' t moved</small></div>' +
          '<div class="tile"><span>' + (a.role === 'shipper' ? 'Freight spend' : 'Payouts') + '</span><b>' + esc(a.value) + '</b><small>lifetime</small></div>' +
          '<div class="tile"><span>Agreements</span><b>' + a.agreements_signed + '</b><small>' + a.agreements_waiting + ' awaiting signature</small></div>' +
        '</div>' +
        '<div class="kyc-grid"><div>' +
          '<section class="panel"><div class="panel-head"><h3>Agreements</h3>' +
            '<a class="btn btn-ghost btn-sm" href="#/agreements/new">Draft one</a></div>' +
            (d.agreements.length
              ? '<div class="table-wrap"><table><thead><tr><th>Document</th><th>Counterparty</th><th>Type</th>' +
                '<th>Status</th><th class="num">Updated</th></tr></thead><tbody>' + agreementRows(d.agreements) + '</tbody></table></div>'
              : '<p class="muted">Nothing signed or sent yet.</p>') + '</section>' +
          '<section class="panel"><div class="panel-head"><h3>Verification</h3>' +
            '<a class="btn btn-ghost btn-sm" href="#/kyc/' + a.id + '">Open the file</a></div>' +
            '<dl class="facts">' +
              [['Status', k.status_label], ['Business', (k.profile || {}).legal_name],
               ['Type', k.entity_name], ['Registration', (k.profile || {}).reg_number],
               ['TPIN', (k.profile || {}).tin],
               ['Documents', k.documents_filed + ' of ' + k.documents_required + ' filed'],
               ['People', k.people.length]].map(function (f) {
                return '<dt>' + esc(f[0]) + '</dt><dd>' + esc(f[1] === 0 ? '0' : (f[1] || '—')) + '</dd>';
              }).join('') + '</dl></section>' +
          (d.fuel_facility
            ? '<section class="panel"><h3>Fuel facility</h3><dl class="facts">' +
                '<dt>Limit</dt><dd>' + esc(M.kwacha(d.fuel_facility.limit_ngwee)) + '</dd>' +
                '<dt>Outstanding</dt><dd>' + esc(M.kwacha(d.fuel_facility.outstanding_ngwee)) + '</dd>' +
                '<dt>Status</dt><dd>' + esc(d.fuel_facility.status) + '</dd></dl></section>' : '') +
          '<section class="panel"><h3>Recent loads</h3>' +
            (d.orders.length
              ? orderTable(d.orders, [COL.ref, COL.route, COL.cargo, COL.status,
                                      a.role === 'shipper' ? COL.total : COL.payout])
              : '<p class="muted">No loads yet.</p>') + '</section>' +
        '</div><aside>' +
          '<section class="panel"><h3>Account</h3>' +
            '<div id="acct-err"></div>' +
            '<dl class="facts"><dt>Joined</dt><dd>' + esc(M.when(a.created_at)) + '</dd>' +
            '<dt>Trading</dt><dd>' + (suspended ? 'Suspended' : 'Active') + '</dd></dl>' +
            (suspended
              ? '<button class="btn btn-primary btn-block" data-account-status="active">Reactivate account</button>'
              : '<button class="btn btn-ghost btn-block" data-account-status="suspended">Suspend account</button>') +
          '</section>' +
          (k.status === 'in_review'
            ? '<section class="panel"><h3>Waiting on you</h3><p class="muted">This file was submitted ' +
              esc(M.ago(k.submitted_at)) + ' and has not been decided.</p>' +
              '<a class="btn btn-primary btn-block" href="#/kyc/' + a.id + '">Review the file</a></section>' : '') +
        '</aside></div>'
      );

      bindAgreementRows();
      el('.main').addEventListener('click', function (e) {
        var btn = e.target.closest('[data-account-status]');
        if (!btn) return;
        var next = btn.dataset.accountStatus;
        var reason = next === 'suspended' ? prompt('Why is this account being suspended?') : 'Reactivated';
        if (!reason) return;
        api.setAccountStatus(a.id, { status: next, reason: reason })
          .then(function () { viewAccount(id); })
          .catch(function (err) {
            el('#acct-err').innerHTML = '<div class="notice notice-error">' + esc(err.message) + '</div>';
          });
      });
    }).catch(fail);
  }

  var ROUTES = {
    shipper: { '': viewShipperHome, 'orders': viewShipperOrders, 'book': viewBook,
               'hire': viewHireBook, 'hires': viewHires, 'contracts': viewContracts,
               'verify': viewVerify, 'agreements': viewAgreements },
    driver:  { '': viewDriverBoard, 'my': viewDriverJobs, 'fuel': viewFuel,
               'earnings': viewEarnings, 'verify': viewVerify, 'agreements': viewAgreements },
    ops:     { '': viewOpsDispatch, 'orders': viewOpsOrders, 'drivers': viewOpsDrivers,
               'book': viewBook, 'hire': viewHireBook, 'hires': viewHires,
               'contracts': viewContracts, 'kyc': viewOpsKyc, 'network': viewNetwork,
               'quotes': viewOpsQuotes, 'rfps': viewOpsRfps, 'agreements': viewAgreements }
  };

  function route() {
    var hash = (location.hash || '#/').slice(2);
    var path = hash.split('?')[0];
    var parts = path.split('/');

    if (path === 'logout') {
      return api.logout().catch(function () {}).then(function () {
        api.setToken(null);
        state.user = null;
        location.hash = '#/login';
        route();
      });
    }

    if (!state.user) {
      return path === 'register' ? viewRegister() : viewLogin();
    }
    if (path === 'login' || path === 'register') {
      location.hash = '#/';
      return route();
    }

    // Detail views are shared by every role that can see them.
    if (parts[0] === 'orders' && parts[1]) return viewOrder(parts[1]);
    if (parts[0] === 'hires' && parts[1]) return viewHire(parts[1]);
    if (parts[0] === 'kyc' && parts[1] && state.user.role === 'ops') return viewOpsKycOne(parts[1]);
    if (parts[0] === 'network' && parts[1] && state.user.role === 'ops') return viewAccount(parts[1]);
    if (parts[0] === 'agreements' && parts[1]) {
      return parts[1] === 'new' ? viewAgreementNew() : viewAgreement(parts[1]);
    }
    if (parts[0] === 'quotes' && parts[1] && state.user.role === 'ops') return viewOpsQuote(parts[1]);
    if (parts[0] === 'rfps' && parts[1] && state.user.role === 'ops') {
      return parts[1] === 'new' ? viewOpsRfpNew() : viewOpsRfp(parts[1]);
    }

    var view = ROUTES[state.user.role][parts[0]];
    if (!view) { location.hash = '#/'; return; }
    view();
  }

  window.addEventListener('hashchange', route);

  /* --- boot ------------------------------------------------------------- */
  api.config().then(function (cfg) {
    state.config = cfg;
    if (!api.token()) { route(); return; }
    return api.me().then(function (res) {
      state.user = res.user;
      state.vehicle = res.vehicle || null;
      state.kyc = res.kyc || null;
      route();
    }).catch(function () {
      api.setToken(null);
      route();
    });
  }).catch(function () {
    root.innerHTML = '<div class="auth-wrap"><div class="auth-card">' +
      '<div class="notice notice-error">Cannot reach the Musanga API. Is the server running?</div></div></div>';
  });
})();
