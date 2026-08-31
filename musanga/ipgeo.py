"""Turns a raw IP + User-Agent into something a human can read - a rough
location and a device, the way DocSend or Wix labels an anonymous visitor
instead of just printing their address.

No third-party library: a hand-rolled User-Agent parse (regex over the
handful of browsers/OSes that actually show up) and a cached call to a free
IP-geolocation API for the rest. Lookups are cached in ip_geo forever - a
reader's city does not change between opens, and the cache is what keeps the
ops page fast after the first hit.

The other half of the job is telling a person from a bot: Outlook Safe
Links, Slack's unfurler and various mail scanners all auto-open a shared
link within seconds of send, which would otherwise read as "the customer
opened it" before anyone has looked at their inbox.
"""

import ipaddress
import json
import time
import urllib.error
import urllib.request

GEO_LOOKUP_URL = "https://ipapi.co/%s/json/"
GEO_TIMEOUT_SECONDS = 3

# Automated openers, not readers: mail security scanners that pre-fetch
# links, and chat/social unfurlers that fetch a link to build a preview card.
_BOT_MARKERS = (
    "bot", "spider", "crawl", "slurp", "facebookexternalhit", "slackbot",
    "whatsapp", "telegrambot", "linkedinbot", "twitterbot", "discordbot",
    "safelinks", "proofpoint", "mimecast", "barracuda", "outlook-",
    "headlesschrome", "phantomjs", "python-urllib", "python-requests", "curl/",
)

# Checked in order with `next()`, so a marker that is a substring of another
# browser's UA (Edge and Opera both carry "Chrome/") must come first.
_BROWSERS = (
    ("Edg/", "Edge"), ("OPR/", "Opera"), ("SamsungBrowser/", "Samsung Internet"),
    ("CriOS/", "Chrome"), ("FxiOS/", "Firefox"), ("Chrome/", "Chrome"),
    ("Firefox/", "Firefox"), ("Version/", "Safari"),
)

# Same ordering rule: iOS and ChromeOS UAs both contain "Mac OS X" / "Linux"
# as part of their real platform token, so the specific ones go first.
_PLATFORMS = (
    ("iPhone", "iPhone"), ("iPad", "iPad"), ("Android", "Android"),
    ("CrOS", "ChromeOS"), ("Windows", "Windows"), ("Mac OS X", "Mac"),
    ("Linux", "Linux"),
)


def parse_agent(agent):
    """{'browser', 'os'} from a raw User-Agent, or None if it looks like a
    bot/scanner rather than a person. Best-effort - covers what actually
    shows up in these logs, not a full UA database."""
    agent = agent or ""
    low = agent.lower()
    if not agent or any(marker in low for marker in _BOT_MARKERS):
        return None
    browser = next((label for marker, label in _BROWSERS if marker in agent), "")
    platform = next((label for marker, label in _PLATFORMS if marker in agent), "")
    return {"browser": browser, "os": platform}


def _is_lookupable(ip):
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return False
    return not (addr.is_private or addr.is_loopback or addr.is_link_local or addr.is_reserved)


def _fetch_geo(ip):
    req = urllib.request.Request(
        GEO_LOOKUP_URL % ip,
        headers={"User-Agent": "Musanga/1.0 (+https://musanga.vercel.app)"})
    try:
        with urllib.request.urlopen(req, timeout=GEO_TIMEOUT_SECONDS) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, ValueError, TimeoutError, OSError):
        return None
    if not isinstance(data, dict) or data.get("error"):
        return None
    return {"city": data.get("city") or "", "region": data.get("region") or "",
            "country": data.get("country_name") or ""}


def geolocate(conn, ip):
    """City/region/country for `ip`, cached in ip_geo so it is only ever
    looked up once. Empty dict for a private/local address or a lookup that
    fails - callers fall back to a plain 'Visitor' label rather than block
    the page on a retry."""
    if not ip or not _is_lookupable(ip):
        return {}
    row = conn.execute(
        "SELECT city, region, country FROM ip_geo WHERE ip = ?", (ip,)).fetchone()
    if row is not None:
        return dict(row)
    geo = _fetch_geo(ip)
    if geo is None:
        return {}
    conn.execute(
        "INSERT INTO ip_geo (ip, city, region, country, looked_up_at) VALUES (?,?,?,?,?)",
        (ip, geo["city"], geo["region"], geo["country"], int(time.time())))
    conn.commit()
    return geo


def visitor_label(email, ip, geo, device):
    """A Wix-style name for one view: the reader's email if the link asked
    for one, otherwise their rough location, otherwise something honest
    about what we don't know. `device` is parse_agent()'s result - None
    means this open was a bot/scanner, not a person."""
    if email:
        return email
    if device is None:
        return "Link scanner"
    place = ", ".join(p for p in (geo.get("city"), geo.get("country")) if p)
    if place:
        return "Visitor from " + place
    return "Visitor" if ip else "Anonymous"


def device_label(device):
    """'Chrome · Windows' from parse_agent()'s result, '' if unknown."""
    if not device:
        return ""
    return " · ".join(p for p in (device.get("browser"), device.get("os")) if p)
