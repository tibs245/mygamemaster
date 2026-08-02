#!/usr/bin/env python3
"""
geo_query.py — DETERMINISTIC spatial queries for the "living world" (MJ Tonnerre).

Purpose (contract §4, doc 01 §6): answer EXACTLY "who is where / around /
path / crossing" and DECLARE movements — the LLM NEVER produces
coordinates. All geometry is deterministic: this script reads the spatial graph
(`geo.json`), actors (`actors.json`) and the campaign (`world.json`, READ-ONLY)
and computes. The LLM queries and narrates; it computes nothing.

This module is both:
  * IMPORTABLE — `from geo_query import ou_est, qui_est_a, voisins, chemin,
    distance, dans_rayon, croisement, creer_lieu, deplacer, valider_geo` ;
  * EXECUTABLE — CLI `argparse` with subcommands (first positional = campaign),
    messages in English, markers (📍 ➜ ⏱ ⚠), optional `--json` output.

Subcommands (map 1-1 to functions):
  build       <campaign> [--apply] [--force]      generates geo.json (containment +
                                                  adjacency + MDS anchor)
  ou-est      <campaign> <entite_id> [--t T]
  qui-est-a   <campaign> <lieu_id> [--t T] [--rayon R]
  voisins     <campaign> <lieu_id>
  chemin      <campaign> <a> <b>
  distance    <campaign> <a> <b> [--vol-d-oiseau]
  dans-rayon  <campaign> <point_id> <rayon> [--t T]
  croisement  <campaign> --traj-a <f|-|@id> --traj-b <f|-|@id> --seuil D [--pas-ut N]
  creer-lieu  <campaign> --nom STR --depuis ID --dir DIR --distance-m M [--type T]
                          [--parent ID] [--apply]
  deplacer    <campaign> --entite ID --vers ID --depart-t T [--motif STR] [--apply]
  valider     <campaign>

Cross-cutting conventions (contract §0):
  * source of truth = files; no state outside files;
  * NON-DESTRUCTIVE: NEVER writes to world.json / npcs.json / events.json /
    hooks / existing scripts. WRITES only geo.json (build, creer-lieu)
    and actors.json (deplacer), and only in --apply mode, via worldlib's
    atomic write;
  * exit codes: 0 ok; 1 business condition signaled (nothing found, path
    nonexistent, no crossing, violations refusing a write); 2 usage /
    file not found / broken JSON;
  * fail-open on READ (queries return an empty/degraded result rather than
    raising); fail-hard possible OUTSIDE loop (build / --apply).

Targets: Python 3.11, PURE STDLIB (no external dependencies). Imports `worldlib`
(never the reverse); imports NO other script from the contract (parallel
development). See contract `docs/living-world/08-implementation-contract.md` §4, §5,
§13, §14.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

import worldlib as W


SCRIPTS_DIR = Path(__file__).resolve().parent
GEO_VERSION = 1


def _log(message: str) -> None:
    """Trace to stderr (never pollutes --json on stdout)."""
    print(message, file=sys.stderr)


# ════════════════════════════════════════════════════════════════════════════
#  GENERIC containment derivation — no hardcoded campaign name/id
# ════════════════════════════════════════════════════════════════════════════
#
# `build` reflects the CONTAINMENT and ids carried BY THE DATA: each
# region/location in world.json carries its own `id` field (hierarchical) and, for
# locations, `alias`. geo_query therefore knows NO location name nor campaign id:
# it READS everything from world.json. The parent of a location is DERIVED from its
# hierarchical id (cf. `_parent_depuis_id`). If a campaign does not provide an id,
# it is forged by slug (generic, see `_collecter_lieux`).


def _parent_depuis_id(lid) -> str | None:
    """Derives the parent of a location from its hierarchical id (pure string computation).

      * `region:*`                       → None (regions are roots);
      * `lieu:<R>/<a>` (1 segment)       → `region:<R>`;
      * `lieu:<R>/<a>/<b>/…` (≥2 segm.)  → `lieu:<R>/<…everything except last>`.
    Generic: no campaign name, no table. None if id is not usable.
    """
    if not isinstance(lid, str) or ":" not in lid:
        return None
    prefixe, chemin = lid.split(":", 1)
    if prefixe == "region":
        return None
    if prefixe != "lieu":
        return None
    segments = [s for s in chemin.split("/") if s != ""]
    if len(segments) < 2:
        # No sub-path under the region → malformed id for a location.
        return None
    region = segments[0]
    if len(segments) == 2:
        # `lieu:<R>/<a>` → parent = the region.
        return f"region:{region}"
    # `lieu:<R>/<a>/…/<last>` → parent = the location without its last segment.
    return "lieu:" + "/".join(segments[:-1])


# Mapping of record type labels (world.json) → geo.schema.json enum.
# Defaults to "lieu" if unrecognized (the schema keeps the enum, we stay within it).
_TYPE_FICHE_VERS_GEO = {
    "habitation": "habitation",
    "cabane": "habitation",
    "maison": "habitation",
    "campement": "campement",
    "camp": "campement",
    "village": "habitation",
    "hameau": "habitation",
    "site-ancien": "site-ancien",
    "site ancien": "site-ancien",
    "site_ancien": "site-ancien",
    "menhir": "menhir",
    "dolmen": "menhir",
    "ruine": "ruine",
    "ruines": "ruine",
    "foret": "foret",
    "forêt": "foret",
    "bois": "foret",
    "clairiere": "clairiere",
    "clairière": "clairiere",
    "grotte": "grotte",
    "cave": "grotte",
    "colline": "colline",
    "butte": "colline",
    "riviere": "riviere",
    "rivière": "riviere",
    "gue": "riviere",
    "gué": "riviere",
    "fleuve": "riviere",
    "ruisseau": "riviere",
    "sentier": "sentier",
    "chemin": "sentier",
    "crypte": "crypte",
    "salle": "crypte",
    "edifice": "edifice",
    "temple": "edifice",
    "fort": "ruine",
    "marais": "zone-naturelle",
    "zone-naturelle": "zone-naturelle",
    "zone naturelle": "zone-naturelle",
    "montagne": "montagne",
    "mont": "montagne",
    "pic": "montagne",
    "gouffre": "gouffre",
    "abime": "gouffre",
    "abîme": "gouffre",
    "desert": "desert",
    "désert": "desert",
    "auberge": "lieu-interet",
    "taverne": "lieu-interet",
    "relais": "lieu-interet",
    "point de rencontre": "lieu-interet",
    "point-de-rencontre": "lieu-interet",
    "lieu-interet": "lieu-interet",
    "lieu d'interet": "lieu-interet",
}

_TYPES_GEO_VALIDES = {
    "region", "habitation", "campement", "site-ancien", "menhir", "ruine",
    "foret", "clairiere", "grotte", "colline", "riviere", "sentier", "crypte",
    "edifice", "zone-naturelle", "lieu",
    # Additional types (rendered by map_schema; extensible per campaign).
    "montagne", "gouffre", "desert", "lieu-interet",
}


def _norm_nom(nom: str) -> str:
    """Normalizes a record name/type (generic TYPE lookup utility).

    NFKD without diacritics, lowercase, « ° » and « n° » reduced, any character
    outside [a-z0-9()] becomes a space, spaces reduced.
    """
    if not nom:
        return ""
    s = unicodedata.normalize("NFKD", str(nom))
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.lower()
    s = s.replace("n°", "n ").replace("°", " ")
    s = s.replace("œ", "oe").replace("æ", "ae")
    s = re.sub(r"[^a-z0-9()]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _type_geo(type_fiche) -> str:
    """Maps a record type (world.json) to the geo enum, default 'lieu'."""
    if not isinstance(type_fiche, str):
        return "lieu"
    brut = _norm_nom(type_fiche)
    if brut in _TYPE_FICHE_VERS_GEO:
        return _TYPE_FICHE_VERS_GEO[brut]
    if brut in _TYPES_GEO_VALIDES:
        return brut
    # Soft heuristic on the first word.
    premier = brut.split(" ", 1)[0] if brut else ""
    if premier in _TYPE_FICHE_VERS_GEO:
        return _TYPE_FICHE_VERS_GEO[premier]
    if premier in _TYPES_GEO_VALIDES:
        return premier
    return "lieu"


# ════════════════════════════════════════════════════════════════════════════
#  Extraction of cardinal DIRECTION from a French description
# ════════════════════════════════════════════════════════════════════════════
#
# Graph edges carry a direction (N, NE, E, SE, S, SO, O, NO, or '?').
# Descriptions in `regles.temps.deplacements` often give it in plain text
# ("à l'ouest", "direction nord-est", "nord-nord-est"). It is extracted via a
# pattern table, from MOST SPECIFIC to most general (compound directions first).

_OPPOSE_DIR = {
    "N": "S", "S": "N", "E": "O", "O": "E",
    "NE": "SO", "SO": "NE", "NO": "SE", "SE": "NO", "?": "?",
}

# Order: compound (8-wind) BEFORE simple cardinals, otherwise "nord-est" would be
# captured by "nord". "nord-nord-est", "est-nord-est"… → mapped to the nearest
# 8-wind (contract §5: "nord-nord-est → N" is the given example).
_MOTIFS_DIRECTION = [
    # 16-wind mapped to 8-wind (contract: nord-nord-est → N).
    (r"nord[\s\-]*nord[\s\-]*est", "N"),
    (r"nord[\s\-]*nord[\s\-]*ouest", "N"),
    (r"sud[\s\-]*sud[\s\-]*est", "S"),
    (r"sud[\s\-]*sud[\s\-]*ouest", "S"),
    (r"est[\s\-]*nord[\s\-]*est", "E"),
    (r"est[\s\-]*sud[\s\-]*est", "E"),
    (r"ouest[\s\-]*nord[\s\-]*ouest", "O"),
    (r"ouest[\s\-]*sud[\s\-]*ouest", "O"),
    # 8-wind compound directions.
    (r"nord[\s\-]*est", "NE"),
    (r"nord[\s\-]*ouest", "NO"),
    (r"sud[\s\-]*est", "SE"),
    (r"sud[\s\-]*ouest", "SO"),
    # simple cardinals (with common articles).
    (r"(?:vers le |au |du |à l['’ ]|l['’ ]|le )?nord\b", "N"),
    (r"(?:vers le |au |du |à l['’ ]|l['’ ]|le )?sud\b", "S"),
    (r"(?:vers l['’ ]|à l['’ ]|l['’ ]|l['’])?est\b", "E"),
    (r"(?:vers l['’ ]|à l['’ ]|l['’ ]|l['’])?ouest\b", "O"),
]


def _direction_depuis_description(desc: str) -> str:
    """Extracts a cardinal direction (8-wind) from a description, '?' if absent.

    Takes the FIRST direction mentioned (most relevant: the initial heading of
    the travel). Compound before cardinals to avoid "nord-est" captured by "nord".
    """
    if not desc or not isinstance(desc, str):
        return "?"
    s = unicodedata.normalize("NFKD", desc)
    s = "".join(c for c in s if not unicodedata.combining(c)).lower()

    meilleure_pos = None
    meilleure_dir = "?"
    for motif, direction in _MOTIFS_DIRECTION:
        m = re.search(motif, s)
        if m is None:
            continue
        # We keep the direction whose pattern appears EARLIEST; at equal position,
        # the table (compound first) breaks ties deterministically.
        pos = m.start()
        if meilleure_pos is None or pos < meilleure_pos:
            meilleure_pos = pos
            meilleure_dir = direction
    return meilleure_dir


def _voie_depuis_description(desc: str) -> str | None:
    """Extracts the 'voie' (travel text) from a description: what follows the duration
    dash ("40min — à l'ouest, suivre le ruisseau…" → "à l'ouest, …").

    Returns a compact version (gently truncated) or None.
    """
    if not desc or not isinstance(desc, str):
        return None
    # Separates the initial duration from the description (— or long -).
    parts = re.split(r"\s+[—–-]\s+", desc, maxsplit=1)
    voie = parts[1].strip() if len(parts) == 2 else desc.strip()
    # Compact: remove carriage returns, truncate cleanly to ~110 characters.
    voie = re.sub(r"\s+", " ", voie)
    if len(voie) > 110:
        voie = voie[:107].rstrip() + "…"
    return voie or None


def _vecteur_dir(direction: str) -> tuple[float, float]:
    """Unit vector (x→East, y→North) for an 8-wind direction; (0,0) if '?'."""
    return W._VECTEURS_DIR.get(direction, (0.0, 0.0))


# ════════════════════════════════════════════════════════════════════════════
#  BUILD subcommand — generation of geo.json (containment + adjacency + anchor)
# ════════════════════════════════════════════════════════════════════════════
#
# Generates the complete spatial graph for a campaign:
#   1) CONTAINMENT — one node per location from §2.2 (+ root regions), parent fixed;
#   2) ADJACENCY  — edges from regles.temps.deplacements (duration → temps_ut via
#      minutes_vers_ut(parser_duree_minutes), direction extracted from descriptions),
#      reciprocal edge (return direction, opposite direction) added if absent;
#   3) ANCHOR    — SMACOF MDS (worldlib) on the duration matrix; locations not
#      covered by the matrix (sealed without route, sub-locations, regions) are anchored
#      by deterministic FALLBACK (near a known neighbor / barycenter).

def _routes_depuis_monde(monde: dict) -> list[dict]:
    """Extracts all routes (id_a, id_b, minutes, direction, voie) from
    regles.temps.deplacements.

    Iterates over `depuis_<src>_vers` (dict), `entre` (dict of keys `<a>_vers_<b>`), and
    simple top-level keys `<a>_vers_<b>` (strings). Labels are resolved
    to ids via the index built from world.json (`W.index_labels`) — no hardcoded names —
    and duration by the worldlib parser, to stay consistent with MDS.
    """
    dep = (monde.get("rules", {}) or {}).get("time", {}).get("movements", {})
    routes: list[dict] = []
    if not isinstance(dep, dict):
        return routes

    idx_labels = W.index_labels(monde)

    def ajouter(label_a, label_b, desc):
        ida = W._label_vers_id(label_a, idx_labels)
        idb = W._label_vers_id(label_b, idx_labels)
        if not (isinstance(desc, str) and ida and idb):
            return
        mn = W.parser_duree_minutes(desc)
        if mn <= 0:
            return
        routes.append({
            "a": ida, "b": idb, "minutes": mn,
            "dir": _direction_depuis_description(desc),
            "voie": _voie_depuis_description(desc),
        })

    for section_key, section_val in dep.items():
        if section_key == "gouvernance":
            continue
        if isinstance(section_val, str):
            if "_vers_" in section_key:
                gauche, droite = section_key.split("_vers_", 1)
                ajouter(gauche, droite, section_val)
            continue
        if not isinstance(section_val, dict):
            continue
        if section_key.startswith("depuis_") and section_key.endswith("_vers"):
            src_label = section_key[len("depuis_"):-len("_vers")]
            for dest_key, desc in section_val.items():
                ajouter(src_label, dest_key, desc)
        elif section_key == "entre":
            for cle, desc in section_val.items():
                if "_vers_" in cle:
                    gauche, droite = cle.split("_vers_", 1)
                    ajouter(gauche, droite, desc)
    return routes


def _collecter_lieux(monde: dict) -> list[dict]:
    """Builds the list of location NODES (without edges or anchor) from world.json.

    Entirely GENERIC: no hardcoded campaign name/id.
      * Regions: for each `reg` in `universe.regions`, id = `reg["id"]` (otherwise
        forged `"region:" + slug(nom)`), parent None, type "region", description =
        `description`|`ambiance`.
      * Locations: for each `fiche` in `reg["locations"]`, id = `fiche["id"]` (otherwise
        forged `"lieu:<region-slug>/<slug(nom)>"`), parent DERIVED from id via
        `_parent_depuis_id` (a sub-location encodes its parent in its id), type via
        `_type_geo`, description compacted.
    """
    noeuds: dict[str, dict] = {}
    regions = (monde.get("universe", {}) or {}).get("regions", []) or []

    # Root regions (parent null, aretes []). We store the order + region slug
    # to forge ids for locations without ids and keep a deterministic order.
    region_ids: list[str] = []
    region_slug: dict[int, str] = {}   # region index → root slug for locations
    for i, reg in enumerate(regions):
        if not isinstance(reg, dict):
            continue
        rnom = reg.get("name", "") or ""
        rid = reg.get("id")
        if not (isinstance(rid, str) and rid):
            rid = "region:" + W.slug(rnom)
        if not rid or rid == "region:":
            continue
        region_slug[i] = rid.split(":", 1)[1] if ":" in rid else W.slug(rnom)
        desc = reg.get("description") or reg.get("ambiance") or ""
        noeuds[rid] = {
            "id": rid,
            "name": rnom,
            "parent": None,
            "type": "region",
            "altitude": None,
            "ancrage": {"x": 0, "y": 0},
            "aretes": [],
            "description_narrative": _compacter(desc, 180) if isinstance(desc, str) else "",
        }
        region_ids.append(rid)

    # Locations from records.
    for i, reg in enumerate(regions):
        if not isinstance(reg, dict):
            continue
        rslug = region_slug.get(i, "")
        for fiche in reg.get("locations", []) or []:
            if not isinstance(fiche, dict):
                continue
            nom = fiche.get("name", "") or ""
            lid = fiche.get("id")
            if not (isinstance(lid, str) and lid):
                # Location without id: we FORGE an id under the region (slug) to not
                # lose information nor break the hierarchy (genericity).
                base = W.slug(nom)
                if not base:
                    continue
                lid = "lieu:" + (f"{rslug}/{base}" if rslug else base)
                _log(f"ℹ Location without id mapped by slug: « {nom} » → {lid}")
            parent = _parent_depuis_id(lid)
            desc = fiche.get("description", "") or ""
            noeuds[lid] = {
                "id": lid,
                "name": nom,
                "parent": parent,
                "type": _type_geo(fiche.get("type")),
                "altitude": None,
                "ancrage": {"x": 0, "y": 0},   # filled by MDS anchor below
                "aretes": [],
                "description_narrative": _compacter(desc, 180),
            }

    # Deterministic order: regions (world.json order) first, then locations sorted
    # by id.
    region_set = set(region_ids)
    autres = sorted(nid for nid in noeuds if nid not in region_set)
    return [noeuds[r] for r in region_ids] + [noeuds[a] for a in autres]


def _compacter(texte: str, n: int) -> str:
    """Reduces a text to a single line truncated to n characters (soft truncation)."""
    if not isinstance(texte, str):
        return ""
    t = re.sub(r"\s+", " ", texte).strip()
    if len(t) > n:
        t = t[: n - 1].rstrip() + "…"
    return t


def _injecter_aretes(noeuds: list[dict], routes: list[dict]) -> None:
    """Adds edges from routes to nodes (in place).

    For each route a→b (duration → temps_ut, direction, voie), we place edge a→b
    and, if missing, the reciprocal edge b→a (opposite direction, same temps_ut).
    More costly parallel edges do not replace a less costly one.
    """
    idx = {n["id"]: n for n in noeuds}

    def poser(src: str, dst: str, temps_ut: int, direction: str,
              distance_m, voie):
        noeud = idx.get(src)
        if noeud is None or dst not in idx:
            return
        aretes = noeud.setdefault("aretes", [])
        # Existing edge to dst? Keep the least costly.
        for ar in aretes:
            if ar.get("vers") == dst:
                if temps_ut < ar.get("temps_ut", math.inf):
                    ar["temps_ut"] = temps_ut
                    ar["dir"] = direction
                    if voie:
                        ar["voie"] = voie
                return
        arete = {
            "vers": dst,
            "dir": direction if direction in W.DIRECTIONS else "?",
            "distance_m": distance_m,
            "temps_ut": temps_ut,
        }
        if voie:
            arete["voie"] = voie
        aretes.append(arete)

    for r in routes:
        temps_ut = W.minutes_vers_ut(r["minutes"])
        if temps_ut < 1:
            temps_ut = 1
        poser(r["a"], r["b"], temps_ut, r["dir"], None, r.get("voie"))
        # Reciprocal (return direction): opposite direction, same cost ("outbound = return").
        poser(r["b"], r["a"], temps_ut, _OPPOSE_DIR.get(r["dir"], "?"), None, None)

    # Deterministic sort of edges by (temps_ut, vers).
    for n in noeuds:
        n["aretes"].sort(key=lambda a: (a.get("temps_ut", 0), a.get("vers", "")))


def _ancrer_tous(noeuds: list[dict], routes: list[dict]) -> float:
    """Computes the (x,y) anchor of ALL nodes (in place). Returns MDS stress.

    1) SMACOF MDS (worldlib) on the duration matrix derived from routes → anchors
       covered locations;
    2) Deterministic FALLBACK for uncovered locations (sealed without route, sub-locations,
       regions): placed at a small offset from a known adjacent neighbor, otherwise at
       the barycenter of anchored nodes. Root regions remain at (0,0).
    """
    idx = {n["id"]: n for n in noeuds}

    # 1) Duration matrix (in UT) from extracted routes.
    paires_ut = []
    for r in routes:
        ut = W.minutes_vers_ut(r["minutes"])
        paires_ut.append((r["a"], r["b"], max(ut, 1)))
    ids_mds = sorted({a for a, _, _ in paires_ut} | {b for _, b, _ in paires_ut})

    coords: dict[str, dict] = {}
    stress = 0.0
    if ids_mds:
        # Builds a minimal graph and reuses worldlib.matrice_durees(geo) to
        # benefit from the Floyd-Warshall completion + proven symmetrization.
        geo_min = {"locations": [
            {"id": nid, "parent": None, "ancrage": {"x": 0, "y": 0}, "aretes": []}
            for nid in ids_mds
        ]}
        gmin_idx = {n["id"]: n for n in geo_min["locations"]}
        for a, b, ut in paires_ut:
            gmin_idx[a]["aretes"].append(
                {"vers": b, "dir": "?", "distance_m": None, "temps_ut": ut})
        ids_ord, D = W.matrice_durees(geo_min)
        coords = W.ancrer_mds(ids_ord, D, iterations=300, seed=42)
        stress = W.stress_normalise(ids_ord, D, coords)

    # Apply MDS coords.
    for nid, xy in coords.items():
        if nid in idx:
            idx[nid]["ancrage"] = {"x": int(xy["x"]), "y": int(xy["y"])}

    # 2) Fallback for unanchored locations (excluding root regions).
    ancres = set(coords.keys())
    bary = _barycentre([idx[a]["ancrage"] for a in ancres if a in idx]) if ancres else (0, 0)

    # Repeat a few passes: a sub-location can anchor on a neighbor itself
    # anchored in the previous pass (deterministic, bounded propagation).
    for _ in range(6):
        change = False
        for n in noeuds:
            nid = n["id"]
            if nid in ancres or n.get("type") == "region":
                continue
            # a) Already-anchored adjacent neighbor → place at a small offset in the
            #    edge direction.
            ancre_voisin = _ancre_depuis_voisin(n, idx, ancres)
            if ancre_voisin is not None:
                n["ancrage"] = ancre_voisin
                ancres.add(nid)
                change = True
                continue
            # b) Anchored parent (sub-location of type room/niche) → slight deterministic offset.
            parent = n.get("parent")
            if isinstance(parent, str) and parent in ancres:
                pa = idx[parent]["ancrage"]
                d = (hash(nid) % 7) - 3
                n["ancrage"] = {"x": int(pa["x"]) + d, "y": int(pa["y"]) - d}
                ancres.add(nid)
                change = True
        if not change:
            break

    # c) Everything still unanchored → barycenter (with micro-offset per id to
    #    avoid exact overlap).
    for n in noeuds:
        nid = n["id"]
        if nid in ancres or n.get("type") == "region":
            continue
        d = (hash(nid) % 11) - 5
        n["ancrage"] = {"x": int(bary[0]) + d, "y": int(bary[1]) + d}
        ancres.add(nid)

    return stress


def _ancre_depuis_voisin(noeud: dict, idx: dict, ancres: set) -> dict | None:
    """Places a node at an offset from an already-anchored adjacent neighbor.

    Looks for an edge (from the node OR toward the node) connecting an anchored neighbor,
    and places the node `temps_ut` units in the edge direction (or a small default). None
    if no anchored neighbor.
    """
    nid = noeud["id"]
    # Outgoing edges from the node.
    for ar in noeud.get("aretes", []):
        v = ar.get("vers")
        if v in ancres and v in idx:
            base = idx[v]["ancrage"]
            ux, uy = _vecteur_dir(_OPPOSE_DIR.get(ar.get("dir", "?"), "?"))
            d = float(ar.get("temps_ut", 6) or 6)
            return {"x": int(round(base["x"] + ux * d)),
                    "y": int(round(base["y"] + uy * d))}
    # Incoming edges (an anchored neighbor points toward us).
    for autre_id, autre in idx.items():
        if autre_id not in ancres:
            continue
        for ar in autre.get("aretes", []):
            if ar.get("vers") == nid:
                base = idx[autre_id]["ancrage"]
                ux, uy = _vecteur_dir(ar.get("dir", "?"))
                d = float(ar.get("temps_ut", 6) or 6)
                return {"x": int(round(base["x"] + ux * d)),
                        "y": int(round(base["y"] + uy * d))}
    return None


def _barycentre(ancrages: list[dict]) -> tuple[int, int]:
    """Integer barycenter of a list of anchors {x,y}; (0,0) if empty."""
    pts = [(a.get("x", 0), a.get("y", 0)) for a in ancrages if isinstance(a, dict)]
    if not pts:
        return (0, 0)
    sx = sum(p[0] for p in pts) / len(pts)
    sy = sum(p[1] for p in pts) / len(pts)
    return (int(round(sx)), int(round(sy)))


def construire_geo(campagne: Path) -> dict:
    """Builds the complete geo object (dict) for a campaign (without writing it).

    Reads world.json (READ-ONLY). Returns {'meta':…, 'locations':[…]}. Deterministic.
    """
    monde = W.charger_json(Path(campagne) / "world.json", {}) or {}
    nom_campagne = (monde.get("meta", {}) or {}).get("name") \
        or (monde.get("meta", {}) or {}).get("titre") \
        or Path(campagne).name

    noeuds = _collecter_lieux(monde)
    routes = _routes_depuis_monde(monde)
    _injecter_aretes(noeuds, routes)
    stress = _ancrer_tous(noeuds, routes)

    geo = {
        "meta": {
            "campagne": nom_campagne,
            "version": GEO_VERSION,
            "genere_par": "geo_query.py build",
            "date": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "echelle": "1 unite d'ancrage ~ 1 UT de marche (non metrique, usage code uniquement)",
            "mds_stress_normalise": round(stress, 4),
        },
        "locations": noeuds,
    }
    return geo


def build(campagne: Path, apply: bool = False, force: bool = False) -> dict:
    """Generates geo.json (containment + adjacency + MDS anchor).

    --apply writes geo.json (atomic); default = dry-run (writes nothing) and returns
    the stress. Refuses to overwrite an existing geo.json without --force.
    Returns {'ecrit':bool, 'chemin':str, 'nb_lieux':int, 'nb_aretes':int,
    'stress':float, 'violations':[…], 'geo':<object>}.
    """
    campagne = Path(campagne)
    geo = construire_geo(campagne)
    nb_lieux = len(geo["locations"])
    nb_aretes = sum(len(n.get("aretes", [])) for n in geo["locations"])
    stress = geo["meta"]["mds_stress_normalise"]

    # Structural validation (graph invariants) before any write.
    violations = _valider_objet_geo(geo)["erreurs"]

    cible = campagne / "geo.json"
    ecrit = False
    if apply:
        if cible.exists() and not force:
            _log(f"⚠ {cible} already exists — use --force to overwrite. "
                 f"No write.")
        elif violations:
            _log(f"❌ {len(violations)} violation(s) — write refused:")
            for v in violations:
                _log(f"   - {v}")
        else:
            W.sauver_json_atomique(cible, geo)
            ecrit = True

    return {
        "ecrit": ecrit,
        "chemin": str(cible),
        "nb_lieux": nb_lieux,
        "nb_aretes": nb_aretes,
        "stress": stress,
        "violations": violations,
        "geo": geo,
    }


# ════════════════════════════════════════════════════════════════════════════
#  4.1  Importable functions — spatial queries (fixed signatures)
# ════════════════════════════════════════════════════════════════════════════

def _resoudre_t(campagne: Path, T: int | None) -> int:
    """Effective T: the provided value or worldlib.t_courant (fail-open)."""
    if T is not None:
        return int(T)
    try:
        return W.t_courant(campagne)
    except Exception as e:                 # fail-open: never crash a query
        _log(f"ℹ t_courant unavailable ({e}) — T=0 by default.")
        return 0


def _trajectoire_entite(campagne: Path, geo: dict, acteurs: dict,
                        entite_id: str) -> list[dict] | None:
    """Trajectory of an entity: actor (its trajectory) OR location (static stay).

    None if the entity is unknown (neither actor nor location).
    """
    idx_act = W.index_acteurs(acteurs)
    if entite_id in idx_act:
        return W.trajectoire_de(idx_act[entite_id])
    if entite_id in W.index_lieux(geo):
        # A location is "immobile": permanent stay at itself.
        return [{"lieu": entite_id, "de": 0, "a": None}]
    return None


def ou_est(campagne: Path, entite_id: str, T: int | None = None) -> dict:
    """« Where is X at T? ».

    Returns {'entite':id, 'lieu':'<id>', 'x':float, 'y':float,
    'en_mouvement':bool, 'T':int, 'narratif':str}. `entite` can be an actor (via
    its trajectory) OR a location (static position). {} if not found (fail-open).
    """
    campagne = Path(campagne)
    T = _resoudre_t(campagne, T)
    geo = W.charger_geo(campagne)
    acteurs = W.charger_acteurs(campagne)

    traj = _trajectoire_entite(campagne, geo, acteurs, entite_id)
    if traj is None or not traj:
        _log(f"ℹ ou_est: unknown entity « {entite_id} ».")
        return {}

    pos = W.position_a(geo, traj, T)
    if not pos:
        return {}
    return {
        "entite": entite_id,
        "lieu": pos.get("lieu"),
        "x": pos.get("x", 0.0),
        "y": pos.get("y", 0.0),
        "en_mouvement": bool(pos.get("en_mouvement", False)),
        "T": T,
        "narratif": W.t_vers_narratif(T),
    }


def qui_est_a(campagne: Path, lieu_id: str, T: int | None = None,
              rayon: float | None = None) -> list[dict]:
    """« Who is here (or within range) at T? ».

    List of present actors: [{'id','nom','type','lieu','distance'}]. If rayon
    None → EXACT presence at the location (or its contents); otherwise presence within
    the anchor radius around the location. Sorted by ascending distance then id.
    """
    campagne = Path(campagne)
    T = _resoudre_t(campagne, T)
    geo = W.charger_geo(campagne)
    acteurs = W.charger_acteurs(campagne)
    idx_lieux = W.index_lieux(geo)

    if lieu_id not in idx_lieux:
        _log(f"ℹ qui_est_a: unknown location « {lieu_id} ».")
        return []

    ancre_lieu = W._ancrage_xy(idx_lieux.get(lieu_id))
    # Set of locations "counting as here": the location + its recursive contents.
    ici = {lieu_id} | set(W.contenus(geo, lieu_id, recursif=True))

    presents: list[dict] = []
    for aid, acteur in W.index_acteurs(acteurs).items():
        traj = W.trajectoire_de(acteur)
        if not traj:
            continue
        pos = W.position_a(geo, traj, T)
        if not pos:
            continue
        lieu_acteur = pos.get("lieu")

        if rayon is None:
            # Exact presence (location or content).
            if lieu_acteur in ici:
                presents.append(_present(acteur, lieu_acteur, 0.0))
        else:
            # Presence within the anchor radius.
            if ancre_lieu is None:
                continue
            dx = pos.get("x", 0.0) - ancre_lieu[0]
            dy = pos.get("y", 0.0) - ancre_lieu[1]
            dist = math.hypot(dx, dy)
            if dist <= float(rayon):
                presents.append(_present(acteur, lieu_acteur, round(dist, 2)))

    presents.sort(key=lambda p: (p["distance"], p["id"]))
    return presents


def _present(acteur: dict, lieu: str, distance: float) -> dict:
    """Formats an actor presence entry."""
    return {
        "id": acteur.get("id"),
        "name": acteur.get("name", acteur.get("id")),
        "type": acteur.get("type", "npcs"),
        "lieu": lieu,
        "distance": distance,
    }


def voisins(campagne: Path, lieu_id: str) -> dict:
    """« What is around? ».

    {'lieu':id, 'aretes':[{vers,dir,distance_m,temps_ut,voie}],
    'contenus':[id…], 'parent':id|None}. Deterministic, zero hallucination. {} if
    location unknown.
    """
    campagne = Path(campagne)
    geo = W.charger_geo(campagne)
    idx = W.index_lieux(geo)
    noeud = idx.get(lieu_id)
    if noeud is None:
        _log(f"ℹ voisins: unknown location « {lieu_id} ».")
        return {}
    parent = noeud.get("parent")
    return {
        "lieu": lieu_id,
        "aretes": W.aretes_sortantes(geo, lieu_id),
        "contenus": W.contenus(geo, lieu_id, recursif=False),
        "parent": parent if isinstance(parent, str) else None,
    }


def chemin(campagne: Path, a: str, b: str) -> dict:
    """« How to get from A to B, in how much time? ».

    = enriched worldlib.plus_court_chemin: {'chemin':[id…], 'aretes':[…],
    'temps_ut':int, 'distance_m':int, 'duree_narrative':str}. temps_ut=-1 if no
    path ('duree_narrative' is then '—').
    """
    campagne = Path(campagne)
    geo = W.charger_geo(campagne)
    res = W.plus_court_chemin(geo, a, b)
    temps_ut = res.get("temps_ut", -1)
    res["duree_narrative"] = _duree_narrative(temps_ut) if temps_ut >= 0 else "—"
    return res


def distance(campagne: Path, a: str, b: str, vol_oiseau: bool = False) -> dict:
    """{'a','b','temps_ut','distance_m','vol_oiseau'}.

    temps_ut/distance_m come from the shortest path (graph). vol_oiseau =
    Euclidean anchor distance (useful for proximity sorting). If vol_oiseau
    is requested but anchor is missing, the field is -1.0.
    """
    campagne = Path(campagne)
    geo = W.charger_geo(campagne)
    pc = W.plus_court_chemin(geo, a, b)
    vo = W.distance_vol_oiseau(geo, a, b)
    return {
        "a": a,
        "b": b,
        "temps_ut": pc.get("temps_ut", -1),
        "distance_m": pc.get("distance_m", 0),
        "vol_oiseau": vo,
    }


def dans_rayon(campagne: Path, point_id: str, rayon: float,
               T: int | None = None) -> dict:
    """Spatial filtering around a point (anchor), at T.

    {'locations':[{'id','distance'}], 'actors':[{'id','distance'}]} within the anchor
    radius around point_id. The point itself is not listed in 'locations'.
    Sorted by ascending distance.
    """
    campagne = Path(campagne)
    T = _resoudre_t(campagne, T)
    rayon = float(rayon)
    geo = W.charger_geo(campagne)
    acteurs = W.charger_acteurs(campagne)
    idx = W.index_lieux(geo)

    centre = W._ancrage_xy(idx.get(point_id))
    if centre is None:
        _log(f"ℹ dans_rayon: unknown point or missing anchor « {point_id} ».")
        return {"locations": [], "actors": []}

    lieux_dans: list[dict] = []
    for lid, noeud in idx.items():
        if lid == point_id:
            continue
        p = W._ancrage_xy(noeud)
        if p is None:
            continue
        d = math.hypot(p[0] - centre[0], p[1] - centre[1])
        if d <= rayon:
            lieux_dans.append({"id": lid, "distance": round(d, 2)})

    acteurs_dans: list[dict] = []
    for aid, acteur in W.index_acteurs(acteurs).items():
        traj = W.trajectoire_de(acteur)
        if not traj:
            continue
        pos = W.position_a(geo, traj, T)
        if not pos:
            continue
        d = math.hypot(pos.get("x", 0.0) - centre[0], pos.get("y", 0.0) - centre[1])
        if d <= rayon:
            acteurs_dans.append({"id": aid, "distance": round(d, 2)})

    lieux_dans.sort(key=lambda x: (x["distance"], x["id"]))
    acteurs_dans.sort(key=lambda x: (x["distance"], x["id"]))
    return {"locations": lieux_dans, "actors": acteurs_dans}


def croisement(campagne: Path, traj_a: list[dict], traj_b: list[dict],
               seuil: float, pas_ut: int = 6) -> list[dict]:
    """Intersection of two trajectories (the "does it cross the raid?" computation).

    Samples T by `pas_ut` steps (default 1 h) over the COMMON INTERVAL of the two
    trajectories; at each T, computes the anchor distance between the two
    positions; returns WINDOWS (runs of contiguous T) where distance <= seuil,
    one entry per window (at the T of minimum distance in the window):
      [{'T':int, 'lieu':'<id approx>', 'distance':float, 'narratif':str}].
    Empty list if never in range (or trajectories with no common interval).
    """
    campagne = Path(campagne)
    geo = W.charger_geo(campagne)
    seuil = float(seuil)
    pas = max(1, int(pas_ut))

    if not traj_a or not traj_b:
        return []

    bornes_a = _bornes_trajectoire(traj_a)
    bornes_b = _bornes_trajectoire(traj_b)
    if bornes_a is None or bornes_b is None:
        return []
    t_de = max(bornes_a[0], bornes_b[0])
    t_a = min(bornes_a[1], bornes_b[1])
    if t_de > t_a:
        return []   # no temporal overlap

    fenetres: list[dict] = []
    courante: dict | None = None   # current window (min distance)

    T = t_de
    while T <= t_a:
        pa = W.position_a(geo, traj_a, T)
        pb = W.position_a(geo, traj_b, T)
        if pa and pb:
            d = math.hypot(pa.get("x", 0.0) - pb.get("x", 0.0),
                           pa.get("y", 0.0) - pb.get("y", 0.0))
            if d <= seuil:
                if courante is None:
                    courante = {"T": T, "distance": d, "lieu": pa.get("lieu")}
                elif d < courante["distance"]:
                    courante.update({"T": T, "distance": d, "lieu": pa.get("lieu")})
            else:
                if courante is not None:
                    fenetres.append(_fenetre_croisement(courante))
                    courante = None
        T += pas

    if courante is not None:
        fenetres.append(_fenetre_croisement(courante))
    return fenetres


def _fenetre_croisement(c: dict) -> dict:
    """Formats a crossing window (at the T of minimum distance)."""
    return {
        "T": c["T"],
        "lieu": c.get("lieu"),
        "distance": round(c["distance"], 2),
        "narratif": W.t_vers_narratif(c["T"]),
    }


def _bornes_trajectoire(traj: list[dict]) -> tuple[int, int] | None:
    """(T_min, T_max) covered by a trajectory. Effective T_max if last 'a' is
    null = bounded to the largest 'de' (the position remains constant beyond that, so
    sampling does not need to go further for the proximity test…
    EXCEPT if the other trajectory continues: then extended via the caller).

    Returns (min of 'de', max of known bounds); if the last segment has
    'a':null, we take its 'de' as upper bound (the entity stays there).
    None if trajectory is empty.
    """
    if not traj:
        return None
    des = []
    fins = []
    for seg in traj:
        if not isinstance(seg, dict):
            continue
        des.append(int(seg.get("de", 0)))
        a = seg.get("a", None)
        if a is not None:
            fins.append(int(a))
    if not des:
        return None
    t_min = min(des)
    # Upper bound: the largest known end, or the largest 'de' (open stay).
    t_max = max(fins) if fins else max(des)
    t_max = max(t_max, max(des))
    return (t_min, t_max)


# ════════════════════════════════════════════════════════════════════════════
#  Declarations (the LLM does not provide coordinates) — creer_lieu / deplacer
# ════════════════════════════════════════════════════════════════════════════

def creer_lieu(campagne: Path, nom: str, depuis: str, dir: str,
               distance_m: int, *, type_lieu: str = "lieu",
               parent: str | None = None, apply: bool = False) -> dict:
    """RELATIVE DECLARATION of a new location (the LLM does not provide (x,y)).

    The code: computes anchor = anchor(depuis) + vector(dir, distance_m→scale),
    forges the id (slug, under `parent` or the region of `depuis`), creates the
    reciprocal edge depuis<->id (temps_ut = minutes_vers_ut of a walking duration estimate),
    VALIDATES (invariants §5), and if apply → writes geo.json (atomic).
    Returns {'id', 'noeud', 'violations':[…], 'ecrit':bool}.
    `dir` ∈ {N,NE,E,SE,S,SO,O,NO}. Refuses (violations non-empty) if attachment KO.
    """
    campagne = Path(campagne)
    geo = W.charger_geo(campagne)
    idx = W.index_lieux(geo)

    violations: list[str] = []

    # Input validation.
    direction = str(dir).upper().strip()
    if direction not in W.DIRECTIONS:
        violations.append(
            f"direction « {dir} » invalid (expected ∈ {', '.join(W.DIRECTIONS)}).")
    if depuis not in idx:
        violations.append(f"unknown departure location « {depuis} » (reference).")
    try:
        dm = int(distance_m)
    except (TypeError, ValueError):
        dm = -1
    if dm <= 0:
        violations.append(f"distance_m invalid « {distance_m} » (must be > 0).")

    type_geo = type_lieu if type_lieu in _TYPES_GEO_VALIDES else "lieu"
    if type_lieu not in _TYPES_GEO_VALIDES:
        _log(f"ℹ creer_lieu: non-standard type « {type_lieu} » → 'lieu'.")

    # Without a valid departure we can neither anchor nor attach: stop here.
    if depuis not in idx or direction not in W.DIRECTIONS or dm <= 0:
        return {"id": None, "noeud": None, "violations": violations, "ecrit": False}

    # Parent: explicit, otherwise the root region of the departure location (read from geo).
    if parent is None:
        parent = W.lieu_racine(geo, depuis)
    if parent not in idx:
        violations.append(f"unknown parent « {parent} » (reference).")

    # Forged id: under the parent (kebab), with deterministic slug.
    base_slug = W.slug(nom)
    if not base_slug:
        violations.append(f"name « {nom} » produces no usable slug.")
        return {"id": None, "noeud": None, "violations": violations, "ecrit": False}
    # Hierarchical prefix: derived from parent (region → 'lieu:<region>/slug';
    # location → 'lieu:<parent-path>/slug').
    nouvel_id = _forger_id(parent, base_slug)
    if nouvel_id in idx:
        violations.append(f"id already exists « {nouvel_id} » (collision).")

    # Relative anchor: anchor(depuis) + vector(dir) * scale(distance_m).
    base = W._ancrage_xy(idx.get(depuis)) or (0.0, 0.0)
    ut_estime = _metres_vers_ut(dm)
    ux, uy = _vecteur_dir(direction)
    anc = {"x": int(round(base[0] + ux * ut_estime)),
           "y": int(round(base[1] + uy * ut_estime))}

    # Reciprocal edge depuis <-> nouvel_id.
    arete_aller = {
        "vers": nouvel_id, "dir": direction, "distance_m": dm,
        "temps_ut": ut_estime,
        "voie": f"{nom} (declared from {idx[depuis].get('name') or idx[depuis].get('nom') or depuis})",
    }
    arete_retour = {
        "vers": depuis, "dir": _OPPOSE_DIR.get(direction, "?"),
        "distance_m": dm, "temps_ut": ut_estime,
    }

    noeud = {
        "id": nouvel_id,
        "name": nom,
        "parent": parent,
        "type": type_geo,
        "altitude": None,
        "ancrage": anc,
        "aretes": [arete_retour],
        "description_narrative": "",
    }

    # Builds a candidate geo (copy) to validate invariants BEFORE writing.
    geo_cand = _geo_avec_nouveau_lieu(geo, noeud, depuis, arete_aller)
    rapport = _valider_objet_geo(geo_cand)
    violations.extend(rapport["erreurs"])

    ecrit = False
    if apply:
        if violations:
            _log(f"❌ creer_lieu refused: {len(violations)} violation(s).")
        else:
            W.sauver_json_atomique(campagne / "geo.json", geo_cand)
            ecrit = True

    return {"id": nouvel_id, "noeud": noeud, "violations": violations, "ecrit": ecrit}


def _forger_id(parent: str, base_slug: str) -> str:
    """Forges the hierarchical id of a location under `parent`.

    parent = region 'region:<x>'      → 'lieu:<x>/<slug>'
    parent = location 'lieu:<chemin>' → 'lieu:<chemin>/<slug>'
    Other/unknown                      → 'lieu:<slug>'
    """
    if parent.startswith("region:"):
        racine = parent.split(":", 1)[1]
        return f"lieu:{racine}/{base_slug}"
    if parent.startswith("lieu:"):
        chemin_parent = parent.split(":", 1)[1]
        return f"lieu:{chemin_parent}/{base_slug}"
    return f"lieu:{base_slug}"


def _metres_vers_ut(distance_m: int) -> int:
    """Converts a distance in meters to walking time (UT), deterministic.

    Walking assumption ≈ 4 km/h on Marche terrain (≈ 667 m / 10 min = 1 UT).
    Minimum 1 UT for any distance > 0. (Internal scale, never shown to the LLM.)
    """
    if distance_m <= 0:
        return 1
    ut = int(round(distance_m / 667.0))
    return ut if ut >= 1 else 1


def _geo_avec_nouveau_lieu(geo: dict, noeud: dict, depuis: str,
                           arete_aller: dict) -> dict:
    """Copy of geo with the new node added and the outbound edge placed on `depuis`.

    Does NOT modify the original (queries remain fail-open). Minimal deep copy
    (locations + edges of the only touched node `depuis`).
    """
    lieux = []
    for n in geo.get("locations", []):
        if n.get("id") == depuis:
            copie = dict(n)
            copie["aretes"] = list(n.get("aretes", [])) + [arete_aller]
            lieux.append(copie)
        else:
            lieux.append(n)
    lieux.append(noeud)
    nouveau = dict(geo)
    nouveau["locations"] = lieux
    return nouveau


def deplacer(campagne: Path, entite_id: str, vers: str, depart_t: int,
             *, motif: str = "", apply: bool = False) -> dict:
    """DECLARES an actor movement.

    Builds the edge 'chemin' (plus_court_chemin) from the entity's current position
    (at depart_t) to `vers`, deduces the duration (sum of temps_ut), APPENDs a
    'deplacement' segment then a stay to the actor's trajectory in
    actors.json, VALIDATES (valider_trajectoire + monotonicity vs t_courant), and if apply →
    writes actors.json (atomic).
    Returns {'entite','segments_ajoutes':[…],'arrivee_t':int,'violations':[…],
    'ecrit':bool}.
    """
    campagne = Path(campagne)
    geo = W.charger_geo(campagne)
    acteurs = W.charger_acteurs(campagne)
    idx_act = W.index_acteurs(acteurs)
    idx_lieux = W.index_lieux(geo)

    violations: list[str] = []
    depart_t = int(depart_t)

    if entite_id not in idx_act:
        violations.append(f"unknown actor « {entite_id} » (reference).")
    if vers not in idx_lieux:
        violations.append(f"unknown destination « {vers} » (reference).")

    # Monotonicity vs present: we do not declare a departure in the past.
    t_now = _resoudre_t(campagne, None)
    if depart_t < t_now:
        violations.append(
            f"depart_t ({depart_t}) earlier than the present (T={t_now}) — monotonicity.")

    if violations:
        return {"entite": entite_id, "segments_ajoutes": [], "arrivee_t": depart_t,
                "violations": violations, "ecrit": False}

    acteur = idx_act[entite_id]
    traj = list(W.trajectoire_de(acteur))

    # Entity position at depart_t (departure location of the movement).
    pos = W.position_a(geo, traj, depart_t)
    depart_lieu = pos.get("lieu") if pos else None
    if depart_lieu is None or depart_lieu not in idx_lieux:
        violations.append(
            f"undetermined departure position at T={depart_t} for « {entite_id} ».")
        return {"entite": entite_id, "segments_ajoutes": [], "arrivee_t": depart_t,
                "violations": violations, "ecrit": False}

    # Edge path from departure → destination.
    pc = W.plus_court_chemin(geo, depart_lieu, vers)
    if pc.get("temps_ut", -1) < 0 or not pc.get("chemin"):
        violations.append(
            f"no path from « {depart_lieu} » to « {vers} » (disconnected).")
        return {"entite": entite_id, "segments_ajoutes": [], "arrivee_t": depart_t,
                "violations": violations, "ecrit": False}

    duree = int(pc["temps_ut"])
    arrivee_t = depart_t + duree

    # Trivial case: already at destination.
    if depart_lieu == vers or duree == 0:
        segment_sejour = {"lieu": vers, "de": depart_t, "a": None}
        segments_ajoutes = [segment_sejour]
    else:
        segment_depl = {
            "type": "deplacement", "de": depart_t, "a": arrivee_t,
            "chemin": list(pc["chemin"]), "motif": motif or "",
        }
        segment_sejour = {"lieu": vers, "de": arrivee_t, "a": None}
        segments_ajoutes = [segment_depl, segment_sejour]

    # New trajectory: we TRUNCATE the last open segment (a:null) at depart_t,
    # then append. (Continuity preservation.)
    nouvelle_traj = _tronquer_a(traj, depart_t) + segments_ajoutes

    # Validation of trajectory invariants on the graph.
    viol_traj = W.valider_trajectoire(geo, nouvelle_traj)
    violations.extend(viol_traj)

    ecrit = False
    if not violations and apply:
        # Re-integrates the trajectory into a COPY of actors.json then writes (atomic).
        acteurs_maj = _acteurs_avec_trajectoire(acteurs, entite_id, nouvelle_traj)
        W.sauver_json_atomique(campagne / "actors.json", acteurs_maj)
        ecrit = True
    elif violations and apply:
        _log(f"❌ deplacer refused: {len(violations)} violation(s).")

    return {
        "entite": entite_id,
        "segments_ajoutes": segments_ajoutes,
        "arrivee_t": arrivee_t,
        "violations": violations,
        "ecrit": ecrit,
    }


def _tronquer_a(traj: list[dict], T: int) -> list[dict]:
    """Truncates a trajectory at instant T: keeps all segments starting
    before T, closing the last open segment (a:null or a>T) at T.

    Guarantees continuity before appending a new segment starting at T.
    """
    if not traj:
        return []
    resultat: list[dict] = []
    segs = sorted((s for s in traj if isinstance(s, dict)), key=lambda s: int(s.get("de", 0)))
    for seg in segs:
        de = int(seg.get("de", 0))
        a = seg.get("a", None)
        if de >= T:
            # Segment entirely in the future of T: discard it (replaced by the
            # new movement). Stop (subsequent ones are also discarded).
            break
        copie = dict(seg)
        if a is None or int(a) > T:
            copie["a"] = T
        resultat.append(copie)
    return resultat


def _acteurs_avec_trajectoire(acteurs: dict, entite_id: str,
                              trajectoire: list[dict]) -> dict:
    """Copy of actors.json where the trajectory of `entite_id` is replaced.

    Also updates `localisation_id` (derived display field) on the last
    stay, to remain consistent with any backward-compatible readers.
    """
    out = dict(acteurs)
    nouveaux = []
    dernier_lieu = None
    for seg in reversed(trajectoire):
        if isinstance(seg, dict) and seg.get("lieu"):
            dernier_lieu = seg["lieu"]
            break
    for a in acteurs.get("actors", []) or []:
        if isinstance(a, dict) and a.get("id") == entite_id:
            copie = dict(a)
            copie["trajectory"] = trajectoire
            if dernier_lieu:
                copie["localisation_id"] = dernier_lieu
            nouveaux.append(copie)
        else:
            nouveaux.append(a)
    out["actors"] = nouveaux
    return out


# ════════════════════════════════════════════════════════════════════════════
#  4.3  Graph validator (the 5 invariants from doc 01 §5)
# ════════════════════════════════════════════════════════════════════════════

def _valider_objet_geo(geo: dict) -> dict:
    """Validates a geo OBJECT (already loaded) without touching the disk.

    Implements the structural invariants of the graph (contract §4.3, doc 01 §5):
      (1) Attachment — valid parent + ≥ 1 edge (except root regions);
      (2) Reference  — every edge.vers exists;
      (and types/anchors well-formed).
    Continuity/monotonicity (3,4) concern the trajectories in actors.json (cf.
    valider_trajectoire) and duration governance (5) is delegated to the distance
    validator in valider_geo(campaign). Returns
    {'ok':bool, 'erreurs':[…], 'avertissements':[…]}.
    """
    erreurs: list[str] = []
    avert: list[str] = []

    if not isinstance(geo, dict) or not isinstance(geo.get("locations"), list):
        return {"ok": False, "erreurs": ["geo.json: invalid structure (no 'locations')."],
                "avertissements": []}

    idx = W.index_lieux(geo)
    ids = set(idx.keys())

    racines = 0
    for nid, noeud in idx.items():
        parent = noeud.get("parent")
        aretes = noeud.get("aretes", [])
        est_region = noeud.get("type") == "region" or parent is None

        # (1) Attachment.
        if parent is None:
            racines += 1
        else:
            if not isinstance(parent, str):
                erreurs.append(f"{nid}: badly typed parent.")
            elif parent not in ids:
                erreurs.append(f"{nid}: parent « {parent} » not found (attachment).")
            # ≥ 1 edge except root region.
            if not est_region and (not isinstance(aretes, list) or len(aretes) == 0):
                # Tolerance: a location can be connected by an INCOMING edge only.
                if not _a_une_arete_entrante(idx, nid):
                    avert.append(
                        f"{nid}: no edge (potential island — weak attachment).")

        # (2) Edge reference check.
        if isinstance(aretes, list):
            for ar in aretes:
                if not isinstance(ar, dict):
                    erreurs.append(f"{nid}: malformed edge (not an object).")
                    continue
                v = ar.get("vers")
                if v not in ids:
                    erreurs.append(f"{nid}: edge to « {v} » not found (reference).")
                tu = ar.get("temps_ut")
                if not isinstance(tu, (int, float)) or tu < 1:
                    avert.append(f"{nid}: edge to « {v} » with suspicious temps_ut ({tu}).")

        # Well-formed anchor.
        if W._ancrage_xy(noeud) is None:
            avert.append(f"{nid}: missing or malformed anchor.")

    if racines == 0:
        erreurs.append("No root region (parent null) — graph without containment anchor.")

    return {"ok": not erreurs, "erreurs": erreurs, "avertissements": avert}


def _a_une_arete_entrante(idx: dict, cible: str) -> bool:
    """True if there exists an edge (from another node) pointing to `cible`."""
    for nid, noeud in idx.items():
        if nid == cible:
            continue
        for ar in noeud.get("aretes", []) or []:
            if isinstance(ar, dict) and ar.get("vers") == cible:
                return True
    return False


def valider_geo(campagne: Path) -> dict:
    """Validates complete geo.json (contract §4.3).

    {'ok':bool, 'erreurs':[…], 'avertissements':[…]}. Structural invariants
    (attachment, reference) + duration governance (5) delegated to
    validator-distances.py re-launched as a subprocess on world.json (best-effort:
    its outcome does not invalidate the graph, it is joined as a warning).
    """
    campagne = Path(campagne)
    geo = W.charger_geo(campagne)
    rapport = _valider_objet_geo(geo)

    # (5) Duration governance: re-launches the existing distance validator
    # (best-effort, never fails hard here).
    vd = SCRIPTS_DIR / "validator-distances.py"
    monde = campagne / "world.json"
    if vd.exists() and monde.exists():
        try:
            import subprocess
            proc = subprocess.run(
                [sys.executable, str(vd), str(monde)],
                capture_output=True, text=True, timeout=60,
            )
            if proc.returncode not in (0,):
                rapport["avertissements"].append(
                    "validator-distances.py reports duration governance discrepancies "
                    f"(code {proc.returncode}) — see its report.")
        except Exception as e:                # best-effort, never breaks validation
            rapport["avertissements"].append(
                f"validator-distances.py not re-launched ({e}).")
    return rapport


# ════════════════════════════════════════════════════════════════════════════
#  Rendering helpers (compact text)
# ════════════════════════════════════════════════════════════════════════════

def _duree_narrative(temps_ut: int) -> str:
    """Duration in UT → short narrative label ('40 min', '1 h 30', '~5 h').

    The player never sees UT; this rendering serves text outputs. ≥ 60 min → h
    (and minutes if not round).
    """
    if temps_ut is None or temps_ut < 0:
        return "—"
    minutes = int(temps_ut) * W.MINUTES_PAR_UT
    if minutes < 60:
        return f"{minutes} min"
    h, m = divmod(minutes, 60)
    return f"{h} h" if m == 0 else f"{h} h {m:02d}"


def _charger_trajectoire_arg(campagne: Path, spec: str) -> list[dict] | None:
    """Resolves the --traj-* argument: JSON file, '-' (stdin) or '@<actor-id>'.

    Returns the list of segments, or None on failure (reported on stderr).
    """
    if spec is None:
        return None
    spec = str(spec)
    # @<id> → trajectory of an actor from actors.json.
    if spec.startswith("@"):
        aid = spec[1:]
        acteurs = W.charger_acteurs(campagne)
        idx = W.index_acteurs(acteurs)
        if aid not in idx:
            _log(f"❌ trajectoire: actor « {aid} » not found in actors.json.")
            return None
        return W.trajectoire_de(idx[aid])
    # '-' → stdin.
    if spec == "-":
        try:
            data = json.load(sys.stdin)
        except (json.JSONDecodeError, ValueError) as e:
            _log(f"❌ trajectoire (stdin): unreadable JSON: {e}.")
            return None
    else:
        data = W.charger_json(spec, None)
        if data is None:
            _log(f"❌ trajectoire: file not found or unreadable « {spec} ».")
            return None
    # Accepts either a list of segments or {'trajectory':[…]}.
    if isinstance(data, dict) and isinstance(data.get("trajectory"), list):
        return data["trajectory"]
    if isinstance(data, list):
        return data
    _log("❌ trajectoire: unexpected format (list of segments expected).")
    return None


# ════════════════════════════════════════════════════════════════════════════
#  CLI — argparse with subcommands (first positional = campaign)
# ════════════════════════════════════════════════════════════════════════════

def _exiger_campagne(args) -> Path | None:
    """Resolves and VERIFIES the existence of the campaign directory. None → code 2."""
    camp = W.chemin_campagne(args.campagne)
    if not camp.is_dir():
        _log(f"❌ Campaign not found: {camp}")
        return None
    return camp


def _sortir_json(obj) -> None:
    print(json.dumps(obj, ensure_ascii=False, indent=2))


def cmd_build(args) -> int:
    camp = _exiger_campagne(args)
    if camp is None:
        return 2
    if not (camp / "world.json").exists():
        _log(f"❌ world.json not found in {camp}")
        return 2
    res = build(camp, apply=args.apply, force=args.force)
    if args.as_json:
        out = {k: v for k, v in res.items() if k != "geo"}
        out["mode"] = "apply" if args.apply else "dry-run"
        _sortir_json(out)
    else:
        mode = "APPLY" if args.apply else "dry-run"
        print(f"🗺  build geo.json — {camp.name} — mode {mode}")
        print(f"   {res['nb_lieux']} locations · {res['nb_aretes']} edges · "
              f"MDS stress = {res['stress']}")
        if res["violations"]:
            print(f"   ⚠ {len(res['violations'])} violation(s):")
            for v in res["violations"]:
                print(f"      - {v}")
        if res["ecrit"]:
            print(f"   ✅ written: {res['chemin']}")
        elif args.apply:
            print("   ❌ not written (see messages above).")
        else:
            print(f"   ℹ dry-run: no write (use --apply to write "
                  f"{res['chemin']}).")
    # Code: 2 if blocking violations in apply mode, otherwise 0.
    if res["violations"] and args.apply and not res["ecrit"]:
        return 2
    return 0


def cmd_ou_est(args) -> int:
    camp = _exiger_campagne(args)
    if camp is None:
        return 2
    res = ou_est(camp, args.entite_id, T=args.t)
    if args.as_json:
        _sortir_json(res)
    elif not res:
        print(f"⚠ Entity not found: {args.entite_id}")
    else:
        mvt = " (in motion)" if res["en_mouvement"] else ""
        print(f"📍 {res['entite']} → {res['lieu']}{mvt} — {res['narratif']}")
    return 0 if res else 1


def cmd_qui_est_a(args) -> int:
    camp = _exiger_campagne(args)
    if camp is None:
        return 2
    res = qui_est_a(camp, args.lieu_id, T=args.t, rayon=args.rayon)
    if args.as_json:
        _sortir_json(res)
    elif not res:
        rstr = f" (radius {args.rayon})" if args.rayon is not None else ""
        print(f"ℹ Nobody at {args.lieu_id}{rstr}.")
    else:
        print(f"📍 Present at {args.lieu_id}:")
        for p in res:
            d = f" — at {p['distance']}" if args.rayon is not None and p["distance"] else ""
            print(f"   • {p['id']} ({p['name']}, {p['type']}){d}")
    return 0 if res else 1


def cmd_voisins(args) -> int:
    camp = _exiger_campagne(args)
    if camp is None:
        return 2
    res = voisins(camp, args.lieu_id)
    if args.as_json:
        _sortir_json(res)
    elif not res:
        print(f"⚠ Location not found: {args.lieu_id}")
    else:
        print(f"📍 Around {res['lieu']}"
              + (f"  (in {res['parent']})" if res["parent"] else ""))
        for a in res["aretes"]:
            voie = f" — {a['voie']}" if a.get("voie") else ""
            print(f"   {a.get('dir', '?')} ➜ {a['vers']}  "
                  f"({_duree_narrative(a.get('temps_ut', -1))}){voie}")
        for c in res["contenus"]:
            print(f"   ⊂ contains {c}")
    return 0 if res else 1


def cmd_chemin(args) -> int:
    camp = _exiger_campagne(args)
    if camp is None:
        return 2
    res = chemin(camp, args.a, args.b)
    if args.as_json:
        _sortir_json(res)
    elif res.get("temps_ut", -1) < 0:
        print(f"⚠ No path from {args.a} to {args.b}.")
    else:
        etapes = " ➜ ".join(res["chemin"])
        print(f"➜ {etapes}")
        print(f"⏱ {res['duree_narrative']} ({res['temps_ut']} UT)"
              + (f" · {res['distance_m']} m" if res.get("distance_m") else ""))
    return 0 if res.get("temps_ut", -1) >= 0 else 1


def cmd_distance(args) -> int:
    camp = _exiger_campagne(args)
    if camp is None:
        return 2
    res = distance(camp, args.a, args.b, vol_oiseau=args.vol_d_oiseau)
    if args.as_json:
        _sortir_json(res)
    else:
        if res["temps_ut"] < 0:
            print(f"⚠ {args.a} and {args.b} are not connected by the graph.")
        else:
            print(f"⏱ {args.a} ↔ {args.b} : {_duree_narrative(res['temps_ut'])} "
                  f"({res['temps_ut']} UT)"
                  + (f" · {res['distance_m']} m" if res["distance_m"] else ""))
        if args.vol_d_oiseau:
            vo = res["vol_oiseau"]
            print(f"   as-the-crow-flies (anchor): "
                  + (f"{vo:.1f}" if vo >= 0 else "undetermined"))
    return 0 if res["temps_ut"] >= 0 else 1


def cmd_dans_rayon(args) -> int:
    camp = _exiger_campagne(args)
    if camp is None:
        return 2
    res = dans_rayon(camp, args.point_id, args.rayon, T=args.t)
    if args.as_json:
        _sortir_json(res)
    else:
        print(f"📍 Within radius {args.rayon} around {args.point_id}:")
        if res["locations"]:
            print("   Locations:")
            for l in res["locations"]:
                print(f"      • {l['id']} (≈{l['distance']})")
        if res["actors"]:
            print("   Actors:")
            for a in res["actors"]:
                print(f"      • {a['id']} (≈{a['distance']})")
        if not res["locations"] and not res["actors"]:
            print("   (nothing)")
    return 0 if (res["locations"] or res["actors"]) else 1


def cmd_croisement(args) -> int:
    camp = _exiger_campagne(args)
    if camp is None:
        return 2
    traj_a = _charger_trajectoire_arg(camp, args.traj_a)
    traj_b = _charger_trajectoire_arg(camp, args.traj_b)
    if traj_a is None or traj_b is None:
        return 2
    res = croisement(camp, traj_a, traj_b, seuil=args.seuil, pas_ut=args.pas_ut)
    if args.as_json:
        _sortir_json(res)
    elif not res:
        print(f"ℹ No crossing (threshold {args.seuil}).")
    else:
        print(f"⚠ {len(res)} crossing window(s) (threshold {args.seuil}):")
        for f in res:
            print(f"   • {f['narratif']} — near {f['lieu']} (distance {f['distance']})")
    return 0 if res else 1


def cmd_creer_lieu(args) -> int:
    camp = _exiger_campagne(args)
    if camp is None:
        return 2
    res = creer_lieu(camp, nom=args.nom, depuis=args.depuis, dir=args.dir,
                     distance_m=args.distance_m, type_lieu=args.type,
                     parent=args.parent, apply=args.apply)
    if args.as_json:
        _sortir_json(res)
    else:
        if res["violations"]:
            print(f"⚠ creer-lieu refused: {len(res['violations'])} violation(s):")
            for v in res["violations"]:
                print(f"   - {v}")
        else:
            print(f"📍 New location: {res['id']} (« {args.nom} »)")
            anc = res["noeud"]["ancrage"]
            print(f"   internal anchor computed (code only); attached to "
                  f"{res['noeud']['parent']}")
            if res["ecrit"]:
                print(f"   ✅ written to geo.json")
            elif args.apply:
                print("   ❌ not written (violations).")
            else:
                print("   ℹ dry-run: no write (use --apply).")
    return 0 if not res["violations"] else 1


def cmd_deplacer(args) -> int:
    camp = _exiger_campagne(args)
    if camp is None:
        return 2
    res = deplacer(camp, entite_id=args.entite, vers=args.vers,
                   depart_t=args.depart_t, motif=args.motif, apply=args.apply)
    if args.as_json:
        _sortir_json(res)
    else:
        if res["violations"]:
            print(f"⚠ deplacer refused: {len(res['violations'])} violation(s):")
            for v in res["violations"]:
                print(f"   - {v}")
        else:
            print(f"➜ {res['entite']} → {args.vers}  "
                  f"(arrival {W.t_vers_narratif(res['arrivee_t'])})")
            if res["ecrit"]:
                print("   ✅ trajectory written to actors.json")
            elif args.apply:
                print("   ❌ not written (violations).")
            else:
                print("   ℹ dry-run: no write (use --apply).")
    return 0 if not res["violations"] else 1


def cmd_valider(args) -> int:
    camp = _exiger_campagne(args)
    if camp is None:
        return 2
    res = valider_geo(camp)
    if args.as_json:
        _sortir_json(res)
    else:
        print(f"🔎 Validation of geo.json — {camp.name}")
        if res["erreurs"]:
            print(f"   🔴 {len(res['erreurs'])} error(s):")
            for e in res["erreurs"]:
                print(f"      - {e}")
        if res["avertissements"]:
            print(f"   🟠 {len(res['avertissements'])} warning(s):")
            for a in res["avertissements"]:
                print(f"      - {a}")
        if res["ok"] and not res["avertissements"]:
            print("   ✅ valid graph.")
        elif res["ok"]:
            print("   ✅ valid graph (non-blocking warnings).")
    if res["erreurs"]:
        return 2
    if res["avertissements"]:
        return 1
    return 0


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="geo_query.py",
        description="Deterministic spatial queries for the living world (MJ Tonnerre).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python3 geo_query.py build <campaign> --apply\n"
            "  python3 geo_query.py voisins <campaign> lieu:<region>/<lieu>\n"
            "  python3 geo_query.py chemin <campaign> "
            "lieu:<region>/<lieu-a> lieu:<region>/<lieu-b>\n"
            "  python3 geo_query.py croisement <campaign> "
            "--traj-a @acteur:<id> --traj-b @faction:<id> --seuil 50\n"
        ),
    )
    sub = ap.add_subparsers(dest="commande", required=True)

    def _ajout_json(p):
        p.add_argument("--json", action="store_true", dest="as_json",
                       help="Output in JSON format (raw function object).")

    # build
    p = sub.add_parser("build", help="Generates geo.json (containment + adjacency + MDS anchor).")
    p.add_argument("campagne", help="Path to the campaign directory.")
    p.add_argument("--apply", action="store_true", help="Writes geo.json (atomic).")
    p.add_argument("--force", action="store_true",
                   help="Overwrites an existing geo.json (with --apply).")
    _ajout_json(p)
    p.set_defaults(func=cmd_build)

    # ou-est
    p = sub.add_parser("ou-est", help="Where is an entity (actor or location) at T?")
    p.add_argument("campagne")
    p.add_argument("entite_id")
    p.add_argument("--t", type=int, default=None, help="Instant T (UT). Default: t_courant.")
    _ajout_json(p)
    p.set_defaults(func=cmd_ou_est)

    # qui-est-a
    p = sub.add_parser("qui-est-a", help="Who is at a location (or within a radius) at T?")
    p.add_argument("campagne")
    p.add_argument("lieu_id")
    p.add_argument("--t", type=int, default=None)
    p.add_argument("--rayon", type=float, default=None,
                   help="Anchor radius; without radius → exact presence at the location.")
    _ajout_json(p)
    p.set_defaults(func=cmd_qui_est_a)

    # voisins
    p = sub.add_parser("voisins", help="Edges + contained locations around a location.")
    p.add_argument("campagne")
    p.add_argument("lieu_id")
    _ajout_json(p)
    p.set_defaults(func=cmd_voisins)

    # chemin
    p = sub.add_parser("chemin", help="Shortest path A→B (edges + duration).")
    p.add_argument("campagne")
    p.add_argument("a")
    p.add_argument("b")
    _ajout_json(p)
    p.set_defaults(func=cmd_chemin)

    # distance
    p = sub.add_parser("distance", help="Duration/distance A↔B (graph; +as-the-crow-flies).")
    p.add_argument("campagne")
    p.add_argument("a")
    p.add_argument("b")
    p.add_argument("--vol-d-oiseau", action="store_true", dest="vol_d_oiseau",
                   help="Adds the Euclidean anchor distance.")
    _ajout_json(p)
    p.set_defaults(func=cmd_distance)

    # dans-rayon
    p = sub.add_parser("dans-rayon", help="Locations + actors within a radius around a point.")
    p.add_argument("campagne")
    p.add_argument("point_id")
    p.add_argument("rayon", type=float)
    p.add_argument("--t", type=int, default=None)
    _ajout_json(p)
    p.set_defaults(func=cmd_dans_rayon)

    # croisement
    p = sub.add_parser("croisement", help="Intersection windows of two trajectories.")
    p.add_argument("campagne")
    p.add_argument("--traj-a", dest="traj_a", required=True,
                   help="JSON file | '-' (stdin) | '@<actor-id>'.")
    p.add_argument("--traj-b", dest="traj_b", required=True,
                   help="JSON file | '-' (stdin) | '@<actor-id>'.")
    p.add_argument("--seuil", type=float, required=True,
                   help="Anchor distance below which there is a crossing.")
    p.add_argument("--pas-ut", dest="pas_ut", type=int, default=6,
                   help="Sampling step in UT (default 6 = 1 h).")
    _ajout_json(p)
    p.set_defaults(func=cmd_croisement)

    # creer-lieu
    p = sub.add_parser("creer-lieu", help="Declares a location RELATIVELY (no coordinates).")
    p.add_argument("campagne")
    p.add_argument("--nom", required=True)
    p.add_argument("--depuis", required=True, help="id of the reference location.")
    p.add_argument("--dir", required=True, help="Direction ∈ {N,NE,E,SE,S,SO,O,NO}.")
    p.add_argument("--distance-m", dest="distance_m", type=int, required=True,
                   help="Distance in meters from 'depuis'.")
    p.add_argument("--type", default="lieu", help="Location type (default 'lieu').")
    p.add_argument("--parent", default=None,
                   help="id of the parent (default: region of the departure location).")
    p.add_argument("--apply", action="store_true", help="Writes geo.json (atomic).")
    _ajout_json(p)
    p.set_defaults(func=cmd_creer_lieu)

    # deplacer
    p = sub.add_parser("deplacer", help="Declares an actor movement (builds the path).")
    p.add_argument("campagne")
    p.add_argument("--entite", required=True, help="id of the actor.")
    p.add_argument("--vers", required=True, help="id of the destination location.")
    p.add_argument("--depart-t", dest="depart_t", type=int, required=True,
                   help="Departure instant T (UT).")
    p.add_argument("--motif", default="", help="Narrative reason for the movement.")
    p.add_argument("--apply", action="store_true", help="Writes actors.json (atomic).")
    _ajout_json(p)
    p.set_defaults(func=cmd_deplacer)

    # valider
    p = sub.add_parser("valider", help="Validates geo.json (graph invariants + governance).")
    p.add_argument("campagne")
    _ajout_json(p)
    p.set_defaults(func=cmd_valider)

    return ap


def main(argv=None) -> int:
    ap = build_parser()
    args = ap.parse_args(argv)
    try:
        return args.func(args)
    except BrokenPipeError:
        return 0
    except KeyboardInterrupt:
        _log("Interrupted.")
        return 2


if __name__ == "__main__":
    sys.exit(main())
