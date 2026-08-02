#!/usr/bin/env python3
"""
test_campagnes_livrees.py — the two SHIPPED campaigns are a contract.

Run from `scripts/`:
    python3 -m unittest discover -s tests

`_template` is what every new campaign is copied from and `example-mistfall` is
what people read to learn the format: a defect there is reproduced into every
table. Two regressions caught here:

  * the `tts` feature axis was missing from both `meta.features` while the
    engine declares SIX axes (feature_toggle._FEATURES), and a comment still
    said "Five";
  * the in-game clock was duplicated under `meta.time.tracking` while every
    reader (clock.py, hooks/_lib.py) uses `rules.time.tracking` — two clocks,
    one of them silently ignored and free to drift.
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent.parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import feature_toggle as FT  # noqa: E402

CAMPAGNES_DIR = SCRIPTS_DIR.parents[3] / "data" / "mygamemaster" / "campaigns"
LIVREES = ("_template", "example-mistfall")


def _monde(nom: str) -> dict:
    return json.loads((CAMPAGNES_DIR / nom / "world.json").read_text(encoding="utf-8"))


@unittest.skipUnless(CAMPAGNES_DIR.is_dir(), "shipped campaigns not present")
class TestFeatures(unittest.TestCase):

    def test_les_six_axes_sont_declares(self):
        for nom in LIVREES:
            with self.subTest(campagne=nom):
                features = _monde(nom)["meta"]["features"]
                for axe in FT._FEATURES:
                    self.assertIn(axe, features,
                                  f"{nom}: feature axis '{axe}' missing from meta.features")

    def test_tts_est_present_et_actif(self):
        for nom in LIVREES:
            with self.subTest(campagne=nom):
                self.assertIs(_monde(nom)["meta"]["features"].get("tts"), True)

    def test_aucun_axe_inconnu(self):
        for nom in LIVREES:
            with self.subTest(campagne=nom):
                axes = {k for k in _monde(nom)["meta"]["features"] if not k.startswith("_")}
                self.assertEqual(axes - set(FT._FEATURES), set())

    def test_la_voix_auto_est_documentee_comme_opt_in(self):
        """`tts: true` must not read as "the voice speaks by itself".

        The axis gives `!raconte`; the per-turn automatic voice is
        meta.hooks.tts_auto and it ships false (docs/10-field-report.md). A
        template that does not say so reproduces the confusion into every table."""
        meta = _monde("_template")["meta"]
        self.assertIs(meta.get("hooks", {}).get("tts_auto"), False)
        self.assertIn("tts_auto", meta["features"].get("_schema", ""))

    def test_le_commentaire_ne_dit_plus_cinq(self):
        for nom in LIVREES:
            with self.subTest(campagne=nom):
                schema = _monde(nom)["meta"]["features"].get("_schema", "")
                self.assertNotIn("Five", schema)
                self.assertIn("Six", schema)


@unittest.skipUnless(CAMPAGNES_DIR.is_dir(), "shipped campaigns not present")
class TestHorlogeUnique(unittest.TestCase):
    """One clock, at the path the code actually reads."""

    def test_tracking_est_sous_rules_time(self):
        for nom in LIVREES:
            with self.subTest(campagne=nom):
                suivi = _monde(nom)["rules"]["time"]["tracking"]
                self.assertIn("current_day", suivi)
                self.assertIn("current_hour", suivi)

    def test_pas_de_second_tracking_sous_meta_time(self):
        for nom in LIVREES:
            with self.subTest(campagne=nom):
                self.assertNotIn("tracking", _monde(nom)["meta"]["time"],
                                 f"{nom}: duplicate clock under meta.time — readers "
                                 "use rules.time.tracking, this copy would drift unseen")

    def test_les_lecteurs_reels_trouvent_lhorloge(self):
        """clock.py and hooks/_lib.py both navigate rules.time.tracking — the
        shipped data must be readable through that exact path, not another."""
        chemin_lu = lambda m: (m.get("rules") or {}).get("time", {}).get("tracking", {})  # noqa: E731
        for nom in LIVREES:
            with self.subTest(campagne=nom):
                suivi = chemin_lu(_monde(nom))
                self.assertIsInstance(suivi.get("current_day"), int)
                self.assertTrue(str(suivi.get("current_hour") or "").strip())


@unittest.skipUnless(CAMPAGNES_DIR.is_dir(), "shipped campaigns not present")
class TestExempleConforme(unittest.TestCase):
    """example-mistfall must satisfy world.schema.json — it is the reference
    people copy from."""

    def test_world_json_sans_ecart_de_schema(self):
        import validate_schema as VS
        schema = VS.charger_schema("world")
        for nom in LIVREES:
            with self.subTest(campagne=nom):
                ecarts = VS.valider(_monde(nom), schema, schema)
                self.assertEqual(ecarts, [], f"{nom}: {ecarts}")

    def test_factions_ont_attitude_et_objectifs(self):
        for f in _monde("example-mistfall")["global_state"]["factions"]:
            with self.subTest(faction=f.get("name")):
                self.assertTrue(f.get("short_term_goals"))
                self.assertTrue(f.get("long_term_goals"))
                self.assertTrue(f.get("attitude_actuelle"))

    def test_chaque_faction_a_une_entree_horloge_avec_actions_en_cours(self):
        monde = _monde("example-mistfall")
        noms = {f["name"] for f in monde["global_state"]["factions"]}
        horloge = monde["global_state"]["faction_actions_horloge"]["actions"]
        self.assertEqual({e["faction"] for e in horloge}, noms)
        for entree in horloge:
            with self.subTest(faction=entree["faction"]):
                actions = entree.get("actions_en_cours")
                self.assertTrue(actions, "each faction needs at least one live action")
                for a in actions:
                    self.assertTrue(a.get("action"))
                    self.assertTrue(a.get("consequence"))
                    self.assertIsInstance(a.get("echeance"), dict)

    def test_echeances_epinglees_ne_sont_pas_deja_depassees(self):
        """A shipped example whose deadlines are overdue on day 1 teaches the
        wrong thing and makes check_session fail out of the box."""
        import check_session as CS
        monde = _monde("example-mistfall")
        jour = monde["rules"]["time"]["tracking"]["current_day"]
        for entree in monde["global_state"]["faction_actions_horloge"]["actions"]:
            for a in entree["actions_en_cours"]:
                infos = CS.echeance_infos(a["echeance"])
                with self.subTest(action=a["action"][:40]):
                    self.assertIsNotNone(infos["due"], "deadline must be machine-parsable")
                    self.assertGreaterEqual(infos["due"], jour)

    def test_module_actif_a_ses_donnees(self):
        """load_campaign readiness: weather was ON without rules.weather."""
        import load_campaign as LC
        rapport = LC.analyser(CAMPAGNES_DIR / "example-mistfall")
        self.assertEqual(rapport["donnees_manquantes"], [])
        self.assertTrue(rapport["ok"], rapport)


@unittest.skipUnless(CAMPAGNES_DIR.is_dir(), "shipped campaigns not present")
class TestRoutesResolvables(unittest.TestCase):
    """Route labels that resolve to nothing produce a 0-edge map in silence."""

    def test_les_labels_de_routes_resolvent_tous(self):
        import worldlib as W
        monde = _monde("example-mistfall")
        index = W.index_labels(monde)
        deplacements = monde["rules"]["time"]["movements"]
        labels = set()
        for cle, valeur in deplacements.items():
            if cle.startswith("depuis_") and cle.endswith("_vers") and isinstance(valeur, dict):
                labels.add(cle[len("depuis_"):-len("_vers")])
                labels.update(valeur.keys())
        self.assertTrue(labels)
        for label in sorted(labels):
            with self.subTest(label=label):
                self.assertIsNotNone(W._label_vers_id(label, index),
                                     f"route label '{label}' resolves to no location id")


if __name__ == "__main__":
    unittest.main()
