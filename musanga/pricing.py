"""Bulk freight rating.

Mining and agricultural haulage is not priced like a parcel. The industry
quotes a rate per tonne per kilometre, with a minimum billable tonnage so a
half-empty trailer still covers the trip. That is what this engine does:

    freight = tonnes_billed x km x rate_per_tonne_km x commodity x corridor
    + fixed costs (loading, border clearance, waiting)

All money is an integer of ngwee (1 ZMW = 100 ngwee); only the view divides.
"""

from . import geo

# --- equipment ------------------------------------------------------------
# Real trailer classes running Zambian corridors. `payload_t` is the legal
# payload, `mobilisation_ngwee` covers hooking up and positioning the unit.
EQUIPMENT = {
    "tipper30": {
        "name": "30t Tipper",
        "blurb": "Ore, coal, aggregate and anything that discharges by tipping",
        "payload_t": 30,
        "rate_per_tkm_ngwee": 190,
        "mobilisation_ngwee": 180000,
        "avg_speed_kph": 45,
        "km_per_litre": 2.4,
        "commodities": ["copper_ore", "coal", "aggregate", "limestone", "manganese"],
    },
    "sidetipper34": {
        "name": "34t Side Tipper",
        "blurb": "The Copperbelt workhorse for concentrate and bulk ore",
        "payload_t": 34,
        "rate_per_tkm_ngwee": 175,
        "mobilisation_ngwee": 210000,
        "avg_speed_kph": 45,
        "km_per_litre": 2.2,
        "commodities": ["copper_concentrate", "copper_ore", "coal", "manganese", "aggregate"],
    },
    "flatbed30": {
        "name": "30t Flatbed",
        "blurb": "Cathodes, bagged fertiliser, cement and palletised freight",
        "payload_t": 30,
        "rate_per_tkm_ngwee": 200,
        "mobilisation_ngwee": 175000,
        "avg_speed_kph": 50,
        "km_per_litre": 2.6,
        "commodities": ["copper_cathodes", "fertiliser", "cement", "maize", "soya", "general"],
    },
    "superlink34": {
        "name": "34t Superlink",
        "blurb": "Two trailers, maximum payload on the long export runs",
        "payload_t": 34,
        "rate_per_tkm_ngwee": 168,
        "mobilisation_ngwee": 230000,
        "avg_speed_kph": 48,
        "km_per_litre": 2.2,
        "commodities": ["copper_cathodes", "maize", "soya", "wheat", "fertiliser", "general"],
    },
    "bulktanker": {
        "name": "40,000L Tanker",
        "blurb": "Fuel, sulphuric acid and liquid reagents, ADR-certified",
        "payload_t": 33,
        "rate_per_tkm_ngwee": 255,
        "mobilisation_ngwee": 320000,
        "avg_speed_kph": 42,
        "km_per_litre": 2.3,
        "commodities": ["fuel", "sulphuric_acid", "reagents"],
    },
    "lowbed": {
        "name": "Lowbed / Abnormal",
        "blurb": "Excavators, crushers, mills and abnormal-load plant",
        "payload_t": 60,
        "rate_per_tkm_ngwee": 340,
        "mobilisation_ngwee": 650000,
        "avg_speed_kph": 32,
        "km_per_litre": 1.8,
        "commodities": ["machinery", "plant"],
    },
}

