#!/usr/bin/env python3
"""Reset the database and fill it with a realistic week on the corridors.

Deterministic: same data every run, so demos and screenshots are stable.
"""

import os
import random
import time
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from musanga import agreements, api, db, docs, geo, kyc, pricing, rental  # noqa: E402

DEMO_PASSWORD = "musanga2026"

# role, name, phone, email, company
USERS = [
    ("ops", "Njavwa Mutambo", "+260970000001", "njavwa@musanga.com", "Musanga"),
    ("ops", "Christal Phiri", "+260970000002", "control@musanga.com", "Musanga"),
    ("shipper", "Wakunyambo Mwanamuke", "+260971000001", "logistics@kansanshi.zm", "Kansanshi Mining"),
    ("shipper", "Musonda Nsama", "+260971000002", "supply@nitrogenchem.zm", "Nitrogen Chemicals of Zambia"),
    ("shipper", "Namaala Liebenthal", "+260971000003", "ops@puma-energy.zm", "Puma Energy Zambia"),
    ("shipper", "Mwenda Katongo", "+260971000004", "inbound@zamgrain.zm", "ZamGrain Agri"),
]

# name, phone, equipment, plate, home base
DRIVERS = [
    ("Emmanuel Kwenda", "+260972000001", "sidetipper34", "BAK 4471", "chingola"),
    ("Khambula Msiska", "+260972000002", "sidetipper34", "BAK 5582", "solwezi"),
    ("Violet Blessings", "+260972000003", "tipper30", "CAC 1193", "kitwe"),
    ("Simunza Munyangana", "+260972000004", "flatbed30", "DAD 7734", "lusaka"),
    ("Harry Banda", "+260972000005", "superlink34", "EAE 2210", "ndola"),
    ("Tasha Mwansa", "+260972000006", "superlink34", "EAE 6650", "mkushi"),
    ("Kalubwa Karabassis", "+260972000007", "bulktanker", "FAF 8801", "ndola"),
    ("Musonda Chanda", "+260972000008", "bulktanker", "FAF 9912", "lusaka"),
    ("Daniel Zulu", "+260972000009", "lowbed", "GAG 3030", "kitwe"),
    ("Gift Mulenga", "+260972000010", "bulkgrain34", "HAH 4412", "mkushi"),
    ("Chola Bwalya", "+260972000011", "bulkgrain34", "HAH 5523", "kabwe"),
]

