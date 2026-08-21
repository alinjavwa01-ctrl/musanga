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

CREATE INDEX IF NOT EXISTS idx_orders_shipper ON orders(shipper_id);
CREATE INDEX IF NOT EXISTS idx_orders_driver  ON orders(driver_id);
CREATE INDEX IF NOT EXISTS idx_orders_status  ON orders(status);
CREATE INDEX IF NOT EXISTS idx_events_order   ON events(order_id);
CREATE INDEX IF NOT EXISTS idx_hires_hirer     ON hires(hirer_id);
CREATE INDEX IF NOT EXISTS idx_hires_status    ON hires(status);
CREATE INDEX IF NOT EXISTS idx_hire_events     ON hire_events(hire_id);
"""


def connect():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init():
    conn = connect()
    with conn:
        conn.executescript(SCHEMA)
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
