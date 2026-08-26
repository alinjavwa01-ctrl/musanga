"""Southern and Central African freight geography.

Bulk freight does not move between suburbs, it moves along corridors, and the
corridors do not stop at Zambia's border. Zambia is landlocked and sits at the
junction of five of them, so the network is modelled as named nodes on the
regional trunk system, each tagged with its country, with measured road
distances for the lanes we actually run.

A lane that crosses a border is a different commercial animal to a domestic
one: it needs a clearing agent, a transit bond, cross-border cover and a stack
of documents. `crossings()` works out which posts a lane passes through so the
rest of the platform can price and paper it correctly.
"""

import heapq
import math

# kind drives what a node is for and how it is drawn:
# 'mine', 'agri', 'industrial', 'hub', 'border', 'port', 'market'.
NODES = {
    # ================= ZAMBIA =============================================
    # --- Copperbelt & North-Western: the mining heartland ------------------
    "kitwe":       {"name": "Kitwe",             "lat": -12.8024, "lng": 28.2132, "kind": "mine",       "region": "Copperbelt",    "country": "ZM"},
    "ndola":       {"name": "Ndola",             "lat": -12.9587, "lng": 28.6366, "kind": "hub",        "region": "Copperbelt",    "country": "ZM"},
    "chingola":    {"name": "Chingola",          "lat": -12.5289, "lng": 27.8492, "kind": "mine",       "region": "Copperbelt",    "country": "ZM"},
    "mufulira":    {"name": "Mufulira",          "lat": -12.5497, "lng": 28.2408, "kind": "mine",       "region": "Copperbelt",    "country": "ZM"},
    "luanshya":    {"name": "Luanshya",          "lat": -13.1367, "lng": 28.4166, "kind": "mine",       "region": "Copperbelt",    "country": "ZM"},
    "solwezi":     {"name": "Solwezi",           "lat": -12.1688, "lng": 26.3894, "kind": "mine",       "region": "North-Western", "country": "ZM"},
    "kalumbila":   {"name": "Kalumbila",         "lat": -12.2833, "lng": 25.3167, "kind": "mine",       "region": "North-Western", "country": "ZM"},
    "lumwana":     {"name": "Lumwana",           "lat": -12.1500, "lng": 25.8500, "kind": "mine",       "region": "North-Western", "country": "ZM"},
    "kabwe":       {"name": "Kabwe",             "lat": -14.4469, "lng": 28.4464, "kind": "industrial", "region": "Central",       "country": "ZM"},
    "kapiri":      {"name": "Kapiri Mposhi",     "lat": -13.9709, "lng": 28.6698, "kind": "hub",        "region": "Central",       "country": "ZM"},
    "maamba":      {"name": "Maamba Collieries", "lat": -17.3667, "lng": 27.1667, "kind": "mine",       "region": "Southern",      "country": "ZM"},
    "kabwelume":   {"name": "Kansanshi Mine",    "lat": -12.0950, "lng": 26.4250, "kind": "mine",       "region": "North-Western", "country": "ZM"},

    # --- Farming blocks ----------------------------------------------------
    "mkushi":      {"name": "Mkushi Farm Block", "lat": -13.6200, "lng": 29.3900, "kind": "agri", "region": "Central",  "country": "ZM"},
    "chisamba":    {"name": "Chisamba",          "lat": -14.9667, "lng": 28.3833, "kind": "agri", "region": "Central",  "country": "ZM"},
    "mumbwa":      {"name": "Mumbwa",            "lat": -14.9833, "lng": 27.0667, "kind": "agri", "region": "Central",  "country": "ZM"},
    "serenje":     {"name": "Serenje",           "lat": -13.2333, "lng": 30.2333, "kind": "agri", "region": "Central",  "country": "ZM"},
    "mazabuka":    {"name": "Mazabuka",          "lat": -15.8567, "lng": 27.7450, "kind": "agri", "region": "Southern", "country": "ZM"},
    "choma":       {"name": "Choma",             "lat": -16.8089, "lng": 26.9819, "kind": "agri", "region": "Southern", "country": "ZM"},
    "monze":       {"name": "Monze",             "lat": -16.2833, "lng": 27.4833, "kind": "agri", "region": "Southern", "country": "ZM"},
    "chipata":     {"name": "Chipata",           "lat": -13.6333, "lng": 32.6500, "kind": "agri", "region": "Eastern",  "country": "ZM"},
    "kaoma":       {"name": "Kaoma",             "lat": -14.8000, "lng": 24.8000, "kind": "agri", "region": "Western",  "country": "ZM"},

    # --- Zambian hubs and industrial sites --------------------------------
    "lusaka":      {"name": "Lusaka",            "lat": -15.4167, "lng": 28.2833, "kind": "hub",        "region": "Lusaka",   "country": "ZM"},
    "kafue":       {"name": "Kafue",             "lat": -15.7690, "lng": 28.1810, "kind": "industrial", "region": "Lusaka",   "country": "ZM"},
    "chilanga":    {"name": "Chilanga",          "lat": -15.5560, "lng": 28.2740, "kind": "industrial", "region": "Lusaka",   "country": "ZM"},
    "livingstone": {"name": "Livingstone",       "lat": -17.8419, "lng": 25.8543, "kind": "hub",        "region": "Southern", "country": "ZM"},
    "sesheke":     {"name": "Sesheke",           "lat": -17.4758, "lng": 24.2967, "kind": "hub",        "region": "Western",  "country": "ZM"},
    "mpulungu":    {"name": "Mpulungu Port",     "lat": -8.7667,  "lng": 31.1167, "kind": "port",       "region": "Northern", "country": "ZM"},

    # --- Zambian border posts ---------------------------------------------
    "kasumbalesa": {"name": "Kasumbalesa",  "lat": -12.2333, "lng": 27.8000, "kind": "border", "region": "Copperbelt", "country": "ZM", "opposite": "CD", "post": "Kasumbalesa"},
    "chirundu":    {"name": "Chirundu",     "lat": -16.0333, "lng": 28.8500, "kind": "border", "region": "Southern",   "country": "ZM", "opposite": "ZW", "post": "Chirundu"},
    "nakonde":     {"name": "Nakonde",      "lat": -9.3333,  "lng": 32.7500, "kind": "border", "region": "Muchinga",   "country": "ZM", "opposite": "TZ", "post": "Nakonde / Tunduma"},
    "kazungula":   {"name": "Kazungula",    "lat": -17.7900, "lng": 25.2600, "kind": "border", "region": "Southern",   "country": "ZM", "opposite": "BW", "post": "Kazungula Bridge"},
    "mwami":       {"name": "Mwami",        "lat": -13.6500, "lng": 32.7833, "kind": "border", "region": "Eastern",    "country": "ZM", "opposite": "MW", "post": "Mwami / Mchinji"},
    "victoriaf":   {"name": "Victoria Falls Bridge", "lat": -17.9243, "lng": 25.8572, "kind": "border", "region": "Southern", "country": "ZM", "opposite": "ZW", "post": "Victoria Falls"},
    "katimamulilo":{"name": "Katima Mulilo","lat": -17.5000, "lng": 24.2667, "kind": "border", "region": "Western",    "country": "ZM", "opposite": "NA", "post": "Wenela / Katima Mulilo"},
    "mwanjawantu": {"name": "Mwanja Wantu", "lat": -14.5333, "lng": 33.1000, "kind": "border", "region": "Eastern",    "country": "ZM", "opposite": "MZ", "post": "Cassacatiza"},
    "jimbe":       {"name": "Jimbe",        "lat": -11.1833, "lng": 22.3667, "kind": "border", "region": "North-Western","country": "ZM","opposite": "AO", "post": "Jimbe"},

    # ================= DR CONGO ===========================================
    "lubumbashi":  {"name": "Lubumbashi",   "lat": -11.6876, "lng": 27.5026, "kind": "market", "region": "Haut-Katanga", "country": "CD"},
    "likasi":      {"name": "Likasi",       "lat": -10.9814, "lng": 26.7333, "kind": "mine",   "region": "Haut-Katanga", "country": "CD"},
    "kolwezi":     {"name": "Kolwezi",      "lat": -10.7167, "lng": 25.4667, "kind": "mine",   "region": "Lualaba",      "country": "CD"},
    "fungurume":   {"name": "Tenke Fungurume","lat": -10.6000,"lng": 26.2000,"kind": "mine",   "region": "Lualaba",      "country": "CD"},
    "kasumbalesa_cd": {"name": "Kasumbalesa (DRC side)", "lat": -12.2200, "lng": 27.7900, "kind": "border", "region": "Haut-Katanga", "country": "CD", "opposite": "ZM", "post": "Kasumbalesa"},

    # ================= ZIMBABWE ===========================================
    "harare":      {"name": "Harare",       "lat": -17.8292, "lng": 31.0522, "kind": "market", "region": "Harare",         "country": "ZW"},
    "bulawayo":    {"name": "Bulawayo",     "lat": -20.1500, "lng": 28.5833, "kind": "market", "region": "Bulawayo",       "country": "ZW"},
    "mutare":      {"name": "Mutare",       "lat": -18.9707, "lng": 32.6709, "kind": "hub",    "region": "Manicaland",     "country": "ZW"},
    "gweru":       {"name": "Gweru",        "lat": -19.4500, "lng": 29.8167, "kind": "market", "region": "Midlands",       "country": "ZW"},
    "chirundu_zw": {"name": "Chirundu (Zimbabwe side)", "lat": -16.0400, "lng": 28.8600, "kind": "border", "region": "Mashonaland West", "country": "ZW", "opposite": "ZM", "post": "Chirundu"},
    "beitbridge":  {"name": "Beitbridge",   "lat": -22.2167, "lng": 30.0000, "kind": "border", "region": "Matabeleland South", "country": "ZW", "opposite": "ZA", "post": "Beitbridge"},
    "machipanda":  {"name": "Forbes / Machipanda", "lat": -18.9333, "lng": 32.8500, "kind": "border", "region": "Manicaland", "country": "ZW", "opposite": "MZ", "post": "Forbes / Machipanda"},

    # ================= TANZANIA ===========================================
    "dar":         {"name": "Dar es Salaam Port", "lat": -6.7924, "lng": 39.2083, "kind": "port",   "region": "Dar es Salaam", "country": "TZ"},
    "mbeya":       {"name": "Mbeya",        "lat": -8.9000,  "lng": 33.4500, "kind": "hub",    "region": "Mbeya",   "country": "TZ"},
    "tunduma":     {"name": "Tunduma",      "lat": -9.3000,  "lng": 32.7667, "kind": "border", "region": "Songwe",  "country": "TZ", "opposite": "ZM", "post": "Nakonde / Tunduma"},

    # ================= MALAWI =============================================
    "lilongwe":    {"name": "Lilongwe",     "lat": -13.9833, "lng": 33.7833, "kind": "market", "region": "Central", "country": "MW"},
    "blantyre":    {"name": "Blantyre",     "lat": -15.7861, "lng": 35.0058, "kind": "market", "region": "Southern","country": "MW"},
    "mchinji":     {"name": "Mchinji",      "lat": -13.7986, "lng": 32.8878, "kind": "border", "region": "Central", "country": "MW", "opposite": "ZM", "post": "Mwami / Mchinji"},

    # ================= MOZAMBIQUE =========================================
    "beira":       {"name": "Beira Port",   "lat": -19.8436, "lng": 34.8389, "kind": "port", "region": "Sofala",   "country": "MZ"},
    "nacala":      {"name": "Nacala Port",  "lat": -14.5428, "lng": 40.6728, "kind": "port", "region": "Nampula",  "country": "MZ"},
    "tete":        {"name": "Tete",         "lat": -16.1564, "lng": 33.5867, "kind": "hub",  "region": "Tete",     "country": "MZ"},

    # ================= SOUTH AFRICA & BOTSWANA ============================
    "musina":      {"name": "Musina",       "lat": -22.3389, "lng": 30.0400, "kind": "border", "region": "Limpopo", "country": "ZA", "opposite": "ZW", "post": "Beitbridge"},
    "johannesburg":{"name": "Johannesburg", "lat": -26.2041, "lng": 28.0473, "kind": "market", "region": "Gauteng",      "country": "ZA"},
    "durban":      {"name": "Durban Port",  "lat": -29.8587, "lng": 31.0218, "kind": "port",   "region": "KwaZulu-Natal","country": "ZA"},
    "gaborone":    {"name": "Gaborone",     "lat": -24.6282, "lng": 25.9231, "kind": "market", "region": "South-East",   "country": "BW"},
    "francistown": {"name": "Francistown",  "lat": -21.1700, "lng": 27.5100, "kind": "hub",    "region": "North-East",   "country": "BW"},

    # ================= NAMIBIA & ANGOLA ===================================
    "walvisbay":   {"name": "Walvis Bay Port", "lat": -22.9576, "lng": 14.5053, "kind": "port", "region": "Erongo", "country": "NA"},
    "windhoek":    {"name": "Windhoek",     "lat": -22.5609, "lng": 17.0658, "kind": "hub",    "region": "Khomas", "country": "NA"},
    "lobito":      {"name": "Lobito Port",  "lat": -12.3644, "lng": 13.5456, "kind": "port",   "region": "Benguela","country": "AO"},
}

