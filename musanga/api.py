"""JSON API. Plain functions over sqlite, dispatched by a tiny pattern router."""

import json
import os
import re
import secrets
import sys
import threading
import time
import traceback

from . import agreements, db, docs, fuel, geo, insurance, kyc, pricing, rental

# The lifecycle of a job. Each status lists what may legally follow it, so an
# out-of-order update is rejected instead of corrupting the timeline.
FLOW = {
    "placed": ["assigned", "cancelled"],
    "assigned": ["at_pickup", "cancelled"],
    "at_pickup": ["in_transit", "cancelled"],
    "in_transit": ["delivered"],
    "delivered": [],
    "cancelled": [],
}

# A hire runs on its own lifecycle: we confirm it, float it out, it works, it
# comes off hire when the customer is done, and it is closed once back.
HIRE_FLOW = {
    "requested": ["confirmed", "cancelled"],
    "confirmed": ["on_site", "cancelled"],
    "on_site": ["off_hire"],
    "off_hire": ["returned"],
    "returned": [],
    "cancelled": [],
}

HIRE_STATUS_LABEL = {
    "requested": "Hire requested",
    "confirmed": "Confirmed",
    "on_site": "On site",
    "off_hire": "Off hire",
    "returned": "Returned to depot",
    "cancelled": "Cancelled",
}

OPEN_HIRE_STATUSES = ("requested", "confirmed", "on_site", "off_hire")

STATUS_LABEL = {
    "placed": "Load booked",
    "assigned": "Carrier assigned",
    "at_pickup": "At load-out",
    "in_transit": "In transit",
    "delivered": "Delivered",
    "cancelled": "Cancelled",
}

OPEN_STATUSES = ("placed", "assigned", "at_pickup", "in_transit")

# Which document stage has to be complete before a load may reach a status.
# This is the whole point of the register: the truck is stopped in the yard,
# where the paperwork is cheap to fix, instead of at Chirundu, where it is not.
STATUS_REQUIRES_DOCS = {
    "assigned": "booking",
    "in_transit": "border",
    "delivered": "delivery",
}
PAYMENT_METHODS = {
    "airtel": "Airtel Money",
    "mtn": "MTN MoMo",
    "zamtel": "Zamtel Kwacha",
    "card": "Card",
    "invoice": "Invoice (30 days)",
}



# --- throttling ------------------------------------------------------------
# Sign-in and sign-up are the two endpoints worth guessing at, so they get a
# per-address budget. This is in-process: on one long-running server it is the
# whole story, and on serverless it is per instance, which raises the cost of
# guessing without pretending to be a distributed rate limiter.

ATTEMPT_WINDOW_SECONDS = 900
ATTEMPT_LIMIT = 20
_attempts = {}
_attempts_lock = threading.Lock()


def throttle(ip, limit=ATTEMPT_LIMIT):
    if not ip:
        return
    now = time.time()
    with _attempts_lock:
        recent = [t for t in _attempts.get(ip, []) if now - t < ATTEMPT_WINDOW_SECONDS]
        recent.append(now)
        _attempts[ip] = recent
        if len(_attempts) > 4096:  # bound the memory, oldest addresses first
            for stale in sorted(_attempts, key=lambda k: _attempts[k][-1])[:1024]:
                _attempts.pop(stale, None)
    if len(recent) > limit:
        raise ApiError("Too many attempts. Wait fifteen minutes and try again.", 429)


def clear_attempts(ip):
    """A successful sign-in is evidence the address is not guessing."""
    if ip:
        with _attempts_lock:
            _attempts.pop(ip, None)


class ApiError(Exception):
    def __init__(self, message, status=400):
        Exception.__init__(self, message)
        self.message = message
        self.status = status


# --- helpers ---------------------------------------------------------------

def row_to_dict(row):
    return dict(row) if row is not None else None


def require(payload, *fields):
    missing = [f for f in fields if not str(payload.get(f) or "").strip()]
    if missing:
        raise ApiError("Missing required field(s): %s" % ", ".join(missing))
    return [str(payload[f]).strip() for f in fields]


# A session that never expires is a credential that never expires. Fourteen
# days by default, overridable for a deployment that wants shorter.
SESSION_DAYS = int(os.environ.get("MUSANGA_SESSION_DAYS") or 14)


def current_user(conn, token):
    if not token:
        return None
    row = conn.execute(
        "SELECT u.* FROM sessions s JOIN users u ON u.id = s.user_id "
        "WHERE s.token = ? AND s.created_at > ?",
        (token, db.now() - SESSION_DAYS * 86400),
    ).fetchone()
    return row_to_dict(row)


def auth(conn, token, *roles):
    user = current_user(conn, token)
    if not user:
        raise ApiError("Sign in to continue", 401)
    if roles and user["role"] not in roles:
        raise ApiError("Your account does not have access to this", 403)
    return user


def require_active(user):
    if (user.get("account_status") or "active") != "active":
        raise ApiError("This account is suspended. Contact Musanga control.", 403)


def public_user(user):
    out = {k: user[k] for k in ("id", "role", "name", "phone", "email", "company") if k in user}
    status = user.get("kyc_status") or "unverified"
    out["kyc_status"] = status
    out["kyc_status_label"] = kyc.STATUS_LABEL.get(status, status)
    out["kyc_note"] = user.get("kyc_note")
    out["account_status"] = user.get("account_status") or "active"
    out["verified"] = status == "verified" or user.get("role") in kyc.STAFF_ROLES
    out["can"] = {action: kyc.can(user, action) for action in kyc.GATED}
    return out


def require_verified(user, action):
    """Limited mode. The account exists and can look around; committing to a
    load, a machine or money waits for the file to be cleared."""
    require_active(user)
    if not kyc.can(user, action):
        raise ApiError(kyc.GATED[action], 403)


def log_event(conn, order_id, status, note, actor):
    conn.execute(
        "INSERT INTO events (order_id, status, note, actor, created_at) VALUES (?,?,?,?,?)",
        (order_id, status, note, actor, db.now()),
    )


def order_json(conn, row, include_timeline=False):
    o = row_to_dict(row)
    o["status_label"] = STATUS_LABEL.get(o["status"], o["status"])
    o["equipment_name"] = pricing.EQUIPMENT[o["equipment_key"]]["name"]
    o["service_name"] = pricing.SERVICE_LEVELS[o["service_key"]]["name"]
    o["commodity_name"] = pricing.COMMODITIES.get(o["commodity_key"], {}).get("name", o["commodity_key"])
    o["sector"] = pricing.COMMODITIES.get(o["commodity_key"], {}).get("sector", "general")
    o["from_name"] = geo.NODES[o["from_zone"]]["name"]
    o["to_name"] = geo.NODES[o["to_zone"]]["name"]
    cur = o.get("currency") or "ZMW"
    o["total"] = pricing.money(o["total_ngwee"], cur)
    o["payout"] = pricing.money(o["payout_ngwee"], cur)
    o["stops"] = stops_json(conn, o["id"])
    o["documents"] = documents_json(conn, o["id"])
    o["tracking"] = tracking_json(conn, o)
    o["weights"] = weights_json(o)
    try:
        o["crossings"] = geo.crossings(o["from_zone"], o["to_zone"])
    except ValueError:
        o["crossings"] = []
    o["payment_label"] = PAYMENT_METHODS.get(o["payment_method"], o["payment_method"])
    if o.get("driver_id"):
        d = conn.execute("SELECT name, phone FROM users WHERE id = ?", (o["driver_id"],)).fetchone()
        o["driver"] = row_to_dict(d)
        v = conn.execute("SELECT equipment_key, plate FROM vehicles WHERE driver_id = ?", (o["driver_id"],)).fetchone()
        o["driver_vehicle"] = row_to_dict(v)
    ent = conn.execute("SELECT * FROM fuel_entitlements WHERE order_id = ?", (o["id"],)).fetchone()
    if ent:
        o["fuel"] = {
            "litres": ent["litres"],
            "litres_drawn": ent["litres_drawn"],
            "litres_remaining": int(ent["litres"]) - int(ent["litres_drawn"]),
            "price_ngwee_per_litre": ent["price_ngwee_per_litre"],
            "status": ent["status"],
            "value": pricing.kwacha(int(ent["litres"]) * int(ent["price_ngwee_per_litre"])),
            "drawn_value": pricing.kwacha(int(ent["litres_drawn"]) * int(ent["price_ngwee_per_litre"])),
        }
    pol = conn.execute("SELECT * FROM insurance_policies WHERE order_id = ?", (o["id"],)).fetchone()
    if pol:
        o["cover"] = dict(
            row_to_dict(pol),
            declared_value=pricing.kwacha(pol["declared_value_ngwee"]),
            premium=pricing.kwacha(pol["premium_ngwee"]),
            rate_pct=round(pol["rate_bp"] / 100.0, 2),
        )
    settlement = conn.execute("SELECT * FROM settlements WHERE order_id = ?", (o["id"],)).fetchone()
    if settlement:
        o["settlement"] = dict(
            row_to_dict(settlement),
            gross=pricing.kwacha(settlement["gross_ngwee"]),
            fuel_deduction=pricing.kwacha(settlement["fuel_deduction_ngwee"]),
            net=pricing.kwacha(settlement["net_ngwee"]),
        )
    if include_timeline:
        rows = conn.execute(
            "SELECT status, note, actor, created_at FROM events WHERE order_id = ? ORDER BY id", (o["id"],)
        ).fetchall()
        o["timeline"] = [
            dict(row_to_dict(r), label=STATUS_LABEL.get(r["status"], r["status"])) for r in rows
        ]
    return o


# --- routes ----------------------------------------------------------------


def get_health(ctx):
    """Liveness plus one round trip to the database, for the platform's health
    check. Deliberately says nothing about what is inside."""
    conn = ctx["conn"]
    row = conn.execute("SELECT COUNT(*) AS n FROM users").fetchone()
    return {
        "ok": True,
        "database": "postgres" if db.postgres() else "sqlite",
        "accounts": row["n"],
        "time": db.now(),
    }


def get_config(ctx):
    return {
        "zones": geo.node_list(),
        # Every lane we have actually measured, for the network map. Anything
        # not in here is estimated from great-circle and is not drawn.
        "lanes": [{"from": a, "to": b, "km": km} for (a, b), km in geo.ROAD_KM.items()],
        "equipment": pricing.equipment_list(),
        "commodities": pricing.commodity_list(),
        "services": pricing.service_list(),
        "plant": rental.plant_list(),
        "plant_categories": rental.category_list(),
        "payment_methods": [{"key": k, "name": v} for k, v in PAYMENT_METHODS.items()],
        "countries": geo.country_list(),
        "corridors": geo.corridor_list(),
        "document_stages": [{"key": k, "name": docs.STAGE_LABEL[k]} for k in docs.STAGES],
        "kyc": {
            "entities": [dict(e, key=k) for k, e in kyc.ENTITIES.items()],
            "groups": [{"key": g, "name": kyc.GROUP_LABEL[g]} for g in kyc.GROUPS],
            "field_labels": kyc.FIELD_LABEL,
        },
    }


def post_quote(ctx):
    p = ctx["body"]
    require(p, "equipment", "service", "from_zone", "to_zone")
    commodity = p.get("commodity") or "general"
    try:
        q = pricing.quote(p["equipment"], p["service"], p["from_zone"], p["to_zone"],
                          p.get("tonnes", 0), commodity, stops=p.get("stops", 0))
    except (pricing.QuoteError, ValueError) as e:
        raise ApiError(str(e))
    return decorate_quote(q, commodity, p)


def decorate_quote(q, commodity, p):
    """Money is stored in ngwee and shown in the lane's trading currency, so
    every figure a shipper reads is formatted once, here."""
    cur = q["currency"]
    q["total"] = pricing.money(q["total_ngwee"], cur)
    q["net"] = pricing.money(q["net_ngwee"], cur)
    q["vat"] = pricing.money(q["vat_ngwee"], cur)
    q["rate_per_tonne"] = pricing.money(
        int(q["net_ngwee"] / q["billed_tonnes"]) if q["billed_tonnes"] else 0, cur)
    q["rate_per_tkm"] = pricing.kwacha(q["rate_per_tkm_ngwee"])
    for line in q["lines"]:
        line["amount"] = pricing.money(line["ngwee"], cur)
    q["lines"] = [l for l in q["lines"] if l["ngwee"]]
    q["documents"] = docs.required_for(commodity, q["from_zone"], q["to_zone"], q["equipment"])
    q["document_count"] = len(q["documents"])
    return q


def post_distance(ctx):
    """Road distance between two nodes. Published corridor tables need this
    without pretending to be a priced load."""
    p = ctx["body"]
    require(p, "from_zone", "to_zone")
    try:
        km = geo.route_km(p["from_zone"], p["to_zone"])
    except ValueError:
        raise ApiError("Unknown location")
    return {
        "from_zone": p["from_zone"], "to_zone": p["to_zone"],
        "from_name": geo.NODES[p["from_zone"]]["name"],
        "to_name": geo.NODES[p["to_zone"]]["name"],
        "distance_km": km,
    }


def post_register(ctx):
    conn, p = ctx["conn"], ctx["body"]
    throttle(ctx.get("ip"))
    name, phone, password, role = require(p, "name", "phone", "password", "role")
    if role not in ("shipper", "driver", "ops"):
        raise ApiError("Unknown account type")
    if len(password) < 8:
        raise ApiError("Password must be at least 8 characters")
    if conn.execute("SELECT 1 FROM users WHERE phone = ?", (phone,)).fetchone():
        raise ApiError("That phone number already has an account")
    cur = conn.execute(
        "INSERT INTO users (role, name, phone, email, company, password_hash, created_at) VALUES (?,?,?,?,?,?,?)",
        (role, name, phone, p.get("email"), p.get("company"), db.hash_password(password), db.now()),
    )
    user_id = cur.lastrowid
    clear_attempts(ctx.get("ip"))
    # The verification file is opened with the account, empty. Nothing about
    # signing up depends on it being filled in.
    conn.execute(
        "INSERT INTO kyc_profiles (user_id, entity_type, trading_name, country, updated_at) VALUES (?,?,?,?,?)",
        (user_id, "individual" if role == "driver" else "limited", p.get("company"), "ZM", db.now()))
    log_kyc(conn, user_id, "unverified", "Account opened", name)
    if role == "driver":
        conn.execute(
            "INSERT INTO vehicles (driver_id, equipment_key, plate, home_zone, is_online) VALUES (?,?,?,?,0)",
            (user_id, p.get("equipment_key") or "flatbed30", p.get("plate") or "UNREGISTERED",
             p.get("home_zone") or "lusaka"),
        )
    conn.commit()
    return _start_session(conn, user_id)


