"""Request for prices and capacity - sent to transporters as a link.

An RFP is the freight version of a tender: Musanga has tonnage to move on a
lane in a window, and wants firm prices and firm capacity back. The wrong way
to run this is a WhatsApp thread and a spreadsheet; the right way is a link
per transporter, a form that asks for the numbers we need, and terms of
bidding that bind them to the insurance and indemnity we rely on the moment
we hand a load over.

The terms below are what a transporter agrees to when they submit a bid. They
are shorter than the master carrier agreement on purpose: the master is the
contract for the loads that follow; this is the promise the bid stands on. It
locks the price and capacity for the RFP window, requires the goods-in-transit
cover and the operator licences on which we rely, and confirms the transporter
is not on a sanctions list. What we sign at award is the carrier agreement (or
one already in place); what they sign here is the bid.

The body is frozen and hashed the moment the RFP is sent - so the text a
transporter agreed to is exactly the text on the record, and cannot be
quietly restated later.
"""

import hashlib
import re

from .agreements import COMPANY, _clean


TERMS = """MUSANGA REQUEST FOR PRICES AND CAPACITY - BIDDING TERMS

These are the terms on which {{counterparty}} (the "Carrier") submits a bid
to {{company_name}} ("Musanga") in response to RFP {{ref}}.

## 1. What the Carrier is bidding for

1.1 Musanga is inviting prices and firm capacity to move the loads described
    on the RFP page for the window shown. The Carrier's bid states its rate
    per tonne (or per trip, as marked), the number of trucks it will commit
    to the window, and the tonnage it can move in it.

## 2. The bid stands until the RFP closes

2.1 A bid submitted on this page is a firm offer. It stands until Musanga
    closes the RFP or until the date shown on the page, whichever is first,
    and may not be withdrawn or re-priced in that window.

2.2 Where Musanga awards all or part of the tonnage to the Carrier inside
    that window, the Carrier will carry the awarded loads at the rate bid
    and to the capacity bid.

## 3. Cover and licences the Carrier confirms

3.1 By signing, the Carrier confirms that for every load it would carry on
    an award under this RFP it holds and will keep current:

    (a) a road transport operator licence for the lane and every country the
        load transits;
    (b) motor and third-party cover current for the vehicles committed;
    (c) goods-in-transit cover at a sum insured of no less than
        {{cover_min}} per load, with Musanga noted as an interested party
        and the policy responsive to the commodity classes on the RFP;
    (d) certificates of fitness for every vehicle committed and licences for
        every driver committed.

3.2 The Carrier will produce copies of any of the above to Musanga on
    request, and Musanga may verify them directly with the insurer or the
    issuing authority.

## 4. Sanctions, anti-bribery and fitness to trade

4.1 The Carrier confirms that neither it, nor any person who owns or
    controls it, is on a sanctions list applied in Zambia or in any country
    the loads transit, and that it will not perform an award under this RFP
    while any of that changes.

4.2 The Carrier will not offer, pay or accept a bribe or a facilitation
    payment in connection with a load carried under an award of this RFP,
    including at a border post or a weighbridge.

## 5. Award, contracting and the master

5.1 Award is at Musanga's discretion. Musanga may award all, part or none of
    the tonnage; may split between carriers; and is not bound to accept the
    lowest bid.

5.2 The loads awarded are carried on the Musanga Carrier services agreement
    already in place with the Carrier, or on the one Musanga issues to the
    Carrier on award. Each load is confirmed by a rate confirmation issued
    through the platform.

5.3 Musanga settles awarded loads on the payment terms stated on the RFP
    page ({{payment_terms}}). The terms are legible before the Carrier
    submits a rate: the Carrier prices with the settlement schedule known.

## 6. If the Carrier does not honour the bid

6.1 Where the Carrier fails to present the equipment or the capacity it
    bid, Musanga may source the shortfall in the market and recover the
    difference between the bid and the sourced rate from the Carrier as
    liquidated damages, together with any positioning cost incurred.

6.2 Nothing in this clause limits Musanga's other remedies.

## 7. Confidentiality of the RFP

7.1 The RFP, the tonnage, the rates and any information disclosed on this
    page are confidential and are not disclosed by the Carrier to a third
    party except to submit and perform its bid.

## 8. Electronic signature and law

8.1 The parties agree that submitting this bid on the Musanga platform is
    an electronic signature to these terms and to the bid, and binds the
    Carrier as a wet signature would. The platform records the time, the
    address and the account the bid was placed from, and that record is the
    Carrier's signature to it.

8.2 These terms are governed by the laws of the Republic of Zambia and any
    dispute is referred to arbitration in Lusaka under the Arbitration Act
    No. 19 of 2000.
"""


