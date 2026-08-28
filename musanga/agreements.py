"""Contracts a customer signs by link, and the templates they are built from.

How a freight customer actually signs today is: somebody emails a PDF, they
print it, sign it, photograph it and send it back, and three weeks later
nobody can find it. So agreements here work the way the customer already
expects from DocuSign - a link, a document, a signature, a copy - with no
account and no password in the way. The account is optional; the audit trail
is not.

What makes a signature defensible is not the image of it. It is the record of
what exact text was in front of the signer, when they opened it, from where,
and what they typed to adopt it. So the body is frozen and hashed at send,
and every touch on the document is written to `agreement_events` and never
updated.

Templates are plain text with {{placeholders}}. They are deliberately not
HTML: what is signed has to be exactly what was displayed, and text is the
only version of that which cannot be quietly restyled into meaning something
else.
"""

import hashlib
import re

COMPANY = {
    "name": "Musanga Logistics Limited",
    "short": "Musanga",
    "reg": "Registered in Zambia, company number 120180012345",
    "tpin": "TPIN 1001234567",
    "address": "Plot 4523, Great North Road, Lusaka, Zambia",
    "email": "contracts@musanga.com",
}

KINDS = {
    "quotation": "Quotation",
    "master": "Master agreement",
    "carrier": "Carrier agreement",
    "shipment": "Shipment agreement",
    "rate_schedule": "Rate schedule",
    "hire": "Plant hire agreement",
    "nda": "Non-disclosure agreement",
}

# Once a document is out for signature its text is fixed; these are the states
# it can be in and what may still be done to it.
STATUSES = ["draft", "sent", "viewed", "signed", "declined", "void"]
STATUS_LABEL = {
    "draft": "Draft",
    "sent": "Out for signature",
    "viewed": "Opened by signer",
    "signed": "Signed",
    "declined": "Declined",
    "void": "Voided",
}
OPEN_STATUSES = ("sent", "viewed")


def _clean(text):
    """Templates are written indented inside this file; the document is not."""
    return re.sub(r"\n{3,}", "\n\n", text.strip()) + "\n"


PREAMBLE = """This agreement is made between:

(1) {{company_name}}, {{company_reg}}, {{company_tpin}}, of {{company_address}}
    ("Musanga"); and

(2) {{counterparty}}{{counterparty_reg}}, of {{counterparty_address}}
    (the "Customer").

Reference: {{ref}}
Dated: {{dated}}
"""


QUOTATION = PREAMBLE + """
## 1. What we are quoting for

    Lane                 {{lane}}
    Loading point        {{pickup}}
    Discharge point      {{dropoff}}
    Distance             {{distance}}
    Border               {{crossings}}
    Commodity            {{commodity}}
    Equipment            {{equipment}}
    Tonnage              {{tonnage}}
    Loads                {{loads}}

## 2. The price

    Rate per tonne       {{rate}}
    Per load             {{per_load}}
    Total                {{total}}

2.1 Quoted in {{currency}}. {{tax_note}}

2.2 This quotation is valid until {{valid_until}}. After that it is re-rated
    against the diesel price and the border charges of the day.

## 3. What the price includes

{{included}}

## 4. What it excludes

4.1 Customs duty, VAT and any tax levied on the goods in the destination
    country.

4.2 Clearing agent fees, where the Customer appoints their own agent.

4.3 Standing time beyond {{free_hours}} hours free at each end, charged at
    {{demurrage}} per vehicle per day or part day.

4.4 Any charge arising from an instruction given after loading - a diversion,
    a second discharge point, a re-weigh, a return load.

## 5. How the load is run

5.1 The billing weight is the weighbridge ticket at loading, subject to the
    minimum billable tonnage for the equipment class. A variance at discharge
    of up to {{tolerance}} is normal handling loss; beyond that it is a
    shortage and is settled against the cover for the load.

5.2 The document checklist for this lane and commodity is raised against the
    booking on the Musanga platform, and each party files the documents it
    owns. The load does not pass a stage until the mandatory documents for
    that stage are on file. For this lane that means {{document_note}}.

5.3 The Customer is given a tracking reference and can follow the load without
    an account.

## 6. Payment

6.1 {{payment_terms}}

## 7. Accepting this quotation

7.1 Signing below accepts the rate and the terms above and authorises Musanga
    to plan against it. It is not itself a booking: each load is booked
    against this quotation on the platform or in writing, and carried on the
    Musanga terms of carriage or on any master agreement in force between the
    parties.

7.2 Musanga confirms equipment availability at the point of booking.
"""