COUNTRIES = {
    "ZM": {"name": "Zambia",       "currency": "ZMW"},
    "CD": {"name": "DR Congo",     "currency": "USD"},
    "ZW": {"name": "Zimbabwe",     "currency": "USD"},
    "TZ": {"name": "Tanzania",     "currency": "USD"},
    "MW": {"name": "Malawi",       "currency": "USD"},
    "MZ": {"name": "Mozambique",   "currency": "USD"},
    "ZA": {"name": "South Africa", "currency": "USD"},
    "BW": {"name": "Botswana",     "currency": "USD"},
    "NA": {"name": "Namibia",      "currency": "USD"},
    "AO": {"name": "Angola",       "currency": "USD"},
}

# The five corridors Zambian freight actually runs on. Each is an ordered
# chain of nodes; `crossings` walks it to find the border posts on a lane.
CORRIDORS = {
    "north_south": {
        "name": "North-South Corridor",
        "chain": ["durban", "johannesburg", "musina", "beitbridge", "bulawayo", "gweru", "harare",
                  "chirundu_zw", "chirundu", "lusaka", "kabwe", "kapiri", "ndola", "kitwe",
                  "chingola", "kasumbalesa", "kasumbalesa_cd", "lubumbashi"],
    },
    "dar": {
        "name": "Dar es Salaam Corridor",
        "chain": ["dar", "mbeya", "tunduma", "nakonde", "kapiri", "lusaka"],
    },
    "beira": {
        "name": "Beira Corridor",
        "chain": ["beira", "machipanda", "mutare", "harare", "chirundu_zw", "chirundu", "lusaka"],
    },
    "nacala": {
        "name": "Nacala Corridor",
        "chain": ["nacala", "blantyre", "lilongwe", "mchinji", "mwami", "chipata", "lusaka"],
    },
    "walvis": {
        "name": "Walvis Bay Corridor",
        "chain": ["walvisbay", "windhoek", "katimamulilo", "sesheke", "livingstone", "lusaka"],
    },
}

