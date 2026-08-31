"""Storage. SQLite by default, Postgres when the environment points at one.

No ORM and no migration tool: the schema below is the single source of truth,
`init()` is idempotent so it doubles as the migration, and
`supabase/generate_schema.py` translates this same schema into the Postgres one
so the two cannot drift.

Which database is in use is decided by one environment variable. Set
DATABASE_URL (or SUPABASE_DB_URL) to a Postgres URL and every connection goes
there; leave it unset and the platform runs on a local file with nothing to
install. `connect()` returns the same interface either way, so nothing above
this module knows the difference."""

import hashlib
import os
import secrets
import sqlite3
import time

DB_PATH = os.environ.get("MUSANGA_DB", os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "musanga.db"))
SQLITE_TIMEOUT_SECONDS = 10

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  role          TEXT NOT NULL CHECK (role IN ('shipper','driver','ops')),
  name          TEXT NOT NULL,
  phone         TEXT NOT NULL UNIQUE,
  email         TEXT,
  company       TEXT,
  password_hash TEXT NOT NULL,
  created_at    INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS sessions (
  token      TEXT PRIMARY KEY,
  user_id    INTEGER NOT NULL REFERENCES users(id),
  created_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS vehicles (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  driver_id   INTEGER NOT NULL REFERENCES users(id),
  equipment_key TEXT NOT NULL,
  plate       TEXT NOT NULL,
  home_zone   TEXT NOT NULL,
  is_online   INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS orders (
  id                   INTEGER PRIMARY KEY AUTOINCREMENT,
  ref                  TEXT NOT NULL UNIQUE,
  shipper_id           INTEGER NOT NULL REFERENCES users(id),
  driver_id            INTEGER REFERENCES users(id),
  equipment_key        TEXT NOT NULL,
  service_key          TEXT NOT NULL,
  commodity_key        TEXT NOT NULL DEFAULT 'general',
  from_zone            TEXT NOT NULL,
  to_zone              TEXT NOT NULL,
  pickup_address       TEXT NOT NULL,
  dropoff_address      TEXT NOT NULL,
  recipient_name       TEXT NOT NULL,
  recipient_phone      TEXT NOT NULL,
  goods                TEXT NOT NULL,
  tonnes               REAL NOT NULL DEFAULT 0,
  billed_tonnes        REAL NOT NULL DEFAULT 0,
  distance_km          REAL NOT NULL,
  eta_minutes          INTEGER NOT NULL,
  total_ngwee          INTEGER NOT NULL,
  payout_ngwee         INTEGER NOT NULL,
  payment_method       TEXT NOT NULL,
  payment_status       TEXT NOT NULL DEFAULT 'pending',
  status               TEXT NOT NULL DEFAULT 'placed',
  scheduled_for        INTEGER,
  proof_note           TEXT,
  created_at           INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS hires (
  id               INTEGER PRIMARY KEY AUTOINCREMENT,
  ref              TEXT NOT NULL UNIQUE,
  hirer_id         INTEGER NOT NULL REFERENCES users(id),
  plant_key        TEXT NOT NULL,
  site_zone        TEXT NOT NULL,
  site_address     TEXT NOT NULL,
  site_contact     TEXT NOT NULL,
  site_phone       TEXT NOT NULL,
  purpose          TEXT NOT NULL,
  days             INTEGER NOT NULL,
  tier             TEXT NOT NULL,
  depot_zone       TEXT NOT NULL,
  float_km         REAL NOT NULL,
  with_operator    INTEGER NOT NULL DEFAULT 0,
  with_fuel        INTEGER NOT NULL DEFAULT 0,
  with_waiver      INTEGER NOT NULL DEFAULT 1,
  total_ngwee      INTEGER NOT NULL,
  payment_method   TEXT NOT NULL,
  payment_status   TEXT NOT NULL DEFAULT 'pending',
  status           TEXT NOT NULL DEFAULT 'requested',
  start_on         INTEGER,
  meter_note       TEXT,
  created_at       INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS hire_events (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  hire_id    INTEGER NOT NULL REFERENCES hires(id),
  status     TEXT NOT NULL,
  note       TEXT,
  actor      TEXT,
  created_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS events (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  order_id   INTEGER NOT NULL REFERENCES orders(id),
  status     TEXT NOT NULL,
  note       TEXT,
  actor      TEXT,
  created_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS fuel_facilities (
  id                INTEGER PRIMARY KEY AUTOINCREMENT,
  driver_id         INTEGER NOT NULL UNIQUE REFERENCES users(id),
  limit_ngwee       INTEGER NOT NULL DEFAULT 0,
  outstanding_ngwee INTEGER NOT NULL DEFAULT 0,
  status            TEXT NOT NULL DEFAULT 'active',
  completed_loads   INTEGER NOT NULL DEFAULT 0,
  avg_weekly_payout_ngwee INTEGER NOT NULL DEFAULT 0,
  rebased_at        INTEGER,
  created_at        INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS fuel_entitlements (
  id                    INTEGER PRIMARY KEY AUTOINCREMENT,
  order_id              INTEGER NOT NULL UNIQUE REFERENCES orders(id),
  driver_id             INTEGER NOT NULL REFERENCES users(id),
  litres                INTEGER NOT NULL,
  litres_drawn          INTEGER NOT NULL DEFAULT 0,
  price_ngwee_per_litre INTEGER NOT NULL,
  status                TEXT NOT NULL DEFAULT 'open',
  created_at            INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS fuel_draws (
  id                    INTEGER PRIMARY KEY AUTOINCREMENT,
  entitlement_id        INTEGER NOT NULL REFERENCES fuel_entitlements(id),
  driver_id             INTEGER NOT NULL REFERENCES users(id),
  litres                INTEGER NOT NULL,
  price_ngwee_per_litre INTEGER NOT NULL,
  value_ngwee           INTEGER NOT NULL,
  cost_ngwee_per_litre  INTEGER,
  station               TEXT,
  drawn_at              INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS settlements (
  id                   INTEGER PRIMARY KEY AUTOINCREMENT,
  order_id             INTEGER NOT NULL UNIQUE REFERENCES orders(id),
  driver_id            INTEGER NOT NULL REFERENCES users(id),
  gross_ngwee          INTEGER NOT NULL,
  fuel_deduction_ngwee INTEGER NOT NULL DEFAULT 0,
  net_ngwee            INTEGER NOT NULL,
  settled_at           INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS insurance_policies (
  id                   INTEGER PRIMARY KEY AUTOINCREMENT,
  order_id             INTEGER NOT NULL UNIQUE REFERENCES orders(id),
  commodity_key        TEXT NOT NULL,
  declared_value_ngwee INTEGER NOT NULL,
  rate_bp              INTEGER NOT NULL,
  premium_ngwee        INTEGER NOT NULL,
  commission_ngwee     INTEGER NOT NULL,
  insurer              TEXT,
  policy_ref           TEXT,
  status               TEXT NOT NULL DEFAULT 'quoted',
  created_at           INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_orders_shipper ON orders(shipper_id);
CREATE INDEX IF NOT EXISTS idx_orders_driver  ON orders(driver_id);
CREATE INDEX IF NOT EXISTS idx_orders_status  ON orders(status);
CREATE INDEX IF NOT EXISTS idx_events_order   ON events(order_id);
CREATE TABLE IF NOT EXISTS order_stops (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  order_id        INTEGER NOT NULL REFERENCES orders(id),
  seq             INTEGER NOT NULL,
  node_key        TEXT NOT NULL,
  address         TEXT NOT NULL,
  recipient_name  TEXT NOT NULL,
  recipient_phone TEXT NOT NULL,
  tonnes          REAL NOT NULL DEFAULT 0,
  discharged_kg   INTEGER,
  status          TEXT NOT NULL DEFAULT 'pending',
  proof_note      TEXT,
  completed_at    INTEGER
);

CREATE TABLE IF NOT EXISTS order_documents (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  order_id    INTEGER NOT NULL REFERENCES orders(id),
  doc_key     TEXT NOT NULL,
  name        TEXT NOT NULL,
  owner       TEXT NOT NULL,
  stage       TEXT NOT NULL,
  mandatory   INTEGER NOT NULL DEFAULT 1,
  note        TEXT,
  status      TEXT NOT NULL DEFAULT 'outstanding',
  reference   TEXT,
  filed_by    TEXT,
  filed_at    INTEGER,
  expires_on  INTEGER,
  UNIQUE (order_id, doc_key)
);

CREATE TABLE IF NOT EXISTS order_positions (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  order_id   INTEGER NOT NULL REFERENCES orders(id),
  lat        REAL NOT NULL,
  lng        REAL NOT NULL,
  node_key   TEXT,
  place      TEXT,
  km_done    REAL,
  km_left    REAL,
  source     TEXT NOT NULL DEFAULT 'driver',
  note       TEXT,
  created_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS contracts (
  id                  INTEGER PRIMARY KEY AUTOINCREMENT,
  ref                 TEXT NOT NULL UNIQUE,
  shipper_id          INTEGER NOT NULL REFERENCES users(id),
  name                TEXT NOT NULL,
  commodity_key       TEXT NOT NULL,
  equipment_key       TEXT NOT NULL,
  from_zone           TEXT NOT NULL,
  to_zone             TEXT NOT NULL,
  tonnes_committed    REAL NOT NULL,
  tonnes_called_off   REAL NOT NULL DEFAULT 0,
  rate_ngwee_per_tonne INTEGER NOT NULL,
  currency            TEXT NOT NULL DEFAULT 'ZMW',
  tolerance_pct       REAL NOT NULL DEFAULT 0.5,
  starts_on           INTEGER NOT NULL,
  ends_on             INTEGER NOT NULL,
  status              TEXT NOT NULL DEFAULT 'active',
  created_at          INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_stops_order     ON order_stops(order_id);
CREATE INDEX IF NOT EXISTS idx_docs_order      ON order_documents(order_id);
CREATE INDEX IF NOT EXISTS idx_positions_order ON order_positions(order_id);
CREATE INDEX IF NOT EXISTS idx_contracts_ship  ON contracts(shipper_id);

CREATE INDEX IF NOT EXISTS idx_hires_hirer     ON hires(hirer_id);
CREATE INDEX IF NOT EXISTS idx_hires_status    ON hires(status);
CREATE INDEX IF NOT EXISTS idx_hire_events     ON hire_events(hire_id);
CREATE INDEX IF NOT EXISTS idx_entitlements_dr ON fuel_entitlements(driver_id);
CREATE INDEX IF NOT EXISTS idx_draws_driver    ON fuel_draws(driver_id);
CREATE INDEX IF NOT EXISTS idx_settlements_dr  ON settlements(driver_id);

CREATE TABLE IF NOT EXISTS kyc_profiles (
  user_id        INTEGER PRIMARY KEY REFERENCES users(id),
  entity_type    TEXT NOT NULL DEFAULT 'limited',
  legal_name     TEXT,
  trading_name   TEXT,
  reg_number     TEXT,
  tin            TEXT,
  vat_number     TEXT,
  vat_registered INTEGER NOT NULL DEFAULT 0,
  cross_border   INTEGER NOT NULL DEFAULT 0,
  country        TEXT NOT NULL DEFAULT 'ZM',
  address        TEXT,
  sector         TEXT,
  updated_at     INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS kyc_people (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id       INTEGER NOT NULL REFERENCES users(id),
  full_name     TEXT NOT NULL,
  position      TEXT NOT NULL DEFAULT 'Director',
  id_type       TEXT NOT NULL DEFAULT 'nrc',
  id_number     TEXT NOT NULL,
  nationality   TEXT NOT NULL DEFAULT 'ZM',
  date_of_birth TEXT,
  ownership_pct REAL NOT NULL DEFAULT 0,
  is_control    INTEGER NOT NULL DEFAULT 0,
  created_at    INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS kyc_documents (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id     INTEGER NOT NULL REFERENCES users(id),
  doc_key     TEXT NOT NULL,
  name        TEXT NOT NULL,
  reference   TEXT,
  filename    TEXT,
  mime        TEXT,
  size_bytes  INTEGER NOT NULL DEFAULT 0,
  content     TEXT,
  status      TEXT NOT NULL DEFAULT 'filed',
  note        TEXT,
  issued_on   TEXT,
  expires_on  TEXT,
  filed_at    INTEGER NOT NULL,
  reviewed_at INTEGER,
  UNIQUE (user_id, doc_key)
);

CREATE TABLE IF NOT EXISTS kyc_events (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id    INTEGER NOT NULL REFERENCES users(id),
  status     TEXT NOT NULL,
  note       TEXT,
  actor      TEXT,
  created_at INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_kyc_people_user ON kyc_people(user_id);
CREATE INDEX IF NOT EXISTS idx_kyc_docs_user   ON kyc_documents(user_id);
CREATE INDEX IF NOT EXISTS idx_kyc_events_user ON kyc_events(user_id);

CREATE TABLE IF NOT EXISTS agreements (
  id                 INTEGER PRIMARY KEY AUTOINCREMENT,
  ref                TEXT NOT NULL UNIQUE,
  kind               TEXT NOT NULL,
  title              TEXT NOT NULL,
  body               TEXT NOT NULL,
  body_hash          TEXT NOT NULL,
  counterparty       TEXT NOT NULL,
  counterparty_email TEXT,
  counterparty_phone TEXT,
  account_id         INTEGER REFERENCES users(id),
  order_ref          TEXT,
  hire_ref           TEXT,
  created_by         INTEGER NOT NULL REFERENCES users(id),
  status             TEXT NOT NULL DEFAULT 'draft',
  token              TEXT NOT NULL UNIQUE,
  expires_at         INTEGER,
  sent_at            INTEGER,
  viewed_at          INTEGER,
  signed_at          INTEGER,
  signer_name        TEXT,
  signer_title       TEXT,
  signer_email       TEXT,
  signature_type     TEXT,
  signature          TEXT,
  signed_ip          TEXT,
  signed_agent       TEXT,
  decline_reason     TEXT,
  countersigned_at   INTEGER,
  countersigned_by   INTEGER REFERENCES users(id),
  countersignature   TEXT,
  created_at         INTEGER NOT NULL
);

-- Every opening of a document link, and what the reader actually did with it.
-- A signature tells you the end of the story; this tells you whether the
-- customer read past the price, whether they came back, and who else they
-- forwarded it to.
CREATE TABLE IF NOT EXISTS agreement_views (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  agreement_id INTEGER NOT NULL REFERENCES agreements(id),
  view_token   TEXT NOT NULL UNIQUE,
  viewer_email TEXT,
  ip           TEXT,
  agent        TEXT,
  seconds      INTEGER NOT NULL DEFAULT 0,
  max_section  INTEGER NOT NULL DEFAULT 0,
  sections     INTEGER NOT NULL DEFAULT 0,
  downloaded   INTEGER NOT NULL DEFAULT 0,
  signed       INTEGER NOT NULL DEFAULT 0,
  opened_at    INTEGER NOT NULL,
  last_seen_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS agreement_events (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  agreement_id INTEGER NOT NULL REFERENCES agreements(id),
  event        TEXT NOT NULL,
  actor        TEXT,
  ip           TEXT,
  agent        TEXT,
  note         TEXT,
  created_at   INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_agreements_account ON agreements(account_id);
CREATE INDEX IF NOT EXISTS idx_agreements_status  ON agreements(status);
CREATE INDEX IF NOT EXISTS idx_agreement_events   ON agreement_events(agreement_id);
CREATE INDEX IF NOT EXISTS idx_agreement_views    ON agreement_views(agreement_id);

-- Quotes ops sends out for the customer to accept and pay before we book the
-- load. The row freezes the pricing inputs and the total at send time, so the
-- customer sees the same number even if pricing constants change later.
CREATE TABLE IF NOT EXISTS quotes (
  id                 INTEGER PRIMARY KEY AUTOINCREMENT,
  ref                TEXT NOT NULL UNIQUE,
  token              TEXT NOT NULL UNIQUE,
  status             TEXT NOT NULL DEFAULT 'sent',
  equipment_key      TEXT NOT NULL,
  service_key        TEXT NOT NULL,
  commodity_key      TEXT NOT NULL,
  from_zone          TEXT NOT NULL,
  to_zone            TEXT NOT NULL,
  tonnes             REAL NOT NULL DEFAULT 0,
  stops_json         TEXT,
  pickup_address     TEXT,
  dropoff_address    TEXT,
  goods              TEXT,
  total_ngwee        INTEGER NOT NULL,
  net_ngwee          INTEGER NOT NULL,
  vat_ngwee          INTEGER NOT NULL DEFAULT 0,
  currency           TEXT NOT NULL DEFAULT 'ZMW',
  distance_km        REAL NOT NULL DEFAULT 0,
  eta_minutes        INTEGER NOT NULL DEFAULT 0,
  counterparty       TEXT NOT NULL,
  counterparty_email TEXT,
  counterparty_phone TEXT,
  payment_method     TEXT NOT NULL,
  payment_ref        TEXT,
  proof_note         TEXT,
  paid_at            INTEGER,
  paid_by            INTEGER REFERENCES users(id),
  order_ref          TEXT,
  note               TEXT,
  document_name      TEXT,
  document_mime      TEXT,
  document_size      INTEGER,
  document_content   TEXT,
  require_signature  INTEGER NOT NULL DEFAULT 1,
  require_payment    INTEGER NOT NULL DEFAULT 0,
  signed_at          INTEGER,
  signer_name        TEXT,
  signer_email       TEXT,
  signature          TEXT,
  signed_ip          TEXT,
  reminder_days      TEXT,
  last_reminded_at   INTEGER,
  reminder_count     INTEGER NOT NULL DEFAULT 0,
  created_by         INTEGER NOT NULL REFERENCES users(id),
  created_at         INTEGER NOT NULL,
  sent_at            INTEGER,
  viewed_at          INTEGER,
  accepted_at        INTEGER,
  expires_at         INTEGER
);

CREATE INDEX IF NOT EXISTS idx_quotes_status  ON quotes(status);
CREATE INDEX IF NOT EXISTS idx_quotes_created ON quotes(created_by);

-- One row per opening of a quote link. This is the DocSend-style trail:
-- ops can see how many times a customer opened the rate, from which IP,
-- how long they stayed, whether they took a copy of the attached document,
-- and whether the same link was forwarded to a colleague.
CREATE TABLE IF NOT EXISTS quote_views (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  quote_id     INTEGER NOT NULL REFERENCES quotes(id),
  view_token   TEXT NOT NULL UNIQUE,
  viewer_email TEXT,
  ip           TEXT,
  agent        TEXT,
  seconds      INTEGER NOT NULL DEFAULT 0,
  downloaded   INTEGER NOT NULL DEFAULT 0,
  signed       INTEGER NOT NULL DEFAULT 0,
  opened_at    INTEGER NOT NULL,
  last_seen_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS quote_events (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  quote_id   INTEGER NOT NULL REFERENCES quotes(id),
  event      TEXT NOT NULL,
  actor      TEXT,
  ip         TEXT,
  agent      TEXT,
  note       TEXT,
  created_at INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_quote_views  ON quote_views(quote_id);
CREATE INDEX IF NOT EXISTS idx_quote_events ON quote_events(quote_id);

-- Requests for prices and capacity sent to transporters. One row per RFP,
-- one row per invited transporter, one row per bid submitted. The terms body
-- lives on the RFP so every invitee sees the same text, and it is hashed so
-- what the transporter signed cannot be quietly restated.
CREATE TABLE IF NOT EXISTS rfps (
  id                 INTEGER PRIMARY KEY AUTOINCREMENT,
  ref                TEXT NOT NULL UNIQUE,
  title              TEXT NOT NULL,
  corridor           TEXT NOT NULL,
  from_place         TEXT NOT NULL,
  to_place           TEXT NOT NULL,
  commodity          TEXT NOT NULL,
  equipment          TEXT NOT NULL,
  tonnes_total       REAL NOT NULL DEFAULT 0,
  trucks_needed      INTEGER NOT NULL DEFAULT 0,
  loading_from       TEXT,
  loading_to         TEXT,
  currency           TEXT NOT NULL DEFAULT 'ZMW',
  target_ngwee_per_tonne INTEGER,
  cover_min          TEXT,
  notes              TEXT,
  terms_body         TEXT NOT NULL,
  terms_hash         TEXT NOT NULL,
  status             TEXT NOT NULL DEFAULT 'open',
  closes_at          INTEGER,
  created_by         INTEGER NOT NULL REFERENCES users(id),
  created_at         INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS rfp_invites (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  rfp_id        INTEGER NOT NULL REFERENCES rfps(id),
  token         TEXT NOT NULL UNIQUE,
  carrier_name  TEXT NOT NULL,
  carrier_email TEXT,
  carrier_phone TEXT,
  account_id    INTEGER REFERENCES users(id),
  status        TEXT NOT NULL DEFAULT 'sent',
  sent_at       INTEGER,
  opened_at     INTEGER,
  submitted_at  INTEGER,
  declined_at   INTEGER,
  decline_reason TEXT,
  created_at    INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS rfp_bids (
  id                    INTEGER PRIMARY KEY AUTOINCREMENT,
  rfp_id                INTEGER NOT NULL REFERENCES rfps(id),
  invite_id             INTEGER NOT NULL REFERENCES rfp_invites(id),
  rate_ngwee_per_tonne  INTEGER NOT NULL,
  currency              TEXT NOT NULL DEFAULT 'ZMW',
  trucks_offered        INTEGER NOT NULL DEFAULT 0,
  capacity_tonnes       REAL NOT NULL DEFAULT 0,
  available_from        TEXT,
  available_to          TEXT,
  notes                 TEXT,
  signer_name           TEXT NOT NULL,
  signer_title          TEXT,
  signer_email          TEXT,
  signature             TEXT,
  terms_hash            TEXT NOT NULL,
  ip                    TEXT,
  agent                 TEXT,
  status                TEXT NOT NULL DEFAULT 'submitted',
  awarded_at            INTEGER,
  awarded_by            INTEGER REFERENCES users(id),
  created_at            INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS rfp_events (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  rfp_id     INTEGER NOT NULL REFERENCES rfps(id),
  invite_id  INTEGER REFERENCES rfp_invites(id),
  bid_id     INTEGER REFERENCES rfp_bids(id),
  event      TEXT NOT NULL,
  actor      TEXT,
  ip         TEXT,
  agent      TEXT,
  note       TEXT,
  created_at INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_rfp_invites_rfp ON rfp_invites(rfp_id);
CREATE INDEX IF NOT EXISTS idx_rfp_bids_rfp    ON rfp_bids(rfp_id);
CREATE INDEX IF NOT EXISTS idx_rfp_events_rfp  ON rfp_events(rfp_id);
"""


def postgres():
    """True when this process is pointed at a Postgres database."""
    from . import pgdb
    return pgdb.configured()


def connect():
    if postgres():
        from . import pgdb
        return pgdb.connect()
    conn = sqlite3.connect(DB_PATH, timeout=SQLITE_TIMEOUT_SECONDS)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    # Concurrent readers alongside a writer, which the threaded server needs.
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA busy_timeout = %d" % (SQLITE_TIMEOUT_SECONDS * 1000))
    return conn


# Columns added to `orders` after the first release. SQLite has no
# "ADD COLUMN IF NOT EXISTS", so init() applies them by inspection - which
# keeps init() the whole migration story, as before.
ORDER_COLUMNS = [
    ("contract_id",     "INTEGER REFERENCES contracts(id)"),
    ("currency",        "TEXT NOT NULL DEFAULT 'ZMW'"),
    ("corridor",        "TEXT"),
    ("is_export",       "INTEGER NOT NULL DEFAULT 0"),
    ("stops_count",     "INTEGER NOT NULL DEFAULT 0"),
    ("loaded_kg",       "INTEGER"),
    ("discharged_kg",   "INTEGER"),
    ("variance_kg",     "INTEGER"),
    ("tolerance_pct",   "REAL NOT NULL DEFAULT 0.5"),
    ("last_lat",        "REAL"),
    ("last_lng",        "REAL"),
    ("last_place",      "TEXT"),
    ("last_ping_at",    "INTEGER"),
]


# Same story on `users`: verification arrived after the first accounts did,
# so an existing account gets the columns and starts life unverified.
AGREEMENT_COLUMNS = [
    ("require_email",  "INTEGER NOT NULL DEFAULT 0"),
    ("allow_download", "INTEGER NOT NULL DEFAULT 1"),
    ("link_disabled",  "INTEGER NOT NULL DEFAULT 0"),
    # DocuSign-style evidence captured at signing, so the certificate can show
    # how the signer was identified and what they consented to. esign_consent
    # is the ESIGN/UETA consent to transact electronically; authority_attested
    # is the signer's confirmation they may bind the counterparty; auth_method
    # records how they were identified (see agreements.AUTH_METHOD_LABEL).
    ("esign_consent",      "INTEGER NOT NULL DEFAULT 0"),
    ("authority_attested", "INTEGER NOT NULL DEFAULT 0"),
    ("auth_method",        "TEXT"),
]

QUOTE_COLUMNS = [
    ("document_name",    "TEXT"),
    ("document_mime",    "TEXT"),
    ("document_size",    "INTEGER"),
    ("document_content", "TEXT"),
    ("require_signature", "INTEGER NOT NULL DEFAULT 1"),
    ("require_payment",   "INTEGER NOT NULL DEFAULT 0"),
    ("signed_at",         "INTEGER"),
    ("signer_name",       "TEXT"),
    ("signer_email",      "TEXT"),
    ("signature",         "TEXT"),
    ("signed_ip",         "TEXT"),
    ("reminder_days",     "TEXT"),
    ("last_reminded_at",  "INTEGER"),
    ("reminder_count",    "INTEGER NOT NULL DEFAULT 0"),
    # Profit First: what the truck actually costs to buy, and what the
    # border/permit stack costs, so the margin is legible per quote rather
    # than a wish. slot_count > 1 turns the quote into a fixed package - the
    # unit of sale for spot cross-border where a single truck is not worth
    # dispatching.
    ("slot_count",         "INTEGER NOT NULL DEFAULT 1"),
    ("carrier_ngwee",      "INTEGER"),
    ("pass_through_ngwee", "INTEGER"),
    # A reservation window: after this the slots go back on the shelf. The
    # release itself is a cron; released_at is a note that it fired.
    ("reserve_by",         "INTEGER"),
    ("released_at",        "INTEGER"),
    # Pre-payment conditions the customer or consignee has to satisfy before
    # cash is taken - the Zim import permit is the archetype. JSON array of
    # {label, met, met_at, met_by}.
    ("conditions_json",    "TEXT"),
]

USER_COLUMNS = [
    ("kyc_status",       "TEXT NOT NULL DEFAULT 'unverified'"),
    ("kyc_submitted_at", "INTEGER"),
    ("kyc_decided_at",   "INTEGER"),
    ("kyc_note",         "TEXT"),
    ("kyc_reviewed_by",  "INTEGER"),
    ("account_status",   "TEXT NOT NULL DEFAULT 'active'"),
]

RFP_BID_COLUMNS = [
    # The trucks a bidder commits: JSON list of {plate, trailer, driver, ready}.
    # Stored as JSON rather than a child table because a bid is atomic - the
    # trucks are read and written with the bid, never edited alone, and RFP
    # award scoring cares about the count and the fleet as a set.
    ("trucks_json", "TEXT"),
]

RFP_COLUMNS = [
    # Payment terms: when Musanga settles the load. A transporter prices very
    # differently at Net-30 vs 33% on loading, so this has to be first-class
    # on the RFP - not a footnote inside the terms body. Stored as a short
    # human string ("33% on loading, 33% on delivery, 34% on POD") so it
    # renders straight into the page and the terms template alike.
    ("payment_terms", "TEXT"),
]


def _add_missing_columns(conn):
    for table, columns in (("orders", ORDER_COLUMNS), ("users", USER_COLUMNS),
                           ("agreements", AGREEMENT_COLUMNS),
                           ("quotes", QUOTE_COLUMNS),
                           ("rfp_bids", RFP_BID_COLUMNS),
                           ("rfps", RFP_COLUMNS)):
        have = {r["name"] for r in conn.execute("PRAGMA table_info(%s)" % table)}
        for name, decl in columns:
            if name not in have:
                conn.execute("ALTER TABLE %s ADD COLUMN %s %s" % (table, name, decl))


def init():
    """Create anything missing and return an open connection.

    On Postgres the schema is the generated file, applied statement by
    statement; every statement there is IF NOT EXISTS, so this is equally the
    install and the migration.
    """
    if postgres():
        from . import pgdb
        pgdb.apply_schema()
        return connect()
    conn = connect()
    with conn:
        conn.executescript(SCHEMA)
        _add_missing_columns(conn)
    return conn


def now():
    return int(time.time())


# --- passwords -------------------------------------------------------------
# pbkdf2 from the stdlib. Not argon2, but it is salted, iterated and correct.

PBKDF2_ROUNDS = 120_000


def hash_password(password):
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), PBKDF2_ROUNDS).hex()
    return "pbkdf2$%d$%s$%s" % (PBKDF2_ROUNDS, salt, digest)


def verify_password(password, stored):
    try:
        _, rounds, salt, digest = stored.split("$")
    except ValueError:
        return False
    check = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), int(rounds)).hex()
    return secrets.compare_digest(check, digest)


def new_ref(prefix="MSG"):
    """Human-readable reference someone can read down a phone line."""
    return "%s-%s" % (prefix, secrets.token_hex(3).upper())
