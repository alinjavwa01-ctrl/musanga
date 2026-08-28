"""Know-your-customer: what an account has to prove before it can trade.

The signup is deliberately thin - a name, a phone, a password - because the
cost of making someone assemble their PACRA file before they can even see a
rate is that they never come back. So an account exists from the first screen
and can quote, browse the load board and look around, but it cannot commit
money or steel until it is verified: no loads booked, no machines hired, no
jobs accepted, no fuel drawn.

Everything that gets an account from `unverified` to `verified` is here:
which business details are needed, which company and tax documents, and who
has to be named. The rest of the platform asks this module two questions -
"what is still outstanding?" and "may this account do X?" - and nothing else.
"""

# --- account states -------------------------------------------------------
# unverified -> in_review -> verified, with rejected as a terminal-ish state
# that ops can put back into the applicant's hands.
STATUSES = ["unverified", "in_review", "verified", "rejected"]
STATUS_LABEL = {
    "unverified": "Not verified",
    "in_review": "In review",
    "verified": "Verified",
    "rejected": "Needs attention",
}

# What a limited-mode account may not do. The message is what the customer
# reads, so it says what to do next rather than what went wrong.
GATED = {
    "book_load": "Verify your business before booking a load",
    "hire_plant": "Verify your business before renting a machine",
    "accept_job": "Verify your operation before accepting a load",
    "draw_fuel": "Verify your operation before drawing fuel",
    "credit_terms": "Invoice terms open once your business is verified",
}

# --- entity types ---------------------------------------------------------
ENTITIES = {
    "limited": {
        "name": "Limited company",
        "note": "Registered with PACRA as a private or public limited company.",
        "fields": ["legal_name", "reg_number", "tin", "country", "address", "sector"],
        "people": "directors",
    },
    "sole_trader": {
        "name": "Sole trader",
        "note": "A business name registered to one person, or an owner-driver.",
        "fields": ["legal_name", "reg_number", "tin", "country", "address"],
        "people": "owner",
    },
    "partnership": {
        "name": "Partnership",
        "fields": ["legal_name", "reg_number", "tin", "country", "address"],
        "people": "partners",
    },
    "cooperative": {
        "name": "Cooperative or association",
        "fields": ["legal_name", "reg_number", "tin", "country", "address"],
        "people": "committee",
    },
    "individual": {
        "name": "Individual",
        "note": "No registered business - a driver trading in their own name.",
        "fields": ["legal_name", "tin", "country", "address"],
        "people": "self",
    },
}

FIELD_LABEL = {
    "legal_name": "Registered legal name",
    "trading_name": "Trading name",
    "reg_number": "Registration number (PACRA)",
    "tin": "Taxpayer identification number (TPIN)",
    "vat_number": "VAT registration number",
    "country": "Country of registration",
    "address": "Registered business address",
    "sector": "Industry",
}

# --- document catalogue ---------------------------------------------------
# `group` is only how the checklist reads on screen. `mandatory` is what
# actually stops a submission.

GROUPS = ["company", "tax", "people", "operating", "banking"]
GROUP_LABEL = {
    "company": "Company documents",
    "tax": "Tax documents",
    "people": "Identity of the people behind it",
    "operating": "Operating licences",
    "banking": "Banking",
}


def _doc(key, name, group, mandatory=True, note="", expires=False):
    return {"key": key, "name": name, "group": group, "mandatory": mandatory,
            "note": note, "expires": expires}


COMPANY_DOCS = [
    _doc("cert_incorporation", "Certificate of incorporation", "company",
         note="PACRA Form 2 or the certificate itself."),
    _doc("pacra_printout", "PACRA company printout, dated in the last 6 months", "company",
         note="Shows current directors and shareholding.", expires=True),
    _doc("share_register", "Share register or ownership statement", "company", mandatory=False,
         note="Needed when the printout does not show shareholding."),
]

SOLE_DOCS = [
    _doc("business_name_cert", "Business name registration certificate", "company"),
]

TAX_DOCS = [
    _doc("tpin_cert", "ZRA taxpayer registration certificate (TPIN)", "tax"),
    _doc("tax_clearance", "ZRA tax clearance certificate", "tax",
         note="Current year. Invoice terms are not opened without it.", expires=True),
    _doc("vat_cert", "VAT registration certificate", "tax", mandatory=False,
         note="Only if the business is VAT registered."),
]

PEOPLE_DOCS = [
    _doc("director_id", "NRC or passport for every director and 25%+ owner", "people"),
    _doc("proof_address", "Proof of business address", "people",
         note="Utility bill, lease or council rates notice, under 3 months old.", expires=True),
]

