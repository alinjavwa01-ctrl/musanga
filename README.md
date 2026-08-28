# Musanga

**Move it. Or rent it.**

Bulk freight and plant hire for mining and agriculture across Southern and
Central Africa. Ten years on from the 2016 original, rebuilt as one platform
that rates, papers, dispatches and tracks a load from a Zambian farm block to a
Zimbabwean mill or a Congolese mine gate.

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
| Signing room | `/sign/<token>` | A contract, signed by link, with no account at all |
| JSON API | `/api/*` | Everything the front end uses |

## Demo accounts

Password for all of them: `musanga2026`

| Role | Phone | Who |
| --- | --- | --- |
| Shipper | `+260971000001` | Kansanshi Mining |
| Shipper | `+260971000002` | Nitrogen Chemicals of Zambia |
| Carrier | `+260972000001` | Emmanuel Kwenda, 34t side tipper |
| Carrier | `+260972000007` | Kalubwa Karabassis, 40,000L tanker |
| Carrier | `+260972000010` | Gift Mulenga, 34t bulk grain tipper |
| Carrier | `+260972000011` | Chola Bwalya - verification still in review |
| Control | `+260970000001` | Musanga operations |

`python3 seed.py` resets the database to a fixed set of demo loads and hires at
every stage of their pipelines.

## How it is put together

```
server.py          stdlib HTTP server: static files from web/ plus the API
seed.py            deterministic demo data
tests.py           end-to-end API tests against a running server
tests_kyc.py       signup, limited mode and the verification queue
tests_agreements.py  contract drafting, signing by link, the network console
stamp.py           stamps asset URLs with a content hash for cache busting
boot.py            first-boot database setup for a deployment
musanga/
  geo.py           the regional network: nodes, road distances, borders, routing
  docs.py          the document checklist each lane and cargo requires
  kyc.py           what an account must prove before it can trade
  agreements.py    contract templates, and what a signature has to carry
  pricing.py       the freight rate engine
  rental.py        the plant hire rate engine
  api.py           JSON endpoints, auth, and both lifecycles
  db.py            SQLite schema, password hashing, references
brand/
  fleet.py         generates the flat-vector truck artwork, light and dark
web/
  index.html       marketing site
  app.html         platform shell (hash-routed SPA)
  track.html       public tracking
  sign.html        the signing room: one document, one signature, no account
  img/*.svg        full-bleed artwork (swap for photography, see below)
  css/brand.css    design tokens - the black-and-white system
  css/landing.css  marketing site
  css/app.css      platform
  js/api.js        API client and shared helpers
  js/landing.js    both rate widgets, plant catalogue, corridor table, network map
  js/app.js        the platform: routing and all three consoles
  js/track.js      public tracking
  js/sign.js       the signing room
  img/fleet/       generated truck artwork - do not edit by hand
```

### The freight rate engine

A rate per tonne-kilometre is what the market quotes, but it is an output, not
an input. The engine costs the trip first and derives the rate from it:

```
cost  = fuel + tyres + maintenance + driver + standing cost + tolls
      + border clearance, bonds and levies + cargo handling
      + the empty leg back
price = cost / (1 - margin), floored at a minimum viable trip
rate  = price / (billed tonnes x km)
```

That ordering is what lets one code path hold a rate on a 2,900 km Kalumbila
to Durban lane and a 55 km Lusaka to Chisamba run, and explain either of them
line by line to a shipper who wants to argue about it.

The details that matter:

- **Cost is country by country.** Diesel is indexed per country and tolls are
  charged per country-kilometre, so the Zimbabwean third of a Durban run is
  costed at Zimbabwean toll rates. The split is apportioned across the routed
  path, not guessed.
- **The empty leg is priced in.** A truck discharging at a mine gate has a
  25% chance of a backload; one discharging at a hub has an 80% chance. The
  expected empty kilometres are part of the cost, because somebody pays for
  them either way.
- **Borders are named, not averaged.** Kasumbalesa costs more and takes 48
  hours; Mwami costs less and takes 14. Clearing, bond and levies are separate
  line items per post.
