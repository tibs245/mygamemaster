#!/usr/bin/env python3
"""
causal_propagate.py — BOUNDED causal propagation of the "living world" (MJ Tonnerre).

Goal (contract §8, doc 04): make one event CAUSE others — ELSEWHERE (at a distance,
via the typed relationships of actors) and LATER (with a delay). This is what makes
long-term consistency almost free: we record FUTURE dated events (status "programme")
in a SEPARATE file (`scheduled_events.json`), which the tick engine resolves when
T reaches them. We "find the traces" of a drama we did not witness without having
simulated the detail.

Two graphs coexist: the SPATIAL graph (geo.json) says who is *next to* whom;
the CAUSAL graph (actor relationships, actors.json) says who *depends on* whom. This
propagation traverses the second.

DETERMINISM: *who* is affected, *when* (T = T_cause + delai_ut), *with what
intensity* (× weight × ATTENUATION) — pure graph traversal. The code cannot
"forget" a chain. The NARRATIVE QUALIFICATION (*how* the target reacts:
riot? rationing? call for help?) is left to a DEFERRED LLM SEAM
(`qualifier_narratif`, §LLM below) — done ONLY at resolution and ONLY
if the event becomes observable by the player. NO LLM call is made here.

Safeguards (GUARANTEED termination, contract §8.1 / doc 04 §2):
  * PROFONDEUR_MAX     : the cascade does not go to infinity;
  * SEUIL              : below this significance threshold, the wave dies out;
  * ATTENUATION (< 1)  : each relay weakens the effect → STRICTLY decreasing
                         significance (anti-cycle);
  * BUDGET_PAR_SOURCE  : max number of derived events per root event.

This module is both:
  * IMPORTABLE — `from causal_propagate import propager, regle_de_propagation,
    programmer_evenement, appliquer`;
  * EXECUTABLE — CLI `argparse` with subcommand `propager` (first positional =
    campaign), messages in French, markers (🌊 ➜ ⏱ ⚠ ✅ ℹ), output `--json`.

Cross-cutting conventions (contract §0):
  * source of truth = files; no state outside files;
  * NON-DESTRUCTIVE: NEVER writes to world.json / npcs.json / events.json /
    actors.json / geo.json / hooks / existing scripts. WRITES ONLY
    (atomic append) to scheduled_events.json, and only in --apply mode;
  * exit codes: 0 ok; 1 business condition signalled (wave extinguished immediately
    below SEUIL, no derived events); 2 usage / file not found / broken JSON;
  * propagation NEVER recalculates the past: it only schedules FUTURE events
    (T >= T of the cause).

Targets: Python 3.11, PURE STDLIB (no external dependencies). Imports `worldlib`
(never the reverse); imports NO other script from the contract (parallel development;
scripts call each other as subprocesses if needed). See contract
`docs/monde-vivant/08-contrat-implementation.md` §8, §13, §14.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import worldlib as W


SCRIPTS_DIR = Path(__file__).resolve().parent
PROG_VERSION = 1
SOURCE = "causal_propagate.py"


def _log(message: str) -> None:
    """Trace to stderr (never pollutes --json on stdout)."""
    print(message, file=sys.stderr)


# ════════════════════════════════════════════════════════════════════════════
# 8.1  Bounding constants (FROZEN — contract §8.1)
# ════════════════════════════════════════════════════════════════════════════

PROFONDEUR_MAX = 4        # the cascade does not go to infinity (safeguard 1)
SEUIL = 0.15              # below this significance threshold, the wave dies out (safeguard 2)
ATTENUATION = 0.6        # factor (< 1) applied at each hop (safeguard 3; termination)
BUDGET_PAR_SOURCE = 16   # max number of derived events per root event (safeguard 4)


# ════════════════════════════════════════════════════════════════════════════
#  DETERMINISTIC propagation table  (type_evt, relation.type) → effect
# ════════════════════════════════════════════════════════════════════════════
#
# This is the deterministic core: given the TYPE of the current event and the TYPE
# of the outgoing relationship, what TYPE of effect propagates to the target? A pair
# absent from the table → None (the wave has no effect through this link). The table
# is EXTENSIBLE per campaign (see _REGLES_CAMPAGNE / enrichir_regles).
#
# Reading: (incoming event type, relationship type) -> {"type": <outgoing effect type>}.
# Effect types are neutral narrative labels; their QUALIFICATION (the
# "how") is deferred to the LLM, not here.

_REGLES_PROPAGATION: dict[tuple[str, str], dict] = {
    # — Predation / raid: a raid or pillage puts local pressure on what the predator
    #   covets or threatens.
    ("raid", "predation"):        {"type": "pression_locale"},
    ("pillage", "predation"):     {"type": "pression_locale"},
    ("raid", "approvisionnement"): {"type": "penurie"},          # the target loses its source
    ("pillage", "approvisionnement"): {"type": "penurie"},

    # — Shortage / famine: propagates along supply chains (after reserves are depleted,
    #   encoded by delai_ut), escalates to overlords (call for help), and pushes
    #   dependents to leave (migration).
    ("penurie", "approvisionnement"): {"type": "penurie"},
    ("penurie", "route_commerciale"): {"type": "penurie"},
    ("penurie", "vassalite"):     {"type": "appel_a_l_aide"},
    ("penurie", "tutelle"):       {"type": "appel_a_l_aide"},
    ("penurie", "alliance"):      {"type": "appel_a_l_aide"},
    ("penurie", "predation"):     {"type": "depart_migrants"},   # a settlement that can no longer feed itself migrates

    # — Fire / disaster to fields or stores: cuts off downstream supply.
    ("incendie", "approvisionnement"): {"type": "penurie"},
    ("incendie", "route_commerciale"): {"type": "penurie"},

    # — Hostility / war: draws in allies (relief) and reveals/activates treacheries.
    ("guerre", "alliance"):       {"type": "appel_a_l_aide"},
    ("guerre", "hostilite"):      {"type": "represailles"},
    ("guerre", "vassalite"):      {"type": "requisition"},
    ("trahison", "commandement"): {"type": "desordre"},

    # — Local pressure: a zone under pressure hardens its positions (fortification)
    #   and strains its relations with rivals/competitors.
    ("pression_locale", "predation"):    {"type": "fortification"},
    ("pression_locale", "concurrence"):  {"type": "tension"},
    ("pression_locale", "rivalite"):     {"type": "tension"},

    # — Ongoing migration: a passing column puts pressure on the territory it crosses.
    ("migration", "predation"):   {"type": "pression_locale"},
    ("depart_migrants", "predation"): {"type": "pression_locale"},
}

# Campaign-specific overrides (populated by enrichir_regles), take priority over
# the base table.
_REGLES_CAMPAGNE: dict[tuple[str, str], dict] = {}


def enrichir_regles(rules: dict) -> None:
    """Registers campaign-SPECIFIC propagation rules.

    `rules`: { (type_evt, type_relation) -> {"type": <effect>} } OR
              { "<type_evt>|<type_relation>" -> {"type": <effect>} }.
    These pairs TAKE PRIORITY over the base table. No persistent global side effects:
    used for extensions/tests. (The contract allows a table extensible per campaign.)
    """
    if not isinstance(rules, dict):
        return
    for cle, effet in rules.items():
        if isinstance(cle, tuple) and len(cle) == 2:
            couple = (str(cle[0]), str(cle[1]))
        elif isinstance(cle, str) and "|" in cle:
            g, d = cle.split("|", 1)
            couple = (g.strip(), d.strip())
        else:
            continue
        if isinstance(effet, dict) and isinstance(effet.get("type"), str):
            _REGLES_CAMPAGNE[couple] = {"type": effet["type"]}


def regle_de_propagation(type_evt: str, relation: dict) -> dict | None:
    """DETERMINISTIC table (type_evt, relation.type) → effect {'type':…} or None.

    Returns the TYPE of effect that propagates to the target through this relationship,
    or None if the pair has no effect (the wave has no effect through this link).
    Campaign overrides (enrichir_regles) take priority over the base table.
    Unknown pairs → None.

    Examples (contract §8.2):
      (raid|pillage, predation)     → 'pression_locale'
      (penurie, approvisionnement)  → 'penurie'
      (penurie, vassalite)          → 'appel_a_l_aide'
      (incendie, approvisionnement) → 'penurie'
    """
    if not isinstance(relation, dict):
        return None
    type_rel = relation.get("type")
    if not isinstance(type_evt, str) or not isinstance(type_rel, str):
        return None
    couple = (type_evt, type_rel)
    effet = _REGLES_CAMPAGNE.get(couple) or _REGLES_PROPAGATION.get(couple)
    if effet is None:
        return None
    # Defensive copy (the table must never be mutated by the caller).
    return {"type": effet["type"]}


# ════════════════════════════════════════════════════════════════════════════
#  Factory for a "scheduled" event  (contract §8.3)
# ════════════════════════════════════════════════════════════════════════════

def _t_pad(T: int) -> str:
    """Zero-pads T for readable id uniqueness (at least 4 digits)."""
    return f"{int(T):04d}"


def programmer_evenement(*, cible: str, T: int, type: str,
                         significativite: float, cause: str,
                         statut: str = "programme") -> dict:
    """Builds a SCHEDULED event conforming to evenement_programme.schema.json (§8.3).

    id = 'evt:<type>-<T>' (T zero-padded for uniqueness). T is a FUTURE instant in UT.
    'narratif' remains None: narrative qualification is DEFERRED to the LLM seam
    (qualifier_narratif), done only at resolution if observable. Significance is
    bounded within [0, 1].
    """
    sig = float(significativite)
    sig = 0.0 if sig < 0 else (1.0 if sig > 1 else sig)
    return {
        "id": f"evt:{type}-{_t_pad(T)}",
        "T": int(T),
        "type": str(type),
        "cible": str(cible),
        "acteur": None,
        "cause": str(cause),
        "significativite": round(sig, 6),
        "statut": str(statut),
        "label": None,
        "consequence_attendue": None,
        "visible_par_pj": False,
        "narratif": None,            # ← DEFERRED LLM qualification (never computed here)
        "source": SOURCE,
    }


# ════════════════════════════════════════════════════════════════════════════
#  DEFERRED LLM seam — narrative qualification (BOUNDARY, never called here)
# ════════════════════════════════════════════════════════════════════════════

def qualifier_narratif(evt: dict, campagne: Path) -> str | None:
    """DEFERRED LLM SEAM — narrative qualification of an event, NOT called here.

    The "how" of a cascade (does the target revolt? ration? fortify? call for help?)
    is a NARRATIVE decision left to a small model, done ONLY at the RESOLUTION of
    the event by the tick engine and ONLY if the event becomes OBSERVABLE by the
    player (lazy generation, doc 04 §2). PROPAGATION (topology + timing) is purely
    deterministic and NEVER depends on this seam.

    Default implementation (and invariant of this module): returns None — NO network
    call, NO LLM. Plugging in a model (gemma-4 via `hermes -p`) is the responsibility
    of the tick engine (world_tick), at resolution; it has NOTHING to do in the
    scheduling phase. This hook exists only to CLEARLY mark the boundary.
    """
    # Explicit boundary: propagation does not invoke any LLM. Deferred to the tick.
    return None


# ════════════════════════════════════════════════════════════════════════════
#  8.2  Multi-level causal propagation, BOUNDED and DETERMINISTIC
# ════════════════════════════════════════════════════════════════════════════

def _evt_t(evt: dict) -> int:
    """T of an event (accepts 'T' or, tolerantly, integer 't'). Default 0."""
    if not isinstance(evt, dict):
        return 0
    t = evt.get("T", evt.get("t"))
    if isinstance(t, bool) or not isinstance(t, int):
        return 0
    return t


def _evt_significativite(evt: dict) -> float:
    """Significance of an event (default 0.5 if absent/unreadable)."""
    if not isinstance(evt, dict):
        return 0.5
    s = evt.get("significativite")
    if isinstance(s, bool) or not isinstance(s, (int, float)):
        return 0.5
    return float(s)


def _noeud_source(evt: dict, idx: dict[str, dict]) -> str | None:
    """id of the actor-NODE from which the relationships propagating this event originate.

    Chooses the node ACTUALLY present in actors.json (`idx`):
      * priority to the TARGET — once an event is RESOLVED on a target, it is that
        target which re-propagates along ITS OWN dependencies (the starving settlement
        migrates, the city in shortage calls its overlord…). Conforms to the worked
        example in doc 04 §4 (the fire on a city propagates via that city's relationships,
        then its overlord's, etc.);
      * failing that (target = simple location without relationships, e.g. the hut
        targeted by a raid), the originating ACTOR — it is the RAIDER who carries the
        predation relationships toward its victims.
    Returns None if neither the target nor the actor is a known node.
    """
    if not isinstance(evt, dict):
        return None
    candidats = []
    for clef in ("cible", "acteur"):
        v = evt.get(clef)
        if isinstance(v, str) and v:
            candidats.append(v)
    # Priority to the candidate present in actors.json.
    for c in candidats:
        if c in idx:
            return c
    # Otherwise, the first candidate (the wave will die out for lack of known relationships).
    return candidats[0] if candidats else None


def propager(evt: dict, profondeur: int = 0, *,
             campagne: Path, acteurs: dict | None = None,
             budget: list[int] | None = None,
             emis: list[dict] | None = None) -> list[dict]:
    """Multi-level causal propagation, BOUNDED and DETERMINISTIC (contract §8.2).

    Returns the flat list of derived "scheduled" events (all levels combined).
    Algorithm (doc 04 §2):

        if profondeur > PROFONDEUR_MAX:          return          # safeguard 1
        if evt.significativite < SEUIL:          return          # safeguard 2
        if budget exhausted (BUDGET_PAR_SOURCE): return          # safeguard 4
        for each outgoing relationship of evt's node (actors.json):
            effect = regle_de_propagation(evt.type, relation)    # deterministic
            if effect is None: continue
            evt_derive = programmer_evenement(
                cible           = relation.vers,
                T               = evt.T + relation.delai_ut,      # later
                type            = effect.type,
                significativite = evt.significativite × weight × ATTENUATION,  # safeguard 3
                cause           = evt.id,
                statut          = 'programme')
            emis.append(evt_derive); budget[0] -= 1
            propager(evt_derive, profondeur+1, …)                # bounded recursion

    NEVER recalculates the past: only schedules FUTURE events (T >= evt.T;
    any negative delai_ut is bounded to 0). DETERMINISTIC: relationships traversed
    in file order; significance STRICTLY decreasing (× weight ×
    ATTENUATION, both < 1 in practice) ⇒ guaranteed termination even in the presence
    of cycles in the causal graph.

    Accumulation parameters (for internal recursive use; top-level caller leaves
    them as default): `acteurs` = already-loaded actors.json (avoids N reads);
    `budget` = shared [remaining]; `emis` = shared accumulator list.
    """
    campagne = Path(campagne)
    if emis is None:
        emis = []
    if budget is None:
        budget = [BUDGET_PAR_SOURCE]
    if acteurs is None:
        acteurs = W.charger_acteurs(campagne)

    # — Safeguard 1: bounded depth.
    if profondeur > PROFONDEUR_MAX:
        return emis
    # — Safeguard 2: the wave dies out below the significance threshold.
    if _evt_significativite(evt) < SEUIL:
        return emis
    # — Safeguard 4: budget per source exhausted.
    if budget[0] <= 0:
        return emis

    idx = W.index_acteurs(acteurs)
    noeud_id = _noeud_source(evt, idx)
    if noeud_id is None:
        return emis

    noeud = idx.get(noeud_id)
    if noeud is None:
        # Target/actor outside actors.json (e.g. a simple location with no known
        # dependencies): no outgoing relationships → the wave stops here (deterministic,
        # fail-open).
        return emis

    type_evt = evt.get("type") if isinstance(evt, dict) else None
    sig_courante = _evt_significativite(evt)
    t_courant_evt = _evt_t(evt)
    cause_id = evt.get("id") if isinstance(evt, dict) else None
    if not isinstance(cause_id, str) or not cause_id:
        cause_id = f"evt:{type_evt}-{_t_pad(t_courant_evt)}"

    for relation in W.relations_de(noeud):
        if budget[0] <= 0:
            break
        effet = regle_de_propagation(type_evt, relation)
        if effet is None:
            continue

        cible = relation.get("vers")
        if not isinstance(cible, str) or not cible:
            continue

        # — Later: T = T_cause + delai_ut (causal conservation). Never the past.
        delai = relation.get("delai_ut", 0)
        if isinstance(delai, bool) or not isinstance(delai, int):
            delai = 0
        if delai < 0:
            delai = 0
        T_derive = t_courant_evt + delai

        # — Attenuation: STRICTLY decreasing significance.
        poids = relation.get("poids")
        if isinstance(poids, bool) or not isinstance(poids, (int, float)):
            poids = relation.get("intensite")
        if isinstance(poids, bool) or not isinstance(poids, (int, float)):
            poids = 0.5
        poids = float(poids)
        if poids < 0:
            poids = 0.0
        elif poids > 1:
            poids = 1.0  # caps intensity at 1 → STRICT decrease guaranteed (weight·ATTENUATION < 1)
        sig_derive = sig_courante * poids * ATTENUATION

        evt_derive = programmer_evenement(
            cible=cible,
            T=T_derive,
            type=effet["type"],
            significativite=sig_derive,
            cause=cause_id,
            statut="programme",
        )
        # Attribution: the originating actor remains the current node if it is one.
        # GENERIC test for a namespaced id (`type:path`) — fixes no prefix.
        if isinstance(noeud_id, str) and ":" in noeud_id:
            evt_derive["acteur"] = noeud_id
        evt_derive["profondeur"] = profondeur + 1

        # — Invariant safety: NEVER schedule in the past.
        if evt_derive["T"] < t_courant_evt:
            evt_derive["T"] = t_courant_evt
            evt_derive["id"] = f"evt:{evt_derive['type']}-{_t_pad(evt_derive['T'])}"

        emis.append(evt_derive)
        budget[0] -= 1

        # — Bounded recursion (the depth/threshold guard is at the head of propager).
        propager(evt_derive, profondeur + 1,
                 campagne=campagne, acteurs=acteurs, budget=budget, emis=emis)

    return emis


# ════════════════════════════════════════════════════════════════════════════
#  Seed from a fulfilled intention  (CLI --intention)
# ════════════════════════════════════════════════════════════════════════════

def _evt_racine_depuis_intention(campagne: Path, acteur_id: str,
                                 intent_id: str, acteurs: dict) -> dict | None:
    """Builds the ROOT event from an actor's intention (actors.json).

    The target = intention.lieu (or the actor itself if non-spatial). The type = effect
    type inferred from the action (simple heuristic: 'raid' if the action evokes a raid,
    otherwise 'consequence'). Significance = intention.significativite (default 0.5).
    T = intention deadline (deterministic). Returns None if not found.
    """
    idx = W.index_acteurs(acteurs)
    acteur = idx.get(acteur_id)
    if acteur is None:
        _log(f"❌ Actor not found in actors.json: {acteur_id}")
        return None
    intention = None
    for it in acteur.get("plan", []) or []:
        if isinstance(it, dict) and it.get("id") == intent_id:
            intention = it
            break
    if intention is None:
        _log(f"❌ Intention « {intent_id} » not found in {acteur_id}'s plan.")
        return None

    cible = intention.get("lieu")
    if not isinstance(cible, str) or not cible:
        cible = acteur_id

    # Root effect type: LIGHTWEIGHT deterministic heuristic on the action label.
    action = (intention.get("action") or "").lower()
    if "raid" in action or "pille" in action or "pillage" in action or "razzia" in action:
        type_evt = "raid"
    elif "incend" in action or "brûl" in action or "brul" in action:
        type_evt = "incendie"
    elif "pénur" in action or "penur" in action or "famine" in action:
        type_evt = "penurie"
    else:
        type_evt = "consequence"

    T = intention.get("echeance")
    if isinstance(T, bool) or not isinstance(T, int):
        T = W.t_courant(campagne)

    sig = intention.get("significativite")
    if isinstance(sig, bool) or not isinstance(sig, (int, float)):
        sig = 0.5

    racine = {
        "id": f"{acteur_id}#{intent_id}",
        "T": int(T),
        "type": type_evt,
        "cible": cible,
        "acteur": acteur_id,
        "cause": intent_id,
        "significativite": float(sig),
        "statut": "resolu",          # the intention is FULFILLED → the root is resolved
    }
    return racine


# ════════════════════════════════════════════════════════════════════════════
#  Persistence — atomic append to scheduled_events.json (SEPARATE)
# ════════════════════════════════════════════════════════════════════════════

NOM_FICHIER_PROG = "scheduled_events.json"


def _meta_par_defaut(campagne: Path) -> dict:
    """Metadata for a fresh scheduled_events.json (contract §8.3)."""
    return {
        "campagne": _nom_campagne(campagne),
        "version": PROG_VERSION,
        "note": ("Evenements PROGRAMMES/RESOLUS par le monde vivant. T en UT. "
                 "Ne JAMAIS fusionner dans events.json sans decision MJ."),
    }


def _nom_campagne(campagne: Path) -> str:
    """Human-readable campaign name (from world.json if possible, otherwise folder)."""
    monde = W.charger_json(Path(campagne) / "world.json", {}) or {}
    for chemin in (("meta", "name"), ("meta", "titre"), ("titre",), ("name",)):
        cur = monde
        ok = True
        for k in chemin:
            if isinstance(cur, dict) and k in cur:
                cur = cur[k]
            else:
                ok = False
                break
        if ok and isinstance(cur, str) and cur:
            return cur
    return Path(campagne).name


def appliquer(campagne: Path, evenements: list[dict]) -> int:
    """ATOMIC append of events to scheduled_events.json. Returns the number written.

    Creates the file (with metadata) if it does not exist. WRITES ONLY this SEPARATE
    file — NEVER to events.json (non-destructive invariant, contract §0.2/§14.3).
    Duplicate ids already present are ignored (idempotence: the same scheduled event
    is never emitted twice). Raises OSError if the atomic write fails (outside the
    game loop: fail-hard assumed).
    """
    campagne = Path(campagne)
    if not evenements:
        return 0
    chemin = campagne / NOM_FICHIER_PROG
    fichier = W.charger_json(chemin, None)
    if not isinstance(fichier, dict) or "evenements" not in fichier:
        fichier = {"meta": _meta_par_defaut(campagne), "evenements": []}
    if not isinstance(fichier.get("evenements"), list):
        fichier["evenements"] = []

    existants = {e.get("id") for e in fichier["evenements"]
                 if isinstance(e, dict) and isinstance(e.get("id"), str)}

    ecrits = 0
    for evt in evenements:
        if not isinstance(evt, dict):
            continue
        eid = evt.get("id")
        if isinstance(eid, str) and eid in existants:
            continue
        fichier["evenements"].append(evt)
        if isinstance(eid, str):
            existants.add(eid)
        ecrits += 1

    if ecrits:
        W.sauver_json_atomique(chemin, fichier)
    return ecrits


# ════════════════════════════════════════════════════════════════════════════
#  Propagation summary (return value / CLI output)
# ════════════════════════════════════════════════════════════════════════════

def resumer(evt_racine: dict, derives: list[dict], *, ecrits: int = 0,
            applique: bool = False) -> dict:
    """Builds a STRUCTURED propagation summary (CLI/import return value).

    {'racine': {id,T,type,cible,significativite},
     'nb_derives': int, 'profondeur_max': int, 'significativite_min': float|None,
     'eteinte_demblee': bool, 'derives': [evt…], 'ecrits': int, 'applique': bool}.
    """
    profs = [int(e.get("profondeur", 0)) for e in derives]
    sigs = [float(e.get("significativite", 0.0)) for e in derives]
    sig_racine = _evt_significativite(evt_racine)
    return {
        "racine": {
            "id": evt_racine.get("id"),
            "T": _evt_t(evt_racine),
            "type": evt_racine.get("type"),
            "cible": evt_racine.get("cible"),
            "significativite": round(sig_racine, 6),
        },
        "nb_derives": len(derives),
        "profondeur_max": max(profs) if profs else 0,
        "significativite_min": round(min(sigs), 6) if sigs else None,
        "eteinte_demblee": (sig_racine < SEUIL),
        "derives": derives,
        "ecrits": ecrits,
        "applique": applique,
    }


# ════════════════════════════════════════════════════════════════════════════
#  CLI — argparse with subcommand `propager` (first positional = campaign)
# ════════════════════════════════════════════════════════════════════════════

def _exiger_campagne(args) -> Path | None:
    """Resolves and VERIFIES the existence of the campaign folder. None → exit code 2."""
    camp = W.chemin_campagne(args.campagne)
    if not camp.is_dir():
        _log(f"❌ Campaign not found: {camp}")
        return None
    return camp


def _sortir_json(obj) -> None:
    print(json.dumps(obj, ensure_ascii=False, indent=2))


def _charger_evt_arg(spec: str) -> dict | None:
    """Resolves the --evt argument: JSON file path or '-' (stdin).

    Returns the event object (dict), or None on failure (reported on stderr).
    Accepts either a standalone event or {'evenements':[…]} (takes the 1st).
    """
    if spec is None:
        return None
    spec = str(spec)
    if spec == "-":
        try:
            data = json.load(sys.stdin)
        except (json.JSONDecodeError, ValueError) as e:
            _log(f"❌ event (stdin): unreadable JSON: {e}.")
            return None
    else:
        data = W.charger_json(spec, None)
        if data is None:
            _log(f"❌ event: file not found or unreadable « {spec} ».")
            return None
    if isinstance(data, dict) and isinstance(data.get("evenements"), list) and data["evenements"]:
        prem = data["evenements"][0]
        return prem if isinstance(prem, dict) else None
    if isinstance(data, dict):
        return data
    _log("❌ event: unexpected format (event object expected).")
    return None


def _afficher_resume_texte(res: dict, camp: Path, applique: bool) -> None:
    """Compact text output with markers (contract §0.7)."""
    r = res["racine"]
    print(f"🌊 Causal propagation — {camp.name}")
    print(f"   root: {r['id']}  ({r['type']} @ {r['cible']}, "
          f"signif. {r['significativite']}, {W.t_vers_narratif(r['T'])})")
    if res["eteinte_demblee"]:
        print(f"   ℹ wave extinguished immediately: significance {r['significativite']} "
              f"< SEUIL {SEUIL}. No derived events.")
        return
    if not res["derives"]:
        print("   ℹ no derived events (no propagating relationship).")
        return
    print(f"   ➜ {res['nb_derives']} derived event(s) "
          f"(max depth {res['profondeur_max']}, "
          f"min signif. {res['significativite_min']}):")
    for e in res["derives"]:
        prof = int(e.get("profondeur", 0))
        indent = "   " + "  " * prof
        print(f"{indent}• {e['type']} @ {e['cible']}  "
              f"⏱ {W.t_vers_narratif(e['T'])}  signif. {e['significativite']}  "
              f"(cause {e['cause']})")
    if applique:
        print(f"   ✅ {res['ecrits']} event(s) written → {camp / NOM_FICHIER_PROG}")
    else:
        print(f"   ℹ dry-run: nothing written (use --apply to write "
              f"{camp / NOM_FICHIER_PROG}).")


def cmd_propager(args) -> int:
    camp = _exiger_campagne(args)
    if camp is None:
        return 2

    # Seed source: --evt (root event) OR --intention (actor:intent).
    if bool(args.evt) == bool(args.intention):
        _log("❌ Provide EXACTLY one seed: --evt <file|-> OR "
             "--intention <acteur_id>:<intent_id>.")
        return 2

    acteurs = W.charger_acteurs(camp)

    if args.evt:
        evt_racine = _charger_evt_arg(args.evt)
        if evt_racine is None:
            return 2
    else:
        spec = str(args.intention)
        if ":" not in spec:
            _log("❌ --intention expects the format <acteur_id>:<intent_id> "
                 "(e.g. 'faction:<faction>:intent:<intent>').")
            return 2
        # The actor id itself contains ':' (e.g. 'faction:<faction>'), and the
        # intention id too ('intent:<intent>'). Split on the '#' SEPARATOR if
        # present, otherwise cut before the last 'intent:'.
        if "#" in spec:
            acteur_id, intent_id = spec.split("#", 1)
        elif ":intent:" in spec:
            acteur_id, reste = spec.split(":intent:", 1)
            intent_id = "intent:" + reste
        else:
            acteur_id, intent_id = spec.rsplit(":", 1)
        evt_racine = _evt_racine_depuis_intention(camp, acteur_id, intent_id, acteurs)
        if evt_racine is None:
            return 2

    # — Propagation (DETERMINISTIC, bounded). The root itself is NOT rewritten;
    #   ONLY its derived events are scheduled (the root is already a fact/intention).
    derives = propager(evt_racine, 0, campagne=camp, acteurs=acteurs)

    ecrits = 0
    if args.apply and derives:
        try:
            ecrits = appliquer(camp, derives)
        except OSError as e:
            _log(f"❌ Failed to write {NOM_FICHIER_PROG}: {e}")
            return 2

    res = resumer(evt_racine, derives, ecrits=ecrits, applique=bool(args.apply))

    if args.as_json:
        out = {k: v for k, v in res.items()}
        out["mode"] = "apply" if args.apply else "dry-run"
        out["fichier"] = str(camp / NOM_FICHIER_PROG)
        _sortir_json(out)
    else:
        _afficher_resume_texte(res, camp, applique=bool(args.apply))

    # Exit codes: 1 if the wave dies out immediately (below SEUIL → no derived events); 0 otherwise.
    if res["eteinte_demblee"]:
        return 1
    return 0


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="causal_propagate.py",
        description="Bounded, deterministic causal propagation of the living world "
                    "(MJ Tonnerre).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python3 causal_propagate.py propager <campagne> --evt racine.json --json\n"
            "  echo '{\"id\":\"evt:incendie-4000\",\"T\":4000,\"type\":\"incendie\","
            "\"cible\":\"ville:<ville>\",\"significativite\":0.9}' | \\\n"
            "      python3 causal_propagate.py propager <campagne> --evt -\n"
            "  python3 causal_propagate.py propager <campagne> "
            "--intention faction:<faction>:intent:<intent> --apply\n"
            "\nSafeguards (guaranteed termination): PROFONDEUR_MAX="
            f"{PROFONDEUR_MAX}, SEUIL={SEUIL}, ATTENUATION={ATTENUATION}, "
            f"BUDGET_PAR_SOURCE={BUDGET_PAR_SOURCE}.\n"
            "Writes ONLY scheduled_events.json (never events.json)."
        ),
    )
    sub = ap.add_subparsers(dest="commande", required=True)

    p = sub.add_parser(
        "propager",
        help="Propagate a root event (or intention) and schedule its derived events.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("campagne", help="Path to the campaign folder.")
    p.add_argument("--evt", default=None,
                   help="Root event: JSON file path | '-' (stdin).")
    p.add_argument("--intention", default=None,
                   help="Seed from a fulfilled intention: "
                        "<acteur_id>:<intent_id> (e.g. "
                        "'faction:<faction>:intent:<intent>').")
    p.add_argument("--apply", action="store_true",
                   help="Atomically append derived events to scheduled_events.json.")
    p.add_argument("--json", action="store_true", dest="as_json",
                   help="Output in JSON format (summary + derived events).")
    p.set_defaults(func=cmd_propager)

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
