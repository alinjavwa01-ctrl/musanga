"""Bulk freight rating, built up from what a trip actually costs to run.

A rate per tonne-kilometre is what the market quotes, but it is an output, not
an input. Underneath it sits diesel, tyres, the driver, the standing cost of
the unit, tolls in every country the lane touches, and a border bill that is
the same whether the trailer is full or half empty. So this engine costs the
trip first and derives the rate from it:

    cost   = fuel + tyres + maintenance + driver + standing + tolls
             + borders + handling + the empty leg back
    price  = cost / (1 - margin), floored at a minimum viable trip
    rate   = price / (billed tonnes x km)

That ordering is what lets the platform hold a rate on a 2,900 km Kalumbila to
Durban lane and a 55 km Lusaka to Chisamba run with the same code, and explain
either one line by line to a shipper who wants to argue about it.

All money is an integer of ngwee (1 ZMW = 100 ngwee); only the view divides.
Cross-border lanes are quoted in USD, because that is what the counterparty
contracts in, but they are still computed and stored in ngwee.
"""

from . import geo

# --- the cost basis -------------------------------------------------------
# Everything downstream is derived from these. They are the numbers to argue
# about in a rate review; the formulas themselves should not need to change.

DIESEL_NGWEE_PER_LITRE = 3400        # Zambian pump price for bulk diesel
FX_ZMW_PER_USD = 27.5                # used only to present cross-border rates

# Diesel is not the same price along the whole corridor, and a truck fills
# where it is cheapest. This is the multiplier on the Zambian pump price for
# the share of the lane run in each country.
FUEL_INDEX = {
    "ZM": 1.00, "CD": 1.28, "ZW": 1.24, "TZ": 1.02,
    "MW": 1.18, "MZ": 1.06, "ZA": 0.96, "BW": 0.94, "NA": 0.98, "AO": 0.72,
}

# Tolls and road access, ngwee per kilometre, per country. Zimbabwe is the
# expensive one: toll gates roughly every eighty kilometres and heavy-vehicle
# tariffs to match.
TOLL_NGWEE_PER_KM = {
    "ZM": 40, "CD": 95, "ZW": 330, "TZ": 60,
    "MW": 120, "MZ": 180, "ZA": 275, "BW": 90, "NA": 70, "AO": 60,
}

DRIVER_NGWEE_PER_DAY = 45000         # wage, plus a night-out allowance
CROSSBORDER_ALLOWANCE_NGWEE_PER_DAY = 55000   # subsistence in hard currency
STANDING_NGWEE_PER_DAY = 350000      # finance, fleet insurance, licences, depot
DRIVING_HOURS_PER_DAY = 10
AVG_MOVING_KPH = 50
LOADING_HOURS = 6
DISCHARGE_HOURS = 5