- **Time is days, not hours.** A driver cannot drive around the clock, so a
  long lane costs whole days of wage, subsistence and standing cost. Border
  queue hours are part of that.
- **Minimum billable tonnage.** A trip bills at least 60% of the unit's
  payload, so an operator is never asked to run 600 km on eight tonnes.
- **Commodity decides equipment.** Sulphuric acid can only be quoted on an
  ADR tanker; grain in bulk only on a food-grade unit. The API rejects an
  impossible pairing, and dispatch refuses to assign a carrier whose unit
  cannot carry the load.
- **Exports are zero-rated and quoted in dollars.** A cross-border lane
  carries no Zambian VAT and is presented in USD, because that is what the
  counterparty contracts in. It is still computed and stored in ngwee.

### The network

Zambia is landlocked at the junction of five corridors, so the network does
not stop at the border. `geo.py` holds 65 nodes across ten countries with
their real coordinates, and the measured road distances between them.

Anything not measured end to end is routed: a Dijkstra pass over the measured
lanes gives the honest road distance and, as a side effect, the exact border
posts a load will pass through. Mkushi to Harare is 777 km through Chirundu
because that is the road, not because a straight line was multiplied by a
fudge factor.

```
North-South   Durban - Johannesburg - Beitbridge - Harare - Chirundu
              - Lusaka - Copperbelt - Kasumbalesa - Lubumbashi
Dar es Salaam Dar - Mbeya - Tunduma/Nakonde - Kapiri Mposhi - Lusaka
Beira         Beira - Machipanda - Mutare - Harare - Chirundu - Lusaka
Nacala        Nacala - Blantyre - Lilongwe - Mchinji/Mwami - Chipata
Walvis Bay    Walvis Bay - Windhoek - Katima Mulilo - Livingstone - Lusaka
```

### Documents

A truck is not stopped at Chirundu because nobody phoned ahead. It is stopped
because the export permit is in someone's inbox in Lusaka.

So documents are part of the load, not an attachment to it. `docs.py` derives
a checklist from the lane and the cargo - a domestic fertiliser run needs 8
documents, a maize export to Zimbabwe needs 23 - and each item is owned by
somebody and due at a stage. The lifecycle is gated on it:

| To reach | Everything must be filed up to |
| --- | --- |
| Carrier assigned | Before dispatch |
| In transit | Before the border |
| Delivered | On delivery |

The truck is stopped in the yard, where the paperwork is cheap to fix, rather
than at the post, where it is not.

### Weights

Grain and concentrate are sold on weight, and the gap between the loading
weighbridge and the discharge weighbridge is the number both sides argue
about. Both are recorded against the load, the variance is computed against
the contract tolerance, and a short delivery is flagged before settlement
rather than discovered after it. Weighed cargo cannot be closed without a
discharge figure.

### Multi-drop

Fertiliser out of a plant is one truck and several agro-dealers. A load is a
sequence of drops, the last of which is the destination, so a single delivery
and a five-drop run are the same shape. Each drop carries its own tonnage,
signature and weighbridge ticket, and the load cannot close while one is
unsigned.

### Contracts

A contract rate is not a discount, it is committed tonnage at an agreed rate
over a period, drawn down load by load. The rate is the platform's own rate
for the lane at contract terms, so nobody is quoted one number and billed
another, and "how much of this month's allocation is left" is a query.

### Tracking

Regional lanes run for days through places where a telematics feed is not a
given, so a position is whatever the platform can get: a coordinate from the
driver's phone, or a named point on the corridor - which is what a phone call
from Nakonde with no signal gives you. Both produce the same thing: distance
covered, distance left along the road, and an ETA that moves. A raw coordinate
snaps to the nearest node.

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

## Signing up, and verification

Signing up asks for four things: a name, a phone number, a password, and which
side of the network you are on. Nothing else. No company registration, no tax
number, no documents. The account exists from that screen and can rate loads,
look at the board and move around the console immediately.

