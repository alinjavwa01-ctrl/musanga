#!/usr/bin/env python3
"""End-to-end tests against a running server. Usage: python3 tests.py [port]"""
import json, sys, urllib.request, urllib.error

PORT = sys.argv[1] if len(sys.argv) > 1 else "8000"
BASE = "http://127.0.0.1:%s" % PORT

def call(method, path, body=None, token=None):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = "Bearer " + token
    req = urllib.request.Request(
        BASE + path, method=method,
        data=json.dumps(body).encode() if body is not None else None, headers=headers)
    try:
        with urllib.request.urlopen(req) as r:
            return r.status, json.load(r)
    except urllib.error.HTTPError as e:
        return e.code, json.load(e)

PASS = FAIL = 0
def check(name, cond, extra=""):
    global PASS, FAIL
    if cond:
        PASS += 1; print("  ok    %s" % name)
    else:
        FAIL += 1; print("  FAIL  %s  %s" % (name, extra))

# --- rate engine, no auth --------------------------------------------------
s, cfg = call("GET", "/api/config")
check("config loads", s == 200 and cfg["equipment"] and cfg["commodities"], s)

s, q = call("POST", "/api/quote", {"equipment": "sidetipper34", "commodity": "copper_concentrate",
    "service": "spot", "from_zone": "kalumbila", "to_zone": "kasumbalesa", "tonnes": 34})
check("rates a concentrate export", s == 200 and q["total_ngwee"] > 0, q)
check("border clearance charged", any(l["label"] == "Border clearance" and l["ngwee"] > 0 for l in q["lines"]), q["lines"])

s, q2 = call("POST", "/api/quote", {"equipment": "bulktanker", "commodity": "sulphuric_acid",
    "service": "priority", "from_zone": "kafue", "to_zone": "chingola", "tonnes": 29})
check("hazard permit charged", any("Hazardous" in l["label"] and l["ngwee"] > 0 for l in q2["lines"]), q2["lines"])

s, q3 = call("POST", "/api/quote", {"equipment": "superlink34", "commodity": "maize",
    "service": "spot", "from_zone": "mkushi", "to_zone": "lusaka", "tonnes": 10})
check("minimum billable tonnage applies", q3["billed_tonnes"] > q3["tonnes"], q3)

s, r = call("POST", "/api/quote", {"equipment": "flatbed30", "commodity": "sulphuric_acid",
    "service": "spot", "from_zone": "kafue", "to_zone": "kitwe", "tonnes": 20})
check("acid rejected on a flatbed", s == 400 and "cannot carry" in r.get("error", ""), r)

s, r = call("POST", "/api/quote", {"equipment": "flatbed30", "commodity": "maize",
    "service": "spot", "from_zone": "mkushi", "to_zone": "lusaka", "tonnes": 45})
check("overload rejected", s == 400 and "exceeds" in r.get("error", ""), r)

s, r = call("POST", "/api/quote", {"equipment": "flatbed30", "commodity": "maize",
    "service": "spot", "from_zone": "mkushi", "to_zone": "lusaka", "tonnes": 0})
check("zero tonnage rejected", s == 400, r)

s, d = call("POST", "/api/distance", {"from_zone": "kafue", "to_zone": "mkushi"})
check("publishes corridor distance", s == 200 and d["distance_km"] > 0, d)
s, r = call("POST", "/api/distance", {"from_zone": "kafue", "to_zone": "atlantis"})
check("unknown location rejected", s == 400, r)

# --- auth ------------------------------------------------------------------
s, shipper = call("POST", "/api/auth/login", {"phone": "+260971000001", "password": "musanga2026"})
check("shipper signs in", s == 200 and shipper.get("token"), shipper)
st = shipper["token"]
s, r = call("POST", "/api/auth/login", {"phone": "+260971000001", "password": "nope"})
check("wrong password rejected", s == 401, r)

s, carrier = call("POST", "/api/auth/login", {"phone": "+260972000001", "password": "musanga2026"})
check("carrier signs in", s == 200, carrier)
ct = carrier["token"]
s, control = call("POST", "/api/auth/login", {"phone": "+260970000001", "password": "musanga2026"})
check("control signs in", s == 200, control)
ot = control["token"]

s, r = call("GET", "/api/orders")
check("loads require auth", s == 401, r)
s, r = call("GET", "/api/ops/summary", token=st)
check("shipper blocked from control", s == 403, r)
s, r = call("GET", "/api/jobs", token=st)
check("shipper blocked from load board", s == 403, r)

