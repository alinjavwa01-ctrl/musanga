"""Plant hire.

The other half of the business: a site needs the machine, not a truck. Hire is
priced on a duration tier rather than distance - a day rate, a better week
rate, a better month rate - plus getting the unit to site and back.
"""

from . import geo

# Rates are in ngwee per period. `operator_day_ngwee` is the crew cost when the
# customer takes the machine wet-hired; dry hire is the machine alone.
PLANT = {
    "excavator20": {
        "name": "20t Excavator",
        "blurb": "Bulk earthworks, trenching, loading haul trucks",
        "category": "earthmoving",
        "day_ngwee": 480000,
        "week_ngwee": 2650000,
        "month_ngwee": 9200000,
        "operator_day_ngwee": 95000,
        "fuel_lph": 22,
        "transport_class": "lowbed",
    },
    "excavator30": {
        "name": "30t Excavator",
        "blurb": "Mine benches, mass excavation, heavy rock",
        "category": "earthmoving",
        "day_ngwee": 720000,
        "week_ngwee": 3950000,
        "month_ngwee": 13800000,
        "operator_day_ngwee": 110000,
        "fuel_lph": 32,
        "transport_class": "lowbed",
    },
    "wheelloader": {
        "name": "Wheel Loader",
        "blurb": "Stockpile handling, load-out, yard work",
        "category": "earthmoving",
        "day_ngwee": 420000,
        "week_ngwee": 2300000,
        "month_ngwee": 8000000,
        "operator_day_ngwee": 90000,
        "fuel_lph": 20,
        "transport_class": "lowbed",
    },
    "dozer": {
        "name": "Bulldozer D8",
        "blurb": "Push work, ripping, haul road formation",
        "category": "earthmoving",
        "day_ngwee": 780000,
        "week_ngwee": 4300000,
        "month_ngwee": 15000000,
        "operator_day_ngwee": 115000,
        "fuel_lph": 38,
        "transport_class": "lowbed",
    },
    "grader": {
        "name": "Motor Grader",
        "blurb": "Haul roads, farm tracks, site levelling",
        "category": "earthmoving",
        "day_ngwee": 520000,
        "week_ngwee": 2850000,
        "month_ngwee": 9900000,
        "operator_day_ngwee": 95000,
        "fuel_lph": 18,
        "transport_class": "lowbed",
    },
    "tlb": {
        "name": "TLB (Backhoe)",
        "blurb": "Service trenches, small civils, general site work",
        "category": "earthmoving",
        "day_ngwee": 260000,
        "week_ngwee": 1400000,
        "month_ngwee": 4800000,
        "operator_day_ngwee": 75000,
        "fuel_lph": 9,
        "transport_class": "flatbed30",
    },
    "adt": {
        "name": "Articulated Dump Truck",
        "blurb": "In-pit haulage, 30t off-road payload",
        "category": "earthmoving",
        "day_ngwee": 690000,
        "week_ngwee": 3800000,
        "month_ngwee": 13200000,
        "operator_day_ngwee": 105000,
        "fuel_lph": 34,
        "transport_class": "lowbed",
    },
    "crusher": {
        "name": "Mobile Jaw Crusher",
        "blurb": "On-site aggregate, 150 t/h throughput",
        "category": "processing",
        "day_ngwee": 1150000,
        "week_ngwee": 6300000,
        "month_ngwee": 22000000,
        "operator_day_ngwee": 140000,
        "fuel_lph": 45,
        "transport_class": "lowbed",
    },
    "drillrig": {
        "name": "Blasthole Drill Rig",
        "blurb": "Production drilling and grade control",
        "category": "processing",
        "day_ngwee": 1350000,
        "week_ngwee": 7400000,
        "month_ngwee": 26000000,
        "operator_day_ngwee": 165000,
        "fuel_lph": 40,
        "transport_class": "lowbed",
    },
    "crane50": {
        "name": "50t Mobile Crane",
        "blurb": "Plant installation, structural lifts",
        "category": "lifting",
        "day_ngwee": 890000,
        "week_ngwee": 4900000,
        "month_ngwee": 17000000,
        "operator_day_ngwee": 130000,
        "fuel_lph": 16,
        "transport_class": "lowbed",
    },
    "telehandler": {
        "name": "Telehandler",
        "blurb": "Yard lifting, bagged material, site logistics",
        "category": "lifting",
        "day_ngwee": 310000,
        "week_ngwee": 1700000,
        "month_ngwee": 5900000,
        "operator_day_ngwee": 78000,
        "fuel_lph": 11,
        "transport_class": "flatbed30",
    },
    "genset500": {
        "name": "500 kVA Generator",
        "blurb": "Site power, camp power, plant backup",
        "category": "support",
        "day_ngwee": 340000,
        "week_ngwee": 1850000,
        "month_ngwee": 6400000,
        "operator_day_ngwee": 0,
        "fuel_lph": 95,
        "transport_class": "flatbed30",
    },
    "bowser": {
        "name": "Water Bowser 16,000L",
        "blurb": "Dust suppression on haul roads and pads",
        "category": "support",
        "day_ngwee": 290000,
        "week_ngwee": 1580000,
        "month_ngwee": 5400000,
        "operator_day_ngwee": 72000,
        "fuel_lph": 14,
        "transport_class": "flatbed30",
    },
    "compactor": {
        "name": "Padfoot Compactor",
        "blurb": "Road base, embankments, tailings work",
        "category": "earthmoving",
        "day_ngwee": 300000,
        "week_ngwee": 1640000,
        "month_ngwee": 5700000,
        "operator_day_ngwee": 76000,
        "fuel_lph": 13,
        "transport_class": "flatbed30",
    },
}

