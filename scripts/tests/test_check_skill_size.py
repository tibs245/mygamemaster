#!/usr/bin/env python3
"""
test_check_skill_size.py — tests for the skill character-budget guard.

STDLIB `unittest` (no pytest required). Run from `scripts/`:
    python3 -m unittest discover -s tests

Covers the contract the guard exists to enforce:
  * a skill under 80 % is silent, 80–90 % warns without blocking, ≥ 90 % fails;
  * the failure message names the file, its usage, and what to do about it;
  * a skill the guard cannot read blocks instead of vanishing from the report;
  * classification uses the larger of characters and UTF-8 bytes;
  * MGM_SKILL_SIZE_SKIP=1 turns a budget failure into a warning (operator
    escape hatch) but never waives an unmeasurable file.

The shipped repo's own budget is asserted by the guard step in CI and in
.pre-commit-run-tests.sh, which print the actionable remedy — not here, where a
failure would only surface as `AssertionError: 1 != 0` and would ignore the
documented escape hatch.
"""

import io
import os
import stat
import unittest
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path
from tempfile import TemporaryDirectory

import check_skill_size as CSS


def ecrire_skill(racine: Path, module: str, taille: int, char: str = "x") -> Path:
    chemin = racine / "modules" / "gaming" / module / "SKILL.md"
    chemin.parent.mkdir(parents=True, exist_ok=True)
    chemin.write_text(char * taille, encoding="utf-8")
    return chemin


def ecrire_skill_brut(racine: Path, module: str, octets: bytes) -> Path:
    chemin = racine / "modules" / "gaming" / module / "SKILL.md"
    chemin.parent.mkdir(parents=True, exist_ok=True)
    chemin.write_bytes(octets)
    return chemin


def lancer(argv: list[str]) -> tuple[int, str]:
    sortie = io.StringIO()
    with redirect_stdout(sortie), redirect_stderr(sortie):
        code = CSS.main(argv)
    return code, sortie.getvalue()


class TestClassify(unittest.TestCase):
    def test_tiers(self):
        self.assertEqual(CSS.classify(10_000, 100_000)[0], CSS.OK)
        self.assertEqual(CSS.classify(79_999, 100_000)[0], CSS.OK)
        self.assertEqual(CSS.classify(80_000, 100_000)[0], CSS.WARN)
        self.assertEqual(CSS.classify(89_999, 100_000)[0], CSS.WARN)
        self.assertEqual(CSS.classify(90_000, 100_000)[0], CSS.FAIL)
        self.assertEqual(CSS.classify(104_162, 100_000)[0], CSS.FAIL)

    def test_ratio_is_usage_share(self):
        self.assertAlmostEqual(CSS.classify(45_000, 100_000)[1], 0.45)

    def test_limit_constant_matches_platform(self):
        self.assertEqual(CSS.LIMIT, 100_000)
        self.assertLess(CSS.WARN_RATIO, CSS.FAIL_RATIO)


class TestScan(unittest.TestCase):
    def test_finds_every_skill_and_reports_usage(self):
        with TemporaryDirectory() as tmp:
            racine = Path(tmp)
            ecrire_skill(racine, "small", 1_000)
            ecrire_skill(racine, "big", 95_000)
            resultats, illisibles = CSS.scan(racine)
        index = {r[0]: (r[1], r[4]) for r in resultats}
        self.assertEqual(illisibles, [])
        self.assertEqual(len(index), 2)
        self.assertEqual(index["modules/gaming/small/SKILL.md"], (1_000, CSS.OK))
        self.assertEqual(index["modules/gaming/big/SKILL.md"], (95_000, CSS.FAIL))

    def test_ignores_non_skill_markdown(self):
        with TemporaryDirectory() as tmp:
            racine = Path(tmp)
            chemin = ecrire_skill(racine, "one", 10)
            (chemin.parent / "README.md").write_text("y" * 200_000, encoding="utf-8")
            self.assertEqual(len(CSS.scan(racine)[0]), 1)

    def test_measures_characters_and_bytes(self):
        with TemporaryDirectory() as tmp:
            racine = Path(tmp)
            ecrire_skill(racine, "accents", 1_000, char="é")
            (resultat,), _ = CSS.scan(racine)
        self.assertEqual(resultat[1], 1_000)   # characters
        self.assertEqual(resultat[2], 2_000)   # UTF-8 bytes

    def test_unreadable_file_is_collected_not_dropped(self):
        with TemporaryDirectory() as tmp:
            racine = Path(tmp)
            # 99 000 latin-1 'é' — a real hazard in a bilingual FR/EN repo.
            ecrire_skill_brut(racine, "latin1", "é".encode("latin-1") * 99_000)
            ecrire_skill(racine, "fine", 1_000)
            resultats, illisibles = CSS.scan(racine)
        self.assertEqual([r[0] for r in resultats], ["modules/gaming/fine/SKILL.md"])
        self.assertEqual(len(illisibles), 1)
        self.assertEqual(illisibles[0][0], "modules/gaming/latin1/SKILL.md")
        self.assertIn("UnicodeDecodeError", illisibles[0][1])


