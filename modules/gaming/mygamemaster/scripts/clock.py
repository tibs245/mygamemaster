#!/usr/bin/env python3
"""
clock.py — Faction clock advancer for MJ Tonnerre.

Reads `global_state.faction_actions_horloge`, computes the CURRENT GAME TIME
deterministically, and for each action in PINNED DEADLINE format marks its
status:

  - "approche" if current >= anchor + min (and current < anchor + max)
  - "echue"    if current >= anchor + max
  - "en_cours" otherwise

The computed STATUS is written to `echeance.statut` only in --apply mode
(deadlines already "resolue" are left intact: a resolution is a
narrative GM decision, never overwritten by the machine).

PINNED deadline format consumed EXACTLY (cf. mission):
  "echeance": {
    "texte": "<original phrase preserved word for word>",
    "unite": "jour" | "ut",        # UT → "ut", otherwise "jour"
    "min": <int|null>,             # lower bound, in units, counted from "ancre"
    "max": <int|null>,             # upper bound if range; otherwise equals min
    "ancre": <int>,                # game time (current day / t UT) at placement
    "statut": "en_cours" | "echue" | "resolue"
  }

Current game time:
  - UT regime      → last `t` from events.json (in UT)
  - narrative regime → the day the fiction is AT, i.e. the latest "Day N" /
    "Jour N" that OPENS an entry in the chronology or a session log. A day
    written mid-sentence ("the levy must arrive by Day 63") is a future date,
    not a clock reading, and is deliberately not counted.
The `echeance.unite` field determines the comparison scale:
  - "ut"   → compare to current `t` (UT)
  - "jour" → compare to current day

Deadlines still in STRING FORMAT (free string, not migrated): ignored and
FLAGGED (they cannot be advanced by machine).

DRIFT DETECTION (TIME-03 / TIME-04). Several files write game time
independently (the clock declared in world.json, events.json, the "Day N"
mentioned in the chronology and the session logs, the living-world events
emitted by world_tick.py). On a real campaign they diverged by 51 days without
anyone noticing. `detecter_derive` converts every source to a game DAY and
compares them against each other; the spread is reported in every mode and is a
business failure (exit 1) above `TOLERANCE_DERIVE_JOURS`. A temporal file that
exists but cannot be read is an anomaly, never a dropped source: a dropped
source reads as an agreeing one.

Anomalies carry `bloquant`. Only those meaning the clock itself is untrustworthy
(rejected unit override, resolved event dated in the future, unreadable temporal
file) fail; an undatable deadline or a fantasy calendar are reported and let the
close proceed.

Usage:
  python3 clock.py <path/campaign>                 # --dry-run (default): report only
  python3 clock.py <path/campaign> --apply         # writes status to world.json
  python3 clock.py <path/campaign> --json          # machine report
  python3 clock.py <path/campaign> --faction NAME  # filter one faction
  python3 clock.py <path/campaign> --drift         # temporal sources only

Exit codes:
  0  no overdue deadline, sources agree
  1  at least one OVERDUE unresolved deadline (consequence to play out)
     and/or the temporal sources DIVERGE (drift)
  2  usage error (campaign/files not found)

Escape hatch: MGM_ALLOW_CLOCK_DRIFT=1 makes a detected drift non-fatal (still
reported, loudly). For a live campaign whose drift the GM judged narratively
acceptable — it does NOT fix anything.
"""

import argparse
import json
import os
import re
import sys
import unicodedata
from pathlib import Path

import worldlib as WL


# ─── The time unit, IN CODE (TIME-01) — meta.time only OVERRIDES these ───────
MINUTES_PAR_UT = 10
UT_PAR_HEURE = 6
UT_PAR_JOUR = 144
MINUTES_PAR_JOUR = 24 * 60

# ─── Drift detection — one writer owns game time (TIME-03 / TIME-04) ─────────
# Absorbs "Day N" vs T-converted-from-UT rounding, not a real drift (+51 days).
TOLERANCE_DERIVE_JOURS = 1

ENV_ALLOW_DERIVE = "MGM_ALLOW_CLOCK_DRIFT"
ENV_TOLERANCE_DERIVE = "MGM_CLOCK_DRIFT_TOLERANCE_DAYS"

_STATUTS_RESOLUS = ("resolu", "resolue", "resolved", "accompli", "accomplished")

