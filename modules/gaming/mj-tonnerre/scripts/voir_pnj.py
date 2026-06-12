#!/usr/bin/env python3
"""
voir_pnj.py — READ-ONLY consultation of an NPC from npcs.json (GM side).

Replaces the recurring heredoc `python3 << EOF … for pnj in p: if name==… print …`
that the GM copies to re-read a sheet. Searches by name (exact case-insensitive,
then substring), displays ALL fields of the sheet, including
**GM secret fields** (`hypotheses_mj`, `notes_privees`, `derniere_interaction`).

NOT to be confused with `build_brief.py`: that one produces a *brief intended for
NPC agents* and **deliberately omits** secret fields (to avoid leaking them
to the agent). `voir_pnj.py` is the opposite: the COMPLETE view for the GM's eyes.
Never writes (read-only, like check_session.py).

Target: campaign (folder) OR direct path to npcs.json.

Usage:
  python3 voir_pnj.py <campagne> <name>            # full sheet, human-readable
  python3 voir_pnj.py <campagne> <name> --json     # raw NPC object (machine)
  python3 voir_pnj.py <campagne> --list           # list NPCs (+ location)
  python3 voir_pnj.py <campagne> <name> --max 1500 # truncate long fields
  python3 voir_pnj.py <npcs.json> <name>            # direct path

Exit codes:
  0  NPC found and displayed (or --list OK)
  1  NPC not found / ambiguous (multiple substring matches)
  2  usage error (npcs.json not found, unexpected structure, missing name)
"""

import argparse
import json
import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS_DIR))
try:
    import worldlib as W  # charger_json(), chemin_campagne() — loader helpers
    _charger = W.charger_json
    _resoudre = W.chemin_campagne
except Exception:  # fail-open: standalone if worldlib is unavailable
    def _charger(chemin, defaut=None):
        try:
            with open(chemin, "r", encoding="utf-8") as f:
                return json.load(f)
        except FileNotFoundError:
            return defaut
        except (OSError, json.JSONDecodeError, ValueError):
            return defaut

    def _resoudre(arg):
        return Path(arg).expanduser().resolve()


# Preferred display order; any field not in the list follows, sorted alpha. `illustration`
# (image path) is pushed to the end — visual noise for a GM read.
ORDRE = (
    "name", "titre", "description", "attitude", "relation_niveau",
    "localisation_actuelle", "premiere_rencontre", "derniere_interaction",
    "established_facts", "hypotheses_mj", "stats", "modificateurs",
    "competences_observees", "limites", "inventory", "notes_privees",
)
EN_FIN = ("illustration",)


def _err(msg: str) -> None:
    print(msg, file=sys.stderr)


def resoudre_pnj_json(campagne: str) -> Path:
    """Path to npcs.json: direct .json path, or <campagne>/npcs.json."""
    base = _resoudre(campagne)
    if base.suffix == ".json":
        return base
    return base / "npcs.json"


def liste_pnj(donnees) -> list[dict]:
    """Normalises npcs.json into a LIST of sheets (direct list, or container dict)."""
    if isinstance(donnees, list):
        return [x for x in donnees if isinstance(x, dict)]
    if isinstance(donnees, dict):
        for cle in ("pnj", "pnjs", "characters"):
            v = donnees.get(cle)
            if isinstance(v, list):
                return [x for x in v if isinstance(x, dict)]
        # dict {id: sheet} → values
        vals = [v for v in donnees.values() if isinstance(v, dict) and "name" in v]
        if vals:
            return vals
    return []


def trouver(pnjs: list[dict], name: str):
    """Returns (sheet, None) if found, otherwise (None, list_of_ambiguous_candidates).

    Priority: case-insensitive equality → otherwise substring (1 match only).
    """
    cible = name.strip().lower()
    for p in pnjs:
        if str(p.get("name", "")).lower() == cible:
            return p, None
    partiels = [p for p in pnjs if cible in str(p.get("name", "")).lower()]
    if len(partiels) == 1:
        return partiels[0], None
    return None, partiels  # 0 → not found, >1 → ambiguous


def cles_ordonnees(fiche: dict) -> list[str]:
    """Sheet keys in preferred order, extras in the middle, EN_FIN at the end."""
    presentes = set(fiche)
    tete = [k for k in ORDRE if k in presentes]
    fin = [k for k in EN_FIN if k in presentes]
    reste = sorted(presentes - set(tete) - set(fin))
    return tete + reste + fin


def rendre(fiche: dict, maxlen: int) -> str:
    """Human-readable view: `**key**: value`; objects/lists as indented JSON."""
    lignes = [f"=== {fiche.get('name', 'UNKNOWN NPC')} ==="]
    for k in cles_ordonnees(fiche):
        if k == "name":
            continue
        v = fiche[k]
        if isinstance(v, (list, dict)):
            v = json.dumps(v, ensure_ascii=False, indent=2)
        else:
            v = str(v)
        if maxlen and len(v) > maxlen:
            v = v[:maxlen] + f"… [+{len(v) - maxlen} chars.]"
        lignes.append(f"**{k}**:")
        lignes.append(v)
        lignes.append("")
    return "\n".join(lignes).rstrip() + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Consult (read-only) an NPC sheet from npcs.json.")
    ap.add_argument("campagne", help="campaign folder, OR path to npcs.json")
    ap.add_argument("name", nargs="?", help="NPC name (exact or substring)")
    ap.add_argument("--list", action="store_true", dest="lister",
                    help="list available NPCs (+ location)")
    ap.add_argument("--json", action="store_true", dest="sortie_json",
                    help="display the raw NPC object as JSON")
    ap.add_argument("--max", type=int, default=0, metavar="N",
                    help="truncate each field to N characters (0 = unlimited)")
    args = ap.parse_args(argv)

    chemin = resoudre_pnj_json(args.campagne)
    if not chemin.is_file():
        _err(f"❌ npcs.json not found: {chemin}")
        return 2

    sentinelle = object()
    donnees = _charger(chemin, sentinelle)
    if donnees is sentinelle:
        _err(f"❌ npcs.json unreadable: {chemin}")
        return 2
    pnjs = liste_pnj(donnees)
    if not pnjs:
        _err(f"❌ no usable NPC sheet found in {chemin}")
        return 2

    if args.lister:
        print(f"Available NPCs ({len(pnjs)}):")
        for p in sorted(pnjs, key=lambda x: str(x.get("name", ""))):
            loc = p.get("localisation_actuelle", "?")
            print(f"  • {str(p.get('name', '?')):24s} [{loc}]")
        return 0

    if not args.name:
        _err("❌ NPC name required (or --list).")
        return 2

    fiche, ambigus = trouver(pnjs, args.name)
    if fiche is None:
        if ambigus:
            noms = ", ".join(str(p.get("name", "?")) for p in ambigus)
            _err(f"❌ \"{args.name}\" is ambiguous — candidates: {noms}")
        else:
            dispo = ", ".join(str(p.get("name", "?")) for p in pnjs)
            _err(f"❌ NPC \"{args.name}\" not found. Available: {dispo}")
        return 1

    if args.sortie_json:
        print(json.dumps(fiche, ensure_ascii=False, indent=2))
    else:
        print(rendre(fiche, args.max), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