# equipment, service, from, to, pickup, dropoff, contact, phone, description,
# tonnes, commodity, payment
LOADS = [
    ("sidetipper34", "contract", "kalumbila", "kasumbalesa", "Kalumbila Mine, load-out bay 3",
     "Kasumbalesa Border, bonded yard", "Chanda Mulenga", "+260976100001",
     "Copper concentrate, export to DRC smelter", 34, "copper_concentrate", "invoice"),
    ("sidetipper34", "spot", "solwezi", "ndola", "Kansanshi Mine weighbridge",
     "Ndola, Mopani smelter gate", "Bwalya Zulu", "+260976100002",
     "Concentrate to smelter", 33, "copper_concentrate", "invoice"),
    ("flatbed30", "contract", "kitwe", "chirundu",
     "Mufulira refinery warehouse", "Chirundu Border, transit shed", "Grace Tembo", "+260976100003",
     "Copper cathodes, export bundles", 28, "copper_cathodes", "invoice"),
    ("bulktanker", "priority", "ndola", "solwezi", "Ndola Fuel Terminal, bay 2",
     "Kansanshi Mine bulk fuel farm", "Peter Sakala", "+260976100004",
     "Diesel resupply for mine fleet", 31, "fuel", "invoice"),
    ("bulktanker", "spot", "ndola", "kitwe", "Ndola Fuel Terminal, bay 5",
     "Kitwe depot", "Alice Banda", "+260976100005",
     "Diesel to Copperbelt depot", 30, "fuel", "invoice"),
    ("bulktanker", "priority", "kafue", "chingola", "Nitrogen Chemicals, acid plant",
     "Chingola, Nchanga leach plant", "Joseph Mwale", "+260976100006",
     "Sulphuric acid for leaching", 29, "sulphuric_acid", "invoice"),
    ("superlink34", "contract", "kafue", "mkushi", "Nitrogen Chemicals of Zambia, Kafue",
     "Mkushi Farm Block, central store", "Danny Chola", "+260976100007",
     "Compound D fertiliser, bagged", 33, "fertiliser", "invoice"),
    ("superlink34", "contract", "kafue", "chisamba", "Nitrogen Chemicals of Zambia, Kafue",
     "Chisamba, agro-dealer depot", "Mary Phiri", "+260976100008",
     "Urea, 50 kg bags", 32, "fertiliser", "invoice"),
    ("superlink34", "spot", "mkushi", "lusaka", "Mkushi Farm Block, silo 4",
     "Lusaka, grain terminal", "Sam Nyirenda", "+260976100009",
     "Maize to national reserve", 34, "maize", "invoice"),
    ("superlink34", "spot", "mumbwa", "lusaka", "Mumbwa, farm weighbridge",
     "Lusaka, crushing plant", "Ruth Mbewe", "+260976100010",
     "Soya beans for crushing", 31, "soya", "airtel"),
    ("tipper30", "spot", "maamba", "kafue", "Maamba Collieries, stockpile 2",
     "Kafue, industrial boiler yard", "Kunda Sinyinza", "+260976100011",
     "Thermal coal", 30, "coal", "invoice"),
    ("tipper30", "contract", "chilanga", "lusaka", "Chilanga quarry",
     "Lusaka, road works site", "Dr Mumba", "+260976100012",
     "Crushed aggregate", 29, "aggregate", "mtn"),
    ("flatbed30", "spot", "chilanga", "solwezi", "Chilanga Cement plant",
     "Solwezi, contractor yard", "Elias Mwape", "+260976100013",
     "Bagged cement for mine works", 30, "cement", "invoice"),
    ("lowbed", "priority", "lusaka", "kalumbila", "Lusaka, plant importer yard",
     "Kalumbila Mine, workshop", "Fred Musonda", "+260976100014",
     "Hydraulic excavator relocation", 52, "machinery", "invoice"),
    ("superlink34", "contract", "kafue", "choma", "Nitrogen Chemicals of Zambia, Kafue",
     "Choma, co-op warehouse", "Beatrice Hamoonga", "+260976100015",
     "Compound D for planting season", 33, "fertiliser", "invoice"),
    ("sidetipper34", "contract", "chingola", "kasumbalesa", "Nchanga Mine load-out",
     "Kasumbalesa Border, bonded yard", "Nathan Kaunda", "+260976100016",
     "Copper concentrate, export", 34, "copper_concentrate", "invoice"),
    # The grain export: Central Province to a Zimbabwean buyer, priced in
    # dollars, through Chirundu, on a food-grade unit.
    ("bulkgrain34", "contract", "mkushi", "harare", "Mkushi Farm Block, silo 4",
     "Harare, Aspindale grain depot", "Tendai Moyo", "+263772100001",
     "White maize, bulk, export to Zimbabwe", 34, "maize", "invoice"),
    ("bulkgrain34", "contract", "mkushi", "harare", "Mkushi Farm Block, silo 2",
     "Harare, Aspindale grain depot", "Tendai Moyo", "+263772100001",
     "White maize, bulk, export to Zimbabwe", 34, "maize", "invoice"),
]

# Extra drops on a run, keyed by the index of the load they belong to. The
# fertiliser distribution out of Kafue is one truck and several agro-dealers.
EXTRA_STOPS = {
    6: [("chisamba", "Chisamba, Omnia agro-dealer depot", "Mary Phiri", "+260976100008", 11),
        ("kabwe", "Kabwe, Omnia regional store", "Isaac Ngoma", "+260976100020", 11)],
    14: [("monze", "Monze, farmers co-op store", "Alice Muleya", "+260976100021", 11),
         ("mazabuka", "Mazabuka, estate central store", "Peter Hamoonga", "+260976100022", 11)],
}