# --- booking ---------------------------------------------------------------
load = {"equipment": "sidetipper34", "commodity": "copper_concentrate", "service": "spot",
        "from_zone": "chingola", "to_zone": "kasumbalesa", "tonnes": 34,
        "pickup_address": "Nchanga load-out", "dropoff_address": "Kasumbalesa bonded yard",
        "recipient_name": "Test Agent", "recipient_phone": "+260970000099",
        "goods": "Concentrate export test", "payment_method": "invoice"}
s, o = call("POST", "/api/orders", load, token=st)
check("books a load", s == 200 and o.get("ref"), o)
ref = o["ref"]
check("starts as placed", o["status"] == "placed", o.get("status"))
check("invoice terms recorded", o["payment_status"] == "invoiced", o.get("payment_status"))
check("timeline opened", len(o["timeline"]) == 1, o.get("timeline"))

bad = dict(load, commodity="maize")
s, r = call("POST", "/api/orders", bad, token=st)
check("booking validates equipment vs cargo", s == 400, r)

# --- public tracking -------------------------------------------------------
s, t = call("GET", "/api/track/" + ref)
check("public tracking works", s == 200 and t["ref"] == ref, t)
check("tracking hides commercials", "total_ngwee" not in t and "payout_ngwee" not in t, list(t))

# --- carrier ---------------------------------------------------------------
s, board = call("GET", "/api/jobs", token=ct)
check("load board shows matching work", s == 200 and any(j["ref"] == ref for j in board["jobs"]), s)
s, a = call("POST", "/api/jobs/%s/accept" % ref, token=ct)
check("carrier accepts", s == 200 and a["status"] == "assigned", a)
s, a2 = call("POST", "/api/jobs/%s/accept" % ref, token=ct)
check("double accept blocked", s == 409, a2)
s, r = call("POST", "/api/orders/%s/status" % ref, {"status": "delivered"}, token=ct)
check("status skipping blocked", s == 400, r)
for step in ("at_pickup", "in_transit"):
    s, r = call("POST", "/api/orders/%s/status" % ref, {"status": step}, token=ct)
    check("carrier advances to %s" % step, s == 200 and r["status"] == step, r)
s, r = call("POST", "/api/orders/%s/status" % ref,
            {"status": "delivered", "proof_note": "Weighbridge ticket 44821"}, token=ct)
check("carrier delivers", s == 200 and r["status"] == "delivered", r)
check("proof of delivery stored", r["proof_note"] == "Weighbridge ticket 44821", r.get("proof_note"))
check("full timeline recorded", len(r["timeline"]) == 5, len(r.get("timeline", [])))

# --- isolation -------------------------------------------------------------
s, other = call("POST", "/api/auth/login", {"phone": "+260971000002", "password": "musanga2026"})
s, r = call("GET", "/api/orders/" + ref, token=other["token"])
check("other shipper cannot read the load", s == 403, r)

# --- control ---------------------------------------------------------------
s, summary = call("GET", "/api/ops/summary", token=ot)
check("control summary", s == 200 and "tonne_km" in summary, summary)
check("tonnage tracked", summary["tonnes_moved"] > 0, summary.get("tonnes_moved"))
s, carriers = call("GET", "/api/ops/drivers", token=ot)
check("carrier roster", s == 200 and len(carriers["drivers"]) == 9, s)
s, earn = call("GET", "/api/driver/earnings", token=ct)
check("carrier earnings", s == 200 and earn["paid_ngwee"] > 0, earn)

s, all_loads = call("GET", "/api/orders", token=ot)
queued = [x for x in all_loads["orders"] if x["status"] == "placed" and not x.get("driver_id")]
if queued:
    target = queued[0]
    wrong = [d for d in carriers["drivers"] if d["equipment_key"] != target["equipment_key"]][0]
    right = [d for d in carriers["drivers"] if d["equipment_key"] == target["equipment_key"]]
    s, r = call("POST", "/api/orders/%s/assign" % target["ref"], {"driver_id": wrong["id"]}, token=ot)
    check("dispatch rejects wrong equipment", s == 400, r)
    if right:
        s, r = call("POST", "/api/orders/%s/assign" % target["ref"], {"driver_id": right[0]["id"]}, token=ot)
        check("dispatch assigns matching carrier", s == 200 and r["status"] == "assigned", r)