# --- equipment ------------------------------------------------------------
# Real trailer classes running the regional corridors. `payload_t` is the
# legal payload on a 56t GVM combination; consumption is measured laden.
EQUIPMENT = {
    "tipper30": {
        "name": "30t Tipper",
        "blurb": "Ore, coal, aggregate and anything that discharges by tipping",
        "payload_t": 30,
        "mobilisation_ngwee": 180000,
        "km_per_litre": 2.4,
        "km_per_litre_empty": 3.4,
        "tyre_ngwee_per_km": 120,
        "maintenance_ngwee_per_km": 190,
        "commodities": ["copper_ore", "coal", "aggregate", "limestone", "manganese"],
    },
    "sidetipper34": {
        "name": "34t Side Tipper",
        "blurb": "The Copperbelt workhorse for concentrate and bulk ore",
        "payload_t": 34,
        "mobilisation_ngwee": 210000,
        "km_per_litre": 2.2,
        "km_per_litre_empty": 3.2,
        "tyre_ngwee_per_km": 140,
        "maintenance_ngwee_per_km": 210,
        "commodities": ["copper_concentrate", "copper_ore", "coal", "manganese", "aggregate"],
    },
    "flatbed30": {
        "name": "30t Flatbed",
        "blurb": "Bagged, palletised and crated cargo under tarpaulin",
        "payload_t": 30,
        "mobilisation_ngwee": 150000,
        "km_per_litre": 2.6,
        "km_per_litre_empty": 3.6,
        "tyre_ngwee_per_km": 110,
        "maintenance_ngwee_per_km": 170,
        "commodities": ["copper_cathodes", "fertiliser", "cement", "maize", "soya", "general"],
    },
    "superlink34": {
        "name": "34t Superlink Tautliner",
        "blurb": "Curtain-sided, weatherproof, the regional export standard",
        "payload_t": 34,
        "mobilisation_ngwee": 190000,
        "km_per_litre": 2.5,
        "km_per_litre_empty": 3.5,
        "tyre_ngwee_per_km": 135,
        "maintenance_ngwee_per_km": 195,
        "commodities": ["copper_cathodes", "maize", "soya", "wheat", "fertiliser",
                        "sugar", "general"],
    },
    "bulkgrain34": {
        "name": "34t Bulk Grain Tipper",
        "blurb": "Food-grade tipping trailer, sealed and certified for grain in bulk",
        "payload_t": 34,
        "mobilisation_ngwee": 225000,
        "km_per_litre": 2.3,
        "km_per_litre_empty": 3.3,
        "tyre_ngwee_per_km": 140,
        "maintenance_ngwee_per_km": 205,
        "commodities": ["maize", "soya", "wheat", "sugar"],
    },
    "bulktanker": {
        "name": "40,000L Tanker",
        "blurb": "ADR-compliant for fuel, acid and mining reagents",
        "payload_t": 34,
        "mobilisation_ngwee": 260000,
        "km_per_litre": 2.3,
        "km_per_litre_empty": 3.3,
        "tyre_ngwee_per_km": 150,
        "maintenance_ngwee_per_km": 250,
        "commodities": ["fuel", "sulphuric_acid", "reagents"],
    },
    "lowbed": {
        "name": "Lowbed / Abnormal",
        "blurb": "Plant, fixed equipment and anything over-dimension",
        "payload_t": 60,
        "mobilisation_ngwee": 420000,
        "km_per_litre": 1.9,
        "km_per_litre_empty": 3.0,
        "tyre_ngwee_per_km": 190,
        "maintenance_ngwee_per_km": 300,
        "commodities": ["machinery", "plant"],
    },
}

# --- commodities ----------------------------------------------------------
# `factor` is a handling and risk load on the running cost, not a markup:
# acid needs an escort and a spill plan, grain needs a fumigated trailer and a
# weighbridge at each end, cathodes need a seal and a security escort.
COMMODITIES = {
    "copper_concentrate": {"name": "Copper concentrate", "factor": 1.14, "sector": "mining",      "hazard": False, "food_grade": False},
    "copper_cathodes":    {"name": "Copper cathodes",    "factor": 1.22, "sector": "mining",      "hazard": False, "food_grade": False},
    "copper_ore":         {"name": "Copper ore",         "factor": 1.00, "sector": "mining",      "hazard": False, "food_grade": False},
    "manganese":          {"name": "Manganese ore",      "factor": 1.05, "sector": "mining",      "hazard": False, "food_grade": False},
    "coal":               {"name": "Coal",               "factor": 0.96, "sector": "mining",      "hazard": False, "food_grade": False},
    "aggregate":          {"name": "Aggregate / stone",  "factor": 0.92, "sector": "mining",      "hazard": False, "food_grade": False},
    "limestone":          {"name": "Limestone",          "factor": 0.94, "sector": "mining",      "hazard": False, "food_grade": False},
    "sulphuric_acid":     {"name": "Sulphuric acid",     "factor": 1.55, "sector": "mining",      "hazard": True,  "food_grade": False},
    "reagents":           {"name": "Mining reagents",    "factor": 1.45, "sector": "mining",      "hazard": True,  "food_grade": False},
    "fuel":               {"name": "Diesel / fuel",      "factor": 1.48, "sector": "energy",      "hazard": True,  "food_grade": False},
    "maize":              {"name": "Maize",              "factor": 1.06, "sector": "agriculture", "hazard": False, "food_grade": True},
    "soya":               {"name": "Soya beans",         "factor": 1.08, "sector": "agriculture", "hazard": False, "food_grade": True},
    "wheat":              {"name": "Wheat",              "factor": 1.08, "sector": "agriculture", "hazard": False, "food_grade": True},
    "sugar":              {"name": "Sugar",              "factor": 1.06, "sector": "agriculture", "hazard": False, "food_grade": True},
    "fertiliser":         {"name": "Fertiliser",         "factor": 1.08, "sector": "agriculture", "hazard": False, "food_grade": False},
    "cement":             {"name": "Cement",             "factor": 1.04, "sector": "construction","hazard": False, "food_grade": False},
    "machinery":          {"name": "Machinery / plant",  "factor": 1.35, "sector": "mining",      "hazard": False, "food_grade": False},
    "plant":              {"name": "Fixed plant",        "factor": 1.40, "sector": "mining",      "hazard": False, "food_grade": False},
    "general":            {"name": "General cargo",      "factor": 1.00, "sector": "general",     "hazard": False, "food_grade": False},
}

