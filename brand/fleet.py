#!/usr/bin/env python3
"""Generates the flat-vector fleet: four trucks, two value schemes, one scene.

Why a generator and not a drawing file: the brief asks for every asset in a
light and a dark version with identical geometry and inverted values. Drawing
that twice guarantees they drift. Here the geometry is written once and the
palette is a parameter, so a light asset and its dark twin cannot disagree.

The rules, from the brief, enforced in code rather than by eye:

  * black, white and the nine greys, and nothing else. There is no accent.
    Status colour is deliberately absent - it belongs to a load, not to an
    illustration.
  * strict orthographic side profile, travelling left to right
  * solid fills, no gradients, no strokes on the bodywork, no shadows
  * the truck is the darkest thing in frame in light mode and the lightest in
    dark mode; scenery steps through the grey ramp behind it
  * the truck holds position and the world moves past it

Two kinds of file come out of this:

  fleet/<truck>-<mode>.svg   the truck alone, layers named and grouped, no
                             animation, for animating in CSS elsewhere
  fleet/scene-<truck>.svg    the truck in the corridor, animating itself, both
                             modes in one file. Self-contained so it can be
                             dropped into an <img> and still run.

Run: python3 brand/fleet.py
"""

import os

OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "web", "img", "fleet")

# The whole palette. Any value not on this list is a bug.
RAMP = ["#000000", "#0a0a0a", "#161616", "#262626", "#404040", "#6e6e6e",
        "#9a9a9a", "#cccccc", "#e6e6e6", "#f2f2f2", "#f7f7f7", "#ffffff"]

LIGHT = {
    "sky":      "#ffffff",
    "ridge":    "#e6e6e6",   # furthest: lowest contrast
    "hill":     "#cccccc",
    "far_mass": "#9a9a9a",   # headframe, silo
    "ground":   "#f2f2f2",
    "road":     "#404040",
    "kerb":     "#9a9a9a",
    "body":     "#0a0a0a",   # the truck: darkest in frame
    "body_alt": "#262626",   # chassis, second plane of the body
    "glass":    "#9a9a9a",
    "tyre":     "#161616",
    "hub":      "#f2f2f2",
    "mark":     "#6e6e6e",
}

DARK = {
    "sky":      "#0a0a0a",
    "ridge":    "#161616",
    "hill":     "#262626",
    "far_mass": "#404040",
    "ground":   "#161616",
    "road":     "#6e6e6e",
    "kerb":     "#404040",
    "body":     "#f2f2f2",   # the truck: lightest in frame
    "body_alt": "#cccccc",
    "glass":    "#6e6e6e",
    "tyre":     "#e6e6e6",
    "hub":      "#262626",
    "mark":     "#9a9a9a",
}

# Frame. The truck is drawn at a fixed station in the scene and never leaves it.
SCENE_W, SCENE_H = 640, 260
ROAD_Y = 206          # top of the road surface
AXLE_Y = ROAD_Y - 4   # wheel centres sit just into the road
TRUCK_X = 150         # where the truck stands, left of centre

WHEEL_R = 15
HUB_R = 5.4


# --- pieces ---------------------------------------------------------------

def wheel(cx, cy, name, p):
    """A wheel is three shapes: tyre, hub and one spoke bar. The bar is the
    only reason the rotation reads at all at 320px wide."""
    return (
        '<g class="wheel" id="%s">' % name +
        '<circle cx="%g" cy="%g" r="%g" fill="%s"/>' % (cx, cy, WHEEL_R, p["tyre"]) +
        '<circle cx="%g" cy="%g" r="%g" fill="%s"/>' % (cx, cy, HUB_R, p["hub"]) +
        '<rect x="%g" y="%g" width="%g" height="2.4" rx="1.2" fill="%s"/>'
        % (cx - HUB_R + 0.6, cy - 1.2, HUB_R * 2 - 1.2, p["body"]) +
        "</g>"
    )


def cab(x, p, tall=False):
    """Cab, bonnet and one window wedge. Four shapes, no more."""
    top = AXLE_Y - (62 if tall else 56)
    height = AXLE_Y - top - 4
    return (
        '<g id="cab">'
        '<rect x="%g" y="%g" width="46" height="%g" rx="7" fill="%s"/>' % (x, top, height, p["body"]) +
        '<path d="M%g %g h30 v16 h-34 z" fill="%s"/>' % (x + 8, top + 8, p["glass"]) +
        '<rect x="%g" y="%g" width="14" height="20" rx="4" fill="%s"/>' % (x + 44, AXLE_Y - 30, p["body_alt"]) +
        '<rect x="%g" y="%g" width="6" height="%g" rx="3" fill="%s"/>'   # exhaust stack
        % (x + 42, top - 14, 18, p["body_alt"]) +
        "</g>"
    )


