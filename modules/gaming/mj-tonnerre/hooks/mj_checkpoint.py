#!/usr/bin/env python3
"""
mj_checkpoint.py — in-turn GATE (called by the GM before delivering narration).

The GM pipes their draft; the LLM judge checks it (Steward lenient + conduct strict).
- OK            → « ✅ CHECKPOINT OK » (exit 0) → the GM delivers.
- INFRACTION    → explicit feedback + « rewrite then retry » (exit 1) → the GM corrects.
- BUDGET EXHAUSTED → after N attempts, « ⚠️ FORCED » (exit 0) + log → NEVER loops.

The response is TEXT (the GM reads it in terminal output), not JSON.

Usage (from the campaign cwd) :
  echo "<narration draft>" | python3 .../mj_checkpoint.py [--declared "player action"]
  python3 .../mj_checkpoint.py --file brouillon.txt --declared "Rubis mange un saucisson"
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _lib as L  # noqa: E402
import llm_judge as J  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--declared", default=os.environ.get("MJ_DECLARED", ""))
    ap.add_argument("--file", default=None)
    ap.add_argument("--draft", default=None)
    args = ap.parse_args()

    if args.draft is not None:
        draft = args.draft
    elif args.file:
        try:
            draft = open(args.file, encoding="utf-8").read()
        except Exception:
            print("⚠️ CHECKPOINT : brouillon illisible — livre ta narration."); return 0
    else:
        draft = sys.stdin.read()

    camp = L.campaign_dir({"cwd": os.getcwd()})
    monde = L.load_monde(camp)
    jcfg = L.judge_config(monde)
    payload = {"cwd": os.getcwd(), "session_id": "gate"}

    if not jcfg["actif"]:
        print("✅ CHECKPOINT (juge inactif) — livre ta narration."); return 0

    verdict = J.judge(draft, args.declared, L.etat_brief(camp, monde, for_judge=True), jcfg)
    if "_skipped" in verdict:
        print("✅ CHECKPOINT (juge indisponible : %s) — livre ta narration." % verdict["_skipped"]); return 0

    violations = verdict.get("violations", [])
    if not violations:
        L.attempts_reset(camp, payload)
        L.scoreboard_update(camp, jcfg["modele"], True, 0, 0, [])
        print("✅ CHECKPOINT OK — aucune règle enfreinte. Livre ta narration."); return 0

    n = L.attempts_inc(camp, payload)
    fb = J.format_feedback(violations)
    by_rule = [v.get("regle", "?") for v in violations]
    bq = sum(1 for v in violations if v.get("domaine") == "banquier")
    cd = sum(1 for v in violations if v.get("domaine") == "conduite")

    if n >= jcfg["gate_max_tentatives"]:
        # Budget exhausted: force through to avoid looping, log and keep the feedback.
        L.attempts_reset(camp, payload)
        L.scoreboard_update(camp, jcfg["modele"], False, bq, cd, by_rule, forced=1)
        L.set_pending(camp, payload, fb)
        print("⚠️ CHECKPOINT FORCÉ après %d tentatives — corrige au mieux et LIVRE "
              "(infractions restantes loguées) :\n%s" % (n, fb))
        return 0

    L.scoreboard_update(camp, jcfg["modele"], False, bq, cd, by_rule)
    print("%s\n\n➡️ Réécris ta narration puis relance le checkpoint (tentative %d/%d)."
          % (fb, n, jcfg["gate_max_tentatives"]))
    return 1


if __name__ == "__main__":
    sys.exit(main())
