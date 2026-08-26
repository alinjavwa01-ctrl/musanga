/* Shared API client + small DOM helpers. Loaded by every page. */
(function (global) {
  'use strict';

  var TOKEN_KEY = 'musanga.token';

  function token() { return localStorage.getItem(TOKEN_KEY); }
  function setToken(t) {
    if (t) localStorage.setItem(TOKEN_KEY, t);
    else localStorage.removeItem(TOKEN_KEY);
  }

  function request(method, path, body) {
    var opts = { method: method, headers: {} };
    if (body !== undefined) {
      opts.headers['Content-Type'] = 'application/json';
      opts.body = JSON.stringify(body);
    }
    var t = token();
    if (t) opts.headers['Authorization'] = 'Bearer ' + t;

    return fetch(path, opts).then(function (res) {
      return res.json().catch(function () { return {}; }).then(function (data) {
        if (!res.ok) {
          var err = new Error(data.error || ('Request failed (' + res.status + ')'));
          err.status = res.status;
          throw err;
        }
        return data;
      });
    });
  }

  var api = {
    token: token,
    setToken: setToken,
    get: function (p) { return request('GET', p); },
    post: function (p, b) { return request('POST', p, b || {}); },

    config: function () { return request('GET', '/api/config'); },
    quote: function (b) { return request('POST', '/api/quote', b); },
    distance: function (b) { return request('POST', '/api/distance', b); },
    login: function (b) { return request('POST', '/api/auth/login', b); },
    register: function (b) { return request('POST', '/api/auth/register', b); },
    logout: function () { return request('POST', '/api/auth/logout', {}); },
    me: function () { return request('GET', '/api/me'); },
    orders: function () { return request('GET', '/api/orders'); },
    order: function (ref) { return request('GET', '/api/orders/' + ref); },
    createOrder: function (b) { return request('POST', '/api/orders', b); },
    setStatus: function (ref, b) { return request('POST', '/api/orders/' + ref + '/status', b); },
    track: function (ref) { return request('GET', '/api/track/' + encodeURIComponent(ref)); },
    jobs: function () { return request('GET', '/api/jobs'); },
    accept: function (ref) { return request('POST', '/api/jobs/' + ref + '/accept', {}); },
    assign: function (ref, id) { return request('POST', '/api/orders/' + ref + '/assign', { driver_id: id }); },
    drivers: function () { return request('GET', '/api/ops/drivers'); },
    summary: function () { return request('GET', '/api/ops/summary'); },
    earnings: function () { return request('GET', '/api/driver/earnings'); },
    setOnline: function (on) { return request('POST', '/api/driver/online', { online: !!on }); },
    setVehicle: function (b) { return request('POST', '/api/driver/vehicle', b); },

    fileDocument: function (ref, b) { return request('POST', '/api/orders/' + ref + '/documents', b); },
    ping: function (ref, b) { return request('POST', '/api/orders/' + ref + '/position', b); },
    weigh: function (ref, b) { return request('POST', '/api/orders/' + ref + '/weights', b); },
    completeStop: function (ref, seq, b) { return request('POST', '/api/orders/' + ref + '/stops/' + seq + '/done', b || {}); },
    contracts: function () { return request('GET', '/api/contracts'); },
    createContract: function (b) { return request('POST', '/api/contracts', b); },

    fuel: function () { return request('GET', '/api/fuel'); },
    fuelDraw: function (ref, b) { return request('POST', '/api/fuel/' + ref + '/draw', b); },
    settlements: function () { return request('GET', '/api/settlements'); },
    coverQuote: function (b) { return request('POST', '/api/insurance/quote', b); },

    hireQuote: function (b) { return request('POST', '/api/hire/quote', b); },
    hires: function () { return request('GET', '/api/hires'); },
    hire: function (ref) { return request('GET', '/api/hires/' + ref); },
    createHire: function (b) { return request('POST', '/api/hires', b); },
    setHireStatus: function (ref, b) { return request('POST', '/api/hires/' + ref + '/status', b); }
  };

  /* --- DOM helpers ------------------------------------------------------ */
  function el(sel, root) { return (root || document).querySelector(sel); }
  function els(sel, root) { return Array.prototype.slice.call((root || document).querySelectorAll(sel)); }

  // Everything user-supplied goes through this before touching innerHTML.
  function esc(v) {
    return String(v === null || v === undefined ? '' : v)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
  }

  function options(list, valueKey, labelKey) {
    return list.map(function (item) {
      return '<option value="' + esc(item[valueKey]) + '">' + esc(item[labelKey]) + '</option>';
    }).join('');
  }

  function kwacha(ngwee) {
    return 'K' + (ngwee / 100).toLocaleString('en-ZM', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  }

  function ago(unixSeconds) {
    var mins = Math.max(0, Math.round((Date.now() / 1000 - unixSeconds) / 60));
    if (mins < 1) return 'just now';
    if (mins < 60) return mins + ' min ago';
    var hrs = Math.round(mins / 60);
    if (hrs < 24) return hrs + (hrs === 1 ? ' hour ago' : ' hours ago');
    var days = Math.round(hrs / 24);
    return days + (days === 1 ? ' day ago' : ' days ago');
  }

  function when(unixSeconds) {
    return new Date(unixSeconds * 1000).toLocaleString('en-ZM', {
      day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit'
    });
  }

  function duration(minutes) {
    if (minutes < 60) return minutes + ' min';
    var h = Math.floor(minutes / 60), m = minutes % 60;
    return h + 'h' + (m ? ' ' + m + 'm' : '');
  }

  // Fire fn at most once per `wait` ms of quiet - used by the live quote.
  function debounce(fn, wait) {
    var timer;
    return function () {
      var args = arguments, self = this;
      clearTimeout(timer);
      timer = setTimeout(function () { fn.apply(self, args); }, wait);
    };
  }

  global.M = {
    api: api, el: el, els: els, esc: esc, options: options,
    kwacha: kwacha, ago: ago, when: when, duration: duration, debounce: debounce
  };
})(window);
