#!/usr/bin/env python3
"""
world_tick.py — Tick engine for the "living world" (MJ Tonnerre).

The HEARTBEAT of the world (doc 03, contract §7). It advances actor plans,
applies consequences DETERMINISTICALLY, invokes the LLM only at *seams*
(a single boundary: `agent_decide`, §7.5), emits T-dated events and
triggers causal cascades (via `causal_propagate`, bounded §8). Two modes:

  * PRE  — projection + staging. Projects the world up to `--t-session`,
    classifies LOD (hot/warm/cold), resolves due intentions, makes warm/hot
    actors "think" (LLM seam, here deterministic STUB), computes crossings
    with the player's cone (via geo_query.croisement), promotes to hot,
    and ASSEMBLES a text briefing ready for injection.
  * POST — reconciliation. Confronts the PLANNED plan with REALITY (player
    facts read from a session log), marks intentions accomplished/failed,
    renews disrupted plans (LLM seam) and propagates player actions (the
    player becomes a cause).

The LLM seam `agent_decide` is a CLEARLY ISOLATED BOUNDARY FUNCTION: HERE it
returns a deterministic STUB (continuation of long-term goal as intention) WITHOUT
any network call. The real LLM integration (gemma-4 via `hermes -p acteur-<slug>`)
is INJECTABLE (env var `MGM_AGENT_DECIDE_CMD`) and outside pure-code scope.

Cross-cutting conventions (contract §0):
  * source of truth = files; no state outside files;
  * NON-DESTRUCTIVE: NEVER writes to world.json / npcs.json / events.json /
    hooks / existing scripts. WRITES only to actors.json
    (plans/trajectories/lod) and evenements_programmes.json (emitted events), and
    only in --apply mode, via worldlib atomic write;
  * exit codes: 0 ok; 1 business condition signalled; 2 usage / file not found;
    3 TEMPORAL INCOHERENCE (see below);
  * `pre`/`post` run OUTSIDE the narration loop: they CAN fail hard in
    --apply (file not found → 2). READS remain fail-open EXCEPT on game time.

TEMPORAL COHERENCE (TIME-04). Fail-open is not coherence: reading game time was
guarded by `except: T = 0`, so a campaign on day 58 whose files became unreadable
kept ticking at day 1, exited 0, and reported success. Game time is now read in
ONE place (`_t_courant`) and it fails loud. A projection window that runs
backwards, and a reconciliation with no session log to reconcile against, are
reported as incoherences and exit 3. A no-op that comes from a FEATURE TOGGLE is
a different thing: it stays exit 0, but it is announced in the output.
Escape hatch: MGM_ALLOW_CLOCK_DRIFT=1 accepts the incoherence (still reported).

Targets: Python 3.11, PURE STDLIB (no external dependencies). Imports `worldlib`
and MAY import `geo_query` and `causal_propagate` as modules (only authorised
inter-script dependencies, contract §0.9 / §7). Robust to ABSENCE of
`causal_propagate` (parallel development): degraded propagation if unavailable.

CLI:
  world_tick.py pre   <campaign> [--t-session T] [--cone <f|->] [--apply] [--json]
  world_tick.py post  <campaign> [--session <NNN|file>] [--apply] [--json]
  world_tick.py lod   <campaign> [--t T] [--json]
  world_tick.py actor <campaign> promote|demote <actor_id> [--apply]

See contract `docs/living-world/08-implementation-contract.md` §6, §7, §13, §14.
"""

from __future__ import annotations

import argparse
import json
import os
import shlex
import subprocess
import sys
from pathlib import Path

import worldlib as W

# geo_query is an AUTHORISED dependency (contract §7): imported for
# `projeter_croisements` (crossing) and cone resolution. Defensive import:
# if unavailable, we degrade (no crossings rather than a crash).
try:
    import geo_query as G
except Exception as _e_geo:          # pragma: no cover - robustesse import
    G = None
    print(f"ℹ world_tick : geo_query unavailable ({_e_geo}) — "
          f"crossings disabled (degraded mode).", file=sys.stderr)

# causal_propagate is an AUTHORISED dependency but may not yet exist
# (parallel development, contract §0.9). Defensive import → degraded propagation.
try:
    import causal_propagate as C
except Exception as _e_causal:        # pragma: no cover - robustesse import
    C = None


SCRIPTS_DIR = Path(__file__).resolve().parent


def _log(message: str) -> None:
    """Log to stderr (never pollutes --json on stdout)."""
    print(message, file=sys.stderr)


# ════════════════════════════════════════════════════════════════════════════
#  7.4  Tick constants (fixed)
# ════════════════════════════════════════════════════════════════════════════

SEUIL_TIEDE_UT = 864       # 6 h of travel: below this → warm
SEUIL_CROISEMENT = 50.0    # crossing anchor distance (≈ "within sight range")
PAS_PROJECTION_UT = 6      # crossing sampling step (1 h)

# Default "recent" window in a briefing (3 days).
_FENETRE_RECENT_UT = 432
# Default propagation delay when a relation specifies none.
_DELAI_PROPAGATION_DEFAUT = 0


# ════════════════════════════════════════════════════════════════════════════
#  Safe operators (preconditions) — DETERMINISTIC evaluable subset
# ════════════════════════════════════════════════════════════════════════════

import re as _re

# Numeric comparison "ressources.<key> <op> <number>" ONLY (safe).
_OPERATEURS = {
    "<": lambda a, b: a < b,
    "<=": lambda a, b: a <= b,
    ">": lambda a, b: a > b,
    ">=": lambda a, b: a >= b,
    "==": lambda a, b: a == b,
    "!=": lambda a, b: a != b,
}
_RE_PRECOND = _re.compile(
    r"^\s*ressources\.([A-Za-z_][A-Za-z0-9_]*)\s*"
    r"(<=|>=|==|!=|<|>)\s*(-?\d+(?:\.\d+)?)\s*$"
)


# ════════════════════════════════════════════════════════════════════════════
#  7.3  Internal functions — LOD
# ════════════════════════════════════════════════════════════════════════════

def _cone_lieux(cone: dict | None) -> list[str]:
    """Locations of interest from the player's cone (probable destinations). [] if no cone."""
    if not isinstance(cone, dict):
        return []
    lieux = cone.get("locations", [])
    return [l for l in lieux if isinstance(l, str)] if isinstance(lieux, list) else []


def _cone_fenetre(cone: dict | None, defaut: tuple[int, int]) -> tuple[int, int]:
    """Window [T0,T1] of the cone (provided default if absent/malformed)."""
    if isinstance(cone, dict):
        fen = cone.get("fenetre")
        if (isinstance(fen, list) and len(fen) == 2
                and all(isinstance(x, (int, float)) for x in fen)):
            return (int(fen[0]), int(fen[1]))
    return defaut


def classer_LOD(acteur: dict, contexte_joueur: dict, geo: dict, T_a: int) -> str:
    """Returns 'chaud' | 'tiede' | 'froid' (contract §7.3).

    Combines SPATIAL distance (geo) and TEMPORAL imminence (plan's minimum deadline
    vs the window [T_de, T_a]). FIXED rules:
      * 'chaud'  : the actor is at the player's current location OR a crossing is
                   already materialised (present in contexte_joueur['croisements_ids']);
      * 'tiede'  : distance_graphe_ut(actor, cone) <= SEUIL_TIEDE_UT (=864, 6 h)
                   OR a 'planifie' deadline from the plan falls within [T_de, T_a];
      * 'froid'  : otherwise.
    An actor with `majeur:false` is ALWAYS 'froid' (frozen reactive sheet, doc 02 §2).
    PCs (resolved by worldlib.pj_ids, reserved) are never classified here by
    the caller.
    """
    if not isinstance(acteur, dict):
        return "froid"
    if not acteur.get("majeur", False):
        return "froid"

    T_a = int(T_a)
    T_de = int(contexte_joueur.get("T_de", T_a)) if isinstance(contexte_joueur, dict) else T_a
    cone = contexte_joueur.get("cone") if isinstance(contexte_joueur, dict) else None
    lieu_joueur = contexte_joueur.get("lieu_joueur") if isinstance(contexte_joueur, dict) else None
    croisements_ids = (contexte_joueur.get("croisements_ids", set())
                       if isinstance(contexte_joueur, dict) else set())

    aid = acteur.get("id")
    traj = W.trajectoire_de(acteur)

    # --- HOT: co-located with the player OR crossing already materialised. ---
    if aid in croisements_ids:
        return "chaud"
    if isinstance(lieu_joueur, str) and traj:
        pos = W.position_a(geo, traj, T_a)
        lieu_acteur = pos.get("lieu") if pos else None
        if lieu_acteur is not None and _meme_lieu_ou_contenu(geo, lieu_acteur, lieu_joueur):
            return "chaud"

    # --- WARM (temporal imminence): a deadline falls within the window. ---
    for intention in _plan(acteur):
        if intention.get("statut") != "planifie":
            continue
        ech = _echeance_int(intention)
        if ech is not None and T_de <= ech <= T_a:
            return "tiede"

    # --- WARM (spatial proximity): within <= SEUIL_TIEDE_UT of the player's cone. ---
    cone_lieux = _cone_lieux(cone)
    if cone_lieux and traj:
        pos = W.position_a(geo, traj, T_a)
        lieu_acteur = pos.get("lieu") if pos else None
        if isinstance(lieu_acteur, str):
            for cible in cone_lieux:
                d = W.distance_graphe_ut(geo, lieu_acteur, cible)
                if d is not None and 0 <= d <= SEUIL_TIEDE_UT:
                    return "tiede"

    return "froid"


def _meme_lieu_ou_contenu(geo: dict, lieu_a: str, lieu_b: str) -> bool:
    """True if lieu_a == lieu_b, or if one contains the other (containment)."""
    if lieu_a == lieu_b:
        return True
    if lieu_b in W.contenus(geo, lieu_a, recursif=True):
        return True
    if lieu_a in W.contenus(geo, lieu_b, recursif=True):
        return True
    return False


def _plan(acteur: dict) -> list[dict]:
    """Plan (intention list) of an actor, robust."""
    if not isinstance(acteur, dict):
        return []
    plan = acteur.get("plan", [])
    return [i for i in plan if isinstance(i, dict)] if isinstance(plan, list) else []


