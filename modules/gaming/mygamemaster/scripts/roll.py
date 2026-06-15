#!/usr/bin/env python3
"""
roll.py — Real dice roller for MJ Tonnerre.

Rolls REAL dice (cryptographic entropy via `secrets`, no network)
and MECHANICALLY applies the natural dice roll rule (SOUL.md §NATURAL DIE RULE):
  - natural roll = 1  → always failure, even with +20 (FUMBLE)
  - natural roll = N (max of die, e.g. 20) → always success, even with -10 (CRITIQUE)
These two outcomes override any threshold (DC).

The goal: the GM CALLS this script instead of inventing a "plausible" number.
Each dice roll is logged (timestamp, formula, dice, total, result) in an
auditable log file, to allow replay/explanation of disputes.

Supported formulas:
  "1d20+3"   "d20"   "2d6"   "1d20-1"   "3d8+2"   "1d100"   "4d6"
The "1" before the "d" is optional.

Usage:
  python3 roll.py "1d20+3"
  python3 roll.py "1d20+3" --dc 15 --stat Dexterity
  python3 roll.py "2d6+1" --json
  python3 roll.py "1d20" --seed 42          # reproducible (tests/disputes ONLY)
  python3 roll.py "1d20+5" --log /path/to/jets.log

Exit codes:
  0  dice roll performed (success OR failure: a roll failure is NOT a program error)
  2  invalid formula / usage error
"""

import argparse
import json
import os
import re
import secrets
import subprocess
import sys
from datetime import datetime

# ─── Default log location ───────────────────────────────────────────────────
# Next to the script, in scripts/. Overridable via --log or $MGM_ROLL_LOG.
_DOSSIER_SCRIPT = os.path.dirname(os.path.abspath(__file__))
LOG_DEFAUT = os.environ.get("MGM_ROLL_LOG", os.path.join(_DOSSIER_SCRIPT, "jets.log"))

# Formula: [N]dF[+/-M]   e.g.: 1d20+3, d6, 2d8-1
_RE_FORMULE = re.compile(r"^\s*(\d*)\s*[dD]\s*(\d+)\s*([+-]\s*\d+)?\s*$")


# ─── Pure functions ──────────────────────────────────────────────────────────

def parser_formule(formule: str) -> tuple[int, int, int]:
    """Parse 'NdF+M' → (number_of_dice, faces, modifier).

    Raises ValueError if the formula is invalid.
    """
    m = _RE_FORMULE.match(formule)
    if not m:
        raise ValueError(
            f"Invalid formula: « {formule} ». Expected: 'NdF[+/-M]' "
            f"(e.g. 1d20+3, d6, 2d8-1)."
        )
    nb = int(m.group(1)) if m.group(1) else 1
    faces = int(m.group(2))
    modif = int(m.group(3).replace(" ", "")) if m.group(3) else 0

    if nb < 1:
        raise ValueError("The number of dice must be ≥ 1.")
    if nb > 100:
        raise ValueError("The number of dice is limited to 100.")
    if faces < 2:
        raise ValueError("A die must have at least 2 faces.")
    if faces > 1000:
        raise ValueError("The number of faces is limited to 1000.")
    return nb, faces, modif


def tirer_des(nb: int, faces: int, rng) -> list[int]:
    """Rolls `nb` dice with `faces` sides using generator `rng`.

    `rng` must expose randrange(n) -> [0, n[ (common method of both
    secrets.SystemRandom AND random.Random). Returns the list of raw results
    (1..faces). randrange is uniform and without modulo bias.
    """
    return [rng.randrange(faces) + 1 for _ in range(nb)]


# ─── Quantum source (qrandom.io) ─────────────────────────────────────────────

class QuantumRNG:
    """Generator exposing `randrange(n)` like secrets/random, but drawing
    each value from the quantum API qrandom.io (curl via subprocess).

    The network is used ONLY by this object (therefore ONLY if --quantique).
    On network failure / timeout / parse error, falls back per die to the
    cryptographic fallback `secrets` — a dice roll NEVER crashes due to
    network issues. Records whether at least one die fell back to fallback.
    """

    def __init__(self):
        self._secrets = secrets.SystemRandom()
        self.fallback_utilise = False   # True as soon as a die falls back to secrets
        self.tous_fallback = True       # True if NO quantum draw succeeded

    def randrange(self, n: int) -> int:
        """Returns an integer in [0, n[. Attempts qrandom.io (min=1..max=n →
        subtract 1), otherwise secrets.randbelow(n)."""
        try:
            proc = subprocess.run(
                ["curl", "-sf", "--max-time", "5",
                 f"https://qrandom.io/api/random/int?min=1&max={n}"],
                capture_output=True, text=True, timeout=6,
            )
            if proc.returncode != 0:
                raise RuntimeError(f"curl rc={proc.returncode}")
            valeur = int(proc.stdout.strip())   # raw integer 1..n
            if not (1 <= valeur <= n):
                raise ValueError(f"hors borne : {valeur}")
            self.tous_fallback = False
            return valeur - 1                   # bring back to [0, n[
        except Exception:
            # Per-die fallback: NEVER let the roll fail.
            self.fallback_utilise = True
            return self._secrets.randrange(n)