SERVICE_LEVELS = {
    "spot":     {"name": "Spot load",     "blurb": "One load, priced today", "multiplier": 1.00, "lead_hours": 24},
    "priority": {"name": "Priority",      "blurb": "Truck positioned within 12 hours", "multiplier": 1.22, "lead_hours": 12},
    "contract": {"name": "Contract rate", "blurb": "Committed monthly tonnage, best rate", "multiplier": 0.90, "lead_hours": 48},
}

# A trip must bill at least this share of the trailer's payload - an operator
# cannot run a 600 km leg on eight tonnes of revenue.
MIN_BILLABLE_LOAD_RATIO = 0.60

# --- border costs ---------------------------------------------------------
# What it actually takes to get a laden truck through a post: the agent, the
# bond, the road fund levy, carbon tax and the temporary import permit. Posts
# differ enough that a single figure is a lie, so they are named.
BORDER_COSTS = {
    "Kasumbalesa":        {"clearing": 480000, "bond": 260000, "levies": 420000, "hours": 48},
    "Chirundu":           {"clearing": 320000, "bond": 210000, "levies": 300000, "hours": 22},
    "Beitbridge":         {"clearing": 350000, "bond": 240000, "levies": 340000, "hours": 30},
    "Nakonde / Tunduma":  {"clearing": 300000, "bond": 200000, "levies": 260000, "hours": 26},
    "Mwami / Mchinji":    {"clearing": 230000, "bond": 160000, "levies": 200000, "hours": 14},
    "Forbes / Machipanda":{"clearing": 260000, "bond": 180000, "levies": 230000, "hours": 18},
    "Kazungula Bridge":   {"clearing": 250000, "bond": 175000, "levies": 240000, "hours": 16},
    "Victoria Falls":     {"clearing": 240000, "bond": 170000, "levies": 220000, "hours": 16},
    "Wenela / Katima Mulilo": {"clearing": 230000, "bond": 160000, "levies": 200000, "hours": 14},
    "Cassacatiza":        {"clearing": 240000, "bond": 165000, "levies": 210000, "hours": 18},
    "Jimbe":              {"clearing": 280000, "bond": 190000, "levies": 250000, "hours": 24},
}
DEFAULT_BORDER_COST = {"clearing": 300000, "bond": 200000, "levies": 280000, "hours": 24}

# Cover on a cross-border leg is a different policy to a domestic one, and the
# Yellow Card is a per-trip cost on any lane leaving Zambia.
COMESA_YELLOW_CARD_NGWEE = 145000

HAZARD_PERMIT_NGWEE = 95000
ABNORMAL_LOAD_PERMIT_NGWEE = 380000
FOOD_GRADE_PREP_NGWEE = 68000        # wash-out, fumigation and the certificate
WEIGHBRIDGE_NGWEE = 22000            # one at each end, on cargo sold by weight

# --- the empty leg --------------------------------------------------------
# The cost that sinks operators. A truck that discharges at a mine gate has
# nothing to load back, and somebody pays for those kilometres. How much of
# the return leg we expect to sell depends on where the load ends.
BACKLOAD_ODDS = {
    "hub": 0.80, "port": 0.75, "industrial": 0.70, "market": 0.60,
    "border": 0.55, "agri": 0.35, "mine": 0.25,
}
DEFAULT_BACKLOAD_ODDS = 0.40

# --- the margin -----------------------------------------------------------
GROSS_MARGIN = 0.18                  # what the trip has to make over its cost
PLATFORM_TAKE_RATE = 0.12            # our share; the rest is the carrier's
VAT_RATE = 0.16                      # Zambian VAT, domestic lanes only
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