MASTER = PREAMBLE + """
## 1. What this agreement covers

1.1 Musanga arranges and performs the road carriage of goods for the
    Customer on the corridors it operates in Zambia and the region, and
    provides the related services set out in this agreement.

1.2 This is a master agreement. It sets the terms on which every load is
    carried. It does not commit either party to any volume. Each load is
    booked separately, on the Musanga platform or in writing, and each
    booking is governed by this agreement.

1.3 Where a shipment agreement, rate schedule or written booking
    confirmation conflicts with this agreement, that document prevails for
    that load only, and only on the point of conflict.

## 2. Booking and acceptance

2.1 The Customer books a load by placing it on the platform or by written
    instruction accepted by Musanga. A booking is accepted when Musanga
    issues a booking reference.

2.2 Each booking states the equipment class, the commodity, the loading and
    discharge points, the tonnage and the rate. The Customer is responsible
    for the accuracy of what it declares, in particular the commodity, its
    weight and its hazard classification.

2.3 Musanga may decline a booking, and may withdraw from a load before
    loading, where the cargo is misdeclared, where the loading point is not
    safe or accessible, or where a permit required for the lane is not in
    place.

## 3. Rates, invoicing and payment

3.1 Rates are those in the rate schedule in force, or those quoted and
    accepted for the individual load. Rates are quoted per tonne or per trip
    as stated, exclusive of VAT.

3.2 Where a load is charged by weight, the weighbridge ticket at loading is
    the billing weight, subject to the minimum billable tonnage stated for
    the equipment class.

3.3 Payment terms are {{payment_terms}} from the date of invoice. Invoice
    terms are extended against a verified account and a current tax
    clearance certificate, and may be withdrawn on notice.

3.4 Interest on overdue amounts accrues at {{interest_rate}} per month,
    calculated daily, from the due date until payment.

3.5 The Customer may not withhold or set off any amount on account of a
    claim that has not been agreed or determined.

## 4. Fuel and cost adjustment

4.1 Rates are set against a diesel pump price of {{fuel_base}} per litre.

4.2 Where the pump price moves by more than {{fuel_band}} from that
    reference, either party may require the rates to be adjusted by the
    proportion of the rate attributable to fuel, on 14 days' written notice.
    Adjustments apply to loads booked after the notice takes effect.

## 5. Loading, discharge and standing time

5.1 The Customer provides safe access, and loads and discharges within
    {{free_hours}} hours of the vehicle presenting at the gate.

5.2 Standing time beyond the free hours is charged at {{demurrage}} per
    vehicle per day or part day.

5.3 The Customer is responsible for loading the vehicle correctly and within
    axle limits. Where the Customer or its agent loads, any fine, delay or
    damage arising from overloading or bad load distribution is for the
    Customer's account.

## 6. Weights, tolerance and shortage

6.1 Weight at loading and weight at discharge are both recorded on a
    certified weighbridge and both are recorded on the platform.

6.2 A variance of up to {{tolerance}} of the loading weight is treated as
    normal handling and moisture loss and is not a shortage.

6.3 A variance beyond that tolerance is a shortage, and is settled against
    the goods-in-transit cover in place for the load.

## 7. Cargo, cover and liability

7.1 Musanga carries goods-in-transit cover for every load it performs, at
    the sum insured stated in the booking. Cover is subject to the terms of
    the policy, including its exclusions.

7.2 Where the Customer does not declare a value, cover is limited to
    {{default_cover}} per load, which the Customer accepts is a limit set by
    the absence of a declaration and not a valuation of the goods.

7.3 Musanga is not liable for loss of profit, loss of contract, loss of
    market or any indirect or consequential loss, however arising.

7.4 A claim must be notified within 7 days of discharge, and supported
    within 30 days by the delivery note, both weighbridge tickets and an
    invoice for the goods. A claim notified outside those periods is time
    barred.

7.5 Nothing in this agreement limits liability for death or personal injury
    caused by negligence, or for fraud.

## 8. Documents and compliance

8.1 The Customer provides, in time for dispatch, every document the load
    requires from its side: permits, invoices, packing lists, certificates
    of origin, and anything the destination country requires of the
    consignee.

8.2 Musanga provides the consignment note, the carrier's licences and the
    cover certificate, and files them against the load on the platform.

8.3 Neither party will offer, pay or accept a bribe or a facilitation
    payment in connection with a load carried under this agreement. A breach
    of this clause entitles the other party to terminate immediately.

## 9. Sanctions, dangerous goods and prohibited cargo

9.1 The Customer will not tender cargo that is prohibited, or that would put
    either party in breach of a sanctions regime.

9.2 Dangerous goods are tendered only with a dangerous goods declaration and
    a material safety data sheet, and only against equipment certified for
    them.

## 10. Subcontracting

10.1 Musanga may perform a load through a vetted carrier on its network.
     Musanga remains responsible to the Customer for that carriage as if it
     had performed it itself.

## 11. Confidentiality and data

11.1 Rates, volumes and lane data disclosed under this agreement are
     confidential and are not disclosed to a third party except to perform a
     load, to a professional adviser, or where required by law.

11.2 Each party complies with the Data Protection Act, 2021 in respect of
     personal data it handles under this agreement, including driver and
     consignee contact details.

## 12. Force majeure

12.1 Neither party is liable for failure to perform caused by an event
     beyond its reasonable control, including border closure, civil unrest,
     flood, or the impassability of a road on the lane. The affected party
     notifies the other promptly and both act to limit the effect.

## 13. Term and termination

13.1 This agreement runs from {{starts_on}} for {{term}}, and continues
     after that until either party ends it on {{notice}} written notice.

13.2 Either party may terminate immediately where the other is in material
     breach and has not remedied it within 14 days of written notice, or
     where the other becomes insolvent.

13.3 Termination does not affect a load already in transit, which is
     completed and paid for under this agreement.

## 14. Governing law and disputes

14.1 This agreement is governed by the laws of the Republic of Zambia.

14.2 The parties will attempt to settle a dispute in good faith within 21
     days. Failing that, the dispute is referred to arbitration in Lusaka
     under the Arbitration Act No. 19 of 2000, before a single arbitrator.

## 15. Whole agreement

15.1 This agreement, with the rate schedule and the bookings made under it,
     is the whole agreement between the parties on its subject, and replaces
     anything said or written before it.

15.2 A variation is effective only when it is in writing and signed or
     accepted electronically by both parties. The parties agree that an
     electronic signature applied through the Musanga platform binds them as
     a wet signature would.
"""