# Measured road distances (km) on the lanes we actually run. Stored once per
# unordered pair; `route_km` looks the pair up in either direction and falls
# back to a corridor-chained sum, then to a great-circle estimate.
ROAD_KM = {
    # --- Zambia domestic ---------------------------------------------------
    ("lusaka", "kitwe"): 360, ("lusaka", "ndola"): 321, ("lusaka", "chingola"): 415,
    ("lusaka", "mufulira"): 390, ("lusaka", "luanshya"): 350, ("lusaka", "kabwe"): 139,
    ("lusaka", "kapiri"): 200, ("lusaka", "solwezi"): 600, ("lusaka", "kalumbila"): 750,
    ("lusaka", "lumwana"): 665, ("lusaka", "kabwelume"): 610, ("lusaka", "chisamba"): 55,
    ("lusaka", "mkushi"): 290, ("lusaka", "mumbwa"): 150, ("lusaka", "mazabuka"): 125,
    ("lusaka", "monze"): 190, ("lusaka", "choma"): 285, ("lusaka", "livingstone"): 473,
    ("lusaka", "kafue"): 45, ("lusaka", "chilanga"): 22, ("lusaka", "chirundu"): 135,
    ("lusaka", "chipata"): 570, ("lusaka", "nakonde"): 1010, ("lusaka", "maamba"): 320,
    ("lusaka", "kaoma"): 430, ("lusaka", "mpulungu"): 1120, ("lusaka", "kazungula"): 540,
    ("lusaka", "mwami"): 600, ("lusaka", "kasumbalesa"): 480, ("lusaka", "serenje"): 385,
    ("lusaka", "sesheke"): 700, ("lusaka", "katimamulilo"): 715, ("lusaka", "victoriaf"): 478,
    ("kitwe", "ndola"): 65, ("kitwe", "chingola"): 55, ("kitwe", "mufulira"): 60,
    ("kitwe", "luanshya"): 45, ("kitwe", "kasumbalesa"): 120, ("kitwe", "solwezi"): 250,
    ("chingola", "kasumbalesa"): 65, ("chingola", "solwezi"): 185,
    ("ndola", "kasumbalesa"): 175, ("ndola", "kabwe"): 190, ("ndola", "mkushi"): 165,
    ("ndola", "kapiri"): 125, ("kapiri", "kabwe"): 62, ("kapiri", "mkushi"): 95,
    ("kapiri", "serenje"): 185, ("kapiri", "nakonde"): 810, ("serenje", "mkushi"): 90,
    ("solwezi", "kalumbila"): 150, ("solwezi", "lumwana"): 65, ("solwezi", "kabwelume"): 12,
    ("kalumbila", "kasumbalesa"): 320, ("kalumbila", "jimbe"): 240, ("solwezi", "jimbe"): 385,
    ("mkushi", "kabwe"): 155, ("chisamba", "kabwe"): 85,
    ("mazabuka", "monze"): 65, ("monze", "choma"): 95, ("choma", "livingstone"): 190,
    ("livingstone", "kazungula"): 70, ("livingstone", "victoriaf"): 11,
    ("livingstone", "sesheke"): 205, ("sesheke", "katimamulilo"): 15,
    ("chipata", "mwami"): 30, ("chipata", "mwanjawantu"): 105,
    ("kafue", "mazabuka"): 80, ("kafue", "chirundu"): 95, ("maamba", "choma"): 105,

    # --- DR Congo ----------------------------------------------------------
    ("kasumbalesa", "kasumbalesa_cd"): 3, ("kasumbalesa_cd", "lubumbashi"): 95,
    ("lubumbashi", "likasi"): 120, ("likasi", "fungurume"): 175, ("fungurume", "kolwezi"): 105,
    ("lubumbashi", "kolwezi"): 400, ("kolwezi", "kasumbalesa_cd"): 490,

    # --- Zimbabwe ----------------------------------------------------------
    ("chirundu", "chirundu_zw"): 2, ("chirundu_zw", "harare"): 350,
    ("harare", "bulawayo"): 439, ("harare", "gweru"): 275, ("gweru", "bulawayo"): 164,
    ("harare", "mutare"): 263, ("mutare", "machipanda"): 12,
    ("bulawayo", "beitbridge"): 321, ("harare", "beitbridge"): 580,
    ("beitbridge", "musina"): 15, ("musina", "johannesburg"): 535,
    ("johannesburg", "durban"): 568,

    # --- Tanzania ----------------------------------------------------------
    ("nakonde", "tunduma"): 3, ("tunduma", "mbeya"): 110, ("mbeya", "dar"): 830,
    ("tunduma", "dar"): 935,

    # --- Malawi and Mozambique --------------------------------------------
    ("mwami", "mchinji"): 3, ("mchinji", "lilongwe"): 110,
    ("lilongwe", "blantyre"): 310, ("blantyre", "nacala"): 905, ("blantyre", "beira"): 690,
    ("machipanda", "beira"): 285, ("tete", "blantyre"): 380, ("tete", "beira"): 590,
    ("mwanjawantu", "tete"): 290,

    # --- Botswana and Namibia ---------------------------------------------
    ("kazungula", "francistown"): 490, ("francistown", "gaborone"): 435,
    ("katimamulilo", "windhoek"): 1200, ("windhoek", "walvisbay"): 395,
}

