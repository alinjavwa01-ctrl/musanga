# Musanga

**Move it. Or rent it.**

Heavy freight and plant hire for Zambian mining, agriculture and fuel. Ten
years on from the 2016 original, rebuilt as one platform that rates, dispatches
and tracks both sides.

Runs on Python 3's standard library and hand-written HTML/CSS/JS. No package
manager, no build step, no external services.

```bash
./run.sh
```

Then open <http://localhost:8000>.

| Surface | Path | What it is |
| --- | --- | --- |
| Marketing site | `/` | Positioning, the plant catalogue, and a live two-mode rate widget |
| Platform | `/app` | Shipper, carrier and control consoles behind one sign-in |
| Public tracking | `/track` | Reference lookup for loads and hires, no account needed |
| JSON API | `/api/*` | Everything the front end uses |

## Demo accounts

Password for all of them: `musanga2026`

| Role | Phone | Who |
| --- | --- | --- |
| Shipper | `+260971000001` | Kansanshi Mining |
| Shipper | `+260971000002` | Nitrogen Chemicals of Zambia |
| Carrier | `+260972000001` | Emmanuel Kwenda, 34t side tipper |
| Carrier | `+260972000007` | Kalubwa Karabassis, 40,000L tanker |
| Control | `+260970000001` | Musanga operations |

`python3 seed.py` resets the database to a fixed set of demo loads and hires at
every stage of their pipelines.

## How it is put together

```
server.py          stdlib HTTP server: static files from web/ plus the API
seed.py            deterministic demo data
tests.py           end-to-end API tests against a running server
musanga/
  geo.py           nodes and measured road distances on Zambia's corridors
  pricing.py       the freight rate engine
  rental.py        the plant hire rate engine
  api.py           JSON endpoints, auth, and both lifecycles
  db.py            SQLite schema, password hashing, references
web/
  index.html       marketing site
  app.html         platform shell (hash-routed SPA)
  track.html       public tracking
  img/*.svg        full-bleed artwork (swap for photography, see below)
  css/brand.css    design tokens - the black-and-white system
  css/landing.css  marketing site
  css/app.css      platform
  js/api.js        API client and shared helpers
  js/landing.js    both rate widgets, plant catalogue, corridor table
  js/app.js        the platform: routing and all three consoles
  js/track.js      public tracking
```

### The freight rate engine

Heavy haulage is quoted per tonne-kilometre, not per trip:

```
freight = billed_tonnes x km x rate_per_tkm x commodity_factor
        + mobilisation + border clearance + permits
        + contract adjustment - backhaul credit
```

The details that matter:

- **Minimum billable tonnage.** A trip bills at least 60% of the unit's
  payload, so an operator is never asked to run 600 km on eight tonnes.
- **Commodity decides equipment.** Sulphuric acid can only be quoted on an
  ADR tanker; concentrate only on tippers. The API rejects an impossible
  pairing, and dispatch refuses to assign a carrier whose unit cannot carry
  the load.
- **Corridor costs are explicit.** Border clearance, hazardous-goods permits
  and abnormal-load escorts are separate line items, not margin.
- **Backhaul credit.** A leg ending at a loading hub can be refilled, so it is
  discounted rather than priced as a one-way trip.
- **Long-haul taper.** Beyond 400 km the per-tonne-km rate drops, because
  mobilisation is amortised over more distance.

### The plant hire rate engine

Hire is priced on duration, not distance:

```
hire = cheapest_of(day_rate x days, week_tiers, month_tiers)
     + float from nearest depot, both legs
     + operator + fuel + damage waiver
```

- **The cheaper tier always wins.** A nine-day hire is quoted as one week plus
  two days, or two whole weeks, whichever is less. Hiring for longer is never
  more expensive than hiring for less.
- **Float is priced in.** Every quote includes moving the machine out from the
  nearest of the Lusaka, Ndola and Solwezi depots and collecting it after.
  Heavier plant floats on a lowbed, lighter plant on a flatbed.
- **Wet or dry.** Take our operator or run it yourself. Unmanned units like
  generators never bill a crew, whatever the request asks for.

Money is stored as integer ngwee (1 ZMW = 100 ngwee) end to end. Only the
view layer divides by 100.

### The load lifecycle