# plant, site, address, contact, phone, purpose, days, operator, fuel, payment
HIRES = [
    ("excavator30", "kalumbila", "Kalumbila Mine, west pit", "Fred Musonda", "+260976200001",
     "Bench stripping, west pit extension", 30, True, True, "invoice"),
    ("grader", "mkushi", "Mkushi Farm Block, access roads", "Danny Chola", "+260976200002",
     "Farm access road rehabilitation before the rains", 9, True, False, "invoice"),
    ("crusher", "chingola", "Nchanga, aggregate pad", "Nathan Kaunda", "+260976200003",
     "On-site aggregate for tailings dam works", 14, True, True, "invoice"),
    ("genset500", "solwezi", "Kansanshi, contractor camp", "Peter Sakala", "+260976200004",
     "Camp power while the substation is down", 60, False, True, "invoice"),
    ("tlb", "lusaka", "Lusaka, Mungwi Road yard", "Grace Tembo", "+260976200005",
     "Service trenching at the new warehouse", 3, True, False, "airtel"),
    ("crane50", "ndola", "Ndola, smelter workshop", "Joseph Mwale", "+260976200006",
     "Mill liner change-out lift", 5, True, False, "invoice"),
    ("bowser", "maamba", "Maamba Collieries, haul road", "Kunda Sinyinza", "+260976200007",
     "Dust suppression on the main haul road", 21, True, True, "invoice"),
    ("adt", "lumwana", "Lumwana Mine, in-pit", "Alice Banda", "+260976200008",
     "Supplementary in-pit haulage", 30, True, True, "invoice"),
]

# Where each hire has got to.
HIRE_PROGRESS = ["on_site", "returned", "on_site", "on_site", "returned",
                 "confirmed", "off_hire", "requested"]

# Where each load has got to, so the demo shows a full pipeline at once.
PROGRESS = ["delivered", "delivered", "delivered", "delivered", "in_transit", "in_transit",
            "delivered", "at_pickup", "in_transit", "assigned", "delivered", "assigned",
            "placed", "placed", "placed", "placed", "in_transit", "placed"]


# The demo network is an established one, so every account on it is already
# through KYC - except one carrier, left waiting in the queue so control has
# something real to review.
def verify_accounts(conn, now):
    rows = conn.execute("SELECT * FROM users WHERE role != 'ops' ORDER BY id").fetchall()
    pending_id = conn.execute("SELECT id FROM users WHERE role = 'driver' ORDER BY id DESC LIMIT 1").fetchone()["id"]

    for row in rows:
        entity = "sole_trader" if row["role"] == "driver" else "limited"
        legal = row["company"] or ("%s Transport" % row["name"].split()[-1])
        conn.execute(
            "INSERT INTO kyc_profiles (user_id, entity_type, legal_name, trading_name, reg_number, "
            "tin, vat_registered, vat_number, country, address, sector, updated_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (row["id"], entity, "%s Limited" % legal if entity == "limited" else legal,
             row["company"] or row["name"], "1200%04d" % row["id"], "100%07d" % (2000000 + row["id"]),
             1 if entity == "limited" else 0,
             "VAT%06d" % row["id"] if entity == "limited" else None,
             "ZM", "Plot %d, Great North Road, Lusaka" % (100 + row["id"]),
             "mining" if row["role"] == "shipper" else "road transport", now - 86400 * 30))
        conn.execute(
            "INSERT INTO kyc_people (user_id, full_name, position, id_type, id_number, nationality, "
            "ownership_pct, is_control, created_at) VALUES (?,?,?,?,?,?,?,1,?)",
            (row["id"], row["name"], "Director" if entity == "limited" else "Owner", "nrc",
             "%06d/10/1" % (100000 + row["id"]), "ZM", 100 if entity != "limited" else 60,
             now - 86400 * 30))

        profile = dict(conn.execute("SELECT * FROM kyc_profiles WHERE user_id = ?", (row["id"],)).fetchone())
        checklist = kyc.catalogue(row["role"], entity, vat_registered=bool(profile["vat_registered"]))
        # The pending carrier is mid-file: licences in, insurance still to come.
        for i, doc in enumerate(checklist):
            if row["id"] == pending_id and doc["group"] == "operating" and i % 2:
                continue
            conn.execute(
                "INSERT INTO kyc_documents (user_id, doc_key, name, reference, status, filed_at, reviewed_at) "
                "VALUES (?,?,?,?,?,?,?)",
                (row["id"], doc["key"], doc["name"], "REF-%s-%d" % (doc["key"][:6].upper(), row["id"]),
                 "filed" if row["id"] == pending_id else "accepted", now - 86400 * 29,
                 None if row["id"] == pending_id else now - 86400 * 28))

        if row["id"] == pending_id:
            conn.execute("UPDATE users SET kyc_status = 'in_review', kyc_submitted_at = ? WHERE id = ?",
                         (now - 7200, row["id"]))
            conn.execute("INSERT INTO kyc_events (user_id,status,note,actor,created_at) VALUES (?,?,?,?,?)",
                         (row["id"], "in_review", "Submitted for verification", row["name"], now - 7200))
        else:
            conn.execute("UPDATE users SET kyc_status = 'verified', kyc_submitted_at = ?, kyc_decided_at = ? WHERE id = ?",
                         (now - 86400 * 29, now - 86400 * 28, row["id"]))
            conn.execute("INSERT INTO kyc_events (user_id,status,note,actor,created_at) VALUES (?,?,?,?,?)",
                         (row["id"], "verified", "File cleared by control", "Christal Phiri", now - 86400 * 28))


