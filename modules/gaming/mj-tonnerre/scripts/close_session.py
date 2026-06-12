#!/usr/bin/env python3
"""
close_session.py — Session closing pipeline in 1 command (MJ Tonnerre).

Chains the existing deterministic guards then a ~10-point pipeline check.
REFUSES (exit ≠ 0) if a blocking step fails. Does NOT commit on its own:
it PROPOSES a commit message and lets the GM/Steward decide
(option `--commit` documented but disabled by default).

Chained steps (reuses neighbouring scripts via subprocess):
  1. validate_json.py        <campaign>/           → BLOCKING if exit ≠ 0
  2. validator-distances.py  <campaign>/world.json → WARN (exit 1) / BLOCKING (exit 2)
  3. check_session.py        <campaign> [--session]→ BLOCKING if exit ≠ 0
  4. clock.py --dry-run      <campaign>            → ALERT if deadline elapsed

~10-point pipeline check (read-only, complements check_session):
  P1  session locations propagated into universe.regions[].locations
  P2  encountered NPCs filed in npcs.json
  P3  each faction has objectif_court_terme + objectif_long_terme
  P4  each faction present in faction_actions_horloge
  P5  clock up to date: no elapsed unresolved deadline (clock.py)
  P6  chronology: global_state.chronologie not empty
  P7  session log complete: heure_fin filled in
  P8  session log complete: resume not empty
  P9  session log complete: etat_fin present
  P10 timeline (UT regime): events.json present and valid

Usage:
  python3 close_session.py <campaign> [--session N]
  python3 close_session.py <campaign> --titre "..." --teaser "..."
  python3 close_session.py <campaign> --json
  python3 close_session.py <campaign> --commit        # explicit, see WARNING

Exit codes:
  0  pipeline green → closing possible (proposed commit message)
  1  at least one BLOCKING step missing → closing refused
  2  usage error (campaign/scripts not found)
"""

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent


def charger_json(chemin: Path):
    with open(chemin, "r", encoding="utf-8") as f:
        return json.load(f)


def lancer(script: str, args: list[str]) -> dict:
    """Launch a neighbouring script and capture exit code + stdout/stderr."""
    cmd = [sys.executable, str(SCRIPTS_DIR / script), *args]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        return {"script": script, "exit": proc.returncode,
                "stdout": proc.stdout, "stderr": proc.stderr}
    except FileNotFoundError:
        return {"script": script, "exit": 127, "stdout": "",
                "stderr": f"{script} not found in {SCRIPTS_DIR}"}
    except subprocess.TimeoutExpired:
        return {"script": script, "exit": 124, "stdout": "",
                "stderr": f"{script} exceeded timeout (120 s)"}


def _tick_post_si_actif(campagne: Path, num: int) -> dict:
    """B2 — run `world_tick.py post --apply` if actors.json exists.
    NON-BLOCKING: returns a trace dict, never raises.
    {'lance':bool,'exit':int,'stdout':str,'stderr':str,'raison':str}.

    Simplified gate: we do NOT read meta.hooks.tick_post here. world_tick.py
    guards ITSELF on features.temporalite (cf. _lib + docs/monde-vivant/10):
    if temporality is OFF, it performs a clean no-op exit 0. We only keep
    the `actors.json exists` check to avoid a useless call on a campaign
    without a living world.
    """
    if not (campagne / "actors.json").exists():
        return {"lance": False, "raison": "actors.json absent (living world not initialised)"}
    # ⚠️ world_tick.py uses SUBCOMMANDS: the verb 'post' comes FIRST,
    #    before the positional <campaign> (cf. docs/monde-vivant/09 §3.4).
    #    DO NOT write [campagne, "post", …].
    r = lancer("world_tick.py",
               ["post", str(campagne), "--session", str(num), "--apply"])
    # Usage error (exit 2) or missing script (127) → do NOT raise: alert higher up.
    return {"lance": True, "exit": r["exit"], "stdout": r["stdout"],
            "stderr": r["stderr"], "raison": ""}


# ─── Session number ───────────────────────────────────────────────────────────

def derniere_session(campagne: Path) -> tuple[int | None, Path | None]:
    sessions_dir = campagne / "sessions"
    if not sessions_dir.is_dir():
        return None, None
    cands = []
    for sp in sessions_dir.glob("*.json"):
        m = re.match(r"0*(\d+)", sp.stem)
        if m:
            cands.append((int(m.group(1)), sp))
    if not cands:
        return None, None
    cands.sort()
    return cands[-1]


