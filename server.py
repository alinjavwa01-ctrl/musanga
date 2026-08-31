#!/usr/bin/env python3
"""Musanga dev server: static files from web/ plus the JSON API from musanga/.

Runs on the Python standard library alone - no pip install, no build step.

    python3 server.py            # http://localhost:8000
    python3 server.py --port 9000
    python3 server.py --seed     # reset the database with demo data
"""

import argparse
import json
import os
import posixpath
import sys
import time
from http.server import HTTPServer, SimpleHTTPRequestHandler
from socketserver import ThreadingMixIn
from urllib.parse import unquote, urlparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from musanga import api, config, db  # noqa: E402

config.load_env()

WEB_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web")
# A KYC upload is base64 in a JSON body, so the ceiling is the 4 MB file
# limit plus its encoding overhead.
MAX_BODY_BYTES = 8 << 20

# In development, assets must never be cached or an edit hides behind an old
# copy. In production the URLs are version-stamped by stamp.py, so the same
# files can be cached hard.
DEV = os.environ.get("MUSANGA_ENV", "development") != "production"
STATIC_CACHE = "no-store, must-revalidate" if DEV else "public, max-age=31536000, immutable"


class Handler(SimpleHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def __init__(self, *args, **kwargs):
        SimpleHTTPRequestHandler.__init__(self, *args, directory=WEB_ROOT, **kwargs)

    # --- plumbing ---------------------------------------------------------
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
        raw = self.rfile.read(length)
        try:
            return json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            raise ValueError("Body must be valid JSON")

    def _send_json(self, status, payload):
        body = json.dumps(payload, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _handle_api(self, method):
        started = time.time()
        try:
            body = self._read_body() if method in ("POST", "DELETE") else {}
        except ValueError as e:
            return self._send_json(400, {"error": str(e)})
        path = urlparse(self.path).path
        status, payload = api.dispatch(method, path, body, self._token(), self._meta())
        self._send_json(status, payload)
        # One line per API call: what, how it went, how long it took. Enough to
        # find a slow endpoint or a 500 without a logging stack.
        sys.stderr.write("  %s %s %d %dms\n"
                         % (method, path, status, (time.time() - started) * 1000))

    def _meta(self):
        """Who is calling, for the signature audit trail. Behind a proxy the
        socket address is the proxy, so the forwarded header wins when set."""
        forwarded = (self.headers.get("X-Forwarded-For") or "").split(",")[0].strip()
        return {"ip": forwarded or self.client_address[0],
                "agent": (self.headers.get("User-Agent") or "")[:300]}

    # --- routing ----------------------------------------------------------
    def do_POST(self):
        if urlparse(self.path).path.startswith("/api/"):
            return self._handle_api("POST")
        self._send_json(404, {"error": "No such endpoint"})

    def do_DELETE(self):
        if urlparse(self.path).path.startswith("/api/"):
            return self._handle_api("DELETE")
        self._send_json(404, {"error": "No such endpoint"})

    def do_GET(self):
        path = urlparse(self.path).path
        if path.startswith("/api/"):
            return self._handle_api("GET")
        SimpleHTTPRequestHandler.do_GET(self)

    def guess_type(self, path):
        """Declare UTF-8 on text responses.

        Without a charset the browser falls back to its own guess, which mangles
        anything outside ASCII - and with X-Content-Type-Options: nosniff it
        cannot recover by inspecting the bytes.
        """
        mimetype = SimpleHTTPRequestHandler.guess_type(self, path)
        if mimetype.startswith("text/") or mimetype in ("application/javascript", "image/svg+xml"):
            if "charset=" not in mimetype:
                return mimetype + "; charset=utf-8"
        return mimetype

    def end_headers(self):
        path = urlparse(self.path).path
        if not path.startswith("/api/"):
            # HTML always revalidates so a deploy is visible immediately; the
            # version-stamped assets it points at can be cached hard.
            self.send_header(
                "Cache-Control",
                "no-store, must-revalidate" if (DEV or path.endswith(".html") or path in ("/", "/track")) else STATIC_CACHE,
            )
        for header, value in SECURITY_HEADERS:
            self.send_header(header, value)
        if not DEV:
            # Only meaningful behind TLS, which is where production runs.
            self.send_header("Strict-Transport-Security",
                             "max-age=31536000; includeSubDomains")
        SimpleHTTPRequestHandler.end_headers(self)

    def translate_path(self, path):
        """Serve web/ and fall back to the app shell so client-side routes
        like /app/orders survive a page refresh."""
        clean = posixpath.normpath(unquote(urlparse(path).path))
        if clean in ("/", ""):
            return os.path.join(WEB_ROOT, "index.html")
        if clean == "/track":
            return os.path.join(WEB_ROOT, "track.html")
        # /sign/<token> is a public signing room: one page, the token in the URL.
        if clean == "/sign" or clean.startswith("/sign/"):
            return os.path.join(WEB_ROOT, "sign.html")
        # /quote/<token> is the public quote page. Same shape as /sign.
        if clean == "/quote" or clean.startswith("/quote/"):
            return os.path.join(WEB_ROOT, "quote.html")
        # /rfp/<token> is the transporter's RFP page. One page, one token.
        if clean == "/rfp" or clean.startswith("/rfp/"):
            return os.path.join(WEB_ROOT, "rfp.html")
        candidate = os.path.join(WEB_ROOT, clean.lstrip("/"))
        if os.path.isfile(candidate):
            return candidate
        if clean.startswith("/app"):
            return os.path.join(WEB_ROOT, "app.html")
        return candidate


# Sensible defaults for a site that loads no third-party anything.
SECURITY_HEADERS = [
    ("X-Content-Type-Options", "nosniff"),
    ("X-Frame-Options", "DENY"),
    ("Referrer-Policy", "strict-origin-when-cross-origin"),
    # style-src needs 'unsafe-inline' because the app builds views with inline
    # style attributes. Scripts stay strict - that is where XSS actually lives,
    # and everything user-supplied is escaped before it reaches innerHTML.
    ("Content-Security-Policy",
     "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; "
     "script-src 'self'; connect-src 'self'; frame-ancestors 'none'; "
     "base-uri 'none'; form-action 'self'; object-src 'none'"),
]


class Server(ThreadingMixIn, HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def main():
    parser = argparse.ArgumentParser(description="Musanga dev server")
    parser.add_argument("--port", type=int, default=int(os.environ.get("PORT", 8000)))
    parser.add_argument("--host", default=os.environ.get("HOST", "127.0.0.1"))
    parser.add_argument("--seed", action="store_true", help="reset the database with demo data")
    args = parser.parse_args()

    if args.seed:
        from seed import seed
        seed()

    # A database that will not answer must not stop the server coming up. The
    # landing page, the catalogue and every quote are computed rather than
    # stored, so they serve regardless; the endpoints that genuinely need the
    # database fail one request at a time and say why. Dying here turns one
    # wrong password into "the whole site is down", which hides the very thing
    # it is trying to report.
    try:
        db.init().close()
    except Exception as e:  # noqa: BLE001 - report it, do not die of it
        print("\n  WARNING: the database is not reachable.")
        print("    %s: %s" % (type(e).__name__, e))
        print("    Quotes, distances, the catalogue and the landing page still work.")
        print("    Accounts, bookings and tracking will not until this is fixed.")

    httpd = Server((args.host, args.port), Handler)
    print("\n  Musanga (%s) running on http://%s:%d"
          % ("production" if not DEV else "development", args.host, args.port))
    for key, value in sorted(config.describe().items()):
        print("    %-13s %s" % (key, value))
    print("  Landing page  /          Platform  /app          Tracking  /track\n")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n  Stopped.")


if __name__ == "__main__":
    main()
