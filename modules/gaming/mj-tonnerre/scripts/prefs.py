#!/usr/bin/env python3
"""
prefs.py — Read/write a player's out-of-fiction PLAY PREFERENCES.

Per-player, table-style preferences (pacing, tone likes/dislikes, combat
verbosity, spotlight, content boundaries, "enjoys being deceived", plus any
custom key) live in the `preferences` block of that player's character sheet
(`personnages/<discord_id>.json`). They persist across sessions and are
surfaced to the GM each turn (hook pre_llm_call) so play can be tailored.

This is NOT in-fiction data — it is meta/table guidance about HOW the player
likes to be run, kept compartmentalized per player exactly like the sheet.

Documented keys (all optional; a missing/empty block changes nothing — fail-open):
  rythme            string  — preferred pacing
  ton_aime          list    — tone likes
  ton_evite         list    — tone dislikes
  verbosite_combat  string  — combat verbosity (e.g. concise|vivid)
  spotlight         string  — spotlight preferences
  limites_contenu   list    — content boundaries
  aime_etre_trompe  bool    — enjoys being deceived (fair foreshadowing)
  custom            object  — any extra free-form keys
Unknown top-level keys are accepted and stored under `custom` automatically.

Compartmentalization: this script only ever touches ONE player's file
(the one named by <discord_id>). It NEVER reads or returns another player's
preferences.

Usage:
  # Read the whole preferences block (JSON to stdout):
  python3 prefs.py <campaign> <discord_id> get
  # Read one key:
  python3 prefs.py <campaign> <discord_id> get <key>
  # Set a documented key (value parsed as JSON, falls back to raw string):
  python3 prefs.py <campaign> <discord_id> set rythme "slow-burn investigation"
  python3 prefs.py <campaign> <discord_id> set aime_etre_trompe true
  python3 prefs.py <campaign> <discord_id> set ton_aime '["mystery","lore"]'
  # Set a custom key (stored under preferences.custom):
  python3 prefs.py <campaign> <discord_id> set music_cues "play a sting on crits"
  # Remove a key:
  python3 prefs.py <campaign> <discord_id> unset rythme
  python3 prefs.py … set … --dry-run     # validate + preview, do not write
  python3 prefs.py … --json              # machine output

Exit codes:
  0  success (read / write / dry-run OK)
  1  invalid data (bad value, write failure)
  2  usage error (sheet not found, unreadable sheet…)
"""

import argparse
import json
import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS_DIR))
try:
    import worldlib as W  # charger_json(), sauver_json_atomique(), chemin_campagne()
    _charger = W.charger_json
    _ecrire = W.sauver_json_atomique
    _resoudre = W.chemin_campagne
except Exception:  # fail-open: standalone if worldlib unavailable
    import os
    import tempfile

    def _charger(chemin, defaut=None):
        try:
            with open(chemin, "r", encoding="utf-8") as f:
                return json.load(f)
        except FileNotFoundError:
            return defaut
        except (OSError, json.JSONDecodeError, ValueError):
            return defaut

    def _ecrire(chemin, donnees):
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
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise

    def _resoudre(arg):
        return Path(arg).expanduser().resolve()


# Documented top-level preference keys (kept FR to match sibling sheet keys
# such as notes_perso/objectifs; a later PR handles FR→EN renames).
CLES_DOCUMENTEES = (
    "rythme",
    "ton_aime",
    "ton_evite",
    "verbosite_combat",
    "spotlight",
    "limites_contenu",
    "aime_etre_trompe",
)
# Reserved keys that never get demoted into custom.
CLES_RESERVEES = set(CLES_DOCUMENTEES) | {"custom", "_description"}


def _err(msg: str) -> None:
    print(msg, file=sys.stderr)


def _resoudre_fiche(campagne: str, discord_id: str) -> Path:
    """Path to personnages/<discord_id>.json (or direct path to a .json)."""
    base = _resoudre(campagne)
    if base.suffix == ".json":
        return base
    return base / "personnages" / f"{discord_id}.json"


def _bloc_prefs(fiche: dict) -> dict:
    p = fiche.get("preferences")
    return p if isinstance(p, dict) else {}


