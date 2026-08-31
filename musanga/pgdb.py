"""Postgres for production, behind the same tiny interface SQLite already has.

`musanga/api.py` was written against `sqlite3`: it calls `conn.execute(sql,
params)`, reads rows by column name, takes `cur.lastrowid` after an insert and
calls `conn.commit()`. Rewriting fifteen hundred lines of that into a second
dialect is how two data layers start disagreeing with each other, so this
module presents that same interface over Postgres instead, and the handlers do
not know which database they are talking to.

What it has to reconcile:

  * placeholders. pg8000 speaks the DB-API, so the driver's own qmark style
    takes `?` unchanged.
  * `lastrowid`. Postgres has no such thing; it has RETURNING. Every INSERT
    into a table with an `id` column gets `RETURNING id` appended, and the
    value comes back as `lastrowid`.
  * `INSERT OR IGNORE`, which is `ON CONFLICT DO NOTHING`.
  * `PRAGMA`, which does not exist and is skipped.

Connection reuse matters more here than it did with a file. A new TLS
connection to Supabase costs more than most of the queries behind it, so
connections are pooled and handed back on close().

Configuration, all from the environment:

    DATABASE_URL   postgresql://user:password@host:5432/postgres
                   (SUPABASE_DB_URL is accepted as an alias)
    MUSANGA_DB_SSL verify (default) | no-verify
    MUSANGA_DB_POOL how many connections to keep, default 5

Nothing here is imported unless a Postgres URL is configured, so the local
SQLite path keeps its zero-dependency promise.
"""

import os
import re
import ssl
import threading
import urllib.parse

TIMEOUT_SECONDS = 15
DEFAULT_POOL = 5


class ConfigError(RuntimeError):
    """The database URL is missing or unusable."""


# Where the connection string may be found, best first.
#
# DATABASE_URL is what this project sets by hand. The POSTGRES_* names are what
# the Vercel-Supabase marketplace integration injects on its own, which is the
# whole point of using it: the credential is placed into the deployment without
# anyone copying a password between two dashboards.
#
# POSTGRES_URL is preferred over POSTGRES_URL_NON_POOLING because "non pooling"
# means the direct host, and Supabase now serves that over IPv6 only unless the
# paid IPv4 add-on is bought - which most runners, Vercel included, cannot
# reach.
URL_VARS = ("DATABASE_URL", "SUPABASE_DB_URL", "POSTGRES_URL",
            "POSTGRES_PRISMA_URL", "POSTGRES_URL_NON_POOLING")

TRANSACTION_PORT = 6543
SESSION_PORT = 5432


def source():
    """Which environment variable the URL came from. For logs and health -
    a name, never a value."""
    for name in URL_VARS:
        if (os.environ.get(name) or "").startswith(("postgres://", "postgresql://")):
            return name
    return ""


def session_mode(raw):
    """Point a pooler URL at session mode.

    Supavisor answers on two ports: 6543 is transaction mode and 5432 is
    session mode. pg8000 speaks the extended query protocol, so it names and
    reuses prepared statements; transaction mode hands the underlying
    connection to somebody else between statements and the name goes with it.
    That fails intermittently under load rather than at startup, which is the
    worst way for it to fail. The integration hands out the 6543 URL by
    default, so it is corrected here rather than left to be discovered in
    production.
    """
    parsed = urllib.parse.urlparse(raw)
    if (parsed.hostname or "").endswith("pooler.supabase.com") and parsed.port == TRANSACTION_PORT:
        host = "%s:%d" % (parsed.hostname, SESSION_PORT)
        return parsed._replace(netloc="%s@%s" % (parsed.netloc.rsplit("@", 1)[0], host)).geturl()
    return raw


def url():
    for name in URL_VARS:
        raw = (os.environ.get(name) or "").strip()
        if raw.startswith(("postgres://", "postgresql://")):
            return session_mode(raw)
    return ""


def configured():
    return url().startswith(("postgres://", "postgresql://"))


def _driver():
    try:
        import pg8000.dbapi as driver
    except ImportError:  # pragma: no cover - only hit on a misconfigured host
        raise ConfigError(
            "DATABASE_URL is set but pg8000 is not installed. "
            "Run: pip3 install -r requirements.txt")
    # `?` placeholders, so the SQL in api.py is the SQL that runs.
    driver.paramstyle = "qmark"
    return driver