PLACEHOLDER = re.compile(r"\{\{(\w+)\}\}")

DEFAULT_COVER_MIN = "K500,000"

# Payment terms are how Musanga settles awarded loads. Presenting them as a
# short list of legible options - not a free-text field - is how the supplier
# side becomes tradeable: a transporter knows exactly what "fast" costs
# compared to standard, and prices honestly against either. New presets go
# here in order of how commonly Musanga expects to use them.
PAYMENT_TERM_PRESETS = [
    ("net_30",        "Net 30 from POD received",
                      "Musanga settles the freight in full within 30 days of "
                      "receiving the signed proof of delivery."),
    ("split_33_33_34", "33% on loading, 33% on delivery, 34% on POD received",
                      "Musanga releases 33% once the load is on the truck and "
                      "the loading ticket is in, 33% on discharge, and the "
                      "final 34% within 5 days of receiving the signed POD."),
    ("split_50_50",   "50% on loading, 50% on POD received",
                      "Musanga releases 50% at loading against the loading "
                      "ticket, and 50% within 5 days of receiving the signed "
                      "proof of delivery."),
    ("fast_100",      "100% on loading",
                      "Musanga settles the whole freight at loading against the "
                      "loading ticket. Priced at a premium to the corridor "
                      "average, awarded on capacity and cover before rate."),
]

DEFAULT_PAYMENT_TERMS = PAYMENT_TERM_PRESETS[0][1]


def payment_terms_label(value):
    """Return a short label for whatever string is stored - matches a preset
    if there is one, otherwise falls back to the value itself. Used by the
    ops and public JSON so the UI can render the terms without knowing about
    presets."""
    if not value:
        return DEFAULT_PAYMENT_TERMS
    for _, label, _ in PAYMENT_TERM_PRESETS:
        if value == label:
            return label
    return value


def render(fields):
    """Fill the RFP terms body with the RFP's own reference, the transporter
    it went to, and the cover we need on the load. Left blanks show as a
    rule, the way the agreements module does it - a contract with a hole
    should look like one."""
    values = {
        "company_name": COMPANY["name"],
        "cover_min": DEFAULT_COVER_MIN,
        "payment_terms": DEFAULT_PAYMENT_TERMS,
    }
    values.update({k: v for k, v in (fields or {}).items() if v not in (None, "")})

    def fill(match):
        name = match.group(1)
        value = values.get(name)
        return str(value) if value not in (None, "") else "__________"

    return _clean(PLACEHOLDER.sub(fill, TERMS))


def digest(body):
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


STATUSES = ["open", "closed", "void"]
STATUS_LABEL = {"open": "Open for bids", "closed": "Closed", "void": "Voided"}

INVITE_STATUSES = ["sent", "opened", "submitted", "declined"]
INVITE_STATUS_LABEL = {
    "sent": "Sent",
    "opened": "Opened",
    "submitted": "Bid submitted",
    "declined": "Declined",
}

BID_STATUSES = ["submitted", "shortlisted", "declined", "awarded"]
BID_STATUS_LABEL = {
    "submitted": "Submitted",
    "shortlisted": "Shortlisted",
    "declined": "Declined",
    "awarded": "Awarded",
}