CARRIER = PREAMBLE + """
## 1. What this agreement covers

1.1 The Carrier carries loads offered by Musanga on the Musanga platform, as
    an independent contractor. This agreement sets the terms of every load
    the Carrier accepts. It does not guarantee volume.

1.2 The Carrier is not an employee, agent or partner of Musanga, and has no
    authority to bind Musanga.

## 2. Accepting a load

2.1 A load is offered on the platform with the lane, the commodity, the
    tonnage, the equipment class and the payout. The Carrier accepts it on
    the platform, and acceptance creates a contract of carriage for that
    load on these terms.

2.2 Once accepted, the Carrier presents the agreed equipment, with a driver
    licensed for it, within the loading window.

2.3 A load may only be subcontracted with Musanga's prior written consent.

## 3. Payout and settlement

3.1 The payout for a load is the amount shown when the load is accepted.

3.2 Musanga settles {{payment_terms}} of a clean proof of delivery, with the
    delivery note and both weighbridge tickets filed on the platform.

3.3 Musanga may net against a settlement any fuel drawn against the load,
    any advance, and any amount the Carrier owes Musanga.

## 4. Compliance and equipment

4.1 The Carrier holds and keeps current: an RTSA road transport operator
    licence, certificates of fitness for every vehicle, motor and
    third-party cover, and goods-in-transit cover at the sum insured Musanga
    requires. Copies are filed on the platform and kept current.

4.2 The Carrier complies with drivers' hours, axle load limits and the road
    traffic law of every country it transits.

4.3 Musanga may withdraw a load, or suspend the Carrier from the platform,
    where a licence or a cover lapses.

## 5. The load in transit

5.1 The Carrier keeps the load on the agreed route, keeps the platform
    updated with position, and reports any delay, diversion, breakdown or
    incident immediately.

5.2 Seals are applied at loading and are broken only at discharge or by an
    authority, and any break is reported and recorded.

5.3 The Carrier does not part with the goods except to the consignee named
    in the consignment note, against signature.

## 6. Loss, damage and shortage

6.1 The Carrier is liable for loss of or damage to the goods in its
    possession, up to the sum insured for the load, save where caused by
    inherent vice, bad loading by the shipper, or an event beyond its
    reasonable control.

6.2 A shortage beyond the tolerance stated for the commodity is deducted
    from settlement or claimed against the Carrier's cover.

## 7. Fuel facility

7.1 Where Musanga extends a fuel facility, diesel drawn against a load is
    advanced, not paid, and is recovered from the settlement for that load.

7.2 The facility is a limit, not a commitment, and may be reduced or
    withdrawn at any time.

## 8. Anti-bribery, sanctions and conduct

8.1 The Carrier will not offer, pay or accept a bribe or a facilitation
    payment, including at a border post or a weighbridge, in connection with
    a load carried for Musanga.

8.2 The Carrier's drivers conduct themselves professionally at a customer's
    site and follow that site's safety rules.

## 9. Insurance, indemnity and liability

9.1 The Carrier indemnifies Musanga against any claim arising from its
    performance of a load, including third-party claims, fines and the cost
    of recovering a vehicle.

## 10. Term, suspension and termination

10.1 This agreement runs from {{starts_on}} until either party ends it on
     {{notice}} written notice.

10.2 Musanga may suspend the Carrier immediately where safety, a lapsed
     licence, a lapsed cover or a compliance failure requires it.

10.3 Termination does not affect a load in transit, which is completed and
     settled under this agreement.

## 11. Confidentiality

11.1 Rates, payouts, customer identities and lane data are confidential and
     are not disclosed or used outside performing loads for Musanga.

## 12. Governing law and disputes

12.1 This agreement is governed by the laws of the Republic of Zambia, and
     disputes are referred to arbitration in Lusaka under the Arbitration
     Act No. 19 of 2000.

12.2 The parties agree that an electronic signature applied through the
     Musanga platform binds them as a wet signature would.
"""