# Supabase does not use a public CA. Its Postgres endpoints present a
# certificate issued by "Supabase Intermediate 2021 CA", so the system trust
# store cannot verify them and a default context fails the handshake. The fix
# is their root certificate ("Supabase Root 2021 CA", valid to 2031), which is
# committed at supabase/prod-ca.crt - a public certificate, not a secret.
# Replace it from Project settings -> Database -> SSL configuration, or from
# https://supabase-downloads.s3-ap-southeast-1.amazonaws.com/prod/ssl/prod-ca-2021.crt
CA_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "supabase", "prod-ca.crt")


def ca_path():
    return os.environ.get("MUSANGA_DB_CA") or (CA_FILE if os.path.isfile(CA_FILE) else "")


def _ssl_context():
    mode = (os.environ.get("MUSANGA_DB_SSL") or "verify").lower()
    if mode == "disable":
        return None

    context = ssl.create_default_context()
    if mode == "no-verify":
        # Encrypted, but no longer proving who is on the other end. An explicit
        # setting, never a silent fallback: a connection that quietly stops
        # checking certificates is worse than one that fails loudly.
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        return context

    path = ca_path()
    if path:
        if not os.path.isfile(path):
            raise ConfigError("MUSANGA_DB_CA points at %s, which does not exist" % path)
        context.load_verify_locations(cafile=path)
        # The pooler's certificate is a wildcard for *.pooler.supabase.com and
        # matches the host, so hostname checking stays on.
    return context


def _params():
    parsed = urllib.parse.urlparse(url())
    if not parsed.hostname:
        raise ConfigError("DATABASE_URL is not a valid Postgres URL")
    return {
        "host": parsed.hostname,
        "port": parsed.port or 5432,
        "user": urllib.parse.unquote(parsed.username or "postgres"),
        "password": urllib.parse.unquote(parsed.password or ""),
        "database": (parsed.path or "/postgres").lstrip("/") or "postgres",
        "timeout": TIMEOUT_SECONDS,
        "ssl_context": _ssl_context(),
    }


# --- SQL translation -------------------------------------------------------
# Small, mechanical and cached. Anything that cannot be translated mechanically
# belongs in the handler, written portably, rather than being papered over here.

# Tables whose primary key is a generated `id`, and which therefore support
# lastrowid. Derived from the schema rather than listed by hand.
def _id_tables():
    from . import db
    found = set()
    for statement in db.SCHEMA.split(";"):
        match = re.search(r"CREATE TABLE IF NOT EXISTS (\w+)\s*\((.*)", statement,
                          re.I | re.S)
        if match and "INTEGER PRIMARY KEY AUTOINCREMENT" in match.group(2).upper():
            found.add(match.group(1).lower())
    return found


ID_TABLES = None
_TRANSLATED = {}
_INSERT_INTO = re.compile(r"^\s*INSERT\s+(?:OR\s+IGNORE\s+)?INTO\s+(\w+)", re.I)


def translate(sql):
    """SQLite statement in, Postgres statement out. `None` means 'skip it'."""
    global ID_TABLES
    if sql in _TRANSLATED:
        return _TRANSLATED[sql]

    out = sql
    stripped = out.strip().upper()

    if stripped.startswith("PRAGMA"):
        _TRANSLATED[sql] = None
        return None

    ignore = False
    if re.match(r"^\s*INSERT\s+OR\s+IGNORE\s+INTO", out, re.I):
        out = re.sub(r"^(\s*)INSERT\s+OR\s+IGNORE\s+INTO", r"\1INSERT INTO", out, flags=re.I)
        ignore = True

    match = _INSERT_INTO.match(out)
    if match:
        if ID_TABLES is None:
            ID_TABLES = _id_tables()
        table = match.group(1).lower()
        if ignore and "ON CONFLICT" not in out.upper():
            out = out.rstrip().rstrip(";") + " ON CONFLICT DO NOTHING"
        if table in ID_TABLES and "RETURNING" not in out.upper():
            out = out.rstrip().rstrip(";") + " RETURNING id"

    _TRANSLATED[sql] = out
    return out