# ─── ~10-point pipeline check ─────────────────────────────────────────────────

def check_pipeline(campagne: Path, session_path: Path, monde: dict,
                   res_check: dict, res_clock: dict) -> list[dict]:
    """Return a list of points: {"id","label","ok","bloquant","detail"}."""
    points = []

    def add(pid, label, ok, bloquant, detail=""):
        points.append({"id": pid, "label": label, "ok": ok,
                       "bloquant": bloquant, "detail": detail})

    session = charger_json(session_path)

    # P1 & P2: delegated to check_session.py (exit code = source of truth).
    # We summarise its verdict for both points here to stay DRY.
    check_ok = res_check["exit"] == 0
    add("P1", "Session locations propagated into universe.regions",
        check_ok, True,
        "verified by check_session.py" if check_ok
        else "check_session.py reports a blocking discrepancy (see its report)")
    add("P2", "Encountered NPCs filed in npcs.json",
        check_ok, True,
        "verified by check_session.py" if check_ok
        else "check_session.py reports a blocking discrepancy (see its report)")

    # P3 & P4: factions / clock (direct read, independent).
    factions = monde.get("global_state", {}).get("factions", [])
    horloge = monde.get("global_state", {}).get("faction_actions_horloge", {})
    h_actions = horloge.get("actions", []) if isinstance(horloge, dict) else []
    factions_horloge = {_norm(a.get("faction", "")) for a in h_actions
                        if isinstance(a, dict)}

    sans_obj = [f.get("name", "?") for f in factions if isinstance(f, dict)
                and not (f.get("objectif_court_terme") and f.get("objectif_long_terme"))]
    add("P3", "Each faction has objectif CT + LT",
        not sans_obj, True,
        "" if not sans_obj else f"incomplete factions: {', '.join(sans_obj)}")

    sans_horloge = [f.get("name", "?") for f in factions if isinstance(f, dict)
                    and _norm(f.get("name", "")) not in factions_horloge]
    add("P4", "Each faction present in faction_actions_horloge",
        not sans_horloge, True,
        "" if not sans_horloge else f"missing: {', '.join(sans_horloge)}")

    # P5: clock up to date (clock.py). Elapsed unresolved deadline = ALERT,
    # non-blocking for the commit (it is a narrative decision for the GM) but
    # strongly flagged.
    clock_ok = res_clock["exit"] == 0
    add("P5", "Clock up to date (no elapsed unresolved deadline)",
        clock_ok, False,
        "" if clock_ok else "clock.py reports ≥ 1 ELAPSED deadline — "
        "consequence to play out / resolve by the GM")

    # P6: chronology not empty.
    chrono = monde.get("global_state", {}).get("chronologie", "")
    add("P6", "Chronology filled in (global_state.chronologie)",
        bool(str(chrono).strip()), True,
        "" if str(chrono).strip() else "chronologie empty")

    # P7-P9: session log complete.
    heure_fin = str(session.get("heure_fin", "")).strip()
    add("P7", "Session log: heure_fin filled in",
        bool(heure_fin), True,
        "" if heure_fin else "heure_fin empty (session not finalised)")
    resume = str(session.get("resume", "")).strip()
    add("P8", "Session log: resume filled in",
        bool(resume), True,
        "" if resume else "resume empty")
    add("P9", "Session log: etat_fin present",
        bool(session.get("etat_fin")), False,
        "" if session.get("etat_fin") else "etat_fin absent (recommended)")

    # P10: UT timeline.
    temps = monde.get("meta", {}).get("time", {})
    est_ut = "ut" in str(temps.get("regime", "")).lower() or temps.get("units_per_day")
    if est_ut:
        evt = campagne / "events.json"
        evt_ok = evt.exists()
        detail = ""
        if evt_ok:
            try:
                charger_json(evt)
            except (OSError, json.JSONDecodeError) as e:
                evt_ok = False
                detail = f"events.json illisible : {e}"
        else:
            detail = "events.json absent (required in UT regime)"
        add("P10", "UT timeline: events.json present and valid",
            evt_ok, True, detail)
    else:
        add("P10", "UT timeline: N/A (narrative regime)", True, False,
            "narrative regime — events.json not required")

    return points


