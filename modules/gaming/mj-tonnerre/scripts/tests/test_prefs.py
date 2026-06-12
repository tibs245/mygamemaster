#!/usr/bin/env python3
"""
test_prefs.py — Tests for prefs.py (per-player play preferences read/write).

STDLIB `unittest` (no pytest). Run from `scripts/`:
    python3 -m unittest discover -s tests

Covers: get whole block / single documented key / custom key, set documented
key (JSON + raw string), set unknown key → custom, unset, dry-run writes
nothing, compartmentalization (only the named player's file is touched),
fail-open exit codes (missing/unreadable sheet), and the CLI surface.
Data: self-contained throwaway campaign in a tmp dir. No real campaign touched.
"""

from __future__ import annotations

import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent.parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import prefs as P  # noqa: E402


ALICE = "100000000000000001"
BOB = "100000000000000002"


def _sheet(nom_joueur, prefs=None):
    fiche = {
        "meta": {"nom_joueur": nom_joueur, "discord_id": "x", "nom_perso": nom_joueur},
        "notes_perso": {"objectifs": [], "relations": {}, "secrets": []},
    }
    if prefs is not None:
        fiche["preferences"] = prefs
    return fiche


class PrefsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="mj-prefs-test-")
        self.camp = Path(self.tmp)
        pdir = self.camp / "personnages"
        pdir.mkdir(parents=True)
        # Alice already has a preferences block; Bob has none (fail-open path).
        (pdir / f"{ALICE}.json").write_text(json.dumps(_sheet("Alice", {
            "rythme": "slow",
            "ton_aime": ["mystery"],
            "aime_etre_trompe": True,
            "custom": {"music": "sting on crits"},
        }), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        (pdir / f"{BOB}.json").write_text(json.dumps(_sheet("Bob"),
                                          ensure_ascii=False, indent=2) + "\n",
                                          encoding="utf-8")

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _run(self, *argv):
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = P.main([str(self.camp), *[str(a) for a in argv]])
        return code, buf.getvalue()

    def _sheet_json(self, discord_id):
        return json.loads((self.camp / "personnages" / f"{discord_id}.json").read_text())

    # ── GET ───────────────────────────────────────────────────────────────
    def test_get_whole_block(self):
        code, out = self._run(ALICE, "get")
        self.assertEqual(code, 0)
        data = json.loads(out)
        self.assertEqual(data["rythme"], "slow")
        self.assertEqual(data["custom"]["music"], "sting on crits")

    def test_get_documented_key(self):
        code, out = self._run(ALICE, "get", "rythme")
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out), "slow")

    def test_get_custom_key(self):
        code, out = self._run(ALICE, "get", "music")
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out), "sting on crits")

    def test_get_missing_block_is_empty(self):
        code, out = self._run(BOB, "get")
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out), {})

    # ── SET ───────────────────────────────────────────────────────────────
    def test_set_documented_raw_string(self):
        code, _ = self._run(ALICE, "set", "spotlight", "share the spotlight")
        self.assertEqual(code, 0)
        self.assertEqual(self._sheet_json(ALICE)["preferences"]["spotlight"],
                         "share the spotlight")

    def test_set_documented_json_bool(self):
        code, _ = self._run(BOB, "set", "aime_etre_trompe", "false")
        self.assertEqual(code, 0)
        self.assertIs(self._sheet_json(BOB)["preferences"]["aime_etre_trompe"], False)

    def test_set_documented_json_list(self):
        code, _ = self._run(BOB, "set", "ton_aime", '["tension","action"]')
        self.assertEqual(code, 0)
        self.assertEqual(self._sheet_json(BOB)["preferences"]["ton_aime"],
                         ["tension", "action"])

    def test_set_unknown_key_goes_to_custom(self):
        code, _ = self._run(BOB, "set", "music_cues", "play a sting")
        self.assertEqual(code, 0)
        prefs = self._sheet_json(BOB)["preferences"]
        self.assertEqual(prefs["custom"]["music_cues"], "play a sting")
        self.assertNotIn("music_cues", {k for k in prefs if k != "custom"})

    def test_set_preserves_other_sheet_fields(self):
        self._run(ALICE, "set", "rythme", "fast")
        fiche = self._sheet_json(ALICE)
        self.assertIn("notes_perso", fiche)
        self.assertEqual(fiche["meta"]["nom_joueur"], "Alice")

    # ── UNSET ─────────────────────────────────────────────────────────────
    def test_unset_documented_key(self):
        code, _ = self._run(ALICE, "unset", "rythme")
        self.assertEqual(code, 0)
        self.assertNotIn("rythme", self._sheet_json(ALICE)["preferences"])

    def test_unset_custom_key(self):
        code, _ = self._run(ALICE, "unset", "music")
        self.assertEqual(code, 0)
        self.assertNotIn("music", self._sheet_json(ALICE)["preferences"]["custom"])

    def test_unset_absent_key_is_noop_success(self):
        code, _ = self._run(ALICE, "unset", "does_not_exist")
        self.assertEqual(code, 0)

    # ── DRY-RUN ───────────────────────────────────────────────────────────
    def test_dry_run_writes_nothing(self):
        before = (self.camp / "personnages" / f"{ALICE}.json").read_text()
        code, _ = self._run(ALICE, "set", "rythme", "changed", "--dry-run")
        self.assertEqual(code, 0)
        after = (self.camp / "personnages" / f"{ALICE}.json").read_text()
        self.assertEqual(before, after)

    # ── COMPARTMENTALIZATION ──────────────────────────────────────────────
    def test_set_touches_only_named_player(self):
        bob_before = (self.camp / "personnages" / f"{BOB}.json").read_text()
        self._run(ALICE, "set", "rythme", "fast")
        bob_after = (self.camp / "personnages" / f"{BOB}.json").read_text()
        self.assertEqual(bob_before, bob_after)

    # ── FAIL-OPEN / USAGE ─────────────────────────────────────────────────
    def test_missing_sheet_exit_2(self):
        code, _ = self._run("999999999999999999", "get")
        self.assertEqual(code, 2)

    def test_set_without_value_exit_1(self):
        code, _ = self._run(ALICE, "set", "rythme")
        self.assertEqual(code, 1)

    def test_json_output(self):
        code, out = self._run(ALICE, "set", "rythme", "fast", "--json")
        self.assertEqual(code, 0)
        payload = json.loads(out)
        self.assertEqual(payload["preferences"]["rythme"], "fast")


if __name__ == "__main__":
    unittest.main()