```
booked -> carrier assigned -> at load-out -> in transit -> delivered
   \                \               \
    ----------------- cancelled -----
```

Transitions are validated server-side against an explicit table, so a load
cannot skip load-out or move backwards. Shippers may only cancel; carriers
move their own loads forward; control can do both.

### The hire lifecycle

```
requested -> confirmed -> on site -> off hire -> returned
     \            \
      ---- cancelled ----
```

Control confirms, delivers and closes. The customer can end a hire early
(`off hire`) or cancel before the machine ships, and nothing else.

## Swapping in your own photography

The four full-bleed bands ship with black-and-white artwork so the site looks
finished out of the box. Each one is a single file:

| File | Where it appears |
| --- | --- |
| `web/img/fleet.jpg` | Under the hero — a real fleet photograph |
| `web/img/pit.svg` | Above plant hire |
| `web/img/terminal.svg` | Above the shipper/carrier split |
| `web/img/farm.svg` | The closing band |

`web/img/corridor.svg` is the artwork the fleet photograph replaced; it is kept
as a spare if you want to go back to a drawn band.

To use a real photograph, drop it in `web/img/` and point the `src` at it:

```html
<img class="bleed-media" src="/img/corridor.jpg" alt="…">
```

Add `bleed-photo` to the band's class list when the source is a photograph
rather than artwork — it uses a taller crop, anchors above centre so a yard
shot keeps its vehicles in frame, and adds back the contrast that grayscale
takes out:

```html
<div class="bleed bleed-photo bleed-overlay">
```

`.bleed-media` handles the rest: the crop (`object-fit: cover`), the responsive
height, and the grayscale treatment that keeps a colour photograph inside the
black-and-white system. The overlay scrim sits above the image, so a light
photograph still carries a readable headline.

Landscape frames crop best — the wider the better. If a photograph carries
another company's livery or wordmark, grayscale will not hide it; check what is
actually legible in the frame before publishing.

## Tests

Start the server, then:

```bash
python3 tests.py 8000
```

Covers both rate engines' guard rails, authentication, role authorisation,
cross-tenant isolation, the full carrier flow, the full hire lifecycle,
dispatch matching, public tracking, and routing. 67 checks.

## Deploying

The app is containerised and needs no build step. `Dockerfile` and `fly.toml`
are ready; nothing has been pushed anywhere yet.

Environment:

| Variable | Default | Notes |
| --- | --- | --- |
| `MUSANGA_ENV` | `development` | `production` turns on long asset caching |
| `MUSANGA_DB` | `./musanga.db` | Put this on a persistent volume |
| `MUSANGA_SEED` | unset | `demo` loads demo data on an empty database |
| `HOST` / `PORT` | `127.0.0.1` / `8000` | `0.0.0.0` in a container |

`boot.py` runs before the server: it creates the schema if the database is
missing and leaves an existing one alone. It seeds demo data **only** when
`MUSANGA_SEED=demo`, because every demo account shares the password printed
above. Leave it unset for anything real and register the first account through
the sign-up form.

To deploy on Fly:

```bash
fly launch --no-deploy && fly volumes create musanga_data --size 1 && fly deploy
```

Before pointing a real domain at this, read the list below — `http.server` is
a development server, and sessions never expire.

## What is stubbed

Honest list of what a production deployment still needs:

- **Payments.** `payment_method` is recorded and settlement flips on delivery,
  but no collection actually happens. Zambia's options are Airtel Money, MTN
  MoMo and Zamtel Kwacha, reachable directly or through an aggregator
  (DPO, Flutterwave, Techpay).
- **Positions.** Tracking is a status timeline, not GPS. Real telematics means
  a device feed per unit and a `positions` table.
- **Hire fleet.** Plant is a catalogue with rates, not individual assets. Real
  hire needs a unit register with serial numbers, service intervals and
  availability, so a booking reserves a specific machine.
- **Routing.** Distances are measured for the corridors we run and estimated
  from great-circle elsewhere. A routing provider would replace `geo.route_km`
  and nothing else.
- **Sessions.** Tokens are opaque and stored in SQLite with no expiry.
- **Serving.** `http.server` is a development server. Production wants a real
  WSGI/ASGI stack, TLS, and Postgres in place of SQLite.
