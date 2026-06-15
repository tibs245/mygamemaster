#!/usr/bin/env python3
"""
add_action.py — Adds one (or more) action(s) to a session log.

Replaces the boilerplate `python3 << EOF … json.load → actions.append → json.dump`
that the GM copies every turn. The model only needs to provide the action data;
the script handles loading, appending, ATOMIC writing (via worldlib:
ensure_ascii=False, indent=2, \\n final, mkstemp+fsync+replace) and JSON
re-validation. A single call, deterministic.

Action format (see sessions/*.json — free schema, additionalProperties):
  {
    "timestamp": "Jour 7, début de soirée",   recommended
    "type": "dialogue",                        recommended (action|dialogue|meta|…)
    "joueur": "Rubis",                         recommended
    "description": "…",                        REQUIRED (core of the action)
    "details": { … },                          optional (free object)
    "resultat": "…"                            recommended
  }
Only `description` is required; the other recommended keys only trigger a
warning on stderr (the log stays consistent without blocking the turn).

Target: either a campaign + a session number, or a direct path.
  python3 add_action.py <campaign> <session>     # e.g. … la-naissance-dun-roi 9
  python3 add_action.py <sessions/009.json>       # direct path

Action data — your choice:
  • stdin (default)        python3 add_action.py CAMP 9 <<'EOF'\n{…}\nEOF
  • inline                 python3 add_action.py CAMP 9 --action '{…}'
  • fichier                python3 add_action.py CAMP 9 --fichier act.json
A single object OR an array of objects (each appended in order).

Usage:
  python3 add_action.py <campaign> <session> [--action JSON | --fichier F]
  python3 add_action.py <session.json>       [--action JSON | --fichier F]
  python3 add_action.py … --dry-run          # validate + preview, do not write
  python3 add_action.py … --json             # machine output

Exit codes:
  0  action(s) added (or dry-run OK)
  1  invalid data (broken JSON, not an object, missing description…)
  2  usage error (session not found, non-session file…)
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


# Non-blocking keys but expected to keep the log readable.
CLES_RECOMMANDEES = ("timestamp", "type", "joueur", "resultat")


def _err(msg: str) -> None:
    print(msg, file=sys.stderr)


def resoudre_session(campagne: str, session: str | None) -> Path:
    """Returns the path to the sessions/NNN.json file.

    Two accepted inputs:
      • a direct path to a .json (session ignored);
      • a campaign (directory) + a session number ("9" → "009.json",
        an already-complete name "009" is preserved as-is).
    Raises ValueError (→ code 2) if the input is inconsistent.
    """
    base = _resoudre(campagne)
    if base.suffix == ".json":
        return base
    if base.is_file():
        raise ValueError(f"« {campagne} » is a file but not a .json.")
    if session is None:
        raise ValueError(
            "session number missing (e.g.: add_action.py <campaign> 9).")
    nom = session.strip()
    if nom.endswith(".json"):
        nom = nom[:-5]
    # Pure number → zero-padded to 3 digits (009); otherwise name kept as-is.
    if nom.isdigit():
        nom = nom.zfill(3)
    return base / "sessions" / f"{nom}.json"


def lire_donnee(args) -> str:
    """Retrieves the action JSON text from --action, --fichier, or stdin."""
    if args.action is not None:
        return args.action
    if args.fichier is not None:
        return Path(args.fichier).read_text(encoding="utf-8")
    if sys.stdin.isatty():
        raise ValueError(
            "no action data: pass --action, --fichier, or a JSON on stdin.")
    return sys.stdin.read()


def normaliser_actions(donnee_txt: str) -> list[dict]:
    """Parses the JSON and returns a LIST of actions (single object → list of 1).

    Validates that each action is an object carrying a non-empty `description`.
    Raises ValueError (→ code 1) on broken JSON / invalid shape.
    """
    txt = donnee_txt.strip()
    if not txt:
        raise ValueError("empty action data.")
    try:
        data = json.loads(txt)
    except json.JSONDecodeError as e:
        raise ValueError(f"broken JSON: {e}") from e

    actions = data if isinstance(data, list) else [data]
    if not actions:
        raise ValueError("empty actions array.")
    for i, act in enumerate(actions):
        ref = f"action[{i}]" if len(actions) > 1 else "action"
        if not isinstance(act, dict):
            raise ValueError(f"{ref} is not a JSON object.")
        desc = act.get("description")
        if not isinstance(desc, str) or not desc.strip():
            raise ValueError(f"{ref}: key « description » required (non-empty string).")
    return actions


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Adds one or more action(s) to a MJ Tonnerre session log.")
    ap.add_argument("campagne",
                    help="campaign directory, OR direct path to sessions/NNN.json")
    ap.add_argument("session", nargs="?",
                    help="session number (e.g. 9 or 009) — unused if direct path")
    src = ap.add_mutually_exclusive_group()
    src.add_argument("--action", help="the action as inline JSON (object or array)")
    src.add_argument("--fichier", help="JSON file containing the action (object or array)")
    ap.add_argument("--dry-run", action="store_true",
                    help="validate and preview without writing")
    ap.add_argument("--json", action="store_true", dest="sortie_json",
                    help="machine output (JSON)")
    args = ap.parse_args(argv)

    # 1) Resolve the target session.
    try:
        chemin = resoudre_session(args.campagne, args.session)
    except ValueError as e:
        _err(f"❌ {e}")
        return 2
    if not chemin.is_file():
        _err(f"❌ session not found: {chemin}")
        return 2

    # 2) Load + verify that it is indeed a session log.
    sentinelle = object()
    session = _charger(chemin, sentinelle)
    if session is sentinelle or not isinstance(session, dict):
        _err(f"❌ session JSON unreadable or non-conforming: {chemin}")
        return 2
    actions_existantes = session.get("actions")
    if actions_existantes is None:
        actions_existantes = []
        session["actions"] = actions_existantes
    elif not isinstance(actions_existantes, list):
        _err(f"❌ « actions » is not an array in {chemin}")
        return 2

    # 3) Read + normalize the action(s).
    try:
        nouvelles = normaliser_actions(lire_donnee(args))
    except (ValueError, OSError) as e:
        _err(f"❌ {e}")
        return 1

    # Soft warnings on recommended keys (non-blocking).
    for i, act in enumerate(nouvelles):
        manquantes = [k for k in CLES_RECOMMANDEES if not act.get(k)]
        if manquantes:
            ref = f"action[{i}]" if len(nouvelles) > 1 else "action"
            _err(f"⚠ {ref}: recommended keys missing — {', '.join(manquantes)}")

    avant = len(actions_existantes)
    total = avant + len(nouvelles)

    if args.dry_run:
        if args.sortie_json:
            print(json.dumps({"dry_run": True, "fichier": str(chemin),
                              "ajoutees": len(nouvelles), "avant": avant,
                              "total": total}, ensure_ascii=False))
        else:
            print(f"[dry-run] {len(nouvelles)} action(s) would bring "
                  f"{avant} → {total} in {chemin.name} (not written).")
        return 0

    # 4) Append + atomic write.
    actions_existantes.extend(nouvelles)
    try:
        _ecrire(chemin, session)
    except OSError as e:
        _err(f"❌ write failure: {e}")
        return 1

    # 5) Re-validation: re-read the written file (the auto-commit hook will pick it up).
    relu = _charger(chemin, sentinelle)
    if relu is sentinelle or not isinstance(relu, dict) \
            or len(relu.get("actions", [])) != total:
        _err(f"❌ inconsistent re-read after write: {chemin}")
        return 1

    if args.sortie_json:
        print(json.dumps({"fichier": str(chemin), "ajoutees": len(nouvelles),
                          "total": total}, ensure_ascii=False))
    else:
        suffixe = "s" if len(nouvelles) > 1 else ""
        print(f"✓ {len(nouvelles)} action{suffixe} added → "
              f"total actions: {total} ({chemin.name})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