def post_login(ctx):
    conn, p = ctx["conn"], ctx["body"]
    throttle(ctx.get("ip"))
    phone, password = require(p, "phone", "password")
    row = conn.execute("SELECT * FROM users WHERE phone = ?", (phone,)).fetchone()
    if not row or not db.verify_password(password, row["password_hash"]):
        raise ApiError("Phone number or password is not right", 401)
    clear_attempts(ctx.get("ip"))
    return _start_session(conn, row["id"])


def _start_session(conn, user_id):
    # Signing in is the natural moment to take out the rubbish: expired rows
    # are useless and this saves running anything on a timer.
    conn.execute("DELETE FROM sessions WHERE created_at < ?", (db.now() - SESSION_DAYS * 86400,))
    token = secrets.token_urlsafe(32)
    conn.execute("INSERT INTO sessions (token, user_id, created_at) VALUES (?,?,?)", (token, user_id, db.now()))
    conn.commit()
    user = row_to_dict(conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone())
    return {"token": token, "user": public_user(user)}


def post_logout(ctx):
    ctx["conn"].execute("DELETE FROM sessions WHERE token = ?", (ctx["token"],))
    ctx["conn"].commit()
    return {"ok": True}


def get_me(ctx):
    user = auth(ctx["conn"], ctx["token"])
    out = {"user": public_user(user)}
    if user["role"] != "ops":
        state = kyc_state(ctx["conn"], user)
        out["kyc"] = {k: state[k] for k in
                      ("status", "status_label", "note", "blockers", "can_submit",
                       "documents_required", "documents_filed")}
    if user["role"] == "driver":
        v = ctx["conn"].execute("SELECT * FROM vehicles WHERE driver_id = ?", (user["id"],)).fetchone()
        out["vehicle"] = row_to_dict(v)
    return out


# --- know your customer ----------------------------------------------------
# Signup is three fields and a password. Everything a regulator, an insurer or
# a bank would ask for is collected here instead, inside the app, after the
# account already exists.

MAX_UPLOAD_BYTES = 4 * 1024 * 1024
ALLOWED_MIME = ("application/pdf", "image/jpeg", "image/png", "image/heic", "image/webp")


def kyc_profile(conn, user_id):
    return row_to_dict(conn.execute("SELECT * FROM kyc_profiles WHERE user_id = ?", (user_id,)).fetchone())


def kyc_people(conn, user_id):
    rows = conn.execute("SELECT * FROM kyc_people WHERE user_id = ? ORDER BY is_control DESC, id",
                        (user_id,)).fetchall()
    return [row_to_dict(r) for r in rows]


def kyc_documents(conn, user_id):
    """Filed documents, without the file bytes - those are fetched one at a
    time, by whoever is entitled to see them."""
    rows = conn.execute(
        "SELECT id, doc_key, name, reference, filename, mime, size_bytes, status, note, "
        "issued_on, expires_on, filed_at, reviewed_at, content IS NOT NULL AS has_file "
        "FROM kyc_documents WHERE user_id = ? ORDER BY filed_at", (user_id,)).fetchall()
    return [row_to_dict(r) for r in rows]


def kyc_state(conn, user):
    """One payload the verification centre renders from end to end."""
    profile = kyc_profile(conn, user["id"])
    people = kyc_people(conn, user["id"])
    filed = kyc_documents(conn, user["id"])
    held = {d["doc_key"] for d in filed if d["status"] != "rejected"}
    checklist, blockers = kyc.outstanding(user["role"], profile, people, held)

    by_key = {d["doc_key"]: d for d in filed}
    for item in checklist:
        item["document"] = by_key.get(item["key"])
        item["status"] = (item["document"] or {}).get("status", "outstanding")

    entity_type = (profile or {}).get("entity_type") or "limited"
    status = user.get("kyc_status") or "unverified"
    mandatory = [d for d in checklist if d["mandatory"]]
    done = len([d for d in mandatory if d["filed"]])
    events = [row_to_dict(r) for r in conn.execute(
        "SELECT * FROM kyc_events WHERE user_id = ? ORDER BY created_at DESC", (user["id"],)).fetchall()]

    return {
        "status": status,
        "status_label": kyc.STATUS_LABEL.get(status, status),
        "note": user.get("kyc_note"),
        "submitted_at": user.get("kyc_submitted_at"),
        "decided_at": user.get("kyc_decided_at"),
        "entity_type": entity_type,
        "entity_name": kyc.ENTITIES.get(entity_type, {}).get("name", entity_type),
        "profile": profile,
        "profile_fields": kyc.profile_fields(entity_type),
        "missing_fields": kyc.missing_fields(profile),
        "people": people,
        "people_rule": kyc.people_rule(entity_type),
        "people_problems": kyc.missing_people(entity_type, people),
        "checklist": checklist,
        "documents_required": len(mandatory),
        "documents_filed": done,
        "blockers": blockers,
        "can_submit": not blockers and status in ("unverified", "rejected"),
        "events": events,
        "gates": kyc.GATED,
    }


def log_kyc(conn, user_id, status, note, actor):
    conn.execute(
        "INSERT INTO kyc_events (user_id, status, note, actor, created_at) VALUES (?,?,?,?,?)",
        (user_id, status, note, actor, db.now()))


def ensure_profile(conn, user):
    if kyc_profile(conn, user["id"]):
        return
    conn.execute(
        "INSERT INTO kyc_profiles (user_id, entity_type, trading_name, country, updated_at) "
        "VALUES (?,?,?,?,?)",
        (user["id"], "individual" if user["role"] == "driver" else "limited",
         user.get("company"), "ZM", db.now()))


def reopen_if_decided(conn, user):
    """Editing the file after a decision puts the account back in your hands."""
    if (user.get("kyc_status") or "unverified") == "in_review":
        raise ApiError("Your file is with our compliance team. It cannot be edited while in review.")


def get_kyc(ctx):
    conn = ctx["conn"]
    user = auth(conn, ctx["token"])
    ensure_profile(conn, user)
    conn.commit()
    return kyc_state(conn, user)


PROFILE_FIELDS = ("entity_type", "legal_name", "trading_name", "reg_number", "tin",
                  "vat_number", "country", "address", "sector")


def post_kyc_profile(ctx):
    conn, p = ctx["conn"], ctx["body"]
    user = auth(conn, ctx["token"])
    reopen_if_decided(conn, user)
    ensure_profile(conn, user)
    if p.get("entity_type") and p["entity_type"] not in kyc.ENTITIES:
        raise ApiError("Unknown business type")

    changes, values = [], []
    for field in PROFILE_FIELDS:
        if field in p:
            changes.append("%s = ?" % field)
            values.append(str(p[field] or "").strip() or None)
    for flag in ("vat_registered", "cross_border"):
        if flag in p:
            changes.append("%s = ?" % flag)
            values.append(1 if p[flag] else 0)
    if changes:
        changes.append("updated_at = ?")
        values += [db.now(), user["id"]]
        conn.execute("UPDATE kyc_profiles SET %s WHERE user_id = ?" % ", ".join(changes), values)

    # The company on the account follows the trading name, so invoices and the
    # load board show what the customer actually calls itself.
    name = str(p.get("trading_name") or p.get("legal_name") or "").strip()
    if name:
        conn.execute("UPDATE users SET company = ? WHERE id = ?", (name, user["id"]))
    conn.commit()
    return kyc_state(conn, current_user(conn, ctx["token"]))


ID_TYPES = ("nrc", "passport", "drivers_licence")


def post_kyc_people(ctx):
    conn, p = ctx["conn"], ctx["body"]
    user = auth(conn, ctx["token"])
    reopen_if_decided(conn, user)
    full_name, id_number = require(p, "full_name", "id_number")
    id_type = p.get("id_type") or "nrc"
    if id_type not in ID_TYPES:
        raise ApiError("Unknown identity document type")
    try:
        ownership = float(p.get("ownership_pct") or 0)
    except (TypeError, ValueError):
        raise ApiError("Ownership must be a percentage")
    if not 0 <= ownership <= 100:
        raise ApiError("Ownership must be between 0 and 100 percent")

    if p.get("is_control"):
        conn.execute("UPDATE kyc_people SET is_control = 0 WHERE user_id = ?", (user["id"],))
    conn.execute(
        "INSERT INTO kyc_people (user_id, full_name, position, id_type, id_number, nationality, "
        "date_of_birth, ownership_pct, is_control, created_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
        (user["id"], full_name, p.get("position") or "Director", id_type, id_number,
         p.get("nationality") or "ZM", p.get("date_of_birth"), ownership,
         1 if p.get("is_control") else 0, db.now()))
    conn.commit()
    return kyc_state(conn, user)


def delete_kyc_person(ctx, person_id):
    conn = ctx["conn"]
    user = auth(conn, ctx["token"])
    reopen_if_decided(conn, user)
    row = conn.execute("SELECT * FROM kyc_people WHERE id = ? AND user_id = ?",
                       (person_id, user["id"])).fetchone()
    if not row:
        raise ApiError("No such person on your file", 404)
    conn.execute("DELETE FROM kyc_people WHERE id = ?", (person_id,))
    conn.commit()
    return kyc_state(conn, user)


def _decode_upload(p):
    """A document arrives as base64 from the browser. Held in the row: this
    project has no object store, and a KYC file is small and rarely read."""
    content = p.get("file")
    if not content:
        return None, None, None, 0
    if "," in content and content[:5] == "data:":
        header, content = content.split(",", 1)
        mime = header[5:].split(";")[0]
    else:
        mime = p.get("mime") or "application/octet-stream"
    if mime not in ALLOWED_MIME:
        raise ApiError("Upload a PDF or a photo (JPEG, PNG, HEIC or WebP)")
    size = int(len(content) * 3 / 4)
    if size > MAX_UPLOAD_BYTES:
        raise ApiError("That file is larger than 4 MB. Photograph the page rather than scanning it at full resolution.")
    return content, mime, str(p.get("filename") or "document").strip()[:120], size


def post_kyc_document(ctx):
    conn, p = ctx["conn"], ctx["body"]
    user = auth(conn, ctx["token"])
    reopen_if_decided(conn, user)
    ensure_profile(conn, user)
    doc_key, = require(p, "doc_key")

    profile = kyc_profile(conn, user["id"])
    catalogue = kyc.catalogue(user["role"], (profile or {}).get("entity_type"),
                              vat_registered=bool((profile or {}).get("vat_registered")),
                              cross_border=bool((profile or {}).get("cross_border")))
    item = [d for d in catalogue if d["key"] == doc_key]
    if not item:
        raise ApiError("That document is not on your checklist")
    item = item[0]

    content, mime, filename, size = _decode_upload(p)
    if not content and not str(p.get("reference") or "").strip():
        raise ApiError("Attach the document, or give the reference number it can be verified against")

    conn.execute(
        "INSERT INTO kyc_documents (user_id, doc_key, name, reference, filename, mime, size_bytes, "
        "content, status, issued_on, expires_on, filed_at) VALUES (?,?,?,?,?,?,?,?,'filed',?,?,?) "
        "ON CONFLICT (user_id, doc_key) DO UPDATE SET reference = excluded.reference, "
        "filename = COALESCE(excluded.filename, kyc_documents.filename), "
        "mime = COALESCE(excluded.mime, kyc_documents.mime), "
        "size_bytes = CASE WHEN excluded.content IS NOT NULL THEN excluded.size_bytes "
        "ELSE kyc_documents.size_bytes END, "
        "content = COALESCE(excluded.content, kyc_documents.content), "
        "status = 'filed', note = NULL, issued_on = excluded.issued_on, "
        "expires_on = excluded.expires_on, filed_at = excluded.filed_at, reviewed_at = NULL",
        (user["id"], doc_key, item["name"], str(p.get("reference") or "").strip() or None,
         filename, mime, size, content, p.get("issued_on"), p.get("expires_on"), db.now()))
    conn.commit()
    return kyc_state(conn, user)


def delete_kyc_document(ctx, doc_id):
    conn = ctx["conn"]
    user = auth(conn, ctx["token"])
    reopen_if_decided(conn, user)
    row = conn.execute("SELECT * FROM kyc_documents WHERE id = ? AND user_id = ?",
                       (doc_id, user["id"])).fetchone()
    if not row:
        raise ApiError("No such document on your file", 404)
    conn.execute("DELETE FROM kyc_documents WHERE id = ?", (doc_id,))
    conn.commit()
    return kyc_state(conn, user)


def get_kyc_file(ctx, doc_id):
    """The file itself, to the account that filed it or to compliance."""
    conn = ctx["conn"]
    user = auth(conn, ctx["token"])
    row = conn.execute("SELECT * FROM kyc_documents WHERE id = ?", (doc_id,)).fetchone()
    if not row or (user["role"] != "ops" and row["user_id"] != user["id"]):
        raise ApiError("No such document", 404)
    if not row["content"]:
        raise ApiError("That document was filed as a reference, with no attachment", 404)
    return {"filename": row["filename"], "mime": row["mime"], "content": row["content"]}


def post_kyc_submit(ctx):
    conn = ctx["conn"]
    user = auth(conn, ctx["token"])
    state = kyc_state(conn, user)
    if state["status"] == "in_review":
        raise ApiError("Your file is already with our compliance team")
    if state["status"] == "verified":
        raise ApiError("This account is already verified")
    if state["blockers"]:
        raise ApiError("Still outstanding: %s" % "; ".join(state["blockers"][:3]))
    conn.execute("UPDATE users SET kyc_status = 'in_review', kyc_submitted_at = ?, kyc_note = NULL WHERE id = ?",
                 (db.now(), user["id"]))
    log_kyc(conn, user["id"], "in_review", "Submitted for verification", user["name"])
    conn.commit()
    return kyc_state(conn, current_user(conn, ctx["token"]))