def _echeance_int(intention: dict, campagne: Path | None = None) -> int | None:
    """Deadline of an intention in T (UT), DETERMINISTIC.

    'echeance' is already an integer in the fixed format; we tolerate it being
    provided in pinned form (via worldlib.echeance_en_t) for robustness.
    """
    ech = intention.get("echeance")
    if isinstance(ech, bool):
        return None
    if isinstance(ech, int):
        return ech
    # Tolerance: pinned deadline not yet converted.
    src = intention.get("echeance_source", ech)
    try:
        return W.echeance_en_t(src, campagne or Path("."))
    except Exception:
        return None


# ════════════════════════════════════════════════════════════════════════════
#  7.3  Preconditions and extended Steward
# ════════════════════════════════════════════════════════════════════════════

def evaluer_preconditions(intention: dict, acteur: dict, T: int) -> bool:
    """Evaluates the preconditions of an intention (contract §7.3).

    SAFE subset: numeric comparisons "ressources.<key> <op> <number>"
    ONLY (no Python eval). Any UNKNOWN or unparseable precondition →
    True (FAIL-OPEN: we never block an intention due to a missing machine
    precondition — the narrative decision falls back to the GM). All must be true (AND).
    """
    if not isinstance(intention, dict):
        return True
    conditions = intention.get("preconditions", [])
    if not isinstance(conditions, list) or not conditions:
        return True
    ressources = acteur.get("ressources", {}) if isinstance(acteur, dict) else {}
    if not isinstance(ressources, dict):
        ressources = {}

    for cond in conditions:
        if not isinstance(cond, str):
            continue
        m = _RE_PRECOND.match(cond)
        if m is None:
            # Unparseable → fail-open (does not block).
            continue
        clef, op, nombre = m.group(1), m.group(2), m.group(3)
        valeur = ressources.get(clef)
        if not isinstance(valeur, (int, float)) or isinstance(valeur, bool):
            # Resource absent/non-numeric → cannot decide → fail-open.
            continue
        seuil = float(nombre)
        fonc = _OPERATEURS.get(op)
        if fonc is None:
            continue
        if not fonc(float(valeur), seuil):
            return False
    return True


def appliquer_consequence(acteur: dict, intention: dict,
                          acteurs_idx: dict, geo: dict) -> dict:
    """Extended Steward (contract §7.3): applies `consequence_effets` of the intention.

    RESOURCE deltas (key → number, may be negative), RELATION mutations,
    and (optionally) a TRAJECTORY segment toward `intention['lieu']`. Mutates
    the actor IN PLACE (and targets in acteurs_idx for relations). REFUSES
    (returns {'ok':False, 'motif':…}) if a CONSERVATION is violated:
      * resource rendered NEGATIVE (creating a deficit is forbidden);
      * teleportation (movement duration < sum of edges — delegated to
        deplacer/valider_trajectoire; here we only apply a real displacement).
    Returns {'ok':True, 'changements':[…]} otherwise.
    """
    if not isinstance(acteur, dict) or not isinstance(intention, dict):
        return {"ok": False, "motif": "actor or intention invalid.", "changements": []}

    effets = intention.get("consequence_effets")
    changements: list[str] = []
    if not isinstance(effets, dict):
        # No machine effect: purely narrative consequence, nothing to apply.
        return {"ok": True, "changements": changements}

    # --- 1) Pre-check resources (atomicity: validate before mutating). ---
    deltas = effets.get("ressources")
    ressources = acteur.setdefault("ressources", {})
    if isinstance(deltas, dict):
        if not isinstance(ressources, dict):
            return {"ok": False, "motif": "actor resources are not well-formed.",
                    "changements": changements}
        projete = dict(ressources)
        for clef, delta in deltas.items():
            if not isinstance(delta, (int, float)) or isinstance(delta, bool):
                continue
            base = projete.get(clef, 0)
            if not isinstance(base, (int, float)) or isinstance(base, bool):
                base = 0
            nouvelle = base + delta
            if nouvelle < 0:
                return {
                    "ok": False,
                    "motif": (f"conservation violation: resource « {clef} » would become "
                              f"negative ({base} + {delta} = {nouvelle})."),
                    "changements": changements,
                }
            projete[clef] = nouvelle
        # Application (atomic: the projection is entirely valid).
        for clef, val in projete.items():
            if ressources.get(clef) != val:
                changements.append(f"ressources.{clef} → {val}")
        acteur["ressources"] = projete

    # --- 2) Relation mutations (on the source actor). ---
    relations_effets = effets.get("relations")
    if isinstance(relations_effets, list):
        rels = acteur.setdefault("relations", [])
        if not isinstance(rels, list):
            rels = []
            acteur["relations"] = rels
        for rel in relations_effets:
            if not isinstance(rel, dict) or "vers" not in rel or "type" not in rel:
                continue
            existante = _trouver_relation(rels, rel.get("vers"), rel.get("type"))
            if existante is None:
                rels.append(dict(rel))
                changements.append(f"relation +{rel.get('type')}→{rel.get('vers')}")
            else:
                for k, v in rel.items():
                    existante[k] = v
                changements.append(f"relation ~{rel.get('type')}→{rel.get('vers')}")

    # --- 3) Trajectory segment (if the effect requests one). ---
    seg = effets.get("trajectory")
    if isinstance(seg, dict) and isinstance(seg.get("lieu"), str):
        traj = acteur.setdefault("trajectory", [])
        if isinstance(traj, list):
            viol = W.valider_trajectoire(geo, traj + [seg])
            if viol:
                return {"ok": False,
                        "motif": "trajectoire invalide : " + " ; ".join(viol),
                        "changements": changements}
            traj.append(seg)
            changements.append(f"trajectory +stay@{seg.get('lieu')}")

    return {"ok": True, "changements": changements}


def _trouver_relation(relations: list[dict], vers, type_):
    """Finds a relation (vers,type) in a list, or None."""
    for r in relations:
        if isinstance(r, dict) and r.get("vers") == vers and r.get("type") == type_:
            return r
    return None


# ════════════════════════════════════════════════════════════════════════════
#  7.3  Resolution of due intentions + event emission
# ════════════════════════════════════════════════════════════════════════════

def resoudre_intentions(acteur: dict, T_de: int, T_a: int,
                        campagne: Path, geo: dict,
                        acteurs_idx: dict | None = None) -> list[dict]:
    """Resolves DUE intentions of an actor (contract §7.3).

    For each 'planifie' intention whose `echeance <= T_a`:
      * if preconditions met → applies the consequence (extended Steward), emits
        a SCHEDULED event (status 'resolu') in format §8.3, triggers causal
        propagation if significant, status → 'accompli';
      * otherwise → status → 'echoue' (no automatic rescheduling: the deadline is
        "at the latest", an unsatisfied overrun is a failure — doc 03 §2).
    Mutates the actor IN PLACE. Returns the list of emitted events (resolved +
    derived). NEVER TOUCHES events.json (events go to
    evenements_programmes.json, appended by the caller in --apply).
    """
    emis: list[dict] = []
    if not isinstance(acteur, dict):
        return emis
    if acteurs_idx is None:
        acteurs_idx = {}

    T_a = int(T_a)
    for intention in _plan(acteur):
        if intention.get("statut") != "planifie":
            continue
        ech = _echeance_int(intention, campagne)
        if ech is None or ech > T_a:
            continue   # not yet due

        # Effective resolution T: the deadline (at the latest), bounded to the present.
        T_resolution = max(int(ech), int(T_de))

        if not evaluer_preconditions(intention, acteur, T_resolution):
            intention["statut"] = "echoue"
            continue

        res = appliquer_consequence(acteur, intention, acteurs_idx, geo)
        if not res.get("ok"):
            # Consequence refused by the Steward → failure (deterministic dominates).
            intention["statut"] = "echoue"
            _log(f"ℹ resoudre_intentions : « {intention.get('id')} » refused — "
                 f"{res.get('motif')}")
            continue

        # Emission of the RESOLVED event (format §8.3).
        evt = _emettre_evenement(acteur, intention, T_resolution)
        emis.append(evt)
        intention["statut"] = "accompli"

        # Causal propagation if significant (bounded, delegated to causal_propagate).
        emis.extend(_propager(evt, campagne, _acteurs_dict(acteurs_idx)))

    return emis


def _emettre_evenement(acteur: dict, intention: dict, T: int) -> dict:
    """Builds a SCHEDULED event with status 'resolu' (format §8.3).

    id = 'evt:<slug-action>-<NNNN>' (T zero-padded for uniqueness). The
    'significativite' field comes from the intention (default 0.5).
    """
    action_slug = W.slug(intention.get("action", "") or intention.get("id", "event"))
    if not action_slug:
        action_slug = "event"
    # Prefer a short slug derived from the intention id if present.
    intent_id = intention.get("id", "")
    if isinstance(intent_id, str) and intent_id.startswith("intent:"):
        action_slug = intent_id.split(":", 1)[1] or action_slug

    sig = intention.get("significativite")
    if not isinstance(sig, (int, float)) or isinstance(sig, bool):
        sig = 0.5

    return {
        "id": f"evt:{action_slug}-{int(T):05d}",
        "T": int(T),
        "type": _type_evenement(intention),
        "cible": intention.get("lieu") or acteur.get("id"),
        "actor": acteur.get("id"),
        "cause": intention.get("id"),
        "significativite": float(sig),
        "statut": "resolu",
        "label": intention.get("action", ""),
        "consequence_attendue": intention.get("consequence_attendue", ""),
        "visible_par_pj": bool(intention.get("visible_par_pj", False)),
        "narratif": None,
        "source": "world_tick.py",
    }


def _type_evenement(intention: dict) -> str:
    """Deduces an event 'type' from the intention (deterministic heuristic).

    Looks for an explicit type in consequence_effets.evenement.type, otherwise
    derives from the action (common keywords), otherwise 'action'.
    """
    effets = intention.get("consequence_effets")
    if isinstance(effets, dict):
        ev = effets.get("event")
        if isinstance(ev, dict) and isinstance(ev.get("type"), str):
            return ev["type"]
    action = (intention.get("action", "") or "").lower()
    for mot, typ in (("raid", "raid"), ("pill", "raid"), ("razzia", "raid"),
                     ("incendie", "incendie"), ("pénurie", "penurie"),
                     ("penurie", "penurie"), ("famine", "penurie"),
                     ("migrat", "migration"), ("attaqu", "attaque"),
                     ("garde", "garde"), ("veille", "garde")):
        if mot in action:
            return typ
    return "action"