EARTH_RADIUS_KM = 6371.0
# The regional trunk network is fairly direct; unmeasured pairs get a modest
# uplift on the straight line rather than an urban-grid factor.
FALLBACK_ROAD_FACTOR = 1.22
SAME_NODE_KM = 15.0

_ADJ = None


def haversine_km(lat1, lng1, lat2, lng2):
    d_lat, d_lng = math.radians(lat2 - lat1), math.radians(lng2 - lng1)
    a = (math.sin(d_lat / 2) ** 2
         + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(d_lng / 2) ** 2)
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(a))


def node(key):
    return NODES.get(key)


def country_of(key):
    n = NODES.get(key)
    return n["country"] if n else None


def _graph():
    """Adjacency built once from the measured lanes. The network is a road
    graph, so the honest distance between two points we have not measured
    end to end is the shortest measured path between them."""
    global _ADJ
    if _ADJ is None:
        adj = {k: [] for k in NODES}
        for (a, b), km in ROAD_KM.items():
            adj[a].append((b, float(km)))
            adj[b].append((a, float(km)))
        _ADJ = adj
    return _ADJ


def shortest_path(from_key, to_key):
    """Dijkstra over the measured lanes. Returns (km, [node keys]) or None."""
    if from_key not in NODES or to_key not in NODES:
        raise ValueError("unknown location")
    if from_key == to_key:
        return SAME_NODE_KM, [from_key]
    adj = _graph()
    dist = {from_key: 0.0}
    prev = {}
    queue = [(0.0, from_key)]
    done = set()
    while queue:
        d, here = heapq.heappop(queue)
        if here in done:
            continue
        done.add(here)
        if here == to_key:
            path = [here]
            while path[-1] != from_key:
                path.append(prev[path[-1]])
            return round(d, 0), list(reversed(path))
        for nxt, km in adj[here]:
            nd = d + km
            if nd < dist.get(nxt, float("inf")):
                dist[nxt] = nd
                prev[nxt] = here
                heapq.heappush(queue, (nd, nxt))
    return None


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
    routed = shortest_path(from_key, to_key)
    if routed:
        return float(routed[0])
    direct = haversine_km(a["lat"], a["lng"], b["lat"], b["lng"])
    return round(direct * FALLBACK_ROAD_FACTOR, 0)