def evaluer_jet(formule: str, des: list[int], faces: int, modif: int,
                dc: int | None) -> dict:
    """Builds the complete result of a dice roll, applying the natural
    die rule when a single d20 (or die) carries the test.

    The natural die rule applies to single-die rolls (the standard case
    for a skill check). For multi-die rolls (e.g. damage 2d6), there is
    no nat1 or nat20: values are simply summed.
    """
    brut = sum(des)
    total = brut + modif

    nat = None
    # Natural die rule: applies only on a single-die test.
    if len(des) == 1:
        de = des[0]
        if de == 1:
            nat = "FUMBLE"      # failure no matter what
        elif de == faces:
            nat = "CRITIQUE"    # success no matter what

    resultat = None
    ecart = None
    if nat == "CRITIQUE":
        resultat = "REUSSITE"
    elif nat == "FUMBLE":
        resultat = "ECHEC"
    elif dc is not None:
        ecart = total - dc
        resultat = "REUSSITE" if total >= dc else "ECHEC"

    return {
        "formule": formule,
        "des": des,
        "faces": faces,
        "brut": brut,
        "modif": modif,
        "total": total,
        "dc": dc,
        "nat": nat,                # null | "FUMBLE" | "CRITIQUE"
        "resultat": resultat,      # null (no DC) | "REUSSITE" | "ECHEC"
        "ecart": ecart,            # null if no DC or if natural die decides
    }


# ─── Human-readable output ───────────────────────────────────────────────────

def formater_lisible(res: dict, stat: str | None,
                     source_rng: str | None = None) -> str:
    """Renders the dice roll in human-readable form for the GM (not the player)."""
    lignes = []
    titre = f"🎲 {res['formule']}"
    if stat:
        titre += f"  ({stat})"
    lignes.append(titre)

    # Announce the draw source when quantum (and signal any fallback to secrets).
    # The "simple" secrets mode stays silent.
    if source_rng and source_rng.startswith("quantique"):
        if source_rng == "quantique":
            lignes.append("   ⚛ Source: quantum (qrandom.io)")
        elif source_rng == "quantique(fallback:secrets)":
            lignes.append("   ⚛ Source: quantum UNAVAILABLE → fallback secrets")
        else:
            lignes.append("   ⚛ Source: quantum with partial fallback secrets")

    des_txt = " + ".join(str(d) for d in res["des"])
    detail = f"   Dice: [{des_txt}]"
    if res["modif"]:
        detail += f"  modif {res['modif']:+d}"
    detail += f"  →  total {res['total']}"
    lignes.append(detail)

    if res["nat"] == "CRITIQUE":
        lignes.append("   ✨ NATURAL MAXIMUM DIE → SUCCESS (overrides threshold)")
    elif res["nat"] == "FUMBLE":
        lignes.append("   💀 NATURAL DIE 1 → FAILURE (overrides threshold)")

    if res["dc"] is not None:
        if res["nat"] is None:
            comp = "≥" if res["resultat"] == "REUSSITE" else "<"
            lignes.append(f"   Threshold (DC) {res['dc']}: {res['total']} {comp} {res['dc']}  (margin {res['ecart']:+d})")
        else:
            lignes.append(f"   Threshold (DC) {res['dc']} ignored — the natural die decides.")

    if res["resultat"] == "REUSSITE":
        lignes.append("   ✅ SUCCESS")
    elif res["resultat"] == "ECHEC":
        lignes.append("   ❌ FAILURE")
    else:
        lignes.append("   (no threshold provided — raw result)")

    return "\n".join(lignes)


# ─── Auditable log ───────────────────────────────────────────────────────────

