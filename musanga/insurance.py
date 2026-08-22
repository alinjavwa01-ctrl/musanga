"""Goods-in-transit cover, placed as an agent.

This is the only line in the carrier bundle that costs nothing to run: no
capital, no credit exposure, no balance sheet. Musanga already knows the
commodity, the declared value, the corridor and the equipment - which is every
variable an underwriter prices on - so placing the cover is a short step from
work already done.

Musanga is an agent, not an underwriter. The premium belongs to the insurer;
only COMMISSION_BP is revenue. Do not net premium into platform income.

Rates below are placeholders in the shape of the real thing. They must be
replaced with a licensed insurer's actual schedule before anything is sold -
selling insurance in Zambia requires an intermediary licence, and quoting a
premium you cannot place is worse than quoting nothing.
"""

# Base rate on declared cargo value, in basis points (1 bp = 0.01%).
BASE_RATE_BP = 25

# Loadings on top of the base rate. Hazardous goods burn, leak and evacuate
# villages; export cargo crosses a border where it sits in a queue for days.
HAZARD_LOADING_BP = 20
BORDER_LOADING_BP = 8

# High-value metal is the theft target on these corridors.
HIGH_VALUE_COMMODITIES = ("copper_cathodes", "copper_concentrate")
HIGH_VALUE_LOADING_BP = 10

# No policy is written below this, whatever the cargo is worth.
MIN_PREMIUM_NGWEE = 45_000  # K450

# What the agent keeps. Confirm against the insurer's agency agreement.
COMMISSION_BP = 1250  # 12.5%


class InsuranceError(Exception):
    """A cover request could not be priced."""


def _is_border(to_zone):
    from . import geo
    node = geo.node(to_zone)
    return bool(node and node.get("kind") == "border")


def rate_bp(commodity_key, to_zone=None):
    """The rate applied to declared value, in basis points."""
    from . import pricing
    commodity = pricing.COMMODITIES.get(commodity_key)
    if not commodity:
        raise InsuranceError("Unknown commodity")

    bp = BASE_RATE_BP
    if commodity.get("hazard"):
        bp += HAZARD_LOADING_BP
    if commodity_key in HIGH_VALUE_COMMODITIES:
        bp += HIGH_VALUE_LOADING_BP
    if to_zone and _is_border(to_zone):
        bp += BORDER_LOADING_BP
    return bp


def quote(commodity_key, declared_value_ngwee, to_zone=None):
    """Price goods-in-transit cover for one load.

    Returns the premium (the insurer's) and the commission (ours), itemised so
    a shipper can see exactly what the cover costs and what we are paid to
    place it.
    """
    try:
        declared = int(declared_value_ngwee)
    except (TypeError, ValueError):
        raise InsuranceError("Declared value must be a whole number of ngwee")
    if declared <= 0:
        raise InsuranceError("Declared value must be positive")

    bp = rate_bp(commodity_key, to_zone)
    premium = max(MIN_PREMIUM_NGWEE, declared * bp // 10_000)
    commission = premium * COMMISSION_BP // 10_000

    return {
        "commodity_key": commodity_key,
        "declared_value_ngwee": declared,
        "rate_bp": bp,
        "premium_ngwee": premium,
        "commission_ngwee": commission,
        "insurer_receives_ngwee": premium - commission,
        "at_minimum": premium == MIN_PREMIUM_NGWEE,
    }