BANK_DOCS = [
    _doc("bank_letter", "Bank confirmation letter", "banking",
         note="On the bank's letterhead, showing the account the platform pays."),
]

# A carrier is also a road transport operator, and that carries its own file.
CARRIER_DOCS = [
    _doc("operator_licence", "RTSA road transport operator licence", "operating", expires=True),
    _doc("git_insurance", "Goods-in-transit insurance schedule", "operating", expires=True,
         note="Sum insured per load, with Musanga noted as an interested party."),
    _doc("motor_insurance", "Motor and third-party insurance certificate", "operating", expires=True),
    _doc("fleet_list", "Fleet list with plates, fitness and horsepower", "operating"),
    _doc("cross_border_permit", "Cross-border road transport permit", "operating", mandatory=False,
         expires=True, note="Only if you run the export corridors."),
]

# Ops accounts are staff. They are verified by being employed, not by filing.
STAFF_ROLES = ("ops",)


def catalogue(role, entity_type, vat_registered=False, cross_border=False):
    """The document checklist for one account, from its role and entity type."""
    entity_type = entity_type if entity_type in ENTITIES else "limited"
    out = []
    if entity_type in ("limited", "partnership", "cooperative"):
        out += COMPANY_DOCS
    elif entity_type == "sole_trader":
        out += SOLE_DOCS
    if entity_type != "individual":
        out += TAX_DOCS
    else:
        out += [d for d in TAX_DOCS if d["key"] == "tpin_cert"]
    out += PEOPLE_DOCS
    if role == "driver":
        out += CARRIER_DOCS
    else:
        out += BANK_DOCS

    adjusted = []
    for d in out:
        d = dict(d)
        if d["key"] == "vat_cert" and vat_registered:
            d["mandatory"] = True
        if d["key"] == "cross_border_permit" and cross_border:
            d["mandatory"] = True
        adjusted.append(d)

    seen, deduped = set(), []
    for d in adjusted:
        if d["key"] in seen:
            continue
        seen.add(d["key"])
        deduped.append(d)
    deduped.sort(key=lambda d: GROUPS.index(d["group"]))
    return deduped


def profile_fields(entity_type):
    entity = ENTITIES.get(entity_type) or ENTITIES["limited"]
    return list(entity["fields"])


def missing_fields(profile):
    """Business details still blank on the profile."""
    if not profile:
        return profile_fields("limited")
    return [f for f in profile_fields(profile.get("entity_type"))
            if not str(profile.get(f) or "").strip()]


def people_rule(entity_type):
    """How many people have to be named, and whether ownership is asked for."""
    if entity_type == "individual":
        return {"minimum": 1, "ownership": False,
                "note": "Name yourself, with the NRC or passport you trade under."}
    if entity_type == "sole_trader":
        return {"minimum": 1, "ownership": False,
                "note": "Name the owner of the business."}
    return {"minimum": 1, "ownership": True,
            "note": "Every director, and every person holding 25% or more. "
                    "One of them must be named as the control person."}


def missing_people(entity_type, people):
    """Why the named people are not yet enough."""
    rule = people_rule(entity_type)
    problems = []
    if len(people) < rule["minimum"]:
        problems.append("Name at least %d person" % rule["minimum"])
        return problems
    if rule["ownership"]:
        if not any(p.get("is_control") for p in people):
            problems.append("Mark one person as the control person")
        owned = sum(float(p.get("ownership_pct") or 0) for p in people)
        if owned > 100.5:
            problems.append("Declared ownership adds up to more than 100%")
    if any(not str(p.get("id_number") or "").strip() for p in people):
        problems.append("Every person needs an NRC or passport number")
    return problems


def outstanding(role, profile, people, filed_keys):
    """Everything between this account and a submission it can defend.

    Returns the checklist with each item resolved, plus the blocking reasons.
    `filed_keys` is the set of document keys already on file and not rejected.
    """
    profile = profile or {}
    entity_type = profile.get("entity_type") or "limited"
    docs = catalogue(role, entity_type,
                     vat_registered=bool(profile.get("vat_registered")),
                     cross_border=bool(profile.get("cross_border")))
    for d in docs:
        d["filed"] = d["key"] in filed_keys
    blockers = []
    for field in missing_fields(profile):
        blockers.append(FIELD_LABEL.get(field, field))
    blockers += missing_people(entity_type, people or [])
    blockers += [d["name"] for d in docs if d["mandatory"] and not d["filed"]]
    return docs, blockers


def can(user, action):
    """Whether a verified-only action is open to this account."""
    if action not in GATED:
        return True
    if user.get("role") in STAFF_ROLES:
        return True
    return user.get("kyc_status") == "verified"