def get_ops_kyc(ctx):
    """The compliance queue: everyone waiting, oldest first."""
    conn = ctx["conn"]
    auth(conn, ctx["token"], "ops")
    rows = conn.execute(
        "SELECT u.*, p.legal_name, p.entity_type, p.reg_number, p.tin "
        "FROM users u LEFT JOIN kyc_profiles p ON p.user_id = u.id "
        "WHERE u.role != 'ops' ORDER BY "
        "CASE u.kyc_status WHEN 'in_review' THEN 0 WHEN 'rejected' THEN 1 "
        "WHEN 'unverified' THEN 2 ELSE 3 END, u.kyc_submitted_at, u.id").fetchall()
    out = []
    for r in rows:
        r = row_to_dict(r)
        out.append({
            "id": r["id"], "name": r["name"], "role": r["role"], "phone": r["phone"],
            "email": r["email"], "company": r["company"], "legal_name": r["legal_name"],
            "entity_type": r["entity_type"], "reg_number": r["reg_number"], "tin": r["tin"],
            "status": r["kyc_status"] or "unverified",
            "status_label": kyc.STATUS_LABEL.get(r["kyc_status"] or "unverified"),
            "submitted_at": r["kyc_submitted_at"], "created_at": r["created_at"],
        })
    return {"applicants": out,
            "waiting": len([a for a in out if a["status"] == "in_review"])}


def get_ops_kyc_one(ctx, user_id):
    conn = ctx["conn"]
    auth(conn, ctx["token"], "ops")
    row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    if not row:
        raise ApiError("No such account", 404)
    applicant = row_to_dict(row)
    state = kyc_state(conn, applicant)
    state["applicant"] = public_user(applicant)
    return state


DECISIONS = {"verified": "Verified", "rejected": "Sent back to the applicant"}


def post_ops_kyc_decision(ctx, user_id):
    conn, p = ctx["conn"], ctx["body"]
    reviewer = auth(conn, ctx["token"], "ops")
    decision, = require(p, "decision")
    if decision not in DECISIONS:
        raise ApiError("A file is either verified or sent back")
    row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    if not row:
        raise ApiError("No such account", 404)
    if row["role"] == "ops":
        raise ApiError("Staff accounts are not verified through this queue")
    note = str(p.get("note") or "").strip()
    if decision == "rejected" and not note:
        raise ApiError("Say what is wrong with the file, so it can be fixed")

    conn.execute("UPDATE users SET kyc_status = ?, kyc_decided_at = ?, kyc_note = ?, kyc_reviewed_by = ? WHERE id = ?",
                 (decision, db.now(), note or None, reviewer["id"], user_id))
    # A rejected file names the documents to redo, so the applicant is not
    # left guessing which one failed.
    for doc_key in (p.get("reject_documents") or []):
        conn.execute("UPDATE kyc_documents SET status = 'rejected', note = ?, reviewed_at = ? "
                     "WHERE user_id = ? AND doc_key = ?", (note or None, db.now(), user_id, doc_key))
    if decision == "verified":
        conn.execute("UPDATE kyc_documents SET status = 'accepted', reviewed_at = ? "
                     "WHERE user_id = ? AND status = 'filed'", (db.now(), user_id))
    log_kyc(conn, user_id, decision, note or DECISIONS[decision], reviewer["name"])
    conn.commit()
    return get_ops_kyc_one(ctx, user_id)


# --- agreements: sign by link ----------------------------------------------
# A shipper does not want an account in order to sign a contract, and making
# them have one is how contracts end up unsigned. So the document is reachable
# on a long random link, and everything that touches it is recorded.

SIGN_WINDOW_DAYS = 30
MAX_SIGNATURE_BYTES = 400 * 1024


def agreement_link(a):
    return "/sign/%s" % a["token"]


def agreement_json(conn, row, include_body=True, include_events=True):
    a = row_to_dict(row)
    out = {k: a[k] for k in (
        "id", "ref", "kind", "title", "counterparty", "counterparty_email",
        "counterparty_phone", "account_id", "order_ref", "hire_ref", "status",
        "signer_name", "signer_title", "signer_email", "signature_type",
        "decline_reason", "created_at", "sent_at", "viewed_at", "signed_at",
        "countersigned_at", "expires_at", "body_hash")}
    out["kind_label"] = agreements.KINDS.get(a["kind"], a["kind"])
    out["status_label"] = agreements.STATUS_LABEL.get(a["status"], a["status"])
    out["link"] = agreement_link(a)
    out["expired"] = bool(a["expires_at"] and a["expires_at"] < db.now()
                          and a["status"] in agreements.OPEN_STATUSES)
    if include_body:
        out["body"] = a["body"]
        out["signature"] = a["signature"]
        out["countersignature"] = a["countersignature"]
    if include_events:
        out["events"] = agreement_events(conn, a["id"])
        out["certificate"] = agreements.certificate(a, out["events"]) if a["status"] == "signed" else None
    return out


def agreement_events(conn, agreement_id):
    rows = conn.execute(
        "SELECT * FROM agreement_events WHERE agreement_id = ? ORDER BY created_at, id",
        (agreement_id,)).fetchall()
    out = []
    for r in rows:
        e = row_to_dict(r)
        e["label"] = agreements.EVENT_LABEL.get(e["event"], e["event"])
        e["created_at_label"] = time.strftime("%d %b %Y %H:%M", time.gmtime(e["created_at"]))
        out.append(e)
    return out


def log_agreement(ctx, agreement_id, event, actor=None, note=None):
    ctx["conn"].execute(
        "INSERT INTO agreement_events (agreement_id, event, actor, ip, agent, note, created_at) "
        "VALUES (?,?,?,?,?,?,?)",
        (agreement_id, event, actor, ctx.get("ip"), ctx.get("agent"), note, db.now()))


def find_agreement(conn, ref):
    row = conn.execute("SELECT * FROM agreements WHERE ref = ?", (ref,)).fetchone()
    if not row:
        raise ApiError("No agreement with that reference", 404)
    return row


def _match_account(conn, p):
    """Link the document to an account where one obviously matches, so a
    signed contract turns up in the customer's own app too."""
    if p.get("account_id"):
        return int(p["account_id"])
    for column, value in (("email", p.get("counterparty_email")), ("phone", p.get("counterparty_phone"))):
        if not value:
            continue
        row = conn.execute("SELECT id FROM users WHERE %s = ?" % column, (str(value).strip(),)).fetchone()
        if row:
            return row["id"]
    return None


def context_from_order(conn, order_ref):
    """A shipment agreement writes itself out of the booking it covers."""
    row = conn.execute("SELECT * FROM orders WHERE ref = ?", (order_ref,)).fetchone()
    if not row:
        raise ApiError("No load with that reference", 404)
    o = order_json(conn, row)
    per_tonne = o["total_ngwee"] / o["billed_tonnes"] if o["billed_tonnes"] else 0
    return o, {
        "order_ref": o["ref"],
        "commodity": o["commodity_name"],
        "equipment": "%s (%s)" % (o["equipment_name"], o["service_name"]),
        "pickup": "%s - %s" % (o["from_name"], o["pickup_address"]),
        "dropoff": "%s - %s" % (o["to_name"], o["dropoff_address"]),
        "corridor": o.get("corridor") or "%s to %s" % (o["from_name"], o["to_name"]),
        "distance": "%s km" % o["distance_km"],
        "tonnage": "%s t (billed %s t)" % (o["tonnes"], o["billed_tonnes"]),
        "rate": "%s per tonne" % pricing.money(int(per_tonne), o.get("currency") or "ZMW"),
        "total": "%s including VAT" % o["total"],
        "payment": o["payment_label"],
        "cover": "Goods in transit, per the booking",
        "tolerance": "%.1f%%" % (o.get("tolerance_pct") or 0.5),
    }


def context_from_hire(conn, hire_ref):
    row = conn.execute("SELECT * FROM hires WHERE ref = ?", (hire_ref,)).fetchone()
    if not row:
        raise ApiError("No hire with that reference", 404)
    h = hire_json(conn, row)
    return h, {
        "plant": h["plant_name"],
        "site": "%s - %s" % (h["site_name"], h["site_address"]),
        "purpose": h["purpose"],
        "days": "%d days" % h["days"],
        "rate": h.get("tier_label") or h["tier"],
        "operator": "Included" if h["with_operator"] else "Not included",
        "fuel": "Included" if h["with_fuel"] else "Not included",
        "waiver": "Taken" if h["with_waiver"] else "Not taken",
        "total": h["total"],
    }


def get_templates(ctx):
    auth(ctx["conn"], ctx["token"], "ops")
    return {"templates": agreements.template_list(), "company": agreements.COMPANY}


def post_agreements(ctx):
    """Draft a document. Nothing leaves the building until it is sent."""
    conn, p = ctx["conn"], ctx["body"]
    user = auth(conn, ctx["token"], "ops")
    template_key, counterparty = require(p, "template", "counterparty")
    if template_key not in agreements.TEMPLATES:
        raise ApiError("No such template")

    fields = dict(p.get("fields") or {})
    fields.setdefault("counterparty", counterparty)
    fields.setdefault("dated", time.strftime("%d %B %Y"))

    order_ref = str(p.get("order_ref") or "").strip() or None
    hire_ref = str(p.get("hire_ref") or "").strip() or None
    if order_ref:
        order, derived = context_from_order(conn, order_ref)
        derived.update({k: v for k, v in fields.items() if v})
        fields = derived
        fields.setdefault("counterparty", counterparty)
    if hire_ref:
        hire, derived = context_from_hire(conn, hire_ref)
        derived.update({k: v for k, v in fields.items() if v})
        fields = derived

    ref = db.new_ref("AGR")
    fields.setdefault("ref", ref)
    body = agreements.render(template_key, fields)
    title = str(p.get("title") or "").strip() or agreements.TEMPLATES[template_key]["name"]

    cur = conn.execute(
        "INSERT INTO agreements (ref, kind, title, body, body_hash, counterparty, counterparty_email, "
        "counterparty_phone, account_id, order_ref, hire_ref, created_by, status, token, created_at) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,'draft',?,?)",
        (ref, agreements.TEMPLATES[template_key]["kind"], title, body, agreements.digest(body),
         counterparty, str(p.get("counterparty_email") or "").strip() or None,
         str(p.get("counterparty_phone") or "").strip() or None, _match_account(conn, p),
         order_ref, hire_ref, user["id"], secrets.token_urlsafe(32), db.now()))
    log_agreement(ctx, cur.lastrowid, "created", user["name"], title)
    conn.commit()
    return agreement_json(conn, conn.execute("SELECT * FROM agreements WHERE id = ?", (cur.lastrowid,)).fetchone())


def get_agreements(ctx):
    """Ops sees the whole book; an account sees only its own paper."""
    conn = ctx["conn"]
    user = auth(conn, ctx["token"])
    if user["role"] == "ops":
        account = ctx["body"].get("account_id")
        rows = conn.execute(
            "SELECT * FROM agreements %s ORDER BY created_at DESC" %
            ("WHERE account_id = ?" if account else ""),
            (account,) if account else ()).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM agreements WHERE account_id = ? AND status != 'draft' ORDER BY created_at DESC",
            (user["id"],)).fetchall()
    return {"agreements": [agreement_json(conn, r, include_body=False, include_events=False) for r in rows]}


def get_agreement(ctx, ref):
    conn = ctx["conn"]
    user = auth(conn, ctx["token"])
    row = find_agreement(conn, ref)
    if user["role"] != "ops" and row["account_id"] != user["id"]:
        raise ApiError("Not your agreement", 403)
    if user["role"] != "ops" and row["status"] == "draft":
        raise ApiError("No agreement with that reference", 404)
    return agreement_json(conn, row)


def post_agreement_send(ctx, ref):
    """Freeze the text, stamp the hash, hand back the link to send."""
    conn, p = ctx["conn"], ctx["body"]
    user = auth(conn, ctx["token"], "ops")
    row = find_agreement(conn, ref)
    if row["status"] not in ("draft", "sent", "viewed"):
        raise ApiError("A %s agreement cannot be sent again. Draft a new one." % row["status"])

    days = int(p.get("expires_in_days") or SIGN_WINDOW_DAYS)
    token = row["token"] if row["status"] != "draft" else row["token"]
    if p.get("reissue"):
        token = secrets.token_urlsafe(32)
    conn.execute(
        "UPDATE agreements SET status = 'sent', token = ?, sent_at = COALESCE(sent_at, ?), "
        "expires_at = ?, viewed_at = NULL WHERE id = ?",
        (token, db.now(), db.now() + days * 86400, row["id"]))
    log_agreement(ctx, row["id"], "resent" if p.get("reissue") else "sent", user["name"],
                  row["counterparty_email"] or row["counterparty_phone"])
    conn.commit()
    return agreement_json(conn, conn.execute("SELECT * FROM agreements WHERE id = ?", (row["id"],)).fetchone())


def post_agreement_void(ctx, ref):
    conn, p = ctx["conn"], ctx["body"]
    user = auth(conn, ctx["token"], "ops")
    row = find_agreement(conn, ref)
    if row["status"] == "signed":
        raise ApiError("A signed agreement cannot be voided. Supersede it with a new one.")
    conn.execute("UPDATE agreements SET status = 'void' WHERE id = ?", (row["id"],))
    log_agreement(ctx, row["id"], "voided", user["name"], str(p.get("reason") or "").strip() or None)
    conn.commit()
    return agreement_json(conn, conn.execute("SELECT * FROM agreements WHERE id = ?", (row["id"],)).fetchone())


def post_agreement_countersign(ctx, ref):
    """Musanga's side of the signature. Only after the customer has signed."""
    conn, p = ctx["conn"], ctx["body"]
    user = auth(conn, ctx["token"], "ops")
    row = find_agreement(conn, ref)
    if row["status"] != "signed":
        raise ApiError("Nothing to countersign until the customer has signed")
    if row["countersigned_at"]:
        raise ApiError("Already countersigned")
    conn.execute("UPDATE agreements SET countersigned_at = ?, countersigned_by = ?, countersignature = ? WHERE id = ?",
                 (db.now(), user["id"], str(p.get("signature") or user["name"]), row["id"]))
    log_agreement(ctx, row["id"], "countersigned", user["name"])
    conn.commit()
    return agreement_json(conn, conn.execute("SELECT * FROM agreements WHERE id = ?", (row["id"],)).fetchone())


# --- the public signing room ----------------------------------------------

def _open_agreement(conn, token):
    row = conn.execute("SELECT * FROM agreements WHERE token = ?", (token,)).fetchone()
    if not row or row["status"] == "draft":
        raise ApiError("This signing link is not valid", 404)
    if row["status"] == "void":
        raise ApiError("This agreement was withdrawn. Contact Musanga for a new one.", 410)
    if row["expires_at"] and row["expires_at"] < db.now() and row["status"] in agreements.OPEN_STATUSES:
        raise ApiError("This signing link has expired. Ask Musanga to reissue it.", 410)
    return row


