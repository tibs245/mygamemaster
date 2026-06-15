#!/usr/bin/env python3
"""
worldlib.py — Shared library for the "living world" (MJ Tonnerre).

IMPORTABLE module with NO CLI (no `main()` run in pipeline). Provides the
low-level building blocks shared by geo_query / world_tick / causal_propagate /
scene_brief:

  * SAFE JSON load / save (fail-open on read, atomic on write);
  * time conversion T <-> day/hour (1 UT = 10 min, 144 UT = 1 day, T=0 at
    campaign creation); T is the ONLY simulation timeline, the player NEVER
    sees it (fuzzy narrative rendering);
  * spatial graph helpers with three layers: CONTAINMENT (parent), ADJACENCY
    (edges) and ANCHOR (x, y);
  * anchor MDS in PURE STDLIB (SMACOF / stress majorization, Guttman transform)
    deriving COARSE (x, y) coordinates from a travel-time matrix —
    these coordinates are used ONLY in code (radius, crossing, proximity sort)
    and are NEVER shown to the LLM;
  * trajectories (position = function of time) and their validation;
  * access to actors and the causal graph (relations);
  * conversion of "pinned" deadlines (clock.py format) to T.

Targets: Python 3.11, PURE STDLIB (no external dependencies — no pip / numpy
/ scipy). See contract `docs/monde-vivant/08-contrat-implementation.md` §3, §13,
§14: the public signatures below are FROZEN.

Cross-cutting conventions (contract §0):
  * source of truth = files; no state outside files;
  * NON-DESTRUCTIVE: this module never rewrites world.json / npcs.json /
    events.json (it only READS them); only explicit atomic writes by the
    caller (on geo.json / actors.json /
    evenements_programmes.json) go through `sauver_json_atomique`;
  * FAIL-OPEN at runtime: READ functions return a degraded default and a message
    on stderr rather than raising; writes may fail hard.
"""

from __future__ import annotations

import json
import math
import os
import re
import sys
import tempfile
import unicodedata
from pathlib import Path


# ════════════════════════════════════════════════════════════════════════════
# 3.1  Module constants (frozen)
# ════════════════════════════════════════════════════════════════════════════

UT_PAR_HEURE = 6          # 1 UT = 10 min  → 6 UT / hour
UT_PAR_JOUR = 144         # 144 UT = 1 day
MINUTES_PAR_UT = 10
HEURES_JOUR_MARCHE = 12   # 1 marching day = 12 h (travel governance)

# Recognized cardinal directions (edges) + unit vectors (plane: x→East, y→North).
DIRECTIONS = ("N", "NE", "E", "SE", "S", "SO", "O", "NO")
_SQ = math.sqrt(0.5)
_VECTEURS_DIR = {
    "N": (0.0, 1.0),
    "NE": (_SQ, _SQ),
    "E": (1.0, 0.0),
    "SE": (_SQ, -_SQ),
    "S": (0.0, -1.0),
    "SO": (-_SQ, -_SQ),
    "O": (-1.0, 0.0),
    "NO": (-_SQ, _SQ),
}


def _log(message: str) -> None:
    """Fail-open trace to stderr (never to stdout: does not pollute --json)."""
    print(message, file=sys.stderr)


# ════════════════════════════════════════════════════════════════════════════
# 3.2  Safe JSON load / save
# ════════════════════════════════════════════════════════════════════════════

def charger_json(chemin: str | Path, defaut=None):
    """Load a UTF-8 JSON file. Returns `defaut` (and logs to stderr) if absent/corrupt.

    NEVER raises (fail-open): safe inside the game loop. Any access or parsing
    error is swallowed and reported, and the `defaut` value is returned.
    """
    p = Path(chemin)
    try:
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        _log(f"ℹ JSON absent ({p}) — default value used.")
        return defaut
    except (OSError, json.JSONDecodeError, ValueError) as e:
        _log(f"❌ JSON unreadable ({p}) : {e} — default value used.")
        return defaut


