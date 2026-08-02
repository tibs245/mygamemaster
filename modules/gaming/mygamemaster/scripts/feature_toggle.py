#!/usr/bin/env python3
"""feature_toggle.py — Enables/disables a feature flag (meta.features) AT RUNTIME (hot).

`world.json` is re-read at EVERY turn by hooks and scripts (each invocation
is a fresh process): a toggle here takes effect on the NEXT turn, **without
redeploying** the container. This is the opposite of the environment variables
`MGM_FEATURE_*`, which are frozen at startup (= cold).

Reserved for admins (defense-in-depth): for a MUTATION, this script applies a
deterministic GATE — `--author <id>` must appear in `meta.admins` (or the env
`MGM_ADMIN_IDS`). NON-EMPTY admin list + author absent/non-admin → REFUSED (exit 4).
Empty list → allowed, with a note "gate inactive". `--list` remains open to all.
The calling skill/hook also verifies identity upstream and passes `--author`.

Two axis families:
  • "soft" (traceability, verbosite, images, tts) — no direct impact on game state:
    safe to toggle at any time.
  • "structural" (temporality, living_npcs_factions) — affect the simulation:
    hot toggle is possible, but RECOMMENDED at session boundaries (a change
    mid-session can leave scheduled events / plans in limbo) →
    the script emits a warning.

Usage:
  feature_toggle.py <campaign> --list
  feature_toggle.py <campaign> <axis> on|off [--author <id>] [--json]

Pure stdlib. Exit codes: 0 OK · 2 usage / campaign or axis invalid ·
4 mutation refused (author not an admin while an admin list is configured).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path

# Shared "falsy" coercion table (env AND meta.features fallback): a JSON
# string value "off"/"false"/… must be read as False, not as bool("off")=True.
_FALSY = ("0", "false", "off", "non", "no")

SCRIPTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS_DIR))
try:
    import worldlib as W  # FEATURES, features(), charger_json(), sauver_json_atomique()
    _FEATURES = tuple(W.FEATURES)
    _charger = W.charger_json
    _features_eff = W.features
    _ecrire = W.sauver_json_atomique  # race-safe atomic write (mkstemp+fsync+replace)
except Exception:  # fail-open: full autonomy if worldlib is unavailable
    _FEATURES = ("traceability", "verbosity", "living_npcs_factions", "temporality", "images", "tts")

    def _charger(path):
        try:
            with open(path, encoding="utf-8") as fh:
                return json.load(fh)
        except Exception:
            return None

    def _features_eff(monde):  # cascade meta.features > env > True (minimal fallback)
        f = ((monde or {}).get("meta") or {}).get("features") or {}
        out = {}
        for ax in _FEATURES:
            env = os.environ.get("MGM_FEATURE_" + ax.upper())
            d = True if env is None else str(env).strip().lower() not in _FALSY
            # We COERCE the world.json value like the env: a string "off" read
            # via bool() would be True incorrectly — map it through the _FALSY table.
            v = f.get(ax, d)
            out[ax] = d if v is None else (
                bool(v) if isinstance(v, bool) else str(v).strip().lower() not in _FALSY)
        return out

    def _ecrire(path, data):
        """Race-safe fallback WITHOUT worldlib: mkstemp (unique name) + fsync + os.replace.

        Do NOT use a fixed tmp name ("world.json.tmp"): two concurrent processes
        would overwrite each other. mkstemp guarantees a unique name per call.
        """
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        texte = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
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

HOT = ("traceability", "verbosity", "images", "tts")   # safe to toggle hot
STRUCTURAL = ("temporality", "living_npcs_factions")   # preferably toggled between sessions

_ON = ("on", "1", "true", "oui", "yes", "actif")
_OFF = ("off", "0", "false", "non", "no", "inactif")


def _admins(monde) -> set:
    """Set of admin ids: meta.admins ∪ MGM_ADMIN_IDS (csv). Same list as the
    hook bypass (_lib.admins). Empty ⇒ gate inactive (allows + note)."""
    ids = set()
    for x in ((monde or {}).get("meta") or {}).get("admins") or []:
        ids.add(str(x))
    for x in (os.environ.get("MGM_ADMIN_IDS", "") or "").split(","):
        x = x.strip()
        if x:
            ids.add(x)
    return ids


def _tts_auto(monde, feat: dict) -> bool:
    """Resolved state of the AUTOMATIC voice, as hooks/_lib.hooks_cfg resolves it:
    axis `tts` gates it, then meta.hooks.tts_auto, then env MGM_TTS_AUTO, then False.

    Replicated rather than imported: this script must keep running when the hooks
    package is not on the path (same fail-open contract as _features_eff above)."""
    if not feat.get("tts"):
        return False
    h = ((monde or {}).get("meta") or {}).get("hooks") or {}
    v = h.get("tts_auto", os.environ.get("MGM_TTS_AUTO"))
    if v is None:
        return False
    return bool(v) if isinstance(v, bool) else str(v).strip().lower() not in _FALSY


def _afficher_etat(nom: str, feat: dict, as_json: bool, monde=None) -> None:
    auto = _tts_auto(monde, feat)
    if as_json:
        print(json.dumps({"features": feat, "tts_auto": auto}, ensure_ascii=False))
        return
    print("⚙ Features — %s" % nom)
    for ax in _FEATURES:
        famille = "soft" if ax in HOT else "structural"
        # The `tts` row alone is not an answer to "why is there no voice?": the axis
        # can be ON with the per-turn voice opted out, which is the default.
        extra = ""
        if ax == "tts" and feat[ax]:
            extra = ("  — auto-voice: ON" if auto
                     else "  — auto-voice: OFF (opt-in; !raconte works)")
        print("   %s %-22s : %-3s  (%s)%s" % (
            "🟢" if feat[ax] else "⚪", ax, "ON" if feat[ax] else "OFF", famille, extra))
    if feat.get("tts") and not auto:
        print("   ↳ no automatic voice per turn: MGM_TTS_AUTO=1 or meta.hooks.tts_auto=true "
              "to opt in. Silent while opted in? mygamemaster-tts/scripts/tts_doctor.py")


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Enables/disables a feature flag (meta.features) at runtime (hot).")
    ap.add_argument("campagne", help="campaign folder (contains world.json)")
    ap.add_argument("axe", nargs="?", help="one of the 6 axes: %s" % ", ".join(_FEATURES))
    ap.add_argument("valeur", nargs="?", help="on | off")
    ap.add_argument("--list", action="store_true", help="display the effective state of all 6 axes")
    ap.add_argument("--author", default=None,
                    help="id of the command author (admin gate for a mutation; "
                         "compared against meta.admins / MGM_ADMIN_IDS)")
    ap.add_argument("--json", action="store_true", help="JSON output")
    a = ap.parse_args()

    campagne = Path(a.campagne)
    monde_path = campagne / "world.json"
    if not monde_path.exists():
        print("🔴 campaign not found: %s" % monde_path, file=sys.stderr)
        return 2

    monde = _charger(monde_path)
    if not isinstance(monde, dict):
        print("🔴 world.json unreadable: %s" % monde_path, file=sys.stderr)
        return 2
    feat = _features_eff(monde)

    # No axis or --list → display effective state.
    if a.list or not a.axe:
        _afficher_etat(campagne.name, feat, a.json, monde)
        return 0

    axe = a.axe.strip().lower()
    if axe not in _FEATURES:
        print("🔴 unknown axis: %s (expected: %s)" % (axe, ", ".join(_FEATURES)), file=sys.stderr)
        return 2
    if not a.valeur:
        print("🔴 missing value (on|off)", file=sys.stderr)
        return 2
    v = a.valeur.strip().lower()
    if v in _ON:
        nouv = True
    elif v in _OFF:
        nouv = False
    else:
        print("🔴 invalid value: %s (expected on|off)" % a.valeur, file=sys.stderr)
        return 2

    # ── Admin gate (MUTATION only; --list remains open to all). ─────────────────
    # admins = meta.admins ∪ MGM_ADMIN_IDS. If NON-EMPTY and the author is not
    # a member (or --author absent) → REFUSED (exit 4). If EMPTY → allowed + note.
    admins = _admins(monde)
    if admins:
        author = (a.author or "").strip()
        if not author or author not in admins:
            print("🔒 Mutation reserved for admins (meta.admins / MGM_ADMIN_IDS). "
                  "Author \"%s\" not authorized." % (author or "—"), file=sys.stderr)
            return 4
    else:
        print("ℹ no admin configured (meta.admins / MGM_ADMIN_IDS) — gate inactive.",
              file=sys.stderr)

    ancien = bool(feat[axe])
    # Mutation of meta.features (block created if absent).
    meta = monde.setdefault("meta", {})
    if not isinstance(meta, dict):
        meta = monde["meta"] = {}
    feats = meta.setdefault("features", {})
    if not isinstance(feats, dict):
        feats = meta["features"] = {}
    feats[axe] = nouv
    _ecrire(monde_path, monde)

    avert = ""
    if axe in STRUCTURAL:
        avert = (" ⚠ structural axis: hot toggle mid-game may leave scheduled events "
                 "or plans in limbo — prefer session boundaries.")
    msg = "%s %s: %s → %s — takes effect on the next turn, no redeployment needed.%s" % (
        "🟢" if nouv else "⚪", axe, "ON" if ancien else "OFF", "ON" if nouv else "OFF", avert)

    if a.json:
        print(json.dumps({"axe": axe, "ancien": ancien, "nouveau": nouv,
                          "structurant": axe in STRUCTURAL, "message": msg}, ensure_ascii=False))
    else:
        print(msg)
    return 0


if __name__ == "__main__":
    sys.exit(main())