def _norm(name: str) -> str:
    import unicodedata
    if not name:
        return ""
    s = unicodedata.normalize("NFKD", name)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"[^a-z0-9\s]", " ", s.lower())
    return re.sub(r"\s+", " ", s).strip()


# ─── Full pipeline ────────────────────────────────────────────────────────────

def executer(campagne: Path, num_session: int | None,
             titre: str | None, teaser: str | None) -> dict:
    num, session_path = (num_session, campagne / "sessions" / f"{num_session:03d}.json") \
        if num_session is not None else derniere_session(campagne)
    if session_path is None or not session_path.exists():
        raise FileNotFoundError(f"Session not found in {campagne}/sessions")
    num = num if num is not None else int(re.match(r"0*(\d+)", session_path.stem).group(1))

    monde = charger_json(campagne / "world.json")

    # 1. validate_json (BLOCKING) — short-circuits everything else if broken.
    res_json = lancer("validate_json.py", [str(campagne)])

    # 2. validate_schema (BLOCKING) — file structure vs JSON Schemas.
    res_schema = lancer("validate_schema.py", [str(campagne)])

    # 3. distances (WARN/BLOCKING)
    res_dist = lancer("validator-distances.py", [str(campagne / "world.json")])

    # 4. check_session (BLOCKING)
    cs_args = [str(campagne)]
    if num_session is not None:
        cs_args += ["--session", str(num_session)]
    res_check = lancer("check_session.py", cs_args)

    # 5. clock --dry-run (ALERT)
    res_clock = lancer("clock.py", [str(campagne)])

    # 6. world_tick post --apply (LIVING WORLD) — reconciliation. NON-BLOCKING:
    #    gated by the presence of actors.json (world_tick guards itself on
    #    features.temporalite). A failure here NEVER prevents closing (alert).
    res_tick = _tick_post_si_actif(campagne, num)

    # ~10-point pipeline check (skipped if JSON is broken: we read no further)
    points = []
    if res_json["exit"] == 0:
        points = check_pipeline(campagne, session_path, monde,
                                res_check, res_clock)

    # Verdict
    blocs = []
    if res_json["exit"] != 0:
        blocs.append("validate_json: broken JSON (closing impossible)")
    if res_schema["exit"] != 0:
        blocs.append("validate_schema: schema discrepancy (exit %d)" % res_schema["exit"])
    if res_dist["exit"] == 2:
        blocs.append("validator-distances: error (exit 2)")
    if res_check["exit"] not in (0,):
        blocs.append("check_session: blocking discrepancy (exit %d)" % res_check["exit"])
    for p in points:
        if p["bloquant"] and not p["ok"]:
            blocs.append(f"{p['id']} {p['label']} — {p['detail']}")

    alertes = []
    if res_dist["exit"] == 1:
        alertes.append("validator-distances: warnings (human review needed)")
    for p in points:
        if not p["bloquant"] and not p["ok"]:
            alertes.append(f"{p['id']} {p['label']} — {p['detail']}")
    # Living world: reconciliation is informational, never blocking.
    if res_tick.get("lance"):
        if res_tick["exit"] == 0:
            alertes.append("world_tick post: world reconciled (see detail).")
        elif res_tick["exit"] == 1:
            alertes.append("world_tick post: reconciliations applied "
                           "(disrupted plans renewed / propagations).")
        else:
            alertes.append("world_tick post: NON-blocking failure "
                           f"(exit {res_tick['exit']}) — reconciliation to rerun manually.")

    ok = len(blocs) == 0

    # Proposed commit message (never executed here)
    nom_camp = monde.get("meta", {}).get("name", campagne.name)
    titre_aff = titre or _titre_session(session_path)
    msg_commit = f"🎲 {nom_camp} — Session {num:03d} clôturée : {titre_aff}"

    return {
        "campagne": str(campagne),
        "session_num": num,
        "session_fichier": str(session_path),
        "ok": ok,
        "etapes": {
            "validate_json": res_json["exit"],
            "validate_schema": res_schema["exit"],
            "validator_distances": res_dist["exit"],
            "check_session": res_check["exit"],
            "clock": res_clock["exit"],
            "world_tick_post": res_tick.get("exit") if res_tick.get("lance") else None,
        },
        "points": points,
        "bloquants": blocs,
        "alertes": alertes,
        "message_commit_propose": msg_commit,
        "titre": titre_aff,
        "teaser": teaser,
        "_sous_rapports": {
            "validate_json": res_json,
            "validate_schema": res_schema,
            "validator_distances": res_dist,
            "check_session": res_check,
            "clock": res_clock,
            "world_tick_post": res_tick,
        },
    }


