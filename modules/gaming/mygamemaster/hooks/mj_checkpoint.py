#!/usr/bin/env python3
"""
mj_checkpoint.py — in-turn GATE (called by the GM before delivering narration).

Two layers, in this order:

  1. DETERMINISTIC AGENCY GATE (`agency_gate.py`) — local, stdlib, no model. Owns the TIER 0
     rules AGENCY-01/02/03. Its verdict does NOT depend on the LLM judge being configured,
     reachable or in budget: an unavailable judge can no longer let an agency violation through,
     which was the single most expensive defect of the 34-session corpus.
  2. LLM JUDGE (`llm_judge.py`) — everything else (steward consistency + the other conduct
     rules). Fail-open by design, and that is acceptable ONLY because layer 1 already ran.

Exit contract (the response is TEXT, the GM reads it in the terminal):
  - OK                → « ✅ CHECKPOINT OK » (exit 0) → the GM delivers.
  - INFRACTION        → explicit feedback + « rewrite then retry » (exit 1) → the GM corrects.
  - UNREADABLE DRAFT  → refusal (exit 1): a draft that cannot be read cannot be cleared.
  - BUDGET EXHAUSTED  → LOUD forced pass (exit 0), logged to the scoreboard and re-injected on
    the next turn, so the anti-loop property never becomes a silent amnesty.

Operator escape hatches (a live campaign must always be unblockable):
  MGM_AGENCY_GATE=off        disables layer 1 entirely (default: ON).
  MGM_AGENCY_MAX_ATTEMPTS=N  rewrite budget of layer 1 before the forced pass (default 3).

Usage (from the campaign cwd) :
  echo "<narration draft>" | python3 .../mj_checkpoint.py [--declared "player action"]
  python3 .../mj_checkpoint.py --file brouillon.txt --declared "Rubis mange un saucisson"
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _lib as L  # noqa: E402
import agency_gate as A  # noqa: E402
import llm_judge as J  # noqa: E402

AGENCY_ATTEMPTS_KEY = "agency_attempts"


def _agency_attempts(camp, payload, inc=False):
    n = L.snap_get(camp, payload, AGENCY_ATTEMPTS_KEY)
    n = int(n) if isinstance(n, int) else 0
    if inc:
        n += 1
        L.snap_set(camp, payload, AGENCY_ATTEMPTS_KEY, n)
    return n


def _pc_names(camp):
    """PC proper names, so the gate also catches third-person narration ("Rubis s'agenouille")."""
    out = []
    for _, fiche in L.iter_characters(camp):
        nom = (fiche.get("meta") or {}).get("character_name")
        if nom:
            out.append(str(nom))
    return out


def _trace(msg):
    sys.stderr.write("[mj-agency] %s\n" % msg)


def run_agency_gate(draft, declared, camp, payload, modele):
    """Layer 1. Returns (exit code or None to continue to the LLM judge, report or None)."""
    if not A.enabled():
        _trace("gate disabled by %s — deterministic AGENCY check SKIPPED" % A.ENV_SWITCH)
        print("⚠️ AGENCY GATE DISABLED (%s=off) — AGENCY-01/02/03 are unguarded this turn."
              % A.ENV_SWITCH)
        return None, None

    try:
        report = A.analyze(draft, declared, _pc_names(camp))
    except Exception as exc:
        # A gate that cannot run does not get to approve: refuse, and name the escape hatch.
        _trace("internal error: %r" % exc)
        print("🚫 CHECKPOINT REFUSED — the agency gate crashed (%r). Fix it, or unblock the "
              "campaign with %s=off (the turn is then unguarded)." % (exc, A.ENV_SWITCH))
        return 1, None

    if report["ok"]:
        L.snap_set(camp, payload, AGENCY_ATTEMPTS_KEY, 0)
        return None, report

    rules = [v["regle"] for v in report["violations"]]
    n = _agency_attempts(camp, payload, inc=True)
    budget = A.max_attempts()
    fb = J.format_feedback(report["violations"], prefix="🚫 AGENCY GATE (deterministic) — TURN REFUSED")

    if n >= budget:
        # Anti-loop: the gate must never trap the GM in an infinite rewrite. A forced pass is
        # LOUD (stdout + stderr), counted, and re-injected on the next turn — never silent.
        L.snap_set(camp, payload, AGENCY_ATTEMPTS_KEY, 0)
        L.scoreboard_update(camp, modele, False, 0, len(rules), rules, forced=1)
        L.set_pending(camp, payload, fb)
        _trace("FORCED after %d attempts — unresolved %s" % (n, ",".join(rules)))
        print("🚨 AGENCY GATE FORCED after %d attempts — %s STILL VIOLATED. Deliver only if you "
              "have no better option; the violation is logged and re-injected next turn:\n%s"
              % (n, ", ".join(sorted(set(rules))), fb))
        return 0, report

    L.scoreboard_update(camp, modele, False, 0, len(rules), rules)
    _trace("refused (attempt %d/%d): %s" % (n, budget, ",".join(rules)))
    print("%s\n\n➡️ Rewrite: describe only what the PC perceives, then re-run the checkpoint "
          "(attempt %d/%d)." % (fb, n, budget))
    return 1, report


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--declared", default=os.environ.get("MGM_DECLARED", ""))
    ap.add_argument("--file", default=None)
    ap.add_argument("--draft", default=None)
    args = ap.parse_args()

    if args.draft is not None:
        draft = args.draft
    elif args.file:
        try:
            draft = open(args.file, encoding="utf-8").read()
        except Exception:
            print("🚫 CHECKPOINT REFUSED — draft unreadable (%s). The gate cannot clear a draft it "
                  "cannot read: pipe it on stdin or fix the path, then re-run." % args.file)
            return 1
    else:
        draft = sys.stdin.read()

    camp = L.campaign_dir({"cwd": os.getcwd()})
    monde = L.load_monde(camp)
    jcfg = L.judge_config(monde)
    payload = {"cwd": os.getcwd(), "session_id": "gate"}

    code, report = run_agency_gate(draft, args.declared, camp, payload, jcfg["modele"])
    if code is not None:
        return code

    if not jcfg["actif"]:
        print("✅ CHECKPOINT (agency gate passed, judge inactive)%s — deliver your narration."
              % _cite(args.declared, report))
        return 0

    verdict = J.judge(draft, args.declared, L.etat_brief(camp, monde, for_judge=True), jcfg)
    if "_skipped" in verdict:
        print("✅ CHECKPOINT (agency gate passed, judge unavailable: %s) — deliver your narration."
              % verdict["_skipped"])
        return 0

    violations = verdict.get("violations", [])
    if not violations:
        L.attempts_reset(camp, payload)
        L.scoreboard_update(camp, jcfg["modele"], True, 0, 0, [])
        print("✅ CHECKPOINT OK — no rule violated%s. Deliver your narration."
              % _cite(args.declared, report))
        return 0

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
        print("⚠️ CHECKPOINT FORCED after %d attempts — correct as best you can and DELIVER "
              "(remaining violations logged):\n%s" % (n, fb))
        return 0

    L.scoreboard_update(camp, jcfg["modele"], False, bq, cd, by_rule)
    print("%s\n\n➡️ Rewrite your narration then re-run the checkpoint (attempt %d/%d)."
          % (fb, n, jcfg["gate_max_tentatives"]))
    return 1


def _cite(declared, report):
    """AGENCY-03 requires the declaration to be cited when a PC action is let through."""
    allowed = (report or {}).get("allowed") or []
    if not declared or not allowed:
        return ""
    return " — %d PC action(s) admitted as execution of the declaration « %s » (%s)" % (
        len(allowed), L.truncate(declared, 120), allowed[0]["regle"])


if __name__ == "__main__":
    sys.exit(main())
