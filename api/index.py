#!/usr/bin/env python3
"""Vercel entrypoint for the JSON API.

Vercel runs Python as serverless functions on a read-only filesystem, so the
database cannot live beside the code the way it does under server.py. Only
/tmp is writable, and it is per-instance and wiped when the instance recycles.

This module therefore points MUSANGA_DB at /tmp and seeds demo data on cold
start. That makes the deployment a *showcase*: quotes, tracking and the
catalogue are exact, but anything written - a sign-up, a booking, a status
change - lives only as long as that one instance and is not shared with other
visitors. Deployments that need durable state want server.py on a host with a
volume (see fly.toml), or Postgres in place of SQLite.
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

from musanga import api, db  # noqa: E402

# A KYC upload is base64 in a JSON body, so the ceiling is the 4 MB file
# limit plus its encoding overhead.
MAX_BODY_BYTES = 8 << 20

SECURITY_HEADERS = [
    ("X-Content-Type-Options", "nosniff"),
    ("X-Frame-Options", "DENY"),
    ("Referrer-Policy", "strict-origin-when-cross-origin"),
]


def ensure_db():
    """Create and seed the scratch database once per instance."""
    if os.path.exists(db.DB_PATH):
        return
    if os.environ.get("MUSANGA_SEED") == "demo":
        from seed import seed
        seed()
    else:
        db.init().close()


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
