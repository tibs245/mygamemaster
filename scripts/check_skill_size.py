#!/usr/bin/env python3
"""check_skill_size.py — fail before a SKILL.md reaches the character limit.

A skill file at the limit is frozen against writes. In production the main skill
reached 104 162 characters and refused 76 writes (docs/10-field-report.md §3.3).
Warn tier at 80 %, fail tier at 90 %, so a split is still cheap when we ask.

Unit: we cannot prove whether the platform counts characters or UTF-8 bytes, and
the shipped skills differ by up to 9 % between the two. The guard classifies on
whichever is larger, so it is never looser than the limit it enforces.

A SKILL.md that cannot be read (bad permissions, not valid UTF-8) is a failure,
not a skip — an unmeasured skill is what this guard exists to make impossible.

Usage:
    python3 scripts/check_skill_size.py             # scan, exit 1 above the fail tier
    python3 scripts/check_skill_size.py --verbose   # list every skill and its usage
    python3 scripts/check_skill_size.py --root DIR  # scan another tree (fixtures)
    python3 scripts/check_skill_size.py --limit N   # override the limit

Escape hatch: MGM_SKILL_SIZE_SKIP=1 downgrades a budget failure to a warning.
It does not waive an unmeasurable file — re-encode it instead, that is a
one-command fix.

Exit codes: 0 = clean or warnings only, 1 = over the fail tier or unmeasurable,
2 = usage error.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Platform limit for one skill file — 104 162 is where the production skill
# stopped accepting writes. Not ours to raise.
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


def measure(chemin: Path) -> tuple[int, int]:
    """(characters, UTF-8 bytes). Raises if the file cannot be read as UTF-8."""
    octets = chemin.read_bytes()
    return len(octets.decode("utf-8")), len(octets)


def taille(entree: tuple[str, int, int, float, str]) -> int:
    """Worst-case size of a result: whichever of chars and bytes is larger."""
    return max(entree[1], entree[2])


def classify(count: int, limit: int) -> tuple[str, float]:
    ratio = count / limit if limit else 0.0
    if ratio >= FAIL_RATIO:
        return FAIL, ratio
    if ratio >= WARN_RATIO:
        return WARN, ratio
    return OK, ratio


def scan(
    root: Path = ROOT, limit: int = LIMIT
) -> tuple[list[tuple[str, int, int, float, str]], list[tuple[str, str]]]:
    """Measure every skill.

    Returns (resultats, illisibles):
      * resultats  — (relative path, characters, bytes, usage ratio, status)
      * illisibles — (relative path, reason) for every file we could not measure.
        These are never dropped silently: a skill the guard cannot read is a
        skill the guard cannot certify.
    """
    resultats: list[tuple[str, int, int, float, str]] = []
    illisibles: list[tuple[str, str]] = []
    for chemin in skill_files(root):
        nom = str(chemin.relative_to(root))
        try:
            chars, octets = measure(chemin)
        except (OSError, UnicodeDecodeError) as exc:
            illisibles.append((nom, f"{type(exc).__name__}: {exc}"))
            continue
        statut, ratio = classify(max(chars, octets), limit)
        resultats.append((nom, chars, octets, ratio, statut))
    return resultats, illisibles


def ligne(nom: str, chars: int, octets: int, ratio: float, statut: str) -> str:
    marque = {OK: "  ", WARN: "⚠️ ", FAIL: "❌"}[statut]
    return (f"  {marque} {ratio * 100:5.1f}%  {chars:7d} chars / "
            f"{octets:7d} bytes  {nom}")


def _bloc_illisibles(illisibles: list[tuple[str, str]]) -> None:
    print(f"❌ {len(illisibles)} skill file(s) could not be measured — the guard "
          "cannot certify a file it cannot read, so this blocks:")
    for nom, raison in illisibles:
        print(f"     {nom}")
        print(f"       {raison}")
    print("   Re-save the file as UTF-8 (iconv -f latin1 -t utf-8 …) or fix its "
          "permissions, then run the guard again.")
    print("")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--verbose", action="store_true",
                    help="also print skills that are comfortably within budget")
    ap.add_argument("--root", type=Path, default=ROOT,
                    help="repository root to scan (default: this repo)")
    ap.add_argument("--limit", type=int, default=LIMIT,
                    help=f"limit per skill file, chars or bytes (default: {LIMIT})")
    args = ap.parse_args(argv)

    if args.limit <= 0:
        print("❌ --limit must be a positive number.", file=sys.stderr)
        return 2

    resultats, illisibles = scan(args.root, args.limit)
    if not resultats and not illisibles:
        print(f"⚠️  No SKILL.md found under {args.root / SKILLS_DIR} — nothing checked.")
        return 0

    echecs = [r for r in resultats if r[4] == FAIL]
    alertes = [r for r in resultats if r[4] == WARN]
    waived = os.environ.get(ENV_SKIP) == "1"

    if args.verbose:
        print(f"Skill budget: {args.limit} (warn ≥ {WARN_RATIO * 100:.0f}%, "
              f"fail ≥ {FAIL_RATIO * 100:.0f}%; classified on max(chars, bytes))\n")
        for entree in sorted(resultats, key=lambda r: -taille(r)):
            print(ligne(*entree))
        print("")

    if alertes:
        print(f"⚠️  {len(alertes)} skill(s) above {WARN_RATIO * 100:.0f}% of the "
              f"{args.limit} limit — plan the split now, not later:")
        for entree in sorted(alertes, key=lambda r: -taille(r)):
            print(ligne(*entree))
        print("")

    if not echecs and not illisibles:
        plus_gros = max(resultats, key=taille)
        print(f"✅ {len(resultats)} skill file(s) within budget "
              f"(largest: {plus_gros[0]} at {plus_gros[3] * 100:.1f}%).")
        return 0

    if illisibles:
        _bloc_illisibles(illisibles)

    if echecs:
        print(f"❌ {len(echecs)} skill(s) at or above {FAIL_RATIO * 100:.0f}% of the "
              f"{args.limit} limit:")
        for entree in sorted(echecs, key=lambda r: -taille(r)):
            print(ligne(*entree))
        print("")
        print(REMEDE)

    if illisibles:
        return 1

    if waived:
        print(f"\n⚠️  {ENV_SKIP}=1 — failure waived, exiting 0. "
              "That skill is still on its way to being frozen.")
        return 0
    print(f"\n(To unblock a live campaign: {ENV_SKIP}=1 — and open an issue.)")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
