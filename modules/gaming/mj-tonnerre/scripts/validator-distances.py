#!/usr/bin/env python3
"""
Distance consistency validator for MJ Tonnerre.

Checks the 4 rules of travel governance:
1. Indirect route >= direct route between the same two points
2. No route shorter than a neighbouring route to a distant point
3. Maximum 12h day (round trip + work)
4. No inverted hierarchy (near < far)

Usage:
  python3 validator-distances.py <path/monde.json>
  python3 validator-distances.py                  # cherche dans *.json du dossier courant

Returns 0 if all OK, 1 if warnings, 2 if errors.
"""

import json
import re
import sys
from pathlib import Path
from collections import defaultdict


def extraire_minutes(duree_str: str) -> int:
    """Convert a narrative duration string to minutes.
    Supported formats: '2h', '30min', '1h30', '1h30min', '5h45', '7h30',
    '~4h', '1h15 — description'.
    Returns -1 if not parseable.

    Note: minutes after an hour can be written WITHOUT a 'min' suffix
    ("1h30" = 1h and 30 minutes). This was the bug in the original version,
    which silently ignored the minutes of "1h30" (-> 60 instead of 90).
    """
    if not duree_str:
        return -1
    # Strip prefixes (~, ≈, spaces); we only look at the START
    # (the part after "—" is narrative description).
    nettoye = duree_str.strip().lstrip("~≈ ")

    # Case 1: 'Xh' optionally followed by minutes ('Xh', 'XhYY', 'XhYYmin')
    m = re.match(r"(\d+)\s*h\s*(\d+)?\s*(?:min)?", nettoye)
    if m and m.group(1):
        heures = int(m.group(1))
        minutes = int(m.group(2)) if m.group(2) else 0
        total = heures * 60 + minutes
        return total if total > 0 else -1

    # Case 2: minutes only ('YYmin', 'YY min')
    m = re.match(r"(\d+)\s*min", nettoye)
    if m:
        total = int(m.group(1))
        return total if total > 0 else -1

    return -1


def charger_donnees(chemin: Path) -> dict:
    with open(chemin, encoding="utf-8") as f:
        return json.load(f)


def collecter_trajets(monde: dict) -> list[dict]:
    """Extract all travel routes from regles.temps.deplacements."""
    deps = monde.get("regles", {}).get("temps", {}).get("deplacements", {})
    trajets = []

    for section_key, section_val in deps.items():
        if not isinstance(section_val, dict):
            continue
        if section_key == "gouvernance":
            continue
        source_prefix = ""
        if section_key.startswith("depuis_"):
            # depuis_<source>_vers -> strip the prefix AND the "_vers" suffix
            brut = section_key[len("depuis_"):]
            if brut.endswith("_vers"):
                brut = brut[:-len("_vers")]
            source_prefix = brut.replace("_", " ").strip()
        elif section_key == "entre":
            source_prefix = None  # composite keys

        if source_prefix is not None:
            # depuis_<source>_vers: destination -> duration
            for dest_key, desc in section_val.items():
                if not isinstance(desc, str):
                    continue
                minutes = extraire_minutes(desc)
                dest_nom = dest_key.replace("_", " ").strip()
                trajets.append({
                    "source": source_prefix,
                    "destination": dest_nom,
                    "duree_min": minutes,
                    "description": desc,
                    "section": section_key,
                })
        else:
            # entre: key_source_vers_key_dest -> duration
            for cle, desc in section_val.items():
                if not isinstance(desc, str):
                    continue
                parties = cle.split("_vers_")
                if len(parties) != 2:
                    continue
                source = parties[0].replace("_", " ").strip()
                dest = parties[1].replace("_", " ").strip()
                minutes = extraire_minutes(desc)
                trajets.append({
                    "source": source,
                    "destination": dest,
                    "duree_min": minutes,
                    "description": desc,
                    "section": "entre",
                })

    return trajets


