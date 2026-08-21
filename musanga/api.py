"""JSON API. Plain functions over sqlite, dispatched by a tiny pattern router."""

import json
import re
import secrets
import time

from . import db, geo, pricing, rental

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
PAYMENT_METHODS = {
    "airtel": "Airtel Money",
    "mtn": "MTN MoMo",
    "zamtel": "Zamtel Kwacha",
    "card": "Card",
    "invoice": "Invoice (30 days)",
}


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


def current_user(conn, token):
    if not token:
        return None
    row = conn.execute(
        "SELECT u.* FROM sessions s JOIN users u ON u.id = s.user_id WHERE s.token = ?", (token,)
    ).fetchone()
    return row_to_dict(row)


def auth(conn, token, *roles):
    user = current_user(conn, token)
    if not user:
        raise ApiError("Sign in to continue", 401)
    if roles and user["role"] not in roles:
        raise ApiError("Your account does not have access to this", 403)
    return user


def public_user(user):
    return {k: user[k] for k in ("id", "role", "name", "phone", "email", "company") if k in user}


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
    o["total"] = pricing.kwacha(o["total_ngwee"])
    o["payout"] = pricing.kwacha(o["payout_ngwee"])
    o["payment_label"] = PAYMENT_METHODS.get(o["payment_method"], o["payment_method"])
    if o.get("driver_id"):
        d = conn.execute("SELECT name, phone FROM users WHERE id = ?", (o["driver_id"],)).fetchone()
        o["driver"] = row_to_dict(d)
        v = conn.execute("SELECT equipment_key, plate FROM vehicles WHERE driver_id = ?", (o["driver_id"],)).fetchone()
        o["driver_vehicle"] = row_to_dict(v)
    if include_timeline:
        rows = conn.execute(
            "SELECT status, note, actor, created_at FROM events WHERE order_id = ? ORDER BY id", (o["id"],)
        ).fetchall()
        o["timeline"] = [
            dict(row_to_dict(r), label=STATUS_LABEL.get(r["status"], r["status"])) for r in rows
        ]
    return o


# --- routes ----------------------------------------------------------------

def get_config(ctx):
    return {
        "zones": geo.node_list(),
        "equipment": pricing.equipment_list(),
        "commodities": pricing.commodity_list(),
        "services": pricing.service_list(),
        "plant": rental.plant_list(),
        "plant_categories": rental.category_list(),
        "payment_methods": [{"key": k, "name": v} for k, v in PAYMENT_METHODS.items()],
    }


def post_quote(ctx):
    p = ctx["body"]
    require(p, "equipment", "service", "from_zone", "to_zone")
    try:
        q = pricing.quote(p["equipment"], p["service"], p["from_zone"], p["to_zone"],
                          p.get("tonnes", 0), p.get("commodity") or "general")
    except (pricing.QuoteError, ValueError) as e:
        raise ApiError(str(e))
    q["total"] = pricing.kwacha(q["total_ngwee"])
    q["net"] = pricing.kwacha(q["net_ngwee"])
    q["vat"] = pricing.kwacha(q["vat_ngwee"])
    q["rate_per_tkm"] = pricing.kwacha(q["rate_per_tkm_ngwee"])
    for line in q["lines"]:
        line["amount"] = pricing.kwacha(line["ngwee"])
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
    phone, password = require(p, "phone", "password")
    row = conn.execute("SELECT * FROM users WHERE phone = ?", (phone,)).fetchone()
    if not row or not db.verify_password(password, row["password_hash"]):
        raise ApiError("Phone number or password is not right", 401)
    return _start_session(conn, row["id"])


def _start_session(conn, user_id):
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
    if user["role"] == "driver":
        v = ctx["conn"].execute("SELECT * FROM vehicles WHERE driver_id = ?", (user["id"],)).fetchone()
        out["vehicle"] = row_to_dict(v)
    return out