# --- plant hire ------------------------------------------------------------
s, hq = call("POST", "/api/hire/quote", {"plant": "excavator30", "site": "kalumbila", "days": 14})
check("rates a hire", s == 200 and hq["total_ngwee"] > 0, hq)
check("picks the nearest depot", hq["depot"] in ("lusaka", "ndola", "solwezi"), hq.get("depot"))
check("float charged both ways", any("each way" in l["label"] and l["ngwee"] > 0 for l in hq["lines"]), hq["lines"])

s, day = call("POST", "/api/hire/quote", {"plant": "grader", "site": "mkushi", "days": 6})
s, week = call("POST", "/api/hire/quote", {"plant": "grader", "site": "mkushi", "days": 7})
check("a week never costs more than six days", week["total_ngwee"] <= day["total_ngwee"], (day["total_ngwee"], week["total_ngwee"]))
check("tier picked is the cheaper one", week["tier"] == "week", week.get("tier"))

s, dry = call("POST", "/api/hire/quote", {"plant": "tlb", "site": "lusaka", "days": 3, "with_operator": False})
s, wet = call("POST", "/api/hire/quote", {"plant": "tlb", "site": "lusaka", "days": 3, "with_operator": True})
check("operator costs extra", wet["total_ngwee"] > dry["total_ngwee"], (dry["total_ngwee"], wet["total_ngwee"]))

s, gen = call("POST", "/api/hire/quote", {"plant": "genset500", "site": "lusaka", "days": 5, "with_operator": True})
check("unmanned plant takes no operator", gen["with_operator"] is False, gen.get("with_operator"))

s, r = call("POST", "/api/hire/quote", {"plant": "excavator30", "site": "lusaka", "days": 0})
check("zero-day hire rejected", s == 400, r)
s, r = call("POST", "/api/hire/quote", {"plant": "nonesuch", "site": "lusaka", "days": 5})
check("unknown machine rejected", s == 400, r)
s, r = call("POST", "/api/hire/quote", {"plant": "excavator30", "site": "lusaka", "days": 400})
check("year-plus hire rejected", s == 400, r)

hire_body = {"plant": "wheelloader", "site": "ndola", "days": 10, "with_operator": True,
             "site_address": "Ndola, stockpile yard", "site_contact": "Test Contact",
             "site_phone": "+260970000098", "purpose": "Stockpile handling test",
             "payment_method": "invoice"}
s, hire = call("POST", "/api/hires", hire_body, token=st)
check("books a hire", s == 200 and hire.get("ref"), hire)
href = hire["ref"]
check("hire starts as requested", hire["status"] == "requested", hire.get("status"))

s, r = call("GET", "/api/hires", token=ct)
check("carriers have no hire console", s == 403, r)

s, r = call("POST", "/api/hires/%s/status" % href, {"status": "on_site"}, token=ot)
check("hire cannot skip confirmation", s == 400, r)
s, r = call("POST", "/api/hires/%s/status" % href, {"status": "confirmed"}, token=st)
check("customer cannot confirm their own hire", s == 403, r)
s, r = call("POST", "/api/hires/%s/status" % href, {"status": "confirmed"}, token=ot)
check("control confirms", s == 200 and r["status"] == "confirmed", r)
s, r = call("POST", "/api/hires/%s/status" % href, {"status": "on_site"}, token=ot)
check("machine goes on site", s == 200 and r["status"] == "on_site", r)
s, r = call("POST", "/api/hires/%s/status" % href, {"status": "off_hire"}, token=st)
check("customer can end the hire", s == 200 and r["status"] == "off_hire", r)
s, r = call("POST", "/api/hires/%s/status" % href, {"status": "returned", "meter_note": "1,284 h"}, token=ot)
check("control closes the hire", s == 200 and r["status"] == "returned", r)
check("return condition recorded", r["meter_note"] == "1,284 h", r.get("meter_note"))
check("hire timeline complete", len(r["timeline"]) == 5, len(r.get("timeline", [])))

s, r = call("GET", "/api/hires/" + href, token=other["token"])
check("other customer cannot read the hire", s == 403, r)