def journaliser(res: dict, stat: str | None, source_rng: str,
                graine, chemin_log: str) -> None:
    """Appends a JSON line to the log (JSON Lines format, append-only)."""
    enregistrement = {
        "horodatage": datetime.now().isoformat(timespec="seconds"),
        "formule": res["formule"],
        "stat": stat,
        "des": res["des"],
        "faces": res["faces"],
        "brut": res["brut"],
        "modif": res["modif"],
        "total": res["total"],
        "dc": res["dc"],
        "nat": res["nat"],
        "resultat": res["resultat"],
        "ecart": res["ecart"],
        "rng": source_rng,
        "graine": graine,
    }
    try:
        with open(chemin_log, "a", encoding="utf-8") as f:
            f.write(json.dumps(enregistrement, ensure_ascii=False) + "\n")
    except OSError as e:
        # NEVER let a dice roll fail because of the log — but warn about it.
        print(f"⚠ Cannot write log ({chemin_log}): {e}", file=sys.stderr)


# ─── CLI ──────────────────────────────────────────────────────────────────────

def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="roll.py",
        description="Real dice roller (true entropy) with natural die rule.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python3 roll.py \"1d20+3\" --dc 15 --stat Dexterity\n"
            "  python3 roll.py \"2d6+1\" --json\n"
            "  python3 roll.py \"1d20\" --seed 42   (reproducible — tests/disputes)\n"
        ),
    )
    parser.add_argument("formule", help="Dice formula, e.g. '1d20+3', 'd6', '2d8-1'.")
    parser.add_argument("--dc", type=int, default=None,
                        help="Difficulty Class threshold. Success if total ≥ DC.")
    parser.add_argument("--stat", type=str, default=None,
                        help="Attribute/skill being tested (for display and log only).")
    parser.add_argument("--seed", type=int, default=None,
                        help="Seed to make the roll REPRODUCIBLE (tests/disputes ONLY — "
                             "otherwise true entropy via secrets).")
    parser.add_argument("-q", "--quantique", action="store_true",
                        help="Draw each die from the quantum API qrandom.io (curl, network). "
                             "Automatic per-die fallback to secrets if network fails. "
                             "Incompatible with --seed.")
    parser.add_argument("--json", action="store_true", dest="as_json",
                        help="Output as JSON (machine-readable).")
    parser.add_argument("--log", type=str, default=LOG_DEFAUT,
                        help=f"Log file (JSON Lines, append). Default: {LOG_DEFAUT}")
    parser.add_argument("--no-log", action="store_true",
                        help="Do not log this roll.")

    args = parser.parse_args(argv)

    # Parsing formula
    try:
        nb, faces, modif = parser_formule(args.formule)
    except ValueError as e:
        print(f"❌ {e}", file=sys.stderr)
        return 2

    # --seed and --quantique are mutually exclusive (one is locally reproducible,
    # the other draws from the network).
    if args.quantique and args.seed is not None:
        print("❌ --quantique and --seed are incompatible.", file=sys.stderr)
        return 2

    # Generator: secrets by default (true entropy, no network),
    # random.Random(seed) if --seed (reproducible), QuantumRNG if --quantique.
    qrng = None
    if args.quantique:
        qrng = QuantumRNG()
        rng = qrng
        source_rng = "quantique"   # adjusted after draw depending on fallbacks
        graine = None
    elif args.seed is not None:
        import random
        rng = random.Random(args.seed)
        source_rng = "random(seed)"
        graine = args.seed
    else:
        rng = secrets.SystemRandom()
        source_rng = "secrets"
        graine = None

    des = tirer_des(nb, faces, rng)

    # In quantum mode, reflect in the source whether any dice fell back to
    # secrets fallback (at least one die) or if ALL fell back.
    if qrng is not None:
        if qrng.tous_fallback:
            source_rng = "quantique(fallback:secrets)"
        elif qrng.fallback_utilise:
            source_rng = "quantique(fallback partial:secrets)"
        else:
            source_rng = "quantique"
    res = evaluer_jet(args.formule, des, faces, modif, args.dc)

    # Log (unless --no-log)
    if not args.no_log:
        journaliser(res, args.stat, source_rng, graine, args.log)

    # Output
    if args.as_json:
        sortie = dict(res)
        sortie["stat"] = args.stat
        sortie["rng"] = source_rng
        sortie["graine"] = graine
        print(json.dumps(sortie, ensure_ascii=False))
    else:
        print(formater_lisible(res, args.stat, source_rng))

    # A roll failure is not a program error: exit 0 in all cases where
    # the dice roll could be performed.
    return 0


if __name__ == "__main__":
    sys.exit(main())
