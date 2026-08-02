#!/usr/bin/env python3
"""load_campaign.py — Campaign load self-test for MJ Tonnerre.

Verifies that a campaign is READY to be played by the modular engine:
  (a) reads `world.json > modules`, separates ACTIVE modules from inactive ones;
  (b) maps each active module → its `references/modules/<x>.md` file
      (handles underscore key → hyphen filename mapping) and checks it EXISTS;
  (c) verifies that the campaign declares the DATA SECTIONS required by each
      active module (requirements inferred by reading the modules themselves);
  (d) outputs a readable "🧩 READINESS" report.

This is the safeguard that makes conditional module loading
(`world.json > modules.<x>.actif`) VERIFIABLE — instead of "the engine is supposed
to read the modules block". No network, Python 3 stdlib only.

It ALSO performs the FAIL-LOUD legacy-key check (see `verifier_cles_legacy`):
a campaign still carrying pre-rename FRENCH structural keys (`univers`,
`etat_global`, `acteurs`, `evenements`, `lieux`, …) is REFUSED instead of being
silently read as empty. Without this guard the engine reports `meta.features` as
active while `geo.locations`, `actors` and `events` all resolve to nothing — the
living world runs on a void and nobody is told.

Exit codes:
  0  campaign READY (active modules consistent, files present, required data there)
  1  inconsistency (module file missing, or required data absent)
  2  usage / campaign not found / broken JSON / LEGACY (pre-rename) keys detected

Path convention (from project root):
  CAMP=.hermes/mygamemaster/campaigns/<campagne>
  python3 /opt/modules/gaming/mygamemaster/scripts/load_campaign.py "$CAMP"
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

# --- Module registry -------------------------------------------------
# The 8 system modules. For each:
#   - "fichier"  : name of the .md in references/modules/ (underscore key → hyphen filename)
#   - "requis"   : list of DATA requirement groups. Each group is a
#                  list of "OR" paths (at least ONE path in the group must exist).
#                  The module is "data OK" if ALL its groups are satisfied.
#   - "info"     : soft requirements (progressive, filled during play) → never blocking.
#
# Paths target world.json unless prefixed "npcs.json:".
# Requirements inferred from reading modules references/modules/<x>.md + README.md:
#   travel              -> rules.time.movements         (travel.md:92, README:39)
#   factions            -> global_state.factions + faction_actions_horloge (factions.md:11,38 ; README:40)
#   proactivite_pnj     -> npcs.json present (motivations = info)  (proactivite-pnj.md:19 ; README:41)
#   artefacts           -> global_state.artefacts_connus        (artefacts.md:7 ; README:42)
#   politique           -> universe.entites_politiques OR souverainete (politique.md:60-91 ; README:43)
#   weather             -> rules.weather                        (weather.md:16 ; README:44)
#   worldbuilding_lieux -> universe.regions                     (worldbuilding-locations.md:123 ; README:45)
#   construction_royaume-> system.construction_royaume OR rules.construction (construction-royaume.md:5 ; README:46)

MODULES = {
    "travel": {
        "fichier": "travel.md",
        "requis": [["rules.time.movements"]],
        "info": [],
    },
    "factions": {
        "fichier": "factions.md",
        "requis": [
            ["global_state.factions"],
            ["global_state.faction_actions_horloge"],
        ],
        "info": [],
    },
    "proactivite_pnj": {
        "fichier": "proactivite-pnj.md",
        "requis": [["npcs.json:*"]],  # the npcs.json file must exist
        "info": ["npcs.json:motivations_personnelles"],  # progressive (per NPC)
    },
    "artefacts": {
        "fichier": "artefacts.md",
        "requis": [["global_state.artefacts_connus"]],
        "info": [],
    },
    "politique": {
        "fichier": "politique.md",
        "requis": [["universe.entites_politiques", "universe.souverainete", "souverainete"]],
        "info": [],
    },
    "weather": {
        "fichier": "weather.md",
        "requis": [["rules.weather"]],
        "info": ["universe.regions[].biodiversite"],  # progressive (per region)
    },
    "worldbuilding_lieux": {
        "fichier": "worldbuilding-locations.md",
        "requis": [["universe.regions"]],
        "info": [],
    },
    "construction_royaume": {
        "fichier": "construction-royaume.md",
        "requis": [["system.construction_royaume", "rules.construction"]],
        "info": ["global_state.royaume", "global_state.phase_construction"],
    },
}

# Keys of the `modules` block that are NOT modules (tolerated metadata).
NON_MODULE_KEYS = {"_schema"}

# Location of module files, relative to this script (scripts/ -> references/modules/).
MODULES_DIR = Path(__file__).resolve().parent.parent / "references" / "modules"


# --- FAIL-LOUD: pre-rename (French) structural keys ------------------------

# Structural keys only (containers + identity fields the engine navigates by).
# French keys the rename deliberately KEPT (`lieu`, `vers`, `ressources`,
# `relations`, `factions`, `regions`, `unite`, …) are absent on purpose.
LEGACY_STRUCTURAL_KEYS = {
    # top-level containers
    "systeme": "system",
    "univers": "universe",
    "regles": "rules",
    "etat_global": "global_state",
    # collections the living world walks
    "lieux": "locations",
    "acteurs": "actors",
    "evenements": "events",
    "pnj": "npcs",
    "deplacements": "movements",
    "trajectoire": "trajectory",
    "chronologie": "timeline",
    # identity / session bookkeeping
    "nom": "name",
    "temps": "time",
    "suivi": "tracking",
    "lieux_visites": "visited_locations",
    "pnj_rencontres": "npcs_met",
    "faits_etablis": "established_facts",
    "secrets_mj": "gm_secrets",
    "hypotheses_mj": "gm_hypotheses",
    "inventaire": "inventory",
    "equipement": "equipment",
    "competences": "skills",
    # feature axes (meta.features) — these decide what the engine runs
    "tracabilite": "traceability",
    "verbosite": "verbosity",
    "temporalite": "temporality",
    "pnj_faction_vivants": "living_npcs_factions",
}

ENV_ALLOW_LEGACY = "MGM_ALLOW_LEGACY_KEYS"

FICHIERS_SCANNES = ("world.json", "npcs.json", "actors.json", "events.json", "geo.json")

_MIGRATION_CMD = "python3 scripts/migrate_campaign_fr_en.py <campaign_dir> --apply"


class LegacyKeysError(Exception):
    """Raised when a campaign still carries pre-rename FRENCH structural keys.

    Carries the structured findings so callers can render them their own way:
      `.findings` = [{'fichier','chemin','trouvee','attendue','genre'}, …]
      with genre ∈ {'legacy', 'ambigu'}.
    """

    def __init__(self, message: str, findings: list[dict]):
        super().__init__(message)
        self.findings = findings


def _env_autorise_legacy() -> bool:
    return os.environ.get(ENV_ALLOW_LEGACY, "").strip().lower() in ("1", "true", "yes", "on")


def _scanner_legacy(noeud, chemin: str, trouvailles: list[dict], fichier: str) -> None:
    """Recursively collects every legacy FRENCH structural key of `noeud`.

    Two blocking situations, both reported:
      * 'legacy' — the FR key is there and its EN twin is NOT: every EN reader
        of this container sees nothing at all (the silent-empty bug);
      * 'ambigu' — FR and EN keys COEXIST in the same object: which one is
        authoritative is undecidable, and readers would silently pick the EN one
        while writers may keep feeding the FR one.
    """
    if isinstance(noeud, dict):
        for cle, valeur in noeud.items():
            if isinstance(cle, str) and cle in LEGACY_STRUCTURAL_KEYS:
                attendue = LEGACY_STRUCTURAL_KEYS[cle]
                trouvailles.append({
                    "fichier": fichier,
                    "chemin": f"{chemin}.{cle}",
                    "trouvee": cle,
                    "attendue": attendue,
                    "genre": "ambigu" if attendue in noeud else "legacy",
                })
            _scanner_legacy(valeur, f"{chemin}.{cle}", trouvailles, fichier)
    elif isinstance(noeud, list):
        for i, item in enumerate(noeud):
            _scanner_legacy(item, f"{chemin}[{i}]", trouvailles, fichier)


def formater_erreur_legacy(trouvailles: list[dict]) -> str:
    """Builds the actionable failure message (file, offending key, expected key,
    migration command, and how to override)."""
    lignes = [
        "❌ LEGACY (pre-rename FRENCH) KEYS DETECTED — refusing to load this campaign.",
        "",
        "The engine reads ENGLISH structural keys. The keys below are still in their",
        "old French form, so every reader resolves them to EMPTY and the session would",
        "be played on a silently empty world (this is exactly how a real campaign lost",
        "38 locations, 10 actors and 61 events without a single warning).",
        "",
    ]
    par_fichier: dict[str, list[dict]] = {}
    for t in trouvailles:
        par_fichier.setdefault(t["fichier"], []).append(t)

    for fichier, items in par_fichier.items():
        lignes.append(f"  {fichier}")
        vus = set()
        for t in items:
            # Collapse the same key repeated across list items into one line.
            cle_courte = (t["chemin"].split("[")[0], t["trouvee"])
            if cle_courte in vus:
                continue
            vus.add(cle_courte)
            if t["genre"] == "ambigu":
                lignes.append(
                    f"    ✗ {t['chemin']}  → French key '{t['trouvee']}' COEXISTS with "
                    f"its English twin '{t['attendue']}' (ambiguous: which one is authoritative?)"
                )
            else:
                lignes.append(
                    f"    ✗ {t['chemin']}  → found '{t['trouvee']}', expected '{t['attendue']}'"
                )
        lignes.append("")

    lignes += [
        "FIX — migrate the campaign (dry-run first, it writes nothing):",
        f"    {_MIGRATION_CMD.replace(' --apply', '')}",
        f"    {_MIGRATION_CMD}",
        "",
        "OVERRIDE — only if these French keys are intentional (inspecting an",
        "un-migrated backup, deliberate test data…). The engine will then read them",
        "as empty; you accept that:",
        f"    {ENV_ALLOW_LEGACY}=1 python3 .../load_campaign.py <campaign_dir>",
        "    …or pass --allow-legacy-keys on the command line.",
    ]
    return "\n".join(lignes)


def verifier_cles_legacy(campagne: Path, autoriser: bool | None = None) -> list[dict]:
    """FAIL-LOUD check: refuse a campaign still written with FRENCH structural keys.

    `autoriser=None` (default) consults the environment variable
    MGM_ALLOW_LEGACY_KEYS; pass True/False to decide explicitly (the CLI flag
    --allow-legacy-keys passes True).

    Returns the list of findings (empty when the campaign is clean).
    Raises LegacyKeysError when findings exist and the override is not set.
    Unreadable/absent files are skipped here — reporting broken JSON is the
    caller's job (load_campaign returns exit 2 for that on its own).
    """
    campagne = Path(campagne)
    if autoriser is None:
        autoriser = _env_autorise_legacy()

    trouvailles: list[dict] = []
    for nom_fichier in FICHIERS_SCANNES:
        chemin = campagne / nom_fichier
        if not chemin.is_file():
            continue
        try:
            data = _load_json(chemin)
        except (OSError, json.JSONDecodeError):
            continue  # not our error to report
        _scanner_legacy(data, "$", trouvailles, str(chemin))

    if trouvailles and not autoriser:
        raise LegacyKeysError(formater_erreur_legacy(trouvailles), trouvailles)
    if trouvailles:
        print(
            f"⚠️  {len(trouvailles)} legacy FRENCH key(s) present — tolerated because the "
            f"override is active ({ENV_ALLOW_LEGACY}/--allow-legacy-keys). "
            "The engine WILL read these sections as empty.",
            file=sys.stderr,
        )
    return trouvailles


# --- Data access -------------------------------------------------------

def _get_path(data: dict, dotted: str):
    """Resolves a dotted path (e.g. 'rules.time.movements').

    Returns (present: bool, value). A value of None/[]/{}/'' counts as structurally
    present but 'empty' (reported differently).
    The '[].x' suffix tests whether AT LEAST one list element has key x.
    """
    # list case: "universe.regions[].biodiversite"
    if "[]." in dotted:
        head, tail = dotted.split("[].", 1)
        ok, lst = _get_path(data, head)
        if not ok or not isinstance(lst, list):
            return (False, None)
        for item in lst:
            if isinstance(item, dict) and item.get(tail) not in (None, "", [], {}):
                return (True, item.get(tail))
        return (False, None)

    cur = data
    for key in dotted.split("."):
        if isinstance(cur, dict) and key in cur:
            cur = cur[key]
        else:
            return (False, None)
    return (True, cur)


def _is_empty(value) -> bool:
    return value in (None, "", [], {})


def _load_json(path: Path):
    with path.open(encoding="utf-8") as fh:
        return json.load(fh)


# --- Self-test core -------------------------------------------------------

def analyser(campagne: Path, autoriser_legacy: bool | None = None) -> dict:
    """Builds the readiness report for a campaign (structured dict).

    Runs the FAIL-LOUD legacy-key guard FIRST: an un-migrated campaign must not
    be declared READY on the strength of sections the engine cannot even see.
    Raises LegacyKeysError unless the override is active.
    """
    monde_path = campagne / "world.json"
    pnj_path = campagne / "npcs.json"

    verifier_cles_legacy(campagne, autoriser=autoriser_legacy)

    monde = _load_json(monde_path)
    pnj_present = pnj_path.is_file()
    pnj_data = _load_json(pnj_path) if pnj_present else None

    bloc = monde.get("modules", {})
    if not isinstance(bloc, dict):
        raise ValueError("world.json > modules missing or is not an object")

    rapport = {
        "campagne": campagne.name,
        "regime": monde.get("meta", {}).get("time", {}).get("regime", "?"),
        "modules_actifs": [],
        "modules_inactifs": [],
        "fichiers_manquants": [],
        "donnees_manquantes": [],   # blocking — required section ABSENT
        "donnees_vides": [],        # warning — section present but EMPTY (to be filled during play)
        "donnees_info": [],         # soft — progressive requirement
        "cles_inconnues": [],
        "ok": True,
    }

    # Modules declared but outside the registry (typo in a key, etc.)
    for cle in bloc:
        if cle in NON_MODULE_KEYS:
            continue
        if cle not in MODULES:
            rapport["cles_inconnues"].append(cle)
            rapport["ok"] = False

    for cle, spec in MODULES.items():
        entry = bloc.get(cle)
        actif = bool(entry.get("actif")) if isinstance(entry, dict) else False

        if not actif:
            rapport["modules_inactifs"].append(cle)
            continue

        # --- active module: file + data ---
        fichier = spec["fichier"]
        chemin_fichier = MODULES_DIR / fichier
        fichier_ok = chemin_fichier.is_file()
        if not fichier_ok:
            rapport["fichiers_manquants"].append(f"{cle} -> references/modules/{fichier}")
            rapport["ok"] = False

        manques = []   # required section ABSENT → blocking
        vides = []     # required section present but EMPTY → warning
        for groupe in spec["requis"]:
            etat, detail = _verifier_groupe(groupe, monde, pnj_present, pnj_data)
            if etat == "absent":
                manques.append(detail)
            elif etat == "vide":
                vides.append(detail)
        if manques:
            for m in manques:
                rapport["donnees_manquantes"].append(f"{cle} : {m}")
            rapport["ok"] = False
        for v in vides:
            rapport["donnees_vides"].append(f"{cle} : {v}")

        infos = []
        for chemin in spec["info"]:
            etat, _ = _verifier_chemin(chemin, monde, pnj_present, pnj_data)
            if etat != "present":
                infos.append(chemin)
        if infos:
            rapport["donnees_info"].append({"module": cle, "chemins": infos})

        rapport["modules_actifs"].append({
            "cle": cle,
            "fichier": f"references/modules/{fichier}",
            "fichier_present": fichier_ok,
            "donnees_ok": not manques,
            "donnees_vides": bool(vides),
        })

    return rapport


def _verifier_chemin(chemin: str, monde: dict, pnj_present: bool, pnj_data):
    """Returns (state, human_label) with state ∈ {present, vide, absent}.

    - present : the key exists AND carries content;
    - vide    : the key exists but is None/[]/{}/'' (structure there, to be filled during play);
    - absent  : the key does not exist at all (the module has no data support).
    """
    if chemin.startswith("npcs.json:"):
        champ = chemin.split(":", 1)[1]
        if champ == "*":
            return ("present" if pnj_present else "absent", "npcs.json")
        if not pnj_present:
            return ("absent", f"npcs.json>{champ}")
        liste = _pnj_liste(pnj_data)
        ok = any(
            isinstance(p, dict) and p.get(champ) not in (None, "", [], {})
            for p in liste
        )
        return ("present" if ok else "vide", f"npcs.json>{champ}")
    present, value = _get_path(monde, chemin)
    if not present:
        return ("absent", chemin)
    return ("vide" if _is_empty(value) else "present", chemin)


def _verifier_groupe(groupe, monde, pnj_present, pnj_data):
    """Evaluates an "OR" group of paths.

    Returns (state, label):
    - present if AT LEAST one path is present and non-empty;
    - vide    if none is full but at least one exists (empty);
    - absent  if no path exists at all.
    """
    libelles = []
    meilleur = "absent"
    libelle_vide = None
    for chemin in groupe:
        etat, libelle = _verifier_chemin(chemin, monde, pnj_present, pnj_data)
        libelles.append(libelle)
        if etat == "present":
            return ("present", libelle)
        if etat == "vide":
            meilleur = "vide"
            libelle_vide = libelle
    if meilleur == "vide":
        return ("vide", f"{libelle_vide} present but empty (to be filled during play)")
    if len(libelles) == 1:
        return ("absent", f"{libelles[0]} absent")
    return ("absent", "none of [" + " | ".join(libelles) + "] present")


def _pnj_liste(pnj_data):
    """Accepts npcs.json as a bare list OR {"npcs": [...]} (like check_session.py)."""
    if isinstance(pnj_data, list):
        return pnj_data
    if isinstance(pnj_data, dict):
        if isinstance(pnj_data.get("npcs"), list):
            return pnj_data["npcs"]
        for v in pnj_data.values():
            if isinstance(v, list) and v and isinstance(v[0], dict):
                return v
    return []


# --- Rendering -------------------------------------------------------------------

def afficher(rapport: dict) -> None:
    print(f"🧩 READINESS — {rapport['campagne']}  (regime: {rapport['regime']})")
    print("─" * 60)

    actifs = rapport["modules_actifs"]
    inactifs = rapport["modules_inactifs"]

    print(f"⚙️  ACTIVE Modules ({len(actifs)}) :")
    if not actifs:
        print("    (none)")
    for m in actifs:
        fic = "✅" if m["fichier_present"] else "❌ MISSING"
        if not m["donnees_ok"]:
            don = "🔴 required section absent"
        elif m["donnees_vides"]:
            don = "🟡 present but empty"
        else:
            don = "✅"
        print(f"    • {m['cle']:<20} → {m['fichier']}  [file {fic}]  [data {don}]")

    print(f"\n💤 Inactive modules ({len(inactifs)}) : "
          + (", ".join(inactifs) if inactifs else "(none)"))

    if rapport["cles_inconnues"]:
        print("\n🔴 UNKNOWN module keys (typo?) :")
        for c in rapport["cles_inconnues"]:
            print(f"    • {c}  (expected one of: {', '.join(MODULES)})")

    if rapport["fichiers_manquants"]:
        print("\n🔴 MISSING module files :")
        for f in rapport["fichiers_manquants"]:
            print(f"    • {f}")

    if rapport["donnees_manquantes"]:
        print("\n🔴 REQUIRED data sections absent (active module without its data support) :")
        for d in rapport["donnees_manquantes"]:
            print(f"    • {d}")

    if rapport["donnees_vides"]:
        print("\n🟡 Sections present but EMPTY (structure there, to be filled during play — non-blocking) :")
        for d in rapport["donnees_vides"]:
            print(f"    • {d}")

    if rapport["donnees_info"]:
        print("\nℹ️  Soft data (filled during play — non-blocking) :")
        for item in rapport["donnees_info"]:
            print(f"    • {item['module']} : {', '.join(item['chemins'])}")

    print("\n" + "─" * 60)
    if rapport["ok"]:
        print("✅ Campaign READY — active modules consistent, files present, required data there.")
    else:
        print("❌ INCONSISTENCY — fix the 🔴 issues above before playing.")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="load_campaign.py",
        description="Campaign load self-test for MJ Tonnerre (active modules, "
                    "reference files, required data sections).",
        epilog="Exit: 0 ready · 1 inconsistency · 2 usage/not found/broken JSON.",
    )
    parser.add_argument("campagne",
                        help="Path to the campaign folder (containing world.json).")
    parser.add_argument("--json", action="store_true",
                        help="Machine output (JSON) instead of the human-readable report.")
    parser.add_argument("--allow-legacy-keys", action="store_true", dest="allow_legacy",
                        help="Do NOT fail on pre-rename FRENCH structural keys (univers, "
                             "etat_global, acteurs, evenements…); print a warning and carry on. "
                             f"Equivalent to {ENV_ALLOW_LEGACY}=1. The engine will read the "
                             "affected sections as EMPTY.")
    args = parser.parse_args(argv)

    campagne = Path(args.campagne)
    monde_path = campagne / "world.json"
    if not campagne.is_dir() or not monde_path.is_file():
        print(f"❌ Campaign not found: {monde_path} does not exist.", file=sys.stderr)
        return 2

    try:
        rapport = analyser(campagne, autoriser_legacy=args.allow_legacy or None)
    except LegacyKeysError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except json.JSONDecodeError as exc:
        print(f"❌ Broken JSON in {campagne}: {exc}", file=sys.stderr)
        return 2
    except (OSError, ValueError) as exc:
        print(f"❌ Error: {exc}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(rapport, ensure_ascii=False, indent=2))
    else:
        afficher(rapport)

    return 0 if rapport["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