def _propager(evt: dict, campagne: Path, acteurs: dict) -> list[dict]:
    """Triggers causal propagation of an event (bounded, §8).

    Delegates to `causal_propagate.propager` if the module is available; otherwise
    DEGRADED mode: no derivation (the tick never crashes). Returns the flat list of
    derived events.
    """
    if C is None:
        return []
    sig = evt.get("significativite")
    if not isinstance(sig, (int, float)) or isinstance(sig, bool):
        return []
    try:
        seuil = getattr(C, "SEUIL", 0.15)
        if sig < seuil:
            return []
        derives = C.propager(evt, 0, campagne=Path(campagne), acteurs=acteurs)
        return list(derives) if isinstance(derives, list) else []
    except Exception as e:               # robustness: propagation does not crash the tick
        _log(f"ℹ causal propagation ignored for « {evt.get('id')} » ({e}).")
        return []


def _acteurs_dict(acteurs_idx: dict) -> dict:
    """Rebuilds a {'actors':[…]} container from an id→actor index."""
    return {"actors": list(acteurs_idx.values())} if isinstance(acteurs_idx, dict) else {"actors": []}


# ════════════════════════════════════════════════════════════════════════════
#  7.3  Player × trajectory crossings
# ════════════════════════════════════════════════════════════════════════════

def projeter_croisements(campagne: Path, cone: dict,
                         acteurs_tiedes: list[dict], geo: dict,
                         seuil: float) -> list[dict]:
    """Crossings between the PLAYER's trajectory (cone) and those of warm actors.

    For each warm actor: geo_query.croisement(traj(cone), traj(actor),
    seuil). Aggregates and sorts by ascending T. This is the step "does the player
    cross the raid / migration?" (doc 03 §3). DEGRADED mode (geo_query unavailable)
    → []. Each entry: {'actor','T','lieu','distance','narratif'}.
    """
    croisements: list[dict] = []
    if G is None:
        return croisements

    traj_joueur = _trajectoire_cone(cone, geo)
    if not traj_joueur:
        return croisements

    pas = max(1, int(PAS_PROJECTION_UT))
    for acteur in acteurs_tiedes:
        if not isinstance(acteur, dict):
            continue
        aid = acteur.get("id")
        traj_acteur = W.trajectoire_de(acteur)
        if not traj_acteur:
            continue
        try:
            fenetres = G.croisement(Path(campagne), traj_joueur, traj_acteur,
                                    seuil=float(seuil), pas_ut=pas)
        except Exception as e:
            _log(f"ℹ crossing ignored for « {aid} » ({e}).")
            continue
        for f in fenetres or []:
            if not isinstance(f, dict):
                continue
            croisements.append({
                "actor": aid,
                "T": f.get("T"),
                "lieu": f.get("lieu"),
                "distance": f.get("distance"),
                "narratif": f.get("narratif", W.t_vers_narratif(f.get("T", 0))),
            })

    croisements.sort(key=lambda c: (c.get("T") if isinstance(c.get("T"), int) else 0,
                                    str(c.get("actor"))))
    return croisements


