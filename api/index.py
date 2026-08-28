#!/usr/bin/env python3
"""Vercel entrypoint for the JSON API.

Two modes, decided by whether DATABASE_URL is set.

With it set - which is what production does - every instance talks to Supabase
Postgres over the connection pooler. State is durable, shared between
instances, and survives a recycle. This is a real deployment.

Without it, Vercel runs Python on a read-only filesystem where only /tmp is
writable, so the database is a scratch SQLite file seeded with demo data on
cold start. That makes the deployment a *showcase*: quotes, tracking and the
catalogue are exact, but a sign-up or a booking lives only as long as that one
instance. Fine for a link to send someone, wrong for anything real.
"""

import json
import os
import sys
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

# Must be set before musanga.db is imported - DB_PATH is read at import time.
os.environ.setdefault("MUSANGA_DB", "/tmp/musanga.db")
os.environ.setdefault("MUSANGA_ENV", "production")

from musanga import api, config, db  # noqa: E402

config.load_env()

# A KYC upload is base64 in a JSON body, so the ceiling is the 4 MB file
# limit plus its encoding overhead.
MAX_BODY_BYTES = 8 << 20

SECURITY_HEADERS = [
    ("X-Content-Type-Options", "nosniff"),
    ("X-Frame-Options", "DENY"),
    ("Referrer-Policy", "strict-origin-when-cross-origin"),
]


_READY = False

# POSTs that only compute an answer. Everything else writes, and writing to a
# scratch file that dies with the instance is worse than refusing outright.
READ_ONLY_POSTS = ("/api/quote", "/api/distance")


def no_database():
    """True when this is a production deployment with nowhere durable to write.

    The SQLite fallback exists so a showcase link works without a database. On
    a deployment calling itself production it is a trap: sign-up appears to
    succeed, the instance recycles, and the account is gone with no error
    anywhere. Serverless makes it worse - each instance has its own /tmp, so
    the next request may not even reach the file the last one wrote.
    """
    return config.production() and not db.postgres()


def ensure_db():
    """Make sure this instance can serve. Runs once, on the first request.

    On Postgres that means checking the schema is there and applying it if it
    is not - which happens on a fresh project and never again. On SQLite it
    means creating the scratch file, and seeding it when this is a showcase.
    """
    global _READY
    if _READY:
        return

    if db.postgres():
        conn = db.connect()
        try:
            conn.execute("SELECT 1 FROM users LIMIT 1").fetchone()
        except Exception:  # noqa: BLE001 - an empty project has no tables yet
            conn.close()
            db.init().close()
        else:
            conn.close()
        _READY = True
        return

    if not os.path.exists(db.DB_PATH):
        if os.environ.get("MUSANGA_SEED") == "demo":
            from seed import seed
            seed()
        else:
            db.init().close()
    _READY = True


class handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        sys.stderr.write("  %s\n" % (fmt % args))

    def _token(self):
        header = self.headers.get("Authorization") or ""
        return header[7:].strip() if header.lower().startswith("bearer ") else None

    def _read_body(self):
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0:
            return {}
        if length > MAX_BODY_BYTES:
            raise ValueError("Request body too large")
        try:
            return json.loads(self.rfile.read(length).decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            raise ValueError("Body must be valid JSON")

    def _send_json(self, status, payload):
        body = json.dumps(payload, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for header, value in SECURITY_HEADERS:
            self.send_header(header, value)
        self.end_headers()
        self.wfile.write(body)

    def _handle(self, method):
        try:
            ensure_db()
        except Exception as e:  # noqa: BLE001 - a broken instance must say so
            return self._send_json(500, {"error": "Database unavailable: %s" % e})
        try:
            body = self._read_body() if method in ("POST", "DELETE") else {}
        except ValueError as e:
            return self._send_json(400, {"error": str(e)})
        path = urlparse(self.path).path
        if (method in ("POST", "DELETE") and path not in READ_ONLY_POSTS
                and no_database()):
            return self._send_json(503, {
                "error": "This deployment has no database. Set DATABASE_URL to "
                         "the Supabase session pooler and redeploy; until then "
                         "nothing can be saved, so nothing is pretended to be."})
        forwarded = (self.headers.get("X-Forwarded-For") or "").split(",")[0].strip()
        meta = {"ip": forwarded or self.client_address[0],
                "agent": (self.headers.get("User-Agent") or "")[:300]}
        status, payload = api.dispatch(method, path, body, self._token(), meta)
        self._send_json(status, payload)

    def do_GET(self):
        self._handle("GET")

    def do_POST(self):
        self._handle("POST")

    def do_DELETE(self):
        self._handle("DELETE")
