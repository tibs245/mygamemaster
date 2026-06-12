#!/usr/bin/env python3
"""
validate_schema.py — Structural validation of a MJ Tonnerre campaign against
the JSON Schemas in scripts/schemas/ (HOME-BUILT validator, stdlib only —
NO external jsonschema dependency).

Validates :
  world.json        → schemas/world.schema.json
  npcs.json          → schemas/npcs.schema.json
  characters/*.json→ schemas/character.schema.json
  sessions/*.json   → schemas/session.schema.json

The validator supports the Draft 2020-12 subset used by these schemas:
  type (incl. union lists), required, properties, additionalProperties,
  patternProperties, items, enum, oneOf, anyOf, local $ref (#/...), $defs.
Tolerant by design: additionalProperties:true everywhere → only REAL
MISSING items are reported (required fields absent, wrong types, value outside enum).

Usage:
  python3 validate_schema.py <path/campaign>
  python3 validate_schema.py <path/campaign> --json
  python3 validate_schema.py <file.json> --schema world   # a specific file

Exit codes:
  0  conformant (some absent files may remain — non-blocking)
  1  at least one schema deviation detected
  2  usage error (campaign/schemas not found)
"""

import argparse
import json
import re
import sys
from pathlib import Path

SCHEMAS_DIR = Path(__file__).resolve().parent / "schemas"


# ─── Mini JSON Schema validator (subset) ─────────────────────────────────────

_TYPE_PY = {
    "object": dict,
    "array": list,
    "string": str,
    "integer": int,
    "number": (int, float),
    "boolean": bool,
    "null": type(None),
}


def _type_match(valeur, t: str) -> bool:
    if t == "integer":
        # bool is a subclass of int in Python: exclude it from integer/number
        return isinstance(valeur, int) and not isinstance(valeur, bool)
    if t == "number":
        return isinstance(valeur, (int, float)) and not isinstance(valeur, bool)
    if t == "boolean":
        return isinstance(valeur, bool)
    py = _TYPE_PY.get(t)
    return isinstance(valeur, py) if py else True


def _resoudre_ref(ref: str, racine: dict):
    """Resolves a local $ref of the form '#/$defs/x'."""
    if not ref.startswith("#/"):
        return None
    noeud = racine
    for part in ref[2:].split("/"):
        part = part.replace("~1", "/").replace("~0", "~")
        if isinstance(noeud, dict) and part in noeud:
            noeud = noeud[part]
        else:
            return None
    return noeud


def valider(instance, schema: dict, racine: dict, chemin: str = "$") -> list[str]:
    """Returns the list of deviation messages. Empty = conformant."""
    erreurs: list[str] = []

    if not isinstance(schema, dict):
        return erreurs

    # $ref — follow reference
    if "$ref" in schema:
        cible = _resoudre_ref(schema["$ref"], racine)
        if cible is not None:
            return valider(instance, cible, racine, chemin)
        return erreurs

    # oneOf / anyOf: conformant if at least one sub-schema passes.
    for cle in ("oneOf", "anyOf"):
        if cle in schema:
            sous = schema[cle]
            passants = []
            details = []  # (type_matched: bool, errs: list)
            for s in sous:
                errs = valider(instance, s, racine, chemin)
                if not errs:
                    passants.append(s)
                else:
                    # The branch whose `type` matches the instance is the
                    # most relevant to surface (e.g. a malformed dict vs a
                    # non-applicable array branch).
                    t = s.get("type")
                    ts = [t] if isinstance(t, str) else (t or [])
                    type_ok = any(_type_match(instance, x) for x in ts) if ts else True
                    details.append((type_ok, errs))
            if not passants:
                pertinentes = [e for ok, e in details if ok] or [e for _, e in details]
                meilleure = min(pertinentes, key=len) if pertinentes else []
                erreurs.append(f"{chemin} : does not match any of the "
                               f"{len(sous)} variants ({cle})")
                erreurs.extend(meilleure)
            # For oneOf we do not enforce uniqueness (intentional tolerance).
            return erreurs

    # type check
    if "type" in schema:
        types = schema["type"]
        if isinstance(types, str):
            types = [types]
        if not any(_type_match(instance, t) for t in types):
            erreurs.append(f"{chemin} : expected type {types}, "
                           f"got {type(instance).__name__}")
            return erreurs  # no point descending if the type is wrong

    # enum check
    if "enum" in schema and instance not in schema["enum"]:
        erreurs.append(f"{chemin} : value {instance!r} outside enum {schema['enum']}")

    # object validation
    if isinstance(instance, dict):
        for champ in schema.get("required", []):
            if champ not in instance:
                erreurs.append(f"{chemin}.{champ} : required field MISSING")
        props = schema.get("properties", {})
        for k, sub in props.items():
            if k in instance:
                erreurs.extend(valider(instance[k], sub, racine, f"{chemin}.{k}"))
        patterns = schema.get("patternProperties", {})
        for pat, sub in patterns.items():
            rx = re.compile(pat)
            for k, v in instance.items():
                if k in props:
                    continue
                if rx.search(k):
                    erreurs.extend(valider(v, sub, racine, f"{chemin}.{k}"))
        # additionalProperties: only flag if explicitly False.
        if schema.get("additionalProperties") is False:
            connus = set(props)
            pats = [re.compile(p) for p in patterns]
            for k in instance:
                if k in connus:
                    continue
                if any(p.search(k) for p in pats):
                    continue
                erreurs.append(f"{chemin}.{k} : property not allowed")

    # array validation
    if isinstance(instance, list):
        items = schema.get("items")
        if isinstance(items, dict):
            for i, el in enumerate(instance):
                erreurs.extend(valider(el, items, racine, f"{chemin}[{i}]"))

    return erreurs


