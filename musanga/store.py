"""Supabase storage over PostgREST, on the standard library alone.

Why REST and not a Postgres driver: psycopg2 is a compiled dependency and this
project has no package manager by design. Supabase exposes every table and
function over PostgREST, which is plain HTTPS and JSON, so urllib is enough.

Configuration, all from the environment:

    SUPABASE_URL          https://<project>.supabase.co
    SUPABASE_SERVICE_KEY  the service_role key - server side only, never shipped
                          to a browser. It bypasses row level security.
    SUPABASE_SCHEMA       optional, defaults to public

Usage mirrors the SQL it generates:

    store.select("orders", eq={"ref": "MSG-1A2B3C"}, limit=1)
    store.insert("events", {"order_id": 4, "status": "delivered"})
    store.update("orders", {"status": "delivered"}, eq={"id": 4})
    store.rpc("settle_load", {"p_order_id": 4, "p_gross": 100, "p_deduction": 20})

Errors arrive as StoreError with the Postgres message attached, because a
silent failure in a ledger is worse than a loud one.
"""

import json
import os
import urllib.error
import urllib.parse
import urllib.request

TIMEOUT_SECONDS = 20


class StoreError(Exception):
    """A request to Supabase failed."""

    def __init__(self, message, status=None, detail=None):
        Exception.__init__(self, message)
        self.status = status
        self.detail = detail


def _config():
    url = (os.environ.get("SUPABASE_URL") or "").rstrip("/")
    key = os.environ.get("SUPABASE_SERVICE_KEY") or ""
    if not url or not key:
        raise StoreError(
            "SUPABASE_URL and SUPABASE_SERVICE_KEY must be set to use the "
            "Supabase store")
    return url, key


def configured():
    """True when the environment can reach a Supabase project."""
    return bool(os.environ.get("SUPABASE_URL") and os.environ.get("SUPABASE_SERVICE_KEY"))


def _headers(key, prefer=None):
    headers = {
        "apikey": key,
        "Authorization": "Bearer %s" % key,
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    schema = os.environ.get("SUPABASE_SCHEMA")
    if schema and schema != "public":
        headers["Accept-Profile"] = schema
        headers["Content-Profile"] = schema
    if prefer:
        headers["Prefer"] = prefer
    return headers


def _request(method, path, query=None, body=None, prefer=None):
    url, key = _config()
    target = "%s%s" % (url, path)
    if query:
        target += "?" + urllib.parse.urlencode(query, doseq=True)

    data = None
    if body is not None:
        data = json.dumps(body).encode("utf-8")

    req = urllib.request.Request(target, data=data, method=method,
                                 headers=_headers(key, prefer))
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_SECONDS) as resp:
            raw = resp.read()
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            payload = json.loads(raw.decode("utf-8"))
            message = payload.get("message") or payload.get("hint") or raw.decode("utf-8")
            detail = payload.get("details")
        except (ValueError, UnicodeDecodeError):
            message, detail = raw.decode("utf-8", "replace"), None
        raise StoreError(message, status=e.code, detail=detail)
    except urllib.error.URLError as e:
        raise StoreError("Cannot reach Supabase: %s" % e.reason)

    if not raw:
        return None
    try:
        return json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        raise StoreError("Supabase returned a response that was not JSON")


def _filters(eq=None, is_=None, in_=None):
    """PostgREST encodes filters as query parameters: column=op.value."""
    query = {}
    for column, value in (eq or {}).items():
        query[column] = "eq.%s" % value
    for column, value in (is_ or {}).items():
        query[column] = "is.%s" % ("null" if value is None else value)
    for column, values in (in_ or {}).items():
        query[column] = "in.(%s)" % ",".join(str(v) for v in values)
    return query


def select(table, columns="*", eq=None, is_=None, in_=None,
           order=None, limit=None, single=False):
    """Read rows. `single` returns one row or None instead of a list."""
    query = _filters(eq, is_, in_)
    query["select"] = columns
    if order:
        query["order"] = order
    if limit:
        query["limit"] = limit
    rows = _request("GET", "/rest/v1/%s" % table, query=query) or []
    if single:
        return rows[0] if rows else None
    return rows


def insert(table, row, upsert=False):
    """Insert one row or a list of rows, returning what was written."""
    prefer = "return=representation"
    if upsert:
        prefer += ",resolution=merge-duplicates"
    rows = _request("POST", "/rest/v1/%s" % table, body=row, prefer=prefer) or []
    if isinstance(row, dict):
        return rows[0] if rows else None
    return rows


def update(table, changes, eq=None, is_=None, in_=None):
    """Update matching rows, returning them. Refuses an unfiltered update."""
    query = _filters(eq, is_, in_)
    if not query:
        raise StoreError("Refusing to update %s with no filter" % table)
    return _request("PATCH", "/rest/v1/%s" % table, query=query, body=changes,
                    prefer="return=representation") or []


def delete(table, eq=None, is_=None, in_=None):
    """Delete matching rows. Refuses an unfiltered delete."""
    query = _filters(eq, is_, in_)
    if not query:
        raise StoreError("Refusing to delete from %s with no filter" % table)
    return _request("DELETE", "/rest/v1/%s" % table, query=query,
                    prefer="return=representation") or []


def rpc(function, args=None):
    """Call a Postgres function. This is how anything atomic is done."""
    return _request("POST", "/rest/v1/rpc/%s" % function, body=args or {})


def count(table, eq=None, is_=None, in_=None):
    """Row count, without pulling the rows back."""
    rows = select(table, columns="id", eq=eq, is_=is_, in_=in_)
    return len(rows)


def health():
    """Cheap round trip, for a startup check or a health endpoint."""
    try:
        select("users", columns="id", limit=1)
        return {"ok": True}
    except StoreError as e:
        return {"ok": False, "error": str(e), "status": e.status}