def get_sign(ctx, token):
    """What the signer sees. No account, no session, no other customer's data."""
    conn = ctx["conn"]
    row = _open_agreement(conn, token)
    if row["status"] == "sent":
        conn.execute("UPDATE agreements SET status = 'viewed', viewed_at = ? WHERE id = ?",
                     (db.now(), row["id"]))
        log_agreement(ctx, row["id"], "opened", row["counterparty"])
        conn.commit()
        row = conn.execute("SELECT * FROM agreements WHERE id = ?", (row["id"],)).fetchone()

    a = agreement_json(conn, row)
    return {
        "agreement": {k: a[k] for k in (
            "ref", "kind", "kind_label", "title", "body", "body_hash", "counterparty",
            "counterparty_email", "status", "status_label", "signed_at", "signer_name",
            "signer_title", "signer_email", "signature", "countersigned_at",
            "countersignature", "expires_at", "order_ref", "hire_ref")},
        "company": agreements.COMPANY,
        "events": [{"label": e["label"], "created_at": e["created_at"]} for e in a["events"]],
        "certificate": a["certificate"],
    }


def post_sign(ctx, token):
    conn, p = ctx["conn"], ctx["body"]
    row = _open_agreement(conn, token)
    if row["status"] == "signed":
        raise ApiError("This agreement has already been signed")
    if row["status"] == "declined":
        raise ApiError("This agreement was declined. Contact Musanga for a new one.")

    signer_name, signer_email = require(p, "signer_name", "signer_email")
    if "@" not in signer_email:
        raise ApiError("That does not look like an email address")
    if not p.get("consent"):
        raise ApiError("Tick the box to adopt your signature electronically")
    signature = str(p.get("signature") or "").strip()
    signature_type = p.get("signature_type") or "typed"
    if signature_type not in ("typed", "drawn"):
        raise ApiError("Unknown signature type")
    if not signature:
        raise ApiError("Draw or type your signature")
    if len(signature) > MAX_SIGNATURE_BYTES:
        raise ApiError("That signature image is too large")
    if signature_type == "typed" and signature.strip().lower() != signer_name.strip().lower():
        raise ApiError("A typed signature must match the name you signed as")

    conn.execute(
        "UPDATE agreements SET status = 'signed', signed_at = ?, signer_name = ?, signer_title = ?, "
        "signer_email = ?, signature = ?, signature_type = ?, signed_ip = ?, signed_agent = ? WHERE id = ?",
        (db.now(), signer_name, str(p.get("signer_title") or "").strip() or None, signer_email,
         signature, signature_type, ctx.get("ip"), ctx.get("agent"), row["id"]))
    log_agreement(ctx, row["id"], "signed", "%s <%s>" % (signer_name, signer_email))
    # A signature is also a way of finding the account: sign with the address
    # you registered with and the copy lands in your own app.
    if not row["account_id"]:
        match = conn.execute("SELECT id FROM users WHERE email = ?", (signer_email,)).fetchone()
        if match:
            conn.execute("UPDATE agreements SET account_id = ? WHERE id = ?", (match["id"], row["id"]))
    conn.commit()
    return get_sign(ctx, token)


def post_decline(ctx, token):
    conn, p = ctx["conn"], ctx["body"]
    row = _open_agreement(conn, token)
    if row["status"] == "signed":
        raise ApiError("This agreement has already been signed")
    reason, = require(p, "reason")
    conn.execute("UPDATE agreements SET status = 'declined', decline_reason = ? WHERE id = ?",
                 (reason, row["id"]))
    log_agreement(ctx, row["id"], "declined", str(p.get("signer_name") or row["counterparty"]), reason)
    conn.commit()
    return {"ok": True, "status": "declined"}


def post_sign_downloaded(ctx, token):
    """The signer took a copy. Recorded, because 'I never received it' is the
    most common thing said about a contract nobody can produce."""
    conn = ctx["conn"]
    row = _open_agreement(conn, token)
    log_agreement(ctx, row["id"], "downloaded", row["signer_name"] or row["counterparty"])
    conn.commit()
    return {"ok": True}


# --- the mothership: every counterparty on the network ---------------------
# Control needs one place that answers "who is this company, are they cleared,
# what have they signed, and what are they running right now" without opening
# four screens. This is that place.

def account_summary(conn, row):
    a = row_to_dict(row)
    role = a["role"]
    if role == "shipper":
        volume = conn.execute(
            "SELECT COUNT(*) c, COALESCE(SUM(total_ngwee),0) v, COALESCE(SUM(tonnes),0) t "
            "FROM orders WHERE shipper_id = ? AND status != 'cancelled'", (a["id"],)).fetchone()
        live = conn.execute(
            "SELECT COUNT(*) c FROM orders WHERE shipper_id = ? AND status IN ('placed','assigned','at_pickup','in_transit')",
            (a["id"],)).fetchone()["c"]
    else:
        volume = conn.execute(
            "SELECT COUNT(*) c, COALESCE(SUM(payout_ngwee),0) v, COALESCE(SUM(tonnes),0) t "
            "FROM orders WHERE driver_id = ? AND status != 'cancelled'", (a["id"],)).fetchone()
        live = conn.execute(
            "SELECT COUNT(*) c FROM orders WHERE driver_id = ? AND status IN ('assigned','at_pickup','in_transit')",
            (a["id"],)).fetchone()["c"]

    signed = conn.execute(
        "SELECT COUNT(*) c FROM agreements WHERE account_id = ? AND status = 'signed'", (a["id"],)).fetchone()["c"]
    waiting = conn.execute(
        "SELECT COUNT(*) c FROM agreements WHERE account_id = ? AND status IN ('sent','viewed')",
        (a["id"],)).fetchone()["c"]

    status = a.get("kyc_status") or "unverified"
    return {
        "id": a["id"], "role": role, "name": a["name"], "phone": a["phone"], "email": a["email"],
        "company": a["company"], "created_at": a["created_at"],
        "account_status": a.get("account_status") or "active",
        "kyc_status": status, "kyc_status_label": kyc.STATUS_LABEL.get(status, status),
        "loads": volume["c"], "live_loads": live, "tonnes": round(volume["t"] or 0, 1),
        "value_ngwee": volume["v"] or 0, "value": pricing.kwacha(volume["v"] or 0),
        "agreements_signed": signed, "agreements_waiting": waiting,
    }


def get_network(ctx):
    conn = ctx["conn"]
    auth(conn, ctx["token"], "ops")
    rows = conn.execute("SELECT * FROM users WHERE role != 'ops' ORDER BY role, COALESCE(company, name)").fetchall()
    accounts = [account_summary(conn, r) for r in rows]
    return {
        "shippers": [a for a in accounts if a["role"] == "shipper"],
        "carriers": [a for a in accounts if a["role"] == "driver"],
        "totals": {
            "accounts": len(accounts),
            "awaiting_review": len([a for a in accounts if a["kyc_status"] == "in_review"]),
            "unverified": len([a for a in accounts if a["kyc_status"] == "unverified"]),
            "suspended": len([a for a in accounts if a["account_status"] == "suspended"]),
            "paper_out": sum(a["agreements_waiting"] for a in accounts),
        },
    }


def get_account(ctx, user_id):
    """One counterparty, whole: who they are, their file, their paper, their
    work, and what they are owed or owe."""
    conn = ctx["conn"]
    auth(conn, ctx["token"], "ops")
    row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    if not row or row["role"] == "ops":
        raise ApiError("No such account", 404)
    account = row_to_dict(row)

    out = {"account": account_summary(conn, row), "user": public_user(account)}
    out["kyc"] = kyc_state(conn, account)
    out["agreements"] = [agreement_json(conn, r, include_body=False, include_events=False) for r in conn.execute(
        "SELECT * FROM agreements WHERE account_id = ? ORDER BY created_at DESC", (user_id,)).fetchall()]

    if account["role"] == "shipper":
        orders = conn.execute("SELECT * FROM orders WHERE shipper_id = ? ORDER BY created_at DESC LIMIT 25",
                              (user_id,)).fetchall()
        out["contracts"] = [row_to_dict(r) for r in conn.execute(
            "SELECT * FROM contracts WHERE shipper_id = ? ORDER BY created_at DESC", (user_id,)).fetchall()]
        out["hires"] = [hire_json(conn, r) for r in conn.execute(
            "SELECT * FROM hires WHERE hirer_id = ? ORDER BY created_at DESC LIMIT 10", (user_id,)).fetchall()]
    else:
        orders = conn.execute("SELECT * FROM orders WHERE driver_id = ? ORDER BY created_at DESC LIMIT 25",
                              (user_id,)).fetchall()
        out["vehicle"] = row_to_dict(conn.execute(
            "SELECT * FROM vehicles WHERE driver_id = ?", (user_id,)).fetchone())
        facility = conn.execute("SELECT * FROM fuel_facilities WHERE driver_id = ?", (user_id,)).fetchone()
        out["fuel_facility"] = row_to_dict(facility)
        out["settlements"] = [row_to_dict(r) for r in conn.execute(
            "SELECT * FROM settlements WHERE driver_id = ? ORDER BY settled_at DESC LIMIT 10",
            (user_id,)).fetchall()]
    out["orders"] = [order_json(conn, r) for r in orders]
    return out


def post_account_status(ctx, user_id):
    conn, p = ctx["conn"], ctx["body"]
    staff = auth(conn, ctx["token"], "ops")
    status, = require(p, "status")
    if status not in ("active", "suspended"):
        raise ApiError("An account is either active or suspended")
    row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    if not row or row["role"] == "ops":
        raise ApiError("No such account", 404)
    note = str(p.get("reason") or "").strip()
    if status == "suspended" and not note:
        raise ApiError("Say why the account is being suspended")
    conn.execute("UPDATE users SET account_status = ? WHERE id = ?", (status, user_id))
    log_kyc(conn, user_id, status, note or "Account reactivated", staff["name"])
    conn.commit()
    return get_account(ctx, user_id)


def post_orders(ctx):
    conn, p = ctx["conn"], ctx["body"]
    user = auth(conn, ctx["token"], "shipper", "ops")
    require_verified(user, "book_load")
    require(p, "equipment", "service", "commodity", "from_zone", "to_zone", "pickup_address",
            "dropoff_address", "recipient_name", "recipient_phone", "goods", "payment_method")
    if p["payment_method"] not in PAYMENT_METHODS:
        raise ApiError("Unknown payment method")
    if p["payment_method"] == "invoice":
        require_verified(user, "credit_terms")
    extra_stops = [s for s in (p.get("stops") or []) if s.get("node_key")]
    try:
        q = pricing.quote(p["equipment"], p["service"], p["from_zone"], p["to_zone"],
                          p.get("tonnes", 0), p["commodity"], stops=len(extra_stops))
    except (pricing.QuoteError, ValueError) as e:
        raise ApiError(str(e))

    contract = None
    if p.get("contract_ref"):
        contract = conn.execute("SELECT * FROM contracts WHERE ref = ? AND shipper_id = ?",
                                (p["contract_ref"], user["id"])).fetchone()
        if not contract:
            raise ApiError("No contract with that reference on your account", 404)
        if contract["status"] != "active":
            raise ApiError("That contract is %s" % contract["status"])
        remaining = contract["tonnes_committed"] - contract["tonnes_called_off"]
        if q["tonnes"] > remaining + 0.01:
            raise ApiError("Only %.1f t left on contract %s" % (remaining, contract["ref"]))

    ref = db.new_ref()
    # Invoiced customers are billed later; everyone else pays on the wallet
    # prompt, which we mark paid once the collection callback lands.
    payment_status = "invoiced" if p["payment_method"] == "invoice" else "pending"
    cur = conn.execute(
        """INSERT INTO orders (ref, shipper_id, equipment_key, service_key, commodity_key, from_zone, to_zone,
             pickup_address, dropoff_address, recipient_name, recipient_phone, goods, tonnes, billed_tonnes,
             distance_km, eta_minutes, total_ngwee, payout_ngwee, payment_method, payment_status,
             status, scheduled_for, created_at, currency, corridor, is_export, stops_count, contract_id)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,'placed',?,?,?,?,?,?,?)""",
        (ref, user["id"], p["equipment"], p["service"], p["commodity"], p["from_zone"], p["to_zone"],
         p["pickup_address"].strip(), p["dropoff_address"].strip(), p["recipient_name"].strip(),
         p["recipient_phone"].strip(), p["goods"].strip(), q["tonnes"], q["billed_tonnes"], q["distance_km"],
         q["eta_minutes"], q["total_ngwee"], q["partner_payout_ngwee"], p["payment_method"],
         payment_status, p.get("scheduled_for"), db.now(), q["currency"], q["corridor"],
         1 if q["export"] else 0, len(extra_stops), contract["id"] if contract else None),
    )
    order_id = cur.lastrowid
    log_event(conn, order_id, "placed", "Order created by %s" % user["name"], user["name"])
    bind_cover(conn, order_id, p)
    seed_stops(conn, order_id, p, extra_stops)
    seed_documents(conn, order_id, p["commodity"], p["from_zone"], p["to_zone"], p["equipment"])
    if contract:
        conn.execute("UPDATE contracts SET tonnes_called_off = tonnes_called_off + ? WHERE id = ?",
                     (q["tonnes"], contract["id"]))
        log_event(conn, order_id, "placed",
                  "Called off against contract %s" % contract["ref"], user["name"])
    conn.commit()
    row = conn.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()
    return order_json(conn, row, include_timeline=True)


def get_orders(ctx):
    conn = ctx["conn"]
    user = auth(conn, ctx["token"])
    if user["role"] == "shipper":
        rows = conn.execute("SELECT * FROM orders WHERE shipper_id = ? ORDER BY id DESC", (user["id"],)).fetchall()
    elif user["role"] == "driver":
        rows = conn.execute("SELECT * FROM orders WHERE driver_id = ? ORDER BY id DESC", (user["id"],)).fetchall()
    else:
        rows = conn.execute("SELECT * FROM orders ORDER BY id DESC LIMIT 200").fetchall()
    return {"orders": [order_json(conn, r) for r in rows]}


def get_order(ctx, ref):
    conn = ctx["conn"]
    user = auth(conn, ctx["token"])
    row = conn.execute("SELECT * FROM orders WHERE ref = ?", (ref,)).fetchone()
    if not row:
        raise ApiError("No load with that reference", 404)
    if user["role"] == "shipper" and row["shipper_id"] != user["id"]:
        raise ApiError("Not your order", 403)
    if user["role"] == "driver" and row["driver_id"] not in (user["id"], None):
        raise ApiError("Not your job", 403)
    return order_json(conn, row, include_timeline=True)


