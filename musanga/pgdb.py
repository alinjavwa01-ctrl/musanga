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


def url():
    return os.environ.get("DATABASE_URL") or os.environ.get("SUPABASE_DB_URL") or ""


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


def _ssl_context():
    mode = (os.environ.get("MUSANGA_DB_SSL") or "verify").lower()
    if mode == "disable":
        return None
    context = ssl.create_default_context()
    if mode == "no-verify":
        # Only for a host whose certificate chain is not public. It still
        # encrypts; it stops proving who is on the other end.
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
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


def apply_schema(path=None):
    """Create anything missing. Every statement is IF NOT EXISTS, so this is
    the migration as well as the install."""
    path = path or os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "supabase", "schema.sql")
    with open(path) as handle:
        script = handle.read()
    conn = connect()
    try:
        conn.executescript(script)
    finally:
        conn.close()


def health():
    """One round trip, for the health endpoint and for boot."""
    conn = connect()
    try:
        row = conn.execute("SELECT count(*) AS users FROM users").fetchone()
        return {"ok": True, "users": row["users"]}
    finally:
        conn.close()
