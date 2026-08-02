#!/usr/bin/env python3
"""
map_schema.py — DETERMINISTIC cartographic schema from geo.json (MJ Tonnerre).

Goal: produce a CONDITIONING IMAGE (a flat-colour schema) from the actual spatial
graph, then passed as `--ref-image` to the illustration pipeline
(`mygamemaster-images`): the *code* fixes the composition, the *model* only needs
to embellish. The model is never asked to place anything.

  The LLM never reads the anchor coordinates (layer C, reserved for code):
  this script consumes them internally for drawing.

GROUND TRUTH (from geo.json): which locations exist, who is near whom,
which road connects what (anchor + edges + type).

SYNTHESISED (geo.json stores neither extent, nor size, nor path) — DETERMINISTIC
heuristics, exactly what a conditioning image must provide:
  * BIOMES — organic blobs around natural points (forest/hill/water…);
  * TOWN SIZE — built footprint derived from connectivity (degree) + containment
    (sub-locations): a well-connected crossroads becomes a market town;
  * WINDING ROADS — if an obstacle (hill/forest/cave) borders the straight
    segment, the road GOES AROUND IT (Bezier); otherwise slight natural curve.
    The player is free to cut straight across — it is the trade road that detours;
  * WATER — rivers as sinuous blue bands; edges with aquatic `voie`
    (ford/ferry/river/stream/sea/boat) drawn as wavy blue lines.

Labels: NUMBERED markers + side legend panel (default) — overlapping names gone.
The name list is also emitted (stdout + sidecar `.legend.txt`) to be injected
into the embellishment prompt. Modes: --labels numbered|inline|none.

⚠ Rasterisation: ImageMagick's INTERNAL SVG engine (used when librsvg/inkscape
are absent) renders ONLY `<rect>`/`<circle>`/`<polygon>`/`<line>`/`<text>` —
NOT `<path>` nor `<polyline>`. So only these primitives are emitted: curves
(winding roads, waterways) are sampled as `<line>` segments.

Fidelity modes (the "who drew the map" is carried by the caller):
  * normal       — schema faithful to the graph;
  * --unreliable — INTENTIONALLY misleading map (scrambled positions, ghost road
    and ghost location, swapped labels) for a failure / a trap.
    Deterministic via --seed. NOTHING on the image marks it as false.

Usage:
  python3 map_schema.py <campaign_folder> [--lieu <id>] [--out path.svg]
      [--no-png] [--width 1024] [--labels numbered|inline|none]
      [--unreliable] [--seed N]

Conventions (aligned with geo_query.py / worldlib.py):
  * first positional = path to the campaign folder;
  * PURE STDLIB; imports `worldlib` (never the reverse);
  * fail-open on read; codes: 0 ok; 1 nothing to draw; 2 usage/file.

Targets: Python 3.11.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import math
import random
import re
import shutil
import subprocess
import sys
from pathlib import Path

import worldlib as W


# ════════════════════════════════════════════════════════════════════════════
#  Semiology — type families
# ════════════════════════════════════════════════════════════════════════════

# SINGLE SOURCE OF TRUTH for semiology. Everything derives from it — layer colour,
# marker shape, obstacle status (detours), default biome extent,
# visual phrase injected into the prompt — so that the same type renders IDENTICALLY
# everywhere, every time (consistency + reproducibility). Changing this table = changing
# the render: bump `_TABLE_VERSION` to invalidate persisted map caches.
#
#   family  : "eau" | "biome" | "ville" | "repere" | "autre"
#   obstacle: True → TRADE ROADS go around it (depending on the mode of transport
#             in THIS universe, defined by the GM). This is NEVER a barrier: the
#             player can always leave the roads (climb, cross) — difficulty is the
#             GM's concern, not the map's. The detour is purely COSMETIC (legibility
#             of the known route).
#   etendue : default radius of the biome blob (× base_r); 0 = no fill area.
#             Overridden by the `etendue` attribute of the location in geo.json if present
#             → evolution (deforestation, drought…) is driven by the WORLD,
#             never by chance.
#   visuel  : default English description, injected into the embellishment prompt.
_TABLE_VERSION = 2

# Defaults (fantasy universe). Do NOT hardcode all game systems here: each campaign
# can extend/override via `map_semantics.json` (see charger_semantique) —
# new types, colours, visibility. The geo.json types remain the data;
# this table only says HOW to draw them.
#   visible : False → the type does NOT appear on the map (abstract/secret location).
_SEM = {
    "habitation":     {"color": "#b5651d", "shape": "carre",    "family": "ville",  "obstacle": False, "etendue": 0,   "visuel": "a small village of cottages"},
    "campement":      {"color": "#d98c2b", "shape": "triangle", "family": "ville",  "obstacle": False, "etendue": 0,   "visuel": "a camp of tents"},
    "edifice":        {"color": "#7a7a7a", "shape": "carre",    "family": "ville",  "obstacle": False, "etendue": 0,   "visuel": "a lone stone building"},
    "lieu-interet":   {"color": "#c8923a", "shape": "etoile",   "family": "repere", "obstacle": False, "etendue": 0,   "visuel": "a point of interest such as an inn, tavern or meeting place"},
    "site-ancien":    {"color": "#7b5ea7", "shape": "losange",  "family": "repere", "obstacle": False, "etendue": 0,   "visuel": "an ancient shrine of standing stones"},
    "menhir":         {"color": "#6b4f9e", "shape": "losange",  "family": "repere", "obstacle": False, "etendue": 0,   "visuel": "a lone standing stone (menhir)"},
    "ruine":          {"color": "#8a7a8f", "shape": "losange",  "family": "repere", "obstacle": False, "etendue": 0,   "visuel": "crumbling stone ruins"},
    "crypte":         {"color": "#4b3b63", "shape": "losange",  "family": "repere", "obstacle": False, "etendue": 0,   "visuel": "an underground crypt entrance"},
    "grotte":         {"color": "#4a4a4a", "shape": "rond",     "family": "biome",  "obstacle": True,  "etendue": 1.6, "visuel": "a dark cave mouth in rock"},
    "gouffre":        {"color": "#2e2a3a", "shape": "rond",     "family": "biome",  "obstacle": True,  "etendue": 1.8, "visuel": "a deep dark chasm / abyss"},
    "foret":          {"color": "#3f7d4f", "shape": "rond",     "family": "biome",  "obstacle": True,  "etendue": 2.6, "visuel": "dense green woodland"},
    "clairiere":      {"color": "#7bbf6a", "shape": "rond",     "family": "biome",  "obstacle": False, "etendue": 1.8, "visuel": "a sunlit forest clearing"},
    "zone-naturelle": {"color": "#5a9e6a", "shape": "rond",     "family": "biome",  "obstacle": False, "etendue": 2.2, "visuel": "wild natural ground"},
    "colline":        {"color": "#a9905a", "shape": "triangle", "family": "biome",  "obstacle": True,  "etendue": 2.0, "visuel": "a rocky hill"},
    "montagne":       {"color": "#8c7b6b", "shape": "triangle", "family": "biome",  "obstacle": True,  "etendue": 3.0, "visuel": "a high rocky mountain range with snowy peaks"},
    "desert":         {"color": "#d8c48a", "shape": "rond",     "family": "biome",  "obstacle": False, "etendue": 3.2, "visuel": "an arid desert of sand dunes"},
    "riviere":        {"color": "#3b7fb5", "shape": "rond",     "family": "eau",    "obstacle": False, "etendue": 1.8, "visuel": "a river ford with flowing blue water"},
    "sentier":        {"color": "#9b7b4b", "shape": "rond",     "family": "autre",  "obstacle": False, "etendue": 0,   "visuel": "a path marker"},
    "lieu":           {"color": "#8a8a8a", "shape": "rond",     "family": "autre",  "obstacle": False, "etendue": 0,   "visuel": "a small notable landmark"},
}
# Default record: any absent field falls back here. `visible` is True
# everywhere unless overridden (campaign override).
_SEM_DEFAUT = {"color": "#8a8a8a", "shape": "rond", "family": "autre",
               "obstacle": False, "etendue": 0, "visible": True,
               "visuel": "a landmark"}

# Campaign override (populated by main from map_semantics.json).
_OVERRIDE: dict = {}

_RE_VOIE_EAU = re.compile(
    r"gu[ée]|bac|fleuve|rivi[èe]re|ruisseau|mer|maritime|bateau|barque|pont", re.I)

_FOND = "#efe2bf"            # neutral parchment — final style is left to the model
_C_ROUTE = "#6b4a2a"
_C_EAU = "#3b7fb5"
_C_TEXTE = "#2b2218"
_C_BATI = "#9c6b3a"

# Campaign-level map config — BEHAVIOURS are genre-dependent,
# not just types. The GM generates it based on the universe; fantasy is only
# a default. E.g.: cyberpunk-jetpack → detours=false (you fly over); space →
# routes=false, compass=false, dark background (neither north nor terrain).
#   routes  : draw connections (edges) between locations
#   detours : roads go around obstacles (assumes GROUND-level travel)
#   compass : show the compass rose (does a "north" even make sense?)
#   fond    : background colour of the layer
_CARTE_DEFAUT = {"routes": True, "detours": True, "compass": True, "fond": _FOND}
_CARTE_CFG: dict = dict(_CARTE_DEFAUT)


def _sem(typ: str) -> dict:
    """Effective semiology record for a type: default < built-in <
    campaign override. Guarantees all keys (including `visible`)."""
    typ = typ or "lieu"
    return {**_SEM_DEFAUT, **_SEM.get(typ, {}), **_OVERRIDE.get(typ, {})}


def charger_semantique(camp: Path) -> dict:
    """Load the campaign semantic override (`map_semantics.json`), so that
    EVERY game (even non-existent ones: sci-fi, post-apoc…) can define ITS types
    and what should / should not appear. Format: {"types": {"<type>": {<fields>}}}.
    Fields (all optional): color, shape (rond|carre|triangle|losange|etoile),
    family (ville|biome|eau|repere|autre), obstacle (bool), etendue (float),
    visible (bool — False ⇒ never drawn), visuel (phrase for the prompt).
    Returns (types_override, carte_cfg)."""
    data = W.charger_json(camp / "map_semantics.json", {})
    if not data:  # pre-rename campaigns keep the French filename
        data = W.charger_json(camp / "carte_semantique.json", {})
    if not isinstance(data, dict):
        return {}, dict(_CARTE_DEFAUT)
    cfg = dict(_CARTE_DEFAUT)
    if isinstance(data.get("carte"), dict):
        cfg.update({k: data["carte"][k] for k in _CARTE_DEFAUT if k in data["carte"]})
    return data.get("types", {}), cfg


def _etendue(node: dict) -> float:
    """Effective extent of a biome: `etendue` attribute of the location (world)
    otherwise type default. Controls zone size in a DETERMINISTIC and grounded way."""
    rec = _sem(node.get("type") or "lieu")
    v = node.get("etendue")
    try:
        return float(v) if v is not None else float(rec["etendue"])
    except (TypeError, ValueError):
        return float(rec["etendue"])


def _rng(*cle) -> random.Random:
    """Deterministic and STABLE RNG across processes/machines (hash() is salted)."""
    h = hashlib.md5("|".join(map(str, cle)).encode()).hexdigest()[:12]
    return random.Random(int(h, 16))


# ════════════════════════════════════════════════════════════════════════════
#  Selection + projection (North up) — unchanged
# ════════════════════════════════════════════════════════════════════════════

def selectionner(geo: dict, lieu: str | None) -> list[dict]:
    tous = [n for n in geo.get("locations", []) or []
            if isinstance(n, dict) and isinstance(n.get("id"), str)
            and n.get("type") != "region"]
    if not lieu:
        return tous
    racine = W.lieu_racine(geo, lieu)
    if racine is None:
        return tous
    return [n for n in tous if W.lieu_racine(geo, n["id"]) == racine] or tous


def projeter(noeuds, largeur, marge):
    pts = {n["id"]: (float(n.get("ancrage", {}).get("x", 0)),
                     float(n.get("ancrage", {}).get("y", 0))) for n in noeuds}
    xs = [p[0] for p in pts.values()]
    ys = [p[1] for p in pts.values()]
    xmin, xmax, ymin, ymax = min(xs), max(xs), min(ys), max(ys)
    span = max(xmax - xmin, ymax - ymin)
    util = largeur - 2 * marge
    if span <= 1e-9:
        cote = max(1, math.ceil(math.sqrt(len(pts))))
        pas = util / max(1, cote - 1) if cote > 1 else 0
        out = {nid: (marge + (i % cote) * pas, marge + (i // cote) * pas)
               for i, nid in enumerate(pts)}
        return out, largeur
    ech = util / span
    hauteur = int(marge * 2 + (ymax - ymin) * ech)
    out = {nid: (marge + (x - xmin) * ech, marge + (ymax - y) * ech)
           for nid, (x, y) in pts.items()}
    return out, hauteur


# ════════════════════════════════════════════════════════════════════════════
#  Geometry
# ════════════════════════════════════════════════════════════════════════════

def _dist_point_segment(px, py, ax, ay, bx, by):
    """Distance from P to segment AB + parameter t of the foot of the perpendicular."""
    dx, dy = bx - ax, by - ay
    l2 = dx * dx + dy * dy
    if l2 <= 1e-9:
        return math.hypot(px - ax, py - ay), 0.0
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / l2))
    fx, fy = ax + t * dx, ay + t * dy
    return math.hypot(px - fx, py - fy), t


def _blob(cx, cy, r, cle, opacite, couleur, n=12) -> str:
    """Deterministic organic polygon (zone suggestion)."""
    rng = _rng("blob", cle)
    pts = []
    for i in range(n):
        ang = 2 * math.pi * i / n
        rr = r * rng.uniform(0.72, 1.28)
        pts.append(f"{cx + rr*math.cos(ang):.1f},{cy + rr*math.sin(ang):.1f}")
    return (f'<polygon points="{" ".join(pts)}" fill="{couleur}" '
            f'opacity="{opacite}"/>')


# ════════════════════════════════════════════════════════════════════════════
#  Edges (roads)
# ════════════════════════════════════════════════════════════════════════════

def _cle(a, b):
    return "|".join(sorted((a, b)))


def _aretes_uniques(geo, coords):
    """(a, b, voie) deduplicated, only rendered endpoints."""
    vues, out = set(), []
    for a in coords:
        for ar in W.aretes_sortantes(geo, a):
            b = ar.get("vers")
            if not isinstance(b, str) or b not in coords:
                continue
            if _cle(a, b) in vues:
                continue
            vues.add(_cle(a, b))
            out.append((a, b, ar.get("voie")))
    return out


def _echantillon_quad(p0, c, p1, n=16):
    """Quadratic Bezier → list of points (the SVG engine renders only <line>)."""
    pts = []
    for i in range(n + 1):
        t = i / n
        u = 1 - t
        pts.append((u * u * p0[0] + 2 * u * t * c[0] + t * t * p1[0],
                    u * u * p0[1] + 2 * u * t * c[1] + t * t * p1[1]))
    return pts


def _trace_route(a, b, coords, obstacles, est_eau):
    """Returns (points, est_eau): the road goes around the most obstructing obstacle,
    otherwise a slight natural curve. `points` is a polyline (segments <line>)."""
    x0, y0 = coords[a]
    x1, y1 = coords[b]
    mx, my = (x0 + x1) / 2, (y0 + y1) / 2
    seg = math.hypot(x1 - x0, y1 - y0) or 1.0
    nx, ny = -(y1 - y0) / seg, (x1 - x0) / seg   # unit normal

    if est_eau:
        return _ondule(x0, y0, x1, y1, amp=min(16, seg * 0.07)), True

    pire = None
    for cx, cy, r, nid in obstacles:
        if nid in (a, b):
            continue
        d, t = _dist_point_segment(cx, cy, x0, y0, x1, y1)
        if d < r and 0.08 < t < 0.92 and (pire is None or d < pire[3]):
            cote = (cx - mx) * nx + (cy - my) * ny  # side the obstacle is on
            pire = (r - d, cote, r, d)
    if pire is not None:
        _, cote, r, d = pire
        # The curve only moves by half the control point offset → ×2.
        ecart = max((r + 0.5 * r) - d, 0.3 * r)
        ctrl = 2.0 * ecart * (-1 if cote >= 0 else 1)
        c = (mx + nx * ctrl, my + ny * ctrl)
        return _echantillon_quad((x0, y0), c, (x1, y1)), False

    # No obstacle: light, deterministic natural curve.
    g = _rng("route", _cle(a, b)).uniform(-1, 1) * seg * 0.05
    c = (mx + nx * g, my + ny * g)
    return _echantillon_quad((x0, y0), c, (x1, y1)), False


def _ondule(x0, y0, x1, y1, amp, n=14):
    """Wavy polyline (waterway / river route)."""
    seg = math.hypot(x1 - x0, y1 - y0) or 1.0
    nx, ny = -(y1 - y0) / seg, (x1 - x0) / seg
    pts = []
    for i in range(n + 1):
        t = i / n
        bx, by = x0 + (x1 - x0) * t, y0 + (y1 - y0) * t
        off = amp * math.sin(t * math.pi * 3)
        pts.append((bx + nx * off, by + ny * off))
    return pts


def _segments(points, couleur, width, dash=None):
    """Polyline → sequence of <line> elements (the only stroke primitive rendered everywhere)."""
    d = f' stroke-dasharray="{dash}"' if dash else ''
    out = []
    for (x0, y0), (x1, y1) in zip(points, points[1:]):
        out.append(f'<line x1="{x0:.1f}" y1="{y0:.1f}" x2="{x1:.1f}" y2="{y1:.1f}" '
                   f'stroke="{couleur}" stroke-width="{width}" '
                   f'stroke-linecap="round"{d}/>')
    return "".join(out)


# ════════════════════════════════════════════════════════════════════════════
#  Markers / footprints
# ════════════════════════════════════════════════════════════════════════════

def _marqueur(forme, x, y, r, couleur):
    if forme == "carre":
        return (f'<rect x="{x-r:.1f}" y="{y-r:.1f}" width="{2*r:.1f}" '
                f'height="{2*r:.1f}" fill="{couleur}" stroke="#2b2218" stroke-width="1.5"/>')
    if forme == "triangle":
        p = f"{x:.1f},{y-r:.1f} {x-r:.1f},{y+r:.1f} {x+r:.1f},{y+r:.1f}"
        return f'<polygon points="{p}" fill="{couleur}" stroke="#2b2218" stroke-width="1.5"/>'
    if forme == "losange":
        p = f"{x:.1f},{y-r:.1f} {x+r:.1f},{y:.1f} {x:.1f},{y+r:.1f} {x-r:.1f},{y:.1f}"
        return f'<polygon points="{p}" fill="{couleur}" stroke="#2b2218" stroke-width="1.5"/>'
    if forme == "etoile":   # point of interest (inn, meeting point…)
        pts = []
        for i in range(10):
            ang = -math.pi / 2 + i * math.pi / 5
            rad = r if i % 2 == 0 else r * 0.42
            pts.append(f"{x + rad*math.cos(ang):.1f},{y + rad*math.sin(ang):.1f}")
        return f'<polygon points="{" ".join(pts)}" fill="{couleur}" stroke="#2b2218" stroke-width="1.5"/>'
    return (f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r:.1f}" fill="{couleur}" '
            f'stroke="#2b2218" stroke-width="1.5"/>')


def _emprise_ville(x, y, r, cle, importance):
    """Built-up patch + a few buildings — size ∝ importance."""
    s = [_blob(x, y, r, ("ville", cle), 0.5, _C_BATI, n=10)]
    rng = _rng("bati", cle)
    n_bat = min(8, 1 + importance)
    for _ in range(n_bat):
        ang = rng.uniform(0, 2 * math.pi)
        rad = rng.uniform(0, r * 0.7)
        bx, by = x + rad * math.cos(ang), y + rad * math.sin(ang)
        c = r * rng.uniform(0.12, 0.22)
        s.append(f'<rect x="{bx-c:.1f}" y="{by-c:.1f}" width="{2*c:.1f}" '
                 f'height="{2*c:.1f}" fill="#6b4423" stroke="#3a2410" stroke-width="0.8"/>')
    return "".join(s)


# ════════════════════════════════════════════════════════════════════════════
#  "Unreliable" mode
# ════════════════════════════════════════════════════════════════════════════

def fausser(geo, noeuds, coords, largeur, hauteur, seed):
    rng = random.Random(seed)
    amp = 0.18 * largeur
    coords2 = {nid: (max(0.0, min(largeur, x + rng.uniform(-amp, amp))),
                     max(0.0, min(hauteur, y + rng.uniform(-amp, amp))))
               for nid, (x, y) in coords.items()}
    noms = {n["id"]: n.get("name", "") for n in noeuds}
    ids = list(noms)
    if len(ids) >= 2:
        a, b = rng.sample(ids, 2)
        noms[a], noms[b] = noms[b], noms[a]
    routes_fantomes = [tuple(rng.sample(ids, 2))] if len(ids) >= 2 else []
    fantome = None
    if ids:
        fantome = {"id": "__fantome__",
                   "name": rng.choice(["Old Ford", "Standing Stone", "Forgotten Spring",
                                      "Raven's Crossroads", "Grey Mound"]),
                   "type": rng.choice(["ruine", "menhir", "habitation"]),
                   "px": rng.uniform(0, largeur), "py": rng.uniform(0, hauteur)}
    supprimees = set()
    ar = _aretes_uniques(geo, coords)
    if ar:
        v = rng.choice(ar)
        supprimees.add(_cle(v[0], v[1]))
    return coords2, noms, routes_fantomes, supprimees, fantome


# ════════════════════════════════════════════════════════════════════════════
#  SVG rendering
# ════════════════════════════════════════════════════════════════════════════

def rendre_svg(geo, noeuds, coords, largeur, hauteur, titre, focus,
               labels_mode, truque=None):
    idx = {n["id"]: n for n in noeuds}
    noms = {n["id"]: n.get("name", "") for n in noeuds}
    types = {n["id"]: (n.get("type") or "lieu") for n in noeuds}
    degre = {n["id"]: len(W.aretes_sortantes(geo, n["id"])) for n in noeuds}
    contenance = {n["id"]: len(W.contenus(geo, n["id"])) for n in noeuds}

    routes_fantomes, supprimees, fantome = [], set(), None
    if truque:
        coords, noms, routes_fantomes, supprimees, fantome = truque

    base_r = max(6.0, largeur / 95)

    # Synthesised radii — grounded biome extent (`etendue` attribute of the location
    # otherwise type default), town size ∝ connectivity + containment.
    rayon_blob, rayon_ville, importance = {}, {}, {}
    for nid in coords:
        rec = _sem(types.get(nid, "lieu"))
        if rec["family"] in ("biome", "eau"):
            fact = _etendue(idx[nid]) if nid in idx else rec["etendue"]
            if fact > 0:
                rayon_blob[nid] = base_r * fact
        if rec["family"] == "ville":
            imp = degre.get(nid, 0) + contenance.get(nid, 0)
            importance[nid] = imp
            rayon_ville[nid] = base_r * (1.0 + min(2.2, 0.45 * imp))

    panneau = 320 if labels_mode == "numbered" else 0   # "pins" = numbers without panel
    W_tot = largeur + panneau

    s = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W_tot}" '
         f'height="{hauteur}" viewBox="0 0 {W_tot} {hauteur}">']
    s.append(f'<rect width="{W_tot}" height="{hauteur}" fill="{_CARTE_CFG["fond"]}"/>')

    # 1) Biomes (zones) beneath everything else.
    for nid, r in rayon_blob.items():
        couleur = _sem(types[nid])["color"]
        x, y = coords[nid]
        s.append(_blob(x, y, r, ("biome", nid), 0.22, couleur))

    # 1b) Water bands between adjacent rivers.
    obstacles = [(coords[nid][0], coords[nid][1], rayon_blob[nid] * 0.85, nid)
                 for nid in rayon_blob if _sem(types[nid])["obstacle"]]
    for a, b, voie in _aretes_uniques(geo, coords):
        if types.get(a) == "riviere" and types.get(b) == "riviere":
            x0, y0 = coords[a]
            x1, y1 = coords[b]
            s.append(_segments(_ondule(x0, y0, x1, y1, amp=10), _C_EAU, 9))

    # 2) Roads — only if the campaign draws them (see travel mode).
    #    detours=false (flight/jetpack/space) ⇒ straight connections, no detours.
    for a, b, voie in _aretes_uniques(geo, coords) if _CARTE_CFG["routes"] else []:
        if _cle(a, b) in supprimees:
            continue
        est_eau = bool(voie and _RE_VOIE_EAU.search(str(voie))) or \
            (types.get(a) == "riviere" and types.get(b) == "riviere")
        if not _CARTE_CFG["detours"]:
            pts, eau = [coords[a], coords[b]], est_eau
        else:
            pts, eau = _trace_route(a, b, coords, obstacles, est_eau)
        if eau:
            s.append(_segments(pts, _C_EAU, 3.5))
        else:
            # Light halo to lift it off the background/zones, then the stroke.
            s.append(_segments(pts, "#f3ead0", 6))
            dash = "7,6" if voie and "sentier" in str(voie).lower() else None
            s.append(_segments(pts, _C_ROUTE, 3.2, dash=dash))
    for a, b in routes_fantomes:
        if a in coords and b in coords:
            s.append(_segments([coords[a], coords[b]], _C_ROUTE, 3.2))

    # 3) Numbering (top→bottom, left→right) for the legend.
    ordre = sorted(coords, key=lambda nid: (coords[nid][1], coords[nid][0]))
    if fantome:
        ordre.append(fantome["id"])
        coords = {**coords, fantome["id"]: (fantome["px"], fantome["py"])}
        types = {**types, fantome["id"]: fantome["type"]}
        noms = {**noms, fantome["id"]: fantome["name"]}
    numero = {nid: i + 1 for i, nid in enumerate(ordre)}

    # 4) Markers + labels.
    for nid in ordre:
        x, y = coords[nid]
        typ = types.get(nid, "lieu")
        rec = _sem(typ)
        couleur, forme, fam = rec["color"], rec["shape"], rec["family"]
        focus_actif = (nid == focus)
        if fam == "ville":
            s.append(_emprise_ville(x, y, rayon_ville.get(nid, base_r),
                                    nid, importance.get(nid, 0)))
        else:
            rr = base_r * (1.4 if focus_actif else 1.0)
            s.append(_marqueur(forme, x, y, rr, couleur))
        if focus_actif:
            s.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{base_r*1.9:.1f}" '
                     f'fill="none" stroke="#c83737" stroke-width="2.5"/>')
        if labels_mode in ("numbered", "pins"):
            s.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{base_r*0.78:.1f}" '
                     f'fill="#fbf3da" stroke="#2b2218" stroke-width="1.2"/>')
            s.append(f'<text x="{x:.1f}" y="{y + base_r*0.32:.1f}" '
                     f'font-size="{base_r*0.95:.0f}" font-family="serif" '
                     f'text-anchor="middle" fill="{_C_TEXTE}">{numero[nid]}</text>')
        elif labels_mode == "inline" and noms.get(nid):
            s.append(f'<text x="{x:.1f}" y="{y+base_r+13:.1f}" font-size="13" '
                     f'font-family="serif" text-anchor="middle" '
                     f'fill="{_C_TEXTE}">{html.escape(noms[nid])}</text>')

    # 5) Compass rose (if a "north" makes sense) + title.
    if _CARTE_CFG["compass"]:
        s.append(_rose(largeur - 55, 60, 26))
    s.append(f'<text x="20" y="32" font-size="20" font-family="serif" '
             f'font-weight="bold" fill="{_C_TEXTE}">{html.escape(titre)}</text>')

    # 6) Legend panel (numbered mode).
    legende = [(numero[nid], noms.get(nid, ""), types.get(nid, "lieu")) for nid in ordre]
    if labels_mode == "numbered":
        lx = largeur + 16
        s.append(f'<line x1="{largeur}" y1="0" x2="{largeur}" y2="{hauteur}" '
                 f'stroke="#cbb98a" stroke-width="2"/>')
        s.append(f'<text x="{lx}" y="34" font-size="16" font-family="serif" '
                 f'font-weight="bold" fill="{_C_TEXTE}">Legend</text>')
        ly = 58
        for num, nom, typ in legende:
            # A single <text>: ImageMagick's SVG engine does not position <tspan> elements.
            ligne = f"{num}. {nom}  ·  {typ}"
            s.append(f'<text x="{lx}" y="{ly}" font-size="12.5" font-family="serif" '
                     f'fill="{_C_TEXTE}">{html.escape(ligne)}</text>')
            ly += 19
            if ly > hauteur - 20:
                break
    s.append('</svg>')
    return "\n".join(s), legende


def _rose(cx, cy, r):
    return (f'<g><line x1="{cx}" y1="{cy-r}" x2="{cx}" y2="{cy+r}" stroke="{_C_TEXTE}" stroke-width="2"/>'
            f'<line x1="{cx-r}" y1="{cy}" x2="{cx+r}" y2="{cy}" stroke="{_C_TEXTE}" stroke-width="2"/>'
            f'<polygon points="{cx},{cy-r} {cx-5},{cy-r+10} {cx+5},{cy-r+10}" fill="{_C_TEXTE}"/>'
            f'<text x="{cx}" y="{cy-r-5}" font-size="13" font-family="serif" '
            f'text-anchor="middle" fill="{_C_TEXTE}">N</text></g>')


# ════════════════════════════════════════════════════════════════════════════
#  SVG → PNG rasterisation (best effort)
# ════════════════════════════════════════════════════════════════════════════

def _police():
    for c in ["/System/Library/Fonts/Supplemental/Times New Roman.ttf",
              "/System/Library/Fonts/Supplemental/Georgia.ttf",
              "/System/Library/Fonts/Helvetica.ttc",
              "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf",
              "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
              "/usr/share/fonts/truetype/liberation/LiberationSerif-Regular.ttf"]:
        if Path(c).exists():
            return c
    return None


def rasteriser(svg_path, png_path):
    outil = shutil.which("magick") or shutil.which("convert")
    if not outil:
        return False
    police = _police()

    def tenter(cmd):
        try:
            r = subprocess.run(cmd, capture_output=True, timeout=60)
            return r.returncode == 0 and png_path.exists() and png_path.stat().st_size > 0
        except (OSError, subprocess.SubprocessError):
            return False

    if png_path.exists():
        png_path.unlink()
    if police and tenter([outil, "-density", "150", "-font", police,
                          str(svg_path), str(png_path)]):
        return True
    if tenter([outil, "-density", "150", str(svg_path), str(png_path)]):
        return True
    sans = re.sub(r"<text[^>]*>.*?</text>", "", svg_path.read_text(), flags=re.DOTALL)
    tmp = svg_path.with_suffix(".notext.svg")
    tmp.write_text(sans)
    try:
        return tenter([outil, "-density", "150", str(tmp), str(png_path)])
    finally:
        tmp.unlink(missing_ok=True)


# ════════════════════════════════════════════════════════════════════════════
#  Versioning (consistency over time) + reproducible prompt
# ════════════════════════════════════════════════════════════════════════════

def geo_hash(noeuds: list[dict]) -> str:
    """Short and STABLE fingerprint of the rendered geo state (id, type, anchor, extent,
    edges) + semiology table version. Same world → same hash → same map.
    Used for versioning: a new hash ⇒ the world changed ⇒ new map to persist
    (the old one stays, history is preserved)."""
    payload = []
    for n in sorted(noeuds, key=lambda x: x["id"]):
        ar = sorted(
            ((a.get("vers"), a.get("dir"), a.get("distance_m"), a.get("voie"))
             for a in (n.get("aretes") or []) if isinstance(a, dict)),
            key=lambda t: str(t))
        payload.append((n["id"], n.get("type"), n.get("ancrage"),
                        n.get("etendue"), ar))
    # Semiology + map config included: any change = new version.
    blob = json.dumps([_TABLE_VERSION, _OVERRIDE, _CARTE_CFG, payload],
                      sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha1(blob.encode("utf-8")).hexdigest()[:10]


def construire_prompt(camp: Path, legende: list[tuple]) -> str:
    """REPRODUCIBLE embellishment prompt (model-independent): world style
    (world.json > meta.style_visuel.description_complete) + fixed cartographic
    scaffold + per-number description drawn from the semiology table."""
    monde = W.charger_json(camp / "world.json", {})
    style = (((monde.get("meta") or {}).get("style_visuel") or {})
             .get("description_complete")
             or "Hand-drawn fantasy cartography, aged parchment, ink and watercolour.")
    lignes = [f"{num} = {nom}: {_sem(typ)['visuel']}" for num, nom, typ in legende]
    return (
        f"{style} A top-down hand-drawn REGION MAP. The spatial layout is FIXED by "
        "the tracing reference image — only paint the style over it. Forests as green "
        "woodland, water/rivers/marsh in blue, roads as winding ink trade-paths exactly "
        "along the reference lines, a compass rose pointing north at top-right, aged "
        "background. Each numbered pin is a place: render it per its type and write its "
        "name as a small hand-drawn label beside it.\nLocations:\n"
        + "\n".join(lignes)
        + "\nAvoid: photorealistic, satellite, modern elements; never move, add or remove a location."
    )


# ════════════════════════════════════════════════════════════════════════════
#  Command-line interface
# ════════════════════════════════════════════════════════════════════════════

def main() -> int:
    p = argparse.ArgumentParser(
        description="Deterministic cartographic schema from geo.json.")
    p.add_argument("campagne", help="Path to the campaign folder.")
    p.add_argument("--lieu", help="Centre on the region of this location (id).")
    p.add_argument("--out", help="SVG output (default: <campaign>/images/cartes/_schema.svg).")
    p.add_argument("--no-png", action="store_true", help="Do not rasterise to PNG.")
    p.add_argument("--width", type=int, default=1024, help="Map width (px).")
    p.add_argument("--labels", choices=["numbered", "pins", "inline", "none"],
                   default="numbered",
                   help="numbered=numbers+legend panel · pins=numbers only (legend in prompt) "
                        "· inline=names on map · none=nothing.")
    p.add_argument("--unreliable", action="store_true",
                   help="INTENTIONALLY misleading map (failure/trap). Deterministic via --seed.")
    p.add_argument("--seed", type=int, default=1, help="Seed for --unreliable mode.")
    p.add_argument("--emit-prompt", action="store_true",
                   help="Also write the reproducible embellishment prompt (<out>.prompt.txt).")
    p.add_argument("--version", action="store_true",
                   help="Version by geo hash: suffixes outputs with the world fingerprint "
                        "(keeps history instead of overwriting).")
    p.add_argument("--dump-semantique", action="store_true",
                   help="Write an annotated map_semantics.json template (effective table) then exit.")
    args = p.parse_args()

    camp = W.chemin_campagne(args.campagne)

    # Semantic override + campaign map config (extensible by the GM, all universes).
    global _OVERRIDE, _CARTE_CFG
    _OVERRIDE, _CARTE_CFG = charger_semantique(camp)

    if args.dump_semantique:
        eff = {t: {k: _sem(t)[k] for k in ("color", "shape", "family",
                                           "obstacle", "etendue", "visible", "visuel")}
               for t in sorted(set(_SEM) | set(_OVERRIDE))}
        modele = {"_doc": (
                      "Map semantics for THIS campaign — this is YOUR data, GM, "
                      "to shape according to your universe (the fantasy below is just a starting "
                      "point; add space unicorns, wormholes, whatever you want). "
                      "The map shows TRADE ROUTES = the easiest paths "
                      "for transport in your world; a type `obstacle:true` is what these "
                      "routes go around — NEVER a hard barrier: the player can always leave "
                      "the routes (climb, cross a river against the current…), and it's "
                      "YOU who adjudicates the difficulty (tools: geo_query distance/path/"
                      "--as-the-crow-flies/crossing). `carte` = behaviors per transport: "
                      "detours=false if flying over (jetpack, ship); routes=false / "
                      "compass=false if neither roads nor north (space). "
                      "Types: visible=false ⇒ never drawn; shape: circle|square|triangle|"
                      "diamond|star; family: city|biome|water|landmark|other."),
                  "carte": _CARTE_CFG,
                  "types": eff}
        out = camp / "map_semantics.example.json"
        out.write_text(json.dumps(modele, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"📝 Semantic template written: {out}")
        return 0

    geo = W.charger_json(camp / "geo.json", {})
    if not geo or not geo.get("locations"):
        print(f"⚠  No usable geo.json in {camp} "
              f"(run `geo_query.py build` first).", file=sys.stderr)
        return 2

    noeuds = selectionner(geo, args.lieu)
    # Visibility filter: a `visible:false` type never appears (and its roads
    # disappear with it — it is no longer a rendered edge endpoint).
    noeuds = [n for n in noeuds if _sem(n.get("type") or "lieu")["visible"]]
    if not noeuds:
        print("⚠  No location to render.", file=sys.stderr)
        return 1

    coords, hauteur = projeter(noeuds, args.width, marge=70)
    titre = geo.get("meta", {}).get("campagne") or camp.name
    if args.lieu:
        idx = W.index_lieux(geo)
        racine = W.lieu_racine(geo, args.lieu)
        if racine and racine in idx:
            titre = idx[racine].get("name", titre)

    truque = fausser(geo, noeuds, coords, args.width, hauteur, args.seed) \
        if args.unreliable else None

    svg, legende = rendre_svg(geo, noeuds, coords, args.width, hauteur, titre,
                              args.lieu, args.labels, truque)

    # Fingerprint of the rendered geo state: versions (history) and triggers regeneration.
    vhash = geo_hash(noeuds)

    out_svg = Path(args.out) if args.out else (camp / "images" / "cartes" / "_schema.svg")
    if args.version:   # suffix by hash → old version stays on disk
        out_svg = out_svg.with_name(f"{out_svg.stem}.{vhash}{out_svg.suffix}")
    out_svg.parent.mkdir(parents=True, exist_ok=True)
    out_svg.write_text(svg, encoding="utf-8")
    out_svg.with_suffix(".hash").write_text(vhash, encoding="utf-8")

    # Legend → sidecar (to be injected into the embellishment prompt).
    if args.labels in ("numbered", "pins"):
        out_svg.with_suffix(".legend.txt").write_text(
            "\n".join(f"{n}. {nom} ({typ})" for n, nom, typ in legende), encoding="utf-8")

    # Reproducible embellishment prompt.
    if args.emit_prompt:
        out_svg.with_suffix(".prompt.txt").write_text(
            construire_prompt(camp, legende), encoding="utf-8")

    chemin = out_svg
    if not args.no_png:
        out_png = out_svg.with_suffix(".png")
        if rasteriser(out_svg, out_png):
            chemin = out_png
        else:
            print("ℹ  No rasteriser found (ImageMagick) — SVG only.", file=sys.stderr)

    marqueur = "⚠ UNRELIABLE (falsified)" if args.unreliable else "faithful"
    print(f"🗺  Schema {marqueur} — {len(noeuds)} locations — v:{vhash} — {chemin}")
    if args.labels in ("numbered", "pins"):
        print("   names (for the embellishment prompt):")
        for n, nom, typ in legende:
            print(f"     {n}. {nom} ({typ})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