SHIPMENT = PREAMBLE + """
## 1. The load

This agreement covers one load, booked under {{master_reference}}.

    Booking reference    {{order_ref}}
    Commodity            {{commodity}}
    Equipment            {{equipment}}
    Loading point        {{pickup}}
    Discharge point      {{dropoff}}
    Corridor             {{corridor}}
    Distance             {{distance}}
    Tonnage              {{tonnage}}
    Rate                 {{rate}}
    All-in price         {{total}}
    Payment              {{payment}}
    Cover                {{cover}}

## 2. Terms that apply

2.1 This load is carried on the terms of {{master_reference}}. Where no
    master agreement is in force between the parties, the Musanga standard
    terms of carriage apply to this load, and are attached to the booking on
    the platform.

2.2 The figures above are the whole commercial agreement for this load. Any
    additional charge - standing time, a diversion, a second discharge point,
    a re-weigh - is charged only where this agreement or the master
    agreement provides for it.

## 3. Weights

3.1 The billing weight is the weighbridge ticket at loading, subject to the
    minimum billable tonnage for the equipment class.

3.2 A variance at discharge of up to {{tolerance}} is normal handling loss.
    Beyond that it is a shortage and is settled against the cover for this
    load.

## 4. Documents

4.1 The document checklist for this lane and commodity is generated on the
    platform against the booking reference above. Each party files the
    documents it owns, and the load does not pass a stage until the
    mandatory documents for that stage are on file.

## 5. Cancellation

5.1 Cancelled more than 24 hours before the loading window: no charge.

5.2 Cancelled inside 24 hours, or after the vehicle has been dispatched to
    the loading point: {{cancellation}} of the all-in price, to cover the
    positioning already performed.

## 6. Signature

6.1 Signing this agreement confirms the load, the rate and the terms above,
    and authorises Musanga to dispatch against it.
"""