# ─── Loading ──────────────────────────────────────────────────────────────────

def charger(chemin: Path):
    with open(chemin, "r", encoding="utf-8") as f:
        return json.load(f)


def charger_schema(name: str) -> dict:
    p = SCHEMAS_DIR / f"{name}.schema.json"
    if not p.exists():
        raise FileNotFoundError(f"Schema not found: {p}")
    return charger(p)


# ─── Campaign pipeline ────────────────────────────────────────────────────────

def valider_campagne(campagne: Path) -> dict:
    resultats = []  # {"fichier","schema","ecarts":[...]} — list of result dicts

    def ajouter(fichier: Path, schema_nom: str):
        if not fichier.exists():
            resultats.append({"fichier": str(fichier), "schema": schema_nom,
                              "present": False, "ecarts": []})
            return
        try:
            data = charger(fichier)
        except (OSError, json.JSONDecodeError) as e:
            resultats.append({"fichier": str(fichier), "schema": schema_nom,
                              "present": True, "ecarts": [f"$ : unreadable — {e}"]})
            return
        sch = charger_schema(schema_nom)
        ecarts = valider(data, sch, sch)
        resultats.append({"fichier": str(fichier), "schema": schema_nom,
                          "present": True, "ecarts": ecarts})

    ajouter(campagne / "world.json", "world")
    ajouter(campagne / "npcs.json", "npcs")
    ajouter(campagne / "actors.json", "actor")
    ajouter(campagne / "geo.json", "geo")
    for p in sorted((campagne / "characters").glob("*.json")) \
            if (campagne / "characters").is_dir() else []:
        ajouter(p, "character")
    for p in sorted((campagne / "sessions").glob("*.json")) \
            if (campagne / "sessions").is_dir() else []:
        ajouter(p, "session")
    ajouter(campagne / "events.json", "events")

    n_ecarts = sum(len(r["ecarts"]) for r in resultats)
    return {"campagne": str(campagne), "resultats": resultats,
            "n_ecarts": n_ecarts}


# ─── CLI ─────────────────────────────────────────────────────────────────────


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="validate_schema.py",
        description="Validates a campaign against the JSON Schemas (built-in validator).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Exemples :\n"
            "  python3 validate_schema.py .hermes/mj-tonnerre/campaigns/la-naissance-dun-roi\n"
            "  python3 validate_schema.py world.json --schema world\n"
        ),
    )
    parser.add_argument("cible", help="Campaign folder OR a specific .json file.")
    parser.add_argument("--schema", default=None,
                        help="Schema name (world|npcs|character|session) "
                             "when the target is a specific file.")
    parser.add_argument("--json", action="store_true", dest="as_json",
                        help="Output in JSON format.")
    args = parser.parse_args(argv)

    if not SCHEMAS_DIR.is_dir():
        print(f"❌ Schemas folder not found: {SCHEMAS_DIR}", file=sys.stderr)
        return 2

    cible = Path(args.cible)
    if not cible.exists():
        print(f"❌ Target not found: {cible}", file=sys.stderr)
        return 2

    if cible.is_file():
        if not args.schema:
            print("❌ Specify --schema to validate a single file.", file=sys.stderr)
            return 2
        try:
            sch = charger_schema(args.schema)
            data = charger(cible)
        except (FileNotFoundError, json.JSONDecodeError, OSError) as e:
            print(f"❌ {e}", file=sys.stderr)
            return 2
        ecarts = valider(data, sch, sch)
        rapport = {"campagne": None, "resultats": [
            {"fichier": str(cible), "schema": args.schema,
             "present": True, "ecarts": ecarts}], "n_ecarts": len(ecarts)}
    else:
        if not (cible / "world.json").exists():
            print(f"❌ world.json not found in {cible}", file=sys.stderr)
            return 2
        try:
            rapport = valider_campagne(cible)
        except FileNotFoundError as e:
            print(f"❌ {e}", file=sys.stderr)
            return 2

    if args.as_json:
        print(json.dumps(rapport, ensure_ascii=False, indent=2))
        return 1 if rapport["n_ecarts"] else 0

    print(f"📐 Schema validation — "
          f"{Path(rapport['campagne']).name if rapport['campagne'] else cible.name}")
    print("─" * 60)
    for r in rapport["resultats"]:
        nomf = Path(r["fichier"]).name
        if not r.get("present", True):
            print(f"  ⏭  {nomf} (absent — ignored)")
            continue
        if not r["ecarts"]:
            print(f"  ✅ {nomf} [{r['schema']}]")
        else:
            print(f"  ❌ {nomf} [{r['schema']}] — {len(r['ecarts'])} deviation(s):")
            for e in r["ecarts"]:
                print(f"        • {e}")
    print("─" * 60)
    if rapport["n_ecarts"]:
        print(f"❌ {rapport['n_ecarts']} schema deviation(s) in total.")
    else:
        print("✅ No schema deviations.")
    return 1 if rapport["n_ecarts"] else 0


if __name__ == "__main__":
    sys.exit(main())