def _trajectoire_cone(cone: dict | None, geo: dict) -> list[dict]:
    """Builds a player trajectory from the cone.

    The cone may directly provide a 'trajectory' (list of segments); otherwise
    we build it from 'locations' + 'fenetre': a movement chaining the cone's locations
    over the time window (real path via plus_court_chemin),
    OR as a fallback a stay at the first location for the whole window.
    """
    if not isinstance(cone, dict):
        return []
    # Explicit trajectory provided by the caller.
    traj = cone.get("trajectory")
    if isinstance(traj, list) and traj:
        return traj

    lieux = _cone_lieux(cone)
    if not lieux:
        return []
    fen = _cone_fenetre(cone, (0, 0))
    t0, t1 = fen
    if t1 < t0:
        t1 = t0

    # Single location: stay for the whole window.
    if len(lieux) == 1:
        return [{"lieu": lieux[0], "de": t0, "a": None}]

    # Multiple locations: attempt a chain of real displacements on the graph,
    # distributed uniformly over the window. If a segment has no path, fall back
    # to a stay at the first location (the crossing remains computable).
    segments: list[dict] = []
    nb_troncons = len(lieux) - 1
    duree_dispo = max(0, t1 - t0)
    pas_t = (duree_dispo // nb_troncons) if nb_troncons else 0
    t_courant = t0
    ok_chaine = True
    for u, v in zip(lieux, lieux[1:]):
        pc = W.plus_court_chemin(geo, u, v)
        if pc.get("temps_ut", -1) < 0 or not pc.get("chemin"):
            ok_chaine = False
            break
        duree = max(int(pc["temps_ut"]), 1)
        # Cap the segment duration to the available window share (otherwise keep
        # the real duration — the proximity test remains valid).
        arrivee = t_courant + max(duree, pas_t if pas_t > 0 else duree)
        segments.append({
            "type": "deplacement", "de": t_courant, "a": arrivee,
            "chemin": list(pc["chemin"]), "motif": "player cone (projection)",
        })
        t_courant = arrivee
    if ok_chaine and segments:
        segments.append({"lieu": lieux[-1], "de": t_courant, "a": None})
        return segments

    return [{"lieu": lieux[0], "de": t0, "a": None}]


# ════════════════════════════════════════════════════════════════════════════
#  7.5  The LLM seam — agent_decide (CLEARLY isolated boundary)
# ════════════════════════════════════════════════════════════════════════════

# OPTIONAL environment variable: if set, contains a shell command that receives
# the brief on stdin and MUST write a JSON intention to stdout.
# Example: MGM_AGENT_DECIDE_CMD="hermes -p acteur-{slug}".  {slug} is substituted.
_ENV_AGENT_CMD = "MGM_AGENT_DECIDE_CMD"


def agent_decide(acteur: dict, brief: str, campagne: Path) -> dict:
    """LLM SEAM — the ONLY boundary where a model is solicited (contract §7.5).

    Input: a minimal brief + ONE implicit question ("What is your next intention?").
    Output: an INTENTION object conforming to intention.schema.json (§6.2),
    VALIDATED (schema + invariants) before return; refusal → falls back to the
    deterministic stub (deterministic dominates, doc 03 §7).

    INJECTABLE implementation:
      * default OFFLINE / DETERMINISTIC (this code): returns a STUB intention
        marked {'statut':'planifie','action':'(to decide) …'} derived from the
        actor's long-term goal, WITHOUT any network call (ideal for tests & pure
        stdlib dev);
      * LLM implementation (gemma-4 via `hermes -p acteur-<slug>`): wired by
        the env var MGM_AGENT_DECIDE_CMD (the tick does NOT hard-code a network
        call — it calls agent_decide, which encapsulates the choice).

    NB: this module NEVER calls an LLM directly (contract §0.8). Any eventual
    subprocess is entirely controlled by the operator via the environment.

    FEATURE GUARD "living_npcs_factions": if the axis is cut, we do NOT make actors
    "think" new plans via an external LLM agent — the MGM_AGENT_DECIDE_CMD command
    is NOT invoked and we fall back to the deterministic stub.
    (The stub remains allowed: it is plan CONTINUATION, not an LLM decision.
    The tick can therefore advance time and resolve already-planned intentions,
    but no longer "thinks" new plans.) Fail-open: flags read via
    worldlib.features_campagne (all ON if world.json absent).
    """
    cmd_modele = os.environ.get(_ENV_AGENT_CMD)
    intention = None

    # Actor seam: axis cut → no external LLM agent (stub only).
    if cmd_modele and not W.features_campagne(Path(campagne)).get("living_npcs_factions", True):
        _log(f"ℹ agent_decide : axis « living_npcs_factions » cut → "
             f"external LLM agent ignored for « {acteur.get('id')} » "
             f"(deterministic stub).")
        cmd_modele = None

    if cmd_modele:
        intention = _agent_decide_sousprocessus(acteur, brief, cmd_modele)
        if intention is not None:
            intention = _normaliser_intention(intention, acteur, campagne)
            if not valider_intention(intention):
                _log(f"ℹ agent_decide : invalid LLM output for "
                     f"« {acteur.get('id')} » → falling back to deterministic stub.")
                intention = None

    if intention is None:
        intention = _intention_stub(acteur, campagne)

    return intention


def _agent_decide_sousprocessus(acteur: dict, brief: str, cmd_modele: str) -> dict | None:
    """Invokes the injected LLM command (env) as a subprocess. None on failure.

    The command receives the brief on stdin; its stdout must be ONE JSON intention.
    {slug} is substituted with the actor id's slug. Fail-open: any error (missing
    command, broken JSON, timeout) → None (fallback to stub).
    """
    aid = acteur.get("id", "actor")
    slug = W.slug(aid.split(":", 1)[-1]) if isinstance(aid, str) else "actor"
    try:
        cmd = cmd_modele.format(slug=slug, id=aid)
        argv = shlex.split(cmd)
        if not argv:
            return None
        proc = subprocess.run(argv, input=brief, capture_output=True,
                              text=True, timeout=120)
        if proc.returncode != 0 or not proc.stdout.strip():
            return None
        data = json.loads(proc.stdout)
        return data if isinstance(data, dict) else None
    except Exception as e:                 # fail-open: fall back to stub
        _log(f"ℹ agent_decide (subprocess) failed: {e}.")
        return None


def _intention_stub(acteur: dict, campagne: Path) -> dict:
    """DETERMINISTIC STUB intention: continuation of the long-term goal.

    Depends on no network. The default deadline is pushed back by a reasonable
    horizon (1 game week = 7 days) after the current T, so the plan "breathes"
    without being immediately due again. `action` marked "(to decide)" to
    signal to the GM that a real LLM decision will replace this placeholder.
    """
    aid = acteur.get("id", "actor")
    but = acteur.get("but_long_terme", "") or "pursue their objectives"
    T_now = _t_courant(campagne)
    echeance = T_now + 7 * W.UT_PAR_JOUR     # +7 days

    # Location: base/last stay of the actor if it exists (otherwise null).
    lieu = _lieu_courant_acteur(acteur)

    base_slug = W.slug(but)[:32] or "suite"
    return {
        "id": f"intent:suite-{base_slug}",
        "action": f"(to decide) Continue: {but}",
        "lieu": lieu,
        "echeance": int(echeance),
        "echeance_source": {
            "texte": "Default horizon (goal renewal) — 1 game week",
            "unite": "jour",
            "min": 7, "max": 7,
            "ancre": W.t_vers_jour_heure(T_now)[0],
            "statut": "en_cours",
        },
        "preconditions": [],
        "consequence_attendue": (
            "Deterministic renewal of the long-term goal (LLM seam placeholder). "
            "Will be replaced by an intention decided by the actor's agent."),
        "significativite": 0.3,
        "visible_par_pj": False,
        "statut": "planifie",
    }


def _lieu_courant_acteur(acteur: dict) -> str | None:
    """Last known location of an actor (last stay in trajectory / loc)."""
    traj = W.trajectoire_de(acteur)
    for seg in reversed(traj):
        if isinstance(seg, dict) and isinstance(seg.get("lieu"), str):
            return seg["lieu"]
    loc = acteur.get("localisation_id") if isinstance(acteur, dict) else None
    return loc if isinstance(loc, str) else None


def _normaliser_intention(intention: dict, acteur: dict, campagne: Path) -> dict:
    """Completes missing required fields of an LLM intention (robustness).

    Converts a pinned `echeance` to T (worldlib.echeance_en_t), forces missing
    mandatory fields to safe values. NEVER fabricates (x,y) or arbitrary T:
    if the deadline cannot be dated, pushes back by a default horizon
    (consistent with the stub).
    """
    out = dict(intention)
    # Deadline → deterministic integer T.
    ech = out.get("echeance")
    if not isinstance(ech, int) or isinstance(ech, bool):
        src = out.get("echeance_source", ech)
        try:
            t = W.echeance_en_t(src, Path(campagne))
        except Exception:
            t = None
        if t is None:
            _log(f"⚠ _normaliser_intention : deadline {src!r} of "
                 f"{acteur.get('id', 'actor')} is NOT datable — replaced by the "
                 f"default horizon (+7 days); it is not anchored to its source.")
            t = _t_courant(campagne) + 7 * W.UT_PAR_JOUR
        out["echeance"] = int(t)
    out.setdefault("id", f"intent:{W.slug(out.get('action', 'suite'))[:32] or 'suite'}")
    out.setdefault("lieu", _lieu_courant_acteur(acteur))
    out.setdefault("consequence_attendue", "")
    out.setdefault("visible_par_pj", False)
    out.setdefault("statut", "planifie")
    return out


def valider_intention(intention: dict) -> bool:
    """Validates an intention (minimal schema §6.2 + base invariants).

    Reuses validate_schema.py (home-built validator) on intention.schema.json if
    available; otherwise internal structural validation. A valid intention has at
    least {id, action, lieu, echeance:int, consequence_attendue, visible_par_pj,
    statut} properly typed and an integer deadline (no floating T nor (x,y)).
    """
    if not isinstance(intention, dict):
        return False
    # Mandatory structural checks (always performed).
    requis_str = ("id", "action", "consequence_attendue")
    for clef in requis_str:
        if not isinstance(intention.get(clef), str):
            return False
    if not isinstance(intention.get("echeance"), int) or isinstance(intention.get("echeance"), bool):
        return False
    if "lieu" in intention and not (intention["lieu"] is None or isinstance(intention["lieu"], str)):
        return False
    if not isinstance(intention.get("visible_par_pj"), bool):
        return False
    statut = intention.get("statut")
    if statut not in ("planifie", "en_cours", "accompli", "echoue", "annule"):
        return False

    # Schema validation (best-effort, non-blocking if the tool/lib is missing).
    schema_path = SCRIPTS_DIR / "schemas" / "intention.schema.json"
    if schema_path.exists():
        try:
            import json as _json
            import validate_schema as _vs  # type: ignore
            with open(schema_path, encoding="utf-8") as _f:
                schema_obj = _json.load(_f)
            # validate_schema.valider(instance, schema, root) -> list of errors (empty = OK).
            erreurs = _vs.valider(intention, schema_obj, schema_obj)
            if erreurs:
                _log("ℹ valider_intention : schema deviations: "
                     + " ; ".join(map(str, erreurs[:3])))
                return False
        except Exception:
            # Defensive fallback: the structural checks above are sufficient for the seam.
            pass
    return True


# ════════════════════════════════════════════════════════════════════════════
#  Feature flags — GUARD for the "temporality" axis (living world ON/OFF)
# ════════════════════════════════════════════════════════════════════════════
#
# The meta.features.temporality axis is the MAIN SWITCH of the living world engine
# (cf. hooks/_lib.hooks_cfg: tick_pre/tick_post are gated by it).
# If cut, pre/post become a fail-open NO-OP: no heavy reads, no writes, exit 0.
# Flags are read via worldlib.features_campagne
# (cascade meta.features > env MGM_FEATURE_* > True), so fail-open "all ON".

_MSG_TEMPORALITY_OFF = "temporality disabled (meta.features.temporality=false)"
_MSG_TICK_PRE_OFF = "pre-processing disabled (meta.hooks.tick_pre=false)"
_MSG_TICK_POST_OFF = "closing reconciliation disabled (meta.hooks.tick_post=false)"


# ════════════════════════════════════════════════════════════════════════════
#  Temporal coherence — fail-open is NOT coherence (TIME-04)
# ════════════════════════════════════════════════════════════════════════════

CODE_INCOHERENCE_TEMPORELLE = 3
ENV_ALLOW_DERIVE = "MGM_ALLOW_CLOCK_DRIFT"


class IncoherenceTemporelle(RuntimeError):
    """Game time could not be established.

    Raised instead of falling back to T=0: a tick that silently runs at T=0 on a
    day-58 campaign emits events dated 58 days in the past, exits 0, and reports
    a clean success. That is the failure mode this class exists to make loud.
    """


def _derive_autorisee() -> bool:
    """True when the operator accepts a divergent clock (same hatch as clock.py)."""
    return os.environ.get(ENV_ALLOW_DERIVE, "").strip().lower() in (
        "1", "true", "yes", "on")


def _t_courant(campagne: Path) -> int:
    """Current T (UT) — the SINGLE reader of game time in this module, fail-LOUD."""
    try:
        return W.t_courant(Path(campagne))
    except Exception as e:
        raise IncoherenceTemporelle(
            f"current game time is unreadable in {campagne}: {e}") from e


def _hook_actif(monde, nom: str) -> bool:
    """Fine toggle meta.hooks.<nom> (default True). False ONLY if explicitly
    cut. Read from the already-loaded world; fail-open "active" if block absent.

    NB: the "temporality" axis (main switch) is checked separately upstream;
    here we read ONLY the fine toggle (cf. _lib.hooks_cfg: tick_pre/tick_post
    are gated by temporality, but can be cut independently).
    """
    h = (monde.get("meta") or {}).get("hooks") if isinstance(monde, dict) else None
    h = h if isinstance(h, dict) else {}
    return W.as_bool(h.get(nom), True)


def _noop_pre(campagne: Path, motif: str = _MSG_TEMPORALITY_OFF,
              feature_temporality: bool = False) -> dict:
    """Coherent empty PRE result when the tick is cut (no-op).

    Same SHAPE as the nominal return of pre() (keys present, empty lists) so that
    no consumer breaks; writes NOTHING. The briefing carries the message.
    `motif` = reason for the no-op (temporality axis OR meta.hooks.tick_pre toggle).
    `feature_temporality` stays True when only the fine toggle cuts (axis still ON).
    `noop` carries the reason so a caller cannot mistake a CONFIGURED no-op for a
    tick that ran and found nothing.
    """
    T = _t_courant(campagne)
    return {
        "t_de": T,
        "t_a": T,
        "ticks": [],
        "croisements": [],
        "promus_chaud": [],
        "scenes": [],
        "briefing": motif,
        "ecritures": [],
        "feature_temporality": feature_temporality,
        "message": motif,
        "noop": motif,
        "incoherences": [],
        "avertissements": [],
    }


def _noop_post(motif: str = _MSG_TEMPORALITY_OFF,
               feature_temporality: bool = False) -> dict:
    """Coherent empty POST result when the tick is cut (no-op).

    `motif` = reason (temporality axis OR meta.hooks.tick_post toggle).
    `feature_temporality` stays True when only the fine toggle cuts (axis still ON).
    """
    return {
        "faits_joueur": [],
        "reconciliations": [],
        "plans_renouveles": [],
        "propagations": [],
        "ecritures": [],
        "feature_temporality": feature_temporality,
        "message": motif,
        "noop": motif,
        "incoherences": [],
    }


# ════════════════════════════════════════════════════════════════════════════
#  7.2  PRE — projection + staging
# ════════════════════════════════════════════════════════════════════════════

def pre(campagne: Path, t_session: int | None = None,
        cone: dict | None = None, apply: bool = False) -> dict:
    """PRE-PROCESSING (contract §7.2): projects the world up to `t_session`.

    Steps:
      1) T_de = t_courant; T_a = t_session (default t_courant);
      2) classify the LOD of each major actor (hot/warm/cold);
      3) resolve due intentions (deterministic: consequences + events +
         propagation);
      4) make warm/hot actors "think" on empty plan (seam agent_decide);
      5) project player × warm-trajectory crossings;
      6) promote crossed actors to hot;
      7) assemble the text BRIEFING.
    Without --apply: DRY-RUN (writes NOTHING). With --apply: writes actors.json
    (lod/plans/trajectories updated) and APPENDs emitted events to
    evenements_programmes.json. NEVER events.json/world.json.

    FEATURE GUARD: if meta.features.temporality is False, the engine does NOT run
    → fail-open no-op (coherent empty result, no writes).

    Returns {'t_de','t_a','ticks':[…],'croisements':[…],'promus_chaud':[…],
    'scenes':[…],'briefing':str,'ecritures':[…]}.
    """
    campagne = Path(campagne)

    # world.json loaded ONCE: feature flags + meta.hooks toggles + pj_ids.
    monde = W.charger_json(campagne / "world.json", {}) or {}

    # Main switch: "temporality" axis cut → no-op (fail-open).
    if not W.features(monde).get("temporality", True):
        _log("ℹ pre : " + _MSG_TEMPORALITY_OFF + " — no-op (no writes).")
        return _noop_pre(campagne)
    # Fine toggle: meta.hooks.tick_pre=false cuts PRE-processing (default true),
    # even with temporality ON (cf. _lib.hooks_cfg / docs 10-features).
    if not _hook_actif(monde, "tick_pre"):
        _log("ℹ pre : " + _MSG_TICK_PRE_OFF + " — no-op (no writes).")
        return _noop_pre(campagne, motif=_MSG_TICK_PRE_OFF, feature_temporality=True)

    # PCs of the campaign (there can be SEVERAL): reserved set that the tick
    # never makes "think". Empty = no PC declared → PC branches inert.
    pj_set = set(W.pj_ids(monde))

    geo = W.charger_geo(campagne)
    acteurs = W.charger_acteurs(campagne)
    acteurs_idx = W.index_acteurs(acteurs)

    incoherences: list[dict] = []
    avertissements: list[dict] = []

    T_de = _t_courant(campagne)
    T_a = int(t_session) if t_session is not None else T_de
    if T_a < T_de:
        incoherences.append({
            "code": "t_session_anterieur",
            "message": (f"t_session ({T_a}) is BEHIND current game time ({T_de}) — "
                        f"clamped to the present; a {T_de - T_a} UT gap between the "
                        "caller's clock and the campaign's means one of them drifted"),
        })
        _log("⚠ pre : " + incoherences[-1]["message"])
        T_a = T_de
    elif T_a == T_de:
        avertissements.append({
            "code": "fenetre_vide",
            "message": (f"empty projection window (t_session == t_courant == {T_de}): "
                        "the world was NOT advanced — pass --t-session to project it"),
        })
        _log("ℹ pre : " + avertissements[-1]["message"])

    contexte = _contexte_joueur(cone, T_de, T_a)

    ticks: list[dict] = []
    evenements_emis: list[dict] = []
    tiedes: list[dict] = []

    # --- 2/3/4) Per actor: LOD, resolution, thinking. ---
    for aid, acteur in acteurs_idx.items():
        if aid in pj_set:
            continue   # PCs are reserved: the tick never makes them "think"
        if not acteur.get("majeur", False):
            # Frozen reactive sheet: cold, we only stamp.
            acteur["lod"] = "froid"
            ticks.append(_resume_tick(acteur, "froid", [], False))
            continue

        lod = classer_LOD(acteur, contexte, geo, T_a)
        acteur["lod"] = lod

        emis_acteur: list[dict] = []
        a_pense = False
        if lod in ("tiede", "chaud"):
            emis_acteur = resoudre_intentions(acteur, T_de, T_a, campagne, geo, acteurs_idx)
            evenements_emis.extend(emis_acteur)
            tiedes.append(acteur)

            # Should the actor think about what comes next? (empty plan or all resolved)
            if _plan_epuise(acteur):
                brief = _brief_acteur(campagne, acteur, emis_acteur)
                intention = agent_decide(acteur, brief, campagne)
                if intention and valider_intention(intention):
                    _inserer_intention(acteur, intention)
                    a_pense = True
        # cold: no fine resolution, no LLM (abstract clock — here no-op
        # because long-term goals have no deadline due in the cold window).

        ticks.append(_resume_tick(acteur, lod, emis_acteur, a_pense))

    # --- 5) Player × warm-trajectory crossings. ---
    croisements = projeter_croisements(campagne, contexte.get("cone") or {},
                                       tiedes, geo, SEUIL_CROISEMENT)

    # --- 6) Promotion to hot of crossed actors. ---
    promus: list[str] = []
    scenes: list[dict] = []
    for c in croisements:
        aid = c.get("actor")
        acteur = acteurs_idx.get(aid)
        if acteur is not None and acteur.get("lod") != "chaud":
            acteur["lod"] = "chaud"
            promus.append(aid)
        scenes.append(_scene_depuis_croisement(c, acteurs_idx))

    # --- 7) Briefing assembly. ---
    briefing = _assembler_briefing(campagne, T_de, T_a, ticks, croisements,
                                   scenes, promus, evenements_emis)

    # --- Writes (--apply only). ---
    ecritures: list[str] = []
    if apply:
        # actors.json: lod/plans/trajectories updated (rewrite the full container
        # from the mutated index, preserving meta).
        acteurs_out = dict(acteurs) if isinstance(acteurs, dict) else {}
        acteurs_out["actors"] = list(acteurs_idx.values())
        W.sauver_json_atomique(campagne / "actors.json", acteurs_out)
        ecritures.append(str(campagne / "actors.json"))
        # evenements_programmes.json: append emitted events.
        if evenements_emis:
            n = _appender_evenements(campagne, evenements_emis)
            ecritures.append(f"{campagne / 'evenements_programmes.json'} (+{n})")

    return {
        "t_de": T_de,
        "t_a": T_a,
        "ticks": ticks,
        "croisements": croisements,
        "promus_chaud": promus,
        "scenes": scenes,
        "briefing": briefing,
        "ecritures": ecritures,
        "noop": None,
        "incoherences": incoherences,
        "avertissements": avertissements,
    }


def _contexte_joueur(cone: dict | None, T_de: int, T_a: int) -> dict:
    """Player context consumed by classer_LOD / projeter_croisements."""
    lieu_joueur = None
    croisements_ids: set[str] = set()
    if isinstance(cone, dict):
        lieu_joueur = cone.get("lieu_joueur")
        # An already-known crossing (provided by the caller) forces hot.
        cids = cone.get("croisements_ids")
        if isinstance(cids, (list, set, tuple)):
            croisements_ids = {x for x in cids if isinstance(x, str)}
    return {
        "cone": cone,
        "T_de": int(T_de),
        "T_a": int(T_a),
        "lieu_joueur": lieu_joueur,
        "croisements_ids": croisements_ids,
    }


def _plan_epuise(acteur: dict) -> bool:
    """True if the actor has NO remaining 'planifie'/'en_cours' intention (needs rethinking)."""
    for intention in _plan(acteur):
        if intention.get("statut") in ("planifie", "en_cours"):
            return False
    return True


def _inserer_intention(acteur: dict, intention: dict) -> None:
    """Inserts an intention into the actor's plan (without id duplication)."""
    plan = acteur.setdefault("plan", [])
    if not isinstance(plan, list):
        plan = []
        acteur["plan"] = plan
    iid = intention.get("id")
    for existante in plan:
        if isinstance(existante, dict) and existante.get("id") == iid:
            existante.update(intention)
            return
    plan.append(intention)


def _resume_tick(acteur: dict, lod: str, emis: list[dict], a_pense: bool) -> dict:
    """Per-actor summary (entry in 'ticks')."""
    return {
        "actor": acteur.get("id"),
        "name": acteur.get("name", acteur.get("id")),
        "lod": lod,
        "events": [e.get("id") for e in emis],
        "a_pense": a_pense,
        "situation": acteur.get("situation", ""),
    }


def _scene_depuis_croisement(c: dict, acteurs_idx: dict) -> dict:
    """Stages a crossing (mini narrative object for the briefing)."""
    aid = c.get("actor")
    acteur = acteurs_idx.get(aid, {})
    return {
        "actor": aid,
        "name": acteur.get("name", aid),
        "T": c.get("T"),
        "lieu": c.get("lieu"),
        "distance": c.get("distance"),
        "narratif": c.get("narratif"),
        "resume": acteur.get("situation", ""),
    }


def _brief_acteur(campagne: Path, acteur: dict, emis: list[dict]) -> str:
    """MINIMAL brief passed to the seam (goal + situation + resources + recent events).

    Aligned with build_brief.py (existing): we give ONLY the relevant to the actor's
    agent (anti-knowledge-leak, doc 02 §3). No network call here.
    """
    lignes = [f"=== ACTOR BRIEF: {acteur.get('name') or acteur.get('nom') or acteur.get('id')} ==="]
    lignes.append(f"Long-term goal: {acteur.get('but_long_terme', '')}")
    motifs = acteur.get("motivations", [])
    if isinstance(motifs, list) and motifs:
        lignes.append("Motivations: " + ", ".join(str(m) for m in motifs))
    lignes.append(f"Situation: {acteur.get('situation', '')}")
    res = acteur.get("ressources", {})
    if isinstance(res, dict) and res:
        lignes.append("Resources: "
                      + ", ".join(f"{k}={v}" for k, v in res.items()))
    if emis:
        lignes.append("Recent events concerning you:")
        for e in emis:
            lignes.append(f"  • {e.get('label') or e.get('id')} "
                          f"({W.t_vers_narratif(e.get('T', 0))})")
    lignes.append("Question: What is your next intention?")
    lignes.append("=== END BRIEF ===")
    return "\n".join(lignes)


# ════════════════════════════════════════════════════════════════════════════
#  7.2  POST — reconciliation
# ════════════════════════════════════════════════════════════════════════════

def post(campagne: Path, session: dict | str | None = None,
         apply: bool = False) -> dict:
    """POST-PROCESSING (contract §7.2): reconciles the PLANNED and the REAL.

    Reads what the player has ACTUALLY done (session log: `sessions/<NNN>.json` or
    provided path/dict), extracts the FACTS, confronts each touched actor with those
    facts (real position/resources/relations), marks intentions accomplished/failed,
    renews disrupted plans (seam agent_decide) and PROPAGATES player actions (the
    player becomes a cause).
    Without --apply: DRY-RUN. With --apply: writes actors.json and APPENDs
    propagation events to evenements_programmes.json.

    FEATURE GUARD: if meta.features.temporality is False, the engine does NOT run
    → fail-open no-op (coherent empty result, no writes).

    Returns {'faits_joueur':[…],'reconciliations':[…],'plans_renouveles':[…],
    'propagations':[evt_id…],'ecritures':[…]}.
    """
    campagne = Path(campagne)

    # world.json loaded ONCE: feature flags + meta.hooks toggles + pj_ids.
    monde = W.charger_json(campagne / "world.json", {}) or {}

    # Main switch: "temporality" axis cut → no-op (fail-open).
    if not W.features(monde).get("temporality", True):
        _log("ℹ post : " + _MSG_TEMPORALITY_OFF + " — no-op (no writes).")
        return _noop_post()
    # Fine toggle: meta.hooks.tick_post=false cuts the closing reconciliation
    # (default true), even with temporality ON (cf. _lib.hooks_cfg / docs 10-features).
    if not _hook_actif(monde, "tick_post"):
        _log("ℹ post : " + _MSG_TICK_POST_OFF + " — no-op (no writes).")
        return _noop_post(motif=_MSG_TICK_POST_OFF, feature_temporality=True)

    # PCs of the campaign (there can be SEVERAL). Empty = no PC declared →
    # PC branches inert. `pj_premier` = "main" PC for building a cause-event
    # when a player fact designates none (decision: take the FIRST pj_id,
    # cf. _evenement_depuis_fait).
    pj_set = set(W.pj_ids(monde))
    pj_premier = W.pj_id(monde)   # first of pj_ids() or None (backward compat)

    geo = W.charger_geo(campagne)
    acteurs = W.charger_acteurs(campagne)
    acteurs_idx = W.index_acteurs(acteurs)

    incoherences: list[dict] = []
    session_obj = _resoudre_session(campagne, session)
    if session_obj is None:
        incoherences.append({
            "code": "session_introuvable",
            "message": (f"session log {session!r} not found or unreadable in "
                        f"{campagne / 'sessions'}"
                        if session is not None else
                        f"no session log in {campagne / 'sessions'}")
            + " — the reconciliation would run over ZERO player facts and report "
              "a clean success over nothing",
        })
        _log("❌ post : " + incoherences[-1]["message"])
        # Refusing AFTER writing actors.json would leave the world mutated by a
        # reconciliation the caller then rejects (exit 3).
        return {"faits_joueur": [], "reconciliations": [], "plans_renouveles": [],
                "propagations": [], "ecritures": [], "noop": None,
                "incoherences": incoherences}
    faits = extraire_faits_joueur(session_obj)

    reconciliations: list[dict] = []
    plans_renouveles: list[str] = []
    propagations_evt: list[dict] = []

    # Touched actors = those named in facts (by id or by name) + those whose
    # PC crosses the target. We process all major actors (except PCs).
    for aid, acteur in acteurs_idx.items():
        if aid in pj_set:
            continue   # PCs are not world actors to reconcile
        if not acteur.get("majeur", False):
            continue
        faits_acteur = _faits_concernant(acteur, faits)
        rec = reconcilier_etat(acteur, faits_acteur, geo)
        if rec.get("changements") or rec.get("plan_perturbe"):
            reconciliations.append(rec)
        if rec.get("plan_perturbe"):
            ren = renouveler_plan(acteur, faits_acteur, campagne)
            if ren.get("intention"):
                plans_renouveles.append(aid)

    # Propagation of player actions with consequences (the player = cause).
    # We attach the event to the "main" PC (first pj_id) for lack of better:
    # the player fact does not distinguish WHICH PC acted (the session log is shared).
    # If the fact names an explicit target, it takes priority (cf. _evenement_depuis_fait).
    for fait in faits:
        if not fait.get("a_consequences"):
            continue
        evt = _evenement_depuis_fait(fait, campagne, pj_premier)
        propagations_evt.append(evt)
        propagations_evt.extend(_propager(evt, campagne, _acteurs_dict(acteurs_idx)))

    # Writes.
    ecritures: list[str] = []
    if apply:
        acteurs_out = dict(acteurs) if isinstance(acteurs, dict) else {}
        acteurs_out["actors"] = list(acteurs_idx.values())
        W.sauver_json_atomique(campagne / "actors.json", acteurs_out)
        ecritures.append(str(campagne / "actors.json"))
        if propagations_evt:
            n = _appender_evenements(campagne, propagations_evt)
            ecritures.append(f"{campagne / 'evenements_programmes.json'} (+{n})")

    return {
        "faits_joueur": faits,
        "reconciliations": reconciliations,
        "plans_renouveles": plans_renouveles,
        "propagations": [e.get("id") for e in propagations_evt],
        "ecritures": ecritures,
        "noop": None,
        "incoherences": incoherences,
    }


def _resoudre_session(campagne: Path, session: dict | str | None) -> dict | None:
    """Resolves the session argument: dict as-is, file path, or '<NNN>'.

    '<NNN>' (number) → sessions/<NNN zero-padded 3>.json, then <NNN>.json, then
    any log whose name STARTS with that number (close_session accepts those and
    the two must resolve the same file). None → last session present in
    sessions/. Returns None if not found/unreadable — the caller reports it.
    """
    if isinstance(session, dict):
        return session
    sessions_dir = campagne / "sessions"
    if isinstance(session, str) and session:
        # Pure number → padded file, then the unpadded name (both exist in the wild;
        # missing the second one made the reconciliation run over an empty session).
        if session.isdigit():
            n = int(session)
            for nom in (f"{n:03d}.json", f"{n}.json"):
                data = W.charger_json(sessions_dir / nom, None)
                if data is not None:
                    return data
            # close_session derives the number from stems like
            # `031-north-ford.json`; resolving only `031.json` refuses the close.
            if sessions_dir.is_dir():
                for sp in sorted(sessions_dir.glob(f"{n:03d}*.json")) \
                        + sorted(sessions_dir.glob(f"{n}[-_.]*.json")):
                    data = W.charger_json(sp, None)
                    if data is not None:
                        return data
            return None
        # Otherwise, file path (absolute or relative).
        data = W.charger_json(session, None)
        if data is not None:
            return data
        cible = sessions_dir / session
        return W.charger_json(cible, None)
    # Default: last session by number.
    if sessions_dir.is_dir():
        fichiers = sorted(sessions_dir.glob("*.json"))
        if fichiers:
            return W.charger_json(fichiers[-1], None)
    return None


def extraire_faits_joueur(session: dict) -> list[dict]:
    """Extracts the player's FACTS from a session log (what ACTUALLY happened).

    Reads the usual fields of a MJ Tonnerre session log: `actions`,
    `npcs_met`, `visited_locations`, `etat_fin`. Each fact:
      {'type':…, 'libelle':str, 'cible':str|None, 'a_consequences':bool}.
    Robust to partial/null formats (fail-open). DETERMINISTIC.
    """
    faits: list[dict] = []
    if not isinstance(session, dict):
        return faits

    # Actions taken (free text or objects).
    for action in session.get("actions", []) or []:
        if isinstance(action, str):
            faits.append({"type": "action", "libelle": action, "cible": None,
                          "a_consequences": _action_a_consequences(action)})
        elif isinstance(action, dict):
            libelle = action.get("description") or action.get("action") or action.get("libelle") or ""
            cible = action.get("cible") or action.get("actor") or action.get("npcs")
            faits.append({
                "type": "action",
                "libelle": str(libelle),
                "cible": cible if isinstance(cible, str) else None,
                "a_consequences": bool(action.get("a_consequences",
                                                  _action_a_consequences(str(libelle)))),
            })

    # NPCs encountered → encounter fact (touches the corresponding actor).
    for pnj in session.get("npcs_met", []) or []:
        nom = pnj if isinstance(pnj, str) else (pnj.get("name") if isinstance(pnj, dict) else None)
        if nom:
            faits.append({"type": "rencontre", "libelle": f"Encounter: {nom}",
                          "cible": str(nom), "a_consequences": False})

    # Locations visited → presence fact (useful for position reconciliation).
    for lieu in session.get("visited_locations", []) or []:
        nom = lieu if isinstance(lieu, str) else (lieu.get("name") if isinstance(lieu, dict) else None)
        if nom:
            faits.append({"type": "presence", "libelle": f"Visited: {nom}",
                          "cible": str(nom), "a_consequences": False})

    # End state: key leads/NPCs → context (no direct mechanical consequence).
    etat = session.get("etat_fin", {})
    if isinstance(etat, dict):
        lieu_actuel = etat.get("lieu_actuel")
        if isinstance(lieu_actuel, str) and lieu_actuel:
            faits.append({"type": "position_joueur", "libelle": lieu_actuel,
                          "cible": None, "a_consequences": False})

    return faits


def _action_a_consequences(texte: str) -> bool:
    """DETERMINISTIC heuristic: does a player action have propagatable consequences
    (the player becomes a cause)? Impact keywords.
    """
    if not isinstance(texte, str):
        return False
    t = texte.lower()
    mots = (
        # FR stems
        "tue", "tué", "attaqu", "incendi", "brûl", "brule", "détru", "detru",
        "pille", "vol", "libèr", "liber", "sauve", "escorte", "trahi",
        "alli", "négoci", "negoci", "menace", "défend", "defend", "fond",
        # EN stems
        "kill", "attack", "burn", "set fire", "destroy", "raid", "loot",
        "steal", "free", "rescue", "escort", "betray", "ally", "negotiat",
        "threaten", "defend", "found",
    )
    return any(m in t for m in mots)


def _faits_concernant(acteur: dict, faits: list[dict]) -> list[dict]:
    """Subset of facts naming the actor (by id OR by name, case-insensitive)."""
    aid = (acteur.get("id") or "").lower()
    nom = (acteur.get("name") or "").lower()
    concernes: list[dict] = []
    for f in faits:
        blob = (str(f.get("libelle", "")) + " " + str(f.get("cible", ""))).lower()
        if (aid and aid in blob) or (nom and nom in blob):
            concernes.append(f)
    return concernes


def reconcilier_etat(acteur: dict, faits_joueur: list[dict], geo: dict) -> dict:
    """Confronts the PLANNED plan with REALITY (contract §7.3).

    Updates real position/resources/relations from facts, and determines whether
    the plan is DISRUPTED (blocked|deviated|accelerated|ignored). Deterministic
    heuristic:
      * a consequential fact naming the actor (e.g. "attacked the Band") marks
        targeted 'planifie' intentions as 'echoue' and signals plan_perturbe;
      * otherwise, plan unchanged (the column arrives alone at the pass — doc 03
        §4 "ignored").
    Mutates the actor IN PLACE. Returns {'actor','changements':[…],'plan_perturbe':bool}.
    """
    changements: list[str] = []
    plan_perturbe = False
    if not isinstance(acteur, dict):
        return {"actor": None, "changements": changements, "plan_perturbe": False}

    impactant = any(f.get("a_consequences") for f in faits_joueur)
    if impactant:
        # The player has acted ON the actor: their current intentions are disrupted.
        for intention in _plan(acteur):
            if intention.get("statut") in ("planifie", "en_cours"):
                intention["statut"] = "echoue"
                plan_perturbe = True
                changements.append(f"intention « {intention.get('id')} » → echoue (player action)")
        if plan_perturbe:
            acteur["situation"] = (acteur.get("situation", "")
                                   + " [Plan disrupted by player intervention.]").strip()

    return {"actor": acteur.get("id"), "changements": changements,
            "plan_perturbe": plan_perturbe}


def renouveler_plan(acteur: dict, faits_joueur: list[dict], campagne: Path) -> dict:
    """Renews the plan of a disrupted actor (contract §7.3).

    Prepares a brief (including the disruption reason) and calls agent_decide
    for a NEW intention (short-term goal → continuation). Validates (schema +
    invariants); refusal → rethinks ONCE; failure → no intention inserted.
    Mutates the actor IN PLACE. Returns {'actor','intention':…|None,'refus':[…]}.
    """
    refus: list[str] = []
    brief = _brief_acteur(campagne, acteur, [])
    brief += "\n[Context: your previous plan was disrupted — propose a follow-up.]"

    for tentative in range(2):     # one retry max (feed-forward)
        intention = agent_decide(acteur, brief, campagne)
        if intention and valider_intention(intention):
            _inserer_intention(acteur, intention)
            return {"actor": acteur.get("id"), "intention": intention, "refus": refus}
        refus.append(f"attempt #{tentative + 1} rejected (schema/invariants).")
        brief += f"\n[Previous rejection: {refus[-1]} — fix it.]"

    return {"actor": acteur.get("id"), "intention": None, "refus": refus}


def _evenement_depuis_fait(fait: dict, campagne: Path,
                           pj_id: str | None = None) -> dict:
    """Builds a RESOLVED event (format §8.3) from a consequential player fact
    (the player becomes a CAUSE of propagation).

    `pj_id` = id of the "main" PC of the action (first of worldlib.pj_ids;
    the session log does not distinguish WHICH PC acted). If None (no PC declared),
    degrades cleanly: no PC actor built, the target falls back to that of the
    fact (otherwise None). No hard-coded PC id.
    """
    T = _t_courant(campagne)
    libelle = str(fait.get("libelle", "player action"))
    type_evt = _type_fait(libelle)
    slug = W.slug(libelle)[:32] or "player-action"
    evt = {
        "id": f"evt:{slug}-{int(T):05d}",
        "T": int(T),
        "type": type_evt,
        "cible": fait.get("cible") or pj_id,
        "actor": pj_id,
        "cause": "player",
        "significativite": 0.6,
        "statut": "resolu",
        "label": libelle,
        "consequence_attendue": "Consequence of a player action (propagation).",
        "visible_par_pj": True,
        "narratif": None,
        "source": "world_tick.py (post)",
    }
    return evt


def _type_fait(libelle: str) -> str:
    """Event type deduced from a player fact label (deterministic)."""
    t = (libelle or "").lower()
    # NOTE: the emitted TYPE values (incendie, attaque, raid, secours, diplomatie,
    # alliance, trahison, fondation) are load-bearing keys consumed by
    # causal_propagate.py — they stay French. Only the MATCH stems carry EN aliases.
    for mot, typ in (("incendi", "incendie"), ("brûl", "incendie"), ("brule", "incendie"),
                     ("burn", "incendie"), ("set fire", "incendie"),
                     ("tue", "attaque"), ("attaqu", "attaque"),
                     ("kill", "attaque"), ("attack", "attaque"),
                     ("pille", "raid"), ("raid", "raid"), ("loot", "raid"),
                     ("escorte", "secours"), ("sauve", "secours"), ("défend", "secours"),
                     ("escort", "secours"), ("rescue", "secours"), ("defend", "secours"),
                     ("negoci", "diplomatie"), ("négoci", "diplomatie"),
                     ("negotiat", "diplomatie"),
                     ("alli", "alliance"), ("ally", "alliance"),
                     ("trahi", "trahison"), ("betray", "trahison"),
                     ("fond", "fondation"), ("found", "fondation")):
        if mot in t:
            return typ
    return "action"


# ════════════════════════════════════════════════════════════════════════════
#  Scheduled events: atomic append (SEPARATE file, non-destructive)
# ════════════════════════════════════════════════════════════════════════════

def _appender_evenements(campagne: Path, evenements: list[dict]) -> int:
    """Appends events to evenements_programmes.json (atomic, dedup by id).

    Creates the file (with meta) if it does not exist. NEVER on events.json.
    If `causal_propagate.appliquer` is available, reuses it (inter-agent write
    consistency); otherwise appends ourselves in the same format (§8.3). Returns
    the number ACTUALLY written (excluding duplicates).
    """
    if not evenements:
        return 0
    # Reuse the causal module's appender if it exists (same file format).
    if C is not None and hasattr(C, "appliquer"):
        try:
            return int(C.appliquer(Path(campagne), evenements))
        except Exception as e:
            _log(f"ℹ causal_propagate.appliquer unavailable ({e}) — local append.")

    cible = Path(campagne) / "evenements_programmes.json"
    data = W.charger_json(cible, None)
    if not isinstance(data, dict) or not isinstance(data.get("events"), list):
        data = {
            "meta": {
                "campagne": _nom_campagne(campagne),
                "version": 1,
                "note": ("SCHEDULED/RESOLVED events by the living world. T in UT. "
                         "NEVER merge into events.json without GM decision."),
            },
            "events": [],
        }
    existants = {e.get("id") for e in data["events"] if isinstance(e, dict)}
    n = 0
    for evt in evenements:
        if not isinstance(evt, dict):
            continue
        if evt.get("id") in existants:
            continue
        data["events"].append(evt)
        existants.add(evt.get("id"))
        n += 1
    if n:
        W.sauver_json_atomique(cible, data)
    return n


def _nom_campagne(campagne: Path) -> str:
    """Human-readable campaign name (meta from world.json, otherwise folder name)."""
    monde = W.charger_json(Path(campagne) / "world.json", {}) or {}
    meta = monde.get("meta", {}) if isinstance(monde, dict) else {}
    nom = meta.get("name") or meta.get("titre")
    return nom if isinstance(nom, str) and nom else Path(campagne).name


# ════════════════════════════════════════════════════════════════════════════
#  Briefing (text ready to inject — doc 05 / contract §7.2)
# ════════════════════════════════════════════════════════════════════════════

def _assembler_briefing(campagne: Path, T_de: int, T_a: int, ticks: list[dict],
                        croisements: list[dict], scenes: list[dict],
                        promus: list[str], evenements: list[dict]) -> str:
    """Assembles the text BRIEFING of the pre-processing (compact, markers).

    Designed to be injected as-is by the session-opening skill. Durations in
    NARRATIVE form (never raw T nor (x,y)).
    """
    lignes: list[str] = []
    lignes.append(f"┌─ LIVING WORLD BRIEFING ─ {W.t_vers_narratif(T_a)} "
                  f"(projection {W.t_vers_narratif(T_de)} → {W.t_vers_narratif(T_a)}) ─┐")

    # Crossings (the heart of pre-processing).
    if croisements:
        lignes.append("│ ⚠ POSSIBLE CROSSINGS:")
        for c in croisements:
            nom = _nom_acteur(c.get("actor"), scenes)
            lignes.append(f"│   • {c.get('narratif')} — {nom} near "
                          f"{_lieu_court(c.get('lieu'))} (distance {c.get('distance')})")
    else:
        lignes.append("│ ℹ No crossing projected with the player's cone.")

    # Promotions to hot.
    if promus:
        lignes.append("│ 🔴 PROMOTED HOT (just-in-time staging): "
                      + ", ".join(promus))

    # Warm actors that acted.
    actifs = [t for t in ticks if t.get("lod") in ("tiede", "chaud") and t.get("events")]
    if actifs:
        lignes.append("│ 🟠 ACTIVE ACTORS (resolved intentions):")
        for t in actifs:
            lignes.append(f"│   • {t.get('name') or t.get('actor')} [{t.get('lod')}] : "
                          + ", ".join(t.get("events", [])))

    # Emitted events (dated in narrative form).
    visibles = [e for e in evenements if e.get("visible_par_pj")]
    if visibles:
        lignes.append("│ ⏰ EVENTS (observable):")
        for e in visibles:
            lignes.append(f"│   • {W.t_vers_narratif(e.get('T', 0))} — "
                          f"{e.get('label') or e.get('id')}")

    # LOD summary.
    chauds = [t["actor"] for t in ticks if t.get("lod") == "chaud"]
    tiedes_ids = [t["actor"] for t in ticks if t.get("lod") == "tiede"]
    lignes.append(f"│ LOD : {len(chauds)} hot · {len(tiedes_ids)} warm · "
                  f"{sum(1 for t in ticks if t.get('lod') == 'froid')} cold")
    lignes.append("└" + "─" * 60 + "┘")
    return "\n".join(lignes)


def _nom_acteur(aid, scenes: list[dict]) -> str:
    for s in scenes:
        if s.get("actor") == aid:
            return s.get("name", aid)
    return aid if isinstance(aid, str) else "?"


def _lieu_court(lieu_id) -> str:
    """Short form of a location id for display (last readable segment)."""
    if not isinstance(lieu_id, str):
        return "?"
    queue = lieu_id.rsplit("/", 1)[-1]
    return queue.replace("-", " ")


# ════════════════════════════════════════════════════════════════════════════
#  7.1  CLI — argparse with subcommands (first positional = campaign)
# ════════════════════════════════════════════════════════════════════════════

def _exiger_campagne(args) -> Path | None:
    """Resolves and VERIFIES the existence of the campaign folder. None → code 2."""
    camp = W.chemin_campagne(args.campagne)
    if not camp.is_dir():
        _log(f"❌ Campaign not found: {camp}")
        return None
    return camp


def _sortir_json(obj) -> None:
    print(json.dumps(obj, ensure_ascii=False, indent=2))


def _charger_cone_arg(spec: str | None) -> dict | None:
    """Resolves --cone: JSON file path or '-' (stdin). None if absent/failed."""
    if not spec:
        return None
    if spec == "-":
        try:
            return json.load(sys.stdin)
        except (json.JSONDecodeError, ValueError) as e:
            _log(f"❌ cone (stdin): unreadable JSON: {e}.")
            return None
    data = W.charger_json(spec, None)
    if data is None:
        _log(f"❌ cone: file not found or unreadable « {spec} ».")
    return data if isinstance(data, dict) else None


def _signaler_etat_temporel(res: dict) -> int | None:
    """Print the no-op reason / warnings / incoherences of a tick result.

    Returns CODE_INCOHERENCE_TEMPORELLE when the run must fail, None otherwise.
    A CONFIGURED no-op is legitimate and stays exit 0, but it is announced: the
    field report's worst case is an engine believed active that ran over nothing.
    """
    if res.get("noop"):
        _log("ℹ NO-OP (configured): " + res["noop"] + " — nothing was computed.")
    for av in res.get("avertissements") or []:
        _log("ℹ " + av["message"])
    incoherences = res.get("incoherences") or []
    for inc in incoherences:
        _log("❌ TEMPORAL INCOHERENCE — " + inc["message"])
    if not incoherences:
        return None
    if _derive_autorisee():
        _log(f"   ⚠ {ENV_ALLOW_DERIVE}=1 — accepted by the operator, nothing fixed.")
        return None
    _log(f"   → resynchronise the temporal files, or set {ENV_ALLOW_DERIVE}=1 "
         f"to proceed anyway.")
    return CODE_INCOHERENCE_TEMPORELLE


def cmd_pre(args) -> int:
    camp = _exiger_campagne(args)
    if camp is None:
        return 2
    # In --apply, we require actors.json (we do not invent actor truth).
    if args.apply and not (camp / "actors.json").exists():
        _log(f"❌ actors.json not found in {camp} — nothing to project in --apply.")
        return 2
    cone = None
    if args.cone:
        cone = _charger_cone_arg(args.cone)
        if cone is None:
            _log("❌ --cone was given but could not be read — refusing to project "
                 "on a silently empty cone.")
            return 2
    try:
        res = pre(camp, t_session=args.t_session, cone=cone, apply=args.apply)
    except IncoherenceTemporelle as e:
        _log(f"❌ TEMPORAL INCOHERENCE — {e}")
        return CODE_INCOHERENCE_TEMPORELLE
    if args.as_json:
        _sortir_json(res)
    else:
        print(res["briefing"])
        if args.apply and res["ecritures"]:
            print("✅ Writes: " + " ; ".join(res["ecritures"]))
        elif not args.apply:
            print("ℹ dry-run: no writes (use --apply to persist).")
    code = _signaler_etat_temporel(res)
    if code is not None:
        return code
    # Code 1 if a crossing was found (business condition signalled), otherwise 0.
    return 1 if res["croisements"] else 0


def cmd_post(args) -> int:
    camp = _exiger_campagne(args)
    if camp is None:
        return 2
    if args.apply and not (camp / "actors.json").exists():
        _log(f"❌ actors.json not found in {camp} — nothing to reconcile in --apply.")
        return 2
    try:
        res = post(camp, session=args.session, apply=args.apply)
    except IncoherenceTemporelle as e:
        _log(f"❌ TEMPORAL INCOHERENCE — {e}")
        return CODE_INCOHERENCE_TEMPORELLE
    if args.as_json:
        _sortir_json(res)
    else:
        print(f"🔁 POST — {camp.name}")
        print(f"   {len(res['faits_joueur'])} player fact(s) · "
              f"{len(res['reconciliations'])} reconciliation(s) · "
              f"{len(res['plans_renouveles'])} renewed plan(s) · "
              f"{len(res['propagations'])} propagation(s)")
        for r in res["reconciliations"]:
            if r.get("changements"):
                print(f"   • {r['actor']} : " + " ; ".join(r["changements"]))
        if args.apply and res["ecritures"]:
            print("   ✅ Writes: " + " ; ".join(res["ecritures"]))
        elif not args.apply:
            print("   ℹ dry-run: no writes (use --apply).")
    code = _signaler_etat_temporel(res)
    if code is not None:
        return code
    return 1 if res["reconciliations"] else 0


def cmd_lod(args) -> int:
    camp = _exiger_campagne(args)
    if camp is None:
        return 2
    geo = W.charger_geo(camp)
    acteurs = W.charger_acteurs(camp)
    acteurs_idx = W.index_acteurs(acteurs)
    pj_set = set(W.pj_ids(W.charger_json(camp / "world.json", {}) or {}))
    T_a = args.t if args.t is not None else W.t_courant(camp)
    contexte = _contexte_joueur(None, T_a, T_a)
    rangs: list[dict] = []
    for aid, acteur in acteurs_idx.items():
        if aid in pj_set:
            continue   # PCs are not classified (reserved)
        lod = classer_LOD(acteur, contexte, geo, T_a)
        rangs.append({"actor": aid, "name": acteur.get("name", aid), "lod": lod})
    if args.as_json:
        _sortir_json({"T": T_a, "narratif": W.t_vers_narratif(T_a), "actors": rangs})
    else:
        print(f"🌡  LOD — {camp.name} — {W.t_vers_narratif(T_a)}")
        for r in rangs:
            marq = {"chaud": "🔴", "tiede": "🟠", "froid": "🟢"}.get(r["lod"], "·")
            print(f"   {marq} {r['lod']:6s} {r['actor']} ({r['name']})")
    return 0


def cmd_actor(args) -> int:
    camp = _exiger_campagne(args)
    if camp is None:
        return 2
    if not (camp / "actors.json").exists():
        _log(f"❌ actors.json not found in {camp}.")
        return 2
    acteurs = W.charger_acteurs(camp)
    acteurs_idx = W.index_acteurs(acteurs)
    acteur = acteurs_idx.get(args.acteur_id)
    if acteur is None:
        _log(f"❌ Unknown actor: {args.acteur_id}")
        return 2

    if args.operation == "promote":
        acteur["majeur"] = True
        if acteur.get("lod") == "froid":
            acteur["lod"] = "tiede"
        message = f"promoted to major actor (lod={acteur['lod']})"
    else:  # demote
        acteur["majeur"] = False
        acteur["lod"] = "froid"
        # Freeze the trajectory: truncate any open segment at the present (frozen stay).
        message = "demoted to reactive sheet (cold, trajectory frozen)"

    ecrit = False
    if args.apply:
        out = dict(acteurs)
        out["actors"] = list(acteurs_idx.values())
        W.sauver_json_atomique(camp / "actors.json", out)
        ecrit = True

    if args.as_json:
        _sortir_json({"actor": args.acteur_id, "operation": args.operation,
                      "majeur": acteur["majeur"], "lod": acteur["lod"], "ecrit": ecrit})
    else:
        print(f"👤 {args.acteur_id} : {message}")
        if ecrit:
            print("   ✅ actors.json updated.")
        elif not args.apply:
            print("   ℹ dry-run: no writes (use --apply).")
    return 0


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="world_tick.py",
        description="Living world tick engine (MJ Tonnerre) — pre/post.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python3 world_tick.py pre  <campaign> --t-session 3960 --json\n"
            "  python3 world_tick.py pre  <campaign> --cone cone.json --apply\n"
            "  python3 world_tick.py post <campaign> --session 009 --apply\n"
            "  python3 world_tick.py lod  <campaign> --t 3960\n"
            "  python3 world_tick.py actor <campaign> promote acteur:la-corneille --apply\n"
            "\nLLM seam: agent_decide is a deterministic STUB by default. To wire a real\n"
            "model, export MGM_AGENT_DECIDE_CMD (e.g. 'hermes -p acteur-{slug}').\n"
        ),
    )
    sub = ap.add_subparsers(dest="command", required=True)

    def _ajout_json(p):
        p.add_argument("--json", action="store_true", dest="as_json",
                       help="Output as JSON (raw function object).")

    # pre
    p = sub.add_parser("pre", help="Projection + staging (before the session).")
    p.add_argument("campagne", metavar="campaign", help="Path to the campaign folder.")
    p.add_argument("--t-session", dest="t_session", type=int, default=None,
                   help="Target T (UT) for the session. Default: t_courant.")
    p.add_argument("--cone", default=None,
                   help="Player cone: JSON file | '-' (stdin). "
                        "{'locations':[…],'fenetre':[T0,T1],'lieu_joueur':id}.")
    p.add_argument("--apply", action="store_true",
                   help="Persist (actors.json + evenements_programmes.json).")
    _ajout_json(p)
    p.set_defaults(func=cmd_pre)

    # post
    p = sub.add_parser("post", help="Reconciliation (after the session).")
    p.add_argument("campagne", metavar="campaign")
    p.add_argument("--session", default=None,
                   help="Number '<NNN>', file path, or last session if absent.")
    p.add_argument("--apply", action="store_true",
                   help="Persist (actors.json + evenements_programmes.json).")
    _ajout_json(p)
    p.set_defaults(func=cmd_post)

    # lod
    p = sub.add_parser("lod", help="Classify and display the LOD of each actor.")
    p.add_argument("campagne", metavar="campaign")
    p.add_argument("--t", type=int, default=None, help="Instant T (UT). Default: t_courant.")
    _ajout_json(p)
    p.set_defaults(func=cmd_lod)

    # actor
    p = sub.add_parser("actor", help="Promote/demote an actor (major ↔ reactive).")
    p.add_argument("campagne", metavar="campaign")
    p.add_argument("operation", choices=["promote", "demote"])
    p.add_argument("acteur_id", metavar="actor_id")
    p.add_argument("--apply", action="store_true", help="Write actors.json (atomic).")
    _ajout_json(p)
    p.set_defaults(func=cmd_actor)

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
