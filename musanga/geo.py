"""Zambia's freight geography: mining nodes, farming blocks, borders and hubs.

Bulk freight does not move between suburbs, it moves along corridors. So the
network is modelled as named nodes on the trunk road system, with real road
distances for the corridors we actually run and a haversine estimate as the
fallback for any pair we have not measured.
"""

import math

# kind drives what a node is for: 'mine', 'agri', 'border', 'hub', 'industrial'.
NODES = {
    # --- Copperbelt & North-Western: the mining heartland ------------------
    "kitwe":       {"name": "Kitwe",             "lat": -12.8024, "lng": 28.2132, "kind": "mine",       "region": "Copperbelt"},
    "ndola":       {"name": "Ndola",             "lat": -12.9587, "lng": 28.6366, "kind": "hub",        "region": "Copperbelt"},
    "chingola":    {"name": "Chingola",          "lat": -12.5289, "lng": 27.8492, "kind": "mine",       "region": "Copperbelt"},
    "mufulira":    {"name": "Mufulira",          "lat": -12.5497, "lng": 28.2408, "kind": "mine",       "region": "Copperbelt"},
    "luanshya":    {"name": "Luanshya",          "lat": -13.1367, "lng": 28.4166, "kind": "mine",       "region": "Copperbelt"},
    "solwezi":     {"name": "Solwezi",           "lat": -12.1688, "lng": 26.3894, "kind": "mine",       "region": "North-Western"},
    "kalumbila":   {"name": "Kalumbila",         "lat": -12.2833, "lng": 25.3167, "kind": "mine",       "region": "North-Western"},
    "lumwana":     {"name": "Lumwana",           "lat": -12.1500, "lng": 25.8500, "kind": "mine",       "region": "North-Western"},
    "kabwe":       {"name": "Kabwe",             "lat": -14.4469, "lng": 28.4464, "kind": "industrial", "region": "Central"},
    "maamba":      {"name": "Maamba Collieries", "lat": -17.3667, "lng": 27.1667, "kind": "mine",       "region": "Southern"},
    "kabwelume":   {"name": "Kansanshi Mine",    "lat": -12.0950, "lng": 26.4250, "kind": "mine",       "region": "North-Western"},

    # --- Farming blocks ----------------------------------------------------
    "mkushi":      {"name": "Mkushi Farm Block", "lat": -13.6200, "lng": 29.3900, "kind": "agri", "region": "Central"},
    "chisamba":    {"name": "Chisamba",          "lat": -14.9667, "lng": 28.3833, "kind": "agri", "region": "Central"},
    "mumbwa":      {"name": "Mumbwa",            "lat": -14.9833, "lng": 27.0667, "kind": "agri", "region": "Central"},
    "mazabuka":    {"name": "Mazabuka",          "lat": -15.8567, "lng": 27.7450, "kind": "agri", "region": "Southern"},
    "choma":       {"name": "Choma",             "lat": -16.8089, "lng": 26.9819, "kind": "agri", "region": "Southern"},
    "monze":       {"name": "Monze",             "lat": -16.2833, "lng": 27.4833, "kind": "agri", "region": "Southern"},
    "chipata":     {"name": "Chipata",           "lat": -13.6333, "lng": 32.6500, "kind": "agri", "region": "Eastern"},
    "kaoma":       {"name": "Kaoma",             "lat": -14.8000, "lng": 24.8000, "kind": "agri", "region": "Western"},

    # --- Borders and export gateways --------------------------------------
    "kasumbalesa": {"name": "Kasumbalesa (DRC)",   "lat": -12.2333, "lng": 27.8000, "kind": "border", "region": "Copperbelt"},
    "chirundu":    {"name": "Chirundu (Zimbabwe)", "lat": -16.0333, "lng": 28.8500, "kind": "border", "region": "Southern"},
    "nakonde":     {"name": "Nakonde (Tanzania)",  "lat": -9.3333,  "lng": 32.7500, "kind": "border", "region": "Muchinga"},
    "kazungula":   {"name": "Kazungula (Botswana)","lat": -17.7900, "lng": 25.2600, "kind": "border", "region": "Southern"},
    "mwami":       {"name": "Mwami (Malawi)",      "lat": -13.6500, "lng": 32.7833, "kind": "border", "region": "Eastern"},

    # --- Hubs and industrial sites ----------------------------------------
    "lusaka":      {"name": "Lusaka",            "lat": -15.4167, "lng": 28.2833, "kind": "hub",        "region": "Lusaka"},
    "kafue":       {"name": "Kafue",             "lat": -15.7690, "lng": 28.1810, "kind": "industrial", "region": "Lusaka"},
    "chilanga":    {"name": "Chilanga",          "lat": -15.5560, "lng": 28.2740, "kind": "industrial", "region": "Lusaka"},
    "livingstone": {"name": "Livingstone",       "lat": -17.8419, "lng": 25.8543, "kind": "hub",        "region": "Southern"},
    "mpulungu":    {"name": "Mpulungu Port",     "lat": -8.7667,  "lng": 31.1167, "kind": "hub",        "region": "Northern"},
}