# --- commodities ----------------------------------------------------------
# `factor` prices the risk and handling each cargo carries; `hazard` cargo
# needs certified equipment and escorts, which is why it costs what it does.
COMMODITIES = {
    "copper_concentrate": {"name": "Copper concentrate", "factor": 1.14, "sector": "mining",      "hazard": False},
    "copper_cathodes":    {"name": "Copper cathodes",    "factor": 1.22, "sector": "mining",      "hazard": False},
    "copper_ore":         {"name": "Copper ore",         "factor": 1.00, "sector": "mining",      "hazard": False},
    "manganese":          {"name": "Manganese ore",      "factor": 1.05, "sector": "mining",      "hazard": False},
    "coal":               {"name": "Coal",               "factor": 0.96, "sector": "mining",      "hazard": False},
    "aggregate":          {"name": "Aggregate / stone",  "factor": 0.92, "sector": "mining",      "hazard": False},
    "limestone":          {"name": "Limestone",          "factor": 0.94, "sector": "mining",      "hazard": False},
    "sulphuric_acid":     {"name": "Sulphuric acid",     "factor": 1.55, "sector": "mining",      "hazard": True},
    "reagents":           {"name": "Mining reagents",    "factor": 1.45, "sector": "mining",      "hazard": True},
    "fuel":               {"name": "Diesel / fuel",      "factor": 1.48, "sector": "energy",      "hazard": True},
    "maize":              {"name": "Maize",              "factor": 1.00, "sector": "agriculture", "hazard": False},
    "soya":               {"name": "Soya beans",         "factor": 1.02, "sector": "agriculture", "hazard": False},
    "wheat":              {"name": "Wheat",              "factor": 1.02, "sector": "agriculture", "hazard": False},
    "fertiliser":         {"name": "Fertiliser",         "factor": 1.08, "sector": "agriculture", "hazard": False},
    "cement":             {"name": "Cement",             "factor": 1.04, "sector": "construction","hazard": False},
    "machinery":          {"name": "Machinery / plant",  "factor": 1.35, "sector": "mining",      "hazard": False},
    "plant":              {"name": "Fixed plant",        "factor": 1.40, "sector": "mining",      "hazard": False},
    "general":            {"name": "General cargo",      "factor": 1.00, "sector": "general",     "hazard": False},
}

# --- contract types -------------------------------------------------------
SERVICE_LEVELS = {
    "spot":     {"name": "Spot load",     "blurb": "One load, priced today", "multiplier": 1.00, "lead_hours": 24},
    "priority": {"name": "Priority",      "blurb": "Truck positioned within 12 hours", "multiplier": 1.30, "lead_hours": 12},
    "contract": {"name": "Contract rate", "blurb": "Committed monthly tonnage, best rate", "multiplier": 0.86, "lead_hours": 48},
}

# A trip must bill at least this share of the trailer's payload - an operator
# cannot run a 600 km leg on eight tonnes of revenue.
MIN_BILLABLE_LOAD_RATIO = 0.60

# Export legs need clearing agents, bonds and queue time at the post.
BORDER_CLEARANCE_NGWEE = 145000
HAZARD_PERMIT_NGWEE = 95000
ABNORMAL_LOAD_PERMIT_NGWEE = 380000

# Long runs amortise the mobilisation better, so the rate tapers.
LONG_HAUL_KM = 400
LONG_HAUL_TAPER = 0.93

# A leg that ends where loads originate can be backfilled, so it is discounted.
BACKHAUL_DISCOUNT = 0.91

# Border queues and mine weighbridges add real hours to a transit estimate.
BORDER_DELAY_HOURS = 14
LOADING_HOURS = 6

PLATFORM_TAKE_RATE = 0.15  # thinner than parcel work; the ticket sizes are large
VAT_RATE = 0.16
MIN_TRIP_NGWEE = 250000


class QuoteError(ValueError):
    pass


def equipment_list():
    return [dict(key=k, **v) for k, v in EQUIPMENT.items()]


def commodity_list():
    return [dict(key=k, **v) for k, v in COMMODITIES.items()]


def service_list():
    return [dict(key=k, **v) for k, v in SERVICE_LEVELS.items()]


def equipment_for(commodity_key):
    """Which trailers may legally and practically carry this cargo."""
    return [k for k, v in EQUIPMENT.items() if commodity_key in v["commodities"]]


