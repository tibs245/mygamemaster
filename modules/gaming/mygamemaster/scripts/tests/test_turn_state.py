#!/usr/bin/env python3
"""
test_turn_state.py — Tests for the turn state machine (`hooks/turn_state.py`).

STDLIB `unittest` (no pytest required). Run from `scripts/`:
    python3 -m unittest discover -s tests

The module under test lives in `hooks/` (it is turn runtime state, persisted in
`.banquier/` through `hooks/_lib.py`), but its tests live here because this is the
directory the pre-push runner discovers automatically; `hooks/test_hooks.py` is a
bespoke harness for hooks invoked as `stdin JSON → stdout JSON` subprocesses, which
`turn_state.py` is not.

Cases are drawn from the corpus documented in `docs/10-field-report.md` and
`references/locked-lessons.md`:
  * S23 — a whole bivouac narrated off an announced intention (AGENCY-04 / TURN-02);
  * S23 — five non-ordinary moments crossed inside a single STOP (TURN-01);
  * S17 — an ellipse longer than about an hour taken without asking (TURN-02);
  * S34 — a fast-forward that lands on a focal event and then keeps going (TURN-06);
  * S14 — stacked actions, here only as a NON-case: that is the agency gate's job.

Covers: signal recognition (FR/EN, canonical `⏩`, commands), the negative rules — a
question / an intention / an ORDINARY ACTION is never a grant — ellipse detection around
the one-hour bar and its position in the sentence (lore and distance are not ellipses),
dialogue masking, the four states and their transitions, grant consumption (once, and
never on a refusal), persistence in `.banquier/snap-<sid>.json`, the anti-loop budget and
its forced release, the operator escape hatch, and the CLI contract.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent.parent
HOOKS_DIR = SCRIPTS_DIR.parent / "hooks"
sys.path.insert(0, str(HOOKS_DIR))

import _lib as L  # noqa: E402
import turn_state as T  # noqa: E402


def make_campaign(root: Path, hooks_cfg: dict | None = None) -> Path:
    camp = root / "campagne"
    camp.mkdir(parents=True, exist_ok=True)
    monde = {"meta": {"name": "test", "hooks": hooks_cfg or {}}}
    (camp / "world.json").write_text(json.dumps(monde), encoding="utf-8")
    return camp


PAYLOAD = {"session_id": "gate"}

# S23: five non-ordinary moments crossed inside a single STOP.
DRAFT_S23_BIVOUAC = (
    "Vous arrivez à la clairière. Trois heures plus tard, le feu prend. "
    "Le lendemain matin, vous êtes de retour au camp."
)
DRAFT_ONE_ELLIPSE = "Trois heures plus tard, la neige a couvert les traces."
DRAFT_TWO_ELLIPSES = (
    "Trois heures plus tard, la forge s'éteint. Le lendemain, la porte est ouverte."
)
DRAFT_STILL = "La hache est plantée dans le billot. Le vent tourne. Le forgeron attend."


class TestSignalRecognition(unittest.TestCase):
    """TURN-02 — what is, and above all what is NOT, a fast-forward signal."""

    def test_canonical_marker(self):
        self.assertEqual(T.classify_input("⏩")[0], "fast_forward")
        self.assertEqual(T.classify_input("⏩ jusqu'au soir")[0], "fast_forward")

    def test_commands_and_plain_language_fr(self):
        for msg in ("!ff", "!avance", "avance rapide jusqu'au soir",
                    "passe à la suite", "saute jusqu'au matin", "ellipse jusqu'au soir",
                    "fais une ellipse", "ok, avance rapide"):
            self.assertEqual(T.classify_input(msg)[0], "fast_forward", msg)

    def test_plain_language_en(self):
        for msg in ("fast forward", "fast-forward to the morning", "skip ahead",
                    "jump to the next scene", "time skip"):
            self.assertEqual(T.classify_input(msg)[0], "fast_forward", msg)

    def test_an_ordinary_action_is_never_a_signal(self):
        """The fail-open this module exists to remove: a verb is not a permission.

        Every line below is a plain declaration of what the PC does. Matching the
        fast-forward vocabulary as a substring would hand a three-hour ellipse to a
        two-metre walk — the most common French action declaration in the corpus.
        """
        for msg in ("J'avance vers la porte de la forge.",
                    "On avance prudemment dans le couloir.",
                    "on avance", "Je saute la barrière.",
                    "je saute au-dessus du ravin",
                    "Je m'avance vers le forgeron.",
                    "Avance vers la porte.",
                    "Je passe la main sur la pierre.",
                    "I move on to the next room", "I skip the meal",
                    "Je prends la hache."):
            self.assertEqual(T.classify_input(msg)[0], "action", msg)

    def test_an_ordinary_action_arms_no_grant_end_to_end(self):
        with tempfile.TemporaryDirectory() as tmp:
            camp = make_campaign(Path(tmp))
            v = T.check_narration(
                camp, PAYLOAD,
                "Trois heures plus tard, vous arrivez au moulin et le meunier vous salue.",
                "J'avance vers la porte de la forge.")
            self.assertEqual(v["input"], "action")
            self.assertFalse(v["granted"])
            self.assertFalse(v["ok"])
            self.assertIn("TURN-02", [x["regle"] for x in v["violations"]])

    def test_a_question_is_never_a_signal(self):
        for msg in ("on avance ?", "on saute jusqu'au matin ?",
                    "should we skip ahead?", "⏸️ tu peux avancer ?"):
            self.assertEqual(T.classify_input(msg)[0], "question", msg)

    def test_an_intention_is_never_a_signal(self):
        for msg in ("je vais passer à la suite", "j'aimerais avancer jusqu'au soir",
                    "je compte monter le bivouac", "I'm going to skip ahead",
                    "we could fast forward"):
            self.assertEqual(T.classify_input(msg)[0], "intention", msg)

    def test_action_and_silence(self):
        self.assertEqual(T.classify_input("Je prends la hache.")[0], "action")
        self.assertEqual(T.classify_input("")[0], "silence")
        self.assertEqual(T.classify_input("   \n ")[0], "silence")

    def test_accents_and_case_are_folded(self):
        self.assertEqual(T.classify_input("AVANCE RAPIDE")[0], "fast_forward")
        self.assertEqual(T.classify_input("Passe à la suite")[0], "fast_forward")
        self.assertEqual(T.classify_input("passe a la suite")[0], "fast_forward")


class TestMomentDetection(unittest.TestCase):
    """What the machine can honestly read: markers, not meaning."""

    def kinds(self, draft):
        return [m["kind"] for m in T.detect_moments(draft)]

    def test_ellipse_above_the_hour_bar(self):
        for draft in ("Trois heures plus tard, la neige tombe.",
                      "Deux jours passent.",
                      "Après quelques heures de marche, la vallée s'ouvre.",
                      "Three hours later, the fire is out.",
                      "After two days, the river is frozen."):
            self.assertIn("ellipse", self.kinds(draft), draft)

    def test_named_ellipses(self):
        for draft in ("Le lendemain matin, la forge est froide.",
                      "Le jour suivant, la porte est ouverte.",
                      "The next morning, the gate is shut.",
                      "Days pass.", "Overnight, the frost takes the field."):
            self.assertIn("ellipse", self.kinds(draft), draft)

    def test_below_the_hour_bar_is_not_an_ellipse(self):
        """TURN-02 sets the bar at about an hour — under it, no grant is required."""
        for draft in ("Quelques instants plus tard, il lève la tête.",
                      "Une heure plus tard, la pluie cesse.",
                      "An hour later, the rain stops.",
                      "Dix minutes plus tard, le feu prend."):
            self.assertEqual(self.kinds(draft), [], draft)

    def test_dialogue_is_not_narration(self):
        """A character speaking of tomorrow does not move the clock."""
        self.assertEqual(self.kinds("« Je partirai le lendemain », dit-il."), [])
        self.assertEqual(self.kinds('"We leave the next morning," he says.'), [])
        self.assertEqual(self.kinds("— Trois jours plus tard, peut-être."), [])

    def test_dialogue_still_closes_the_sentence_before_an_ellipse(self):
        """Masking must not swallow the boundary the ellipse anchor relies on."""
        self.assertEqual(
            self.kinds("Il dit : « Reviens demain. » Trois heures plus tard, "
                       "la forge est froide."), ["ellipse"])

    def test_compound_and_abbreviated_durations(self):
        for draft in ("Une heure et demie plus tard, la pluie cesse.",
                      "Deux jours et demi plus tard, il revient.",
                      "2h plus tard, le feu est mort."):
            self.assertIn("ellipse", self.kinds(draft), draft)

    def test_lore_and_distance_are_not_ellipses(self):
        """A duration mid-sentence is backstory or a distance — it moves no clock."""
        for draft in ("Cinq ans après la chute de l'empire, la ville reste en ruines. "
                      "Le forgeron lève les yeux.",
                      "Le village a brûlé deux ans après la guerre.",
                      "À quelques jours de marche d'ici, après le col, se dresse la tour."):
            self.assertEqual(self.kinds(draft), [], draft)

    def test_travel_markers(self):
        self.assertEqual(self.kinds("Vous arrivez au moulin."), ["travel"])
        self.assertEqual(self.kinds("You reach the mill."), ["travel"])
        self.assertEqual(self.kinds("De retour au camp, le feu est mort."), ["travel"])
        self.assertEqual(self.kinds("Vous arrivez à la clairière."), ["travel"])

    def test_arriver_a_plus_infinitif_is_not_travel(self):
        """« vous arrivez à ouvrir » = you manage to — the PC has not moved."""
        draft = ("Vous arrivez à ouvrir la porte. À l'intérieur, vous arrivez à "
                 "distinguer une silhouette.")
        self.assertEqual(self.kinds(draft), [])
        self.assertEqual(T.evaluate(T.detect_moments(draft), False), [])

    def test_unquantified_later_is_a_documented_miss(self):
        """No quantity, no bar to compare it to: let through on purpose, not a bug."""
        self.assertEqual(self.kinds("Plus tard, il revient."), [])
        self.assertEqual(self.kinds("Later, he comes back."), [])

    def test_a_still_scene_has_no_moment(self):
        self.assertEqual(self.kinds(DRAFT_STILL), [])

    def test_excerpt_keeps_the_original_accents(self):
        moments = T.detect_moments("Trois heures plus tard, la forêt se tait.")
        self.assertIn("forêt", moments[0]["excerpt"])


class TestEvaluate(unittest.TestCase):
    """Pure rule evaluation, no state, no I/O."""

    def rules(self, draft, granted):
        return [v["regle"] for v in T.evaluate(T.detect_moments(draft), granted)]

    def test_ellipse_without_grant_is_turn_02(self):
        self.assertIn("TURN-02", self.rules(DRAFT_ONE_ELLIPSE, False))

    def test_two_moments_without_grant_is_turn_01(self):
        self.assertIn("TURN-01", self.rules(DRAFT_S23_BIVOUAC, False))

    def test_one_travel_without_grant_passes(self):
        self.assertEqual(self.rules("Vous arrivez au moulin. Le meunier lève les yeux.",
                                    False), [])

    def test_grant_allows_one_ellipse_and_the_travel_it_covers(self):
        self.assertEqual(self.rules(DRAFT_ONE_ELLIPSE, True), [])
        self.assertEqual(
            self.rules("Trois heures plus tard, vous arrivez au moulin.", True), [])

    def test_grant_does_not_allow_two_ellipses(self):
        """S34 — the fast-forward lands on ONE focal event, then stops (TURN-06)."""
        self.assertIn("TURN-06", self.rules(DRAFT_TWO_ELLIPSES, True))
        self.assertIn("TURN-06", self.rules(DRAFT_S23_BIVOUAC, True))

    def test_feedback_names_the_rule_and_both_moments(self):
        violations = T.evaluate(T.detect_moments(DRAFT_S23_BIVOUAC), False)
        fb = T.format_feedback(violations)
        self.assertIn("TURN-02", fb)
        self.assertIn("TURN-01", fb)
        self.assertIn("travel", fb)
        self.assertIn("ellipse", fb)

    def test_one_fault_is_reported_once(self):
        """An ellipse plus the travel it carries is ONE fault, not two numbered items."""
        self.assertEqual(
            self.rules("Trois heures plus tard, vous arrivez au moulin.", False),
            ["TURN-02"])

    def test_turn_01_excerpt_carries_both_moments(self):
        """Both excerpts must survive the 160-char cap, not just the first."""
        v = [x for x in T.evaluate(T.detect_moments(DRAFT_S23_BIVOUAC), False)
             if x["regle"] == "TURN-01"][0]
        self.assertIn("1)", v["extrait"])
        self.assertIn("2)", v["extrait"])
        self.assertLessEqual(len(v["extrait"]), 160)


class TestGateAndGrant(unittest.TestCase):
    """The grant: explicit, persisted, consumed once."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.camp = make_campaign(Path(self.tmp.name))

    def tearDown(self):
        self.tmp.cleanup()

    def check(self, draft, declared="", **kw):
        return T.check_narration(self.camp, PAYLOAD, draft, declared, **kw)

    def test_s23_intention_does_not_authorise_the_bivouac(self):
        v = self.check(DRAFT_S23_BIVOUAC, "je vais monter le bivouac")
        self.assertFalse(v["ok"])
        self.assertEqual(v["input"], "intention")
        self.assertIn("TURN-02", [x["regle"] for x in v["violations"]])

    def test_s17_ellipse_without_signal_is_refused(self):
        v = self.check(DRAFT_ONE_ELLIPSE, "Je m'assois près du feu.")
        self.assertFalse(v["ok"])
        self.assertIn("TURN-02", v["feedback"])

    def test_question_is_refused_like_no_signal(self):
        v = self.check(DRAFT_ONE_ELLIPSE, "on avance ?")
        self.assertFalse(v["ok"])
        self.assertEqual(v["input"], "question")

    def test_grant_authorises_then_is_consumed(self):
        first = self.check(DRAFT_ONE_ELLIPSE, "⏩")
        self.assertTrue(first["ok"])
        self.assertTrue(first["grant_consumed"])
        self.assertEqual(first["state"], T.DECISION_STOP)
        second = self.check(DRAFT_ONE_ELLIPSE)
        self.assertFalse(second["ok"], "a consumed grant must not authorise a 2nd turn")

    def test_an_accepted_turn_consumes_an_unused_grant(self):
        self.check(DRAFT_STILL, "⏩")
        self.assertIsNone(T.grant_get(self.camp, PAYLOAD))
        self.assertFalse(self.check(DRAFT_ONE_ELLIPSE)["ok"])

    def test_a_refusal_keeps_the_grant_so_the_rewrite_can_pass(self):
        refused = self.check(DRAFT_TWO_ELLIPSES, "⏩")
        self.assertFalse(refused["ok"])
        self.assertIsNotNone(T.grant_get(self.camp, PAYLOAD))
        self.assertTrue(self.check(DRAFT_ONE_ELLIPSE)["ok"])

    def test_a_new_ordinary_input_expires_a_pending_grant(self):
        T.observe_input(self.camp, PAYLOAD, "⏩")
        T.observe_input(self.camp, PAYLOAD, "Je pose la hache.")
        self.assertIsNone(T.grant_get(self.camp, PAYLOAD))
        self.assertEqual(T.get_state(self.camp, PAYLOAD), T.AWAITING_INPUT)

    def test_silence_holds_the_stop_and_grants_nothing(self):
        self.check(DRAFT_STILL, "Je regarde le feu.")
        obs = T.observe_input(self.camp, PAYLOAD, "")
        self.assertEqual(obs["input"], "silence")
        self.assertEqual(obs["state"], T.DECISION_STOP)
        self.assertFalse(obs["grant"])
        self.assertFalse(self.check(DRAFT_ONE_ELLIPSE)["ok"])

    def test_event_stop_is_recorded_when_declared(self):
        v = self.check(DRAFT_STILL, "Je me tais.", stop=T.EVENT_STOP)
        self.assertTrue(v["ok"])
        self.assertEqual(T.get_state(self.camp, PAYLOAD), T.EVENT_STOP)

    def test_state_and_grant_are_persisted_in_the_banquier_snapshot(self):
        T.observe_input(self.camp, PAYLOAD, "⏩")
        snap = json.loads((self.camp / ".banquier" / "snap-gate.json")
                          .read_text(encoding="utf-8"))
        self.assertEqual(snap[T.K_STATE], T.FF_GRANTED)
        self.assertTrue(snap[T.K_GRANT]["armed"])
        self.assertEqual(snap[T.K_GRANT]["signal"], "⏩")

    def test_state_survives_a_fresh_process_view(self):
        T.observe_input(self.camp, PAYLOAD, "avance rapide")
        self.assertEqual(T.get_state(self.camp, PAYLOAD), T.FF_GRANTED)
        T.reset(self.camp, PAYLOAD)
        self.assertEqual(T.get_state(self.camp, PAYLOAD), T.AWAITING_INPUT)
        self.assertIsNone(T.grant_get(self.camp, PAYLOAD))

    def test_stacked_pc_actions_are_not_this_gate_s_business(self):
        """S14 (eat / get up / lie down) is AGENCY-03 — do not claim to catch it here."""
        draft = "Vous mangez le saucisson, vous vous levez, vous vous recouchez."
        self.assertTrue(self.check(draft, "Je mange.")["ok"])