RATE_SCHEDULE = PREAMBLE + """
## 1. What this schedule does

1.1 This schedule sets the rates that apply to loads booked under
    {{master_reference}}, from {{starts_on}} to {{ends_on}}.

1.2 It replaces any rate schedule previously in force between the parties.

## 2. Rates

{{rate_lines}}

2.1 Rates are per tonne unless stated otherwise, exclusive of VAT, and
    assume a full legal payload for the equipment class.

2.2 Rates include: the empty positioning leg, the driver, fuel at the
    reference price, tolls, and goods-in-transit cover at the standard sum
    insured.

2.3 Rates exclude: standing time beyond the free hours, customs duty and
    clearing agent fees, escort fees for abnormal loads, and any charge
    arising from an instruction given after loading.

## 3. Adjustment

3.1 Rates are set against a diesel pump price of {{fuel_base}} per litre and
    adjust as provided in the master agreement.

3.2 Rates are reviewed on {{review_date}}, or earlier where a road on the
    lane becomes impassable and the diversion adds more than 50 km.

## 4. Volume

4.1 Committed tonnage, where stated, is drawn down load by load on the
    platform against the contract reference, and both parties can see the
    balance at any time.
"""

HIRE = PREAMBLE + """
## 1. What is hired

    Machine              {{plant}}
    Site                 {{site}}
    Purpose              {{purpose}}
    Hire period          {{days}} from {{starts_on}}
    Rate                 {{rate}}
    Operator             {{operator}}
    Fuel                 {{fuel}}
    Damage waiver        {{waiver}}
    All-in price         {{total}}

## 2. Delivery and return

2.1 Musanga floats the machine to site and recovers it at the end of the
    hire. The Customer provides access for a low-bed and a hard standing to
    unload on.

2.2 The machine is inspected and its hour meter read at delivery and at
    recovery, and both readings are recorded on the platform.

## 3. Use of the machine

3.1 The machine is used only for the purpose stated, at the site stated, and
    only by an operator competent for it.

3.2 The machine is not moved to another site, sublet or used as security
    without Musanga's written consent.

3.3 The Customer keeps the machine in a secure position outside working
    hours and reports any breakdown, damage or incident immediately.

## 4. Hours, fuel and maintenance

4.1 The rate assumes {{hours_per_day}} working hours per day. Hours beyond
    that are charged pro rata.

4.2 Where fuel is not included, the Customer fuels the machine with clean
    diesel of the correct specification.

4.3 Musanga performs scheduled servicing. The Customer performs the daily
    checks the operator's handbook requires.

## 5. Risk, damage and waiver

5.1 Risk in the machine passes to the Customer on delivery to site and
    returns to Musanga on recovery.

5.2 Where the damage waiver is taken, the Customer's liability for accidental
    damage is limited to the excess stated in the booking. The waiver does
    not cover misuse, operation by an incompetent operator, submersion,
    theft where the site was left unsecured, or damage to tyres and glass.

5.3 Where the waiver is not taken, the Customer insures the machine for its
    replacement value and names Musanga as loss payee.

## 6. Off hire

6.1 Hire runs until the Customer calls the machine off hire on the platform
    and it is available for recovery. Idle time on site before that call is
    charged.

6.2 The machine is returned in the condition it was delivered in, fair wear
    and tear excepted, and clean enough to inspect.

## 7. Governing law

7.1 This agreement is governed by the laws of the Republic of Zambia and
    disputes are referred to arbitration in Lusaka under the Arbitration Act
    No. 19 of 2000.
"""