# Paper, in the state a ten-year-old network's paper is actually in: master
# agreements signed years ago, one carrier agreement still out for signature,
# and a shipment agreement against a live load.
def seed_agreements(conn, now):
    import secrets as _secrets

    control = conn.execute("SELECT id, name FROM users WHERE role = 'ops' ORDER BY id").fetchone()
    accounts = conn.execute("SELECT * FROM users WHERE role != 'ops' ORDER BY id").fetchall()

    def make(account, template, status, signed_days_ago=None, order_ref=None):
        profile = conn.execute("SELECT * FROM kyc_profiles WHERE user_id = ?", (account["id"],)).fetchone()
        legal = (profile["legal_name"] if profile else None) or account["company"] or account["name"]
        fields = {
            "counterparty": legal,
            "counterparty_reg": ", company number %s" % (profile["reg_number"] if profile else ""),
            "counterparty_address": (profile["address"] if profile else "Lusaka"),
            "dated": time.strftime("%d %B %Y", time.gmtime(now - 86400 * 30)),
            "starts_on": time.strftime("%d %B %Y", time.gmtime(now - 86400 * 30)),
        }
        if order_ref:
            # The shipment agreement is written out of the booking it covers,
            # the same way it is when control drafts one in the app.
            _, derived = api.context_from_order(conn, order_ref)
            derived.update(fields)
            fields = derived
        ref = db.new_ref("AGR")
        fields["ref"] = ref
        body = agreements.render(template, fields)
        signed_at = now - 86400 * signed_days_ago if signed_days_ago else None
        conn.execute(
            "INSERT INTO agreements (ref, kind, title, body, body_hash, counterparty, counterparty_email, "
            "counterparty_phone, account_id, order_ref, created_by, status, token, sent_at, viewed_at, "
            "signed_at, signer_name, signer_title, signer_email, signature, signature_type, signed_ip, "
            "expires_at, countersigned_at, countersigned_by, countersignature, created_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (ref, agreements.TEMPLATES[template]["kind"], agreements.TEMPLATES[template]["name"], body,
             agreements.digest(body), legal, account["email"], account["phone"], account["id"], order_ref,
             control["id"], status, _secrets.token_urlsafe(32), now - 86400 * 31,
             signed_at and signed_at - 600, signed_at,
             account["name"] if signed_at else None, "Director" if signed_at else None,
             account["email"] if signed_at else None,
             account["name"] if signed_at else None, "typed" if signed_at else None,
             "41.79.10.%d" % (20 + account["id"]) if signed_at else None,
             now + 86400 * 30, signed_at and signed_at + 3600, control["id"] if signed_at else None,
             control["name"] if signed_at else None, now - 86400 * 31))
        agreement_id = conn.execute("SELECT id FROM agreements WHERE ref = ?", (ref,)).fetchone()["id"]
        trail = [("created", control["name"], now - 86400 * 31), ("sent", control["name"], now - 86400 * 31)]
        if signed_at:
            trail += [("opened", legal, signed_at - 600), ("signed", legal, signed_at),
                      ("countersigned", control["name"], signed_at + 3600)]
        for event, actor, at in trail:
            conn.execute(
                "INSERT INTO agreement_events (agreement_id, event, actor, ip, agent, created_at) "
                "VALUES (?,?,?,?,?,?)",
                (agreement_id, event, actor, "41.79.10.%d" % (20 + account["id"]),
                 "Mozilla/5.0", at))
        return ref

    live_order = conn.execute("SELECT ref, shipper_id FROM orders WHERE status = 'in_transit' LIMIT 1").fetchone()
    carriers = [a for a in accounts if a["role"] == "driver"]
    for account in accounts:
        if account["role"] == "shipper":
            make(account, "master", "signed", signed_days_ago=30)
            if live_order and live_order["shipper_id"] == account["id"]:
                make(account, "shipment", "sent", order_ref=live_order["ref"])
        elif account is not carriers[-1]:
            make(account, "carrier", "signed", signed_days_ago=25)
        else:
            make(account, "carrier", "sent")