_ANOMALIES_BLOQUANTES = frozenset((
    "config_temps_invalide",
    "evenement_resolu_dans_le_futur",
    "source_temporelle_illisible",
))


def _anomalie(code: str, message: str) -> dict:
    """An anomaly, flagged `bloquant` only when the clock itself is untrustworthy.

    A hand-written deadline and a fantasy calendar are documented as legitimate:
    reporting them is right, refusing the close over them is not — the GM would
    set the drift override permanently and neutralise every temporal gate.
    """
    return {"code": code, "message": message,
            "bloquant": code in _ANOMALIES_BLOQUANTES}


def derive_autorisee() -> bool:
    """True when the operator explicitly accepts a divergent clock.

    Same shape as load_campaign._env_autorise_legacy: an escape hatch exists so a
    live campaign stays closable, and it is loud everywhere it applies.
    """
    return os.environ.get(ENV_ALLOW_DERIVE, "").strip().lower() in (
        "1", "true", "yes", "on")


def tolerance_derive() -> int:
    """Accepted spread in days (env MGM_CLOCK_DRIFT_TOLERANCE_DAYS, else default)."""
    brut = os.environ.get(ENV_TOLERANCE_DERIVE, "").strip()
    if brut:
        try:
            valeur = int(brut)
        except ValueError:
            return TOLERANCE_DERIVE_JOURS
        if valeur >= 0:
            return valeur
    return TOLERANCE_DERIVE_JOURS


# ─── Normalisation (consistent with check_session.py) ───────────────────────

