#!/usr/bin/env python3
"""
scoreboard.py — Metrics reader per model (.banquier/scoreboard.json).

Measures what you ask for: how many "clean" turns (the judge passes, the Steward
does not intervene) vs how many Steward interventions / conduct violations,
PER model → helps with model selection.

Usage:
  python3 scoreboard.py [path/campaign]     # default: cwd
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _lib as L  # noqa: E402


def main():
    camp = L.campaign_dir({"cwd": sys.argv[1] if len(sys.argv) > 1 else os.getcwd()})
    lg = L.lang(L.load_monde(camp))                 # active UI language (fail-open → 'en')
    sb = L.load_scoreboard(camp)
    if not sb:
        print(L.t("scoreboard.none", lg)); return 0

    print(L.t("scoreboard.title", lg, name=camp.name) + "\n")
    hdr = "%-32s %6s %7s %7s %9s %9s %6s" % (
        L.t("scoreboard.col_model", lg), L.t("scoreboard.col_turns", lg),
        L.t("scoreboard.col_clean", lg), L.t("scoreboard.col_pct_clean", lg),
        L.t("scoreboard.col_banker", lg), L.t("scoreboard.col_conduct", lg),
        L.t("scoreboard.col_forced", lg))
    print(hdr); print("-" * len(hdr))
    for model, m in sorted(sb.items(), key=lambda kv: -int(kv[1].get("tours", 0))):
        tours = int(m.get("tours", 0)) or 1
        propres = int(m.get("propres", 0))
        pct = 100.0 * propres / tours
        print("%-32s %6d %7d %6.1f%% %9d %9d %6d" % (
            L.truncate(model, 32), int(m.get("tours", 0)), propres, pct,
            int(m.get("interventions_banquier", 0)), int(m.get("infractions_conduite", 0)),
            int(m.get("forces", 0))))
        par_regle = m.get("par_regle") or {}
        if par_regle:
            top = sorted(par_regle.items(), key=lambda kv: -kv[1])[:5]
            print(L.t("scoreboard.top_rules", lg) + ", ".join("%s×%d" % (k, v) for k, v in top))
    return 0


if __name__ == "__main__":
    sys.exit(main())
