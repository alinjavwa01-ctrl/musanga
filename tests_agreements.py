#!/usr/bin/env python3
"""Agreements, signing by link and the ops mothership.
Usage: python3 tests_agreements.py [port]"""
import json, sys, time, urllib.request, urllib.error

PORT = sys.argv[1] if len(sys.argv) > 1 else "8000"
BASE = "http://127.0.0.1:%s" % PORT
N = int(time.time()) % 100000

def call(method, path, body=None, token=None):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = "Bearer " + token
    req = urllib.request.Request(BASE + path, method=method,
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

s, ops = call("POST", "/api/auth/login", {"phone": "+260970000001", "password": "musanga2026"})
ot = ops["token"]
s, shipper = call("POST", "/api/auth/login", {"phone": "+260971000004", "password": "musanga2026"})
st = shipper["token"]

# --- templates -------------------------------------------------------------
s, t = call("GET", "/api/ops/agreement-templates", token=ot)
check("templates are published", s == 200 and len(t["templates"]) >= 6, s)
check("a shipper cannot see them", call("GET", "/api/ops/agreement-templates", token=st)[0] == 403)

# --- drafting --------------------------------------------------------------
s, a = call("POST", "/api/ops/agreements", {
    "template": "master", "counterparty": "Test Buyer Limited",
    "counterparty_email": "buyer%d@example.zm" % N,
    "fields": {"starts_on": "1 September 2026", "payment_terms": "45 days"}}, ot)
check("a master agreement drafts", s == 200 and a["status"] == "draft", a)
check("the terms entered are in the text", "45 days" in a["body"], "")
check("the counterparty is named in the text", "Test Buyer Limited" in a["body"], "")
check("nothing is left as an empty hole", "{{" not in a["body"], "")
ref = a["ref"]
first_hash = a["body_hash"]

s, bad = call("POST", "/api/ops/agreements", {"template": "nope", "counterparty": "X"}, ot)
check("an unknown template is refused", s == 400, bad)

# --- a draft is not signable ----------------------------------------------
s, hidden = call("GET", "/api/sign/%s" % a["link"].split("/sign/")[1])
check("a draft cannot be opened by link", s == 404, hidden)

# --- sending ---------------------------------------------------------------
s, sent = call("POST", "/api/ops/agreements/%s/send" % ref, {}, ot)
check("sending opens the link", s == 200 and sent["status"] == "sent" and sent["sent_at"], sent)
check("the text is unchanged by sending", sent["body_hash"] == first_hash, "")
token = sent["link"].split("/sign/")[1]

# --- the signing room, with no account ------------------------------------
s, view = call("GET", "/api/sign/" + token)
check("the document opens without signing in", s == 200 and view["agreement"]["body"], s)
check("opening is recorded", any(e["label"] == "Opened by signer" for e in view["events"]), view["events"])
check("the link marks it viewed", view["agreement"]["status"] == "viewed", view["agreement"]["status"])
check("no other customer data leaks in", "account_id" not in view["agreement"], view["agreement"].keys())

s, refused = call("POST", "/api/sign/" + token, {
    "signer_name": "Ann Buyer", "signer_email": "ann@example.zm",
    "signature": "Ann Buyer", "signature_type": "typed"})
check("signing without consent is refused", s == 400, refused)

s, refused = call("POST", "/api/sign/" + token, {
    "signer_name": "Ann Buyer", "signer_email": "ann@example.zm", "consent": True,
    "signature": "Someone Else", "signature_type": "typed"})
check("a typed signature must match the name", s == 400, refused)

s, signed = call("POST", "/api/sign/" + token, {
    "signer_name": "Ann Buyer", "signer_title": "Finance Director",
    "signer_email": "ann@example.zm", "consent": True,
    "signature": "Ann Buyer", "signature_type": "typed"})
check("it signs", s == 200 and signed["agreement"]["status"] == "signed", signed)
check("a certificate of completion comes with it", "CERTIFICATE OF COMPLETION" in (signed["certificate"] or ""), "")
check("the certificate carries the document hash", first_hash in signed["certificate"], "")
check("the audit trail is in order",
      [e["label"] for e in signed["events"]][:3] == ["Drafted", "Sent for signature", "Opened by signer"],
      [e["label"] for e in signed["events"]])

s, again = call("POST", "/api/sign/" + token, {
    "signer_name": "Ann Buyer", "signer_email": "ann@example.zm", "consent": True,
    "signature": "Ann Buyer", "signature_type": "typed"})
check("it cannot be signed twice", s == 400, again)

s, d = call("POST", "/api/sign/%s/downloaded" % token, {})
check("taking a copy is recorded", s == 200, d)

# --- counter-signature and voiding ----------------------------------------
s, void = call("POST", "/api/ops/agreements/%s/void" % ref, {"reason": "no"}, ot)
check("a signed agreement cannot be voided", s == 400, void)
s, cs = call("POST", "/api/ops/agreements/%s/countersign" % ref, {}, ot)
check("Musanga countersigns", s == 200 and cs["countersigned_at"], cs)
s, cs2 = call("POST", "/api/ops/agreements/%s/countersign" % ref, {}, ot)
check("only once", s == 400, cs2)

# --- a shipment agreement writes itself from the booking -------------------
s, orders = call("GET", "/api/orders", token=ot)
order_ref = orders["orders"][0]["ref"]
s, ship = call("POST", "/api/ops/agreements", {
    "template": "shipment", "counterparty": "Test Buyer Limited", "order_ref": order_ref}, ot)
check("a shipment agreement is built from the load", s == 200 and order_ref in ship["body"], ship)
check("its rate is in the document", "per tonne" in ship["body"], "")
s, missing = call("POST", "/api/ops/agreements", {
    "template": "shipment", "counterparty": "X", "order_ref": "MSG-NOPE"}, ot)
check("an unknown booking is refused", s == 404, missing)

# --- links that should not work -------------------------------------------
check("a made-up token is refused", call("GET", "/api/sign/not-a-real-token")[0] == 404)
s, draft2 = call("POST", "/api/ops/agreements", {"template": "nda", "counterparty": "Someone"}, ot)
call("POST", "/api/ops/agreements/%s/send" % draft2["ref"], {}, ot)
s, v = call("POST", "/api/ops/agreements/%s/void" % draft2["ref"], {"reason": "wrong party"}, ot)
check("an unsigned agreement can be voided", s == 200 and v["status"] == "void", v)
s, gone = call("GET", "/api/sign/" + draft2["link"].split("/sign/")[1])
check("a voided link stops working", s == 410, gone)

# --- declining -------------------------------------------------------------
s, d3 = call("POST", "/api/ops/agreements", {"template": "nda", "counterparty": "Declining Co"}, ot)
call("POST", "/api/ops/agreements/%s/send" % d3["ref"], {}, ot)
dtok = d3["link"].split("/sign/")[1]
s, no_reason = call("POST", "/api/sign/%s/decline" % dtok, {})
check("declining needs a reason", s == 400, no_reason)
s, declined = call("POST", "/api/sign/%s/decline" % dtok, {"reason": "Rates not agreed"})
check("it can be declined", s == 200 and declined["status"] == "declined", declined)
s, after = call("POST", "/api/sign/" + dtok, {"signer_name": "A", "signer_email": "a@b.zm",
                                             "consent": True, "signature": "A", "signature_type": "typed"})
check("a declined document cannot then be signed", s == 400, after)

# --- what an account sees --------------------------------------------------
s, mine = call("GET", "/api/agreements", token=st)
check("a shipper sees only their own paper", s == 200 and all(
    x["counterparty"] != "Declining Co" for x in mine["agreements"]), mine)
s, all_of_them = call("GET", "/api/agreements", token=ot)
check("control sees every document", len(all_of_them["agreements"]) > len(mine["agreements"]), "")
s, nope = call("GET", "/api/agreements/%s" % ref, token=st)
check("another account cannot open it", s == 403, nope)

# --- the mothership --------------------------------------------------------
s, net = call("GET", "/api/ops/network", token=ot)
check("the network lists both sides", s == 200 and net["shippers"] and net["carriers"], s)
check("it counts what is waiting", "awaiting_review" in net["totals"], net["totals"])
check("a shipper cannot see the network", call("GET", "/api/ops/network", token=st)[0] == 403)

account_id = net["shippers"][0]["id"]
s, dossier = call("GET", "/api/ops/accounts/%d" % account_id, token=ot)
check("one account opens whole", s == 200 and "kyc" in dossier and "agreements" in dossier and "orders" in dossier, s)

s, refused = call("POST", "/api/ops/accounts/%d/status" % account_id, {"status": "suspended"}, ot)
check("suspending needs a reason", s == 400, refused)
s, susp = call("POST", "/api/ops/accounts/%d/status" % account_id,
               {"status": "suspended", "reason": "Unpaid invoices past 90 days"}, ot)
check("an account can be suspended", s == 200 and susp["account"]["account_status"] == "suspended", susp["account"])

s, who = call("GET", "/api/ops/network", token=ot)
suspended_phone = [a for a in who["shippers"] if a["id"] == account_id][0]["phone"]
s, sus = call("POST", "/api/auth/login", {"phone": suspended_phone, "password": "musanga2026"})
s, blocked = call("POST", "/api/orders", {
    "equipment": "flatbed30", "service": "spot", "commodity": "maize", "from_zone": "mkushi",
    "to_zone": "lusaka", "pickup_address": "a", "dropoff_address": "b", "recipient_name": "c",
    "recipient_phone": "+260970000000", "goods": "maize", "tonnes": 30,
    "payment_method": "card"}, sus["token"])
check("a suspended account cannot book", s == 403 and "suspended" in blocked["error"], blocked)
s, back = call("POST", "/api/ops/accounts/%d/status" % account_id, {"status": "active", "reason": "Paid"}, ot)
check("and can be put back", s == 200 and back["account"]["account_status"] == "active", back["account"])

print("\n  %d passed, %d failed" % (PASS, FAIL))
raise SystemExit(1 if FAIL else 0)
