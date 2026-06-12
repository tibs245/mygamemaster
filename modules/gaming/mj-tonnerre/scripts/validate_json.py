#!/usr/bin/env python3
"""
validate_json.py — Generic JSON validator for a MJ Tonnerre campaign.

Loads ALL JSON files of a campaign and verifies they are
syntactically valid. Replaces the `python3 -c "import json; json.load(...)"`
calls scattered throughout the closing procedure.

Files checked (if they exist):
  - monde.json
  - pnj.json
  - evenements.json
  - personnages/*.json
  - sessions/*.json
  - outils/*.json  (if applicable)
Also recursively scans any other *.json present in the campaign so
nothing is missed (except technical folders: .git, __pycache__, images).

Usage:
  python3 validate_json.py <path/campaign>
  python3 validate_json.py <path/campaign> --json
  python3 validate_json.py file1.json file2.json     # specific files

Output: for each broken JSON, displays the file + line/column of the error.

Exit codes:
  0  all JSON files are valid
  1  at least one JSON file is broken
  2  usage error (path not found, no JSON found)
"""

import argparse
import json
import sys
from pathlib import Path

# Folders to ignore during the recursive scan.
DOSSIERS_IGNORES = {".git", "__pycache__", "images", ".cache", "node_modules"}


def collecter_fichiers(cible: Path) -> list[Path]:
    """Returns the list of *.json files to validate for a target.

    If `cible` is a .json file → [cible].
    If `cible` is a folder (campaign) → all *.json files recursively
    excluding DOSSIERS_IGNORES, sorted by path.
    """
    if cible.is_file():
        return [cible] if cible.suffix == ".json" else []

    fichiers = []
    for p in sorted(cible.rglob("*.json")):
        # Skip if any component of the path (relative to the target) is ignored.
        rel_parts = p.relative_to(cible).parts
        if any(part in DOSSIERS_IGNORES for part in rel_parts):
            continue
        fichiers.append(p)
    return fichiers


def valider_fichier(chemin: Path) -> dict:
    """Validates a JSON file. Returns a result dict:
        {"fichier": str, "ok": bool, "erreur": str|None,
         "ligne": int|None, "colonne": int|None}
    """
    res = {"fichier": str(chemin), "ok": True, "erreur": None,
           "ligne": None, "colonne": None}
    try:
        with open(chemin, "r", encoding="utf-8") as f:
            json.load(f)
    except json.JSONDecodeError as e:
        res.update(ok=False, erreur=e.msg, ligne=e.lineno, colonne=e.colno)
    except (OSError, UnicodeDecodeError) as e:
        res.update(ok=False, erreur=f"Cannot read file: {e}")
    return res


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="validate_json.py",
        description="Validates all JSON files of a MJ Tonnerre campaign.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python3 validate_json.py .hermes/mj-tonnerre/campagnes/la-naissance-dun-roi\n"
            "  python3 validate_json.py monde.json sessions/004.json\n"
        ),
    )
    parser.add_argument("cibles", nargs="+",
                        help="Campaign path(s) (folder) and/or .json files.")
    parser.add_argument("--json", action="store_true", dest="as_json",
                        help="Output in JSON format (machine-readable).")
    args = parser.parse_args(argv)

    # Collection
    fichiers: list[Path] = []
    for c in args.cibles:
        chemin = Path(c)
        if not chemin.exists():
            print(f"❌ Not found: {chemin}", file=sys.stderr)
            return 2
        fichiers.extend(collecter_fichiers(chemin))

    # Deduplicate while preserving order
    vus = set()
    fichiers = [f for f in fichiers if not (f in vus or vus.add(f))]

    if not fichiers:
        print("❌ No .json file found.", file=sys.stderr)
        return 2

    resultats = [valider_fichier(f) for f in fichiers]
    casses = [r for r in resultats if not r["ok"]]

    if args.as_json:
        print(json.dumps({
            "total": len(resultats),
            "valides": len(resultats) - len(casses),
            "casses": casses,
        }, ensure_ascii=False, indent=2))
    else:
        for r in resultats:
            if r["ok"]:
                print(f"✅ {r['fichier']}")
            else:
                loc = ""
                if r["ligne"] is not None:
                    loc = f" (line {r['ligne']}, column {r['colonne']})"
                print(f"❌ {r['fichier']}{loc} — {r['erreur']}")

        print()
        if casses:
            print(f"❌ {len(casses)}/{len(resultats)} broken JSON file(s).")
        else:
            print(f"✅ {len(resultats)} valid JSON file(s).")

    return 1 if casses else 0


if __name__ == "__main__":
    sys.exit(main())
