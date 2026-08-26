"""What paperwork a load actually needs, worked out from the lane and cargo.

A truck is not stopped at Chirundu because nobody phoned ahead. It is stopped
because the export permit is in someone's inbox in Lusaka. So the platform
treats documents as part of the load, not as an attachment to it: every order
gets a checklist derived from where it is going and what is on it, each item
owned by somebody and due at a stage, and the load cannot pass that stage
until the mandatory ones are on file.

`stage` is when the document has to exist, and it maps onto the order status
flow: 'booking' before a truck is committed, 'loading' before it leaves the
origin, 'border' before it reaches the first post, 'delivery' to close.
"""

from . import geo

STAGES = ["booking", "loading", "border", "delivery"]
STAGE_LABEL = {
    "booking": "Before dispatch",
    "loading": "At loading",
    "border": "Before the border",
    "delivery": "On delivery",
}
OWNERS = {"shipper": "Shipper", "carrier": "Carrier", "musanga": "Musanga", "agent": "Clearing agent"}


def _doc(key, name, owner, stage, mandatory=True, note=""):
    return {"key": key, "name": name, "owner": owner, "stage": stage,
            "mandatory": mandatory, "note": note}


# --- always ---------------------------------------------------------------
BASE = [
    _doc("consignment_note", "Road consignment note", "musanga", "loading",
         note="Issued against the booking reference; the contract of carriage."),
    _doc("delivery_note", "Delivery note, signed at discharge", "carrier", "delivery",
         note="Signed and stamped by the receiving party."),
    _doc("goods_cover", "Goods-in-transit cover certificate", "musanga", "booking"),
    _doc("driver_licence", "Driver licence and defensive driving permit", "carrier", "booking"),
    _doc("fitness", "Certificate of fitness and roadworthiness", "carrier", "booking"),
    _doc("operator_licence", "RTSA operator and carrier licence", "carrier", "booking"),
]

# --- cargo sold by weight -------------------------------------------------
WEIGHED = [
    _doc("weighbridge_loading", "Weighbridge ticket at loading", "shipper", "loading",
         note="Gross, tare and net. This is the figure the shipper is invoiced on."),
    _doc("weighbridge_discharge", "Weighbridge ticket at discharge", "carrier", "delivery",
         note="Reconciled against loading weight; variance beyond tolerance is flagged."),
]

# --- food grade -----------------------------------------------------------
FOOD_GRADE = [
    _doc("washout", "Trailer wash-out and fumigation certificate", "carrier", "loading"),
    _doc("grade_cert", "Grading and moisture certificate", "shipper", "loading",
         note="Grade, moisture content and screenings at intake."),
]

# --- hazardous ------------------------------------------------------------
HAZARD = [
    _doc("dg_declaration", "Dangerous goods declaration", "shipper", "loading"),
    _doc("adr_cert", "ADR tanker certification and calibration chart", "carrier", "booking"),
    _doc("msds", "Material safety data sheet", "shipper", "booking"),
    _doc("spill_plan", "Emergency response and spill plan", "carrier", "loading"),
]

# --- mining ---------------------------------------------------------------
MINERALS = [
    _doc("assay", "Assay certificate", "shipper", "loading",
         note="Grade on which the consignment is valued."),
    _doc("seal_record", "Seal numbers recorded at loading", "carrier", "loading"),
]
MINERAL_EXPORT = [
    _doc("mineral_export_permit", "Mineral export permit", "shipper", "booking",
         note="Ministry of Mines; the load cannot be dispatched without it."),
]