def _country_split(from_key, to_key, km):
    """Share of the lane's kilometres run in each country.

    Apportioned across the routed path, so a Kalumbila to Durban load is
    correctly charged Zimbabwean tolls for the Zimbabwean third of it.
    """
    path = geo.route_nodes(from_key, to_key)
    if len(path) < 2:
        return {geo.country_of(from_key): km}
    legs, total = [], 0.0
    for a, b in zip(path, path[1:]):
        hop = geo.ROAD_KM.get((a, b)) or geo.ROAD_KM.get((b, a)) or 0
        legs.append((geo.NODES[a]["country"], geo.NODES[b]["country"], float(hop)))
        total += hop
    if total <= 0:
        return {geo.country_of(from_key): km}
    split = {}
    for ca, cb, hop in legs:
        share = hop / total * km
        # A leg between two countries is half in each.
        if ca == cb:
            split[ca] = split.get(ca, 0.0) + share
        else:
            split[ca] = split.get(ca, 0.0) + share / 2
            split[cb] = split.get(cb, 0.0) + share / 2
    return split


def _fuel_cost(split, litres_per_km_basis, km):
    """Diesel over the lane, priced country by country."""
    total = 0.0
    for country, country_km in split.items():
        index = FUEL_INDEX.get(country, 1.0)
        total += country_km * litres_per_km_basis * DIESEL_NGWEE_PER_LITRE * index
    return total


def _toll_cost(split):
    return sum(country_km * TOLL_NGWEE_PER_KM.get(country, 60)
               for country, country_km in split.items())