def get_track(ctx, ref):
    """Public tracking - anyone holding the reference can watch the job, but
    only the fields a site contact needs are exposed. The prefix decides
    whether this is a freight load or a plant hire."""
    conn = ctx["conn"]

    if ref.upper().startswith("HIR-"):
        row = conn.execute("SELECT * FROM hires WHERE ref = ?", (ref,)).fetchone()
        if not row:
            raise ApiError("No hire with that reference", 404)
        h = hire_json(conn, row, include_timeline=True)
        keep = ("ref", "status", "status_label", "plant_name", "site_name", "depot_name",
                "days", "tier", "with_operator", "purpose", "created_at", "timeline")
        out = {k: h.get(k) for k in keep}
        out["kind"] = "hire"
        return out

    row = conn.execute("SELECT * FROM orders WHERE ref = ?", (ref,)).fetchone()
    if not row:
        raise ApiError("No load with that reference", 404)
    o = order_json(conn, row, include_timeline=True)
    keep = ("ref", "status", "status_label", "from_name", "to_name", "equipment_name", "service_name",
            "commodity_name", "tonnes", "eta_minutes", "distance_km", "goods", "created_at",
            "timeline", "driver", "corridor", "crossings", "tracking")
    out = {k: o.get(k) for k in keep}
    out["kind"] = "freight"
    if out.get("driver"):
        out["driver"] = {"name": out["driver"]["name"]}
    # A consignee should see where the load is and whether the paperwork is
    # holding it up, but not the rate or anyone else's contact details.
    out["stops"] = [
        {"seq": s["seq"], "node_name": s["node_name"], "status": s["status"],
         "tonnes": s["tonnes"], "completed_at": s["completed_at"]}
        for s in (o.get("stops") or [])
    ]
    d = o.get("documents") or {}
    out["documents"] = {"total": d.get("total"), "filed": d.get("filed"),
                        "outstanding": d.get("outstanding"), "complete": d.get("complete"),
                        "next_due": (d.get("next_due") or {}).get("name")}
    w = o.get("weights") or {}
    if w.get("loaded_kg"):
        out["weights"] = w
    return out


def post_status(ctx, ref):
    conn, p = ctx["conn"], ctx["body"]
    user = auth(conn, ctx["token"], "driver", "ops", "shipper")
    row = conn.execute("SELECT * FROM orders WHERE ref = ?", (ref,)).fetchone()
    if not row:
        raise ApiError("No load with that reference", 404)
    target = str(p.get("status") or "")
    if target not in FLOW.get(row["status"], []):
        raise ApiError("Cannot go from %s to %s" % (row["status"], target or "nothing"))
    # A shipper may only pull the plug; drivers move the job forward.
    if user["role"] == "shipper":
        if row["shipper_id"] != user["id"] or target != "cancelled":
            raise ApiError("Shippers can only cancel their own orders", 403)
    if user["role"] == "driver" and row["driver_id"] != user["id"]:
        raise ApiError("Not your job", 403)

    stage = STATUS_REQUIRES_DOCS.get(target)
    if stage and target != "cancelled":
        # An export needs its border stack before it leaves; a domestic load
        # has nothing at that stage, so the check simply passes.
        checklist = documents_json(conn, row["id"])["items"]
        held = {d["doc_key"] for d in checklist if d["status"] in ("filed", "waived")}
        outstanding = docs.blocking(
            [dict(d, key=d["doc_key"]) for d in checklist], held, stage)
        if outstanding:
            raise ApiError(
                "%d document%s outstanding before this load can be %s: %s"
                % (len(outstanding), "" if len(outstanding) == 1 else "s",
                   STATUS_LABEL.get(target, target).lower(),
                   ", ".join(d["name"] for d in outstanding[:4])))

    if target == "delivered":
        # Cargo sold by weight does not close without the discharge figure.
        commodity = pricing.COMMODITIES.get(row["commodity_key"], {})
        if (commodity.get("food_grade") or commodity.get("sector") == "mining") \
                and not row["discharged_kg"]:
            raise ApiError("Record the discharge weighbridge weight before closing this load")
        pending = conn.execute(
            "SELECT COUNT(*) FROM order_stops WHERE order_id = ? AND status != 'done'",
            (row["id"],)).fetchone()[0]
        if pending > 1:
            raise ApiError("%d drops on this load are still unsigned" % pending)

    fields = ["status = ?"]
    values = [target]
    if target == "delivered":
        fields.append("payment_status = ?")
        values.append("invoiced" if row["payment_method"] == "invoice" else "paid")
        if p.get("proof_note"):
            fields.append("proof_note = ?")
            values.append(str(p["proof_note"]).strip())
    values.append(row["id"])
    conn.execute("UPDATE orders SET %s WHERE id = ?" % ", ".join(fields), values)
    log_event(conn, row["id"], target, p.get("note"), user["name"])
    if target == "delivered":
        conn.execute(
            "UPDATE order_stops SET status = 'done', completed_at = ? WHERE order_id = ? AND status != 'done'",
            (db.now(), row["id"]))
        # Delivery is what makes the payout real, so it is also the moment the
        # fuel drawn against this load comes back out of it.
        settle(conn, conn.execute("SELECT * FROM orders WHERE id = ?", (row["id"],)).fetchone())
    elif target == "cancelled":
        conn.execute("UPDATE fuel_entitlements SET status = 'void' WHERE order_id = ? AND status = 'open'",
                     (row["id"],))
    conn.commit()
    return order_json(conn, conn.execute("SELECT * FROM orders WHERE id = ?", (row["id"],)).fetchone(), True)


def get_jobs(ctx):
    """The driver job board: unassigned work this driver's vehicle can carry."""
    conn = ctx["conn"]
    user = auth(conn, ctx["token"], "driver")
    require_verified(user, "accept_job")
    v = conn.execute("SELECT * FROM vehicles WHERE driver_id = ?", (user["id"],)).fetchone()
    if not v:
        raise ApiError("Register a vehicle before taking jobs")
    rows = conn.execute(
        "SELECT * FROM orders WHERE driver_id IS NULL AND status = 'placed' AND equipment_key = ? ORDER BY id DESC",
        (v["equipment_key"],),
    ).fetchall()
    return {"jobs": [order_json(conn, r) for r in rows], "vehicle": row_to_dict(v)}


def post_accept(ctx, ref):
    conn = ctx["conn"]
    user = auth(conn, ctx["token"], "driver")
    require_verified(user, "accept_job")
    v = conn.execute("SELECT * FROM vehicles WHERE driver_id = ?", (user["id"],)).fetchone()
    if not v:
        raise ApiError("Register a vehicle before taking jobs")
    # Guard the claim in SQL so two drivers tapping at once cannot both win.
    cur = conn.execute(
        "UPDATE orders SET driver_id = ?, status = 'assigned' WHERE ref = ? AND driver_id IS NULL AND status = 'placed'",
        (user["id"], ref),
    )
    if cur.rowcount == 0:
        raise ApiError("That job has already been taken", 409)
    row = conn.execute("SELECT * FROM orders WHERE ref = ?", (ref,)).fetchone()
    log_event(conn, row["id"], "assigned", "%s accepted the job (%s)" % (user["name"], v["plate"]), user["name"])
    issue_entitlement(conn, row, user["id"])
    conn.commit()
    return order_json(conn, row, True)


def post_assign(ctx, ref):
    conn, p = ctx["conn"], ctx["body"]
    user = auth(conn, ctx["token"], "ops")
    driver_id = p.get("driver_id")
    row = conn.execute("SELECT * FROM orders WHERE ref = ?", (ref,)).fetchone()
    if not row:
        raise ApiError("No load with that reference", 404)
    if row["status"] not in ("placed", "assigned"):
        raise ApiError("This job is already under way")
    driver = conn.execute("SELECT * FROM users WHERE id = ? AND role = 'driver'", (driver_id,)).fetchone()
    if not driver:
        raise ApiError("Unknown driver")
    # A driver can only be sent a job their vehicle can actually carry.
    v = conn.execute("SELECT * FROM vehicles WHERE driver_id = ?", (driver_id,)).fetchone()
    if not v or v["equipment_key"] != row["equipment_key"]:
        raise ApiError(
            "%s runs a %s - this load needs a %s"
            % (driver["name"],
               pricing.EQUIPMENT.get(v["equipment_key"], {}).get("name", "different unit") if v else "no unit",
               pricing.EQUIPMENT[row["equipment_key"]]["name"])
        )
    conn.execute("UPDATE orders SET driver_id = ?, status = 'assigned' WHERE id = ?", (driver_id, row["id"]))
    log_event(conn, row["id"], "assigned", "Dispatched to %s by %s" % (driver["name"], user["name"]), user["name"])
    issue_entitlement(conn, row, driver_id)
    conn.commit()
    return order_json(conn, conn.execute("SELECT * FROM orders WHERE id = ?", (row["id"],)).fetchone(), True)


def get_drivers(ctx):
    conn = ctx["conn"]
    auth(conn, ctx["token"], "ops")
    rows = conn.execute(
        """SELECT u.id, u.name, u.phone, v.equipment_key, v.plate, v.home_zone, v.is_online,
                  (SELECT COUNT(*) FROM orders o WHERE o.driver_id = u.id AND o.status IN ('assigned','at_pickup','in_transit')) AS active_jobs,
                  (SELECT COUNT(*) FROM orders o WHERE o.driver_id = u.id AND o.status = 'delivered') AS completed
           FROM users u LEFT JOIN vehicles v ON v.driver_id = u.id
           WHERE u.role = 'driver' ORDER BY u.name"""
    ).fetchall()
    out = []
    for r in rows:
        d = row_to_dict(r)
        d["equipment_name"] = pricing.EQUIPMENT.get(d["equipment_key"], {}).get("name", "-")
        d["zone_name"] = geo.NODES.get(d["home_zone"], {}).get("name", "-")
        out.append(d)
    return {"drivers": out}


def get_summary(ctx):
    conn = ctx["conn"]
    auth(conn, ctx["token"], "ops")
    day_ago = db.now() - 86400
    one = lambda sql, args=(): conn.execute(sql, args).fetchone()[0]
    delivered = one("SELECT COUNT(*) FROM orders WHERE status = 'delivered'")
    on_time = one(
        "SELECT COUNT(*) FROM orders o WHERE o.status = 'delivered' AND "
        "(SELECT created_at FROM events e WHERE e.order_id = o.id AND e.status='delivered') "
        "<= o.created_at + o.eta_minutes * 60"
    )
    return {
        "open_jobs": one("SELECT COUNT(*) FROM orders WHERE status IN ('placed','assigned','at_pickup','in_transit')"),
        "unassigned": one("SELECT COUNT(*) FROM orders WHERE status = 'placed' AND driver_id IS NULL"),
        "delivered_today": one("SELECT COUNT(*) FROM orders WHERE status='delivered' AND created_at >= ?", (day_ago,)),
        "gmv_ngwee": one("SELECT COALESCE(SUM(total_ngwee),0) FROM orders WHERE status != 'cancelled'"),
        "revenue_ngwee": one("SELECT COALESCE(SUM(total_ngwee - payout_ngwee),0) FROM orders WHERE status != 'cancelled'"),
        "drivers_online": one("SELECT COUNT(*) FROM vehicles WHERE is_online = 1"),
        "on_time_pct": int(round(100.0 * on_time / delivered)) if delivered else 0,
        "tonnes_moved": round(one("SELECT COALESCE(SUM(tonnes),0) FROM orders WHERE status = 'delivered'"), 1),
        "tonne_km": int(one("SELECT COALESCE(SUM(tonnes * distance_km),0) FROM orders WHERE status != 'cancelled'")),
        "hires_open": one("SELECT COUNT(*) FROM hires WHERE status IN ('requested','confirmed','on_site','off_hire')"),
        "hires_pending": one("SELECT COUNT(*) FROM hires WHERE status = 'requested'"),
        "hire_gmv_ngwee": one("SELECT COALESCE(SUM(total_ngwee),0) FROM hires WHERE status != 'cancelled'"),
        "by_sector": {
            r["commodity_key"]: r["n"]
            for r in conn.execute(
                "SELECT commodity_key, COUNT(*) AS n FROM orders WHERE status != 'cancelled' "
                "GROUP BY commodity_key ORDER BY n DESC LIMIT 6"
            ).fetchall()
        },
        "by_status": {
            r["status"]: r["n"]
            for r in conn.execute("SELECT status, COUNT(*) AS n FROM orders GROUP BY status").fetchall()
        },
    }


def get_earnings(ctx):
    conn = ctx["conn"]
    user = auth(conn, ctx["token"], "driver")
    rows = conn.execute(
        "SELECT ref, payout_ngwee, created_at, status FROM orders WHERE driver_id = ? ORDER BY id DESC", (user["id"],)
    ).fetchall()
    paid = sum(r["payout_ngwee"] for r in rows if r["status"] == "delivered")
    pending = sum(r["payout_ngwee"] for r in rows if r["status"] in OPEN_STATUSES)
    # What the settlements actually paid out, after diesel was netted off. The
    # gross above is what the loads earned; this is what reached the carrier.
    net_row = conn.execute(
        "SELECT COALESCE(SUM(net_ngwee),0) AS net, COALESCE(SUM(fuel_deduction_ngwee),0) AS fuelled "
        "FROM settlements WHERE driver_id = ?", (user["id"],)).fetchone()
    fac = facility_for(conn, user["id"])
    return {
        "paid_ngwee": paid,
        "pending_ngwee": pending,
        "paid": pricing.kwacha(paid),
        "pending": pricing.kwacha(pending),
        "net_paid": pricing.kwacha(net_row["net"]),
        "fuel_netted": pricing.kwacha(net_row["fuelled"]),
        "fuel_outstanding": pricing.kwacha(fac["outstanding_ngwee"]),
        "completed": sum(1 for r in rows if r["status"] == "delivered"),
        "jobs": [dict(row_to_dict(r), payout=pricing.kwacha(r["payout_ngwee"])) for r in rows[:25]],
    }


def post_online(ctx):
    conn = ctx["conn"]
    user = auth(conn, ctx["token"], "driver")
    online = 1 if ctx["body"].get("online") else 0
    conn.execute("UPDATE vehicles SET is_online = ? WHERE driver_id = ?", (online, user["id"]))
    conn.commit()
    return {"online": bool(online)}


