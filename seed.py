#!/usr/bin/env python3
"""Reset the database and fill it with a realistic week on the corridors.

Deterministic: same data every run, so demos and screenshots are stable.
"""

import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from musanga import api, db, docs, geo, pricing, rental  # noqa: E402

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

    conn.commit()
    conn.close()
    print("  Seeded %s users, %s transport partners, %s loads, %s hires -> %s"
          % (len(USERS), len(DRIVERS), len(LOADS), len(HIRES), db.DB_PATH))
    print("  Sign in with any phone number above, password: %s" % DEMO_PASSWORD)


if __name__ == "__main__":
    seed()