def _parser_valeur(brut: str):
    """Parse a CLI value: try JSON (numbers/bools/arrays/objects), else raw string."""
    txt = brut.strip()
    try:
        return json.loads(txt)
    except (json.JSONDecodeError, ValueError):
        return brut


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="Read/write a player's out-of-fiction play preferences.")
    ap.add_argument("campagne",
                    help="campaign directory, OR direct path to personnages/<id>.json")
    ap.add_argument("discord_id",
                    help="player's Discord ID — unused if a direct path is given")
    ap.add_argument("action", choices=("get", "set", "unset"),
                    help="get | set <key> <value> | unset <key>")
    ap.add_argument("cle", nargs="?", help="preference key (for set/unset, or a single get)")
    ap.add_argument("valeur", nargs="?", help="value (for set) — parsed as JSON, else raw string")
    ap.add_argument("--dry-run", action="store_true",
                    help="validate and preview without writing")
    ap.add_argument("--json", action="store_true", dest="sortie_json",
                    help="machine output (JSON)")
    args = ap.parse_args(argv)

    chemin = _resoudre_fiche(args.campagne, args.discord_id)
    if not chemin.is_file():
        _err(f"❌ character sheet not found: {chemin}")
        return 2

    sentinelle = object()
    fiche = _charger(chemin, sentinelle)
    if fiche is sentinelle or not isinstance(fiche, dict):
        _err(f"❌ character sheet unreadable or non-conforming: {chemin}")
        return 2

    # ── GET ──────────────────────────────────────────────────────────────
    if args.action == "get":
        prefs = _bloc_prefs(fiche)
        if args.cle is None:
            print(json.dumps(prefs, ensure_ascii=False, indent=2))
            return 0
        # single key: documented top-level OR under custom
        if args.cle in prefs:
            valeur = prefs[args.cle]
        else:
            valeur = _bloc_prefs(fiche).get("custom", {}).get(args.cle) \
                if isinstance(prefs.get("custom"), dict) else None
        print(json.dumps(valeur, ensure_ascii=False))
        return 0

    # ── UNSET ────────────────────────────────────────────────────────────
    if args.action == "unset":
        if not args.cle:
            _err("❌ unset needs a key.")
            return 1
        prefs = dict(_bloc_prefs(fiche))
        removed = False
        if args.cle in prefs and args.cle not in ("custom", "_description"):
            del prefs[args.cle]
            removed = True
        elif isinstance(prefs.get("custom"), dict) and args.cle in prefs["custom"]:
            prefs["custom"] = {k: v for k, v in prefs["custom"].items() if k != args.cle}
            removed = True
        if not removed:
            _err(f"⚠ key « {args.cle} » not present — nothing to remove.")
            if args.sortie_json:
                print(json.dumps({"fichier": str(chemin), "removed": False,
                                  "cle": args.cle}, ensure_ascii=False))
            return 0
        return _ecrire_prefs(chemin, fiche, prefs, args,
                             resume=f"removed « {args.cle} »")

    # ── SET ──────────────────────────────────────────────────────────────
    if not args.cle:
        _err("❌ set needs a key and a value.")
        return 1
    if args.valeur is None:
        _err("❌ set needs a value: prefs.py CAMP ID set <key> <value>")
        return 1

    valeur = _parser_valeur(args.valeur)
    prefs = dict(_bloc_prefs(fiche))
    if args.cle in CLES_DOCUMENTEES:
        prefs[args.cle] = valeur
        emplacement = args.cle
    else:
        # unknown/custom key → stored under preferences.custom
        custom = dict(prefs.get("custom")) if isinstance(prefs.get("custom"), dict) else {}
        custom[args.cle] = valeur
        prefs["custom"] = custom
        emplacement = f"custom.{args.cle}"
    return _ecrire_prefs(chemin, fiche, prefs, args,
                         resume=f"{emplacement} = {json.dumps(valeur, ensure_ascii=False)}")


def _ecrire_prefs(chemin: Path, fiche: dict, prefs: dict, args, resume: str) -> int:
    """Write the updated preferences block back into the sheet (atomic)."""
    if args.dry_run:
        if args.sortie_json:
            print(json.dumps({"dry_run": True, "fichier": str(chemin),
                              "preferences": prefs}, ensure_ascii=False))
        else:
            print(f"[dry-run] would set {resume} in {chemin.name} (not written).")
        return 0

    fiche["preferences"] = prefs
    try:
        _ecrire(chemin, fiche)
    except OSError as e:
        _err(f"❌ write failure: {e}")
        return 1

    # Re-read to confirm a valid JSON landed (the auto-commit hook will pick it up).
    sentinelle = object()
    relu = _charger(chemin, sentinelle)
    if relu is sentinelle or not isinstance(relu, dict) \
            or not isinstance(relu.get("preferences"), dict):
        _err(f"❌ inconsistent re-read after write: {chemin}")
        return 1

    if args.sortie_json:
        print(json.dumps({"fichier": str(chemin), "preferences": prefs},
                         ensure_ascii=False))
    else:
        print(f"✓ preference saved: {resume} ({chemin.name})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