def chassis(x, width, p):
    return ('<rect id="chassis" x="%g" y="%g" width="%g" height="8" rx="3" fill="%s"/>'
            % (x, AXLE_Y - 20, width, p["body_alt"]))


def tipper_body(x, p):
    """Side tipper: a bin that tapers, because that is what makes it read as
    a tipper and not a box."""
    top, bottom = AXLE_Y - 62, AXLE_Y - 22
    return (
        '<g id="tipper-bin">'
        '<path d="M%g %g L%g %g L%g %g L%g %g Z" fill="%s"/>'
        % (x, top, x + 168, top, x + 158, bottom, x + 8, bottom, p["body"]) +
        '<rect x="%g" y="%g" width="150" height="5" rx="2.5" fill="%s"/>' % (x + 8, top - 7, p["body_alt"]) +
        "</g>"
    )


def tanker_body(x, p):
    """Fuel tanker: one capsule and two saddle bands."""
    top = AXLE_Y - 58
    body = ('<rect x="%g" y="%g" width="176" height="38" rx="19" fill="%s"/>' % (x, top, p["body"]))
    bands = "".join(
        '<rect x="%g" y="%g" width="5" height="38" fill="%s"/>' % (x + offset, top, p["body_alt"])
        for offset in (44, 96, 140))
    dome = '<rect x="%g" y="%g" width="26" height="7" rx="3.5" fill="%s"/>' % (x + 66, top - 6, p["body_alt"])
    return '<g id="tank">' + body + bands + dome + "</g>"


def flatdeck_body(x, p):
    """Flat deck under a tarped agricultural load: the tarp is one hump with
    three strap bars over it."""
    deck_y = AXLE_Y - 26
    tarp = ('<path d="M%g %g q%g %g %g 0 z" fill="%s"/>' % (x + 6, deck_y, 82, -54, 164, p["body"]))
    straps = "".join(
        '<rect x="%g" y="%g" width="4" height="%g" fill="%s"/>' % (x + offset, deck_y - height, height, p["body_alt"])
        for offset, height in ((42, 30), (86, 36), (130, 30)))
    deck = '<rect x="%g" y="%g" width="180" height="8" rx="2" fill="%s"/>' % (x, deck_y, p["body"])
    return '<g id="tarped-load">' + tarp + straps + deck + "</g>"


def box_body(x, p):
    """Box trailer: one rectangle, one door seam, one roof rail."""
    top = AXLE_Y - 66
    return (
        '<g id="box">'
        '<rect x="%g" y="%g" width="180" height="46" rx="4" fill="%s"/>' % (x, top, p["body"]) +
        '<rect x="%g" y="%g" width="4" height="46" fill="%s"/>' % (x + 150, top, p["body_alt"]) +
        '<rect x="%g" y="%g" width="180" height="5" rx="2.5" fill="%s"/>' % (x, top - 5, p["body_alt"]) +
        "</g>"
    )


TRUCKS = {
    "tipper": {
        "name": "Side tipper",
        "note": "Bulk mineral trailer, the Copperbelt workhorse.",
        "trailer": tipper_body, "axles": (46, 208, 238, 268), "width": 300, "tall": True,
    },
    "tanker": {
        "name": "Fuel tanker",
        "note": "Bulk fuel into the mines.",
        "trailer": tanker_body, "axles": (46, 214, 244, 274), "width": 300, "tall": False,
    },
    "flatdeck": {
        "name": "Flat deck, tarped",
        "note": "Agricultural load under tarp and straps.",
        "trailer": flatdeck_body, "axles": (46, 212, 242, 272), "width": 300, "tall": False,
    },
    "box": {
        "name": "Box trailer",
        "note": "General freight, the standard van.",
        "trailer": box_body, "axles": (46, 210, 240, 270), "width": 300, "tall": False,
    },
}


def truck_group(key, p, prefix=""):
    """The vehicle itself: cab, trailer, chassis and four named wheels, all
    grouped so a wheel or the body can be animated on its own."""
    spec = TRUCKS[key]
    body_x = 62
    parts = [
        chassis(52, spec["width"] - 60, p),
        spec["trailer"](body_x + 52, p),
        cab(4, p, spec["tall"]),
    ]
    wheels = "".join(wheel(cx, AXLE_Y, "%swheel-%d" % (prefix, i + 1), p)
                     for i, cx in enumerate(spec["axles"]))
    return ('<g id="%struck" class="truck">'
            '<g id="%sbodywork">%s</g><g id="%swheels">%s</g></g>'
            % (prefix, prefix, "".join(parts), prefix, wheels))


