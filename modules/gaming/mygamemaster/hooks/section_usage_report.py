#!/usr/bin/env python3
"""
section_usage_report.py — Reads .banquier/section-usage.json (one or more
campaigns) and prints "section -> turns solicited -> observed trigger".

This is the read side of the instrumentation in hooks/pre_llm_call.py
(_section_triggers / _lib.section_usage_record). It resolves the DECLENCHEUR
classifications MESURE-SKILL.md §3 could argue only from section content, not
from usage — see docs/.../INSTRUMENTATION.md for what a fired trigger proves
and does not prove.

Usage:
  python3 section_usage_report.py [path/campaign ...]   # default: cwd
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _lib as L  # noqa: E402

# trigger_key -> [(section id, section name) from MESURE-SKILL.md §2 table]
SECTION_MAP = {
    "cmd_cloture": [("#5", "Formatting Conventions"), ("#13", "Systematic notes (§3)")],
    "cmd_game_report": [("#5", "Formatting Conventions")],
    "cmd_reprendre": [("#6", "Discord Conventions")],
    "memory_card_active": [("#17", "Data governance MEMORY vs FILES (§4)")],
    "npc_multi_named": [("#19", "Relational persistence NPC<->NPC")],
    "pause_marker": [("#20", "Embellishment vs data integrity"),
                      ("#21", "Pitfall - regression in correction"),
                      ("#28", "Protocol - erasure post-correction"),
                      ("#29", "Protocol - correction factuelle")],
    "question_mark": [("#26", "Never confirm player deductions (§5)")],
    "npc_any_named": [("#37", "The GM keeps secrets (§9)")],
    "regime_non_narratif": [("#39", "General time management")],
}
# Sections MESURE-SKILL.md §3 flagged as unmeasured, with no cheap pre-call
# signal available from pre_llm_call — reported separately, never inferred.
UNMEASURED = [("#18", "Immediate persistence",
               "no observable signal before generation; would require "
               "instrumenting transform_llm_output.py (out of scope here)")]

MIN_TURNS_FOR_SIGNAL = 20  # below this, a 0-count is noise, not evidence


def _merge(paths):
    total_turns = 0
    counts = {}
    for p in paths:
        camp = L.campaign_dir({"cwd": p})
        data = L.section_usage(camp)
        total_turns += int(data.get("turns", 0))
        for k, v in (data.get("counts") or {}).items():
            counts[k] = counts.get(k, 0) + int(v)
    return total_turns, counts


def _verdict(turns_total, fired):
    if turns_total < MIN_TURNS_FOR_SIGNAL:
        return "insufficient data (<%d turns)" % MIN_TURNS_FOR_SIGNAL
    if fired == 0:
        return "candidate: CUT (never fired)"
    pct = 100.0 * fired / turns_total
    if pct >= 50:
        return "candidate: fold into NOYAU (fires most turns)"
    return "confirms DECLENCHEUR (trigger identified)"


def main():
    paths = sys.argv[1:] or [os.getcwd()]
    turns_total, counts = _merge(paths)
    print("Campaigns   : %s" % ", ".join(paths))
    print("Turns seen  : %d\n" % turns_total)
    hdr = "%-10s %-38s %-22s %6s %7s  %s" % (
        "Section", "Name", "Trigger", "Fired", "Pct", "Verdict")
    print(hdr)
    print("-" * len(hdr))
    rows = []
    for trig, sections in SECTION_MAP.items():
        fired = counts.get(trig, 0)
        pct = (100.0 * fired / turns_total) if turns_total else 0.0
        for sid, name in sections:
            rows.append((sid, name, trig, fired, pct))
    for sid, name, trig, fired, pct in sorted(rows, key=lambda r: r[0]):
        print("%-10s %-38s %-22s %6d %6.1f%%  %s" % (
            sid, name[:38], trig, fired, pct, _verdict(turns_total, fired)))
    for sid, name, why in UNMEASURED:
        print("%-10s %-38s %-22s %6s %7s  UNMEASURED: %s" % (
            sid, name[:38], "-", "-", "-", why))
    return 0


if __name__ == "__main__":
    sys.exit(main())