# Measured road distances (km) on the corridors we actually run. Stored once
# per unordered pair; `route_km` looks the pair up in either direction.
ROAD_KM = {
    ("lusaka", "kitwe"): 360, ("lusaka", "ndola"): 321, ("lusaka", "chingola"): 415,
    ("lusaka", "mufulira"): 390, ("lusaka", "luanshya"): 350, ("lusaka", "kabwe"): 139,
    ("lusaka", "solwezi"): 600, ("lusaka", "kalumbila"): 750, ("lusaka", "lumwana"): 665,
    ("lusaka", "kabwelume"): 610, ("lusaka", "chisamba"): 55, ("lusaka", "mkushi"): 290,
    ("lusaka", "mumbwa"): 150, ("lusaka", "mazabuka"): 125, ("lusaka", "monze"): 190,
    ("lusaka", "choma"): 285, ("lusaka", "livingstone"): 473, ("lusaka", "kafue"): 45,
    ("lusaka", "chilanga"): 22, ("lusaka", "chirundu"): 135, ("lusaka", "chipata"): 570,
    ("lusaka", "nakonde"): 1010, ("lusaka", "maamba"): 320, ("lusaka", "kaoma"): 430,
    ("lusaka", "mpulungu"): 1120, ("lusaka", "kazungula"): 540, ("lusaka", "mwami"): 600,
    ("lusaka", "kasumbalesa"): 480,
    ("kitwe", "ndola"): 65, ("kitwe", "chingola"): 55, ("kitwe", "mufulira"): 60,
    ("kitwe", "luanshya"): 45, ("kitwe", "kasumbalesa"): 120, ("kitwe", "solwezi"): 250,
    ("chingola", "kasumbalesa"): 65, ("chingola", "solwezi"): 185,
    ("ndola", "kasumbalesa"): 175, ("ndola", "kabwe"): 190, ("ndola", "mkushi"): 165,
    ("solwezi", "kalumbila"): 150, ("solwezi", "lumwana"): 65, ("solwezi", "kabwelume"): 12,
    ("kalumbila", "kasumbalesa"): 320,
    ("mkushi", "kabwe"): 155, ("chisamba", "kabwe"): 85,
    ("mazabuka", "monze"): 65, ("monze", "choma"): 95, ("choma", "livingstone"): 190,
    ("livingstone", "kazungula"): 70, ("chipata", "mwami"): 30,
    ("kafue", "mazabuka"): 80, ("kafue", "chirundu"): 95, ("maamba", "choma"): 105,
}

EARTH_RADIUS_KM = 6371.0
# Zambia's trunk network is fairly direct; unmeasured pairs get a modest uplift
# on the straight line rather than an urban-grid factor.
FALLBACK_ROAD_FACTOR = 1.22
SAME_NODE_KM = 15.0


def haversine_km(lat1, lng1, lat2, lng2):
    d_lat, d_lng = math.radians(lat2 - lat1), math.radians(lng2 - lng1)
    a = (math.sin(d_lat / 2) ** 2
         + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(d_lng / 2) ** 2)
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(a))


def node(key):
    return NODES.get(key)


def route_km(from_key, to_key):
    """Road distance between two nodes, measured where we know it."""
    a, b = NODES.get(from_key), NODES.get(to_key)
    if not a or not b:
        raise ValueError("unknown location")
    if from_key == to_key:
        return SAME_NODE_KM
    measured = ROAD_KM.get((from_key, to_key)) or ROAD_KM.get((to_key, from_key))
    if measured:
        return float(measured)
    direct = haversine_km(a["lat"], a["lng"], b["lat"], b["lng"])
    return round(direct * FALLBACK_ROAD_FACTOR, 0)


def node_list():
    order = {"mine": 0, "agri": 1, "industrial": 2, "hub": 3, "border": 4}
    return [
        dict(key=k, **v)
        for k, v in sorted(NODES.items(), key=lambda kv: (order[kv[1]["kind"]], kv[1]["name"]))
    ]


# Kept so the rest of the codebase can keep speaking one vocabulary.
ZONES = NODES
zone = node
zone_list = node_list