NDA = PREAMBLE + """
## 1. Purpose

1.1 The parties are discussing {{purpose}} and will each disclose
    confidential information for that purpose.

## 2. What is confidential

2.1 Confidential information is any information disclosed by one party to
    the other in connection with the purpose, including rates, volumes, lane
    data, customer identities, pricing models and operating data, whether or
    not it is marked confidential.

2.2 It does not include information that is public other than through a
    breach of this agreement, that the receiving party already held, or that
    it develops independently.

## 3. Obligations

3.1 The receiving party uses the information only for the purpose, discloses
    it only to those of its people and advisers who need it for the purpose
    and are under equivalent obligations, and protects it as it would its
    own confidential information.

3.2 Where disclosure is required by law or a regulator, the receiving party
    gives what notice it lawfully can before disclosing.

## 4. Return and term

4.1 On request, the receiving party returns or destroys the information,
    except one copy retained for compliance.

4.2 This agreement runs for {{term}} from the date above, and the
    obligations survive for {{survival}} after it ends.

## 5. No licence, no commitment

5.1 Nothing here transfers any intellectual property or commits either party
    to any transaction.

## 6. Governing law

6.1 This agreement is governed by the laws of the Republic of Zambia.
"""

TEMPLATES = {
    "quotation": {
        "kind": "quotation", "audience": "shipper",
        "name": "Quotation",
        "note": "A priced lane, valid for a period, that the customer accepts by signing.",
        "body": QUOTATION,
        "defaults": {
            "loads": "1", "free_hours": "24", "demurrage": "US$250",
            "tolerance": "0.5%", "payment_terms": "Payment in full before discharge, "
            "or 30 days from invoice against a verified account with a current tax "
            "clearance certificate.",
            "tax_note": "exclusive of VAT.",
            "included": "3.1 The truck, the driver, the fuel and the tolls.\n\n"
                        "3.2 The empty positioning leg to the loading point.\n\n"
                        "3.3 Goods-in-transit cover for the consignment.\n\n"
                        "3.4 Border clearance, bond and levies at the crossing named above.",
            "document_note": "the export paperwork listed on the booking",
        },
    },
    "master": {
        "kind": "master", "audience": "shipper",
        "name": "Master transport services agreement",
        "note": "The umbrella terms every load for this customer is carried on.",
        "body": MASTER,
        "defaults": {
            "payment_terms": "30 days", "interest_rate": "2%",
            "fuel_base": "K34.50", "fuel_band": "7.5%", "free_hours": "24",
            "demurrage": "K3,500", "tolerance": "0.5%", "default_cover": "K250,000",
            "starts_on": "", "term": "12 months", "notice": "60 days",
        },
    },
    "carrier": {
        "kind": "carrier", "audience": "carrier",
        "name": "Carrier services agreement",
        "note": "Terms for a transporter hauling loads off the Musanga board.",
        "body": CARRIER,
        "defaults": {"payment_terms": "within 7 days", "starts_on": "", "notice": "30 days"},
    },
    "shipment": {
        "kind": "shipment", "audience": "shipper",
        "name": "Shipment agreement",
        "note": "One load, its rate and its terms. Generated from a booking.",
        "body": SHIPMENT,
        "defaults": {"master_reference": "the Musanga standard terms of carriage",
                     "tolerance": "0.5%", "cancellation": "40%"},
    },
    "rate_schedule": {
        "kind": "rate_schedule", "audience": "shipper",
        "name": "Rate schedule",
        "note": "Lane rates for a period, hung off a master agreement.",
        "body": RATE_SCHEDULE,
        "defaults": {"master_reference": "the master agreement between the parties",
                     "fuel_base": "K34.50", "rate_lines": "    (rates to be inserted)"},
    },
    "hire": {
        "kind": "hire", "audience": "shipper",
        "name": "Plant hire agreement",
        "note": "One machine, on one site, for a period.",
        "body": HIRE,
        "defaults": {"hours_per_day": "9", "operator": "Included", "fuel": "Not included",
                     "waiver": "Taken"},
    },
    "nda": {
        "kind": "nda", "audience": "any",
        "name": "Mutual non-disclosure agreement",
        "note": "Before rates and volumes are exchanged.",
        "body": NDA,
        "defaults": {"purpose": "a potential freight arrangement",
                     "term": "2 years", "survival": "3 years"},
    },
}