def post_vehicle(ctx):
    conn, p = ctx["conn"], ctx["body"]
    user = auth(conn, ctx["token"], "driver")
    equipment_key, plate, home_zone = require(p, "equipment_key", "plate", "home_zone")
    if equipment_key not in pricing.EQUIPMENT or home_zone not in geo.NODES:
        raise ApiError("Unknown equipment class or location")
    conn.execute(
        "UPDATE vehicles SET equipment_key = ?, plate = ?, home_zone = ? WHERE driver_id = ?",
        (equipment_key, plate.upper(), home_zone, user["id"]),
    )
    conn.commit()
    return {"ok": True}


# --- plant hire -------------------------------------------------------------

def hire_json(conn, row, include_timeline=False):
    h = row_to_dict(row)
    machine = rental.PLANT.get(h["plant_key"], {})
    h["plant_name"] = machine.get("name", h["plant_key"])
    h["category"] = machine.get("category", "support")
    h["status_label"] = HIRE_STATUS_LABEL.get(h["status"], h["status"])
    h["site_name"] = geo.NODES[h["site_zone"]]["name"]
    h["depot_name"] = geo.NODES[h["depot_zone"]]["name"]
    h["total"] = pricing.kwacha(h["total_ngwee"])
    h["payment_label"] = PAYMENT_METHODS.get(h["payment_method"], h["payment_method"])
    h["with_operator"] = bool(h["with_operator"])
    h["with_fuel"] = bool(h["with_fuel"])
    h["with_waiver"] = bool(h["with_waiver"])
    if include_timeline:
        rows = conn.execute(
            "SELECT status, note, actor, created_at FROM hire_events WHERE hire_id = ? ORDER BY id",
            (h["id"],),
        ).fetchall()
        h["timeline"] = [
            dict(row_to_dict(r), label=HIRE_STATUS_LABEL.get(r["status"], r["status"])) for r in rows
        ]
    return h


def log_hire_event(conn, hire_id, status, note, actor):
    conn.execute(
        "INSERT INTO hire_events (hire_id, status, note, actor, created_at) VALUES (?,?,?,?,?)",
        (hire_id, status, note, actor, db.now()),
    )


def post_hire_quote(ctx):
    p = ctx["body"]
    require(p, "plant", "site")
    try:
        q = rental.quote(
            p["plant"], p["site"], p.get("days", 1),
            with_operator=bool(p.get("with_operator", True)),
            with_fuel=bool(p.get("with_fuel", False)),
            with_waiver=bool(p.get("with_waiver", True)),
        )
    except (rental.HireError, ValueError) as e:
        raise ApiError(str(e))
    q["total"] = pricing.kwacha(q["total_ngwee"])
    q["net"] = pricing.kwacha(q["net_ngwee"])
    q["vat"] = pricing.kwacha(q["vat_ngwee"])
    q["effective_day"] = pricing.kwacha(q["effective_day_ngwee"])
    for line in q["lines"]:
        line["amount"] = pricing.kwacha(line["ngwee"])
    return q


def post_hires(ctx):
    conn, p = ctx["conn"], ctx["body"]
    user = auth(conn, ctx["token"], "shipper", "ops")
    require_verified(user, "hire_plant")
    require(p, "plant", "site", "site_address", "site_contact", "site_phone", "purpose", "payment_method")
    if p["payment_method"] not in PAYMENT_METHODS:
        raise ApiError("Unknown payment method")
    try:
        q = rental.quote(
            p["plant"], p["site"], p.get("days", 1),
            with_operator=bool(p.get("with_operator", True)),
            with_fuel=bool(p.get("with_fuel", False)),
            with_waiver=bool(p.get("with_waiver", True)),
        )
    except (rental.HireError, ValueError) as e:
        raise ApiError(str(e))

    ref = db.new_ref("HIR")
    payment_status = "invoiced" if p["payment_method"] == "invoice" else "pending"
    cur = conn.execute(
        """INSERT INTO hires (ref, hirer_id, plant_key, site_zone, site_address, site_contact,
             site_phone, purpose, days, tier, depot_zone, float_km, with_operator, with_fuel,
             with_waiver, total_ngwee, payment_method, payment_status, status, start_on, created_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,'requested',?,?)""",
        (ref, user["id"], q["plant"], q["site"], p["site_address"].strip(), p["site_contact"].strip(),
         p["site_phone"].strip(), p["purpose"].strip(), q["days"], q["tier"], q["depot"], q["float_km"],
         int(q["with_operator"]), int(q["with_fuel"]), int(q["with_waiver"]), q["total_ngwee"],
         p["payment_method"], payment_status, p.get("start_on"), db.now()),
    )
    log_hire_event(conn, cur.lastrowid, "requested", "Hire requested by %s" % user["name"], user["name"])
    conn.commit()
    return hire_json(conn, conn.execute("SELECT * FROM hires WHERE id = ?", (cur.lastrowid,)).fetchone(), True)


def get_hires(ctx):
    conn = ctx["conn"]
    user = auth(conn, ctx["token"])
    if user["role"] == "shipper":
        rows = conn.execute("SELECT * FROM hires WHERE hirer_id = ? ORDER BY id DESC", (user["id"],)).fetchall()
    elif user["role"] == "ops":
        rows = conn.execute("SELECT * FROM hires ORDER BY id DESC LIMIT 200").fetchall()
    else:
        raise ApiError("Plant hire is not part of the carrier console", 403)
    return {"hires": [hire_json(conn, r) for r in rows]}


def get_hire(ctx, ref):
    conn = ctx["conn"]
    user = auth(conn, ctx["token"], "shipper", "ops")
    row = conn.execute("SELECT * FROM hires WHERE ref = ?", (ref,)).fetchone()
    if not row:
        raise ApiError("No hire with that reference", 404)
    if user["role"] == "shipper" and row["hirer_id"] != user["id"]:
        raise ApiError("Not your hire", 403)
    return hire_json(conn, row, True)


def post_hire_status(ctx, ref):
    conn, p = ctx["conn"], ctx["body"]
    user = auth(conn, ctx["token"], "shipper", "ops")
    row = conn.execute("SELECT * FROM hires WHERE ref = ?", (ref,)).fetchone()
    if not row:
        raise ApiError("No hire with that reference", 404)
    target = str(p.get("status") or "")
    if target not in HIRE_FLOW.get(row["status"], []):
        raise ApiError("Cannot go from %s to %s" % (row["status"], target or "nothing"))
    # Customers may end a hire or pull out; only control moves it forward.
    if user["role"] == "shipper":
        if row["hirer_id"] != user["id"] or target not in ("cancelled", "off_hire"):
            raise ApiError("You can end or cancel your own hire, nothing else", 403)

    fields, values = ["status = ?"], [target]
    if target == "returned":
        fields.append("payment_status = ?")
        values.append("invoiced" if row["payment_method"] == "invoice" else "paid")
        if p.get("meter_note"):
            fields.append("meter_note = ?")
            values.append(str(p["meter_note"]).strip())
    values.append(row["id"])
    conn.execute("UPDATE hires SET %s WHERE id = ?" % ", ".join(fields), values)
    log_hire_event(conn, row["id"], target, p.get("note"), user["name"])
    conn.commit()
    return hire_json(conn, conn.execute("SELECT * FROM hires WHERE id = ?", (row["id"],)).fetchone(), True)


# --- router ----------------------------------------------------------------

# --- carrier bundle: fuel credit and cover ---------------------------------
#
# Musanga never advances cash. It extends diesel against a load it has already
# assigned, and nets the balance off the settlement it is already holding. See
# musanga/fuel.py for why each rule is shaped the way it is.

def facility_for(conn, driver_id, create=True):
    """The carrier's fuel facility, opened on first use."""
    row = conn.execute("SELECT * FROM fuel_facilities WHERE driver_id = ?", (driver_id,)).fetchone()
    if row or not create:
        return row
    conn.execute(
        "INSERT INTO fuel_facilities (driver_id, limit_ngwee, outstanding_ngwee, "
        "completed_loads, avg_weekly_payout_ngwee, created_at) VALUES (?,0,0,0,0,?)",
        (driver_id, db.now()),
    )
    return conn.execute("SELECT * FROM fuel_facilities WHERE driver_id = ?", (driver_id,)).fetchone()


def rebase_limit(conn, driver_id, starter_entitlement_ngwee):
    """Re-size the facility from what this carrier has actually earned here.

    Cheap enough to run whenever a load is assigned, which keeps the limit
    honest without a scheduled job.
    """
    fac = facility_for(conn, driver_id)
    row = conn.execute(
        "SELECT COUNT(*) AS n, COALESCE(SUM(gross_ngwee),0) AS gross, "
        "MIN(settled_at) AS first_at FROM settlements WHERE driver_id = ?",
        (driver_id,),
    ).fetchone()
    completed = int(row["n"] or 0)
    weeks = 1.0
    if row["first_at"]:
        weeks = max(1.0, (db.now() - int(row["first_at"])) / 604800.0)
    avg_weekly = int((row["gross"] or 0) / weeks)

    limit = fuel.limit_for(completed, avg_weekly, starter_entitlement_ngwee)
    # The limit can never be cut below money already drawn - that would strand a
    # truck mid-trip for a debt we already approved.
    limit = max(limit, int(fac["outstanding_ngwee"]))
    conn.execute(
        "UPDATE fuel_facilities SET limit_ngwee = ?, completed_loads = ?, "
        "avg_weekly_payout_ngwee = ?, rebased_at = ? WHERE driver_id = ?",
        (limit, completed, avg_weekly, db.now(), driver_id),
    )
    return conn.execute("SELECT * FROM fuel_facilities WHERE driver_id = ?", (driver_id,)).fetchone()


def issue_entitlement(conn, order_row, driver_id):
    """Issue this load's diesel when a carrier takes it.

    Computed from the corridor distance and the equipment class, which is the
    control a generic fuel card cannot have: it does not know the load.
    """
    existing = conn.execute(
        "SELECT * FROM fuel_entitlements WHERE order_id = ?", (order_row["id"],)).fetchone()
    if existing:
        return existing
    try:
        ent = fuel.entitlement(order_row["equipment_key"], order_row["distance_km"])
    except fuel.FuelError:
        return None  # no burn rate on file: no entitlement, load still runs

    rebase_limit(conn, driver_id, ent["value_ngwee"])
    conn.execute(
        "INSERT INTO fuel_entitlements (order_id, driver_id, litres, litres_drawn, "
        "price_ngwee_per_litre, status, created_at) VALUES (?,?,?,0,?,'open',?)",
        (order_row["id"], driver_id, ent["litres"], ent["price_ngwee_per_litre"], db.now()),
    )
    return conn.execute(
        "SELECT * FROM fuel_entitlements WHERE order_id = ?", (order_row["id"],)).fetchone()


def facility_json(fac, entitlements=None):
    f = row_to_dict(fac)
    f["available_ngwee"] = fuel.available(fac["limit_ngwee"], fac["outstanding_ngwee"])
    f["limit"] = pricing.kwacha(fac["limit_ngwee"])
    f["outstanding"] = pricing.kwacha(fac["outstanding_ngwee"])
    f["available"] = pricing.kwacha(f["available_ngwee"])
    if entitlements is not None:
        f["entitlements"] = entitlements
    return f


def entitlement_json(conn, row):
    e = row_to_dict(row)
    e["litres_remaining"] = int(row["litres"]) - int(row["litres_drawn"])
    e["value_ngwee"] = int(row["litres"]) * int(row["price_ngwee_per_litre"])
    e["value"] = pricing.kwacha(e["value_ngwee"])
    o = conn.execute("SELECT ref, from_zone, to_zone, equipment_key, distance_km "
                     "FROM orders WHERE id = ?", (row["order_id"],)).fetchone()
    if o:
        e["order_ref"] = o["ref"]
        e["from_name"] = geo.NODES[o["from_zone"]]["name"]
        e["to_name"] = geo.NODES[o["to_zone"]]["name"]
        e["distance_km"] = o["distance_km"]
    return e


def get_fuel(ctx):
    """The carrier's own facility, with every open entitlement."""
    conn = ctx["conn"]
    user = auth(conn, ctx["token"], "driver")
    fac = facility_for(conn, user["id"])
    rows = conn.execute(
        "SELECT * FROM fuel_entitlements WHERE driver_id = ? AND status = 'open' ORDER BY id DESC",
        (user["id"],),
    ).fetchall()
    return {"facility": facility_json(fac, [entitlement_json(conn, r) for r in rows]),
            "diesel_ngwee_per_litre": fuel.DIESEL_NGWEE_PER_LITRE}


def post_fuel_draw(ctx, ref):
    """Draw diesel against one load, at the pump.

    Two ceilings bind and both are checked here: the load's entitlement and the
    facility's headroom.
    """
    conn, p = ctx["conn"], ctx["body"]
    user = auth(conn, ctx["token"], "driver", "ops")
    require_verified(user, "draw_fuel")
    order = conn.execute("SELECT * FROM orders WHERE ref = ?", (ref,)).fetchone()
    if not order:
        raise ApiError("No load with that reference", 404)
    if user["role"] == "driver" and order["driver_id"] != user["id"]:
        raise ApiError("Not your job", 403)

    ent = conn.execute("SELECT * FROM fuel_entitlements WHERE order_id = ?", (order["id"],)).fetchone()
    if not ent:
        raise ApiError("This load has no fuel entitlement", 404)
    if ent["status"] != "open":
        raise ApiError("That entitlement is %s" % ent["status"])

    require(p, "litres")
    try:
        litres = int(p["litres"])
    except (TypeError, ValueError):
        raise ApiError("Litres must be a whole number")

    fac = facility_for(conn, ent["driver_id"])
    remaining = int(ent["litres"]) - int(ent["litres_drawn"])
    try:
        draw = fuel.check_draw(litres, ent["price_ngwee_per_litre"], remaining,
                               fac["limit_ngwee"], fac["outstanding_ngwee"])
    except fuel.FuelError as e:
        raise ApiError(str(e))

    conn.execute(
        "INSERT INTO fuel_draws (entitlement_id, driver_id, litres, price_ngwee_per_litre, "
        "value_ngwee, station, drawn_at) VALUES (?,?,?,?,?,?,?)",
        (ent["id"], ent["driver_id"], litres, ent["price_ngwee_per_litre"],
         draw["value_ngwee"], (p.get("station") or None), db.now()),
    )
    conn.execute("UPDATE fuel_entitlements SET litres_drawn = litres_drawn + ? WHERE id = ?",
                 (litres, ent["id"]))
    conn.execute("UPDATE fuel_facilities SET outstanding_ngwee = outstanding_ngwee + ? WHERE driver_id = ?",
                 (draw["value_ngwee"], ent["driver_id"]))
    log_event(conn, order["id"], order["status"],
              "Fuel: %d litres (K%.2f)" % (litres, draw["value_ngwee"] / 100.0), user["name"])
    conn.commit()

    fac = facility_for(conn, ent["driver_id"])
    ent = conn.execute("SELECT * FROM fuel_entitlements WHERE id = ?", (ent["id"],)).fetchone()
    return {"draw": {"litres": litres, "value_ngwee": draw["value_ngwee"],
                     "value": pricing.kwacha(draw["value_ngwee"])},
            "entitlement": entitlement_json(conn, ent),
            "facility": facility_json(fac)}