# --- any export -----------------------------------------------------------
EXPORT = [
    _doc("commercial_invoice", "Commercial invoice", "shipper", "booking"),
    _doc("packing_list", "Packing list", "shipper", "booking"),
    _doc("customs_declaration", "Customs export declaration", "agent", "border",
         note="Lodged by the clearing agent ahead of the post."),
    _doc("origin_cert", "Certificate of origin", "shipper", "border",
         note="COMESA or SADC, whichever gives the better duty treatment."),
    _doc("transit_bond", "Transit bond", "agent", "border"),
    _doc("yellow_card", "COMESA Yellow Card", "carrier", "border",
         note="Third-party motor cover valid across the transit countries."),
    _doc("driver_passport", "Driver passport and visa", "carrier", "border"),
    _doc("gate_pass", "Border gate pass and manifest", "agent", "border"),
]

# --- agricultural export --------------------------------------------------
AGRI_EXPORT = [
    _doc("export_permit", "Agricultural export permit", "shipper", "booking",
         note="Ministry of Agriculture; grain permits are issued per season and per tonnage."),
    _doc("phytosanitary", "Phytosanitary certificate", "shipper", "border",
         note="ZARI inspection at origin; the destination will not release without it."),
    _doc("fumigation_cert", "Fumigation certificate for the consignment", "shipper", "border"),
]

# --- per-country arrival --------------------------------------------------
COUNTRY_DOCS = {
    "ZW": [_doc("zw_tip", "Zimbabwe temporary import permit", "agent", "border"),
           _doc("zw_import_licence", "Zimbabwe import licence for the consignee", "shipper", "border",
                note="Grain imports are controlled; the buyer holds this, not the shipper.")],
    "CD": [_doc("cd_tip", "DRC temporary import permit", "agent", "border"),
           _doc("cd_import_decl", "DRC import declaration (Déclaration)", "agent", "border")],
    "TZ": [_doc("tz_tip", "Tanzania temporary import permit", "agent", "border")],
    "MW": [_doc("mw_tip", "Malawi temporary import permit", "agent", "border")],
    "MZ": [_doc("mz_tip", "Mozambique temporary import permit", "agent", "border")],
    "ZA": [_doc("za_tip", "South Africa cross-border road transport permit", "carrier", "border")],
    "BW": [_doc("bw_tip", "Botswana temporary import permit", "agent", "border")],
    "NA": [_doc("na_tip", "Namibia cross-border permit", "agent", "border")],
    "AO": [_doc("ao_tip", "Angola temporary import permit", "agent", "border")],
}


def required_for(commodity_key, from_key, to_key, equipment_key=None):
    """The document checklist for one lane and cargo, deduplicated and
    ordered by the stage it is due at."""
    from . import pricing  # imported here to keep the module dependency one-way

    commodity = pricing.COMMODITIES.get(commodity_key, {})
    export = geo.is_export(from_key, to_key)
    sector = commodity.get("sector")

    out = list(BASE)
    if commodity.get("food_grade") or sector == "agriculture" or commodity_key == "cement":
        out += WEIGHED
    if sector == "mining":
        out += WEIGHED + MINERALS
    if commodity.get("food_grade"):
        out += FOOD_GRADE
    if commodity.get("hazard"):
        out += HAZARD
    if equipment_key == "lowbed":
        out.append(_doc("abnormal_permit", "Abnormal load permit and escort order", "musanga", "loading"))

    if export:
        out += EXPORT
        if sector == "agriculture":
            out += AGRI_EXPORT
        if sector == "mining":
            out += MINERAL_EXPORT
        for country in geo.transit_countries(from_key, to_key):
            if country == geo.country_of(from_key):
                continue
            out += COUNTRY_DOCS.get(country, [])

    seen, deduped = set(), []
    for d in out:
        if d["key"] in seen:
            continue
        seen.add(d["key"])
        deduped.append(d)
    deduped.sort(key=lambda d: STAGES.index(d["stage"]))
    return deduped


def blocking(checklist, held_keys, stage):
    """Mandatory documents due at or before `stage` that are not yet on file."""
    limit = STAGES.index(stage)
    return [d for d in checklist
            if d["mandatory"] and STAGES.index(d["stage"]) <= limit
            and d["key"] not in held_keys]