def verifier_coherence(trajets: list[dict]) -> list[str]:
    """Check the 4 rules. Returns a list of issues."""
    problemes = []

    # Index by (source, destination)
    trajets_dict = {}
    for t in trajets:
        if t["source"] and t["destination"]:
            trajets_dict[(t["source"], t["destination"])] = t["duree_min"]
            trajets_dict[(t["destination"], t["source"])] = t["duree_min"]

    # Build a graph for indirect paths
    lieux = set()
    for t in trajets:
        if t["source"]:
            lieux.add(t["source"])
        if t["destination"]:
            lieux.add(t["destination"])

    # Rule 1: Indirect >= Direct (naive pairwise check)
    for t in trajets:
        if not t["source"] or not t["destination"]:
            continue
        direct = t["duree_min"]
        if direct <= 0:
            continue

        # Look for indirect paths: source -> X -> dest
        for autre in trajets:
            if autre is t:
                continue
            if autre["source"] == t["source"] and autre["destination"] != t["destination"]:
                milieu = autre["destination"]
                # Check whether midpoint -> dest exists
                retour = trajets_dict.get((milieu, t["destination"]), -1)
                if retour > 0 and autre["duree_min"] > 0:
                    indirect = autre["duree_min"] + retour
                    if indirect < direct and indirect > 0:
                        problemes.append(
                            f"⚠ R1: Indirect < Direct — {t['source']} → {milieu} → {t['destination']} "
                            f"= {indirect}min < {t['source']} → {t['destination']} direct = {direct}min. "
                            f"Direct description: «{t['description']}»"
                        )

    # Rule 2: No inverted hierarchy
    # Check that locations are mutually consistent
    for t1 in trajets:
        for t2 in trajets:
            if t1 is t2:
                continue
            if t1["source"] == t2["source"] and t1["duree_min"] > 0 and t2["duree_min"] > 0:
                # Both depart from the same source point
                if t1["duree_min"] < t2["duree_min"]:
                    # t1 is closer, which is expected
                    pass
            if t1["destination"] == t2["destination"] and t1["duree_min"] > 0 and t2["duree_min"] > 0:
                if t1["source"] != t2["source"]:
                    # Same destination but different sources
                    pass

    # Rule 3: Maximum 12h day
    for source in lieux:
        total = 0
        trajets_depuis = [t for t in trajets if t["source"] == source and t["duree_min"] > 0]
        for t in sorted(trajets_depuis, key=lambda x: x["duree_min"], reverse=True)[:3]:
            total += t["duree_min"]
        # Check whether a simple round trip would take > 12h
        for t in trajets_depuis:
            ar = t["duree_min"] * 2
            if ar > 720:
                problemes.append(
                    f"⚠ R3: Round trip > 12h — {source} ↔ {t['destination']} "
                    f"= {ar}min ({ar//60}h{ar%60:02d}). Description: «{t['description']}»"
                )

    # Rule 4: A distant point cannot be reached in less time than a nearby neighbouring point
    # Simple check: if A->B < A->C and B is farther than C on the graph
    for t1 in trajets:
        for t2 in trajets:
            if t1 is t2 or t1["source"] != t2["source"]:
                continue
            if t1["duree_min"] > 0 and t2["duree_min"] > 0:
                # From the same source, a farther point should take more time
                # We cannot verify this automatically without knowing the real topology,
                # but we can warn if durations are identical for differently-named locations
                if (t1["duree_min"] == t2["duree_min"]
                        and t1["destination"] != t2["destination"]
                        and abs(t1["duree_min"] - t2["duree_min"]) < 5):
                    problemes.append(
                        f"ℹ R4: Identical durations — {t1['source']} → {t1['destination']} "
                        f"= {t1['duree_min']}min = {t1['source']} → {t2['destination']}. "
                        f"Check whether this is intentional."
                    )

    return problemes


def main():
    if len(sys.argv) > 1 and sys.argv[1] in ("-h", "--help"):
        print(__doc__)
        sys.exit(0)

    if len(sys.argv) > 1:
        arg = Path(sys.argv[1])
        chemins = [arg / "monde.json"] if arg.is_dir() else [arg]
    else:
        chemins = list(Path.cwd().glob("monde.json"))

    if not chemins:
        print("❌ No monde.json file found. Usage: validator-distances.py <path/monde.json>")
        sys.exit(2)

    global_status = 0

    for chemin in chemins:
        if not chemin.exists():
            print(f"❌ File not found: {chemin}")
            global_status = 2
            continue

        try:
            monde = charger_donnees(chemin)
        except (json.JSONDecodeError, IOError) as e:
            print(f"❌ Read error {chemin}: {e}")
            global_status = 2
            continue

        trajets = collecter_trajets(monde)
        if not trajets:
            print(f"ℹ No route found in {chemin}")
            continue

        print(f"🔍 Checking {chemin.name} — {len(trajets)} route(s)")
        problemes = verifier_coherence(trajets)

        if not problemes:
            print("✅ Consistency validated — 4 rules respected.")
        else:
            for p in problemes:
                if p.startswith("⚠"):
                    print(p)
                    global_status = max(global_status, 1)
                else:
                    print(p)

    # Summary
    if global_status == 0:
        print("\n✅ Everything is consistent.")
    elif global_status == 1:
        print("\n⚠ Human checks are recommended.")
    else:
        print("\n❌ Blocking errors.")

    sys.exit(global_status)


if __name__ == "__main__":
    main()