def quote(equipment_key, service_key, from_key, to_key, tonnes, commodity_key="general",
          stops=0):
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

    try:
        stops = max(0, int(stops or 0))
    except (TypeError, ValueError):
        stops = 0

    km = geo.route_km(from_key, to_key)
    origin, destination = geo.node(from_key), geo.node(to_key)
    billed_t = max(tonnes, eq["payload_t"] * MIN_BILLABLE_LOAD_RATIO)

    posts = geo.crossings(from_key, to_key)
    export = geo.is_export(from_key, to_key)

    # --- the empty leg back -----------------------------------------------
    odds = BACKLOAD_ODDS.get(destination["kind"], DEFAULT_BACKLOAD_ODDS)
    empty_km = km * (1 - odds)

    split_loaded = _country_split(from_key, to_key, km)
    split_empty = _country_split(from_key, to_key, empty_km)

    # --- running cost ------------------------------------------------------
    fuel = _fuel_cost(split_loaded, 1.0 / eq["km_per_litre"], km)
    fuel += _fuel_cost(split_empty, 1.0 / eq["km_per_litre_empty"], empty_km)
    running_km = km + empty_km
    tyres = running_km * eq["tyre_ngwee_per_km"]
    maintenance = running_km * eq["maintenance_ngwee_per_km"]
    tolls = _toll_cost(split_loaded) + _toll_cost(split_empty)

    # --- time --------------------------------------------------------------
    border_hours = sum(BORDER_COSTS.get(p["post"], DEFAULT_BORDER_COST)["hours"] for p in posts)
    drive_hours = running_km / AVG_MOVING_KPH
    handling_hours = LOADING_HOURS + DISCHARGE_HOURS + (stops * 2.5)
    # Drivers cannot drive around the clock, so a long lane costs whole days.
    days = max(1.0, (drive_hours / DRIVING_HOURS_PER_DAY)
               + (border_hours + handling_hours) / 24.0)
    driver = days * DRIVER_NGWEE_PER_DAY
    if export:
        driver += days * CROSSBORDER_ALLOWANCE_NGWEE_PER_DAY
    standing = days * STANDING_NGWEE_PER_DAY

    # --- border bill -------------------------------------------------------
    border_lines = []
    borders = 0
    for p in posts:
        c = BORDER_COSTS.get(p["post"], DEFAULT_BORDER_COST)
        amount = c["clearing"] + c["bond"] + c["levies"]
        borders += amount
        border_lines.append({"label": "%s clearance, bond and levies" % p["post"], "ngwee": amount})
    yellow_card = COMESA_YELLOW_CARD_NGWEE if export else 0

    # --- cargo-specific ----------------------------------------------------
    hazard = HAZARD_PERMIT_NGWEE if commodity["hazard"] else 0
    abnormal = ABNORMAL_LOAD_PERMIT_NGWEE if equipment_key == "lowbed" else 0
    food_grade = FOOD_GRADE_PREP_NGWEE if commodity["food_grade"] else 0
    weighbridge = WEIGHBRIDGE_NGWEE * (2 + stops) if commodity["food_grade"] else 0
    mobilisation = eq["mobilisation_ngwee"]

    # Handling risk loads the running cost, not the pass-through costs: a
    # border fee is the same whatever is in the trailer.
    running = (fuel + tyres + maintenance + tolls + driver + standing) * commodity["factor"]
    multidrop = running * 0.04 * stops

    cost = (running + multidrop + mobilisation + borders + yellow_card
            + hazard + abnormal + food_grade + weighbridge)

    # --- price -------------------------------------------------------------
    price = cost / (1 - GROSS_MARGIN)
    service_adj = price * (service["multiplier"] - 1.0)
    net = int(round(max(MIN_TRIP_NGWEE, price + service_adj)))

    # Exports are zero-rated for Zambian VAT; domestic lanes are not.
    vat = 0 if export else int(round(net * VAT_RATE))
    total = net + vat

    transit_hours = drive_hours * (km / running_km if running_km else 1) \
        + handling_hours + border_hours
    rate_per_tkm = net / (billed_t * km) if billed_t and km else 0

    currency = "USD" if export else "ZMW"
    corridor = geo.corridor_for(from_key, to_key)

    lines = [
        {"label": "Diesel, %s km laden and %s km empty" % (int(km), int(empty_km)),
         "ngwee": int(round(fuel * commodity["factor"]))},
        {"label": "Tyres and maintenance", "ngwee": int(round((tyres + maintenance) * commodity["factor"]))},
        {"label": "Driver and subsistence, %.1f days" % days, "ngwee": int(round(driver * commodity["factor"]))},
        {"label": "Unit standing cost, %.1f days" % days, "ngwee": int(round(standing * commodity["factor"]))},
        {"label": "Tolls and road access", "ngwee": int(round(tolls * commodity["factor"]))},
        {"label": "Mobilisation (%s)" % eq["name"], "ngwee": mobilisation},
    ]
    lines.extend(border_lines)
    lines.extend([
        {"label": "COMESA Yellow Card", "ngwee": yellow_card},
        {"label": "Hazardous goods permit", "ngwee": hazard},
        {"label": "Abnormal load permit and escort", "ngwee": abnormal},
        {"label": "Food-grade wash-out and fumigation", "ngwee": food_grade},
        {"label": "Weighbridge tickets", "ngwee": weighbridge},
        {"label": "Multi-drop handling, %d extra stop%s" % (stops, "" if stops == 1 else "s"),
         "ngwee": int(round(multidrop))},
        {"label": "Margin", "ngwee": int(round(price - cost))},
        {"label": "%s adjustment" % service["name"], "ngwee": int(round(service_adj))},
    ])

    return {
        "equipment": equipment_key,
        "equipment_name": eq["name"],
        "service": service_key,
        "service_name": service["name"],
        "commodity": commodity_key,
        "commodity_name": commodity["name"],
        "from_zone": from_key,
        "to_zone": to_key,
        "from_name": origin["name"],
        "to_name": destination["name"],
        "distance_km": km,
        "empty_km": int(round(empty_km)),
        "backload_odds": round(odds, 2),
        "corridor": corridor["name"] if corridor else None,
        "export": export,
        "crossings": posts,
        "transit_countries": geo.transit_countries(from_key, to_key),
        "stops": stops,
        "tonnes": round(tonnes, 2),
        "billed_tonnes": round(billed_t, 2),
        "rate_per_tkm_ngwee": int(round(rate_per_tkm)),
        "transit_days": round(days, 1),
        "eta_minutes": int(round(transit_hours * 60)),
        "lines": lines,
        "cost_ngwee": int(round(cost)),
        "net_ngwee": net,
        "vat_ngwee": vat,
        "total_ngwee": total,
        "currency": currency,
        "fx_zmw_per_usd": FX_ZMW_PER_USD,
        "total_display": money(total, currency),
        "partner_payout_ngwee": int(round(net * (1 - PLATFORM_TAKE_RATE))),
        "platform_fee_ngwee": net - int(round(net * (1 - PLATFORM_TAKE_RATE))),
    }


def kwacha(ngwee):
    return "K%s" % format(ngwee / 100.0, ",.2f")


def usd(ngwee):
    return "$%s" % format(ngwee / 100.0 / FX_ZMW_PER_USD, ",.2f")


def money(ngwee, currency="ZMW"):
    return usd(ngwee) if currency == "USD" else kwacha(ngwee)


# The platform speaks one vocabulary; these keep older call sites working.
VEHICLES = EQUIPMENT
vehicle_list = equipment_list