s, ht = call("GET", "/api/track/" + href)
check("hires are publicly trackable", s == 200 and ht["kind"] == "hire", ht)
check("hire tracking hides the price", "total_ngwee" not in ht, list(ht))
s, ft = call("GET", "/api/track/" + ref)
check("freight tracking is tagged as freight", ft["kind"] == "freight", ft.get("kind"))
s, r = call("GET", "/api/track/HIR-NOPE99")
check("unknown hire reference 404s", s == 404, r)

s, summary2 = call("GET", "/api/ops/summary", token=ot)
check("control sees hire numbers", summary2["hire_gmv_ngwee"] > 0, summary2.get("hire_gmv_ngwee"))

# --- carrier bundle: fuel credit and cover ---------------------------------
# One load booked with cover, taken by a carrier, fuelled at the pump and
# settled - the whole bundle end to end.

covered = dict(load, declared_value=850000, goods="Covered concentrate test")
s, co = call("POST", "/api/orders", covered, token=st)
check("books a load with cover", s == 200 and co.get("cover"), co.get("cover"))
cref = co["ref"]
check("cover priced off declared value", co["cover"]["declared_value_ngwee"] == 85_000_000, co.get("cover"))
check("cover records our commission", co["cover"]["commission_ngwee"] > 0, co.get("cover"))
check("cover is quoted, not bound", co["cover"]["status"] == "quoted", co["cover"].get("status"))

s, r = call("POST", "/api/orders", dict(covered, declared_value="lots"), token=st)
check("nonsense declared value rejected", s == 400, r)
s, r = call("POST", "/api/insurance/quote", {"commodity": "maize", "declared_value": 200000})
check("cover can be priced without booking", s == 200 and r["premium_ngwee"] > 0, r)

s, r = call("POST", "/api/jobs/%s/accept" % cref, token=ct)
check("carrier takes the covered load", s == 200, r)
check("diesel issued on acceptance", r.get("fuel", {}).get("litres", 0) > 0, r.get("fuel"))

s, fu = call("GET", "/api/fuel", token=ct)
check("carrier sees the facility", s == 200 and fu["facility"]["limit_ngwee"] > 0, fu.get("facility"))
ent = [e for e in fu["facility"]["entitlements"] if e["order_ref"] == cref]
check("this load has an entitlement", len(ent) == 1, [e["order_ref"] for e in fu["facility"]["entitlements"]])
litres = ent[0]["litres_remaining"]

s, r = call("GET", "/api/fuel", token=st)
check("shippers have no fuel facility", s == 403, r)

s, r = call("POST", "/api/fuel/%s/draw" % cref, {"litres": litres + 1}, token=ct)
check("draw beyond the load entitlement refused", s == 400, r)
s, drew = call("POST", "/api/fuel/%s/draw" % cref, {"litres": litres, "station": "Puma Chingola"}, token=ct)
check("carrier draws diesel", s == 200 and drew["draw"]["litres"] == litres, drew)
check("draw lands on the facility", drew["facility"]["outstanding_ngwee"] >= drew["draw"]["value_ngwee"], drew.get("facility"))
s, r = call("POST", "/api/fuel/%s/draw" % cref, {"litres": 1}, token=ct)
check("nothing left to draw on this load", s == 400, r)

for step in ("at_pickup", "in_transit", "delivered"):
    call("POST", "/api/orders/%s/status" % cref, {"status": step}, token=ct)
s, sett = call("GET", "/api/settlements", token=ct)
mine = [x for x in sett["settlements"] if x["ref"] == cref]
check("delivery produces a settlement", len(mine) == 1, [x["ref"] for x in sett["settlements"]])
check("fuel netted off the settlement", mine[0]["fuel_deduction_ngwee"] > 0, mine[0] if mine else None)
check("netting never takes more than half", mine[0]["fuel_deduction_ngwee"] * 2 <= mine[0]["gross_ngwee"], mine[0] if mine else None)
check("carrier still gets paid", mine[0]["net_ngwee"] > 0, mine[0] if mine else None)

s, earn2 = call("GET", "/api/driver/earnings", token=ct)
check("earnings show what fuel took", earn2["fuel_netted"] != "K0.00", earn2.get("fuel_netted"))

# --- routing ---------------------------------------------------------------
s, r = call("GET", "/api/nothing-here")
check("unknown endpoint 404s", s == 404, r)
s, r = call("GET", "/api/quote")
check("wrong method 405s", s == 405, r)

print("\n  %d passed, %d failed\n" % (PASS, FAIL))
sys.exit(1 if FAIL else 0)