def seed():
    if os.path.exists(db.DB_PATH):
        os.remove(db.DB_PATH)
    conn = db.init()
    rng = random.Random(2026)
    now = db.now()

    ids = {}
    for role, name, phone, email, company in USERS:
        cur = conn.execute(
            "INSERT INTO users (role,name,phone,email,company,password_hash,created_at) VALUES (?,?,?,?,?,?,?)",
            (role, name, phone, email, company, db.hash_password(DEMO_PASSWORD), now - 86400 * 200),
        )
        ids[phone] = cur.lastrowid

    by_equipment = {}
    for name, phone, equipment_key, plate, home in DRIVERS:
        cur = conn.execute(
            "INSERT INTO users (role,name,phone,email,company,password_hash,created_at) "
            "VALUES ('driver',?,?,NULL,NULL,?,?)",
            (name, phone, db.hash_password(DEMO_PASSWORD), now - 86400 * 120),
        )
        by_equipment.setdefault(equipment_key, []).append(cur.lastrowid)
        conn.execute(
            "INSERT INTO vehicles (driver_id,equipment_key,plate,home_zone,is_online) VALUES (?,?,?,?,?)",
            (cur.lastrowid, equipment_key, plate, home, 1 if rng.random() > 0.2 else 0),
        )

    verify_accounts(conn, now)

    shippers = [ids[phone] for role, _, phone, _, _ in USERS if role == "shipper"]

    for i, load in enumerate(LOADS):
        (equipment, service, frm, to, pick, drop, contact, phone,
         description, tonnes, commodity, pay) = load
        extra = EXTRA_STOPS.get(i, [])
        q = pricing.quote(equipment, service, frm, to, tonnes, commodity, stops=len(extra))
        created = now - (len(LOADS) - i) * 9000 - rng.randint(0, 3600)
        status = PROGRESS[i]
        driver_id = rng.choice(by_equipment[equipment]) if status != "placed" else None
        payment_status = "invoiced" if pay == "invoice" else ("paid" if status == "delivered" else "pending")

        cur = conn.execute(
            """INSERT INTO orders (ref,shipper_id,driver_id,equipment_key,service_key,commodity_key,
                 from_zone,to_zone,pickup_address,dropoff_address,recipient_name,recipient_phone,goods,
                 tonnes,billed_tonnes,distance_km,eta_minutes,total_ngwee,payout_ngwee,payment_method,
                 payment_status,status,scheduled_for,created_at,currency,corridor,is_export,
                 stops_count,tolerance_pct)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,NULL,?,?,?,?,?,0.5)""",
            (db.new_ref(), shippers[i % len(shippers)], driver_id, equipment, service, commodity,
             frm, to, pick, drop, contact, phone, description, q["tonnes"], q["billed_tonnes"],
             q["distance_km"], q["eta_minutes"], q["total_ngwee"], q["partner_payout_ngwee"],
             pay, payment_status, status, created, q["currency"], q["corridor"],
             1 if q["export"] else 0, len(extra)),
        )
        order_id = cur.lastrowid

        # Drops, in the order the truck runs them, destination last.
        seq = 1
        for node_key, address, who, cell, drop_t in extra:
            conn.execute(
                """INSERT INTO order_stops (order_id,seq,node_key,address,recipient_name,
                     recipient_phone,tonnes,status,completed_at) VALUES (?,?,?,?,?,?,?,?,?)""",
                (order_id, seq, node_key, address, who, cell, drop_t,
                 "done" if status == "delivered" else "pending",
                 created + 40000 if status == "delivered" else None))
            seq += 1
        conn.execute(
            """INSERT INTO order_stops (order_id,seq,node_key,address,recipient_name,
                 recipient_phone,tonnes,status,completed_at) VALUES (?,?,?,?,?,?,?,?,?)""",
            (order_id, seq, to, drop, contact, phone,
             tonnes - sum(s[4] for s in extra),
             "done" if status == "delivered" else "pending",
             created + 60000 if status == "delivered" else None))

        # The document register, filed up to wherever the load has got to.
        reached = ["placed", "assigned", "at_pickup", "in_transit", "delivered"].index(status)
        stage_reached = {0: -1, 1: 0, 2: 0, 3: 2, 4: 3}[reached]
        for d in docs.required_for(commodity, frm, to, equipment):
            filed = docs.STAGES.index(d["stage"]) <= stage_reached
            conn.execute(
                """INSERT INTO order_documents (order_id,doc_key,name,owner,stage,mandatory,note,
                     status,reference,filed_by,filed_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (order_id, d["key"], d["name"], d["owner"], d["stage"], 1, d.get("note"),
                 "filed" if filed else "outstanding",
                 ("%s/%s" % (d["key"][:3].upper(), rng.randint(10000, 99999))) if filed else None,
                 "Musanga Control" if filed else None, created + 3600 if filed else None))

        # Weighbridge tickets on cargo that is sold by weight.
        weighed = pricing.COMMODITIES[commodity].get("food_grade") or \
            pricing.COMMODITIES[commodity]["sector"] == "mining"
        if weighed and reached >= 2:
            loaded_kg = int(tonnes * 1000)
            conn.execute("UPDATE orders SET loaded_kg = ? WHERE id = ?", (loaded_kg, order_id))
            if status == "delivered":
                # A little shrinkage is normal; one load in this set is not.
                shrink = 0.004 if i % 5 else 0.011
                discharged = int(loaded_kg * (1 - shrink))
                conn.execute(
                    "UPDATE orders SET discharged_kg = ?, variance_kg = ? WHERE id = ?",
                    (discharged, discharged - loaded_kg, order_id))

        # A trail of position pings for anything on the road.
        if status in ("in_transit", "at_pickup"):
            path = geo.route_nodes(frm, to)
            walked = path[: max(2, int(len(path) * 0.6))]
            stamp_pos = created + 7200
            for node_key in walked:
                n = geo.NODES[node_key]
                km_left = geo.route_km(node_key, to)
                conn.execute(
                    """INSERT INTO order_positions (order_id,lat,lng,node_key,place,km_done,km_left,
                         source,created_at) VALUES (?,?,?,?,?,?,?,'driver',?)""",
                    (order_id, n["lat"], n["lng"], node_key, n["name"],
                     max(0, q["distance_km"] - km_left), km_left, stamp_pos))
                stamp_pos += rng.randint(9000, 30000)
            last = geo.NODES[walked[-1]]
            conn.execute(
                "UPDATE orders SET last_lat=?, last_lng=?, last_place=?, last_ping_at=? WHERE id=?",
                (last["lat"], last["lng"], last["name"], stamp_pos, order_id))

        stages = ["placed", "assigned", "at_pickup", "in_transit", "delivered"]
        stamp = created
        for stage in stages[: stages.index(status) + 1]:
            conn.execute(
                "INSERT INTO events (order_id,status,note,actor,created_at) VALUES (?,?,?,?,?)",
                (order_id, stage, api.STATUS_LABEL[stage], "Musanga Control", stamp),
            )
            stamp += rng.randint(2400, 10800)

    # Committed tonnage, drawn down load by load. This is what a fertiliser
    # season or a grain export programme actually looks like on paper.
    CONTRACTS = [
        ("Omnia fertiliser distribution, 2026 season", "fertiliser", "superlink34",
         "kafue", "mkushi", 18000, 6420),
        ("Grain export programme, Central to Zimbabwe", "maize", "bulkgrain34",
         "mkushi", "harare", 12000, 2380),
        ("Kansanshi concentrate to Kasumbalesa", "copper_concentrate", "sidetipper34",
         "kalumbila", "kasumbalesa", 24000, 15300),
    ]
    for i, (name, commodity, equipment, frm, to, committed, called) in enumerate(CONTRACTS):
        q = pricing.quote(equipment, "contract", frm, to,
                          pricing.EQUIPMENT[equipment]["payload_t"], commodity)
        conn.execute(
            """INSERT INTO contracts (ref,shipper_id,name,commodity_key,equipment_key,from_zone,
                 to_zone,tonnes_committed,tonnes_called_off,rate_ngwee_per_tonne,currency,
                 tolerance_pct,starts_on,ends_on,status,created_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,0.5,?,?,'active',?)""",
            (db.new_ref("CTR"), shippers[i % len(shippers)], name, commodity, equipment, frm, to,
             committed, called, int(round(q["net_ngwee"] / q["billed_tonnes"])), q["currency"],
             now - 86400 * 60, now + 86400 * 120, now - 86400 * 60))

    for i, hire in enumerate(HIRES):
        (plant, site, address, contact, phone, purpose, days, operator, fuel, pay) = hire
        q = rental.quote(plant, site, days, with_operator=operator, with_fuel=fuel, with_waiver=True)
        created = now - (len(HIRES) - i) * 40000 - rng.randint(0, 7200)
        status = HIRE_PROGRESS[i]
        payment_status = "invoiced" if pay == "invoice" else ("paid" if status == "returned" else "pending")

        cur = conn.execute(
            """INSERT INTO hires (ref,hirer_id,plant_key,site_zone,site_address,site_contact,site_phone,
                 purpose,days,tier,depot_zone,float_km,with_operator,with_fuel,with_waiver,total_ngwee,
                 payment_method,payment_status,status,start_on,created_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,NULL,?)""",
            (db.new_ref("HIR"), shippers[i % len(shippers)], plant, site, address, contact, phone,
             purpose, q["days"], q["tier"], q["depot"], q["float_km"], int(q["with_operator"]),
             int(q["with_fuel"]), int(q["with_waiver"]), q["total_ngwee"], pay, payment_status,
             status, created),
        )
        hire_id = cur.lastrowid

        stages = ["requested", "confirmed", "on_site", "off_hire", "returned"]
        stamp = created
        for stage in stages[: stages.index(status) + 1]:
            conn.execute(
                "INSERT INTO hire_events (hire_id,status,note,actor,created_at) VALUES (?,?,?,?,?)",
                (hire_id, stage, api.HIRE_STATUS_LABEL[stage], "Musanga Control", stamp),
            )
            stamp += rng.randint(7200, 40000)

    seed_agreements(conn, now)

    conn.commit()
    conn.close()
    print("  Seeded %s users, %s transport partners, %s loads, %s hires -> %s"
          % (len(USERS), len(DRIVERS), len(LOADS), len(HIRES), db.DB_PATH))
    print("  Sign in with any phone number above, password: %s" % DEMO_PASSWORD)


if __name__ == "__main__":
    seed()
