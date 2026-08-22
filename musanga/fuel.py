"""Fuel credit: entitlement, limits and settlement netting.

The carrier's binding constraint is diesel, not cash. So Musanga never advances
money - it extends fuel against a load it has already assigned, and nets the
balance off the settlement it is already holding. Nothing leaves the business
that is not already covered by work done.

Three rules carry the whole product:

1.  ENTITLEMENT is computed per load, not per truck. We know the corridor
    distance and the equipment class, so we know a Kansanshi -> Kasumbalesa run
    in a 34t side tipper is 166 litres and not 300. A generic fuel card cannot
    do this, because it does not know what the truck is carrying. This is the
    fraud control.

2.  THE LIMIT is sized to what the carrier has actually earned on the platform,
    and starts at one trip. A carrier with no history gets one trip's diesel.

3.  NETTING takes the outstanding balance or half the load's gross, whichever
    is less. Half, not all: take the whole settlement and the carrier cannot
    afford to run the next load, which ends the relationship and the debt.

Money is integer ngwee throughout, litres are whole litres. Diesel is priced at
the ERB pump ceiling, which moves monthly - see DIESEL_NGWEE_PER_LITRE.
"""

import math

from . import pricing

# ERB maximum pump price for diesel, in ngwee per litre. Reviewed monthly by the
# regulator; SI 77 of 2024 makes this a ceiling, so a negotiated bulk price sits
# at or below it. Update when the ERB publishes.
DIESEL_NGWEE_PER_LITRE = 2811

# Real trips burn more than the arithmetic: idling at the border, detours,
# gradient on the North-Western corridors, and a cold start every morning.
BURN_TOLERANCE = 0.08

# A load is fuelled out and back. A carrier that finds a backhaul keeps the
# difference, which is the incentive we want.
ROUND_TRIP = 2

# What a carrier with no completed loads may draw, as a multiple of the first
# load's own entitlement. One trip: enough to start, not enough to disappear.
STARTER_TRIPS = 1

# Above the starter, the limit tracks earnings. Half of an average week's payout
# is roughly two trips' diesel - enough to keep a truck moving while a
# settlement is in flight.
LIMIT_EARNINGS_FACTOR = 0.5

# Loads that must be completed before the earnings-based limit replaces the
# starter limit.
LIMIT_MIN_HISTORY = 3

# No carrier draws more than this regardless of earnings. Concentration risk:
# one carrier absconding should never be material.
LIMIT_CAP_NGWEE = 5_000_000  # K50,000

# Share of a load's gross payout that may be taken to clear fuel debt.
NETTING_SHARE = 0.5


class FuelError(Exception):
    """A fuel facility rule was broken."""


def litres_for_trip(equipment_key, distance_km, round_trip=True):
    """Diesel a load should need, in whole litres.

    Rounded up: an entitlement that is a litre short strands a truck.
    """
    eq = pricing.EQUIPMENT.get(equipment_key)
    if not eq:
        raise FuelError("Unknown equipment class")
    kmpl = eq.get("km_per_litre")
    if not kmpl:
        raise FuelError("No burn rate recorded for %s" % equipment_key)
    try:
        distance_km = float(distance_km)
    except (TypeError, ValueError):
        raise FuelError("Distance must be a number")
    if distance_km <= 0:
        raise FuelError("Distance must be positive")

    legs = ROUND_TRIP if round_trip else 1
    return int(math.ceil(distance_km * legs / kmpl * (1 + BURN_TOLERANCE)))


def entitlement(equipment_key, distance_km, round_trip=True, price_ngwee=None):
    """What one load may draw. Returns litres and the kwacha value."""
    litres = litres_for_trip(equipment_key, distance_km, round_trip)
    price = DIESEL_NGWEE_PER_LITRE if price_ngwee is None else int(price_ngwee)
    return {
        "litres": litres,
        "price_ngwee_per_litre": price,
        "value_ngwee": litres * price,
        "equipment_key": equipment_key,
        "distance_km": float(distance_km),
        "round_trip": bool(round_trip),
    }


def limit_for(completed_loads, avg_weekly_payout_ngwee, starter_entitlement_ngwee):
    """The carrier's facility ceiling.

    Below LIMIT_MIN_HISTORY completed loads the carrier gets the starter limit
    and nothing more, however much they have billed - a carrier can run up
    earnings on someone else's authority, but they cannot run up history here.
    """
    starter = int(starter_entitlement_ngwee) * STARTER_TRIPS
    if int(completed_loads) < LIMIT_MIN_HISTORY:
        return max(0, starter)

    earned = int(int(avg_weekly_payout_ngwee) * LIMIT_EARNINGS_FACTOR)
    # Never below the starter: a proven carrier should not be squeezed by a
    # quiet fortnight.
    return max(starter, min(earned, LIMIT_CAP_NGWEE))


def available(limit_ngwee, outstanding_ngwee):
    """Headroom left on the facility."""
    return max(0, int(limit_ngwee) - int(outstanding_ngwee))


def check_draw(litres, price_ngwee_per_litre, entitlement_litres,
               limit_ngwee, outstanding_ngwee):
    """Approve or refuse one draw at the pump.

    Two ceilings apply and both bind: the load's own entitlement, and the
    carrier's facility. The entitlement stops a driver filling a second tank on
    our account; the facility stops the exposure compounding across loads.
    """
    litres = int(litres)
    if litres <= 0:
        raise FuelError("Draw must be a positive number of litres")
    if litres > int(entitlement_litres):
        raise FuelError(
            "Draw of %d litres exceeds the %d litres this load is entitled to"
            % (litres, entitlement_litres))

    value = litres * int(price_ngwee_per_litre)
    headroom = available(limit_ngwee, outstanding_ngwee)
    if value > headroom:
        raise FuelError(
            "Draw of K%.2f exceeds the K%.2f left on the facility"
            % (value / 100.0, headroom / 100.0))
    return {"litres": litres, "value_ngwee": value}


def netting(outstanding_ngwee, gross_payout_ngwee, share=NETTING_SHARE):
    """How much of one settlement clears fuel debt.

    The balance or `share` of the gross, whichever is less. The remainder rolls
    to the next load rather than emptying this one.
    """
    outstanding = max(0, int(outstanding_ngwee))
    gross = max(0, int(gross_payout_ngwee))
    deduction = min(outstanding, int(gross * share))
    return {
        "deduction_ngwee": deduction,
        "carrier_receives_ngwee": gross - deduction,
        "outstanding_after_ngwee": outstanding - deduction,
        "cleared": outstanding - deduction == 0,
    }


def margin(litres, pump_ngwee_per_litre=None, cost_ngwee_per_litre=None):
    """What Musanga keeps on volume bought below the ERB ceiling.

    The regulator caps the pump price; the whole upside is the discount
    negotiated into the OMC and dealer margins underneath it.
    """
    pump = DIESEL_NGWEE_PER_LITRE if pump_ngwee_per_litre is None else int(pump_ngwee_per_litre)
    if cost_ngwee_per_litre is None:
        return {"litres": int(litres), "margin_ngwee": 0, "spread_ngwee_per_litre": 0}
    cost = int(cost_ngwee_per_litre)
    if cost > pump:
        raise FuelError("Cost per litre cannot exceed the pump ceiling")
    spread = pump - cost
    return {
        "litres": int(litres),
        "spread_ngwee_per_litre": spread,
        "margin_ngwee": int(litres) * spread,
    }
