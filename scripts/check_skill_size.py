#!/usr/bin/env python3
"""check_skill_size.py — fail before a SKILL.md reaches the character limit.

A skill file at the limit is frozen against writes. In production the main skill
reached 104 162 characters and refused 76 writes (docs/10-field-report.md §3.3).
Warn tier at 80 %, fail tier at 90 %, so a split is still cheap when we ask.

Usage:
    python3 scripts/check_skill_size.py             # scan, exit 1 above the fail tier
    python3 scripts/check_skill_size.py --verbose   # list every skill and its usage
    python3 scripts/check_skill_size.py --root DIR  # scan another tree (fixtures)
    python3 scripts/check_skill_size.py --limit N   # override the character limit

Escape hatch: MGM_SKILL_SIZE_SKIP=1 downgrades every failure to a warning.

Exit codes: 0 = clean or warnings only, 1 = over the fail tier, 2 = usage error.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Platform limit for one skill file, in characters — 104 162 is where the
# production skill stopped accepting writes. Not ours to raise.
LIMIT = 100_000
WARN_RATIO = 0.80
FAIL_RATIO = 0.90

SKILLS_DIR = "modules"
ENV_SKIP = "MGM_SKILL_SIZE_SKIP"

OK, WARN, FAIL = "ok", "warn", "fail"

REMEDE = (
    "How to fix, in order of preference:\n"
    "  1. Move detail out of the skill into its references/ directory and link "
    "the file — a skill routes to knowledge, it does not carry all of it.\n"
    "  2. Split the skill into a second, narrower skill with its own trigger.\n"
    "  3. Delete what the corpus shows is never used.\n"
    "Raising the limit is not an option: it is imposed by the platform, and a "
    "skill that reaches it is frozen against writes."
)


def skill_files(root: Path) -> list[Path]:
    return sorted((root / SKILLS_DIR).rglob("SKILL.md"))


def measure(chemin: Path) -> int:
    """Character count — the unit the platform limit uses, not bytes."""
    return len(chemin.read_text(encoding="utf-8"))


def classify(count: int, limit: int) -> tuple[str, float]:
    ratio = count / limit if limit else 0.0
    if ratio >= FAIL_RATIO:
        return FAIL, ratio
    if ratio >= WARN_RATIO:
        return WARN, ratio
    return OK, ratio


def scan(root: Path = ROOT, limit: int = LIMIT) -> list[tuple[str, int, float, str]]:
    """Measure every skill: (relative path, characters, usage ratio, status)."""
    resultats: list[tuple[str, int, float, str]] = []
    for chemin in skill_files(root):
        try:
            count = measure(chemin)
        except (OSError, UnicodeDecodeError):
            continue
        statut, ratio = classify(count, limit)
        resultats.append((str(chemin.relative_to(root)), count, ratio, statut))
    return resultats


def ligne(nom: str, count: int, ratio: float, statut: str) -> str:
    marque = {OK: "  ", WARN: "⚠️ ", FAIL: "❌"}[statut]
    return f"  {marque} {ratio * 100:5.1f}%  {count:7d} chars  {nom}"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--verbose", action="store_true",
                    help="also print skills that are comfortably within budget")
    ap.add_argument("--root", type=Path, default=ROOT,
                    help="repository root to scan (default: this repo)")
    ap.add_argument("--limit", type=int, default=LIMIT,
                    help=f"character limit per skill file (default: {LIMIT})")
    args = ap.parse_args(argv)

    if args.limit <= 0:
        print("❌ --limit must be a positive number of characters.", file=sys.stderr)
        return 2

    resultats = scan(args.root, args.limit)
    if not resultats:
        print(f"⚠️  No SKILL.md found under {args.root / SKILLS_DIR} — nothing checked.")
        return 0

    echecs = [r for r in resultats if r[3] == FAIL]
    alertes = [r for r in resultats if r[3] == WARN]

    if args.verbose:
        print(f"Skill budget: {args.limit} chars "
              f"(warn ≥ {WARN_RATIO * 100:.0f}%, fail ≥ {FAIL_RATIO * 100:.0f}%)\n")
        for entree in sorted(resultats, key=lambda r: -r[1]):
            print(ligne(*entree))
        print("")

    if alertes:
        print(f"⚠️  {len(alertes)} skill(s) above {WARN_RATIO * 100:.0f}% of the "
              f"{args.limit}-character limit — plan the split now, not later:")
        for entree in sorted(alertes, key=lambda r: -r[1]):
            print(ligne(*entree))
        print("")

    if not echecs:
        plus_gros = max(resultats, key=lambda r: r[1])
        print(f"✅ {len(resultats)} skill file(s) within budget "
              f"(largest: {plus_gros[0]} at {plus_gros[2] * 100:.1f}%).")
        return 0

    print(f"❌ {len(echecs)} skill(s) at or above {FAIL_RATIO * 100:.0f}% of the "
          f"{args.limit}-character limit:")
    for entree in sorted(echecs, key=lambda r: -r[1]):
        print(ligne(*entree))
    print("")
    print(REMEDE)

    if os.environ.get(ENV_SKIP) == "1":
        print(f"\n⚠️  {ENV_SKIP}=1 — failure waived, exiting 0. "
              "That skill is still on its way to being frozen.")
        return 0
    print(f"\n(To unblock a live campaign: {ENV_SKIP}=1 — and open an issue.)")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