def normaliser(nom: str) -> str:
    if not nom:
        return ""
    s = unicodedata.normalize("NFKD", nom)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.lower()
    s = re.sub(r"[^a-z0-9\s]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def charger_json(chemin: Path):
    with open(chemin, "r", encoding="utf-8") as f:
        return json.load(f)


# ─── Time regime ─────────────────────────────────────────────────────────────

def _bloc_temps(monde) -> dict:
    """`world.json > meta.time`, or {} — tolerant of any malformed ancestor."""
    meta = monde.get("meta") if isinstance(monde, dict) else None
    temps = meta.get("time") if isinstance(meta, dict) else None
    return temps if isinstance(temps, dict) else {}


def config_temps(monde) -> dict:
    """Resolve the time-unit convention: CODE defaults + VALIDATED meta.time override.

    Returns {'minutes_par_ut', 'ut_par_jour', 'source', 'anomalies'} where
    `source` is 'code' or 'world.json>meta.time' and `anomalies` is a list of
    {'code','message'}.

    An override that is not a strictly positive int is REJECTED (the code default
    applies) instead of being propagated: `units_per_day: 0` or `"144"` turns
    every day computation into a crash or into garbage. A day that does not add
    up to 1440 min is kept — a campaign may run a fantasy calendar — but is
    reported, because it is far more often a typo.
    """
    temps = _bloc_temps(monde)
    anomalies: list[dict] = []
    surcharge = False

    def _entier_positif(cle: str, defaut: int) -> int:
        nonlocal surcharge
        if cle not in temps:
            return defaut
        val = temps.get(cle)
        if isinstance(val, bool) or not isinstance(val, int) or val <= 0:
            anomalies.append(_anomalie(
                "config_temps_invalide",
                f"meta.time.{cle} = {val!r} is not a strictly positive "
                f"integer — override REJECTED, code default {defaut} used"))
            return defaut
        surcharge = True
        return val

    ut_par_jour = _entier_positif("units_per_day", UT_PAR_JOUR)
    minutes_par_ut = _entier_positif("time_unit_minutes", MINUTES_PAR_UT)

    if ut_par_jour * minutes_par_ut != MINUTES_PAR_JOUR:
        anomalies.append(_anomalie(
            "config_temps_incoherente",
            f"meta.time declares a day of {ut_par_jour * minutes_par_ut} min "
            f"({ut_par_jour} UT × {minutes_par_ut} min) instead of "
            f"{MINUTES_PAR_JOUR} — override kept, every UT↔day conversion "
            "runs on that scale"))

    return {
        "minutes_par_ut": minutes_par_ut,
        "ut_par_jour": ut_par_jour,
        "source": "world.json>meta.time" if surcharge else "code",
        "anomalies": anomalies,
    }


def unites_par_jour(monde) -> int:
    """UT per game day, from the code constant or a validated meta.time override."""
    return config_temps(monde)["ut_par_jour"]


def est_regime_ut(monde: dict) -> bool:
    """True if the campaign is running in UT regime (Time Units)."""
    temps = _bloc_temps(monde)
    regime = str(temps.get("regime", "")).lower()
    if "ut" in regime:
        return True
    # Declaring units_per_day at all = an effective UT configuration.
    return bool(temps.get("units_per_day"))


def unite_attendue(monde: dict) -> str:
    """Expected deadline unit according to the regime (UT → 'ut', otherwise 'jour')."""
    return "ut" if est_regime_ut(monde) else "jour"


def t_courant_ut(campagne: Path, monde: dict) -> int:
    """Current game time in UT: last `t` from events.json.
    Fallback: meta.temps suivi.t_actuel, then 0."""
    evt_path = campagne / "events.json"
    if evt_path.exists():
        try:
            data = charger_json(evt_path)
            ts = [e["t"] for e in data.get("events", [])
                  if isinstance(e.get("t"), int)]
            if ts:
                return max(ts)
            meta_t = data.get("meta", {}).get("dernier_t_enregistre")
            if isinstance(meta_t, int):
                return meta_t
        except (OSError, json.JSONDecodeError, KeyError):
            pass
    suivi = monde.get("rules", {}).get("time", {}).get("tracking", {})
    if isinstance(suivi.get("t_actuel"), int):
        return suivi["t_actuel"]
    return 0


def jour_narratif_source(campagne: Path, monde: dict) -> dict:
    """The day the FICTION is at — {'jour': int|None, 'ancre': bool, 'detail': str}.

    Delegates to `worldlib.jour_narratif_source`: one scanner owns "Day N" /
    "Jour N" so clock.py and world_tick cannot date the same fiction differently.
    Only mentions that ANCHOR an entry count as the present; a deadline or a
    teaser written in prose ("the levy must arrive by Day 63") is a future date,
    not a clock, and reading it as one refuses a perfectly coherent campaign.
    """
    return WL.jour_narratif_source(campagne, monde)


def jour_narratif(campagne: Path, monde: dict) -> int | None:
    """Game day the fiction is at, or None. See `jour_narratif_source`."""
    return jour_narratif_source(campagne, monde)["jour"]


def jour_courant(campagne: Path, monde: dict) -> int:
    """Current game day (narrative regime): the day the fiction is at (cf.
    `jour_narratif`); in UT regime, also derived from current t / units_per_day.
    Min 1."""
    jours = {1}

    if est_regime_ut(monde):
        upd = unites_par_jour(monde)
        jours.add(t_courant_ut(campagne, monde) // upd + 1)

    narratif = jour_narratif(campagne, monde)
    if narratif is not None:
        jours.add(narratif)

    return max(jours)


def temps_courant(campagne: Path, monde: dict) -> dict:
    """Returns both current time scales: {'ut': int, 'jour': int}."""
    return {
        "ut": t_courant_ut(campagne, monde),
        "jour": jour_courant(campagne, monde),
    }


# ─── Drift: comparing the temporal sources against each other ────────────────

def _charger_temporel(chemin: Path) -> tuple[object, str]:
    """(data, error) for a temporal file. Absent → (None, ""), unusable → (None, why).

    A dropped source reads as an agreeing source, so a file that exists and
    cannot be used has to come back as a REASON, never as silence: hiding it
    here is the very fail-open this module exists to remove (TIME-04).
    """
    if not chemin.exists():
        return None, ""
    try:
        data = charger_json(chemin)
    except (OSError, json.JSONDecodeError) as e:
        return None, f"{chemin.name} unreadable: {e}"
    if not isinstance(data, dict):
        return None, f"{chemin.name} is not a JSON object (got {type(data).__name__})"
    if not isinstance(data.get("events"), list):
        return None, (f"{chemin.name} has no usable 'events' list "
                      f"(got {type(data.get('events')).__name__})")
    return data, ""


def _t_entiers(data, cles=("t",)) -> list[int]:
    """Integer `t`/`T` values of an events container ({'events': [...]})."""
    if not isinstance(data, dict):
        return []
    out = []
    for evt in data.get("events", []) or []:
        if not isinstance(evt, dict):
            continue
        for cle in cles:
            val = evt.get(cle)
            if isinstance(val, int) and not isinstance(val, bool):
                out.append(val)
                break
    return out


def decalage_t(monde) -> int:
    """`meta.time.t_offset` — UT at campaign start (48 = 8am). 0 when unusable."""
    val = _bloc_temps(monde).get("t_offset")
    if isinstance(val, int) and not isinstance(val, bool) and val >= 0:
        return val
    return 0


def _jour_depuis_ut(t: int, upd: int, offset: int) -> int:
    """UT → game day, on the campaign's own origin (t_offset) and scale."""
    return (t - offset) // upd + 1


def sources_temporelles(campagne: Path, monde: dict) -> tuple[list[dict], list[dict]]:
    """(sources, anomalies): every INDEPENDENT writer of game time, as a game DAY.

    Four writers exist and none of them knows about the others — that is exactly
    how the corpus campaign ended up with four disagreeing clocks. A source that
    holds nothing is omitted rather than defaulted to day 1: a missing source is
    not an agreeing source. A source that EXISTS but cannot be used comes back as
    an anomaly, never as an omission.
    """
    upd = unites_par_jour(monde)
    offset = decalage_t(monde)
    regime_ut = est_regime_ut(monde)
    sources: list[dict] = []
    anomalies: list[dict] = []

    suivi = monde.get("rules", {}).get("time", {}).get("tracking", {}) \
        if isinstance(monde, dict) else {}
    jour_suivi = suivi.get("current_day") if isinstance(suivi, dict) else None
    if isinstance(jour_suivi, int) and not isinstance(jour_suivi, bool):
        sources.append({
            "id": "rules.time.tracking.current_day",
            "libelle": "in-game clock declared in world.json",
            "jour": jour_suivi,
            "detail": f"current_day={jour_suivi}",
        })

    echelle = f"÷ {upd} UT/day" if not offset \
        else f"− t_offset {offset} ÷ {upd} UT/day"

    evt, err = _charger_temporel(campagne / "events.json")
    if err:
        anomalies.append(_anomalie("source_temporelle_illisible", err))
    ts_events = _t_entiers(evt)
    if ts_events and not regime_ut:
        anomalies.append(_anomalie(
            "source_non_comparable",
            "events.json carries integer t but the campaign is not in UT regime — "
            "the unit those integers count is undeclared, so they cannot be "
            "converted to days; source left out of the comparison"))
    elif ts_events:
        t_max = max(ts_events)
        sources.append({
            "id": "events.json",
            "libelle": "temporal canon (events.json, integer t)",
            "jour": _jour_depuis_ut(t_max, upd, offset),
            "detail": f"max t={t_max} UT {echelle}",
        })

    narratif = jour_narratif_source(campagne, monde)
    if narratif["jour"] is not None:
        sources.append({
            "id": "narratif",
            "libelle": '"Day N" written in the chronology + session logs',
            "jour": narratif["jour"],
            "detail": narratif["detail"],
        })

    prog, err = _charger_temporel(campagne / "evenements_programmes.json")
    if err:
        anomalies.append(_anomalie("source_temporelle_illisible", err))
    ts_prog = _t_entiers(_resolus_seulement(prog), cles=("T", "t"))
    if ts_prog:
        t_max = max(ts_prog)
        sources.append({
            "id": "evenements_programmes.json",
            "libelle": "living-world clock (world_tick, resolved events)",
            "jour": _jour_depuis_ut(t_max, upd, offset),
            "detail": f"max resolved T={t_max} UT {echelle}",
        })

    return sources, anomalies


def _resolus_seulement(prog):
    """Sub-container holding only the events whose status says they HAPPENED.

    A *scheduled* event carries a future T; counting it as elapsed time makes the
    world clock run ahead of the fiction on its own.
    """
    if not isinstance(prog, dict):
        return None
    events = [e for e in prog.get("events", []) or []
              if isinstance(e, dict)
              and str(e.get("statut", "")).strip().lower() in _STATUTS_RESOLUS]
    return {"events": events}


def _anomalies_evenements(campagne: Path, monde: dict,
                          jour_reference: int | None) -> list[dict]:
    """Resolved events dated AFTER the reference day (the corpus had four)."""
    if jour_reference is None:
        return []
    data, _ = _charger_temporel(campagne / "evenements_programmes.json")
    prog = _resolus_seulement(data)
    if prog is None:
        return []
    upd = unites_par_jour(monde)
    offset = decalage_t(monde)
    futurs = []
    for evt in prog["events"]:
        t = evt.get("T", evt.get("t"))
        if not isinstance(t, int) or isinstance(t, bool):
            continue
        jour = _jour_depuis_ut(t, upd, offset)
        if jour > jour_reference:
            futurs.append((evt.get("id", "(no id)"), jour))
    if not futurs:
        return []
    apercu = " ; ".join(f"{eid} → day {j}" for eid, j in futurs[:5])
    if len(futurs) > 5:
        apercu += f" ; …(+{len(futurs) - 5})"
    return [_anomalie(
        "evenement_resolu_dans_le_futur",
        f"{len(futurs)} event(s) marked resolved but dated AFTER the "
        f"current day ({jour_reference}): {apercu}")]


def _anomalies_echeances(monde: dict) -> list[dict]:
    """Deadlines still written as free strings: undatable, hence uncheckable."""
    horloge = monde.get("global_state", {}).get("faction_actions_horloge", {}) \
        if isinstance(monde, dict) else {}
    entrees = horloge.get("actions", []) if isinstance(horloge, dict) else []
    brutes = []
    for entry in entrees:
        if not isinstance(entry, dict):
            continue
        for action in entry.get("actions_en_cours", []) or []:
            if isinstance(action, dict) and not est_echeance_objet(action.get("echeance")):
                brutes.append(f"[{entry.get('faction', '?')}] "
                              f"{action.get('action', '(action ?)')}")
    if not brutes:
        return []
    apercu = " ; ".join(brutes[:5])
    if len(brutes) > 5:
        apercu += f" ; …(+{len(brutes) - 5})"
    return [_anomalie(
        "echeance_non_datable",
        f"{len(brutes)} deadline(s) still in free-string form, so no machine can "
        f"tell whether they elapsed — pin them to advance them: {apercu}")]


def detecter_derive(campagne: Path, monde: dict | None = None,
                    tolerance: int | None = None) -> dict:
    """Compare the temporal sources AGAINST EACH OTHER (TIME-03).

    Returns {'sources', 'jour_min', 'jour_max', 'ecart', 'jour_reference',
    'tolerance', 'derive': bool, 'anomalies', 'override'}.

    `derive` is True as soon as the spread between two sources exceeds the
    tolerance. `anomalies` collects the incoherences a spread cannot express;
    each carries its own `bloquant` flag so a caller weighs them instead of
    folding a hand-written deadline into a clock-divergence refusal.
    """
    campagne = Path(campagne)
    if monde is None:
        monde = charger_json(campagne / "world.json")
    if tolerance is None:
        tolerance = tolerance_derive()

    sources, anomalies = sources_temporelles(campagne, monde)
    jours = [s["jour"] for s in sources]
    jour_min = min(jours) if jours else None
    jour_max = max(jours) if jours else None
    ecart = (jour_max - jour_min) if jours else 0

    declaree = next((s["jour"] for s in sources
                     if s["id"] == "rules.time.tracking.current_day"), None)
    jour_reference = declaree if declaree is not None else jour_max

    anomalies = list(config_temps(monde)["anomalies"]) + anomalies
    anomalies += _anomalies_evenements(campagne, monde, jour_reference)
    anomalies += _anomalies_echeances(monde)

    return {
        "sources": sources,
        "jour_min": jour_min,
        "jour_max": jour_max,
        "jour_reference": jour_reference,
        "ecart": ecart,
        "tolerance": tolerance,
        "derive": ecart > tolerance,
        "anomalies": anomalies,
        "override": derive_autorisee(),
    }


def anomalies_bloquantes(derive: dict) -> list[dict]:
    """Anomalies that make the clock unverifiable, hence refuse the close."""
    return [a for a in (derive or {}).get("anomalies") or [] if a.get("bloquant")]


def formater_derive(derive: dict) -> list[str]:
    """Human rendering of a drift report — one line per source, then the verdict."""
    lignes = ["🕰  Temporal sources (TIME-03 — one writer owns game time):"]
    if not derive["sources"]:
        lignes.append("   ⚠ no temporal source at all — the campaign has no clock "
                      "to check against.")
    for s in derive["sources"]:
        lignes.append(f"   • day {s['jour']:<5} {s['libelle']} ({s['detail']})")

    if derive["derive"]:
        lignes.append(f"   ❌ DRIFT: {derive['ecart']} day(s) between the sources "
                      f"(day {derive['jour_min']} … {derive['jour_max']}, "
                      f"tolerance {derive['tolerance']}).")
    elif anomalies_bloquantes(derive):
        lignes.append(f"   ⚠ the {len(derive['sources'])} READABLE source(s) are "
                      f"{derive['ecart']} day(s) apart — the comparison is "
                      "incomplete, see below.")
    elif len(derive["sources"]) >= 2:
        lignes.append(f"   ✅ sources agree (spread {derive['ecart']} day(s), "
                      f"tolerance {derive['tolerance']}).")
    elif derive["sources"]:
        # A single clock cannot agree with anything: a green tick here would
        # assert a comparison that never happened.
        lignes.append("   ℹ only 1 temporal source — nothing to compare it "
                      "against, divergence NOT ruled out.")
    for a in derive["anomalies"]:
        marque = "❌" if a.get("bloquant") else "⚠"
        lignes.append(f"   {marque} {a['code']}: {a['message']}")
    if (derive["derive"] or anomalies_bloquantes(derive)) and derive["override"]:
        lignes.append(f"   ⚠ {ENV_ALLOW_DERIVE}=1 — divergence ACCEPTED by the "
                      "operator, nothing was fixed.")
    return lignes


# ─── Deadline evaluation ─────────────────────────────────────────────────────

def est_echeance_objet(ech) -> bool:
    """True if the deadline is in PINNED format (object) rather than a string."""
    return isinstance(ech, dict) and "texte" in ech


def courant_pour_unite(courant: dict, unite: str) -> int:
    """Returns the current time in the deadline's unit."""
    return courant.get(unite, courant.get("jour", 0))


def evaluer_echeance(ech: dict, courant: dict) -> dict:
    """Evaluates a OBJECT deadline. Returns:
        {"statut_calcule": "en_cours"|"approche"|"echue"|"resolue",
         "courant": int, "seuil_min": int|None, "seuil_max": int|None,
         "unite": str}
    A deadline already "resolue" is left as-is (GM decision)."""
    statut_actuel = str(ech.get("statut", "en_cours"))
    unite = str(ech.get("unite") or "jour")
    cour = courant_pour_unite(courant, unite)

    if statut_actuel == "resolue":
        return {"statut_calcule": "resolue", "courant": cour,
                "seuil_min": None, "seuil_max": None, "unite": unite}

    ancre = ech.get("ancre")
    mn = ech.get("min")
    mx = ech.get("max")
    if not isinstance(ancre, int):
        ancre = 0
    seuil_min = ancre + mn if isinstance(mn, int) else None
    seuil_max = ancre + mx if isinstance(mx, int) else None
    # Tolerance: if only one bound is provided, the other equals it.
    if seuil_max is None:
        seuil_max = seuil_min
    if seuil_min is None:
        seuil_min = seuil_max

    if seuil_max is not None and cour >= seuil_max:
        statut = "echue"
    elif seuil_min is not None and cour >= seuil_min:
        statut = "approche"
    else:
        statut = "en_cours"

    return {"statut_calcule": statut, "courant": cour,
            "seuil_min": seuil_min, "seuil_max": seuil_max, "unite": unite}


# ─── Full analysis ───────────────────────────────────────────────────────────

def analyser(campagne: Path, filtre_faction: str | None) -> dict:
    monde = charger_json(campagne / "world.json")
    courant = temps_courant(campagne, monde)
    unite_camp = unite_attendue(monde)

    horloge = monde.get("global_state", {}).get("faction_actions_horloge", {})
    entrees = horloge.get("actions", []) if isinstance(horloge, dict) else []

    filtre = normaliser(filtre_faction) if filtre_faction else None

    items = []          # evaluated OBJECT deadlines
    chaines = []        # deadlines still in string format (flagged, ignored)

    for entry in entrees:
        if not isinstance(entry, dict):
            continue
        fnom = entry.get("faction", "(faction ?)")
        if filtre and normaliser(fnom) != filtre:
            continue
        for action in entry.get("actions_en_cours", []):
            if not isinstance(action, dict):
                continue
            label = action.get("action", "(action ?)")
            ech = action.get("echeance")

            if est_echeance_objet(ech):
                ev = evaluer_echeance(ech, courant)
                items.append({
                    "faction": fnom,
                    "action": label,
                    "texte": ech.get("texte", ""),
                    "unite": ev["unite"],
                    "statut_actuel": ech.get("statut", "en_cours"),
                    "statut_calcule": ev["statut_calcule"],
                    "courant": ev["courant"],
                    "seuil_min": ev["seuil_min"],
                    "seuil_max": ev["seuil_max"],
                    "consequence": action.get("consequence", ""),
                    "_ref": ech,  # live reference for --apply
                })
            else:
                chaines.append({
                    "faction": fnom,
                    "action": label,
                    "echeance_brute": ech if isinstance(ech, str) else str(ech),
                })

    n_echue = sum(1 for it in items
                  if it["statut_calcule"] == "echue"
                  and it["statut_actuel"] != "resolue")
    n_approche = sum(1 for it in items if it["statut_calcule"] == "approche")

    return {
        "campagne": str(campagne),
        "regime_unite": unite_camp,
        "config_temps": {k: v for k, v in config_temps(monde).items()
                         if k != "anomalies"},
        "temps_courant": courant,
        "derive": detecter_derive(campagne, monde),
        "items": items,
        "chaines_ignorees": chaines,
        "n_items": len(items),
        "n_echue": n_echue,
        "n_approche": n_approche,
        "n_chaines": len(chaines),
        "_monde": monde,  # for --apply
    }


def appliquer(rapport: dict, campagne: Path) -> int:
    """Writes the computed status to echeance.statut (--apply mode).
    Does not touch deadlines already 'resolue'. Returns the number of
    statuses modified. Rewrites world.json (atomic via temporary file)."""
    n_modif = 0
    for it in rapport["items"]:
        ref = it.get("_ref")
        if not isinstance(ref, dict):
            continue
        if ref.get("statut") == "resolue":
            continue
        nouveau = it["statut_calcule"]
        # 'approche' is not a status in the pinned schema: it is a report signal.
        # The persisted status stays within {en_cours, echue, resolue}.
        statut_persiste = "echue" if nouveau == "echue" else "en_cours"
        if ref.get("statut") != statut_persiste:
            ref["statut"] = statut_persiste
            n_modif += 1

    if n_modif:
        monde = rapport["_monde"]
        chemin = campagne / "world.json"
        tmp = chemin.with_suffix(".json.tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(monde, f, ensure_ascii=False, indent=2)
            f.write("\n")
        tmp.replace(chemin)
    return n_modif


# ─── CLI ─────────────────────────────────────────────────────────────────────

def _nettoyer_pour_json(rapport: dict) -> dict:
    """Removes live references that are non-serialisable / bulky."""
    clean = {k: v for k, v in rapport.items() if k != "_monde"}
    clean["items"] = [{k: v for k, v in it.items() if k != "_ref"}
                      for it in rapport["items"]]
    return clean


def derive_bloquante(derive: dict) -> bool:
    """True when the clocks cannot be trusted AND the operator has not accepted it.

    Only a real spread and a BLOCKING anomaly count. An undatable deadline or a
    non-24h calendar are reported, never a refusal: there is nothing to
    resynchronise, and the only remedy on offer would be the drift override —
    which a GM then leaves on forever, disabling the gate this module is.
    """
    if not derive:
        return False
    return bool(derive.get("derive") or anomalies_bloquantes(derive)) \
        and not derive.get("override")


def code_sortie(rapport: dict, derive_seule: bool = False) -> int:
    """Exit code of a report: 1 on an overdue deadline OR an unaccepted drift.

    TIME-04 — this is the one place that decides, so `--json` and the human
    rendering can never disagree on the verdict. `derive_seule` (mode --drift)
    judges the clocks only, ignoring the deadlines that were not examined.
    """
    if not derive_seule and rapport.get("n_echue"):
        return 1
    return 1 if derive_bloquante(rapport.get("derive") or {}) else 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="clock.py",
        description="Advances the faction clock according to the pinned deadline format.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python3 clock.py .hermes/mygamemaster/campaigns/la-naissance-dun-roi\n"
            "  python3 clock.py <campagne> --apply\n"
            "  python3 clock.py <campagne> --faction 'La Bande du Corbeau' --json\n"
            "  python3 clock.py <campagne> --drift\n"
            "\n"
            f"{ENV_ALLOW_DERIVE}=1 accepts a detected drift (still reported).\n"
            f"{ENV_TOLERANCE_DERIVE}=<n> widens the accepted spread "
            f"(default {TOLERANCE_DERIVE_JOURS} day).\n"
        ),
    )
    parser.add_argument("campagne", help="Path to the campaign folder.")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", default=True,
                      help="Report only, write nothing (DEFAULT).")
    mode.add_argument("--apply", action="store_true",
                      help="Writes echeance.statut to world.json.")
    parser.add_argument("--faction", default=None,
                        help="Filter on one faction (name).")
    parser.add_argument("--json", action="store_true", dest="as_json",
                        help="Output in JSON format.")
    parser.add_argument("--quiet", action="store_true",
                        help="Minimal output (for cron/pipeline use).")
    parser.add_argument("--drift", action="store_true",
                        help="Temporal sources only: what each clock says and "
                             "how far apart they are.")
    args = parser.parse_args(argv)

    campagne = Path(args.campagne)
    if not campagne.is_dir():
        print(f"❌ Campaign not found: {campagne}", file=sys.stderr)
        return 2
    if not (campagne / "world.json").exists():
        print(f"❌ world.json not found in {campagne}", file=sys.stderr)
        return 2

    try:
        rapport = analyser(campagne, args.faction)
    except (json.JSONDecodeError, KeyError, OSError) as e:
        print(f"❌ Unreadable data: {e}", file=sys.stderr)
        return 2

    n_modif = 0
    if args.apply:
        n_modif = appliquer(rapport, campagne)
        rapport["statuts_modifies"] = n_modif

    if args.as_json:
        out = _nettoyer_pour_json(rapport)
        out["mode"] = "apply" if args.apply else "dry-run"
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return code_sortie(rapport)

    tc = rapport["temps_courant"]
    cfg = rapport["config_temps"]
    en_tete = (f"⏱  Clock — {Path(rapport['campagne']).name} "
               f"(regime {rapport['regime_unite']}) — "
               f"day {tc['jour']} / t={tc['ut']} UT — "
               f"1 UT = {cfg['minutes_par_ut']} min, "
               f"{cfg['ut_par_jour']} UT/day (source: {cfg['source']}) — "
               f"mode {'APPLY' if args.apply else 'dry-run'}")
    print(en_tete)

    print()
    for ligne in formater_derive(rapport["derive"]):
        print(ligne)
    print()

    if args.drift:
        return code_sortie(rapport, derive_seule=True)

    if not rapport["items"] and not rapport["chaines_ignorees"]:
        print("ℹ No deadline in faction_actions_horloge.")
        return code_sortie(rapport)

    marqueur = {"echue": "🔴", "approche": "🟠", "en_cours": "🟢", "resolue": "✅"}
    for it in rapport["items"]:
        if it["statut_actuel"] == "resolue":
            sc = "resolue"
        else:
            sc = it["statut_calcule"]
        seuil = (f"[{it['seuil_min']}→{it['seuil_max']} {it['unite']}]"
                 if it["seuil_min"] is not None else "[threshold ?]")
        print(f"{marqueur.get(sc, '•')} [{it['faction']}] {sc.upper()} "
              f"{seuil} current={it['courant']} — {it['action']}")
        if sc == "echue" and it["statut_actuel"] != "resolue" and not args.quiet:
            if it.get("consequence"):
                print(f"      ↳ consequence to play out: {it['consequence']}")

    if rapport["chaines_ignorees"] and not args.quiet:
        print()
        print("ℹ Deadlines still in STRING format (cannot be advanced by machine, "
              "ignored):")
        for c in rapport["chaines_ignorees"]:
            print(f"   ⤷ [{c['faction']}] « {c['echeance_brute']} » "
                  f"(action: {c['action']})")

    print()
    bilan = (f"Summary: {rapport['n_echue']} overdue, "
             f"{rapport['n_approche']} approaching, "
             f"{rapport['n_chaines']} unparsable string(s).")
    if args.apply:
        bilan += f" {n_modif} status(es) written to world.json."
    print(bilan)

    return code_sortie(rapport)


if __name__ == "__main__":
    sys.exit(main())