PLACEHOLDER = re.compile(r"\{\{(\w+)\}\}")

# Placeholders that are allowed to be empty: a customer may have no
# registration number to quote, and that is not a hole in the document.
OPTIONAL = {"counterparty_reg", "trading_name"}


def template_list():
    return [{"key": key, "name": t["name"], "kind": t["kind"], "note": t["note"],
             "audience": t["audience"], "fields": sorted(fields_of(key)),
             "defaults": t["defaults"]}
            for key, t in TEMPLATES.items()]


def fields_of(template_key):
    """Every placeholder a template will ask for."""
    return set(PLACEHOLDER.findall(TEMPLATES[template_key]["body"]))


def render(template_key, context):
    """Fill a template. An unfilled placeholder is left visible as a blank
    rule rather than silently dropped - a contract with a hole in it should
    look like one."""
    template = TEMPLATES[template_key]
    values = dict(template["defaults"])
    values.update({k: v for k, v in (context or {}).items() if v not in (None, "")})
    values.setdefault("company_name", COMPANY["name"])
    values.setdefault("company_reg", COMPANY["reg"])
    values.setdefault("company_tpin", COMPANY["tpin"])
    values.setdefault("company_address", COMPANY["address"])

    def fill(match):
        name = match.group(1)
        value = values.get(name)
        if value not in (None, ""):
            return str(value)
        return "" if name in OPTIONAL else "__________"

    return _clean(PLACEHOLDER.sub(fill, template["body"]))


def digest(body):
    """The hash printed on the signed copy. If the text changes, this does."""
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def certificate(agreement, events):
    """The certificate of completion, in the same plain text as the document.

    This is what gets shown under the signature and travels with the copy:
    who signed, when, from what address, and against which version of the
    text.
    """
    lines = [
        "CERTIFICATE OF COMPLETION",
        "",
        "Document        %s" % agreement["title"],
        "Reference       %s" % agreement["ref"],
        "Document hash   %s" % agreement["body_hash"],
        "Parties         %s and %s" % (COMPANY["name"], agreement["counterparty"]),
        "",
        "Signed by       %s" % (agreement.get("signer_name") or "-"),
        "Title           %s" % (agreement.get("signer_title") or "-"),
        "Email           %s" % (agreement.get("signer_email") or "-"),
        "",
        "Audit trail",
    ]
    for e in events:
        lines.append("  %-19s %-22s %s" % (
            e.get("created_at_label") or "", EVENT_LABEL.get(e["event"], e["event"]),
            " ".join(filter(None, [e.get("actor"), e.get("ip")]))))
    return "\n".join(lines) + "\n"


EVENT_LABEL = {
    "created": "Drafted",
    "sent": "Sent for signature",
    "opened": "Opened by signer",
    "signed": "Signed",
    "declined": "Declined",
    "countersigned": "Countersigned by Musanga",
    "voided": "Voided",
    "downloaded": "Copy downloaded",
    "resent": "Link reissued",
}