def post_orders(ctx):
    conn, p = ctx["conn"], ctx["body"]
    user = auth(conn, ctx["token"], "shipper", "ops")
    require(p, "equipment", "service", "commodity", "from_zone", "to_zone", "pickup_address",
            "dropoff_address", "recipient_name", "recipient_phone", "goods", "payment_method")
    if p["payment_method"] not in PAYMENT_METHODS:
        raise ApiError("Unknown payment method")
    try:
        q = pricing.quote(p["equipment"], p["service"], p["from_zone"], p["to_zone"],
                          p.get("tonnes", 0), p["commodity"])
    except (pricing.QuoteError, ValueError) as e:
        raise ApiError(str(e))

    ref = db.new_ref()
    # Invoiced customers are billed later; everyone else pays on the wallet
    # prompt, which we mark paid once the collection callback lands.
    payment_status = "invoiced" if p["payment_method"] == "invoice" else "pending"
    cur = conn.execute(
        """INSERT INTO orders (ref, shipper_id, equipment_key, service_key, commodity_key, from_zone, to_zone,
             pickup_address, dropoff_address, recipient_name, recipient_phone, goods, tonnes, billed_tonnes,
             distance_km, eta_minutes, total_ngwee, payout_ngwee, payment_method, payment_status,
             status, scheduled_for, created_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,'placed',?,?)""",
        (ref, user["id"], p["equipment"], p["service"], p["commodity"], p["from_zone"], p["to_zone"],
         p["pickup_address"].strip(), p["dropoff_address"].strip(), p["recipient_name"].strip(),
         p["recipient_phone"].strip(), p["goods"].strip(), q["tonnes"], q["billed_tonnes"], q["distance_km"],
         q["eta_minutes"], q["total_ngwee"], q["partner_payout_ngwee"], p["payment_method"],
         payment_status, p.get("scheduled_for"), db.now()),
    )
    log_event(conn, cur.lastrowid, "placed", "Order created by %s" % user["name"], user["name"])
    conn.commit()
    row = conn.execute("SELECT * FROM orders WHERE id = ?", (cur.lastrowid,)).fetchone()
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
            "timeline", "driver")
    out = {k: o.get(k) for k in keep}
    out["kind"] = "freight"
    if out.get("driver"):
        out["driver"] = {"name": out["driver"]["name"]}
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
    conn.commit()
    return order_json(conn, conn.execute("SELECT * FROM orders WHERE id = ?", (row["id"],)).fetchone(), True)


def get_jobs(ctx):
    """The driver job board: unassigned work this driver's vehicle can carry."""
    conn = ctx["conn"]
    user = auth(conn, ctx["token"], "driver")
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
    return {
        "paid_ngwee": paid,
        "pending_ngwee": pending,
        "paid": pricing.kwacha(paid),
        "pending": pricing.kwacha(pending),
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

ROUTES = [
    ("GET", r"^/api/config$", get_config),
    ("POST", r"^/api/quote$", post_quote),
    ("POST", r"^/api/distance$", post_distance),
    ("POST", r"^/api/auth/register$", post_register),
    ("POST", r"^/api/auth/login$", post_login),
    ("POST", r"^/api/auth/logout$", post_logout),
    ("GET", r"^/api/me$", get_me),
    ("GET", r"^/api/orders$", get_orders),
    ("POST", r"^/api/orders$", post_orders),
    ("GET", r"^/api/orders/([A-Za-z0-9-]+)$", get_order),
    ("POST", r"^/api/orders/([A-Za-z0-9-]+)/status$", post_status),
    ("POST", r"^/api/orders/([A-Za-z0-9-]+)/assign$", post_assign),
    ("GET", r"^/api/track/([A-Za-z0-9-]+)$", get_track),
    ("GET", r"^/api/jobs$", get_jobs),
    ("POST", r"^/api/jobs/([A-Za-z0-9-]+)/accept$", post_accept),
    ("GET", r"^/api/ops/drivers$", get_drivers),
    ("GET", r"^/api/ops/summary$", get_summary),
    ("GET", r"^/api/driver/earnings$", get_earnings),
    ("POST", r"^/api/driver/online$", post_online),
    ("POST", r"^/api/driver/vehicle$", post_vehicle),
    ("POST", r"^/api/hire/quote$", post_hire_quote),
    ("GET", r"^/api/hires$", get_hires),
    ("POST", r"^/api/hires$", post_hires),
    ("GET", r"^/api/hires/([A-Za-z0-9-]+)$", get_hire),
    ("POST", r"^/api/hires/([A-Za-z0-9-]+)/status$", post_hire_status),
]

COMPILED = [(m, re.compile(p), h) for m, p, h in ROUTES]


def dispatch(method, path, body, token):
    """Returns (status_code, payload). Raises nothing to the caller."""
    conn = db.connect()
    ctx = {"conn": conn, "body": body or {}, "token": token, "path": path}
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
    except Exception as e:  # noqa: BLE001 - surface the failure, do not 500 silently
        return 500, {"error": "%s: %s" % (type(e).__name__, e)}
    finally:
        conn.close()
