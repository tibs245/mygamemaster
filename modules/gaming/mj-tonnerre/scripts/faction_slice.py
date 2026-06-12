#!/usr/bin/env python3
"""faction_slice.py — Write coordinator (SINGLE writer) anti-concurrency.

Guarantees Level 2 concurrency (cf. audit/06-niveau2-factions.md §7):
the SOURCE OF TRUTH remains the campaign files (monde.json / pnj.json).
An agent (NPC/Faction) NEVER edits a file directly: it receives a SLICE extracted
from its sheet, modifies it in its session, and the coordinator (this script) REINTEGRATES
the slice into the source file — serialized writer, validation before write,
atomic write. → N agents in parallel, ZERO concurrent writes.

Anti-divergence mechanism: `extract` attaches a FINGERPRINT (SHA-256 hash) of the
source state of the slice. `reintegrate` recomputes the fingerprint of the CURRENT
source state and compares it; if it diverges (another writer ran in between), the
script ABSTAINS and reports — it never overwrites a state that has changed.

Subcommands:
  extract <campaign> --faction <name>          → faction slice (sheet + clock) + fingerprint
  extract <campaign> --pnj <name>              → NPC slice (sheet) + fingerprint
  reintegrate <campaign> <slice.json>          → reintegrates the slice (--dry-run default, --apply)
  add-note <campaign> --pnj|--faction <name> "<text>"  → append to notes_privees[]

Stdlib only, no network. Reuses validate_json.py (no duplication).

Exit codes:
  0  success (extract produced / dry-run displayed / apply written)
  1  target not found (faction/NPC) OR abstention on divergent fingerprint
  2  usage error / file / broken JSON / post-write validation failed
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent
SLICE_VERSION = 1


# ─── Shared utilities ────────────────────────────────────────────────────────

def _fold(s: str) -> str:
    """Normalize for comparison: no accents, lowercase, reduced spaces."""
    s = unicodedata.normalize("NFD", str(s))
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return " ".join(s.lower().split())


def _empreinte(obj) -> str:
    """SHA-256 of a JSON object, canonically serialized (sorted keys)."""
    blob = json.dumps(obj, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _maintenant() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _lire_json(path: Path):
    if not path.exists():
        print(f"❌ Not found: {path}", file=sys.stderr)
        sys.exit(2)
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        print(f"❌ Invalid JSON ({path.name}): {e}", file=sys.stderr)
        sys.exit(2)


def _ecrire_atomique(path: Path, data) -> None:
    """Atomic write: tmp in the same folder, fsync, then os.replace."""
    texte = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    fd, tmp = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp",
                               dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(texte)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def _valider_json_fichier(path: Path) -> bool:
    """Reuses validate_json.py (no duplication). True if JSON is valid."""
    res = subprocess.run(
        [sys.executable, str(SCRIPTS_DIR / "validate_json.py"), str(path)],
        capture_output=True, text=True,
    )
    if res.returncode != 0:
        sys.stderr.write(res.stdout)
        sys.stderr.write(res.stderr)
    return res.returncode == 0


# ─── Container access (tolerates both pnj.json formats) ─────────────────────

def _pnj_charger(campagne: Path):
    """Load pnj.json → (raw_data, list). Tolerates bare list OR {"pnj":[...]}."""
    data = _lire_json(campagne / "pnj.json")
    if isinstance(data, list):
        return data, data
    if isinstance(data, dict):
        liste = data.get("pnj")
        if isinstance(liste, list):
            return data, liste
    print("❌ pnj.json: unrecognized container (expected list OR {\"pnj\":[...]}).",
          file=sys.stderr)
    sys.exit(2)


def _index_par_nom(liste, nom: str):
    """Return the index of the entry whose 'nom'/'faction' field matches, or -1."""
    cible = _fold(nom)
    for i, item in enumerate(liste):
        if not isinstance(item, dict):
            continue
        clef = item.get("nom") or item.get("faction") or ""
        if _fold(clef) == cible:
            return i
    # fallback: partial match
    for i, item in enumerate(liste):
        if not isinstance(item, dict):
            continue
        clef = item.get("nom") or item.get("faction") or ""
        if cible in _fold(clef):
            return i
    return -1


def _factions_liste(monde: dict):
    return monde.get("etat_global", {}).get("factions", []) or []


def _horloge_actions(monde: dict):
    return (monde.get("etat_global", {})
            .get("faction_actions_horloge", {})
            .get("actions", []) or [])


# ─── EXTRACT ──────────────────────────────────────────────────────────────────

def _tranche_faction(monde: dict, nom: str):
    """Build the slice of a faction: its sheet + its clock entries.

    Returns (slice_state, error_str|None). The slice_state is the exact object
    that will be re-hashed for divergence detection (sheet + clock linked).
    """
    factions = _factions_liste(monde)
    idx = _index_par_nom(factions, nom)
    if idx < 0:
        noms = ", ".join(f.get("nom", "?") for f in factions
                         if isinstance(f, dict))
        return None, (f"Faction «{nom}» not found. Available: {noms}")
    fiche = factions[idx]
    nom_reel = fiche.get("nom", nom)

    # clock entries linked to this faction (matched on the 'faction' field)
    horloge_liee = [a for a in _horloge_actions(monde)
                    if isinstance(a, dict)
                    and _fold(a.get("faction", "")) == _fold(nom_reel)]

    etat = {"fiche": fiche, "faction_actions_horloge": horloge_liee}
    return etat, None


def _tranche_pnj(campagne: Path, nom: str):
    """Build the slice of an NPC: its sheet. Returns (state, error|None)."""
    _, liste = _pnj_charger(campagne)
    idx = _index_par_nom(liste, nom)
    if idx < 0:
        noms = ", ".join(p.get("nom", "?") for p in liste if isinstance(p, dict))
        return None, (f"NPC «{nom}» not found. Available: {noms}")
    return {"fiche": liste[idx]}, None


def cmd_extract(args) -> int:
    campagne = Path(args.campagne)
    if (args.faction is None) == (args.pnj is None):
        print("❌ extract: specify EXACTLY one of --faction or --pnj.",
              file=sys.stderr)
        return 2

    if args.faction is not None:
        monde = _lire_json(campagne / "monde.json")
        etat, err = _tranche_faction(monde, args.faction)
        cible_type, cible_nom = "faction", args.faction
        source_fichier = "monde.json"
    else:
        etat, err = _tranche_pnj(campagne, args.pnj)
        cible_type, cible_nom = "pnj", args.pnj
        source_fichier = "pnj.json"

    if err:
        print(f"❌ {err}", file=sys.stderr)
        return 1

    nom_reel = etat["fiche"].get("nom", cible_nom)
    slice_obj = {
        "_slice_version": SLICE_VERSION,
        "type": cible_type,
        "campagne": campagne.name,
        "nom": nom_reel,
        "source_fichier": source_fichier,
        "extrait_le": _maintenant(),
        "empreinte_source": _empreinte(etat),
        "etat": etat,
    }

    sortie = json.dumps(slice_obj, ensure_ascii=False, indent=2)
    if args.output:
        Path(args.output).write_text(sortie + "\n", encoding="utf-8")
        print(f"✅ Slice {cible_type} «{nom_reel}» written → {args.output}",
              file=sys.stderr)
        print(f"   empreinte_source: {slice_obj['empreinte_source'][:16]}…",
              file=sys.stderr)
    else:
        print(sortie)
    return 0


# ─── REINTEGRATE ──────────────────────────────────────────────────────────────

def _etat_source_actuel(args_type: str, monde, campagne: Path, nom: str):
    """Recompute the CURRENT source state of a slice (for re-hashing)."""
    if args_type == "faction":
        return _tranche_faction(monde, nom)
    return _tranche_pnj(campagne, nom)


def cmd_reintegrate(args) -> int:
    campagne = Path(args.campagne)
    slice_obj = _lire_json(Path(args.slice))

    for clef in ("type", "nom", "etat", "empreinte_source"):
        if clef not in slice_obj:
            print(f"❌ Invalid slice: field «{clef}» missing.",
                  file=sys.stderr)
            return 2

    cible_type = slice_obj["type"]
    nom = slice_obj["nom"]
    if cible_type not in ("faction", "pnj"):
        print(f"❌ Unknown slice type: {cible_type!r}.", file=sys.stderr)
        return 2

    monde_path = campagne / "monde.json"
    pnj_path = campagne / "pnj.json"
    monde = _lire_json(monde_path) if cible_type == "faction" else None

    # ── FINGERPRINT PRE-CHECK: has the source state diverged since extract? ──
    etat_actuel, err = _etat_source_actuel(cible_type, monde, campagne, nom)
    if err:
        print(f"❌ {err}", file=sys.stderr)
        return 1

    empreinte_actuelle = _empreinte(etat_actuel)
    if empreinte_actuelle != slice_obj["empreinte_source"]:
        print("🔒 ABSTENTION — the source state has DIVERGED since extraction.",
              file=sys.stderr)
        print(f"   fingerprint at extract time: "
              f"{slice_obj['empreinte_source'][:16]}…", file=sys.stderr)
        print(f"   current source fingerprint : "
              f"{empreinte_actuelle[:16]}…", file=sys.stderr)
        print("   Another writer ran in between. No write performed — "
              "re-extract the slice then re-apply the changes.",
              file=sys.stderr)
        return 1

    # ── Source has not changed: safe to reintegrate. ──
    if cible_type == "faction":
        return _reintegrate_faction(args, campagne, monde_path, monde, slice_obj)
    return _reintegrate_pnj(args, campagne, pnj_path, slice_obj)


def _diff_lisible(avant: dict, apres: dict, titre: str) -> None:
    """Display a key-by-key diff (1 level) readable on stderr."""
    print(f"  ── {titre} ──", file=sys.stderr)
    cles = sorted(set(avant) | set(apres))
    aucun = True
    for k in cles:
        a, b = avant.get(k), apres.get(k)
        if a == b:
            continue
        aucun = False
        if k not in avant:
            print(f"   + {k} : {json.dumps(b, ensure_ascii=False)}", file=sys.stderr)
        elif k not in apres:
            print(f"   - {k} (removed)", file=sys.stderr)
        else:
            print(f"   ~ {k} :", file=sys.stderr)
            print(f"       before: {json.dumps(a, ensure_ascii=False)}", file=sys.stderr)
            print(f"       after : {json.dumps(b, ensure_ascii=False)}", file=sys.stderr)
    if aucun:
        print("   (no changes)", file=sys.stderr)


def _reintegrate_faction(args, campagne, monde_path, monde, slice_obj) -> int:
    nouvelle_fiche = slice_obj["etat"]["fiche"]
    nouvelle_horloge = slice_obj["etat"].get("faction_actions_horloge", [])
    nom = slice_obj["nom"]

    factions = _factions_liste(monde)
    idx = _index_par_nom(factions, nom)
    if idx < 0:
        print(f"❌ Faction «{nom}» has disappeared from monde.json.", file=sys.stderr)
        return 1

    ancienne = factions[idx]
    _diff_lisible(ancienne, nouvelle_fiche, f"Fiche faction « {nom} »")

    # Clock: replace the entries of THIS faction with those from the slice.
    horloge = (monde.setdefault("etat_global", {})
               .setdefault("faction_actions_horloge", {})
               .setdefault("actions", []))
    avant_horloge = [a for a in horloge if isinstance(a, dict)
                     and _fold(a.get("faction", "")) == _fold(nom)]
    if avant_horloge != nouvelle_horloge:
        print(f"  ── Faction clock «{nom}»: "
              f"{len(avant_horloge)} entry/entries → {len(nouvelle_horloge)} ──",
              file=sys.stderr)

    if not args.apply:
        print("ℹ️  DRY-RUN — no write performed (use --apply to write).",
              file=sys.stderr)
        return 0

    # Apply: sheet + clock
    factions[idx] = nouvelle_fiche
    autres = [a for a in horloge if not (isinstance(a, dict)
              and _fold(a.get("faction", "")) == _fold(nom))]
    monde["etat_global"]["faction_actions_horloge"]["actions"] = \
        autres + nouvelle_horloge

    return _ecrire_et_valider(monde_path, monde, f"faction « {nom} »")


def _reintegrate_pnj(args, campagne, pnj_path, slice_obj) -> int:
    nouvelle_fiche = slice_obj["etat"]["fiche"]
    nom = slice_obj["nom"]

    data, liste = _pnj_charger(campagne)
    idx = _index_par_nom(liste, nom)
    if idx < 0:
        print(f"❌ NPC «{nom}» has disappeared from pnj.json.", file=sys.stderr)
        return 1

    _diff_lisible(liste[idx], nouvelle_fiche, f"Fiche PNJ « {nom} »")

    if not args.apply:
        print("ℹ️  DRY-RUN — no write performed (use --apply to write).",
              file=sys.stderr)
        return 0

    liste[idx] = nouvelle_fiche
    # data is EITHER the list itself (mutated in place) OR {"pnj": liste}.
    return _ecrire_et_valider(pnj_path, data, f"PNJ « {nom} »")


def _ecrire_et_valider(path: Path, data, libelle: str) -> int:
    """Write atomically THEN validate via validate_json.py. Restore if invalid."""
    sauvegarde = path.read_text(encoding="utf-8")
    _ecrire_atomique(path, data)
    if not _valider_json_fichier(path):
        # Never leave a broken file: restore the original.
        _ecrire_atomique(path, json.loads(sauvegarde))
        print(f"❌ Write cancelled: the result did not validate — "
              f"{path.name} restored.", file=sys.stderr)
        return 2
    print(f"✅ Reintegrated: {libelle} → {path} (JSON validated, atomic write).",
          file=sys.stderr)
    return 0


# ─── ADD-NOTE (write-back from inner loop) ───────────────────────────────────

def cmd_add_note(args) -> int:
    campagne = Path(args.campagne)
    if (args.faction is None) == (args.pnj is None):
        print("❌ add-note: specify EXACTLY one of --faction or --pnj.",
              file=sys.stderr)
        return 2
    texte = args.texte.strip()
    if not texte:
        print("❌ add-note: empty note.", file=sys.stderr)
        return 2

    if args.pnj is not None:
        data, liste = _pnj_charger(campagne)
        idx = _index_par_nom(liste, args.pnj)
        path, cible = campagne / "pnj.json", args.pnj
        conteneur, racine = liste, data
    else:
        monde = _lire_json(campagne / "monde.json")
        liste = _factions_liste(monde)
        idx = _index_par_nom(liste, args.faction)
        path, cible = campagne / "monde.json", args.faction
        conteneur, racine = liste, monde

    if idx < 0:
        noms = ", ".join(x.get("nom", "?") for x in conteneur
                         if isinstance(x, dict))
        print(f"❌ Target «{cible}» not found. Available: {noms}",
              file=sys.stderr)
        return 1

    fiche = conteneur[idx]
    notes = fiche.get("notes_privees")
    if not isinstance(notes, list):
        notes = []

    # Idempotency: do not re-add an identical CONSECUTIVE note.
    if notes and _fold(notes[-1]) == _fold(texte):
        print(f"ℹ️  Note identical to the last one for «{cible}» — not re-added "
              "(idempotent).", file=sys.stderr)
        return 0

    notes = notes + [texte]
    fiche["notes_privees"] = notes
    print(f"  📝 «{cible}» notes_privees: {len(notes) - 1} → {len(notes)} "
          f"entry/entries", file=sys.stderr)
    print(f"     + {texte}", file=sys.stderr)

    if not args.apply:
        print("ℹ️  DRY-RUN — no write performed (use --apply to write).",
              file=sys.stderr)
        return 0

    return _ecrire_et_valider(path, racine, f"note de « {cible} »")


# ─── CLI ──────────────────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="faction_slice.py",
        description="Write coordinator (single writer) anti-concurrency "
                    "for NPC/Faction agents at Level 2 (audit/06 §7).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  faction_slice.py extract <camp> --faction \"La Bande du Corbeau\" -o slice.json\n"
            "  faction_slice.py extract <camp> --pnj Berthe\n"
            "  faction_slice.py reintegrate <camp> slice.json            # dry-run by default\n"
            "  faction_slice.py reintegrate <camp> slice.json --apply\n"
            "  faction_slice.py add-note <camp> --pnj Berthe \"Je me méfie de Drageon.\" --apply\n"
            "\nExit: 0 success · 1 target not found / divergence abstention · 2 usage/JSON/validation."
        ),
    )
    sub = ap.add_subparsers(dest="commande", required=True)

    p_ex = sub.add_parser("extract", help="Extract the slice of a faction or NPC (+ fingerprint).")
    p_ex.add_argument("campagne", help="Path to the campaign folder.")
    g = p_ex.add_mutually_exclusive_group(required=True)
    g.add_argument("--faction", help="Faction name (tolerates accents/case).")
    g.add_argument("--pnj", help="NPC name (tolerates accents/case).")
    p_ex.add_argument("-o", "--output", help="Output file (default: stdout).")
    p_ex.set_defaults(func=cmd_extract)

    p_re = sub.add_parser("reintegrate", help="Reintegrate a slice (single writer, fingerprint pre-check).")
    p_re.add_argument("campagne", help="Path to the campaign folder.")
    p_re.add_argument("slice", help="Slice file produced by extract.")
    p_re.add_argument("--apply", action="store_true",
                      help="Actually write (default: --dry-run).")
    p_re.set_defaults(func=cmd_reintegrate)

    p_an = sub.add_parser("add-note", help="Append to the notes_privees[] array (for agent inner loop).")
    p_an.add_argument("campagne", help="Path to the campaign folder.")
    g2 = p_an.add_mutually_exclusive_group(required=True)
    g2.add_argument("--faction", help="Faction name.")
    g2.add_argument("--pnj", help="NPC name.")
    p_an.add_argument("texte", help="Text of the note to add.")
    p_an.add_argument("--apply", action="store_true",
                      help="Actually write (default: --dry-run).")
    p_an.set_defaults(func=cmd_add_note)

    return ap


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
