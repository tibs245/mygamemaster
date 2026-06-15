#!/usr/bin/env python3
"""
scene_brief.py — Context assembler for the "living world" (MJ Tonnerre).

Purpose (contract §9, doc 05): produce the filtered SCENE BRIEF — the "right window,
at the right moment" — intended for the `pre_llm_call.py` hook. The GM (small model)
does not carry the world: the relevant slice is assembled for it, filtered on THREE AXES:

  * SPATIAL    — where and around what: the current location, its neighbours (directions,
                 durations), its contained locations, and WHO is present at T
                 (geo_query.voisins + qui_est_a + dans_rayon);
  * TEMPORAL   — what is recent and imminent: events from recent days
                 ([T−δ, T]) from events.json (narrative timeline) and
                 evenements_programmes.json (resolved), and especially SCHEDULED events
                 that will "trigger" during the session ([T, T+δ]);
  * RELATIONAL — who has a stake here: relations pointing TOWARD this location or TOWARD ANY
                 of the players (PCs resolved by worldlib.pj_ids; meta.pj_ids /
                 meta.pj_id — a campaign can have MULTIPLE PCs), and actors in
                 motion whose trajectory CROSSES that of the location (crossings).

This module is both:
  * IMPORTABLE — `from scene_brief import scene_brief`;
  * EXECUTABLE — CLI `argparse` (first positional = campaign, second = location),
    messages in French, optional `--json` output.

Cross-cutting conventions (contract §0, §9):
  * source of truth = files; no state outside files;
  * NON-DESTRUCTIVE: READ-ONLY — NEVER writes any file (neither geo.json,
    nor actors.json, nor evenements*.json, nor world.json);
  * STRICT FAIL-OPEN (game loop): any failure (missing/corrupted data,
    geo.json absent, unexpected exception) → MINIMAL BRIEF + code 0. The only non-zero
    code is 2 when the CAMPAIGN itself is not found (usage error);
  * the player NEVER sees the raw T or the coordinates (x, y): everything is rendered in
    NARRATIVE form (t_vers_narratif / durations in plain language). Cf. invariant 01§C.

Targets: Python 3.11, PURE STDLIB (no external dependencies). Imports `worldlib`
and `geo_query` (never the reverse). Cf. contract
`docs/monde-vivant/08-contrat-implementation.md` §9, §13, §14.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from pathlib import Path

import worldlib as W
from i18n import t, resolve_lang

# geo_query is imported best-effort: if (improbably) unavailable, we
# degrade to worldlib directly rather than crashing (strict fail-open).
try:
    import geo_query as G
except Exception as _e:                          # pragma: no cover - garde-fou
    G = None
    print(f"ℹ scene_brief : geo_query unavailable ({_e}) — degraded mode.",
          file=sys.stderr)


# ════════════════════════════════════════════════════════════════════════════
#  Constants (contract §9.1)
# ════════════════════════════════════════════════════════════════════════════

RAYON_DEFAUT = 120.0          # anchor radius for the spatial "PRESENT" filter
FENETRE_UT_DEFAUT = 432       # δ = 3 days: [T−δ, T] (recent) and [T, T+δ] (imminent)
SEUIL_CROISEMENT = 50.0       # anchor distance for a crossing (cf. tick §7.4)
PAS_PROJECTION_UT = 6         # crossing sampling step (1 h)

# PCs are NOT hardcoded here: they are resolved per campaign via
# worldlib.pj_ids(monde) (meta.pj_ids > meta.pj_id > env MGM_PJ_ID > []). A
# campaign can have MULTIPLE PCs. Empty list ⇒ relational filter "toward the
# player" is empty.

# Target width of the text frame (contract §9.2: ~74 columns, soft truncation).
LARGEUR = 74

# Display caps per column (the brief targets "~1 screen": we keep the most
# relevant and signal the rest with "(+N more)"). The complete data
# remains available via --json (uncapped).
MAX_AUTOUR = 8
MAX_PRESENTS = 8
MAX_MOUVEMENT = 4
MAX_RECENT = 4
MAX_IMMINENT = 4
MAX_ENJEUX = 6


def _log(message: str) -> None:
    """Fail-open trace to stderr (never pollutes --json on stdout)."""
    print(message, file=sys.stderr)


# ════════════════════════════════════════════════════════════════════════════
#  Temporal bridge: textual 't' from events.json → T (UT)  [READ ONLY]
# ════════════════════════════════════════════════════════════════════════════
#
# events.json stores TEXTUAL 't' values ("Jour 7, fin d'après-midi") — the
# narrative timeline generated from sessions. We do NOT convert them in place
# (non-destructive). For the RECENT filter, we derive a COMPARABLE T: "Jour N"
# → the UT of the midpoint of the named time slice (or noon by default). This is
# the approximate inverse of worldlib.t_vers_narratif, sufficient to place events
# in the window [T−δ, T].

# Narrative slice → "representative" hour (midpoint of slice). Aligned with
# worldlib._TRANCHES_NARRATIVES (frozen contract §3.3).
_TRANCHE_VERS_HEURE = {
    "nuit": 0,
    "aube": 6,
    "matin": 10,
    "midi": 12,
    "apres-midi": 15,
    "fin d'apres-midi": 18,
    "soir": 20,
}
# Variants/synonyms encountered in real timelines.
_TRANCHE_SYNONYMES = {
    "debut d'apres-midi": 14,
    "debut apres-midi": 14,
    "fin apres-midi": 18,
    "matinee": 10,
    "apres midi": 15,
    "soiree": 20,
    "aurore": 6,
    "midi pile": 12,
    "milieu d'apres-midi": 15,
    "tard": 22,
}


def _norm_txt(texte: str) -> str:
    """Normalises a French text to match time slices (NFKD without accents, lowercase)."""
    s = unicodedata.normalize("NFKD", str(texte))
    s = "".join(c for c in s if not unicodedata.combining(c))
    return s.lower()


def _t_textuel_vers_t(t_texte) -> int | None:
    """«Jour N[, tranche]» → T (UT), or None if no usable «Jour N» is found.

    READ ONLY: used SOLELY to place narrative events within the temporal
    window. Heuristic aligned with t_vers_narratif (approximate inverse).
    A 't' that is ALREADY an integer (improbable case on the events.json side) is
    returned as-is.
    """
    if isinstance(t_texte, bool):
        return None
    if isinstance(t_texte, int):
        return t_texte
    if not isinstance(t_texte, str) or not t_texte.strip():
        return None

    n = _norm_txt(t_texte)
    m = re.search(r"jour\s+(\d+)", n)
    if not m:
        return None
    jour = int(m.group(1))

    # Remainder after "Jour N" → look for a known time slice (longest match
    # first, to capture "fin d'apres-midi" before "apres-midi").
    reste = n[m.end():].lstrip(" ,;-—–").strip()
    heure = 12  # default: noon (consistent with t_courant and echeance_en_t)
    if reste:
        candidats = sorted(
            list(_TRANCHE_VERS_HEURE.items()) + list(_TRANCHE_SYNONYMES.items()),
            key=lambda kv: len(kv[0]), reverse=True,
        )
        for libelle, h in candidats:
            if libelle in reste:
                heure = h
                break
    return W.jour_heure_vers_t(jour, heure, 0)


# ════════════════════════════════════════════════════════════════════════════
#  Sub-functions: fail-open loading of the three sources
# ════════════════════════════════════════════════════════════════════════════

def _charger_evenements_narratifs(campagne: Path) -> list[dict]:
    """List of events from events.json (narrative timeline), [] if absent.

    Each entry is enriched with an internal '_T' field (T derived from the textual 't')
    or None if not datable. DOES NOT MODIFY the file (in-memory copy).
    """
    data = W.charger_json(Path(campagne) / "events.json", {}) or {}
    bruts = data.get("events", []) if isinstance(data, dict) else []
    sortie: list[dict] = []
    for e in bruts or []:
        if not isinstance(e, dict):
            continue
        enrichi = dict(e)
        enrichi["_T"] = _t_textuel_vers_t(e.get("t"))
        sortie.append(enrichi)
    return sortie


def _charger_evenements_programmes(campagne: Path) -> list[dict]:
    """List of events from evenements_programmes.json, [] if absent (fail-open).

    SEPARATE and OPTIONAL file (emitted by causal_propagate / world_tick). Integer T values.
    """
    data = W.charger_json(Path(campagne) / "evenements_programmes.json", {}) or {}
    bruts = data.get("events", []) if isinstance(data, dict) else []
    return [e for e in (bruts or []) if isinstance(e, dict)]


# ════════════════════════════════════════════════════════════════════════════
#  SPATIAL axis — around + contained + present
# ════════════════════════════════════════════════════════════════════════════

def _axe_spatial(campagne: Path, geo: dict, lieu_id: str, T: int,
                 rayon: float) -> dict:
    """Builds AUTOUR (edges), CONTENUS (ids) and PRÉSENTS (actors).

    Delegates to geo_query (voisins / qui_est_a) when available, otherwise to worldlib.
    PRÉSENTS = exact presence at the location (or contained) UNION presence within the anchor
    radius (deduplicated), to capture actors "within range" of a scene.
    """
    # AUTOUR + CONTENUS.
    if G is not None:
        vois = G.voisins(campagne, lieu_id) or {}
    else:                                        # fallback to worldlib directly
        noeud = W.index_lieux(geo).get(lieu_id)
        vois = {
            "lieu": lieu_id,
            "aretes": W.aretes_sortantes(geo, lieu_id),
            "contenus": W.contenus(geo, lieu_id, recursif=False),
            "parent": (noeud.get("parent") if isinstance(noeud, dict) else None),
        } if noeud is not None else {}

    aretes_brutes = vois.get("aretes", []) if isinstance(vois, dict) else []
    autour = []
    for a in aretes_brutes:
        if not isinstance(a, dict):
            continue
        autour.append({
            "vers": a.get("vers"),
            "dir": a.get("dir", "?"),
            "distance_m": a.get("distance_m"),
            "temps_ut": a.get("temps_ut"),
        })
    contenus = list(vois.get("contenus", [])) if isinstance(vois, dict) else []

    # PRÉSENTS: exact (location + contained) ∪ radius.
    presents_map: dict[str, dict] = {}
    if G is not None:
        for p in (G.qui_est_a(campagne, lieu_id, T=T, rayon=None) or []):
            if isinstance(p, dict) and p.get("id"):
                presents_map[p["id"]] = {"id": p["id"], "name": p.get("name", p["id"]),
                                         "type": p.get("type", "npcs")}
        for p in (G.qui_est_a(campagne, lieu_id, T=T, rayon=float(rayon)) or []):
            if isinstance(p, dict) and p.get("id") and p["id"] not in presents_map:
                presents_map[p["id"]] = {"id": p["id"], "name": p.get("name", p["id"]),
                                         "type": p.get("type", "npcs")}

    presents = sorted(presents_map.values(), key=lambda x: x["id"])
    return {"autour": autour, "contenus": contenus, "presents": presents,
            "parent": (vois.get("parent") if isinstance(vois, dict) else None)}


# ════════════════════════════════════════════════════════════════════════════
#  TEMPORAL axis — recent + imminent
# ════════════════════════════════════════════════════════════════════════════

def _axe_temporel(campagne: Path, T: int, fenetre_ut: int) -> dict:
    """Builds RÉCENT ([T−δ, T]) and IMMINENT ([T, T+δ]).

    RECENT   : narrative events (events.json) datable within the past window,
               + SCHEDULED events already 'resolu' within that window.
    IMMINENT : SCHEDULED events (status 'programme', future) that "trigger"
               within [T, T+δ]. Sorted by T. Rendering is NARRATIVE (never the raw T).
    """
    delta = int(fenetre_ut)
    t_bas = T - delta
    t_haut = T + delta

    # --- RECENT (narrative) --------------------------------------------------
    recent: list[dict] = []
    for e in _charger_evenements_narratifs(campagne):
        te = e.get("_T")
        if te is None:
            continue
        if t_bas <= te <= T:
            recent.append({"T": te, "label": _label_evt_narratif(e)})

    # --- RECENT (resolved scheduled events) ---------------------------------
    imminent: list[dict] = []
    for e in _charger_evenements_programmes(campagne):
        te = e.get("T", e.get("t"))
        if not isinstance(te, int) or isinstance(te, bool):
            continue
        statut = e.get("statut", "programme")
        label = _label_evt_programme(e)
        if statut == "resolu" and t_bas <= te <= T:
            recent.append({"T": te, "label": label})
        elif statut == "programme" and T <= te <= t_haut:
            imminent.append({"T": te, "label": label, "type": e.get("type", "?")})

    recent.sort(key=lambda x: x["T"])
    imminent.sort(key=lambda x: x["T"])
    return {"recent": recent, "imminent": imminent}


def _label_evt_narratif(e: dict) -> str:
    """Short label for a narrative event (label, or truncated description)."""
    lab = e.get("label") or e.get("description") or e.get("type") or "(event)"
    return _compacter(str(lab), 64)


def _label_evt_programme(e: dict) -> str:
    """Short label for a scheduled event (label/consequence/type)."""
    lab = (e.get("label") or e.get("consequence_attendue")
           or e.get("type") or "(scheduled event)")
    return _compacter(str(lab), 64)


# ════════════════════════════════════════════════════════════════════════════
#  RELATIONAL axis — stakes + movement (crossings)
# ════════════════════════════════════════════════════════════════════════════

def _axe_relationnel(campagne: Path, geo: dict, acteurs: dict, lieu_id: str,
                     T: int, fenetre_ut: int,
                     pj_ids: set[str] | None = None) -> dict:
    """Builds ENJEUX (relations toward here / toward a PC) and MOUVEMENT (crossings).

    ENJEUX    : relations where 'vers' == lieu_id OR 'vers' == ANY of the PCs
                (`pj_ids`, set resolved by worldlib.pj_ids; empty = no PC
                declared → the "toward the player" section is simply EMPTY, no
                error). Each entry = {actor (source), type, intensite, _vers_pj}.
                Deduplicated, sorted by descending intensity.
    MOUVEMENT : for each actor in motion (trajectory with more than one stay, or
                a 'deplacement' segment) whose position crosses the location within
                [T, T+δ] under SEUIL_CROISEMENT → {actor, T, location, narrative}. ALL
                pj_ids are excluded (a PC is not a "world-movement").
    """
    pj_set = set(pj_ids) if pj_ids else set()

    # --- ENJEUX (stakes) -----------------------------------------------------
    # Relational filter targets: the location, and EACH declared PC (otherwise just the
    # location). We deduplicate ids while keeping the location first (stable order).
    cibles: list[str] = [lieu_id]
    for pid in (pj_ids or []):
        if pid not in cibles:
            cibles.append(pid)
    enjeux: list[dict] = []
    vus: set[tuple] = set()
    for cible in cibles:
        for src_id, rel in W.relations_vers(acteurs, cible):
            cle = (src_id, rel.get("type"), cible)
            if cle in vus:
                continue
            vus.add(cle)
            enjeux.append({
                "actor": src_id,
                "type": rel.get("type", "?"),
                "intensite": _num(rel.get("intensite"), defaut=None),
                "_vers": cible,
                "_vers_pj": cible in pj_set,
            })
    enjeux.sort(key=lambda x: (-(x["intensite"] or 0.0), x["actor"]))

    # --- MOUVEMENT (upcoming crossings with the location) --------------------
    # The location is treated as a point "cone" (permanent stay on itself)
    # over the window [T, T+δ]. We cross each actor IN MOTION against it.
    mouvement: list[dict] = []
    traj_lieu = [{"lieu": lieu_id, "de": T, "a": T + int(fenetre_ut)}]
    for aid, acteur in W.index_acteurs(acteurs).items():
        if aid in pj_set:
            continue                              # no PC is a "world-movement"
        traj = W.trajectoire_de(acteur)
        if not _est_en_mouvement(traj, T, int(fenetre_ut)):
            continue
        fenetres = _croisements(campagne, geo, traj_lieu, traj)
        if not fenetres:
            continue
        f0 = fenetres[0]                          # the 1st crossing (earliest)
        mouvement.append({
            "actor": aid,
            "T": f0.get("T"),
            "lieu": f0.get("lieu") or lieu_id,
            "narratif": f0.get("narratif") or W.t_vers_narratif(f0.get("T", T)),
        })
    mouvement.sort(key=lambda x: (x["T"] if isinstance(x["T"], int) else 0, x["actor"]))
    return {"enjeux": enjeux, "mouvement": mouvement}


def _croisements(campagne: Path, geo: dict, traj_a: list[dict],
                 traj_b: list[dict]) -> list[dict]:
    """Crossings between two trajectories (delegates to geo_query, falls back to worldlib)."""
    if G is not None:
        try:
            return G.croisement(campagne, traj_a, traj_b,
                                 seuil=SEUIL_CROISEMENT, pas_ut=PAS_PROJECTION_UT) or []
        except Exception as e:                    # fail-open
            _log(f"ℹ crossing unavailable ({e}).")
            return []
    # Fallback: minimal direct sampling (without geo_query).
    return _croisements_repli(geo, traj_a, traj_b)


def _croisements_repli(geo: dict, traj_a: list[dict], traj_b: list[dict]) -> list[dict]:
    """Stdlib fallback for crossing (if geo_query is absent): 1 window at closest point."""
    import math
    ba = _bornes(traj_a)
    bb = _bornes(traj_b)
    if not ba or not bb:
        return []
    t_de, t_a = max(ba[0], bb[0]), min(ba[1], bb[1])
    if t_de > t_a:
        return []
    meilleur = None
    T = t_de
    while T <= t_a:
        pa = W.position_a(geo, traj_a, T)
        pb = W.position_a(geo, traj_b, T)
        if pa and pb:
            d = math.hypot(pa.get("x", 0.0) - pb.get("x", 0.0),
                           pa.get("y", 0.0) - pb.get("y", 0.0))
            if d <= SEUIL_CROISEMENT and (meilleur is None or d < meilleur[1]):
                meilleur = (T, d, pa.get("lieu"))
        T += PAS_PROJECTION_UT
    if meilleur is None:
        return []
    return [{"T": meilleur[0], "lieu": meilleur[2], "distance": round(meilleur[1], 2),
             "narratif": W.t_vers_narratif(meilleur[0])}]


def _bornes(traj: list[dict]) -> tuple[int, int] | None:
    """(T_min, T_max) of a trajectory (open stay → bounded by the largest 'de')."""
    if not traj:
        return None
    des, fins = [], []
    for seg in traj:
        if not isinstance(seg, dict):
            continue
        des.append(int(seg.get("de", 0)))
        a = seg.get("a", None)
        if a is not None:
            fins.append(int(a))
    if not des:
        return None
    return (min(des), max(fins) if fins else max(des))


def _est_en_mouvement(traj: list[dict], T: int, fenetre_ut: int) -> bool:
    """True if the trajectory contains an active/upcoming displacement within [T, T+δ],
    or multiple distinct stays (the actor is not fixed at a single location).

    An actor with a single permanent stay ([{lieu, de:0, a:null}]) is NOT "in
    motion": there is no crossing window to project.
    """
    if not traj or len(traj) < 1:
        return False
    t_haut = T + int(fenetre_ut)
    a_deplacement = False
    lieux = set()
    for seg in traj:
        if not isinstance(seg, dict):
            continue
        if seg.get("type") == "deplacement":
            de = int(seg.get("de", 0))
            a = seg.get("a", None)
            a = de if a is None else int(a)
            # Displacement overlapping the window of interest.
            if a >= T and de <= t_haut:
                a_deplacement = True
        elif seg.get("lieu"):
            lieux.add(seg.get("lieu"))
    return a_deplacement or len(lieux) > 1


# ════════════════════════════════════════════════════════════════════════════
#  Main function (frozen signature — contract §9.1)
# ════════════════════════════════════════════════════════════════════════════

def scene_brief(campagne: Path, lieu_id: str, T: int | None = None,
                rayon: float = RAYON_DEFAUT,
                fenetre_ut: int = FENETRE_UT_DEFAUT) -> dict:
    """Builds the filtered SCENE BRIEF (spatial + temporal + relational).

    Default T = worldlib.t_courant. Returns (contract §9.1):
      {'T':int, 'lieu':lieu_id,
       'autour':[{vers,dir,distance_m,temps_ut}],   # geo_query.voisins
       'contenus':[id…],
       'presents':[{id,nom,type}],                  # qui_est_a (location + radius)
       'mouvement':[{acteur,T,lieu,narratif}],      # upcoming crossings
       'recent':[{T,label}],                        # [T−δ, T]
       'imminent':[{T,label,type}],                 # scheduled "triggering" [T, T+δ]
       'enjeux':[{acteur,type,intensite}],          # relations toward here / toward a PC
       'texte':str}                                 # compact rendering (template §9.2)
    δ = fenetre_ut (default 432 UT = 3 days).

    STRICT FAIL-OPEN: any failure → coherent minimal brief (never an exception).
    """
    campagne = Path(campagne)

    # Effective T (fail-open: t_courant never crashes).
    try:
        T_eff = int(T) if T is not None else W.t_courant(campagne)
    except Exception as e:
        _log(f"ℹ scene_brief : t_courant unavailable ({e}) — T=0.")
        T_eff = 0

    # MINIMAL skeleton (returned as-is if everything else fails).
    brief: dict = {
        "T": T_eff,
        "lieu": lieu_id,
        "autour": [],
        "contenus": [],
        "presents": [],
        "mouvement": [],
        "recent": [],
        "imminent": [],
        "enjeux": [],
        "texte": "",
    }

    # Always defined (even if loading fails): safe for text rendering.
    geo: dict = {}
    acteurs: dict = {}

    # Campaign PCs (generic, fail-open): meta.pj_ids > meta.pj_id >
    # env MGM_PJ_ID > []. A campaign can have MULTIPLE PCs. Empty list ⇒ the
    # relational "toward the player" section is simply empty.
    # Active UI language (fail-open → 'en'): env MGM_LANGUAGE > meta.langue > 'en'.
    try:
        _monde = W.charger_json(campagne / "world.json", {}) or {}
        pj_set = set(W.pj_ids(_monde))
        lang = resolve_lang(_monde)
    except Exception as e:
        _log(f"ℹ scene_brief : pj_ids unavailable ({e}) — no PC targeted.")
        pj_set = set()
        lang = resolve_lang(None)

    try:
        geo = W.charger_geo(campagne)
        acteurs = W.charger_acteurs(campagne)

        # Name + description of the location (for the LIEU header).
        noeud = W.index_lieux(geo).get(lieu_id) if isinstance(geo, dict) else None
        brief["_nom_lieu"] = (noeud.get("name") if isinstance(noeud, dict) else None)
        brief["_desc_lieu"] = (noeud.get("description_narrative")
                               if isinstance(noeud, dict) else None)

        # Three axes (each isolated in fail-open).
        try:
            sp = _axe_spatial(campagne, geo, lieu_id, T_eff, rayon)
            brief["autour"] = sp["autour"]
            brief["contenus"] = sp["contenus"]
            brief["presents"] = sp["presents"]
            brief["_parent"] = sp.get("parent")
        except Exception as e:
            _log(f"ℹ scene_brief : spatial axis degraded ({e}).")

        try:
            tp = _axe_temporel(campagne, T_eff, fenetre_ut)
            brief["recent"] = tp["recent"]
            brief["imminent"] = tp["imminent"]
        except Exception as e:
            _log(f"ℹ scene_brief : temporal axis degraded ({e}).")

        try:
            rl = _axe_relationnel(campagne, geo, acteurs, lieu_id, T_eff,
                                  fenetre_ut, pj_ids=pj_set)
            brief["enjeux"] = rl["enjeux"]
            brief["mouvement"] = rl["mouvement"]
        except Exception as e:
            _log(f"ℹ scene_brief : relational axis degraded ({e}).")

    except Exception as e:                        # ultimate safety guard
        _log(f"❌ scene_brief : unexpected failure ({e}) — minimal brief.")

    # Text rendering (always, even minimal).
    try:
        brief["texte"] = _rendre_texte(brief, acteurs, lang)
    except Exception as e:
        _log(f"ℹ scene_brief : text rendering degraded ({e}).")
        brief["texte"] = _rendre_texte_minimal(brief, lang)

    return brief


# ════════════════════════════════════════════════════════════════════════════
#  TEXT rendering — EXACT template for the SCENE BRIEF (contract §9.2)
# ════════════════════════════════════════════════════════════════════════════
#
# Framed block ~1 screen. Header: "T=<int> (<narrative>)". EXACT column labels:
# LIEU AUTOUR PRÉSENTS MOUVEMENT RÉCENT IMMINENT ENJEUX. Durations in
# NARRATIVE form (never the raw T on the player side, never the (x,y)). "⏰" for
# scheduled events. Lines omitted if empty. Target width 74 columns
# (soft truncation; no error on overflow).

# Width of the label column ("LIEU      ", "MOUVEMENT", …). Aligned on the
# longest label ("MOUVEMENT" = 9) + 1 separator space = 10, so that
# content NEVER touches the label (cf. template §9.2).
_ETIQ = 10


def _rendre_texte(brief: dict, acteurs: dict, lang: str | None = None) -> str:
    """Renders the framed block of the SCENE BRIEF (frozen template §9.2).

    All player-facing labels go through the i18n helper `t(..., lang)`; with the
    default/fallback locale (English) the output is byte-identical to before.
    """
    idx_act = W.index_acteurs(acteurs) if isinstance(acteurs, dict) else {}
    T = brief.get("T", 0)
    narr = W.t_vers_narratif(T)

    lignes: list[list[str]] = []   # each entry: [label, content]

    # LIEU (always present).
    nom = brief.get("_nom_lieu")
    desc = brief.get("_desc_lieu")
    lieu_txt = brief.get("lieu") or t("brief.unknown_location", lang)
    if nom:
        suffixe = f" — « {_compacter(desc, 60)} »" if desc else f" — « {nom} »"
        lieu_txt = f"{brief.get('lieu')}{suffixe}"
    lignes.append([t("brief.location", lang), lieu_txt])

    # AUTOUR: "DIR → name (duration) · …" (closest first).
    autour = brief.get("autour", [])
    if autour:
        ordonne = sorted(autour, key=lambda a: _tri_temps(a.get("temps_ut")))
        gardes, reste = _plafonner(ordonne, MAX_AUTOUR)
        morceaux = []
        for a in gardes:
            nom_v = _nom_lieu_court(a.get("vers"), idx_act)
            duree = _duree_narr(a.get("temps_ut"))
            morceaux.append(f"{a.get('dir', '?')} → {nom_v} ({duree})")
        lignes.append([t("brief.around", lang), _joindre(morceaux, " · ", reste, lang)])

    # PRÉSENTS: "id (name) · …".
    presents = brief.get("presents", [])
    if presents:
        gardes, reste = _plafonner(presents, MAX_PRESENTS)
        morceaux = []
        for p in gardes:
            nom_p = p.get("name")
            etiq = p.get("id")
            morceaux.append(f"{etiq} ({nom_p})" if nom_p and nom_p != etiq else f"{etiq}")
        lignes.append([t("brief.present", lang), _joindre(morceaux, " · ", reste, lang)])

    # MOUVEMENT: actors in motion who cross (narrative, never raw T).
    mouvement = brief.get("mouvement", [])
    if mouvement:
        gardes, reste = _plafonner(mouvement, MAX_MOUVEMENT)
        morceaux = []
        for m in gardes:
            nom_m = _nom_acteur_court(m.get("actor"), idx_act)
            lieu_m = _nom_lieu_court(m.get("lieu"), idx_act)
            quand = m.get("narratif") or W.t_vers_narratif(m.get("T", T))
            morceaux.append(f"{nom_m} {t('brief.crosses', lang)} {lieu_m} ({quand})")
        lignes.append([t("brief.movement", lang), _joindre(morceaux, " ; ", reste, lang)])

    # RÉCENT: "JN <label> ; …" (most recent first).
    recent = brief.get("recent", [])
    if recent:
        ordonne = sorted(recent, key=lambda x: x.get("T", 0), reverse=True)
        gardes, reste = _plafonner(ordonne, MAX_RECENT)
        morceaux = [f"{_jour_court(r.get('T'))} {r.get('label')}" for r in gardes]
        lignes.append([t("brief.recent", lang), _joindre(morceaux, " ; ", reste, lang)])

    # IMMINENT: "⏰ <label> JN ; …" (nearest first).
    imminent = brief.get("imminent", [])
    if imminent:
        gardes, reste = _plafonner(imminent, MAX_IMMINENT)
        morceaux = [f"⏰ {i.get('label')} {_jour_court(i.get('T'))}" for i in gardes]
        lignes.append([t("brief.imminent", lang), _joindre(morceaux, " ; ", reste, lang)])

    # ENJEUX: "actor (type .X) [toward the player] ; …".
    enjeux = brief.get("enjeux", [])
    if enjeux:
        gardes, reste = _plafonner(enjeux, MAX_ENJEUX)
        morceaux = []
        for e in gardes:
            nom_e = _nom_acteur_court(e.get("actor"), idx_act)
            typ = e.get("type", "?")
            inten = e.get("intensite")
            inten_txt = f" {_intensite_courte(inten)}" if inten is not None else ""
            cible = t("brief.toward_player", lang) if e.get("_vers_pj") else ""
            morceaux.append(f"{nom_e} ({typ}{inten_txt}){cible}")
        lignes.append([t("brief.stakes", lang), _joindre(morceaux, " ; ", reste, lang)])

    return _encadrer(f"{t('brief.title', lang)} ─ T={T} ({narr})", lignes)


def _rendre_texte_minimal(brief: dict, lang: str | None = None) -> str:
    """Ultra-robust fallback rendering (if _rendre_texte raises): LOCATION only."""
    T = brief.get("T", 0)
    try:
        narr = W.t_vers_narratif(T)
    except Exception:
        narr = "?"
    lignes = [[t("brief.location", lang),
               str(brief.get("lieu") or t("brief.unknown_location", lang))]]
    return _encadrer(f"{t('brief.title', lang)} ─ T={T} ({narr})", lignes)


# ════════════════════════════════════════════════════════════════════════════
#  Formatting helpers (frame, truncation, short labels)
# ════════════════════════════════════════════════════════════════════════════

def _encadrer(titre: str, lignes: list[list[str]]) -> str:
    """Frames a title + lines [label, content] in a Unicode box.

    Content that is too wide is WRAPPED (soft wrap) onto continuation lines
    aligned under the content column. Target width LARGEUR columns.
    """
    interne = LARGEUR - 2                          # space between borders "│…│"
    # Header: "┌─ <title> ──────┐".
    debut = f"┌─ {titre} "
    if len(debut) < LARGEUR - 1:
        debut = debut + "─" * (LARGEUR - 1 - len(debut)) + "┐"
    else:
        debut = debut[:LARGEUR - 1] + "┐"

    out = [debut]
    largeur_contenu = interne - 1 - _ETIQ          # 1 space after the left border

    for etiq, contenu in lignes:
        segments = _wrap(str(contenu), largeur_contenu)
        if not segments:
            segments = [""]
        for k, seg in enumerate(segments):
            label = (etiq if k == 0 else "").ljust(_ETIQ)
            corps = f" {label}{seg}"
            # Pad/truncate to internal width, then add borders.
            corps = _pad_visuel(corps, interne)
            out.append(f"│{corps}│")

    out.append("└" + "─" * interne + "┘")
    return "\n".join(out)


def _wrap(texte: str, largeur: int) -> list[str]:
    """Soft-wraps text into lines <= largeur (cuts at spaces when possible).

    Splits first on "· " and "; " separators to keep readable units,
    then on spaces. A word longer than `largeur` is hard-cut.
    """
    if largeur <= 0:
        return [texte]
    texte = texte.strip()
    if not texte:
        return [""]

    # "Atomic" tokens: we prefer to cut after ' · ' and ' ; '.
    jetons = re.split(r"(\s·\s|\s;\s)", texte)
    # Re-attach separators to the preceding token.
    unites: list[str] = []
    for j in jetons:
        if j in (" · ", " ; ") and unites:
            unites[-1] = unites[-1] + j
        elif j:
            unites.append(j)

    lignes: list[str] = []
    courante = ""
    for u in unites:
        if not courante:
            courante = u
        elif _largeur_visuelle(courante) + _largeur_visuelle(u) <= largeur:
            courante += u
        else:
            lignes.append(_propre_ligne(courante))
            courante = u.lstrip()
        # If a single unit exceeds the width, cut it by words/hard.
        while _largeur_visuelle(courante) > largeur:
            coupe = _couper_a(courante, largeur)
            lignes.append(_propre_ligne(coupe))
            courante = courante[len(coupe):].lstrip()
    if courante:
        lignes.append(_propre_ligne(courante))
    return [l for l in lignes if l] or [""]


def _propre_ligne(texte: str) -> str:
    """Cleans the edges of a wrapped line: removes isolated "· " / "; " separators
    at the head/tail (cut artefacts) and superfluous spaces.
    """
    t = texte.strip()
    # Detach a trailing separator ("word ; " or "word · ") from the content.
    t = re.sub(r"\s*[·;]\s*$", "", t)
    t = re.sub(r"^\s*[·;]\s*", "", t)
    return t.strip()


def _couper_a(texte: str, largeur: int) -> str:
    """Cuts `texte` to <= largeur, preferably at the last space before the limit."""
    if _largeur_visuelle(texte) <= largeur:
        return texte
    # Cut index respecting visual width.
    acc = 0
    dernier_espace = -1
    for i, ch in enumerate(texte):
        acc += _largeur_car(ch)
        if ch == " ":
            dernier_espace = i
        if acc > largeur:
            if dernier_espace > 0:
                return texte[:dernier_espace]
            return texte[:i] if i > 0 else texte[:1]
    return texte


def _pad_visuel(texte: str, largeur: int) -> str:
    """Adjusts `texte` to exactly `largeur` visual columns (pad/truncation)."""
    lv = _largeur_visuelle(texte)
    if lv == largeur:
        return texte
    if lv < largeur:
        return texte + " " * (largeur - lv)
    # Soft truncation with ellipsis when possible.
    return _couper_visuel(texte, largeur)


def _couper_visuel(texte: str, largeur: int) -> str:
    """Truncates to exactly `largeur` visual columns (without overflowing)."""
    if largeur <= 0:
        return ""
    acc = 0
    out = []
    for ch in texte:
        w = _largeur_car(ch)
        if acc + w > largeur:
            break
        out.append(ch)
        acc += w
    # Pad with spaces if a wide character left an empty column.
    res = "".join(out)
    if acc < largeur:
        res += " " * (largeur - acc)
    return res


# Visual width: we treat the "wide" emoji/symbols used here (⏰, ➜…)
# as 1 column (consistent with existing geo_query, which does not double the width).
def _largeur_car(ch: str) -> int:
    """Visual width of a character (combining = 0, rest = 1)."""
    if unicodedata.combining(ch):
        return 0
    return 1


def _largeur_visuelle(texte: str) -> int:
    return sum(_largeur_car(c) for c in texte)


def _plafonner(items: list, maximum: int) -> tuple[list, int]:
    """Keeps at most `maximum` items; returns (kept, nb_remaining)."""
    if maximum is None or maximum < 0 or len(items) <= maximum:
        return list(items), 0
    return list(items[:maximum]), len(items) - maximum


def _joindre(morceaux: list[str], sep: str, reste: int,
             lang: str | None = None) -> str:
    """Joins pieces with `sep` and appends "(+N more)" if `reste` > 0."""
    texte = sep.join(morceaux)
    if reste > 0:
        more = t("brief.more", lang, n=reste)
        texte = f"{texte}{sep}{more}" if texte else more
    return texte


def _tri_temps(temps_ut) -> int:
    """Sort key on temps_ut (non-numeric values last)."""
    if isinstance(temps_ut, bool) or not isinstance(temps_ut, (int, float)):
        return 10 ** 9
    return int(temps_ut)


def _compacter(texte, n: int) -> str:
    """Reduces text to a single line truncated to n characters (soft truncation)."""
    if not isinstance(texte, str):
        return ""
    t = re.sub(r"\s+", " ", texte).strip()
    if len(t) > n:
        t = t[: n - 1].rstrip() + "…"
    return t


def _duree_narr(temps_ut) -> str:
    """Duration in UT → short narrative label (reuses geo_query if available).

    Consistent with geo_query._duree_narrative: '40 min', '1 h 30', '5 h'. '?' if null.
    """
    if G is not None and hasattr(G, "_duree_narrative"):
        try:
            d = G._duree_narrative(temps_ut)
            return d if d != "—" else "?"
        except Exception:
            pass
    if not isinstance(temps_ut, (int, float)) or temps_ut < 0:
        return "?"
    minutes = int(temps_ut) * W.MINUTES_PAR_UT
    if minutes < 60:
        return f"{minutes} min"
    h, m = divmod(minutes, 60)
    return f"{h} h" if m == 0 else f"{h} h {m:02d}"


def _jour_court(T) -> str:
    """T (UT) → compact "JN" (e.g. 'J7'), for the RÉCENT/IMMINENT columns.

    The player sees only a day marker (never the raw UT). '?' if not datable.
    """
    if not isinstance(T, int) or isinstance(T, bool):
        return "?"
    jour, _, _ = W.t_vers_jour_heure(T)
    return f"J{jour}"


def _nom_lieu_court(lieu_id, idx_act: dict) -> str:
    """Human-readable name of a location id: last kebab segment → "words" (without prefix).

    We don't have the geo index here; we derive a label from the id suffix (sufficient
    and deterministic for AUTOUR/MOUVEMENT display).
    """
    if not isinstance(lieu_id, str) or not lieu_id:
        return "?"
    suffixe = lieu_id.rsplit("/", 1)[-1].split(":", 1)[-1]
    return suffixe.replace("-", " ").strip() or lieu_id


def _nom_acteur_court(acteur_id, idx_act: dict) -> str:
    """Name of an actor (from the index) or label derived from the id."""
    if not isinstance(acteur_id, str) or not acteur_id:
        return "?"
    a = idx_act.get(acteur_id)
    if isinstance(a, dict) and a.get("name"):
        return a["name"]
    return acteur_id.split(":", 1)[-1].replace("-", " ").strip() or acteur_id


def _intensite_courte(valeur) -> str:
    """Intensity 0–1 → short label ".4" (doc 05 style: "predation .4")."""
    try:
        v = float(valeur)
    except (TypeError, ValueError):
        return ""
    # ".4" for 0.4; "1" for 1.0; ".85" for 0.85.
    if v >= 1.0:
        return "1"
    txt = f"{v:.2f}".rstrip("0").rstrip(".")
    if txt.startswith("0."):
        txt = txt[1:]                              # "0.4" → ".4"
    return txt


def _num(valeur, defaut=None):
    """Coerces to float if possible, otherwise `defaut`."""
    try:
        if isinstance(valeur, bool):
            return defaut
        return float(valeur)
    except (TypeError, ValueError):
        return defaut


# ════════════════════════════════════════════════════════════════════════════
#  CLI — argparse (first positional = campaign, second = location)
# ════════════════════════════════════════════════════════════════════════════

def _exiger_campagne(arg: str) -> Path | None:
    """Resolves and VERIFIES the existence of the campaign directory. None → code 2."""
    camp = W.chemin_campagne(arg)
    if not camp.is_dir():
        _log(f"❌ Campaign not found: {camp}")
        return None
    return camp


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="scene_brief.py",
        description=("Assembles the filtered SCENE BRIEF (spatial + temporal + "
                     "relational) for the GM (living world)."),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python3 scene_brief.py <campagne> "
            "lieu:<region>/<lieu>\n"
            "  python3 scene_brief.py <campagne> "
            "lieu:<region>/<lieu> --t 1224 --json\n"
        ),
    )
    ap.add_argument("campagne", help="Path to the campaign directory.")
    ap.add_argument("lieu_id", help="id of the scene location (e.g. lieu:<region>/<lieu>).")
    ap.add_argument("--t", type=int, default=None,
                    help="Instant T (UT). Default: t_courant of the campaign.")
    ap.add_argument("--rayon", type=float, default=RAYON_DEFAUT,
                    help=f"Anchor radius for the PRESENT filter (default {RAYON_DEFAUT}).")
    ap.add_argument("--fenetre-ut", dest="fenetre_ut", type=int,
                    default=FENETRE_UT_DEFAUT,
                    help=f"Temporal δ in UT for RECENT/IMMINENT (default "
                         f"{FENETRE_UT_DEFAUT} = 3 days).")
    ap.add_argument("--json", action="store_true", dest="as_json",
                    help="Output in JSON format (the brief object, as-is).")
    return ap


def main(argv=None) -> int:
    """CLI entry point. Code 0 ALWAYS (fail-open), except usage (2) if the
    campaign is not found. Cf. contract §9.3.
    """
    ap = build_parser()
    args = ap.parse_args(argv)

    camp = _exiger_campagne(args.campagne)
    if camp is None:
        return 2

    try:
        brief = scene_brief(camp, args.lieu_id, T=args.t,
                            rayon=args.rayon, fenetre_ut=args.fenetre_ut)
    except Exception as e:                         # ultimate CLI safety guard (fail-open)
        _log(f"❌ scene_brief : unexpected failure ({e}).")
        brief = {"T": 0, "lieu": args.lieu_id, "autour": [], "contenus": [],
                 "presents": [], "mouvement": [], "recent": [], "imminent": [],
                 "enjeux": [], "texte": ""}

    if args.as_json:
        # Purge internal fields (_nom_lieu, _desc_lieu, _parent, _vers…)
        # to output ONLY the contract §9.1 shape.
        sortie = {k: v for k, v in brief.items() if not k.startswith("_")}
        for e in sortie.get("enjeux", []):
            e.pop("_vers", None)
            e.pop("_vers_pj", None)
        print(json.dumps(sortie, ensure_ascii=False, indent=2))
    else:
        print(brief.get("texte", ""))

    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except BrokenPipeError:
        sys.exit(0)
    except KeyboardInterrupt:
        _log("Interrupted.")
        sys.exit(2)