What it cannot do is commit anything. An unverified account is in **limited
mode**: no loads booked, no machines hired, no jobs accepted, no fuel drawn, no
invoice terms. Those open when the account's file clears, and the block is
stated on every screen rather than sprung at the moment somebody tries to book.

Verification happens inside the app, at `#/verify`, in four steps:

1. **The business.** Entity type first - limited company, sole trader,
   partnership, cooperative or individual - because it decides everything that
   follows. Then the legal name, PACRA registration, TPIN, VAT status and
   registered address.
2. **The people.** Directors and anyone holding 25% or more, each with an NRC
   or passport number, and one of them marked as the control person.
3. **The documents.** A checklist generated from the role and entity type:
   certificate of incorporation, PACRA printout, TPIN and tax clearance, VAT
   certificate where registered, director IDs, proof of address, and a bank
   letter. A carrier gets the operator file on top - RTSA licence,
   goods-in-transit and motor cover, fleet list, cross-border permit. Each item
   takes a PDF or a photograph, up to 4 MB, or a reference number to verify
   against.
4. **Submit.** The file locks while compliance has it.

Control works the queue at `#/kyc`. A file is either verified, or sent back
with a note and the specific documents marked as rejected - which puts it back
in the applicant's hands with the reasons attached, rather than a silent
failure.

`musanga/kyc.py` holds all of it: which fields each entity type needs, which
documents each role files, what still blocks a submission, and which actions a
given account state may take. The rest of the platform asks that module two
questions and nothing else.

## Agreements, signed by link

Freight customers do not want an account in order to sign a contract, and
making them have one is how contracts end up unsigned. So agreements work the
way the customer already expects: a link, a document, a signature, a copy.

Control drafts from a template at `#/agreements/new` - master transport
services agreement, carrier services agreement, per-shipment agreement, rate
schedule, plant hire agreement, or a mutual NDA. A shipment agreement fills
itself in from the booking reference: lane, commodity, tonnage, rate and
all-in price come straight off the load.

Sending freezes the text and hashes it. The counterparty opens
`/sign/<token>`, reads the document, types or draws a signature, ticks the
consent, and signs. They get a copy - the document, the signature block and a
certificate of completion, as one self-contained HTML file that opens and
prints anywhere. Musanga countersigns on receipt.

What makes a signature defensible is not the picture of it, so every touch on
the document is written to `agreement_events` and never updated: drafted, sent,
opened (with the address it was opened from), signed, countersigned,
downloaded. The certificate prints that trail against the SHA-256 of the exact
text that was signed.

Signing with the email an account registered under links the signed copy to
that account, so it also appears in the customer's own console under
Agreements.

## The network console

Control has one place that answers "who is this company, are they cleared, what
have they signed, and what are they running right now": `#/network`. Every
shipper and carrier, their verification state, live and lifetime volume, value,
and how much paper is out for signature. Opening one gives the whole
counterparty - the KYC file, every agreement, recent loads, the fuel facility
and settlements for a carrier, contracts and hires for a shipper - and the
controls to verify the file or suspend the account. A suspended account can
still sign in and read; it cannot book, accept or draw.

## The fleet artwork

`brand/fleet.py` generates the flat-vector fleet: four trailers - side tipper,
fuel tanker, tarped flat deck, box trailer - in strict orthographic side
profile, travelling left to right, built from a handful of geometric shapes and
nothing else. Solid fills, no gradients, no outlines, no shadows, no
perspective. Black, white and the nine greys, with no accent colour: depth
comes from grey values and shape overlap, and the truck stays the darkest thing
in frame in light mode and the lightest in dark.

It is a generator rather than a drawing file because every asset ships in a
light and a dark version with identical geometry. Written twice, they drift;
written once with the palette as a parameter, they cannot.

```bash
python3 brand/fleet.py
```

Two kinds of file come out, all of them well under the 100 KB ceiling:

| File | What it is |
| --- | --- |
| `web/img/fleet/<truck>-light.svg`, `-dark.svg` | The truck alone, layers named and grouped, no animation, for animating in CSS elsewhere |
| `web/img/fleet/scene-<truck>.svg` | The truck on the corridor, animating itself, both value schemes in one file |

