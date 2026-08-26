"""SQLite storage. No ORM, no migrations tool - the schema is small enough to
own outright, and `init()` is idempotent so it doubles as the migration."""

import hashlib
import os
import secrets
import sqlite3
import time

DB_PATH = os.environ.get("MUSANGA_DB", os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "musanga.db"))

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
"""


def connect():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
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


def _add_missing_columns(conn):
    have = {r["name"] for r in conn.execute("PRAGMA table_info(orders)")}
    for name, decl in ORDER_COLUMNS:
        if name not in have:
            conn.execute("ALTER TABLE orders ADD COLUMN %s %s" % (name, decl))


def init():
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