class TestNeverLoops(unittest.TestCase):
    """The house contract: a gate that cannot release is a gate that kills a campaign."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.camp = make_campaign(Path(self.tmp.name))

    def tearDown(self):
        self.tmp.cleanup()

    def test_the_budget_forces_the_narration_through(self):
        first = T.check_narration(self.camp, PAYLOAD, DRAFT_ONE_ELLIPSE, "Je taille le bois.")
        self.assertFalse(first["ok"])
        self.assertEqual(first["attempts"], 1)
        self.assertNotIn("forced", first)

        forced = T.check_narration(self.camp, PAYLOAD, DRAFT_ONE_ELLIPSE)
        self.assertTrue(forced["ok"], "the gate must never refuse forever")
        self.assertEqual(forced["forced"], first["max_attempts"])
        self.assertTrue(forced["violations"], "the violations are kept, not erased")

    def test_the_forced_feedback_is_re_injected_next_turn(self):
        for _ in range(3):
            T.check_narration(self.camp, PAYLOAD, DRAFT_ONE_ELLIPSE)
        self.assertIn("TURN-02", L.take_pending(self.camp, PAYLOAD))

    def test_refusals_reach_the_scoreboard(self):
        T.check_narration(self.camp, PAYLOAD, DRAFT_ONE_ELLIPSE, "Je taille le bois.")
        row = L.load_scoreboard(self.camp)[T.SCOREBOARD_KEY]
        self.assertEqual(row["par_regle"]["TURN-02"], 1)
        self.assertEqual(row["infractions_conduite"], 1)

    def test_an_accepted_narration_clears_the_budget(self):
        T.check_narration(self.camp, PAYLOAD, DRAFT_ONE_ELLIPSE, "Je taille le bois.")
        T.check_narration(self.camp, PAYLOAD, DRAFT_STILL)
        self.assertEqual(T.attempts_get(self.camp, PAYLOAD), 0)
        self.assertFalse(T.check_narration(self.camp, PAYLOAD, DRAFT_ONE_ELLIPSE)["ok"])

    def test_the_budget_is_not_the_checkpoint_s(self):
        """Sharing `checkpoint_attempts` would let one gate reset the other's budget."""
        L.attempts_inc(self.camp, PAYLOAD)
        T.check_narration(self.camp, PAYLOAD, DRAFT_STILL)
        self.assertEqual(L.attempts_get(self.camp, PAYLOAD), 1)

    def test_the_budget_is_configurable(self):
        camp = make_campaign(Path(self.tmp.name) / "wide",
                             hooks_cfg={"turn_gate_max_tentatives": 4})
        for i in range(3):
            self.assertFalse(T.check_narration(camp, PAYLOAD, DRAFT_ONE_ELLIPSE)["ok"], i)
        self.assertTrue(T.check_narration(camp, PAYLOAD, DRAFT_ONE_ELLIPSE)["ok"])