The scenes are self-contained - their CSS lives inside the SVG - so they run
inside an `<img>` with no script and no external stylesheet. The truck holds
station and the world moves past it in four parallax layers: ridgeline,
industrial silhouette, hill mass, treeline, each at its own speed, with the
wheels rotating and a 1.1px suspension bounce on the body. `prefers-reduced-motion`
stops all of it.

One deviation from the brief, deliberately: the panning layers run at linear
speed rather than eased. A seamless loop that eases in and out reads as the
ground stuttering twice a cycle. The easing is on the suspension, where it
belongs.

## Swapping in your own photography

The four full-bleed bands ship with black-and-white artwork so the site looks
finished out of the box. Each one is a single file:

| File | Where it appears |
| --- | --- |
| `web/img/musanga-tippers.jpg` | Under the hero — Musanga Tippers on the bench (**you must add this file**) |
| `web/img/pit.svg` | Above plant hire |
| `web/img/terminal.svg` | Above the shipper/carrier split |
| `web/img/farm.svg` | The closing band |

`web/img/corridor.svg` opens the hero. `web/img/fleet.jpg` is **not in use**: it
carries another operator's livery ("moove" is legible on the cab), which is
exactly the trap described below. Replace it with your own photography or delete
it.

Bands marked `bleed-colour` keep their colour rather than being desaturated —
use it for photographs of Musanga's own orange livery, which is the one thing on
the page a competitor cannot copy. Everything else stays in the black-and-white
system.

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

## The carrier bundle

Musanga does not advance cash. The carrier's binding constraint is diesel, not
money, so the platform extends fuel against a load it has already assigned and
nets the balance off the settlement it is already holding. Nothing leaves the
business that is not already covered by work done.

```
assign load -> issue entitlement -> draws at the pump -> deliver -> net off settlement
```

**Entitlement is per load, not per truck.** We know the corridor distance and the
equipment class, so a 183 km round trip in a 34t side tipper is 180 litres and
not 300. A generic fuel card cannot do this because it does not know what the
truck is carrying. This is the fraud control.

**The limit is sized to earnings on this platform.** A carrier with no history
gets one trip's diesel. Above three completed loads the limit tracks half an
average week's payout, capped at K50,000 so no single carrier is material. It is
never cut below money already drawn - that would strand a truck mid-trip for a
debt we approved.

**Netting takes the balance or half the load's gross, whichever is less.** Half,
not all: take the whole settlement and the carrier cannot afford to run the next
load, which ends the relationship and the debt.

Goods-in-transit cover is placed as an agent - the premium belongs to the
insurer, only the commission is platform revenue. The rates in
`musanga/insurance.py` are placeholders in the shape of the real thing and must
be replaced with a licensed insurer's schedule before anything is sold.

Both products live in the platform itself, not only in the API. A carrier signs
in and finds **Fuel & cover**: what is available to draw, what is outstanding
against the limit, the litres issued to each live load with a draw button at the
pump, and every settlement with the diesel shown netted off. The same draw sits
on the load's own page. Earnings lead with what actually reached the carrier
after fuel, with the gross beside it.

Cover is priced on the booking form: a shipper enters the declared value and
sees the premium before committing, and the policy is written against the load
when it is booked - `quoted`, because nothing here binds an insurer.

| Endpoint | What it does |
| --- | --- |
| `GET /api/fuel` | The carrier's facility and every open entitlement |
| `POST /api/fuel/<ref>/draw` | Draw diesel against one load |
| `GET /api/settlements` | What was earned, netted and paid |
| `POST /api/insurance/quote` | Price goods-in-transit cover |

Diesel is priced at `fuel.DIESEL_NGWEE_PER_LITRE`, the ERB pump ceiling. The ERB
reviews it monthly; update it when they publish. SI 77 of 2024 makes it a
ceiling, so a negotiated bulk price sits at or below it and the spread is the
revenue - see `fuel.margin()`.

## Supabase

