#!/usr/bin/env python3
"""check_references.py — find references to files that do not exist.

Renaming a file is easy; the cost is always the references left behind. This
walks every tracked text file, extracts anything that looks like a path to a
repo file, and reports the ones that resolve to nothing.

It is deliberately conservative: a reference is only reported when it looks
unambiguously like a repo path (it carries a known extension, or a directory
prefix we own) AND no file matches it. Prose that merely contains a slash is
ignored, so the signal stays usable as a pre-commit gate.

Usage:
    python3 scripts/check_references.py            # scan, exit 1 if broken
    python3 scripts/check_references.py --verbose  # also list what was checked

Exit codes: 0 = clean, 1 = broken references found, 2 = usage error.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Extensions we treat as "this is a file reference, it must resolve".
SUIVIES = (".md", ".py", ".sh", ".json", ".yml", ".yaml", ".j2", ".csv", ".txt")

# Files we read looking for references.
LISIBLES = (".md", ".py", ".sh", ".yml", ".yaml", ".j2", ".json", ".toml", ".cfg")

# Directories that are documentation-addressable roots of this repo.
RACINES = ("docs/", "modules/", "scripts/", "specs/", "ansible/", "harness/", "data/")

# Markdown links: [label](target)
RE_MD = re.compile(r"\[[^\]]*\]\(([^)\s#]+)")
# Backticked or bare paths carrying a tracked extension.
RE_PATH = re.compile(
    r"[`'\"( ]([A-Za-z0-9_./-]+(?:" + "|".join(re.escape(e) for e in SUIVIES) + r"))")
# Backticked bare filename, no directory: `travel.md`
RE_NU = re.compile(r"`([A-Za-z0-9_-]+\.md)`")

# References that are legitimately not repo files.
IGNORE = re.compile(
    r"^(https?:|mailto:|#|\$|\{|<|\.\.\.|/opt/|/home/|/etc/|/usr/|/var/|/tmp/)"
    r"|^[A-Z_]+\.(md|json)$"          # placeholders like SKILL.md in prose
    r"|\*"                             # globs
    r"|NNN|XXX|NN\.|<[a-z]"            # placeholders: sessions/NNN.json
    r"|/all/vault\.yml$"               # secrets, intentionally absent
    r"|inventory/games\.yml$"          # the real game table, git-ignored by design
)

# Files that live in a CAMPAIGN directory, never in this repo. Docs name them
# constantly; they are not repo references and must not be judged as such.
ARTEFACTS_CAMPAGNE = {
    "MJ-INTENTION-LOG.md", "GM-INTENTION-LOG.md", "analyse-bug-rapport.md",
    "checklist-steward.md",
}


def fichiers_suivis() -> list[str]:
    out = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True,
                         text=True, check=True).stdout
    return [f for f in out.splitlines() if f]


def resout(ref: str, depuis: Path, connus: set[str], strict: bool = False) -> bool:
    """True if `ref` resolves to a tracked file, from the file that cites it.

    `strict` disables the basename fallback. Markdown links must resolve exactly:
    a relative link to `old/name.md` is broken even when `new/name.md` exists,
    and the fallback would otherwise hide precisely the renames this catches.
    """
    ref = ref.strip().rstrip(".,;:")
    if ref in connus:
        return True
    # present on disk but intentionally untracked (local config, generated data)
    if (ROOT / ref).exists():
        return True
    # relative to the citing file's directory
    rel = (depuis.parent / ref).resolve()
    try:
        if str(rel.relative_to(ROOT)) in connus:
            return True
    except ValueError:
        pass
    if strict:
        return False
    # basename match: docs often cite `close_session.py` without its directory
    base = ref.split("/")[-1]
    return any(k.endswith("/" + base) or k == base for k in connus)


def scanner(verbeux: bool = False) -> list[tuple[str, int, str]]:
    connus = set(fichiers_suivis())
    casses: list[tuple[str, int, str]] = []
    for nom in sorted(connus):
        if not nom.endswith(LISIBLES):
            continue
        chemin = ROOT / nom
        try:
            lignes = chemin.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeDecodeError):
            continue
        for num, ligne in enumerate(lignes, 1):
            # Quoted paths are judged only from a repo root: docs legitimately
            # cite campaign-relative paths (sessions/009.json) that live elsewhere.
            liens = {(r, True) for r in RE_MD.findall(ligne)}
            cites = {(r, False) for r in RE_PATH.findall(ligne)
                     if r.startswith(RACINES)}
            # A bare `name.md` in a doc names a repo file too: that is how an
            # index kept pointing at voyage.md long after it became travel.md.
            if nom.endswith(".md"):
                cites |= {(r, False) for r in RE_NU.findall(ligne)}
            for ref, est_lien in liens | cites:
                if ref in ARTEFACTS_CAMPAGNE:
                    continue
                if IGNORE.search(ref) or not ref.endswith(SUIVIES):
                    continue
                if est_lien and "/" not in ref and not ref.endswith((".md", ".py")):
                    continue
                if not resout(ref, chemin, connus, strict=est_lien and "/" in ref):
                    casses.append((nom, num, ref))
                elif verbeux:
                    print(f"  ok   {nom}:{num}  {ref}")
    return casses


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--verbose", action="store_true",
                    help="also print references that resolve")
    args = ap.parse_args(argv)

    casses = scanner(args.verbose)
    if not casses:
        print("✅ No broken file references.")
        return 0

    print(f"❌ {len(casses)} broken reference(s):\n")
    for nom, num, ref in casses:
        print(f"  {nom}:{num}\n      → {ref}")
    print("\nEach one points at a file that does not exist. Fix the reference "
          "or restore the file.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