def settle(conn, order_row):
    """Close out a delivered load: net the fuel off, record what was paid.

    Idempotent - a load already settled returns its existing settlement.
    """
    existing = conn.execute("SELECT * FROM settlements WHERE order_id = ?",
                            (order_row["id"],)).fetchone()
    if existing:
        return row_to_dict(existing)
    driver_id = order_row["driver_id"]
    if not driver_id:
        return None

    fac = facility_for(conn, driver_id)
    gross = int(order_row["payout_ngwee"])
    n = fuel.netting(fac["outstanding_ngwee"], gross)

    conn.execute(
        "INSERT INTO settlements (order_id, driver_id, gross_ngwee, fuel_deduction_ngwee, "
        "net_ngwee, settled_at) VALUES (?,?,?,?,?,?)",
        (order_row["id"], driver_id, gross, n["deduction_ngwee"],
         n["carrier_receives_ngwee"], db.now()),
    )
    conn.execute("UPDATE fuel_facilities SET outstanding_ngwee = ?, completed_loads = completed_loads + 1 "
                 "WHERE driver_id = ?", (n["outstanding_after_ngwee"], driver_id))
    conn.execute("UPDATE fuel_entitlements SET status = 'closed' WHERE order_id = ? AND status = 'open'",
                 (order_row["id"],))
    if n["deduction_ngwee"]:
        log_event(conn, order_row["id"], "delivered",
                  "Fuel netted off settlement: K%.2f" % (n["deduction_ngwee"] / 100.0), "Musanga")
    return row_to_dict(conn.execute("SELECT * FROM settlements WHERE order_id = ?",
                                    (order_row["id"],)).fetchone())


def get_settlements(ctx):
    """What the carrier has been paid, and what was netted off."""
    conn = ctx["conn"]
    user = auth(conn, ctx["token"], "driver")
    rows = conn.execute(
        "SELECT s.*, o.ref FROM settlements s JOIN orders o ON o.id = s.order_id "
        "WHERE s.driver_id = ? ORDER BY s.id DESC", (user["id"],)).fetchall()
    out = []
    for r in rows:
        d = row_to_dict(r)
        d["gross"] = pricing.kwacha(r["gross_ngwee"])
        d["fuel_deduction"] = pricing.kwacha(r["fuel_deduction_ngwee"])
        d["net"] = pricing.kwacha(r["net_ngwee"])
        out.append(d)
    total_net = sum(r["net_ngwee"] for r in rows)
    total_fuel = sum(r["fuel_deduction_ngwee"] for r in rows)
    return {"settlements": out,
            "total_net": pricing.kwacha(total_net),
            "total_fuel": pricing.kwacha(total_fuel)}


def bind_cover(conn, order_id, payload):
    """Place goods-in-transit cover on a load, if the shipper declared a value.

    Musanga is the agent, not the underwriter: the row records what the premium
    is and what we are paid to place it. It stays 'quoted' until an insurer
    confirms - nothing here binds an insurer.
    """
    declared = payload.get("declared_value")
    if declared in (None, "", 0):
        return None
    try:
        declared_ngwee = int(round(float(declared) * 100))
    except (TypeError, ValueError):
        raise ApiError("Declared value must be a number in kwacha")
    try:
        q = insurance.quote(payload["commodity"], declared_ngwee, payload.get("to_zone"))
    except insurance.InsuranceError as e:
        raise ApiError(str(e))
    conn.execute(
        "INSERT INTO insurance_policies (order_id, commodity_key, declared_value_ngwee, rate_bp, "
        "premium_ngwee, commission_ngwee, status, created_at) VALUES (?,?,?,?,?,?,'quoted',?)",
        (order_id, q["commodity_key"], q["declared_value_ngwee"], q["rate_bp"],
         q["premium_ngwee"], q["commission_ngwee"], db.now()),
    )
    log_event(conn, order_id, "placed",
              "Goods-in-transit cover placed: %s declared, premium %s"
              % (pricing.kwacha(q["declared_value_ngwee"]), pricing.kwacha(q["premium_ngwee"])),
              "Musanga")
    return q


def post_insurance_quote(ctx):
    """Price goods-in-transit cover. Musanga places it; the insurer carries it."""
    p = ctx["body"]
    require(p, "commodity", "declared_value")
    try:
        declared = int(round(float(p["declared_value"]) * 100))
    except (TypeError, ValueError):
        raise ApiError("Declared value must be a number in kwacha")
    try:
        q = insurance.quote(str(p["commodity"]), declared, p.get("to_zone"))
    except insurance.InsuranceError as e:
        raise ApiError(str(e))
    q["premium"] = pricing.kwacha(q["premium_ngwee"])
    q["commission"] = pricing.kwacha(q["commission_ngwee"])
    q["rate_pct"] = round(q["rate_bp"] / 100.0, 2)
    return q


# --- multi-drop ------------------------------------------------------------
# Fertiliser out of a plant and grain into a mill are rarely one point to one
# point. A load is a sequence of drops, the last of which is the destination,
# and each drop carries its own tonnage, receipt and weighbridge ticket.

def seed_stops(conn, order_id, p, extra_stops):
    """Write the drop sequence. The booking's own destination is always the
    final stop, so a single-drop load and a five-drop run are the same shape."""
    total_t = float(p.get("tonnes") or 0)
    dropped = 0.0
    for s in extra_stops:
        try:
            dropped += float(s.get("tonnes") or 0)
        except (TypeError, ValueError):
            raise ApiError("Tonnage at each drop must be a number")
    if dropped > total_t + 0.01:
        raise ApiError("The drops add up to %.1f t, more than the %.1f t on the load"
                       % (dropped, total_t))

    seq = 1
    for s in extra_stops:
        if s["node_key"] not in geo.NODES:
            raise ApiError("Unknown drop location: %s" % s["node_key"])
        conn.execute(
            """INSERT INTO order_stops (order_id, seq, node_key, address, recipient_name,
                 recipient_phone, tonnes) VALUES (?,?,?,?,?,?,?)""",
            (order_id, seq, s["node_key"], str(s.get("address") or "").strip(),
             str(s.get("recipient_name") or "").strip(), str(s.get("recipient_phone") or "").strip(),
             float(s.get("tonnes") or 0)))
        seq += 1
    conn.execute(
        """INSERT INTO order_stops (order_id, seq, node_key, address, recipient_name,
             recipient_phone, tonnes) VALUES (?,?,?,?,?,?,?)""",
        (order_id, seq, p["to_zone"], p["dropoff_address"].strip(), p["recipient_name"].strip(),
         p["recipient_phone"].strip(), round(total_t - dropped, 2)))


def stops_json(conn, order_id):
    rows = conn.execute("SELECT * FROM order_stops WHERE order_id = ? ORDER BY seq",
                        (order_id,)).fetchall()
    out = []
    for r in rows:
        s = row_to_dict(r)
        s["node_name"] = geo.NODES.get(s["node_key"], {}).get("name", s["node_key"])
        out.append(s)
    return out


def post_stop_done(ctx, ref, seq):
    """Sign off one drop. The load only closes when the last one is signed."""
    conn, p = ctx["conn"], ctx["body"]
    user = auth(conn, ctx["token"], "driver", "ops")
    row = order_or_404(conn, ref)
    if user["role"] == "driver" and row["driver_id"] != user["id"]:
        raise ApiError("Not your job", 403)
    stop = conn.execute("SELECT * FROM order_stops WHERE order_id = ? AND seq = ?",
                        (row["id"], int(seq))).fetchone()
    if not stop:
        raise ApiError("No such drop on this load", 404)
    if stop["status"] == "done":
        raise ApiError("That drop is already signed off")

    conn.execute(
        "UPDATE order_stops SET status = 'done', proof_note = ?, discharged_kg = ?, completed_at = ? WHERE id = ?",
        (str(p.get("proof_note") or "").strip() or None,
         int(p["discharged_kg"]) if p.get("discharged_kg") else None, db.now(), stop["id"]))
    log_event(conn, row["id"], row["status"],
              "Drop %s of %s signed at %s" % (seq, row["stops_count"] + 1,
                                              geo.NODES.get(stop["node_key"], {}).get("name", "site")),
              user["name"])
    conn.commit()
    return order_json(conn, order_or_404(conn, ref), include_timeline=True)


# --- documents -------------------------------------------------------------
# The checklist is derived from the lane at booking and then lives with the
# load, so what is outstanding is a query, not a phone call.

def seed_documents(conn, order_id, commodity_key, from_key, to_key, equipment_key):
    for d in docs.required_for(commodity_key, from_key, to_key, equipment_key):
        conn.execute(
            """INSERT OR IGNORE INTO order_documents (order_id, doc_key, name, owner, stage,
                 mandatory, note) VALUES (?,?,?,?,?,?,?)""",
            (order_id, d["key"], d["name"], d["owner"], d["stage"],
             1 if d["mandatory"] else 0, d.get("note") or None))


def documents_json(conn, order_id):
    rows = conn.execute(
        "SELECT * FROM order_documents WHERE order_id = ? ORDER BY id", (order_id,)).fetchall()
    items = []
    for r in rows:
        d = row_to_dict(r)
        d["stage_label"] = docs.STAGE_LABEL.get(d["stage"], d["stage"])
        d["owner_label"] = docs.OWNERS.get(d["owner"], d["owner"])
        items.append(d)
    items.sort(key=lambda d: docs.STAGES.index(d["stage"]))
    filed = [d for d in items if d["status"] == "filed"]
    outstanding = [d for d in items if d["status"] != "filed" and d["mandatory"]]
    return {
        "items": items,
        "total": len(items),
        "filed": len(filed),
        "outstanding": len(outstanding),
        "complete": not outstanding,
        "next_due": outstanding[0] if outstanding else None,
    }


def post_document(ctx, ref):
    """File a document against a load. We record the reference and who filed
    it rather than storing the paper: the registry is what unblocks the truck,
    and the paper lives with the party that issued it."""
    conn, p = ctx["conn"], ctx["body"]
    user = auth(conn, ctx["token"], "shipper", "driver", "ops")
    row = order_or_404(conn, ref)
    guard_order_access(user, row)
    require(p, "doc_key")
    doc = conn.execute("SELECT * FROM order_documents WHERE order_id = ? AND doc_key = ?",
                       (row["id"], p["doc_key"])).fetchone()
    if not doc:
        raise ApiError("That document is not on this load's checklist", 404)

    status = p.get("status") or "filed"
    if status not in ("filed", "outstanding", "waived"):
        raise ApiError("Unknown document status")
    if status == "waived" and user["role"] != "ops":
        raise ApiError("Only Musanga operations can waive a document", 403)

    conn.execute(
        """UPDATE order_documents SET status = ?, reference = ?, filed_by = ?, filed_at = ?,
             expires_on = ? WHERE id = ?""",
        (status, str(p.get("reference") or "").strip() or None, user["name"],
         db.now() if status != "outstanding" else None, p.get("expires_on"), doc["id"]))
    log_event(conn, row["id"], row["status"],
              "%s: %s" % (doc["name"], "filed" if status == "filed" else status), user["name"])
    conn.commit()
    return documents_json(conn, row["id"])


# --- weights ---------------------------------------------------------------
# Grain and concentrate are sold on weight, and the gap between the loading
# weighbridge and the discharge weighbridge is the number both sides argue
# about. Recording both makes the variance a fact instead of an argument.

def weights_json(o):
    loaded, discharged = o.get("loaded_kg"), o.get("discharged_kg")
    out = {"loaded_kg": loaded, "discharged_kg": discharged,
           "tolerance_pct": o.get("tolerance_pct") or 0.5}
    if loaded and discharged:
        variance = discharged - loaded
        pct = (variance / float(loaded)) * 100.0
        out["variance_kg"] = variance
        out["variance_pct"] = round(pct, 3)
        out["within_tolerance"] = abs(pct) <= out["tolerance_pct"]
    return out


def post_weights(ctx, ref):
    conn, p = ctx["conn"], ctx["body"]
    user = auth(conn, ctx["token"], "driver", "ops", "shipper")
    row = order_or_404(conn, ref)
    guard_order_access(user, row)

    fields, values, notes = [], [], []
    for key, label in (("loaded_kg", "Loaded"), ("discharged_kg", "Discharged")):
        if p.get(key) in (None, ""):
            continue
        try:
            kg = int(p[key])
        except (TypeError, ValueError):
            raise ApiError("%s weight must be a whole number of kilograms" % label)
        if kg <= 0:
            raise ApiError("%s weight must be more than zero" % label)
        fields.append("%s = ?" % key)
        values.append(kg)
        notes.append("%s %s kg" % (label.lower(), format(kg, ",")))
    if p.get("tolerance_pct") not in (None, ""):
        fields.append("tolerance_pct = ?")
        values.append(float(p["tolerance_pct"]))
    if not fields:
        raise ApiError("Send a loading or discharge weight")

    values.append(row["id"])
    conn.execute("UPDATE orders SET %s WHERE id = ?" % ", ".join(fields), values)
    row = order_or_404(conn, ref)
    w = weights_json(row_to_dict(row))
    if w.get("variance_kg") is not None:
        conn.execute("UPDATE orders SET variance_kg = ? WHERE id = ?", (w["variance_kg"], row["id"]))
        notes.append("variance %s kg (%.2f%%)" % (format(w["variance_kg"], ","), w["variance_pct"]))
        if not w["within_tolerance"]:
            notes.append("OUTSIDE the %.2f%% tolerance" % w["tolerance_pct"])
    log_event(conn, row["id"], row["status"], "Weighbridge: " + ", ".join(notes), user["name"])
    conn.commit()
    return order_json(conn, order_or_404(conn, ref), include_timeline=True)


# --- tracking --------------------------------------------------------------
# Regional lanes run for days across countries where a telematics feed is not
# a given, so position is whatever the platform can get: a driver ping with
# coordinates, or a named point on the corridor. Both produce the same thing -
# distance covered, distance left, and an ETA that moves.

