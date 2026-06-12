#!/usr/bin/env python3
"""
test_emotions.py — Tests for the character emotions module (mj-tonnerre-emotions).

STDLIB `unittest` (no pytest required). Run from `scripts/`:
    python3 -m unittest discover -s tests

Covers:
  * update rules: named event → expected emotional delta (direction + value),
    intensity scaling, clamping to [0, 1];
  * decay: fraction of the gap toward temperament, fast `surprise` decay,
    rate 1.0 lands exactly on temperament;
  * explainability: history journaled with effective deltas + reason, capped;
  * summary: one-line GM brief (tone, ▲/▼ deviations, last shift), '' when no
    emotions data (FAIL-OPEN: absent emotions → no behavior change);
  * CLI: init/apply/adjust/decay/get/summary against a throwaway campaign,
    auto-init on apply, PC sheet opt-in (personnages/*.json), exit codes,
    `summary` exits 0 even on a broken/missing campaign.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent.parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import emotions as E               # noqa: E402

PY = sys.executable
SCRIPT = str(SCRIPTS_DIR / "emotions.py")


def neutral_state():
    return dict(E.DEFAULT_TEMPERAMENT)


def run_cli(*args):
    """Runs emotions.py as a subprocess. Returns (rc, stdout, stderr)."""
    proc = subprocess.run([PY, SCRIPT, *map(str, args)],
                          capture_output=True, text=True, timeout=30)
    return proc.returncode, proc.stdout, proc.stderr


# ════════════════════════════════════════════════════════════════════════════
#  Update rules (pure functions)
# ════════════════════════════════════════════════════════════════════════════

class TestUpdateRules(unittest.TestCase):

    def test_betrayal_moves_emotions_in_the_logical_direction(self):
        state = neutral_state()
        new, applied = E.apply_event(state, "betrayal")
        self.assertLess(new["confiance"], state["confiance"])   # trust collapses
        self.assertGreater(new["colere"], state["colere"])      # anger rises
        self.assertGreater(new["peur"], state["peur"])          # fear rises
        self.assertGreater(new["surprise"], state["surprise"])  # shock
        self.assertIn("colere", applied)

    def test_kindness_repaid_raises_warmth(self):
        new, _ = E.apply_event(neutral_state(), "kindness")
        self.assertGreater(new["confiance"], E.DEFAULT_TEMPERAMENT["confiance"])
        self.assertGreater(new["joie"], E.DEFAULT_TEMPERAMENT["joie"])

    def test_exact_delta_applied(self):
        state = neutral_state()  # confiance 0.3
        new, applied = E.apply_event(state, "promise_kept")  # confiance +0.25
        self.assertAlmostEqual(new["confiance"], 0.55, places=3)
        self.assertAlmostEqual(applied["confiance"], 0.25, places=3)

    def test_intensity_scales_deltas(self):
        full, _ = E.apply_event(neutral_state(), "threat", intensity=1.0)
        half, _ = E.apply_event(neutral_state(), "threat", intensity=0.5)
        gap_full = full["peur"] - E.DEFAULT_TEMPERAMENT["peur"]
        gap_half = half["peur"] - E.DEFAULT_TEMPERAMENT["peur"]
        self.assertAlmostEqual(gap_half, gap_full / 2, places=3)

    def test_clamped_to_unit_interval(self):
        state = dict(neutral_state(), peur=0.9, confiance=0.05)
        new, applied = E.apply_event(state, "attack")  # peur +0.4, confiance -0.3
        self.assertEqual(new["peur"], 1.0)
        self.assertEqual(new["confiance"], 0.0)
        # `applied` records the EFFECTIVE (post-clamping) deltas.
        self.assertAlmostEqual(applied["peur"], 0.1, places=3)
        self.assertAlmostEqual(applied["confiance"], -0.05, places=3)

    def test_unknown_event_raises(self):
        with self.assertRaises(KeyError):
            E.apply_event(neutral_state(), "existential_dread")

    def test_every_rule_only_touches_palette_emotions(self):
        for event, deltas in E.EVENT_RULES.items():
            for emo in deltas:
                self.assertIn(emo, E.EMOTIONS, "%s → %s" % (event, emo))

    def test_apply_deltas_ignores_garbage(self):
        new, applied = E.apply_deltas(neutral_state(),
                                      {"peur": "huge", "inconnu": 0.4, "joie": True})
        self.assertEqual(new, neutral_state())
        self.assertEqual(applied, {})


class TestDecay(unittest.TestCase):

    def test_decay_closes_half_the_gap(self):
        temperament = neutral_state()                       # peur 0.2
        state = dict(temperament, peur=0.8)
        new = E.decay_state(state, temperament, rate=0.5)
        self.assertAlmostEqual(new["peur"], 0.5, places=3)  # 0.8 → halfway to 0.2

    def test_decay_works_upward_too(self):
        temperament = dict(neutral_state(), joie=0.6)
        state = dict(temperament, joie=0.0)                 # grief-stricken optimist
        new = E.decay_state(state, temperament, rate=0.5)
        self.assertAlmostEqual(new["joie"], 0.3, places=3)  # drifts back up

    def test_full_rate_lands_on_temperament(self):
        temperament = neutral_state()
        state = dict(temperament, colere=1.0, joie=0.0)
        new = E.decay_state(state, temperament, rate=1.0)
        self.assertEqual(new, E.normalize_state(temperament))

    def test_surprise_decays_fast_even_at_low_rate(self):
        temperament = neutral_state()                       # surprise 0.0
        state = dict(temperament, surprise=1.0, peur=1.0)
        new = E.decay_state(state, temperament, rate=0.1)
        self.assertLessEqual(new["surprise"], 0.2)          # ≥ 0.8 of gap closed
        self.assertAlmostEqual(new["peur"], 0.92, places=3)  # others at rate 0.1

    def test_bad_rate_falls_back(self):
        temperament = neutral_state()
        state = dict(temperament, peur=0.8)
        new = E.decay_state(state, temperament, rate="not-a-number")
        self.assertAlmostEqual(new["peur"], 0.5, places=3)  # default 0.5


class TestSummaryAndFailOpen(unittest.TestCase):

    def test_no_emotions_means_no_output(self):
        self.assertEqual(E.summary_line({"nom": "Berthe"}), "")
        self.assertEqual(E.summary_line({"nom": "Berthe", "emotions": "high"}), "")
        self.assertEqual(E.summary_line(None), "")
        self.assertEqual(E.summary_block([{"nom": "A"}, {"nom": "B"}]), "")

    def test_summary_shows_deviation_and_reason(self):
        fiche = {"nom": "Berthe", "emotions": {
            "etat": dict(neutral_state(), peur=0.7, confiance=0.1),
            "temperament": neutral_state(),
            "historique": [{"evenement": "betrayal", "deltas": {},
                            "raison": "sold the players out", "session": 2}],
        }}
        line = E.summary_line(fiche)
        self.assertIn("Berthe", line)
        self.assertIn("fearful", line)            # dominant tone ≥ 0.5
        self.assertIn("peur .7▲", line)
        self.assertIn("confiance .1▼", line)
        self.assertIn("sold the players out (S2)", line)

    def test_summary_at_temperament_reads_composed(self):
        fiche = {"nom": "Lady", "emotions": {
            "etat": neutral_state(), "temperament": neutral_state(),
            "historique": [],
        }}
        line = E.summary_line(fiche)
        self.assertIn("composed", line)
        self.assertNotIn("▲", line)

    def test_block_caps_and_orders_by_recency(self):
        fiches = []
        for i in range(8):
            fiches.append({"nom": "P%d" % i, "emotions": {
                "etat": dict(neutral_state(), peur=0.6),
                "temperament": neutral_state(),
                "historique": [{"evenement": "threat", "deltas": {},
                                "raison": "r", "session": i}],
            }})
        block = E.summary_block(fiches, max_npc=6)
        self.assertEqual(block.count("•"), 6)
        self.assertIn("P7", block)                 # most recent shift first
        self.assertNotIn("P0", block)              # oldest dropped past the cap
        self.assertIn("NEVER state feelings", block)

    def test_normalize_state_tolerates_garbage(self):
        out = E.normalize_state({"peur": "deep", "joie": 2.4, "colere": -1})
        self.assertEqual(out["peur"], E.DEFAULT_TEMPERAMENT["peur"])
        self.assertEqual(out["joie"], 1.0)
        self.assertEqual(out["colere"], 0.0)
        self.assertEqual(set(out), set(E.EMOTIONS))


# ════════════════════════════════════════════════════════════════════════════
#  History (explainability journal)
# ════════════════════════════════════════════════════════════════════════════

class TestHistory(unittest.TestCase):

    def test_record_appends_reason_and_session(self):
        emo = {"historique": []}
        E.record_history(emo, "threat", {"peur": 0.3}, "drew a blade", session=4)
        entry = emo["historique"][-1]
        self.assertEqual(entry["evenement"], "threat")
        self.assertEqual(entry["raison"], "drew a blade")
        self.assertEqual(entry["session"], 4)
        self.assertEqual(entry["deltas"], {"peur": 0.3})

    def test_history_is_capped(self):
        emo = {"historique": []}
        for i in range(E.HISTORY_MAX + 7):
            E.record_history(emo, "kindness", {"joie": 0.1}, "r%d" % i)
        self.assertEqual(len(emo["historique"]), E.HISTORY_MAX)
        self.assertEqual(emo["historique"][-1]["raison"],
                         "r%d" % (E.HISTORY_MAX + 6))   # newest kept


# ════════════════════════════════════════════════════════════════════════════
#  CLI integration (throwaway campaign)
# ════════════════════════════════════════════════════════════════════════════

class TestCli(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="mjt-emotions-")
        self.camp = Path(self.tmp.name)
        (self.camp / "personnages").mkdir()
        self._write("monde.json", {"meta": {"nom": "Test"}})
        self._write("pnj.json", [
            {"nom": "Berthe", "faits_etablis": [], "hypotheses_mj": []},
            {"nom": "Firmin", "faits_etablis": [], "hypotheses_mj": []},
        ])
        self._write("personnages/403.json", {
            "meta": {"nom_perso": "Rubis", "discord_id": "403"},
            "inventaire": [],
        })

    def tearDown(self):
        self.tmp.cleanup()

    def _write(self, rel, obj):
        path = self.camp / rel
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(obj, fh, ensure_ascii=False, indent=2)

    def _pnj(self, name):
        data = json.loads((self.camp / "pnj.json").read_text(encoding="utf-8"))
        return next(f for f in data if f["nom"] == name)

    def test_full_lifecycle(self):
        rc, out, _ = run_cli("init", self.camp, "Berthe", "peur=0.4")
        self.assertEqual(rc, 0)
        rc, out, _ = run_cli("apply", self.camp, "Berthe", "--event", "betrayal",
                             "--reason", "sold the players out", "--session", "2")
        self.assertEqual(rc, 0, out)
        emo = self._pnj("Berthe")["emotions"]
        self.assertLess(emo["etat"]["confiance"], 0.3)
        self.assertEqual(emo["historique"][-1]["session"], 2)
        self.assertEqual(emo["historique"][-1]["raison"], "sold the players out")

        rc, out, _ = run_cli("decay", self.camp, "--rate", "1.0")
        self.assertEqual(rc, 0, out)
        emo = self._pnj("Berthe")["emotions"]
        self.assertEqual(E.normalize_state(emo["etat"]),
                         E.normalize_state(emo["temperament"]))

        rc, out, _ = run_cli("get", self.camp, "Berthe", "--json")
        self.assertEqual(rc, 0)
        self.assertIn("historique", json.loads(out) or {})

    def test_init_twice_requires_force(self):
        run_cli("init", self.camp, "Berthe")
        rc, _, err = run_cli("init", self.camp, "Berthe")
        self.assertEqual(rc, 1)
        self.assertIn("--force", err)
        rc, _, _ = run_cli("init", self.camp, "Berthe", "joie=0.9", "--force")
        self.assertEqual(rc, 0)
        self.assertEqual(self._pnj("Berthe")["emotions"]["temperament"]["joie"], 0.9)

    def test_apply_auto_initializes(self):
        rc, _, _ = run_cli("apply", self.camp, "Firmin", "--event", "gift",
                           "--reason", "a warm meal")
        self.assertEqual(rc, 0)
        emo = self._pnj("Firmin")["emotions"]
        self.assertIn("temperament", emo)
        self.assertGreater(emo["etat"]["joie"], E.DEFAULT_TEMPERAMENT["joie"])

    def test_adjust_requires_reason(self):
        rc, _, _ = run_cli("adjust", self.camp, "Berthe", "peur=+0.2")
        self.assertEqual(rc, 2)                    # argparse: --reason required
        rc, _, _ = run_cli("adjust", self.camp, "Berthe", "peur=+0.2",
                           "--reason", "the mist reached the door")
        self.assertEqual(rc, 0)
        self.assertEqual(self._pnj("Berthe")["emotions"]["historique"][-1]["raison"],
                         "the mist reached the door")

    def test_pc_sheet_opt_in(self):
        rc, _, _ = run_cli("apply", self.camp, "Rubis", "--event", "victory",
                           "--reason", "slew the wyrm")
        self.assertEqual(rc, 0)
        fiche = json.loads((self.camp / "personnages" / "403.json")
                           .read_text(encoding="utf-8"))
        self.assertGreater(fiche["emotions"]["etat"]["joie"],
                           E.DEFAULT_TEMPERAMENT["joie"])
        # PC emotions are NEVER injected: summary only reads pnj.json.
        rc, out, _ = run_cli("summary", self.camp)
        self.assertEqual(rc, 0)
        self.assertNotIn("Rubis", out)

    def test_unknown_character_and_event(self):
        rc, _, err = run_cli("get", self.camp, "Nobody")
        self.assertEqual(rc, 1)
        self.assertIn("not found", err)
        rc, _, err = run_cli("apply", self.camp, "Berthe", "--event", "nonsense")
        self.assertEqual(rc, 1)
        self.assertIn("unknown event", err)

    def test_summary_fail_open(self):
        # No emotions data at all → empty output, code 0.
        rc, out, _ = run_cli("summary", self.camp)
        self.assertEqual(rc, 0)
        self.assertEqual(out.strip(), "")
        # Broken pnj.json → still code 0, still silent.
        (self.camp / "pnj.json").write_text("{not json", encoding="utf-8")
        rc, out, _ = run_cli("summary", self.camp)
        self.assertEqual(rc, 0)
        self.assertEqual(out.strip(), "")
        # Missing campaign → still code 0 (the hook must never break a turn).
        rc, out, _ = run_cli("summary", self.camp / "nope")
        self.assertEqual(rc, 0)

    def test_summary_with_data(self):
        run_cli("init", self.camp, "Berthe")
        run_cli("apply", self.camp, "Berthe", "--event", "attack",
                "--reason", "ambushed at the ford", "--session", "3")
        rc, out, _ = run_cli("summary", self.camp)
        self.assertEqual(rc, 0)
        self.assertIn("NPC EMOTIONS", out)
        self.assertIn("Berthe", out)
        self.assertIn("ambushed at the ford (S3)", out)
        self.assertNotIn("Firmin", out)            # no data → no line (fail-open)

    def test_missing_campaign_is_usage_error(self):
        rc, _, _ = run_cli("get", self.camp / "nope", "Berthe")
        self.assertEqual(rc, 2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
