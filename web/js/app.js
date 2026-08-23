/* Musanga platform: a hash-routed single page app over the JSON API.
   One shell, three role-specific navigations - shipper, driver, ops. */
(function () {
  'use strict';

  var M = window.M, api = M.api, esc = M.esc, el = M.el;
  var root = document.getElementById('root');

  var state = { user: null, vehicle: null, config: null };

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
    fuel:  '<path d="M4 20V5a2 2 0 0 1 2-2h5a2 2 0 0 1 2 2v15M3 20h12"/><path d="M13 9h3l2 2v6a2 2 0 0 0 2-2V8l-3-3"/><path d="M6 8h5"/>'
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
      { path: '#/hires', label: 'My hires', icon: 'truck' }
    ],
    driver: [
      { path: '#/', label: 'Load board', icon: 'grid' },
      { path: '#/my', label: 'My loads', icon: 'truck' },
      { path: '#/fuel', label: 'Fuel & cover', icon: 'fuel' },
      { path: '#/earnings', label: 'Earnings', icon: 'cash' }
    ],
    ops: [
      { path: '#/', label: 'Control', icon: 'grid' },
      { path: '#/orders', label: 'All loads', icon: 'list' },
      { path: '#/hires', label: 'Plant hire', icon: 'plant' },
      { path: '#/drivers', label: 'Carriers', icon: 'users' },
      { path: '#/book', label: 'Rate for a client', icon: 'plus' }
    ]
  };

  /* --- shared fragments -------------------------------------------------- */
  function statusPill(o) {
    return '<span class="pill pill-' + esc(o.status) + '">' + esc(o.status_label) + '</span>';
  }

  // What each role is called in the interface, as distinct from its key.
  var ROLE_LABEL = { shipper: 'Shipper', driver: 'Carrier', ops: 'Control' };

  function shell(bodyHtml) {
    var nav = NAV[state.user.role].map(function (item) {
      var active = (location.hash || '#/') === item.path;
      return '<a href="' + item.path + '" class="' + (active ? 'active' : '') + '">' +
             icon(item.icon) + '<span>' + esc(item.label) + '</span></a>';
    }).join('');

    root.innerHTML =
      '<div class="shell">' +
        '<aside class="sidebar">' +
          '<a class="logo" href="/">Musanga</a>' +
          '<span class="side-role">' + esc(ROLE_LABEL[state.user.role]) + '</span>' +
          '<nav class="side-nav">' + nav + '</nav>' +
          '<div class="side-foot">' +
            '<b>' + esc(state.user.name) + '</b>' +
            '<span class="muted">' + esc(state.user.company || state.user.phone) + '</span>' +
            '<a href="#/logout" style="display:flex;gap:8px;align-items:center;margin-top:10px;color:var(--ink-400)">' +
              icon('out') + '<span>Sign out</span></a>' +
          '</div>' +
        '</aside>' +
        '<main class="main">' + bodyHtml + '</main>' +
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
      '<p class="auth-alt">New to Musanga? <a href="#/register">Create an account</a></p>' +
      '<div class="demo-hint"><b>Demo accounts</b> (password <span class="mono">musanga2026</span>)<br>' +
        '<button data-fill="+260971000001">Shipper</button> &middot; ' +
        '<button data-fill="+260972000001">Carrier</button> &middot; ' +
        '<button data-fill="+260970000001">Control</button></div>'
    );

    el('.demo-hint').addEventListener('click', function (e) {
      if (!e.target.dataset.fill) return;
      var f = el('#f');
      f.phone.value = e.target.dataset.fill;
      f.password.value = 'musanga2026';
    });

    el('#f').addEventListener('submit', function (e) {
      e.preventDefault();
      var f = e.target;
      submit(f, api.login({ phone: f.phone.value.trim(), password: f.password.value }));
    });
  }

  function viewRegister() {
    var wanted = new URLSearchParams((location.hash.split('?')[1] || '')).get('role');
    var role = ['shipper', 'driver', 'ops'].indexOf(wanted) >= 0 ? wanted : 'shipper';

    function draw() {
      authShell(
        '<h2>Create your account</h2><p class="muted">One account, whichever side of the network you are on.</p>' +
        '<div class="role-picker">' +
          ['shipper', 'driver', 'ops'].map(function (r) {
            var label = { shipper: 'I ship', driver: 'I haul', ops: 'Musanga control' }[r];
            return '<button type="button" data-role="' + r + '" aria-pressed="' + (r === role) + '">' + label + '</button>';
          }).join('') +
        '</div>' +
        '<div id="err"></div>' +
        '<form id="f">' +
          '<label class="field"><span>Full name</span><input class="input" name="name" required></label>' +
          '<div class="row2">' +
            '<label class="field"><span>Phone number</span><input class="input" name="phone" required placeholder="+2609…"></label>' +
            '<label class="field"><span>Email <span class="muted">(optional)</span></span><input class="input" name="email" type="email"></label>' +
          '</div>' +
          (role === 'shipper' ? '<label class="field"><span>Company <span class="muted">(optional)</span></span><input class="input" name="company"></label>' : '') +
          (role === 'driver' ?
            '<div class="row2">' +
              '<label class="field"><span>Equipment class</span><select class="input" name="equipment_key">' + M.options(state.config.equipment, 'key', 'name') + '</select></label>' +
              '<label class="field"><span>Horse plate</span><input class="input" name="plate" required placeholder="BAK 4471"></label>' +
            '</div>' +
            '<label class="field"><span>Home base</span><select class="input" name="home_zone">' + M.options(state.config.zones, 'key', 'name') + '</select></label>' : '') +
          '<label class="field"><span>Password <span class="muted">(8+ characters)</span></span><input class="input" name="password" type="password" required minlength="8" autocomplete="new-password"></label>' +
          '<button class="btn btn-primary btn-block" type="submit">Create account</button>' +
        '</form>' +
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
        var payload = { role: role, name: f.name.value.trim(), phone: f.phone.value.trim(),
                        email: f.email.value.trim(), password: f.password.value };
        if (f.company) payload.company = f.company.value.trim();
        if (f.plate) {
          payload.equipment_key = f.equipment_key.value;
          payload.plate = f.plate.value.trim().toUpperCase();
          payload.home_zone = f.home_zone.value;
        }
        submit(f, api.register(payload));
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
      location.hash = '#/';
      route();
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
          '<fieldset><legend>The cargo</legend>' +
            '<div class="row2">' +
              '<label class="field"><span>Commodity</span><select class="input" name="commodity">' + commodityOptions + '</select></label>' +
              '<label class="field"><span>Equipment</span><select class="input" name="equipment"></select></label>' +
            '</div>' +
            '<div class="row2">' +
              '<label class="field"><span>Tonnes</span><input class="input" name="tonnes" type="number" min="0.5" step="0.5" value="30" inputmode="decimal" required></label>' +
              '<label class="field"><span>Contract type</span><select class="input" name="service">' + M.options(cfg.services, 'key', 'name') + '</select></label>' +
            '</div>' +
            '<label class="field"><span>Description for the carrier</span><input class="input" name="goods" required placeholder="Compound D fertiliser, 50 kg bags"></label>' +
          '</fieldset>' +

          '<fieldset><legend>Load at</legend>' +
            '<label class="field"><span>Location</span><select class="input" name="from_zone">' + M.options(cfg.zones, 'key', 'name') + '</select></label>' +
            '<label class="field"><span>Site address</span><input class="input" name="pickup_address" required placeholder="Nitrogen Chemicals of Zambia, Kafue"></label>' +
          '</fieldset>' +

          '<fieldset><legend>Deliver to</legend>' +
            '<label class="field"><span>Location</span><select class="input" name="to_zone">' + M.options(cfg.zones, 'key', 'name') + '</select></label>' +
            '<label class="field"><span>Site address</span><input class="input" name="dropoff_address" required placeholder="Mkushi Farm Block, central store"></label>' +
            '<div class="row2">' +
              '<label class="field"><span>Site contact</span><input class="input" name="recipient_name" required></label>' +
              '<label class="field"><span>Contact phone</span><input class="input" name="recipient_phone" required placeholder="+2609…"></label>' +
            '</div>' +
          '</fieldset>' +

          '<fieldset><legend>Cargo cover</legend>' +
            '<label class="field"><span>Declared value of the cargo (kwacha) — leave blank for no cover</span>' +
              '<input class="input" name="declared_value" type="number" min="0" step="1000" inputmode="numeric" placeholder="e.g. 850000"></label>' +
            '<div id="cover" class="muted" style="font-size:.83rem">Goods-in-transit cover, placed with a licensed insurer. Musanga arranges it; the insurer carries it.</div>' +
          '</fieldset>' +

          '<fieldset><legend>Settlement</legend>' +
            '<label class="field"><span>How is this load paid?</span><select class="input" name="payment_method">' +
              M.options(cfg.payment_methods, 'key', 'name') + '</select></label>' +
          '</fieldset>' +

          '<div id="err"></div>' +
          '<button class="btn btn-primary btn-block" type="submit">Book this load</button>' +
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
        from_zone: f.from_zone.value, to_zone: f.to_zone.value, tonnes: Number(f.tonnes.value) || 0
      }).then(function (q) {
        var lines = q.lines.filter(function (l) { return l.ngwee !== 0; }).map(function (l) {
          return '<div><span>' + esc(l.label) + '</span><span>' + esc(l.amount) + '</span></div>';
        }).join('');
        el('#quote').innerHTML =
          '<div class="summary-total"><span class="muted">' + esc(q.equipment_name) + '</span><b>' + esc(q.total) + '</b></div>' +
          '<div class="quote-meta muted" style="font-size:.8rem;display:flex;flex-wrap:wrap;gap:4px 14px">' +
            '<span>' + q.distance_km + ' km</span><span>' + q.billed_tonnes + ' t billed</span>' +
            '<span>' + esc(q.rate_per_tkm) + '/tonne-km</span><span>~' + esc(M.duration(q.eta_minutes)) + '</span>' +
          '</div>' +
          '<div class="summary-lines">' + lines +
            '<div class="total"><span>VAT 16%</span><span>' + esc(q.vat) + '</span></div></div>';
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
        declared_value: Number(f.declared_value.value) || null
      }).then(function (o) {
        location.hash = '#/orders/' + o.ref;
      }).catch(function (err) {
        el('#err').innerHTML = '<div class="notice notice-error">' + esc(err.message) + '</div>';
        btn.disabled = false;
        btn.textContent = 'Book this load';
      });
    });
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
      shell(
        pageHead('Load board', 'Open loads for your ' + (res.vehicle ? equipmentName(res.vehicle.equipment_key) : 'unit') + '.',
          '<label class="switch"><input type="checkbox" id="online"' + (online ? ' checked' : '') + '><i></i>' +
          '<span id="online-label">' + (online ? 'Available' : 'Off duty') + '</span></label>') +
        (res.jobs.length
          ? '<div class="job-grid">' + res.jobs.map(function (o) {
              return jobCard(o, '<button class="btn btn-primary btn-block" data-accept="' + esc(o.ref) + '">Accept &middot; ' + esc(o.payout) + '</button>');
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
                '<dt>Transit</dt><dd>' + esc(o.distance_km) + ' km &middot; ~' + esc(M.duration(o.eta_minutes)) + '</dd>' +
                '<dt>Site contact</dt><dd>' + esc(o.recipient_name) + ' &middot; ' + esc(o.recipient_phone) + '</dd>' +
                '<dt>Carrier</dt><dd>' + (o.driver ? esc(o.driver.name) + ' &middot; ' + esc(o.driver.phone) : '<span class="muted">Not yet assigned</span>') + '</dd>' +
                '<dt>Settlement</dt><dd>' + esc(o.payment_label) + ' &middot; ' + esc(o.payment_status) + '</dd>' +
                (role === 'driver' ? '<dt>Your payout</dt><dd>' + esc(o.payout) + '</dd>'
                                   : '<dt>Total</dt><dd>' + esc(o.total) + '</dd>') +
                (o.cover ? '<dt>Cargo cover</dt><dd>' + esc(o.cover.declared_value) + ' declared &middot; premium ' + esc(o.cover.premium) + ' <span class="muted">(' + esc(o.cover.rate_pct) + '%)</span></dd>' : '') +
                (o.settlement ? '<dt>Settled</dt><dd>' + esc(o.settlement.net) + (o.settlement.fuel_deduction_ngwee ? ' <span class="muted">after ' + esc(o.settlement.fuel_deduction) + ' fuel</span>' : '') + '</dd>' : '') +
                (o.proof_note ? '<dt>Proof</dt><dd>' + esc(o.proof_note) + '</dd>' : '') +
              '</dl>' +
              (actions ? '<div id="err" style="margin-top:20px"></div>' + actions : '') +
            '</div>' +
            fuelPanel(o, role) +
          '</div>' +
          '<div class="panel"><h3>Timeline</h3><ul class="timeline">' + timeline + '</ul></div>' +
        '</div>'
      );

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
              '<label class="field"><span>Site</span><select class="input" name="site">' + M.options(cfg.zones, 'key', 'name') + '</select></label>' +
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
    root.innerHTML = '<div class="auth-wrap"><div class="auth-card">' +
      '<div class="notice notice-error">' + esc(err.message) + '</div>' +
      '<a class="btn btn-ghost btn-block" href="#/">Back</a></div></div>';
  }

  var ROUTES = {
    shipper: { '': viewShipperHome, 'orders': viewShipperOrders, 'book': viewBook,
               'hire': viewHireBook, 'hires': viewHires },
    driver:  { '': viewDriverBoard, 'my': viewDriverJobs, 'fuel': viewFuel,
               'earnings': viewEarnings },
    ops:     { '': viewOpsDispatch, 'orders': viewOpsOrders, 'drivers': viewOpsDrivers,
               'book': viewBook, 'hire': viewHireBook, 'hires': viewHires }
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