def sauver_json_atomique(chemin: str | Path, donnees) -> None:
    """Write `donnees` to JSON ATOMICALLY.

    ensure_ascii=False, indent=2, trailing "\\n". tmp in the SAME directory → flush +
    os.fsync → os.replace (reuses the pattern from faction_slice.py). Raises OSError
    on write failure (this function runs OUTSIDE the game loop: fail-hard is assumed
    to never leave a half-written file).
    """
    p = Path(chemin)
    p.parent.mkdir(parents=True, exist_ok=True)
    texte = json.dumps(donnees, ensure_ascii=False, indent=2) + "\n"
    fd, tmp = tempfile.mkstemp(prefix=p.name + ".", suffix=".tmp", dir=str(p.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(texte)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, p)
    except BaseException:
        # Clean up the tmp file if anything failed before the replace.
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def chemin_campagne(arg: str) -> Path:
    """Resolve the campaign argument to an ABSOLUTE Path. Does NOT require existence here.

    (Existence checking is left to the CLI caller, which decides on exit code 2
    if needed.)
    """
    return Path(arg).expanduser().resolve()


def slug(texte: str) -> str:
    """Deterministic slugification (contract §2.1).

    NFKD → strip diacritics → lowercase → any character outside [a-z0-9]
    becomes '-' → squeeze '-' → strip '-'. Does NOT touch existing '/'
    (preserves the id hierarchy `type:path/sub-path`).

    Frozen examples:
      "Vieux Moulin"              → "vieux-moulin"
      "Poste n°6 — Limite Nord"   → "poste-n-6-limite-nord"
    """
    if not texte:
        return ""
    s = unicodedata.normalize("NFKD", str(texte))
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.lower()
    # Preserve '/' (level separators); everything else outside [a-z0-9]
    # becomes a '-'.
    morceaux = s.split("/")
    propres = []
    for m in morceaux:
        m = re.sub(r"[^a-z0-9]+", "-", m)
        m = m.strip("-")
        propres.append(m)
    return "/".join(propres)


# ════════════════════════════════════════════════════════════════════════════
# 3.2bis  Unified feature flags (meta.features)  — DUPLICATED from hooks/_lib.py
# ════════════════════════════════════════════════════════════════════════════
#
# ⚠ LOGIC INTENTIONALLY DUPLICATED from modules/.../hooks/_lib.py
# (features / as_bool / FEATURES). worldlib is a module WITH NO dependency on
# hooks (separate layers): we copy the contract rather than importing _lib.
# KEEP IN SYNC with _lib.py if axes or cascade logic evolve.
#
# Six main axes, ALL enabled by default. Cascade, from most specific to most general:
#     meta.features.<axe> (world.json)  >  env MGM_FEATURE_<AXE>  >  default True
# The world (world.json) has the final say; the env sets the instance default.
# FAIL-OPEN: an ON axis whose data is missing is a simple no-op, not an error;
# and an absent world.json → "all ON" (features_campagne).

FEATURES = ("traceability", "verbosity", "living_npcs_factions", "temporality", "images", "tts")


def as_bool(val, default: bool) -> bool:
    """Coerce a JSON bool / env string ('1','true','on','oui'…) → bool.

    `default` if None/unknown. Identical to hooks/_lib.as_bool (see warning
    above). Pure stdlib.
    """
    if isinstance(val, bool):
        return val
    if val is None:
        return default
    s = str(val).strip().lower()
    if s in ("1", "true", "yes", "on", "oui"):
        return True
    if s in ("0", "false", "no", "off", "non"):
        return False
    return default


def features(monde) -> dict:
    """Resolve the 5 feature flags. Cascade: meta.features.<axe> > env MGM_FEATURE_<AXE> > True.

    IDENTICAL behavior to hooks/_lib.features (duplicated logic, keep in sync).
    All enabled by default: a world without a meta.features block behaves as
    "all ON". `monde` non-dict or absent features block → all ON.
    """
    m = monde.get("meta") if isinstance(monde, dict) else None
    m = m if isinstance(m, dict) else {}
    f = m.get("features")
    f = f if isinstance(f, dict) else {}
    out = {}
    for axe in FEATURES:
        env_default = as_bool(os.environ.get("MGM_FEATURE_" + axe.upper()), True)
        out[axe] = as_bool(f.get(axe), env_default)
    return out


def features_campagne(campagne: str | Path) -> dict:
    """Load world.json from a campaign and return the dict of 6 feature flags.

    FAIL-OPEN: absent/unreadable world.json → charger_json returns {} → all ON
    (each axis falls back to its env/True default). Used as tick entry point.
    """
    monde = charger_json(Path(campagne) / "world.json", {}) or {}
    return features(monde)


def pj_ids(monde) -> list[str]:
    """LIST of PC ids in the campaign. GENERIC (never hardcoded).

    Some campaigns have MULTIPLE PCs; this is the canonical form. Fail-open
    cascade, from most specific to most general (the FIRST non-empty source wins;
    sources are NOT merged):
      1) `meta.pj_ids` (world.json): list of str (canonical form);
      2) otherwise `meta.pj_id` (world.json): single str → `[meta.pj_id]` (backward-compat);
      3) otherwise env `MGM_PJ_ID`: str split on commas ("a,b" → ["a","b"]);
      4) otherwise `[]`.
    Empty/blank entries are ignored and duplicates removed PRESERVING first-seen
    ORDER. Empty list = "no PC declared" → filters/branches targeting the PC
    degrade cleanly (empty relational panel, no event targeting the PC), never
    an error. Non-dict `monde` is tolerated (→ env/[]).
    """
    m = monde.get("meta") if isinstance(monde, dict) else None
    m = m if isinstance(m, dict) else {}

    # Collect candidate ids from the FIRST non-empty source in the cascade.
    bruts: list = []
    liste = m.get("pj_ids")
    if isinstance(liste, list) and any(isinstance(x, str) and x.strip() for x in liste):
        bruts = liste
    else:
        pid = m.get("pj_id")
        if isinstance(pid, str) and pid.strip():
            bruts = [pid]
        else:
            env = os.environ.get("MGM_PJ_ID")
            if isinstance(env, str) and env.strip():
                bruts = env.split(",")

    # Normalize: ignore non-str / blank entries, deduplicate preserving order.
    sortie: list[str] = []
    vus: set[str] = set()
    for x in bruts:
        if not isinstance(x, str):
            continue
        v = x.strip()
        if not v or v in vus:
            continue
        vus.add(v)
        sortie.append(v)
    return sortie


def pj_id(monde) -> str | None:
    """id of the FIRST player character in the campaign (backward-compat). GENERIC.

    Defined as "first of `pj_ids(monde)` or None". Preserves the old single-PC
    semantics (first declared PC) while relying on the unified multi-PC cascade
    (`meta.pj_ids` > `meta.pj_id` > env `MGM_PJ_ID` > None). None =
    "no PC declared" → branches targeting the PC degrade cleanly.
    """
    ids = pj_ids(monde)
    return ids[0] if ids else None


# ════════════════════════════════════════════════════════════════════════════
# 3.3  Time conversion  T <-> day/hour  (SINGLE bridge)
# ════════════════════════════════════════════════════════════════════════════
#
# T is an integer >= 0 in UT; T=0 = campaign creation; monotone. The player
# NEVER sees T: all conversion goes through these functions (no calendar elsewhere).

# Frozen time-of-day slots for narrative rendering (hour 0–23 → fuzzy label).
_TRANCHES_NARRATIVES = (
    (0, 4, "nuit"),
    (5, 7, "aube"),
    (8, 11, "matin"),
    (12, 13, "midi"),
    (14, 17, "après-midi"),
    (18, 19, "fin d'après-midi"),
    (20, 21, "soir"),
    (22, 23, "nuit"),
)


def t_vers_jour_heure(T: int) -> tuple[int, int, int]:
    """T (UT) → (day, hour, minute).

    day starts at 1: day = T // 144 + 1. hour 0–23, minute ∈ {0,10,…,50}.
    Frozen example: T=0 → (1, 0, 0).
    """
    T = int(T)
    jour = T // UT_PAR_JOUR + 1
    reste = T % UT_PAR_JOUR              # UT within the day (0–143)
    heure = reste // UT_PAR_HEURE        # 0–23
    minute = (reste % UT_PAR_HEURE) * MINUTES_PAR_UT  # 0,10,20,30,40,50
    return (jour, heure, minute)


def jour_heure_vers_t(jour: int, heure: int = 0, minute: int = 0) -> int:
    """Inverse of t_vers_jour_heure. jour >= 1.

    T = (jour-1)*144 + heure*6 + minute//10. Frozen example:
    jour_heure_vers_t(7, 12, 0) == 936.
    """
    return ((int(jour) - 1) * UT_PAR_JOUR
            + int(heure) * UT_PAR_HEURE
            + int(minute) // MINUTES_PAR_UT)


def t_vers_narratif(T: int) -> str:
    """FUZZY narrative rendering — NEVER the raw T.

    Example: 'Jour 58, fin d'après-midi'. Frozen time slots (narrative labels are French game data):
      0-4 nuit · 5-7 aube · 8-11 matin · 12-13 midi · 14-17 après-midi ·
      18-19 fin d'après-midi · 20-21 soir · 22-23 nuit.
    """
    jour, heure, _ = t_vers_jour_heure(T)
    libelle = "nuit"
    for lo, hi, nom in _TRANCHES_NARRATIVES:
        if lo <= heure <= hi:
            libelle = nom
            break
    return f"Jour {jour}, {libelle}"


def parser_duree_minutes(texte: str) -> int:
    """Parse a narrative duration string into MINUTES. -1 if unparsable.

    Accepts '2h', '30min', '1h30', '1h30min', '~4h', '5h45 — desc'… Same
    semantics as validator-distances.extraire_minutes (proven regex copied):
    minutes after an hour can be written WITHOUT the 'min' suffix ("1h30" = 90).
    """
    if not texte:
        return -1
    nettoye = str(texte).strip().lstrip("~≈ ")

    # Case 1: 'Xh' optionally followed by minutes ('Xh', 'XhYY', 'XhYYmin').
    m = re.match(r"(\d+)\s*h\s*(\d+)?\s*(?:min)?", nettoye)
    if m and m.group(1):
        heures = int(m.group(1))
        minutes = int(m.group(2)) if m.group(2) else 0
        total = heures * 60 + minutes
        return total if total > 0 else -1

    # Case 2: minutes only ('YYmin', 'YY min').
    m = re.match(r"(\d+)\s*min", nettoye)
    if m:
        total = int(m.group(1))
        return total if total > 0 else -1

    return -1


def minutes_vers_ut(minutes: int) -> int:
    """DETERMINISTIC rounding of minutes to the nearest UT (stdlib round()).

    round() uses banker's rounding (34.5 → 34). Minimum 1 if minutes > 0.
    Frozen examples: 40min→4, 90min→9, 20min→2, 345min→34.
    """
    minutes = int(minutes)
    if minutes <= 0:
        return 0
    ut = int(round(minutes / MINUTES_PAR_UT))
    return ut if ut >= 1 else 1


def t_courant(campagne: Path) -> int:
    """Current T of the campaign (UT), DETERMINISTIC and FAIL-OPEN.

    Resolution order (contract §3.3):
      1) max of INTEGER 't' values in evenements_programmes.json (resolved events);
      2) otherwise, derived from the max 'Jour N' in world.json>global_state.timeline +
         sessions/*.json via jour_heure_vers_t(jour_max, 12, 0)  (noon by default);
      3) otherwise 0.

    NEVER reads events.json as integers (its 't' values are STRINGS 'Jour N…').
    Reuses the 'Jour N' heuristic from clock.jour_courant.
    """
    campagne = Path(campagne)

    # 1) Scheduled/resolved events (integer t values in UT).
    prog = charger_json(campagne / "evenements_programmes.json", {}) or {}
    ts = []
    if isinstance(prog, dict):
        for e in prog.get("events", []) or []:
            if isinstance(e, dict):
                t = e.get("T", e.get("t"))
                if isinstance(t, int) and not isinstance(t, bool):
                    ts.append(t)
    if ts:
        return max(ts)

    # 2) Largest "Jour N" from the chronology + sessions → noon of that day.
    jour_max = _jour_max_narratif(campagne)
    if jour_max is not None:
        return jour_heure_vers_t(jour_max, 12, 0)

    # 3) Default.
    return 0


def _jour_max_narratif(campagne: Path) -> int | None:
    """Largest "Jour N" found in world.json (chronology) + sessions/*.json.

    None if none found. (Heuristic aligned with clock.jour_courant, but WITHOUT units_per_day
    since this module reasons in pure T.)
    """
    jours: set[int] = set()

    monde = charger_json(campagne / "world.json", {}) or {}
    chrono = monde.get("global_state", {}).get("timeline", "")
    if isinstance(chrono, str):
        for m in re.findall(r"[Jj]our\s+(\d+)", chrono):
            jours.add(int(m))

    sessions_dir = campagne / "sessions"
    if sessions_dir.is_dir():
        for sp in sessions_dir.glob("*.json"):
            try:
                contenu = sp.read_text(encoding="utf-8")
            except OSError:
                continue
            for m in re.findall(r"[Jj]our\s+(\d+)", contenu):
                jours.add(int(m))

    return max(jours) if jours else None


# ════════════════════════════════════════════════════════════════════════════
# 3.4  Graph — loading and CONTAINMENT helpers
# ════════════════════════════════════════════════════════════════════════════

def charger_geo(campagne: Path) -> dict:
    """Load geo.json → dict {'meta':…, 'locations':[…]}; {} if absent (fail-open)."""
    geo = charger_json(Path(campagne) / "geo.json", {})
    return geo if isinstance(geo, dict) else {}


def index_lieux(geo: dict) -> dict[str, dict]:
    """Index locations by id → node. O(1) lookup."""
    idx: dict[str, dict] = {}
    if not isinstance(geo, dict):
        return idx
    for noeud in geo.get("locations", []) or []:
        if isinstance(noeud, dict) and isinstance(noeud.get("id"), str):
            idx[noeud["id"]] = noeud
    return idx


def parents(geo: dict, id_lieu: str) -> list[str]:
    """ASCENDING containment chain: [parent, grandparent, … root].

    [] if root (null parent) or unknown id. Robust to potential cycles (stops
    as soon as an id is seen again).
    """
    idx = index_lieux(geo)
    chaine: list[str] = []
    vus: set[str] = set()
    courant = idx.get(id_lieu)
    while courant is not None:
        p = courant.get("parent")
        if not isinstance(p, str) or p in vus:
            break
        chaine.append(p)
        vus.add(p)
        courant = idx.get(p)
    return chaine


def contenus(geo: dict, id_lieu: str, recursif: bool = False) -> list[str]:
    """Ids of locations whose parent is id_lieu.

    recursif=True → full descendant tree (breadth-first traversal, no duplicates).
    """
    idx = index_lieux(geo)
    directs = [nid for nid, n in idx.items() if n.get("parent") == id_lieu]
    if not recursif:
        return directs
    resultat: list[str] = []
    vus: set[str] = set()
    file = list(directs)
    while file:
        cur = file.pop(0)
        if cur in vus:
            continue
        vus.add(cur)
        resultat.append(cur)
        for nid, n in idx.items():
            if n.get("parent") == cur and nid not in vus:
                file.append(nid)
    return resultat


def lieu_racine(geo: dict, id_lieu: str) -> str | None:
    """Climb up to the root region (null parent). None if id is unknown.

    If id_lieu is already a root, returns itself.
    """
    idx = index_lieux(geo)
    if id_lieu not in idx:
        return None
    chaine = parents(geo, id_lieu)
    return chaine[-1] if chaine else id_lieu


# ════════════════════════════════════════════════════════════════════════════
# 3.5  Graph — ADJACENCY helpers and paths
# ════════════════════════════════════════════════════════════════════════════

def aretes_sortantes(geo: dict, id_lieu: str) -> list[dict]:
    """'aretes' edges of the node (each: {vers,dir,distance_m,temps_ut,voie})."""
    noeud = index_lieux(geo).get(id_lieu)
    if not isinstance(noeud, dict):
        return []
    aretes = noeud.get("aretes", [])
    return [a for a in aretes if isinstance(a, dict)] if isinstance(aretes, list) else []


def voisins_ids(geo: dict, id_lieu: str) -> list[str]:
    """Target ids of outgoing edges (direct adjacency, excluding containment)."""
    return [a["vers"] for a in aretes_sortantes(geo, id_lieu)
            if isinstance(a.get("vers"), str)]


def _adjacence_bidirectionnelle(geo: dict) -> dict[str, dict[str, dict]]:
    """Build a BIDIRECTIONAL adjacency table weighted by 'temps_ut'.

    Graph edges are treated as symmetric ("outward = return"). For parallel edges,
    the SMALLEST cost is kept. Returns
    {id_a: {id_b: {'temps_ut':int, 'distance_m':num|None, 'dir':str, 'voie':str|None,
    'arete':<source edge>}}}.
    """
    idx = index_lieux(geo)
    adj: dict[str, dict[str, dict]] = {nid: {} for nid in idx}

    def ajouter(a: str, b: str, cout: int, arete: dict, dir_ab: str):
        if a not in adj:
            adj[a] = {}
        precedent = adj[a].get(b)
        if precedent is None or cout < precedent["temps_ut"]:
            adj[a][b] = {
                "temps_ut": cout,
                "distance_m": arete.get("distance_m"),
                "dir": dir_ab,
                "voie": arete.get("voie"),
                "arete": arete,
            }

    _opp = {"N": "S", "S": "N", "E": "O", "O": "E",
            "NE": "SO", "SO": "NE", "NO": "SE", "SE": "NO"}

    for a_id, noeud in idx.items():
        for arete in aretes_sortantes(geo, a_id):
            b_id = arete.get("vers")
            if not isinstance(b_id, str):
                continue
            try:
                cout = int(arete.get("temps_ut"))
            except (TypeError, ValueError):
                continue
            if cout < 0:
                continue
            dir_ab = arete.get("dir", "?")
            ajouter(a_id, b_id, cout, arete, dir_ab)
            # Return direction (bidirectional) with opposite direction if known.
            ajouter(b_id, a_id, cout, arete, _opp.get(dir_ab, "?"))
    return adj


def plus_court_chemin(geo: dict, a: str, b: str) -> dict:
    """Dijkstra on the 'temps_ut' weight (BIDIRECTIONAL edges: A→B allows
    B→A at the same cost, "outward = return").

    Returns {'chemin':[id…], 'aretes':[arete…], 'temps_ut':int, 'distance_m':int}
    or {'chemin':[], 'aretes':[], 'temps_ut':-1, 'distance_m':0} if no path exists.
    a==b → {'chemin':[a], 'temps_ut':0}.
    """
    idx = index_lieux(geo)
    vide = {"chemin": [], "aretes": [], "temps_ut": -1, "distance_m": 0}
    if a not in idx or b not in idx:
        return dict(vide)
    if a == b:
        return {"chemin": [a], "aretes": [], "temps_ut": 0, "distance_m": 0}

    adj = _adjacence_bidirectionnelle(geo)

    # Dijkstra without external heapq (priority queue by scan: sufficient for
    # a few dozen nodes; stdlib heapq could have been used but we stay
    # deliberately simple and 100% deterministic on id ordering).
    dist: dict[str, int] = {a: 0}
    prec: dict[str, tuple[str, dict]] = {}   # b → (parent, edge_info)
    non_visites = set(idx.keys())

    while non_visites:
        # Select the unvisited node with minimum distance (deterministic order: id).
        courant = None
        meilleure = None
        for nid in sorted(non_visites):
            d = dist.get(nid)
            if d is None:
                continue
            if meilleure is None or d < meilleure:
                meilleure = d
                courant = nid
        if courant is None:
            break
        non_visites.discard(courant)
        if courant == b:
            break
        for voisin, info in sorted(adj.get(courant, {}).items()):
            if voisin not in non_visites:
                continue
            nouveau = dist[courant] + info["temps_ut"]
            if voisin not in dist or nouveau < dist[voisin]:
                dist[voisin] = nouveau
                prec[voisin] = (courant, info)

    if b not in dist:
        return dict(vide)

    # Reconstruct the path.
    chemin_ids = [b]
    aretes_chemin: list[dict] = []
    distance_totale = 0
    cur = b
    while cur != a:
        parent, info = prec[cur]
        chemin_ids.append(parent)
        aretes_chemin.append(info["arete"])
        dm = info.get("distance_m")
        if isinstance(dm, (int, float)):
            distance_totale += dm
        cur = parent
    chemin_ids.reverse()
    aretes_chemin.reverse()

    return {
        "chemin": chemin_ids,
        "aretes": aretes_chemin,
        "temps_ut": dist[b],
        "distance_m": int(distance_totale),
    }


def distance_graphe_ut(geo: dict, a: str, b: str) -> int:
    """Total 'temps_ut' cost of the shortest path (Dijkstra). -1 if disconnected."""
    return plus_court_chemin(geo, a, b).get("temps_ut", -1)


def distance_vol_oiseau(geo: dict, a: str, b: str) -> float:
    """Euclidean distance between anchors (x,y). -1.0 if an anchor is missing."""
    idx = index_lieux(geo)
    na, nb = idx.get(a), idx.get(b)
    pa = _ancrage_xy(na)
    pb = _ancrage_xy(nb)
    if pa is None or pb is None:
        return -1.0
    return math.hypot(pa[0] - pb[0], pa[1] - pb[1])


def _ancrage_xy(noeud) -> tuple[float, float] | None:
    """Extract (x, y) from a node's anchor, or None if absent/malformed."""
    if not isinstance(noeud, dict):
        return None
    anc = noeud.get("ancrage")
    if not isinstance(anc, dict):
        return None
    x, y = anc.get("x"), anc.get("y")
    if isinstance(x, (int, float)) and isinstance(y, (int, float)):
        return (float(x), float(y))
    return None


# ════════════════════════════════════════════════════════════════════════════
# 3.6  Anchor MDS — PURE STDLIB (travel-time matrix → (x, y))
# ════════════════════════════════════════════════════════════════════════════
#
# SMACOF implementation (stress majorization, Guttman transform). Sufficient for
# a few dozen locations. The produced coordinates are NON-METRIC and are only
# used in code (radius, crossing, proximity sort) — NEVER exposed to the LLM.

# Mapping label (key from regles.temps.deplacements) → location id.
# Sources/destinations in `deplacements` matrices are snake/kebab labels.
# The mapping is NO LONGER hardcoded: it is BUILT on the fly from world.json
# (names + aliases of regions/locations) by `index_labels`. worldlib therefore
# knows NO location name or campaign id — all geography comes from data.


def _norm_label(s) -> str:
    """Normalize a label for lookup in the labels→id index.

    `_` → space, strip, lowercase, then NFKD + strip diacritics.
    (Normalization identical to the former `_label_vers_id`.)
    """
    brut = str(s).replace("_", " ").strip().lower()
    brut = unicodedata.normalize("NFKD", brut)
    return "".join(c for c in brut if not unicodedata.combining(c))


def index_labels(monde) -> dict[str, str]:
    """Build the { _norm_label(form) -> id } index from world.json.

    Iterates `monde["universe"]["regions"]` and, for each region, indexes its
    `nom` → `reg["id"]`; for each location in `reg["locations"]`, indexes its `nom` and
    each of its `alias` → `fiche["id"]`. NO hardcoded names. Fail-open: absent/
    wrongly-typed structure → returns {} (never raises).
    """
    index: dict[str, str] = {}
    if not isinstance(monde, dict):
        return index
    universe = monde.get("universe")
    regions = universe.get("regions") if isinstance(universe, dict) else None
    if not isinstance(regions, list):
        return index
    for reg in regions:
        if not isinstance(reg, dict):
            continue
        rid = reg.get("id")
        rnom = reg.get("name")
        if isinstance(rid, str) and rid and isinstance(rnom, str) and rnom:
            index[_norm_label(rnom)] = rid
        lieux = reg.get("locations")
        if not isinstance(lieux, list):
            continue
        for fiche in lieux:
            if not isinstance(fiche, dict):
                continue
            lid = fiche.get("id")
            if not (isinstance(lid, str) and lid):
                continue
            nom = fiche.get("name")
            if isinstance(nom, str) and nom:
                index[_norm_label(nom)] = lid
            alias = fiche.get("alias")
            if isinstance(alias, list):
                for al in alias:
                    if isinstance(al, str) and al:
                        index[_norm_label(al)] = lid
    return index


def _label_vers_id(label: str, index: dict[str, str]) -> str | None:
    """Map a deplacements matrix label to a location id via `index`.

    Fallback if absent from the index: if the label IS already an id (`lieu:`/`region:`/
    `ville:`), return it as-is; otherwise None.
    """
    if not label:
        return None
    hit = index.get(_norm_label(label))
    if hit is not None:
        return hit
    if str(label).startswith(("lieu:", "region:", "ville:")):
        return str(label)
    return None


def _paires_depuis_deplacements(dep: dict, index: dict[str, str]) -> list[tuple[str, str, int]]:
    """Extract (id_a, id_b, minutes) pairs from regles.temps.deplacements.

    Iterates `depuis_<source>_vers`, `entre`, and simple keys of the form
    `<a>_vers_<b>`. Labels are resolved to ids via `index` (built by
    `index_labels`). Unparsable durations (e.g. "Distance inconnue") and
    unresolved labels are ignored.
    """
    paires: list[tuple[str, str, int]] = []
    if not isinstance(dep, dict):
        return paires

    for section_key, section_val in dep.items():
        if section_key == "gouvernance":
            continue

        # Simple key "<a>_vers_<b>": value = duration (string).
        if isinstance(section_val, str):
            if "_vers_" in section_key:
                gauche, droite = section_key.split("_vers_", 1)
                ida = _label_vers_id(gauche, index)
                idb = _label_vers_id(droite, index)
                mn = parser_duree_minutes(section_val)
                if ida and idb and mn > 0:
                    paires.append((ida, idb, mn))
            continue

        if not isinstance(section_val, dict):
            continue

        if section_key.startswith("depuis_") and section_key.endswith("_vers"):
            src_label = section_key[len("depuis_"):-len("_vers")]
            ida = _label_vers_id(src_label, index)
            for dest_key, desc in section_val.items():
                if not isinstance(desc, str):
                    continue
                idb = _label_vers_id(dest_key, index)
                mn = parser_duree_minutes(desc)
                if ida and idb and mn > 0:
                    paires.append((ida, idb, mn))

        elif section_key == "entre":
            for cle, desc in section_val.items():
                if not isinstance(desc, str) or "_vers_" not in cle:
                    continue
                gauche, droite = cle.split("_vers_", 1)
                ida = _label_vers_id(gauche, index)
                idb = _label_vers_id(droite, index)
                mn = parser_duree_minutes(desc)
                if ida and idb and mn > 0:
                    paires.append((ida, idb, mn))

    return paires


def _paires_depuis_geo(geo: dict) -> list[tuple[str, str, int]]:
    """Extract (id_a, id_b, temps_ut) pairs from the edges of a geo graph."""
    paires: list[tuple[str, str, int]] = []
    idx = index_lieux(geo)
    for a_id in idx:
        for arete in aretes_sortantes(geo, a_id):
            b_id = arete.get("vers")
            try:
                cout = int(arete.get("temps_ut"))
            except (TypeError, ValueError):
                continue
            if isinstance(b_id, str) and cout > 0:
                paires.append((a_id, b_id, cout))
    return paires


def _floyd_warshall(n: int, D: list[list[float]]) -> list[list[float]]:
    """Complete a distance matrix with shortest paths (Floyd-Warshall).

    D[i][j] == math.inf means "no direct edge". Modifies a COPY and returns it.
    Any pair remaining infinite (disconnected graph) is left at inf and must be
    handled by the caller.
    """
    M = [row[:] for row in D]
    for k in range(n):
        Mk = M[k]
        for i in range(n):
            Mik = M[i][k]
            if Mik == math.inf:
                continue
            Mi = M[i]
            for j in range(n):
                via = Mik + Mk[j]
                if via < Mi[j]:
                    Mi[j] = via
    return M


def matrice_durees(geo_ou_deplacements,
                   index_labels=None) -> tuple[list[str], list[list[float]]]:
    """Build the dissimilarity matrix (in UT).

    Input = `deplacements` dict (regles.temps.deplacements) OR `geo` graph.
      * GEO (edges already in ids): extracts (id_a, id_b, temps_ut) pairs;
        `index_labels` is unused (ignored).
      * DEPLACEMENTS (snake labels): resolves labels to ids via
        `index_labels` (cf. `index_labels(monde)`), parses durations
        (parser_duree_minutes) and converts to UT (minutes_vers_ut). If
        `index_labels` is None → no label can be mapped → consistent EMPTY matrix
        (fail-open: we do not guess the geography).
      * completes missing pairs via shortest path (Floyd-Warshall);
      * returns (sorted_ids, D) with D[i][j] symmetric (min of both directions),
        diagonal 0.

    Input detection: a geo graph has a 'locations' key (list of nodes).
    """
    est_geo = (isinstance(geo_ou_deplacements, dict)
               and isinstance(geo_ou_deplacements.get("locations"), list))

    if est_geo:
        brutes = _paires_depuis_geo(geo_ou_deplacements)  # already in UT
        paires_ut = [(a, b, int(ut)) for (a, b, ut) in brutes]
    else:
        idx_lbl = index_labels if isinstance(index_labels, dict) else {}
        brutes = _paires_depuis_deplacements(geo_ou_deplacements or {}, idx_lbl)  # minutes
        paires_ut = [(a, b, minutes_vers_ut(mn)) for (a, b, mn) in brutes]

    # Ordered, deterministic set of encountered ids.
    ids = sorted({a for a, _, _ in paires_ut} | {b for _, b, _ in paires_ut})
    n = len(ids)
    pos = {nid: i for i, nid in enumerate(ids)}

    # Initial matrix: inf outside known edges, 0 on the diagonal.
    D = [[0.0 if i == j else math.inf for j in range(n)] for i in range(n)]
    for a, b, ut in paires_ut:
        i, j = pos[a], pos[b]
        cout = float(max(ut, 1))
        # Symmetrize: keep the smallest observed cost.
        if cout < D[i][j]:
            D[i][j] = cout
            D[j][i] = cout

    if n == 0:
        return ids, D

    # Complete missing pairs via shortest path.
    complet = _floyd_warshall(n, D)

    # Any pair remaining infinite (disconnected component): bound it by a large
    # value derived from the known finite diameter (avoids NaN in the MDS).
    finis = [complet[i][j] for i in range(n) for j in range(n)
             if i != j and complet[i][j] != math.inf]
    grande = (max(finis) * 2.0) if finis else 1.0
    for i in range(n):
        for j in range(n):
            if i != j and complet[i][j] == math.inf:
                complet[i][j] = grande
            complet[i][j] = float(complet[i][j])
    return ids, complet


class _Rng:
    """Minimal DETERMINISTIC pseudo-random generator (LCG) — pure stdlib, without
    depending on the `random` implementation (guarantees MDS reproducibility
    regardless of Python version).
    """

    __slots__ = ("_etat",)

    def __init__(self, seed: int):
        self._etat = (seed ^ 0x5DEECE66D) & ((1 << 48) - 1)

    def random(self) -> float:
        # Numerical Recipes LCG, returns a float in [0, 1).
        self._etat = (self._etat * 6364136223846793005 + 1442695040888963407) & ((1 << 48) - 1)
        return self._etat / float(1 << 48)

    def uniform(self, a: float, b: float) -> float:
        return a + (b - a) * self.random()


def ancrer_mds(ids: list[str], D: list[list[float]],
               iterations: int = 300, seed: int = 42) -> dict[str, dict]:
    """SMACOF (stress majorization) in PURE STDLIB.

    Returns {id: {'x': int, 'y': int}} centered (barycenter at 0) and rounded to
    integer. DETERMINISTIC (frozen seed). Unit: ~1 UT of travel ≈ 1 plan unit
    (internal scale, NEVER shown to the LLM).

    Guarantees: determinism (seed); termination (bounded iterations); non-metric
    coordinates (code use only).
    """
    n = len(ids)
    if n == 0:
        return {}
    if n == 1:
        return {ids[0]: {"x": 0, "y": 0}}

    rng = _Rng(seed)

    # Initial configuration: small reproducible pseudo-random cloud. The initial
    # scale is calibrated to the order of magnitude of the dissimilarities.
    finis = [D[i][j] for i in range(n) for j in range(n)
             if i != j and D[i][j] not in (0.0, math.inf)]
    echelle = (sum(finis) / len(finis)) if finis else 1.0
    X = [[rng.uniform(-echelle, echelle), rng.uniform(-echelle, echelle)]
         for _ in range(n)]

    def _dist(a, b):
        return math.hypot(a[0] - b[0], a[1] - b[1])

    # Unit weights on useful pairs (D > 0, finite), 0 elsewhere.
    W = [[0.0 if (i == j or D[i][j] <= 0 or D[i][j] == math.inf) else 1.0
          for j in range(n)] for i in range(n)]
    somme_w = [sum(W[i]) for i in range(n)]

    # --- SMACOF iteration (Guttman transform) --------------------------------
    # Update of the i-th row:
    #     X'_i = (1/Σ_j w_ij) · (B(X)·X)_i
    # with (B·X)_i = Σ_{j≠i} w_ij · (D_ij / d_ij) · (X_i − X_j)
    # (b_ij = −w_ij·D_ij/d_ij off-diagonal, b_ii = −Σ_{j≠i} b_ij: the sum folds
    # exactly into Σ_{j≠i} s_ij·(X_i − X_j) with s_ij = w_ij·D_ij/d_ij).
    # Σ_j w_ij serves as the pseudo-inverse of V (diagonal approximation, standard
    # for coarse non-metric anchoring). Deterministic, bounded termination.
    iterations = max(1, int(iterations))
    for _ in range(iterations):
        nouveau = [list(p) for p in X]
        for i in range(n):
            if somme_w[i] <= 0:
                continue                       # isolated point: leave it in place
            xi = X[i]
            ax = ay = 0.0
            for j in range(n):
                w = W[i][j]
                if w == 0.0:
                    continue
                xj = X[j]
                dij = _dist(xi, xj)
                if dij < 1e-12:
                    # Superimposed points: tiny deterministic jitter to separate them
                    # (otherwise d_ij=0 → zero contribution, they stay stuck together).
                    jitter = 1e-6 * (1 + (i * n + j) % 7)
                    ax += w * D[i][j] * jitter
                    ay += w * D[i][j] * jitter
                    continue
                s = w * (D[i][j] / dij)
                ax += s * (xi[0] - xj[0])
                ay += s * (xi[1] - xj[1])
            nouveau[i][0] = ax / somme_w[i]
            nouveau[i][1] = ay / somme_w[i]
        X = nouveau

    # Center the barycenter at the origin.
    cx = sum(p[0] for p in X) / n
    cy = sum(p[1] for p in X) / n
    coords: dict[str, dict] = {}
    for i, nid in enumerate(ids):
        coords[nid] = {"x": int(round(X[i][0] - cx)), "y": int(round(X[i][1] - cy))}
    return coords


def stress_normalise(ids: list[str], D: list[list[float]],
                     coords: dict[str, dict]) -> float:
    """Anchor quality indicator.

    sqrt( Σ(d_ij - D_ij)² / Σ D_ij² ) over pairs i<j of useful dissimilarity
    (D_ij > 0, finite). d_ij = Euclidean distance of anchors. 0.0 if denominator
    is zero.
    """
    n = len(ids)
    num = 0.0
    den = 0.0
    for i in range(n):
        ci = coords.get(ids[i])
        if not ci:
            continue
        for j in range(i + 1, n):
            cj = coords.get(ids[j])
            if not cj:
                continue
            Dij = D[i][j]
            if Dij is None or Dij <= 0 or Dij == math.inf:
                continue
            dij = math.hypot(ci["x"] - cj["x"], ci["y"] - cj["y"])
            num += (dij - Dij) ** 2
            den += Dij ** 2
    if den <= 0:
        return 0.0
    return math.sqrt(num / den)


# ════════════════════════════════════════════════════════════════════════════
# 3.7  Trajectories (position = function of time)
# ════════════════════════════════════════════════════════════════════════════
#
# A trajectory is a list of segments sorted by ascending 'de', with no gap or
# overlap. Two forms:
#   * stay         : {"lieu": "<id>", "de": T0, "a": T1}   (a:null = current)
#   * travel       : {"type":"deplacement","de":T0,"a":T1,"chemin":["<id>",…],"motif":"…"}

def _seg_de(seg: dict) -> int:
    return int(seg.get("de", 0))


def _seg_a(seg: dict):
    a = seg.get("a", None)
    return None if a is None else int(a)


def _est_deplacement(seg: dict) -> bool:
    return seg.get("type") == "deplacement"


def position_a(geo: dict, trajectoire: list[dict], T: int) -> dict:
    """Position of an entity at time T.

    Returns {'lieu':'<id>', 'x':float, 'y':float, 'en_mouvement':bool, 'segment':idx}.
      * active stay → location + anchor of that location, en_mouvement=False;
      * active travel → interpolates (x,y) along 'chemin' proportionally in time
        between successive anchors; 'lieu' = id of the nearest edge endpoint,
        en_mouvement=True;
      * T before the 1st segment → 1st location; after the last (a=null) → last location.
    {} if trajectory is empty.
    """
    if not trajectoire:
        return {}
    idx = index_lieux(geo)
    T = int(T)

    segments = sorted(enumerate(trajectoire), key=lambda kv: _seg_de(kv[1]))

    # Before the very first segment → first known location.
    premier_i, premier = segments[0]
    if T < _seg_de(premier):
        return _position_statique(idx, premier, premier_i)

    # Search for the active segment.
    for k, (i, seg) in enumerate(segments):
        de = _seg_de(seg)
        a = _seg_a(seg)
        actif = (de <= T) and (a is None or T < a or (T == a and k == len(segments) - 1))
        # Boundary case: if T == a and this is not the last, the next segment takes over.
        if a is not None and T >= a and k < len(segments) - 1:
            actif = False
        if not actif:
            continue
        if _est_deplacement(seg):
            return _position_deplacement(idx, seg, i, T)
        return _position_statique(idx, seg, i)

    # After the last segment (last finite 'a' exceeded) → last location.
    dernier_i, dernier = segments[-1]
    if _est_deplacement(dernier):
        return _position_deplacement(idx, dernier, dernier_i, _seg_a(dernier) or T)
    return _position_statique(idx, dernier, dernier_i)


def _position_statique(idx: dict, seg: dict, i: int) -> dict:
    """Position of a stay: location + anchor (0,0 if anchor missing)."""
    lid = seg.get("lieu")
    xy = _ancrage_xy(idx.get(lid)) or (0.0, 0.0)
    return {"lieu": lid, "x": xy[0], "y": xy[1], "en_mouvement": False, "segment": i}


def _position_deplacement(idx: dict, seg: dict, i: int, T: int) -> dict:
    """Interpolate position along the 'chemin' of a travel proportionally in time.
    The returned 'lieu' is the nearest current edge endpoint.
    """
    chemin = [c for c in seg.get("chemin", []) if isinstance(c, str)]
    de = _seg_de(seg)
    a = _seg_a(seg)
    # Anchor points of the available path.
    points = [(_ancrage_xy(idx.get(c)) or (0.0, 0.0)) for c in chemin]
    if not points:
        return {"lieu": None, "x": 0.0, "y": 0.0, "en_mouvement": True, "segment": i}
    if len(points) == 1 or a is None or a <= de:
        return {"lieu": chemin[0], "x": points[0][0], "y": points[0][1],
                "en_mouvement": True, "segment": i}

    # Global time fraction [0,1] over the travel segment.
    frac = max(0.0, min(1.0, (T - de) / float(a - de)))
    # Cumulative polyline length to distribute the fraction over segments.
    seg_lens = [math.hypot(points[k + 1][0] - points[k][0],
                           points[k + 1][1] - points[k][1])
                for k in range(len(points) - 1)]
    total = sum(seg_lens)
    if total <= 0:
        # All anchors superimposed: distribute uniformly by index.
        nb = len(points) - 1
        idx_seg = min(nb - 1, int(frac * nb))
        p0, p1 = points[idx_seg], points[idx_seg + 1]
        lieu = chemin[idx_seg + 1] if frac >= (idx_seg + 0.5) / nb else chemin[idx_seg]
        return {"lieu": lieu, "x": p0[0], "y": p0[1],
                "en_mouvement": True, "segment": i}

    cible = frac * total
    cumul = 0.0
    for k, L in enumerate(seg_lens):
        if cumul + L >= cible or k == len(seg_lens) - 1:
            reste = (cible - cumul) / L if L > 0 else 0.0
            reste = max(0.0, min(1.0, reste))
            p0, p1 = points[k], points[k + 1]
            x = p0[0] + (p1[0] - p0[0]) * reste
            y = p0[1] + (p1[1] - p0[1]) * reste
            lieu = chemin[k + 1] if reste >= 0.5 else chemin[k]
            return {"lieu": lieu, "x": x, "y": y, "en_mouvement": True, "segment": i}
        cumul += L

    # Safety fallback (should not be reached).
    return {"lieu": chemin[-1], "x": points[-1][0], "y": points[-1][1],
            "en_mouvement": True, "segment": i}


def valider_trajectoire(geo: dict, trajectoire: list[dict]) -> list[str]:
    """Returns the LIST of violations (empty = valid).

    Checks (contract §3.7):
      * reference: every 'lieu'/'chemin' points to an existing id;
      * continuity: contiguous segments (a[i] == de[i+1]), no overlap;
      * real path: a 'deplacement' follows consecutive existing edges;
      * no teleportation: (a-de) >= sum of edge temps_ut along the path;
      * monotonicity: de <= a (except a=null).
    (The "not in the past" check is done by the caller using T_courant.)
    """
    violations: list[str] = []
    if not isinstance(trajectoire, list) or not trajectoire:
        return violations

    idx = index_lieux(geo)
    adj = _adjacence_bidirectionnelle(geo) if idx else {}

    # Validate in ascending 'de' order.
    segs = sorted(trajectoire, key=_seg_de)

    for k, seg in enumerate(segs):
        if not isinstance(seg, dict):
            violations.append(f"segment #{k} : is not a JSON object.")
            continue
        de = _seg_de(seg)
        a = _seg_a(seg)

        # Internal monotonicity.
        if a is not None and a < de:
            violations.append(f"segment #{k} : a ({a}) < de ({de}) (monotonicity).")

        if _est_deplacement(seg):
            chemin = seg.get("chemin", [])
            if not isinstance(chemin, list) or len(chemin) < 1:
                violations.append(f"segment #{k} (travel) : 'chemin' empty or missing.")
            else:
                # Reference check for path ids.
                for c in chemin:
                    if idx and c not in idx:
                        violations.append(
                            f"segment #{k} : unknown location in path '{c}' (reference).")
                # Real consecutive edges + sum of temps_ut.
                somme_ut = 0
                for u, v in zip(chemin, chemin[1:]):
                    info = adj.get(u, {}).get(v) if adj else None
                    if adj and info is None:
                        violations.append(
                            f"segment #{k} : no edge {u} → {v} (real path).")
                    elif info is not None:
                        somme_ut += info["temps_ut"]
                # No teleportation.
                if a is not None and (a - de) < somme_ut:
                    violations.append(
                        f"segment #{k} : duration {a - de} UT < sum of edges {somme_ut} UT "
                        f"(teleportation forbidden).")
        else:
            lid = seg.get("lieu")
            if idx and lid not in idx:
                violations.append(f"segment #{k} : unknown location '{lid}' (reference).")

        # Continuity with the next segment.
        if k < len(segs) - 1:
            suivant = segs[k + 1]
            a_courant = _seg_a(seg)
            de_suivant = _seg_de(suivant)
            if a_courant is None:
                violations.append(
                    f"segment #{k} : 'a' is null but a following segment exists (continuity).")
            elif a_courant != de_suivant:
                if a_courant < de_suivant:
                    violations.append(
                        f"segment #{k}/#{k + 1} : time gap "
                        f"(a={a_courant} ≠ de_suivant={de_suivant}).")
                else:
                    violations.append(
                        f"segment #{k}/#{k + 1} : overlap "
                        f"(a={a_courant} > de_suivant={de_suivant}).")

    return violations


# ════════════════════════════════════════════════════════════════════════════
# 3.8  Actors and relations (loading / access)
# ════════════════════════════════════════════════════════════════════════════

def charger_acteurs(campagne: Path) -> dict:
    """Load actors.json → {'meta':…, 'actors':[…]}; {} if absent (fail-open)."""
    act = charger_json(Path(campagne) / "actors.json", {})
    return act if isinstance(act, dict) else {}


def index_acteurs(acteurs: dict) -> dict[str, dict]:
    """Index by id → actor."""
    idx: dict[str, dict] = {}
    if not isinstance(acteurs, dict):
        return idx
    for a in acteurs.get("actors", []) or []:
        if isinstance(a, dict) and isinstance(a.get("id"), str):
            idx[a["id"]] = a
    return idx


def trajectoire_de(acteur: dict) -> list[dict]:
    """Return acteur['trajectory'] or [].

    Backward-compat: if 'trajectory' is absent but 'localisation_id' is present,
    builds a stay [{'lieu':loc,'de':0,'a':null}].
    """
    if not isinstance(acteur, dict):
        return []
    traj = acteur.get("trajectory")
    if isinstance(traj, list) and traj:
        return traj
    loc = acteur.get("localisation_id")
    if isinstance(loc, str) and loc:
        return [{"lieu": loc, "de": 0, "a": None}]
    return []


def relations_de(acteur: dict) -> list[dict]:
    """Return acteur['relations'] or []."""
    if not isinstance(acteur, dict):
        return []
    rels = acteur.get("relations")
    return [r for r in rels if isinstance(r, dict)] if isinstance(rels, list) else []


def relations_vers(acteurs: dict, cible_id: str) -> list[tuple[str, dict]]:
    """All relations (acteur_source_id, relation) pointing 'vers' cible_id.

    Used by the RELATIONAL FILTER in scene_brief and for causal propagation.
    """
    resultat: list[tuple[str, dict]] = []
    idx = index_acteurs(acteurs)
    for src_id, acteur in idx.items():
        for rel in relations_de(acteur):
            if rel.get("vers") == cible_id:
                resultat.append((src_id, rel))
    return resultat


# ════════════════════════════════════════════════════════════════════════════
# 3.9  "Pinned" deadlines (bridge between clock.py and T)
# ════════════════════════════════════════════════════════════════════════════

def echeance_en_t(echeance, campagne: Path) -> int | None:
    """Convert a deadline to T (UT). Accepts:

      * an int (already in UT) → as-is;
      * the PINNED format from clock.py {texte,unite,min,max,ancre,statut}:
          unite 'ut'   → ancre + max(UT);
          unite 'jour' → jour_heure_vers_t(ancre + max, 12, 0)  (noon by default);
      * a free-form STRING ('Dans 2-3 semaines…') → None (not machine-datable).

    For a range, takes the HIGH bound (max) = "at the latest" deadline
    (cf. 02§plan). If only 'min' is provided, it serves as the high bound.
    """
    # int already in UT (and not a bool, which is an int in Python).
    if isinstance(echeance, bool):
        return None
    if isinstance(echeance, int):
        return echeance

    if isinstance(echeance, dict) and "texte" in echeance:
        unite = str(echeance.get("unite") or "jour").lower()
        ancre = echeance.get("ancre")
        mx = echeance.get("max")
        mn = echeance.get("min")
        if not isinstance(ancre, int):
            ancre = 0
        borne = mx if isinstance(mx, int) else (mn if isinstance(mn, int) else None)
        if borne is None:
            return None
        if unite == "ut":
            return ancre + borne
        # unit 'jour' (default) → noon of day (ancre + borne).
        return jour_heure_vers_t(ancre + borne, 12, 0)

    # Free-form string or unhandled type: not machine-datable.
    return None


# ════════════════════════════════════════════════════════════════════════════
#  Demo  (direct execution: `python3 worldlib.py [<campaign>]`)
# ════════════════════════════════════════════════════════════════════════════

def _demo(argv: list[str]) -> int:
    """Small NON-DESTRUCTIVE demonstration of worldlib building blocks.

    If a campaign path is provided as an argument, reads (READ-ONLY) its
    `regles.temps.deplacements` matrix, derives an MDS anchor from it and
    displays the stress. Writes NOTHING. Serves as a manual smoke-test.
    """
    print("worldlib — demonstration (pure stdlib, non-destructive)\n")

    # 1) Time conversions.
    print("• Time conversions")
    for T in (0, 936, 3960):
        j, h, m = t_vers_jour_heure(T)
        print(f"    T={T:>5}  →  (jour={j}, {h:02d}h{m:02d})  →  « {t_vers_narratif(T)} »")
    assert jour_heure_vers_t(7, 12, 0) == 936, "anchor Day 7 noon must equal 936"
    assert t_vers_jour_heure(0) == (1, 0, 0)
    print(f"    jour_heure_vers_t(7,12,0) = {jour_heure_vers_t(7, 12, 0)}  (expected 936)")

    # 2) Durations → UT.
    print("\n• Narrative durations → UT")
    for d in ("40min", "1h30", "20min", "5h45 — desc", "~4h", "Distance inconnue"):
        print(f"    « {d:<22} »  →  {parser_duree_minutes(d):>4} min  →  "
              f"{minutes_vers_ut(max(parser_duree_minutes(d), 0))} UT")
    assert minutes_vers_ut(40) == 4 and minutes_vers_ut(20) == 2 and minutes_vers_ut(90) == 9

    # 3) Slug.
    print("\n• Slugification")  # "Slugification" is a technical term, intentionally unchanged
    for s in ("Vieux Moulin", "Poste n°6 — Limite Nord",
              "lieu:<region>/<Lieu Accentué>"):
        print(f"    « {s} »  →  {slug(s)}")

    # 4) MDS on the real matrix (if a campaign is provided), otherwise on a toy set.
    print("\n• Anchor MDS (SMACOF stdlib)")
    deplacements = None
    idx_labels: dict[str, str] = {}
    if len(argv) > 1:
        camp = chemin_campagne(argv[1])
        monde = charger_json(camp / "world.json", {})
        deplacements = monde.get("rules", {}).get("time", {}).get("movements")
        idx_labels = index_labels(monde)
        if deplacements:
            print(f"    source: {camp / 'world.json'} → regles.temps.deplacements")

    if not deplacements:
        # Toy set: ~unit square (durations in minutes). No campaign provided:
        # we build a small ad hoc labels→id index (the engine never guesses the
        # geography, so it must be fed — here hardcoded IN THE DEMO only).
        deplacements = {
            "depuis_a_vers": {
                "b": "40min",
                "c": "20min",
                "d": "1h30",
                "e": "1h30",
            },
            "entre": {
                "e_vers_f": "20min",
            },
        }
        idx_labels = {lab: f"lieu:demo/{lab}" for lab in ("a", "b", "c", "d", "e", "f")}
        print("    source: built-in toy set (no campaign provided)")

    ids, D = matrice_durees(deplacements, idx_labels)
    coords = ancrer_mds(ids, D, iterations=300, seed=42)
    stress = stress_normalise(ids, D, coords)
    print(f"    {len(ids)} locations anchored; normalized stress = {stress:.4f}")
    for nid in ids[:6]:
        print(f"      {nid:<48} → (x={coords[nid]['x']:>4}, y={coords[nid]['y']:>4})")
    if len(ids) > 6:
        print(f"      … (+{len(ids) - 6} more)")

    # 5) Toy trajectory (validation + position).
    print("\n• Trajectory (position = f(time))")
    geo_jouet = {
        "locations": [
            {"id": "A", "parent": None, "ancrage": {"x": 0, "y": 0},
             "aretes": [{"vers": "B", "dir": "E", "temps_ut": 6, "distance_m": 100}]},
            {"id": "B", "parent": None, "ancrage": {"x": 60, "y": 0}, "aretes": []},
        ]
    }
    traj = [
        {"lieu": "A", "de": 0, "a": 10},
        {"type": "deplacement", "de": 10, "a": 16, "chemin": ["A", "B"], "motif": "test"},
        {"lieu": "B", "de": 16, "a": None},
    ]
    viol = valider_trajectoire(geo_jouet, traj)
    print(f"    violations = {viol if viol else 'none'}")
    for T in (5, 13, 20):
        p = position_a(geo_jouet, traj, T)
        print(f"    T={T:>3} → lieu={p['lieu']}  (x={p['x']:.1f}, y={p['y']:.1f})  "
              f"en_mouvement={p['en_mouvement']}")

    print("\n✅ Demonstration complete (no writes).")
    return 0


if __name__ == "__main__":
    sys.exit(_demo(sys.argv))