def route_nodes(from_key, to_key):
    """The nodes a lane runs through, so far as we have measured them."""
    routed = shortest_path(from_key, to_key)
    return routed[1] if routed else [from_key, to_key]


def corridor_for(from_key, to_key):
    """The named corridor a lane runs on, where it runs on one."""
    path = set(route_nodes(from_key, to_key))
    best, best_hits = None, 1
    for key, corridor in CORRIDORS.items():
        hits = len(path & set(corridor["chain"]))
        if hits > best_hits:
            best, best_hits = dict(key=key, **corridor), hits
    return best


def crossings(from_key, to_key):
    """The border posts a lane passes through, in order of travel.

    Walking the routed path picks up every post on the way, so a Mkushi to
    Harare load is correctly papered for Chirundu and a Kalumbila to Durban
    load for both Chirundu and Beitbridge.
    """
    a, b = NODES.get(from_key), NODES.get(to_key)
    if not a or not b:
        raise ValueError("unknown location")

    posts, seen = [], set()
    for key in route_nodes(from_key, to_key):
        n = NODES[key]
        if n["kind"] != "border":
            continue
        name = n.get("post", n["name"])
        if name in seen:
            continue
        seen.add(name)
        posts.append({"key": key, "post": name,
                      "between": [n["country"], n.get("opposite")]})

    # A change of country with no mapped post still means one border's worth
    # of paperwork, which is the honest answer when we have not routed it.
    if not posts and a["country"] != b["country"]:
        posts.append({"key": None,
                      "post": "%s / %s border" % (COUNTRIES[a["country"]]["name"],
                                                  COUNTRIES[b["country"]]["name"]),
                      "between": [a["country"], b["country"]]})
    return posts


def is_export(from_key, to_key):
    return country_of(from_key) != country_of(to_key)


def transit_countries(from_key, to_key):
    """Every country a lane touches, origin and destination included."""
    out = []
    for key in route_nodes(from_key, to_key):
        c = NODES[key]["country"]
        if c not in out:
            out.append(c)
    for c in (country_of(from_key), country_of(to_key)):
        if c not in out:
            out.append(c)
    return out


def node_list():
    order = {"mine": 0, "agri": 1, "industrial": 2, "hub": 3, "port": 4, "market": 5, "border": 6}
    return [
        dict(key=k, **v)
        for k, v in sorted(NODES.items(), key=lambda kv: (kv[1]["country"] != "ZM",
                                                          order[kv[1]["kind"]], kv[1]["name"]))
    ]


def country_list():
    return [dict(key=k, **v) for k, v in COUNTRIES.items()]


def corridor_list():
    return [dict(key=k, name=v["name"], chain=v["chain"]) for k, v in CORRIDORS.items()]


# Kept so the rest of the codebase can keep speaking one vocabulary.
ZONES = NODES
zone = node
zone_list = node_list