# --- rows ------------------------------------------------------------------

class Row(object):
    """A row that answers to a column name, to an index, and to dict().

    sqlite3.Row does all three, and the handlers use all three.
    """

    __slots__ = ("_columns", "_values")

    def __init__(self, columns, values):
        self._columns = columns
        self._values = values

    def __getitem__(self, key):
        if isinstance(key, int):
            return self._values[key]
        try:
            return self._values[self._columns.index(key)]
        except ValueError:
            raise KeyError(key)

    def __contains__(self, key):
        return key in self._columns

    def keys(self):
        return list(self._columns)

    def __iter__(self):
        # dict(row) walks keys, the way sqlite3.Row does.
        return iter(self._columns)

    def __len__(self):
        return len(self._columns)

    def get(self, key, default=None):
        try:
            return self[key]
        except KeyError:
            return default

    def __repr__(self):
        return "<Row %s>" % dict(zip(self._columns, self._values))


class Cursor(object):
    def __init__(self, columns, rows, rowcount, lastrowid):
        self._rows = [Row(columns, values) for values in rows]
        self._index = 0
        self.rowcount = rowcount
        self.lastrowid = lastrowid
        self.description = [(name,) for name in columns]

    def fetchone(self):
        if self._index >= len(self._rows):
            return None
        self._index += 1
        return self._rows[self._index - 1]

    def fetchall(self):
        rest = self._rows[self._index:]
        self._index = len(self._rows)
        return rest

    def __iter__(self):
        return iter(self.fetchall())


# --- connections -----------------------------------------------------------

class Connection(object):
    """What `db.connect()` hands back. Closing returns it to the pool."""

    def __init__(self, raw, pool):
        self._raw = raw
        self._pool = pool
        self.closed = False

    # sqlite3.Connection.execute is a shortcut that makes its own cursor.
    def execute(self, sql, params=()):
        statement = translate(sql)
        if statement is None:
            return Cursor([], [], 0, None)

        cursor = self._raw.cursor()
        try:
            cursor.execute(statement, tuple(params))
            columns = [c[0] for c in (cursor.description or [])]
            rows = cursor.fetchall() if cursor.description else []
            lastrowid = None
            if columns == ["id"] and rows and statement.lstrip().upper().startswith("INSERT"):
                lastrowid = rows[0][0]
                rows = []
            return Cursor(columns, rows, cursor.rowcount, lastrowid)
        finally:
            cursor.close()

    def executescript(self, script):
        """Runs a whole file of DDL, one statement at a time, in one go."""
        cursor = self._raw.cursor()
        try:
            for statement in _split_script(script):
                cursor.execute(statement)
            self._raw.commit()
        finally:
            cursor.close()

    def commit(self):
        self._raw.commit()

    def rollback(self):
        self._raw.rollback()

    def close(self):
        if self.closed:
            return
        self.closed = True
        self._pool.give_back(self._raw)

    # `with conn:` commits on the way out, as sqlite3 does.
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        if exc_type is None:
            self.commit()
        else:
            self.rollback()
        return False


def _split_script(script):
    """Split on semicolons that are not inside a string literal or a $$ body."""
    statements, current, quote, dollar = [], "", None, False
    i = 0
    while i < len(script):
        char = script[i]
        if script.startswith("$$", i):
            dollar = not dollar
            current += "$$"
            i += 2
            continue
        if quote:
            if char == quote:
                quote = None
        elif char in ("'", '"') and not dollar:
            quote = char
        elif char == "-" and script.startswith("--", i) and not dollar:
            end = script.find("\n", i)
            i = len(script) if end < 0 else end
            continue
        elif char == ";" and not dollar:
            if current.strip():
                statements.append(current.strip())
            current = ""
            i += 1
            continue
        current += char
        i += 1
    if current.strip():
        statements.append(current.strip())
    return statements