class TestMain(unittest.TestCase):
    def setUp(self):
        os.environ.pop(CSS.ENV_SKIP, None)

    tearDown = setUp

    def test_clean_tree_passes(self):
        with TemporaryDirectory() as tmp:
            ecrire_skill(Path(tmp), "one", 12_000)
            code, sortie = lancer(["--root", tmp])
        self.assertEqual(code, 0)
        self.assertIn("✅", sortie)
        self.assertIn("12.0%", sortie)

    def test_warning_tier_is_reported_but_not_blocking(self):
        with TemporaryDirectory() as tmp:
            ecrire_skill(Path(tmp), "warned", 85_000)
            code, sortie = lancer(["--root", tmp])
        self.assertEqual(code, 0)
        self.assertIn("⚠️", sortie)
        self.assertIn("85.0%", sortie)
        self.assertIn("modules/gaming/warned/SKILL.md", sortie)

    def test_oversized_skill_fails_with_actionable_message(self):
        with TemporaryDirectory() as tmp:
            ecrire_skill(Path(tmp), "frozen", 95_000)
            code, sortie = lancer(["--root", tmp])
        self.assertEqual(code, 1)
        self.assertIn("modules/gaming/frozen/SKILL.md", sortie)
        self.assertIn("95.0%", sortie)
        self.assertIn("references/", sortie)
        self.assertIn("Split the skill", sortie)
        self.assertIn(CSS.ENV_SKIP, sortie)

    def test_byte_heavy_skill_fails_even_when_char_count_is_safe(self):
        # 60 000 accented characters = 120 000 UTF-8 bytes. Classified on the
        # larger of the two, so the guard is never looser than the limit.
        with TemporaryDirectory() as tmp:
            ecrire_skill(Path(tmp), "accents", 60_000, char="é")
            code, sortie = lancer(["--root", tmp])
        self.assertEqual(code, 1)
        self.assertIn("120.0%", sortie)
        self.assertIn("chars", sortie)
        self.assertIn("bytes", sortie)

    def test_unmeasurable_skill_blocks_and_is_named(self):
        with TemporaryDirectory() as tmp:
            racine = Path(tmp)
            ecrire_skill_brut(racine, "latin1", "é".encode("latin-1") * 99_000)
            ecrire_skill(racine, "fine", 1_000)
            code, sortie = lancer(["--root", tmp])
        self.assertEqual(code, 1)
        self.assertIn("could not be measured", sortie)
        self.assertIn("modules/gaming/latin1/SKILL.md", sortie)
        self.assertIn("UTF-8", sortie)
        self.assertNotIn("✅", sortie)

    @unittest.skipIf(hasattr(os, "geteuid") and os.geteuid() == 0,
                     "root ignores file permissions")
    def test_permission_denied_skill_blocks(self):
        with TemporaryDirectory() as tmp:
            racine = Path(tmp)
            chemin = ecrire_skill(racine, "locked", 95_000)
            chemin.chmod(0)
            try:
                code, sortie = lancer(["--root", tmp])
            finally:
                chemin.chmod(stat.S_IRUSR | stat.S_IWUSR)
        self.assertEqual(code, 1)
        self.assertIn("could not be measured", sortie)
        self.assertIn("modules/gaming/locked/SKILL.md", sortie)

    def test_escape_hatch_waives_the_failure(self):
        os.environ[CSS.ENV_SKIP] = "1"
        with TemporaryDirectory() as tmp:
            ecrire_skill(Path(tmp), "frozen", 99_000)
            code, sortie = lancer(["--root", tmp])
        self.assertEqual(code, 0)
        self.assertIn("waived", sortie)

    def test_escape_hatch_does_not_waive_an_unmeasurable_skill(self):
        os.environ[CSS.ENV_SKIP] = "1"
        with TemporaryDirectory() as tmp:
            racine = Path(tmp)
            ecrire_skill_brut(racine, "latin1", "é".encode("latin-1") * 10)
            code, sortie = lancer(["--root", tmp])
        self.assertEqual(code, 1)
        self.assertIn("could not be measured", sortie)

    def test_escape_hatch_only_on_exact_one(self):
        os.environ[CSS.ENV_SKIP] = "yes"
        with TemporaryDirectory() as tmp:
            ecrire_skill(Path(tmp), "frozen", 99_000)
            code, _ = lancer(["--root", tmp])
        self.assertEqual(code, 1)

    def test_custom_limit(self):
        with TemporaryDirectory() as tmp:
            ecrire_skill(Path(tmp), "one", 9_500)
            self.assertEqual(lancer(["--root", tmp, "--limit", "10000"])[0], 1)
            self.assertEqual(lancer(["--root", tmp, "--limit", "100000"])[0], 0)

    def test_non_positive_limit_is_a_usage_error(self):
        self.assertEqual(lancer(["--limit", "0"])[0], 2)

    def test_empty_tree_is_not_a_failure(self):
        with TemporaryDirectory() as tmp:
            code, sortie = lancer(["--root", tmp])
        self.assertEqual(code, 0)
        self.assertIn("nothing checked", sortie)


if __name__ == "__main__":
    unittest.main()