def quote(equipment_key, service_key, from_key, to_key, tonnes, commodity_key="general"):
    """Rate one trip. Returns an itemised quote, all amounts in ngwee."""
    eq = EQUIPMENT.get(equipment_key)
    if not eq:
        raise QuoteError("Unknown equipment class")
    service = SERVICE_LEVELS.get(service_key)
    if not service:
        raise QuoteError("Unknown contract type")
    commodity = COMMODITIES.get(commodity_key)
    if not commodity:
        raise QuoteError("Unknown commodity")

    try:
        tonnes = float(tonnes or 0)
    except (TypeError, ValueError):
        raise QuoteError("Tonnage must be a number")
    if tonnes <= 0:
        raise QuoteError("Enter the tonnage to move")
    if tonnes > eq["payload_t"]:
        raise QuoteError(
            "%.1f t exceeds the %s t payload of a %s - split the consignment across loads"
            % (tonnes, eq["payload_t"], eq["name"])
        )
    if commodity_key not in eq["commodities"]:
        raise QuoteError("A %s cannot carry %s" % (eq["name"], commodity["name"].lower()))

    km = geo.route_km(from_key, to_key)
    billed_t = max(tonnes, eq["payload_t"] * MIN_BILLABLE_LOAD_RATIO)

    rate = eq["rate_per_tkm_ngwee"]
    if km >= LONG_HAUL_KM:
        rate = rate * LONG_HAUL_TAPER

    linehaul = int(round(billed_t * km * rate * commodity["factor"]))
    mobilisation = eq["mobilisation_ngwee"]

    origin, destination = geo.node(from_key), geo.node(to_key)
    border = BORDER_CLEARANCE_NGWEE if "border" in (origin["kind"], destination["kind"]) else 0
    hazard = HAZARD_PERMIT_NGWEE if commodity["hazard"] else 0
    abnormal = ABNORMAL_LOAD_PERMIT_NGWEE if equipment_key == "lowbed" else 0

    subtotal = linehaul + mobilisation + border + hazard + abnormal
    service_adj = int(round(subtotal * (service["multiplier"] - 1.0)))

    # Running back into a loading hub means the return leg can be sold again.
    backhaul = 0
    if destination["kind"] in ("hub", "industrial") and km >= 150:
        backhaul = -int(round((subtotal + service_adj) * (1 - BACKHAUL_DISCOUNT)))

    net = max(MIN_TRIP_NGWEE, subtotal + service_adj + backhaul)
    vat = int(round(net * VAT_RATE))
    total = net + vat

    transit_hours = km / eq["avg_speed_kph"] + LOADING_HOURS + (BORDER_DELAY_HOURS if border else 0)

    return {
        "equipment": equipment_key,
        "equipment_name": eq["name"],
        "service": service_key,
        "service_name": service["name"],
        "commodity": commodity_key,
        "commodity_name": commodity["name"],
        "from_zone": from_key,
        "to_zone": to_key,
        "distance_km": km,
        "tonnes": round(tonnes, 2),
        "billed_tonnes": round(billed_t, 2),
        "rate_per_tkm_ngwee": int(round(rate)),
        "eta_minutes": int(round(transit_hours * 60)),
        "lines": [
            {"label": "Linehaul %.1f t x %s km" % (billed_t, int(km)), "ngwee": linehaul},
            {"label": "Mobilisation (%s)" % eq["name"], "ngwee": mobilisation},
            {"label": "Border clearance", "ngwee": border},
            {"label": "Hazardous goods permit", "ngwee": hazard},
            {"label": "Abnormal load permit and escort", "ngwee": abnormal},
            {"label": "%s adjustment" % service["name"], "ngwee": service_adj},
            {"label": "Backhaul credit", "ngwee": backhaul},
        ],
        "net_ngwee": net,
        "vat_ngwee": vat,
        "total_ngwee": total,
        "partner_payout_ngwee": int(round(net * (1 - PLATFORM_TAKE_RATE))),
        "platform_fee_ngwee": net - int(round(net * (1 - PLATFORM_TAKE_RATE))),
    }


def kwacha(ngwee):
    return "K%s" % format(ngwee / 100.0, ",.2f")


# The platform speaks one vocabulary; these keep older call sites working.
VEHICLES = EQUIPMENT
vehicle_list = equipment_list