class TestEscapeHatch(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.tmp.cleanup()
        os.environ.pop("MGM_TURN_GATE", None)

    def test_env_var_unblocks_a_live_campaign(self):
        camp = make_campaign(Path(self.tmp.name))
        os.environ["MGM_TURN_GATE"] = "0"
        v = T.check_narration(camp, PAYLOAD, DRAFT_S23_BIVOUAC, "Je taille le bois.")
        self.assertTrue(v["ok"])
        self.assertIn("_skipped", v)

    def test_world_json_overrides_the_env_default(self):
        camp = make_campaign(Path(self.tmp.name), hooks_cfg={"turn_gate": False})
        self.assertFalse(T.gate_enabled(json.loads(
            (camp / "world.json").read_text(encoding="utf-8"))))
        self.assertTrue(T.check_narration(camp, PAYLOAD, DRAFT_ONE_ELLIPSE)["ok"])

    def test_gate_is_on_by_default(self):
        camp = make_campaign(Path(self.tmp.name))
        self.assertTrue(T.gate_enabled(json.loads(
            (camp / "world.json").read_text(encoding="utf-8"))))


class TestCLI(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.camp = make_campaign(Path(self.tmp.name))

    def tearDown(self):
        self.tmp.cleanup()

    def run_cli(self, args, stdin_text="", env_extra=None):
        env = dict(os.environ)
        env.pop("MGM_TURN_GATE", None)
        env.update(env_extra or {})
        proc = subprocess.run(
            [sys.executable, str(HOOKS_DIR / "turn_state.py")] + args,
            input=stdin_text, capture_output=True, text=True, timeout=30,
            cwd=str(self.camp), env=env)
        return proc.stdout, proc.returncode

    def test_check_refuses_with_exit_1_and_names_the_rule(self):
        out, rc = self.run_cli(["check", "--declared", "Je taille le bois."],
                               DRAFT_ONE_ELLIPSE)
        self.assertEqual(rc, 1)
        self.assertIn("TURN-02", out)

    def test_signal_then_check_delivers_with_exit_0(self):
        out, rc = self.run_cli(["signal", "--message", "⏩"])
        self.assertEqual(rc, 0)
        self.assertEqual(json.loads(out)["state"], T.FF_GRANTED)
        out, rc = self.run_cli(["check"], DRAFT_ONE_ELLIPSE)
        self.assertEqual(rc, 0)
        self.assertIn("consumed", out)
        _, rc = self.run_cli(["check"], DRAFT_ONE_ELLIPSE)
        self.assertEqual(rc, 1)

    def test_state_and_reset(self):
        self.run_cli(["signal", "--message", "avance rapide"])
        out, _ = self.run_cli(["state"])
        self.assertTrue(json.loads(out)["grant"]["armed"])
        self.run_cli(["reset"])
        out, _ = self.run_cli(["state"])
        self.assertIsNone(json.loads(out)["grant"])

    def test_json_verdict_is_machine_readable(self):
        out, rc = self.run_cli(["check", "--json"], DRAFT_S23_BIVOUAC)
        verdict = json.loads(out)
        self.assertEqual(rc, 1)
        self.assertFalse(verdict["ok"])
        self.assertEqual(len(verdict["moments"]), 4)
        self.assertEqual(verdict["violations"][0]["domaine"], "conduite")

    def test_env_escape_hatch_from_the_cli(self):
        out, rc = self.run_cli(["check"], DRAFT_ONE_ELLIPSE,
                               env_extra={"MGM_TURN_GATE": "0"})
        self.assertEqual(rc, 0)
        self.assertIn("gate off", out)

    def test_unreadable_draft_never_breaks_the_session(self):
        out, rc = self.run_cli(["check", "--file", "does-not-exist.txt"])
        self.assertEqual(rc, 0)


if __name__ == "__main__":
    unittest.main()