def tracking_json(conn, o):
    rows = conn.execute(
        "SELECT * FROM order_positions WHERE order_id = ? ORDER BY id DESC LIMIT 40",
        (o["id"],)).fetchall()
    pings = [row_to_dict(r) for r in rows]
    out = {"pings": pings, "last": pings[0] if pings else None}
    try:
        out["route"] = [
            {"key": k, "name": geo.NODES[k]["name"], "lat": geo.NODES[k]["lat"],
             "lng": geo.NODES[k]["lng"], "kind": geo.NODES[k]["kind"],
             "country": geo.NODES[k]["country"]}
            for k in geo.route_nodes(o["from_zone"], o["to_zone"])
        ]
    except (ValueError, KeyError):
        out["route"] = []
    if pings:
        last = pings[0]
        out["km_done"] = last.get("km_done")
        out["km_left"] = last.get("km_left")
        if last.get("km_left") is not None:
            hours = last["km_left"] / pricing.AVG_MOVING_KPH / (pricing.DRIVING_HOURS_PER_DAY / 24.0)
            out["eta_at"] = int(last["created_at"] + hours * 3600)
        out["progress_pct"] = round(100.0 * (last.get("km_done") or 0) / o["distance_km"], 1) \
            if o["distance_km"] else 0
    return out


def _nearest_node(lat, lng):
    best, best_km = None, None
    for key, n in geo.NODES.items():
        km = geo.haversine_km(lat, lng, n["lat"], n["lng"])
        if best_km is None or km < best_km:
            best, best_km = key, km
    return best, best_km


def post_position(ctx, ref):
    """A position ping. Coordinates if the driver's phone has them, otherwise
    the nearest named point on the corridor, which is what a phone call gives
    you at Nakonde with no signal."""
    conn, p = ctx["conn"], ctx["body"]
    user = auth(conn, ctx["token"], "driver", "ops")
    row = order_or_404(conn, ref)
    if user["role"] == "driver" and row["driver_id"] != user["id"]:
        raise ApiError("Not your job", 403)
    if row["status"] not in OPEN_STATUSES:
        raise ApiError("This load is not running")

    node_key = p.get("node_key")
    if node_key:
        n = geo.NODES.get(node_key)
        if not n:
            raise ApiError("Unknown location")
        lat, lng, place = n["lat"], n["lng"], n["name"]
    else:
        try:
            lat, lng = float(p["lat"]), float(p["lng"])
        except (KeyError, TypeError, ValueError):
            raise ApiError("Send a node_key, or lat and lng")
        node_key, _ = _nearest_node(lat, lng)
        place = str(p.get("place") or "").strip() or ("near %s" % geo.NODES[node_key]["name"])

    # Progress is measured along the corridor, not as the crow flies: what is
    # left to drive is what is left on the road.
    try:
        # Standing on the destination is nought kilometres away, not the
        # intra-city minimum a quote would charge for the same pair.
        km_left = 0.0 if node_key == row["to_zone"] else geo.route_km(node_key, row["to_zone"])
    except ValueError:
        km_left = None
    km_done = max(0.0, row["distance_km"] - km_left) if km_left is not None else None

    conn.execute(
        """INSERT INTO order_positions (order_id, lat, lng, node_key, place, km_done, km_left,
             source, note, created_at) VALUES (?,?,?,?,?,?,?,?,?,?)""",
        (row["id"], lat, lng, node_key, place, km_done, km_left,
         p.get("source") or ("ops" if user["role"] == "ops" else "driver"),
         str(p.get("note") or "").strip() or None, db.now()))
    conn.execute("UPDATE orders SET last_lat = ?, last_lng = ?, last_place = ?, last_ping_at = ? WHERE id = ?",
                 (lat, lng, place, db.now(), row["id"]))
    conn.commit()
    return order_json(conn, order_or_404(conn, ref), include_timeline=True)


# --- contracts -------------------------------------------------------------
# A contract rate is not a discount, it is committed tonnage at an agreed rate
# over a period, drawn down load by load. Without that, nobody can answer how
# much of this month's allocation is left.

def contract_json(conn, row):
    c = row_to_dict(row)
    c["commodity_name"] = pricing.COMMODITIES.get(c["commodity_key"], {}).get("name", c["commodity_key"])
    c["equipment_name"] = pricing.EQUIPMENT.get(c["equipment_key"], {}).get("name", c["equipment_key"])
    c["from_name"] = geo.NODES.get(c["from_zone"], {}).get("name", c["from_zone"])
    c["to_name"] = geo.NODES.get(c["to_zone"], {}).get("name", c["to_zone"])
    c["tonnes_remaining"] = round(c["tonnes_committed"] - c["tonnes_called_off"], 2)
    c["used_pct"] = round(100.0 * c["tonnes_called_off"] / c["tonnes_committed"], 1) \
        if c["tonnes_committed"] else 0
    c["rate"] = pricing.money(c["rate_ngwee_per_tonne"], c["currency"])
    c["value"] = pricing.money(int(c["rate_ngwee_per_tonne"] * c["tonnes_committed"]), c["currency"])
    c["loads"] = conn.execute("SELECT COUNT(*) FROM orders WHERE contract_id = ?", (c["id"],)).fetchone()[0]
    return c


def get_contracts(ctx):
    conn = ctx["conn"]
    user = auth(conn, ctx["token"])
    if user["role"] == "shipper":
        rows = conn.execute("SELECT * FROM contracts WHERE shipper_id = ? ORDER BY id DESC",
                            (user["id"],)).fetchall()
    elif user["role"] == "ops":
        rows = conn.execute("SELECT * FROM contracts ORDER BY id DESC LIMIT 200").fetchall()
    else:
        rows = []
    return {"contracts": [contract_json(conn, r) for r in rows]}


def post_contracts(ctx):
    conn, p = ctx["conn"], ctx["body"]
    user = auth(conn, ctx["token"], "shipper", "ops")
    require(p, "name", "commodity", "equipment", "from_zone", "to_zone", "tonnes_committed")
    shipper_id = user["id"]
    if user["role"] == "ops" and p.get("shipper_id"):
        shipper_id = int(p["shipper_id"])

    try:
        tonnes = float(p["tonnes_committed"])
    except (TypeError, ValueError):
        raise ApiError("Committed tonnage must be a number")
    if tonnes <= 0:
        raise ApiError("Committed tonnage must be more than zero")

    # The contract rate is the platform's own rate for the lane at contract
    # terms, so a shipper cannot be quoted one number and billed another.
    try:
        q = pricing.quote(p["equipment"], "contract", p["from_zone"], p["to_zone"],
                          p.get("tonnes_per_load") or pricing.EQUIPMENT[p["equipment"]]["payload_t"],
                          p["commodity"])
    except (pricing.QuoteError, ValueError, KeyError) as e:
        raise ApiError(str(e))
    rate_per_tonne = int(round(q["net_ngwee"] / q["billed_tonnes"]))

    starts = int(p.get("starts_on") or db.now())
    ends = int(p.get("ends_on") or (starts + 90 * 86400))
    if ends <= starts:
        raise ApiError("The contract must end after it starts")

    ref = db.new_ref("CTR")
    cur = conn.execute(
        """INSERT INTO contracts (ref, shipper_id, name, commodity_key, equipment_key, from_zone,
             to_zone, tonnes_committed, rate_ngwee_per_tonne, currency, tolerance_pct,
             starts_on, ends_on, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (ref, shipper_id, p["name"].strip(), p["commodity"], p["equipment"], p["from_zone"],
         p["to_zone"], tonnes, rate_per_tonne, q["currency"],
         float(p.get("tolerance_pct") or 0.5), starts, ends, db.now()))
    conn.commit()
    return contract_json(conn, conn.execute("SELECT * FROM contracts WHERE id = ?",
                                            (cur.lastrowid,)).fetchone())


# --- shared guards ---------------------------------------------------------

def order_or_404(conn, ref):
    row = conn.execute("SELECT * FROM orders WHERE ref = ?", (ref,)).fetchone()
    if not row:
        raise ApiError("No load with that reference", 404)
    return row


def guard_order_access(user, row):
    if user["role"] == "shipper" and row["shipper_id"] != user["id"]:
        raise ApiError("Not your order", 403)
    if user["role"] == "driver" and row["driver_id"] not in (user["id"], None):
        raise ApiError("Not your job", 403)


ROUTES = [
    ("GET", r"^/api/health$", get_health),
    ("GET", r"^/api/config$", get_config),
    ("POST", r"^/api/quote$", post_quote),
    ("POST", r"^/api/distance$", post_distance),
    ("POST", r"^/api/auth/register$", post_register),
    ("POST", r"^/api/auth/login$", post_login),
    ("POST", r"^/api/auth/logout$", post_logout),
    ("GET", r"^/api/me$", get_me),
    ("GET", r"^/api/kyc$", get_kyc),
    ("POST", r"^/api/kyc/profile$", post_kyc_profile),
    ("POST", r"^/api/kyc/people$", post_kyc_people),
    ("DELETE", r"^/api/kyc/people/([0-9]+)$", delete_kyc_person),
    ("POST", r"^/api/kyc/documents$", post_kyc_document),
    ("DELETE", r"^/api/kyc/documents/([0-9]+)$", delete_kyc_document),
    ("GET", r"^/api/kyc/documents/([0-9]+)/file$", get_kyc_file),
    ("POST", r"^/api/kyc/submit$", post_kyc_submit),
    ("GET", r"^/api/agreements$", get_agreements),
    ("GET", r"^/api/agreements/([A-Za-z0-9-]+)$", get_agreement),
    ("GET", r"^/api/sign/([A-Za-z0-9_-]+)$", get_sign),
    ("POST", r"^/api/sign/([A-Za-z0-9_-]+)$", post_sign),
    ("POST", r"^/api/sign/([A-Za-z0-9_-]+)/decline$", post_decline),
    ("POST", r"^/api/sign/([A-Za-z0-9_-]+)/downloaded$", post_sign_downloaded),
    ("GET", r"^/api/ops/agreement-templates$", get_templates),
    ("POST", r"^/api/ops/agreements$", post_agreements),
    ("POST", r"^/api/ops/agreements/([A-Za-z0-9-]+)/send$", post_agreement_send),
    ("POST", r"^/api/ops/agreements/([A-Za-z0-9-]+)/void$", post_agreement_void),
    ("POST", r"^/api/ops/agreements/([A-Za-z0-9-]+)/countersign$", post_agreement_countersign),
    ("GET", r"^/api/ops/network$", get_network),
    ("GET", r"^/api/ops/accounts/([0-9]+)$", get_account),
    ("POST", r"^/api/ops/accounts/([0-9]+)/status$", post_account_status),
    ("GET", r"^/api/ops/kyc$", get_ops_kyc),
    ("GET", r"^/api/ops/kyc/([0-9]+)$", get_ops_kyc_one),
    ("POST", r"^/api/ops/kyc/([0-9]+)/decision$", post_ops_kyc_decision),
    ("GET", r"^/api/orders$", get_orders),
    ("POST", r"^/api/orders$", post_orders),
    ("GET", r"^/api/orders/([A-Za-z0-9-]+)$", get_order),
    ("POST", r"^/api/orders/([A-Za-z0-9-]+)/status$", post_status),
    ("POST", r"^/api/orders/([A-Za-z0-9-]+)/assign$", post_assign),
    ("POST", r"^/api/orders/([A-Za-z0-9-]+)/documents$", post_document),
    ("POST", r"^/api/orders/([A-Za-z0-9-]+)/position$", post_position),
    ("POST", r"^/api/orders/([A-Za-z0-9-]+)/weights$", post_weights),
    ("POST", r"^/api/orders/([A-Za-z0-9-]+)/stops/([0-9]+)/done$", post_stop_done),
    ("GET",  r"^/api/contracts$", get_contracts),
    ("POST", r"^/api/contracts$", post_contracts),
    ("GET", r"^/api/track/([A-Za-z0-9-]+)$", get_track),
    ("GET", r"^/api/jobs$", get_jobs),
    ("POST", r"^/api/jobs/([A-Za-z0-9-]+)/accept$", post_accept),
    ("GET", r"^/api/ops/drivers$", get_drivers),
    ("GET", r"^/api/ops/summary$", get_summary),
    ("GET", r"^/api/driver/earnings$", get_earnings),
    ("POST", r"^/api/driver/online$", post_online),
    ("POST", r"^/api/driver/vehicle$", post_vehicle),
    ("GET",  r"^/api/fuel$", get_fuel),
    ("POST", r"^/api/fuel/([A-Za-z0-9-]+)/draw$", post_fuel_draw),
    ("GET",  r"^/api/settlements$", get_settlements),
    ("POST", r"^/api/insurance/quote$", post_insurance_quote),
    ("POST", r"^/api/hire/quote$", post_hire_quote),
    ("GET", r"^/api/hires$", get_hires),
    ("POST", r"^/api/hires$", post_hires),
    ("GET", r"^/api/hires/([A-Za-z0-9-]+)$", get_hire),
    ("POST", r"^/api/hires/([A-Za-z0-9-]+)/status$", post_hire_status),
]

COMPILED = [(m, re.compile(p), h) for m, p, h in ROUTES]


def dispatch(method, path, body, token, meta=None):
    """Returns (status_code, payload). Raises nothing to the caller.

    `meta` carries the caller's address and user agent. Nothing in the freight
    flow needs them; the signature audit trail is worthless without them."""
    conn = db.connect()
    ctx = {"conn": conn, "body": body or {}, "token": token, "path": path,
           "ip": (meta or {}).get("ip"), "agent": (meta or {}).get("agent")}
    try:
        matched_path = False
        for m, pattern, handler in COMPILED:
            match = pattern.match(path)
            if not match:
                continue
            matched_path = True
            if m != method:
                continue
            return 200, handler(ctx, *match.groups())
        return (405 if matched_path else 404), {"error": "No such endpoint"}
    except ApiError as e:
        return e.status, {"error": e.message}
    except Exception as e:  # noqa: BLE001 - nothing reaches the client unlogged
        # The traceback goes to the server log, where the operator can read it.
        # The client gets a reference and nothing about the internals, because
        # exception text has a habit of containing table names and values.
        reference = secrets.token_hex(4)
        traceback.print_exc()
        sys.stderr.write("  error %s on %s %s: %s: %s\n"
                         % (reference, method, path, type(e).__name__, e))
        if os.environ.get("MUSANGA_ENV") == "production":
            return 500, {"error": "Something went wrong on our side. "
                                  "Quote reference %s if you contact us." % reference}
        return 500, {"error": "%s: %s" % (type(e).__name__, e), "reference": reference}
    finally:
        conn.close()