def _titre_session(session_path: Path) -> str:
    try:
        s = charger_json(session_path)
        return s.get("titre_episode") or s.get("titre") or "(title to define)"
    except (OSError, json.JSONDecodeError):
        return "(title to define)"


# ─── CLI ──────────────────────────────────────────────────────────────────────

def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="close_session.py",
        description="Session closing pipeline — deterministic guards + 10-point check.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python3 close_session.py .hermes/mj-tonnerre/campaigns/la-naissance-dun-roi\n"
            "  python3 close_session.py <campagne> --session 5 --titre 'Le Cœur' --json\n"
            "\n"
            "WARNING --commit: this script does NOT commit automatically.\n"
            "It PROPOSES a message. The decision to commit belongs to the GM /\n"
            "the Steward. --commit is only honoured if the pipeline is green AND\n"
            "is NOT run on real campaigns from this tooling.\n"
        ),
    )
    parser.add_argument("campagne", help="Path to the campaign folder.")
    parser.add_argument("--session", type=int, default=None,
                        help="Session number (default: the last one).")
    parser.add_argument("--titre", default=None, help="Episode title (commit).")
    parser.add_argument("--teaser", default=None, help="Teaser (passed as-is to the report).")
    parser.add_argument("--json", action="store_true", dest="as_json",
                        help="Output in JSON format.")
    parser.add_argument("--commit", action="store_true",
                        help="(documented, disabled) commits if green — see WARNING.")
    args = parser.parse_args(argv)

    campagne = Path(args.campagne)
    if not campagne.is_dir() or not (campagne / "world.json").exists():
        print(f"❌ Campaign or world.json not found: {campagne}", file=sys.stderr)
        return 2

    try:
        rapport = executer(campagne, args.session, args.titre, args.teaser)
    except FileNotFoundError as e:
        print(f"❌ {e}", file=sys.stderr)
        return 2
    except (json.JSONDecodeError, KeyError) as e:
        print(f"❌ Unreadable data: {e}", file=sys.stderr)
        return 2

    if args.as_json:
        out = {k: v for k, v in rapport.items() if k != "_sous_rapports"}
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return 0 if rapport["ok"] else 1

    print(f"🧮 Closing — {Path(rapport['campagne']).name} "
          f"— session {rapport['session_num']:03d}")
    print("─" * 60)
    et = rapport["etapes"]
    print(f"  validate_json        : exit {et['validate_json']}")
    print(f"  validator-distances  : exit {et['validator_distances']}")
    print(f"  check_session        : exit {et['check_session']}")
    print(f"  clock (dry-run)      : exit {et['clock']}")
    if et.get("world_tick_post") is not None:
        print(f"  world_tick post      : exit {et['world_tick_post']} (living world)")
    print("─" * 60)
    for p in rapport["points"]:
        mark = "✅" if p["ok"] else ("❌" if p["bloquant"] else "⚠️")
        ligne = f"  {mark} {p['id']} {p['label']}"
        if p["detail"] and not p["ok"]:
            ligne += f" — {p['detail']}"
        print(ligne)
    print("─" * 60)

    if rapport["bloquants"]:
        print("❌ CLOSING REFUSED — blocking steps:")
        for b in rapport["bloquants"]:
            print(f"   • {b}")
        if rapport["alertes"]:
            print("⚠️  Alerts (non-blocking):")
            for a in rapport["alertes"]:
                print(f"   • {a}")
        print("\nFix the blocking points then rerun.")
        return 1

    if rapport["alertes"]:
        print("⚠️  Alerts (non-blocking — to be handled by the GM):")
        for a in rapport["alertes"]:
            print(f"   • {a}")
        print()

    print("✅ Pipeline green — closing possible.")
    print(f"\nProposed commit message:\n   {rapport['message_commit_propose']}")
    print("\nThe commit is NOT performed by this script. The GM / Steward decides:")
    print(f"   cd {campagne} && git add -A && "
          f"git commit -m \"{rapport['message_commit_propose']}\"")

    if args.commit:
        print("\nℹ --commit requested but intentionally NOT executed by this "
              "tooling (see WARNING in --help). Run the command above manually "
              "or let the Steward do it.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
