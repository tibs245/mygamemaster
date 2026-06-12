#!/usr/bin/env python3
"""
clock.py — Faction clock advancer for MJ Tonnerre.

Reads `etat_global.faction_actions_horloge`, computes the CURRENT GAME TIME
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

Current game time (reuses the heuristic from check_session.py):
  - UT regime      → last `t` from evenements.json (in UT)
  - narrative regime → max "Jour N" mentioned (chronology + sessions)
The `echeance.unite` field determines the comparison scale:
  - "ut"   → compare to current `t` (UT)
  - "jour" → compare to current day

Deadlines still in STRING FORMAT (free string, not migrated): ignored and
FLAGGED (they cannot be advanced by machine).

Usage:
  python3 clock.py <path/campaign>                 # --dry-run (default): report only
  python3 clock.py <path/campaign> --apply         # writes status to monde.json
  python3 clock.py <path/campaign> --json          # machine report
  python3 clock.py <path/campaign> --faction NAME  # filter one faction

Exit codes:
  0  no overdue deadline (there may still be "approche" / flagged strings)
  1  at least one OVERDUE unresolved deadline (consequence to play out)
  2  usage error (campaign/files not found)
"""

import argparse
import json
import re
import sys
import unicodedata
from pathlib import Path


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

def est_regime_ut(monde: dict) -> bool:
    """True if the campaign is running in UT regime (Time Units)."""
    temps = monde.get("meta", {}).get("temps", {})
    regime = str(temps.get("regime", "")).lower()
    if "ut" in regime:
        return True
    # Fallback: presence of units_per_day = effective UT config
    return bool(temps.get("units_per_day"))


def unite_attendue(monde: dict) -> str:
    """Expected deadline unit according to the regime (UT → 'ut', otherwise 'jour')."""
    return "ut" if est_regime_ut(monde) else "jour"


def t_courant_ut(campagne: Path, monde: dict) -> int:
    """Current game time in UT: last `t` from evenements.json.
    Fallback: meta.temps suivi.t_actuel, then 0."""
    evt_path = campagne / "evenements.json"
    if evt_path.exists():
        try:
            data = charger_json(evt_path)
            ts = [e["t"] for e in data.get("evenements", [])
                  if isinstance(e.get("t"), int)]
            if ts:
                return max(ts)
            meta_t = data.get("meta", {}).get("dernier_t_enregistre")
            if isinstance(meta_t, int):
                return meta_t
        except (OSError, json.JSONDecodeError, KeyError):
            pass
    suivi = monde.get("regles", {}).get("temps", {}).get("suivi", {})
    if isinstance(suivi.get("t_actuel"), int):
        return suivi["t_actuel"]
    return 0


def jour_courant(campagne: Path, monde: dict) -> int:
    """Current game day (narrative regime), same heuristic as
    check_session.py: max "Jour N" mentioned in the chronology + sessions;
    in UT regime, derived from current t / units_per_day. Min 1."""
    jours = {1}

    temps = monde.get("meta", {}).get("temps", {})
    upd = temps.get("units_per_day")
    if upd:
        t = t_courant_ut(campagne, monde)
        jours.add(t // upd + 1)

    chrono = monde.get("etat_global", {}).get("chronologie", "")
    if isinstance(chrono, str):
        for m in re.findall(r"[Jj]our\s+(\d+)", chrono):
            jours.add(int(m))

    sessions_dir = campagne / "sessions"
    if sessions_dir.is_dir():
        for sp in sessions_dir.glob("*.json"):
            try:
                for m in re.findall(r"[Jj]our\s+(\d+)",
                                    sp.read_text(encoding="utf-8")):
                    jours.add(int(m))
            except OSError:
                pass

    return max(jours)


def temps_courant(campagne: Path, monde: dict) -> dict:
    """Returns both current time scales: {'ut': int, 'jour': int}."""
    return {
        "ut": t_courant_ut(campagne, monde),
        "jour": jour_courant(campagne, monde),
    }


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
    monde = charger_json(campagne / "monde.json")
    courant = temps_courant(campagne, monde)
    unite_camp = unite_attendue(monde)

    horloge = monde.get("etat_global", {}).get("faction_actions_horloge", {})
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
        "temps_courant": courant,
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
    statuses modified. Rewrites monde.json (atomic via temporary file)."""
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
        chemin = campagne / "monde.json"
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


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="clock.py",
        description="Advances the faction clock according to the pinned deadline format.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python3 clock.py .hermes/mj-tonnerre/campagnes/la-naissance-dun-roi\n"
            "  python3 clock.py <campagne> --apply\n"
            "  python3 clock.py <campagne> --faction 'La Bande du Corbeau' --json\n"
        ),
    )
    parser.add_argument("campagne", help="Path to the campaign folder.")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", default=True,
                      help="Report only, write nothing (DEFAULT).")
    mode.add_argument("--apply", action="store_true",
                      help="Writes echeance.statut to monde.json.")
    parser.add_argument("--faction", default=None,
                        help="Filter on one faction (name).")
    parser.add_argument("--json", action="store_true", dest="as_json",
                        help="Output in JSON format.")
    parser.add_argument("--quiet", action="store_true",
                        help="Minimal output (for cron/pipeline use).")
    args = parser.parse_args(argv)

    campagne = Path(args.campagne)
    if not campagne.is_dir():
        print(f"❌ Campaign not found: {campagne}", file=sys.stderr)
        return 2
    if not (campagne / "monde.json").exists():
        print(f"❌ monde.json not found in {campagne}", file=sys.stderr)
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
        return 1 if rapport["n_echue"] else 0

    tc = rapport["temps_courant"]
    en_tete = (f"⏱  Clock — {Path(rapport['campagne']).name} "
               f"(regime {rapport['regime_unite']}) — "
               f"day {tc['jour']} / t={tc['ut']} UT — "
               f"mode {'APPLY' if args.apply else 'dry-run'}")
    print(en_tete)

    if not rapport["items"] and not rapport["chaines_ignorees"]:
        print("ℹ No deadline in faction_actions_horloge.")
        return 0

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
        bilan += f" {n_modif} status(es) written to monde.json."
    print(bilan)

    return 1 if rapport["n_echue"] else 0


if __name__ == "__main__":
    sys.exit(main())