`supabase/migrations/0001_core.sql` is the Postgres schema: a port of the SQLite
tables plus the carrier bundle. `musanga/store.py` talks to it over PostgREST
using `urllib`, so there is still no package manager and no build step.

```bash
export SUPABASE_URL=https://<project>.supabase.co
export SUPABASE_SERVICE_KEY=<service_role key>
```

Apply the migration by pasting the file into the Supabase SQL editor (the
Supabase CLI needs a toolchain this project deliberately does not have).

Two decisions worth knowing:

- **Policy lives in Python, invariants live in Postgres.** `musanga/fuel.py`
  decides how many litres a load gets and how much of a settlement may be
  netted; the constraints in the migration guarantee no path can breach the
  limit or overdraw an entitlement. The rules are not duplicated into plpgsql,
  because two copies drift.
- **RLS is on with no permissive policy.** Authentication is still Musanga's own
  (phone, password, `sessions`), not Supabase Auth, so there is no `auth.uid()`
  to write policies against. The backend uses the service role; anon and
  authenticated roles can read nothing, so a leaked anon key opens nothing. When
  auth moves to Supabase Auth, add per-role policies and stop there.

## Tests

Start the server, then:

```bash
python3 tests.py 8000
```

```bash
python3 tests_credit.py 8000       # fuel facility, settlement netting, cover
python3 tests_kyc.py 8000          # signup, limited mode, the KYC queue
python3 tests_agreements.py 8000   # drafting, signing by link, the network console
```

Between them: both rate engines' guard rails, authentication, role
authorisation, cross-tenant isolation, the full carrier flow, the full hire
lifecycle, dispatch matching, public tracking, routing, the carrier credit
bundle, onboarding and verification, and the whole signing flow including the
audit trail, expiry, voiding and declining. 253 checks.

## Deploying

The app is containerised and needs no build step. `Dockerfile` and `fly.toml`
are ready. Pushing `main` is the deploy: GitHub Actions runs the four suites and
the asset-stamp check, and Vercel builds from the same commit.

Environment:

| Variable | Default | Notes |
| --- | --- | --- |
| `MUSANGA_ENV` | `development` | `production` turns on long asset caching |
| `MUSANGA_DB` | `./musanga.db` | Put this on a persistent volume |
| `MUSANGA_SEED` | unset | `demo` loads demo data on an empty database |
| `HOST` / `PORT` | `127.0.0.1` / `8000` | `0.0.0.0` in a container |

`boot.py` runs before the server. It creates the schema if the database is
missing, and on every boot after that it brings an existing database up to what
the release expects - adding any missing table or column and reporting what it
changed. Existing rows are never touched. It seeds demo data **only** when there
was no database at all and `MUSANGA_SEED=demo` is set, because every demo
account shares the password printed above. Leave it unset for anything real and
register the first account through the sign-up form.

To deploy on Vercel, import the repository at <https://vercel.com/new>. No CLI
step is needed - `vercel.json` routes `web/` as static files and `/api/*` to
`api/index.py`.

**Vercel is a showcase deployment, not a durable one.** Serverless functions get
a read-only filesystem, so the database lives in `/tmp`: it is seeded with demo
data on cold start, is not shared between instances, and is wiped when one
recycles. Quotes, the catalogue and tracking of seeded references are exact;
sign-ups, bookings and status changes will not survive. For anything durable use
Fly, where the database sits on a volume.

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
- **Sending the paper.** An agreement produces a signing link; nothing emails or
  SMSes it yet. Control copies the link out of the console. Wiring it to an
  email provider is one function.
- **KYC files.** Uploads are base64 in a SQLite column, capped at 4 MB. That is
  fine for a few hundred accounts and wrong for a few thousand: the Supabase
  schema already carries a `storage_key` column for moving them to object
  storage.
- **Screening.** Verification is a document check by a person. It does not
  screen against sanctions or PEP lists, which a bank-facing deployment would
  need.
- **Serving.** `http.server` is a development server. Production wants a real
  WSGI/ASGI stack, TLS, and Postgres in place of SQLite.
