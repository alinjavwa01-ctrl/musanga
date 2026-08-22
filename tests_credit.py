#!/usr/bin/env python3
"""Unit tests for the carrier bundle: fuel credit and goods-in-transit cover.

Pure logic, no server and no database - run it anywhere:

    python3 tests_credit.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from musanga import fuel, insurance, pricing  # noqa: E402

PASS = FAIL = 0


def check(label, condition):
    global PASS, FAIL
    if condition:
        PASS += 1
        print("  ok    %s" % label)
    else:
        FAIL += 1
        print("  FAIL  %s" % label)


def raises(label, exc, fn, *args, **kwargs):
    try:
        fn(*args, **kwargs)
    except exc:
        check(label, True)
    except Exception as e:  # noqa: BLE001
        check("%s (raised %s instead)" % (label, type(e).__name__), False)
    else:
        check("%s (did not raise)" % label, False)


# --- entitlement ----------------------------------------------------------
print("\nentitlement")

e = fuel.entitlement("sidetipper34", 183.0)
check("a 183 km round trip in a side tipper is 180 litres", e["litres"] == 180)
check("entitlement is valued at the pump price",
      e["value_ngwee"] == 180 * fuel.DIESEL_NGWEE_PER_LITRE)

one_way = fuel.entitlement("sidetipper34", 183.0, round_trip=False)
check("a one-way leg is about half a round trip",
      abs(one_way["litres"] * 2 - e["litres"]) <= 1)

check("a thirstier class draws more over the same distance",
      fuel.litres_for_trip("lowbed", 183.0) > fuel.litres_for_trip("flatbed30", 183.0))
check("every equipment class has a burn rate",
      all("km_per_litre" in v for v in pricing.EQUIPMENT.values()))

raises("unknown equipment is refused", fuel.FuelError, fuel.entitlement, "spaceship", 100)
raises("a negative distance is refused", fuel.FuelError, fuel.entitlement, "tipper30", -5)
raises("a zero distance is refused", fuel.FuelError, fuel.entitlement, "tipper30", 0)


# --- limits ---------------------------------------------------------------
print("\nlimits")

starter = fuel.limit_for(0, 0, e["value_ngwee"])
check("a carrier with no history gets one trip's diesel",
      starter == e["value_ngwee"] * fuel.STARTER_TRIPS)
check("earnings do not lift the limit before the history does",
      fuel.limit_for(1, 50_000_00, e["value_ngwee"]) == starter)
check("history alone does not lift it either",
      fuel.limit_for(10, 0, e["value_ngwee"]) == starter)

proven = fuel.limit_for(10, 40_000_00, e["value_ngwee"])
check("a proven carrier's limit tracks earnings",
      proven == int(40_000_00 * fuel.LIMIT_EARNINGS_FACTOR))
check("the limit never falls below the starter",
      fuel.limit_for(10, 100, e["value_ngwee"]) == starter)
check("the cap binds however much is earned",
      fuel.limit_for(50, 999_999_00, e["value_ngwee"]) == fuel.LIMIT_CAP_NGWEE)
check("headroom is limit less outstanding", fuel.available(1000, 400) == 600)
check("headroom never goes negative", fuel.available(1000, 5000) == 0)


# --- draws ----------------------------------------------------------------
print("\ndraws at the pump")

ok = fuel.check_draw(160, fuel.DIESEL_NGWEE_PER_LITRE, e["litres"], starter, 0)
check("a draw inside both ceilings is approved", ok["litres"] == 160)
check("a draw is valued at the litre price",
      ok["value_ngwee"] == 160 * fuel.DIESEL_NGWEE_PER_LITRE)

raises("a draw over the load's entitlement is refused", fuel.FuelError,
       fuel.check_draw, 400, fuel.DIESEL_NGWEE_PER_LITRE, e["litres"], starter, 0)
raises("a draw over the facility is refused", fuel.FuelError,
       fuel.check_draw, 180, fuel.DIESEL_NGWEE_PER_LITRE, e["litres"], starter,
       starter)  # already fully drawn
raises("a zero draw is refused", fuel.FuelError,
       fuel.check_draw, 0, fuel.DIESEL_NGWEE_PER_LITRE, e["litres"], starter, 0)

check("entitlement binds even with a huge facility",
      fuel.available(fuel.LIMIT_CAP_NGWEE, 0) > e["value_ngwee"])


# --- netting --------------------------------------------------------------
print("\nsettlement netting")

n = fuel.netting(449_760, 1_481_356)
check("a balance under half the gross clears in one settlement", n["cleared"])
check("the carrier is paid the remainder",
      n["carrier_receives_ngwee"] == 1_481_356 - 449_760)

big = fuel.netting(1_400_000, 1_000_000)
check("never more than half the gross is taken", big["deduction_ngwee"] == 500_000)
check("a balance over half the gross rolls forward", not big["cleared"])
check("the rolled balance is exact", big["outstanding_after_ngwee"] == 900_000)
check("the carrier always leaves with something",
      big["carrier_receives_ngwee"] == 500_000)

zero = fuel.netting(0, 1_000_000)
check("no debt means no deduction", zero["deduction_ngwee"] == 0)
check("no debt pays the carrier in full", zero["carrier_receives_ngwee"] == 1_000_000)

check("a cancelled load with no payout takes nothing",
      fuel.netting(500_000, 0)["deduction_ngwee"] == 0)


# --- fuel margin ----------------------------------------------------------
print("\nfuel margin")

m = fuel.margin(160, cost_ngwee_per_litre=fuel.DIESEL_NGWEE_PER_LITRE - 80)
check("margin is the spread times the litres", m["margin_ngwee"] == 160 * 80)
check("no negotiated price means no margin",
      fuel.margin(160)["margin_ngwee"] == 0)
raises("buying above the ERB ceiling is refused", fuel.FuelError,
       fuel.margin, 160, None, fuel.DIESEL_NGWEE_PER_LITRE + 1)


# --- insurance ------------------------------------------------------------
print("\ngoods in transit")

i = insurance.quote("copper_concentrate", 11_900_000, to_zone="kasumbalesa")
check("premium is rated on declared value",
      i["premium_ngwee"] == 11_900_000 * i["rate_bp"] // 10_000)
check("commission is a slice of the premium",
      i["commission_ngwee"] == i["premium_ngwee"] * insurance.COMMISSION_BP // 10_000)
check("the insurer keeps the rest",
      i["insurer_receives_ngwee"] + i["commission_ngwee"] == i["premium_ngwee"])

check("hazardous cargo rates higher than benign",
      insurance.rate_bp("sulphuric_acid") > insurance.rate_bp("maize"))
check("a border destination loads the rate",
      insurance.rate_bp("maize", "kasumbalesa") > insurance.rate_bp("maize", "ndola"))
check("high-value metal loads the rate",
      insurance.rate_bp("copper_cathodes") > insurance.rate_bp("coal"))

small = insurance.quote("maize", 100_000)
check("a small load pays the minimum premium", small["at_minimum"])
check("the minimum is the floor", small["premium_ngwee"] == insurance.MIN_PREMIUM_NGWEE)

raises("an unknown commodity cannot be covered", insurance.InsuranceError,
       insurance.quote, "unobtainium", 100_000)
raises("a zero declared value is refused", insurance.InsuranceError,
       insurance.quote, "maize", 0)
raises("a negative declared value is refused", insurance.InsuranceError,
       insurance.quote, "maize", -1)


print("\n  %d passed, %d failed\n" % (PASS, FAIL))
sys.exit(1 if FAIL else 0)