# --- the standalone truck asset -------------------------------------------

def truck_svg(key, mode):
    p = LIGHT if mode == "light" else DARK
    spec = TRUCKS[key]
    height = 110
    # Drop the truck onto its own baseline rather than the scene's.
    shift = height - 22 - AXLE_Y
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 %d %d" '
        'width="%d" height="%d" role="img" aria-label="%s, %s mode">'
        % (spec["width"] + 8, height, spec["width"] + 8, height, spec["name"], mode) +
        '<title>Musanga fleet - %s (%s)</title>' % (spec["name"], mode) +
        '<g id="ground"><rect x="0" y="%d" width="%d" height="6" fill="%s"/></g>'
        % (height - 22 + WHEEL_R - 2, spec["width"] + 8, p["road"]) +
        '<g transform="translate(4 %g)">' % shift + truck_group(key, p) + "</g></svg>"
    )


# --- the scene ------------------------------------------------------------
# Layers, back to front: sky, ridgeline, hill mass, industrial silhouette,
# treeline, road, truck. Each moving layer is drawn twice, end to end, and
# slides by exactly its own width - that is what makes the loop seamless.

def ridge_path(width, base, seed):
    """A low plateau ridgeline. Deterministic, so light and dark match and a
    re-run does not produce a different landscape."""
    points, x, value = [], 0, 0
    step = 40
    while x <= width:
        value = (seed * (x // step + 3) * 37) % 23
        points.append((x, base - value))
        x += step
    d = "M0 %d L" % base + " ".join("%d %d" % pt for pt in points) + " %d %d Z" % (width, base)
    return d


def hill_path(width, base, height):
    """Two overlapping domes per tile: the plateau, not mountains."""
    parts = ["M0 %d" % base]
    x = 0
    while x < width:
        parts.append("q %d -%d %d 0" % (60, height, 120))
        x += 120
    parts.append("L%d %d Z" % (width, base))
    return " ".join(parts)


def headframe(x, base, p):
    """A mine headframe: the one thing in the landscape that says Copperbelt.
    Kept as abstract as the trucks - four shapes."""
    return (
        '<g class="headframe">'
        '<rect x="%d" y="%d" width="7" height="54" fill="%s"/>' % (x, base - 54, p["far_mass"]) +
        '<rect x="%d" y="%d" width="7" height="54" fill="%s"/>' % (x + 26, base - 54, p["far_mass"]) +
        '<rect x="%d" y="%d" width="33" height="6" fill="%s"/>' % (x, base - 60, p["far_mass"]) +
        '<path d="M%d %d l16 -20 l17 20 z" fill="%s"/>' % (x, base - 60, p["far_mass"]) +
        "</g>")


def silos(x, base, p):
    return (
        '<g class="silos">' +
        "".join('<rect x="%d" y="%d" width="16" height="42" rx="8" fill="%s"/>'
                % (x + i * 20, base - 42, p["far_mass"]) for i in range(3)) +
        '<rect x="%d" y="%d" width="56" height="7" fill="%s"/>' % (x, base - 49, p["far_mass"]) +
        "</g>")


def scene_svg(key, animated=True):
    """One truck in the corridor. Both value schemes live in this one file:
    the palette is a set of CSS custom properties and the dark block only
    swaps the values, so the geometry can never diverge between modes."""
    spec = TRUCKS[key]
    W, H = SCENE_W, SCENE_H

    def layer(inner_light, speed, name):
        """A tiling layer, drawn twice and slid by one tile width."""
        return ('<g class="layer %s" style="--speed:%gs">'
                '<g class="tile">%s</g><g class="tile" transform="translate(%d 0)">%s</g></g>'
                % (name, speed, inner_light, W, inner_light))

    ridge = '<path d="%s" fill="var(--ridge)"/>' % ridge_path(W, 150, 7)
    hills = '<path d="%s" fill="var(--hill)"/>' % hill_path(W, 178, 34)

    industry = (
        '<g fill="var(--far-mass)">' +
        headframe(96, 152, {"far_mass": "var(--far-mass)"}) +
        silos(430, 158, {"far_mass": "var(--far-mass)"}) +
        "</g>")

    # Between the hills and the road: open plateau, so nothing floats.
    ground = ('<g id="plateau"><rect x="0" y="176" width="%d" height="%d" fill="var(--ground)"/></g>'
              % (W, ROAD_Y - 176))

    # Treeline: clumps of miombo as half-domes on the horizon. Same
    # abstraction as the trucks - two shapes per clump, no trunks, no detail.
    def clump(x, w, h):
        return ('<path d="M%d %d a%d %d 0 0 1 %d 0 z" fill="var(--kerb)"/>'
                % (x, 186, w / 2.0, h, w))
    trees = "".join(clump(x, w, h) for x, w, h in (
        (6, 54, 22), (48, 38, 15), (128, 64, 26), (186, 42, 17), (268, 58, 23),
        (330, 36, 14), (398, 62, 25), (462, 40, 16), (536, 56, 22), (596, 44, 18)))

    # Road: the surface, and the dashes that carry the sense of speed.
    dashes = "".join('<rect x="%d" y="%d" width="30" height="3" fill="var(--sky)"/>' % (x, ROAD_Y + 16)
                     for x in range(0, W, 64))
    road = ('<g id="road"><rect x="0" y="%d" width="%d" height="%d" fill="var(--road)"/>'
            '<rect x="0" y="%d" width="%d" height="3" fill="var(--kerb)"/></g>'
            % (ROAD_Y, W, H - ROAD_Y, ROAD_Y, W))

    palette = """
  :root, svg { --sky:%(sky)s; --ridge:%(ridge)s; --hill:%(hill)s; --far-mass:%(far_mass)s;
    --ground:%(ground)s; --road:%(road)s; --kerb:%(kerb)s; --body:%(body)s;
    --body-alt:%(body_alt)s; --glass:%(glass)s; --tyre:%(tyre)s; --hub:%(hub)s; }
""" % LIGHT + """
  @media (prefers-color-scheme: dark) {
    :root, svg { --sky:%(sky)s; --ridge:%(ridge)s; --hill:%(hill)s; --far-mass:%(far_mass)s;
      --ground:%(ground)s; --road:%(road)s; --kerb:%(kerb)s; --body:%(body)s;
      --body-alt:%(body_alt)s; --glass:%(glass)s; --tyre:%(tyre)s; --hub:%(hub)s; }
  }
""" % DARK

    motion = """
  /* The world moves, the truck holds station. A tiling layer slides exactly
     one tile width and snaps back - at linear speed, because any easing on a
     seamless loop reads as the ground stuttering. The easing the brief asks
     for lives where it belongs: on the suspension. */
  .layer { animation: pan var(--speed) linear infinite; }
  @keyframes pan { to { transform: translateX(-%(w)dpx); } }
  .wheel { animation: roll 1.15s linear infinite; transform-origin: center; transform-box: fill-box; }
  @keyframes roll { to { transform: rotate(360deg); } }
  #bodywork { animation: suspension 2.6s ease-in-out infinite; }
  @keyframes suspension {
    0%%, 100%% { transform: translateY(0); }
    50%%      { transform: translateY(1.1px); }
  }
  @media (prefers-reduced-motion: reduce) {
    .layer, .wheel, #bodywork { animation: none; }
  }
""" % {"w": SCENE_W}

    body = {k: "var(--%s)" % k.replace("_", "-") for k in
            ("body", "body_alt", "glass", "tyre", "hub", "mark", "road")}

    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 %d %d" '
        'preserveAspectRatio="xMidYMax slice" role="img" '
        'aria-label="%s hauling on a Zambian corridor">' % (W, H, spec["name"]) +
        "<title>Musanga - %s on the corridor</title>" % spec["name"] +
        "<style>%s%s</style>" % (palette, motion if animated else "") +
        '<rect width="%d" height="%d" fill="var(--sky)"/>' % (W, H) +
        layer(ridge, 78, "ridgeline") +
        layer(industry, 52, "industry") +
        layer(hills, 34, "hills") +
        ground +
        layer(trees, 15, "treeline") +
        road +
        layer(dashes, 1.9, "road-dashes") +
        '<g id="vehicle" transform="translate(%d %g) scale(1.12)">'
        % (TRUCK_X, AXLE_Y - AXLE_Y * 1.12) + truck_group(key, body) + "</g>" +
        "</svg>")


def main():
    os.makedirs(OUT, exist_ok=True)
    written = []
    for key in TRUCKS:
        for mode in ("light", "dark"):
            path = os.path.join(OUT, "%s-%s.svg" % (key, mode))
            with open(path, "w") as handle:
                handle.write(truck_svg(key, mode))
            written.append(path)
        path = os.path.join(OUT, "scene-%s.svg" % key)
        with open(path, "w") as handle:
            handle.write(scene_svg(key))
        written.append(path)

    for path in written:
        size = os.path.getsize(path)
        assert size < 100 * 1024, "%s is %d bytes, over the 100KB ceiling" % (path, size)
        print("  %-42s %5.1f KB" % (os.path.relpath(path, os.path.dirname(OUT)), size / 1024))


if __name__ == "__main__":
    main()