class Pool(object):
    """A small connection pool. The server is threaded and every request opens
    a connection, so without this each one pays for a TLS handshake."""

    def __init__(self, size=None):
        self.size = int(size or os.environ.get("MUSANGA_DB_POOL") or DEFAULT_POOL)
        self._idle = []
        self._lock = threading.Lock()

    def take(self):
        with self._lock:
            while self._idle:
                raw = self._idle.pop()
                if _alive(raw):
                    return raw
        return _driver().connect(**_params())

    def give_back(self, raw):
        # A connection that failed mid-transaction is not safe to hand on.
        try:
            raw.rollback()
        except Exception:  # noqa: BLE001 - it is going in the bin either way
            _close_quietly(raw)
            return
        with self._lock:
            if len(self._idle) < self.size:
                self._idle.append(raw)
                return
        _close_quietly(raw)

    def drain(self):
        with self._lock:
            idle, self._idle = self._idle, []
        for raw in idle:
            _close_quietly(raw)


def _alive(raw):
    try:
        cursor = raw.cursor()
        cursor.execute("SELECT 1")
        cursor.fetchall()
        cursor.close()
        return True
    except Exception:  # noqa: BLE001 - a dead connection is simply replaced
        _close_quietly(raw)
        return False


def _close_quietly(raw):
    try:
        raw.close()
    except Exception:  # noqa: BLE001
        pass


POOL = Pool()


def connect():
    return Connection(POOL.take(), POOL)


# Chosen once, arbitrary, stable: the key pg_advisory_lock needs to serialise
# schema application. Two cold-starting instances that both run ALTER TABLE
# against the same relation take AccessExclusiveLock in different orders and
# deadlock; making one wait for the other turns that race into a no-op.
SCHEMA_ADVISORY_LOCK = 7318451205


def schema_installed():
    """Cheap presence check: is the newest thing the schema installs there?

    `rfps` is the newest table added in schema.sql, so if it is present the
    whole file has already been applied. Lets a warm cold-start skip the DDL
    entirely and avoids the advisory-lock round trip for the 99% case where
    nothing has changed since the last deploy.

    Whenever schema.sql gains a newer table, move this sentinel to it -
    otherwise a deploy that only adds tables past the old sentinel is judged
    "already installed" and the migration silently skips.
    """
    conn = connect()
    try:
        row = conn.execute(
            "SELECT 1 FROM information_schema.tables "
            "WHERE table_name = 'rfps'"
        ).fetchone()
        return row is not None
    except Exception:  # noqa: BLE001 - if the check itself fails, apply anyway
        return False
    finally:
        conn.close()


def apply_schema(path=None):
    """Create anything missing. Every statement is IF NOT EXISTS, so this is
    the migration as well as the install.

    Serverless makes this delicate: on a fresh deploy several instances cold
    start in parallel, each calls apply_schema, and even the idempotent
    ALTER/CREATE INDEX statements take AccessExclusiveLock. Two of them
    interleaving deadlocks Postgres, which is what ships the "database
    unavailable" page. Two mitigations: skip when the schema is already
    installed, and take a session-level advisory lock so only one instance
    runs the DDL at a time; the others wait, find everything present, and
    return."""
    if schema_installed():
        return
    path = path or os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "supabase", "schema.sql")
    with open(path) as handle:
        script = handle.read()
    conn = connect()
    try:
        conn.execute("SELECT pg_advisory_lock(?)", (SCHEMA_ADVISORY_LOCK,))
        conn.commit()
        try:
            if schema_installed_on(conn):
                return
            conn.executescript(script)
        finally:
            try:
                conn.execute("SELECT pg_advisory_unlock(?)", (SCHEMA_ADVISORY_LOCK,))
                conn.commit()
            except Exception:  # noqa: BLE001 - lock releases on disconnect anyway
                pass
    finally:
        conn.close()


def schema_installed_on(conn):
    """Same check as schema_installed(), but on a caller's connection.

    Once the advisory lock is held, another instance may have finished
    applying the schema while we were waiting; re-checking avoids re-running
    it for nothing."""
    try:
        row = conn.execute(
            "SELECT 1 FROM information_schema.tables "
            "WHERE table_name = 'rfps'"
        ).fetchone()
        return row is not None
    except Exception:  # noqa: BLE001
        return False


def health():
    """One round trip, for the health endpoint and for boot."""
    conn = connect()
    try:
        row = conn.execute("SELECT count(*) AS users FROM users").fetchone()
        return {"ok": True, "users": row["users"]}
    finally:
        conn.close()