CATEGORIES = {
    "earthmoving": "Earthmoving",
    "processing": "Processing & drilling",
    "lifting": "Lifting",
    "support": "Site support",
}

# Where hire fleet is staged. Mobilisation is charged from the nearest depot.
DEPOTS = ["lusaka", "ndola", "solwezi"]

# Duration tiers. Longer commitments earn the better daily rate.
WEEK_DAYS = 7
MONTH_DAYS = 30

# Moving the machine there and back, per kilometre, by transport class.
FLOAT_PER_KM_NGWEE = {"lowbed": 4200, "flatbed30": 2000}
# Out and back - the float returns empty.
FLOAT_LEGS = 2

# Diesel is billed at cost when Musanga fuels the machine.
DIESEL_NGWEE_PER_LITRE = 3450
SHIFT_HOURS = 9

# Optional damage waiver, priced off the hire value.
DAMAGE_WAIVER_RATE = 0.07

VAT_RATE = 0.16
MIN_HIRE_DAYS = 1
MAX_HIRE_DAYS = 365


class HireError(ValueError):
    pass


def plant_list():
    return [dict(key=k, **v) for k, v in PLANT.items()]


def category_list():
    return [{"key": k, "name": v} for k, v in CATEGORIES.items()]


def nearest_depot(site_key):
    """Closest staging depot to the site, and the road distance to it."""
    best, best_km = None, None
    for depot in DEPOTS:
        km = geo.route_km(depot, site_key)
        if best_km is None or km < best_km:
            best, best_km = depot, km
    return best, best_km


def _rate_for(machine, days):
    """Cheapest legitimate way to price this duration, and how it breaks down.

    A 9-day hire should never cost more than 2 weeks, so each tier is offered
    and the customer gets the lower of them.
    """
    options = []

    # Straight day rate.
    options.append(("day", days, machine["day_ngwee"] * days))

    # Whole weeks plus remainder days.
    weeks, rem = divmod(days, WEEK_DAYS)
    if weeks:
        options.append(("week", days, weeks * machine["week_ngwee"] + rem * machine["day_ngwee"]))
        # Rounding the remainder up to another whole week is often cheaper.
        options.append(("week", days, (weeks + (1 if rem else 0)) * machine["week_ngwee"]))

    # Whole months plus remainder priced the same way again.
    months, rem_days = divmod(days, MONTH_DAYS)
    if months:
        sub_weeks, sub_rem = divmod(rem_days, WEEK_DAYS)
        remainder = sub_weeks * machine["week_ngwee"] + sub_rem * machine["day_ngwee"]
        options.append(("month", days, months * machine["month_ngwee"] + remainder))
        options.append(("month", days, (months + (1 if rem_days else 0)) * machine["month_ngwee"]))

    tier, _, amount = min(options, key=lambda o: o[2])
    return tier, int(round(amount))


def quote(plant_key, site_key, days, with_operator=True, with_fuel=False, with_waiver=True):
    """Price one hire. Returns an itemised quote, all amounts in ngwee."""
    machine = PLANT.get(plant_key)
    if not machine:
        raise HireError("Unknown machine")
    if not geo.node(site_key):
        raise HireError("Unknown site")

    try:
        days = int(days)
    except (TypeError, ValueError):
        raise HireError("Hire length must be a whole number of days")
    if days < MIN_HIRE_DAYS:
        raise HireError("Minimum hire is %d day" % MIN_HIRE_DAYS)
    if days > MAX_HIRE_DAYS:
        raise HireError("Hires longer than a year are handled as a contract - talk to us")

    if with_operator and machine["operator_day_ngwee"] == 0:
        with_operator = False  # Nothing to crew on an unmanned unit.

    tier, hire = _rate_for(machine, days)

    depot, km = nearest_depot(site_key)
    float_rate = FLOAT_PER_KM_NGWEE[machine["transport_class"]]
    mobilisation = int(round(km * float_rate * FLOAT_LEGS))

    operator = machine["operator_day_ngwee"] * days if with_operator else 0
    fuel = int(round(machine["fuel_lph"] * SHIFT_HOURS * days * DIESEL_NGWEE_PER_LITRE)) if with_fuel else 0
    waiver = int(round(hire * DAMAGE_WAIVER_RATE)) if with_waiver else 0

    net = hire + mobilisation + operator + fuel + waiver
    vat = int(round(net * VAT_RATE))
    total = net + vat

    return {
        "plant": plant_key,
        "plant_name": machine["name"],
        "category": machine["category"],
        "site": site_key,
        "site_name": geo.node(site_key)["name"],
        "days": days,
        "tier": tier,
        "depot": depot,
        "depot_name": geo.node(depot)["name"],
        "float_km": km,
        "with_operator": bool(with_operator),
        "with_fuel": bool(with_fuel),
        "with_waiver": bool(with_waiver),
        "effective_day_ngwee": int(round(hire / float(days))),
        "lines": [
            {"label": "%s, %d day%s (%s rate)" % (machine["name"], days, "" if days == 1 else "s", tier),
             "ngwee": hire},
            {"label": "Float from %s, %d km each way" % (geo.node(depot)["name"], int(km)), "ngwee": mobilisation},
            {"label": "Operator, %d day%s" % (days, "" if days == 1 else "s"), "ngwee": operator},
            {"label": "Diesel at cost, %d h/day" % SHIFT_HOURS, "ngwee": fuel},
            {"label": "Damage waiver", "ngwee": waiver},
        ],
        "net_ngwee": net,
        "vat_ngwee": vat,
        "total_ngwee": total,
    }
