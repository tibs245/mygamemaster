#!/usr/bin/env python3
"""
test_clock.py — the clock has ONE writer, and it fails loud (TIME-01/03/04).

Run from `scripts/`:
    python3 -m unittest discover -s tests

Three things are pinned here:

  * the time unit is READABLE FROM THE CODE. It used to exist only in
    `world.json > meta.time`; a campaign that omitted the block made the whole
    scale unguessable. `meta.time` is now a validated override.
  * the temporal sources are compared AGAINST EACH OTHER. The corpus campaign
    ran 51 days out of sync for four sessions because each writer was internally
    consistent and nobody compared them.
  * the close REFUSES a divergent clock, and says exactly what diverged — with
    an escape hatch, because a live table must stay closable.

The `fixtures/corpus_horloge_divergente/` campaign is that pathology distilled:
declared clock day 58, events.json day 63, living-world clock day 109.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent.parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import clock as C            # noqa: E402
import close_session as CS   # noqa: E402
import worldlib as W         # noqa: E402

CORPUS = Path(__file__).resolve().parent / "fixtures" / "corpus_horloge_divergente"


def _monde(**meta_time) -> dict:
    monde = {"meta": {"name": "T"}, "rules": {}, "global_state": {}}
    if meta_time:
        monde["meta"]["time"] = meta_time
    return monde


# ════════════════════════════════════════════════════════════════════════════
#  The time unit lives in the code (TIME-01)
# ════════════════════════════════════════════════════════════════════════════

class TestConfigTemps(unittest.TestCase):

    def test_constantes_alignees_avec_worldlib(self):
        """Two modules converting UT↔days on different constants IS the drift."""
        self.assertEqual(C.MINUTES_PAR_UT, W.MINUTES_PAR_UT)
        self.assertEqual(C.UT_PAR_HEURE, W.UT_PAR_HEURE)
        self.assertEqual(C.UT_PAR_JOUR, W.UT_PAR_JOUR)
        self.assertEqual(C.UT_PAR_JOUR * C.MINUTES_PAR_UT, C.MINUTES_PAR_JOUR)

    def test_campagne_sans_meta_time_reste_lisible(self):
        cfg = C.config_temps(_monde())
        self.assertEqual(cfg["ut_par_jour"], 144)
        self.assertEqual(cfg["minutes_par_ut"], 10)
        self.assertEqual(cfg["source"], "code")
        self.assertEqual(cfg["anomalies"], [])

    def test_surcharge_valide_est_honoree(self):
        cfg = C.config_temps(_monde(units_per_day=48, time_unit_minutes=30))
        self.assertEqual(cfg["ut_par_jour"], 48)
        self.assertEqual(cfg["minutes_par_ut"], 30)
        self.assertEqual(cfg["source"], "world.json>meta.time")
        self.assertEqual(cfg["anomalies"], [])

    def test_surcharge_invalide_est_rejetee_et_signalee(self):
        """`"144"` or 0 must not propagate: it crashes or silently zeroes the scale."""
        for valeur in ("144", 0, -3, 1.5, True, None):
            with self.subTest(valeur=valeur):
                cfg = C.config_temps(_monde(units_per_day=valeur))
                self.assertEqual(cfg["ut_par_jour"], C.UT_PAR_JOUR)
                self.assertEqual(cfg["source"], "code")
                self.assertEqual([a["code"] for a in cfg["anomalies"]],
                                 ["config_temps_invalide"])

    def test_journee_qui_ne_tombe_pas_juste_est_signalee(self):
        cfg = C.config_temps(_monde(units_per_day=100, time_unit_minutes=10))
        self.assertEqual(cfg["ut_par_jour"], 100)
        self.assertIn("config_temps_incoherente", [a["code"] for a in cfg["anomalies"]])

    def test_meta_time_malforme_ne_casse_rien(self):
        for monde in ({}, {"meta": None}, {"meta": {"time": "UT"}}, "nope"):
            with self.subTest(monde=monde):
                self.assertEqual(C.config_temps(monde)["ut_par_jour"], C.UT_PAR_JOUR)


# ════════════════════════════════════════════════════════════════════════════
#  Drift between the temporal sources (TIME-03)
# ════════════════════════════════════════════════════════════════════════════

class TestSourcesTemporelles(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.camp = Path(self.tmp.name) / "camp"
        self.camp.mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    def _ecrire(self, nom: str, data: dict):
        (self.camp / nom).parent.mkdir(parents=True, exist_ok=True)
        (self.camp / nom).write_text(json.dumps(data), encoding="utf-8")

    def _monde_jour(self, jour: int) -> dict:
        return {"meta": {"name": "T"},
                "rules": {"time": {"tracking": {"current_day": jour}}},
                "global_state": {"timeline": f"Day {jour}: nothing yet."}}

    def test_sources_concordantes_pas_de_derive(self):
        monde = self._monde_jour(7)
        self._ecrire("world.json", monde)
        rap = C.detecter_derive(self.camp, monde)
        self.assertEqual(rap["ecart"], 0)
        self.assertFalse(rap["derive"])
        self.assertEqual(rap["anomalies"], [])

    def test_source_absente_n_est_pas_une_source_d_accord(self):
        """A campaign with a single clock must not read as 'three clocks agree'."""
        monde = {"meta": {"name": "T"},
                 "rules": {"time": {"tracking": {"current_day": 12}}},
                 "global_state": {}}
        self._ecrire("world.json", monde)
        rap = C.detecter_derive(self.camp, monde)
        self.assertEqual([s["id"] for s in rap["sources"]],
                         ["rules.time.tracking.current_day"])

    def test_jour_narratif_reconnait_les_deux_langues(self):
        """Matching only "Jour N" made this source silently empty on an EN campaign."""
        monde = {"meta": {}, "global_state": {"timeline": "Day 31 — the thaw."}}
        self._ecrire("world.json", monde)
        self.assertEqual(C.jour_max_narratif(self.camp, monde), 31)
        monde_fr = {"meta": {}, "global_state": {"timeline": "Jour 31 — le dégel."}}
        self.assertEqual(C.jour_max_narratif(self.camp, monde_fr), 31)

    def test_evenement_programme_futur_n_avance_pas_l_horloge(self):
        """A SCHEDULED event carries a future T; counting it makes the world
        clock run ahead of the fiction on its own."""
        monde = self._monde_jour(7)
        self._ecrire("world.json", monde)
        self._ecrire("evenements_programmes.json", {"events": [
            {"id": "evt:a", "T": 864, "statut": "resolu"},
            {"id": "evt:b", "T": 100000, "statut": "planifie"},
        ]})
        rap = C.detecter_derive(self.camp, monde)
        vivant = next(s for s in rap["sources"]
                      if s["id"] == "evenements_programmes.json")
        self.assertEqual(vivant["jour"], 7)
        self.assertFalse(rap["derive"])

    def test_evenement_resolu_date_dans_le_futur_est_signale(self):
        monde = self._monde_jour(7)
        self._ecrire("world.json", monde)
        self._ecrire("evenements_programmes.json", {"events": [
            {"id": "evt:futur", "T": 20 * 144, "statut": "resolu"},
        ]})
        rap = C.detecter_derive(self.camp, monde)
        self.assertIn("evenement_resolu_dans_le_futur",
                      [a["code"] for a in rap["anomalies"]])

    def test_echeance_en_chaine_libre_est_signalee(self):
        monde = self._monde_jour(7)
        monde["global_state"]["faction_actions_horloge"] = {"actions": [
            {"faction": "F", "actions_en_cours": [
                {"action": "A", "echeance": "soon-ish"}]}]}
        self._ecrire("world.json", monde)
        rap = C.detecter_derive(self.camp, monde)
        self.assertIn("echeance_non_datable", [a["code"] for a in rap["anomalies"]])

    def test_tolerance_configurable(self):
        monde = self._monde_jour(7)
        monde["global_state"]["timeline"] = "Day 10: three days later."
        self._ecrire("world.json", monde)
        self.assertTrue(C.detecter_derive(self.camp, monde)["derive"])
        self.assertFalse(C.detecter_derive(self.camp, monde, tolerance=5)["derive"])


# ════════════════════════════════════════════════════════════════════════════
#  The corpus pathology (regression)
# ════════════════════════════════════════════════════════════════════════════

class TestCorpusHorlogeDivergente(unittest.TestCase):
    """fixtures/corpus_horloge_divergente — the state that went unnoticed for
    four sessions on the real campaign."""

    def setUp(self):
        self.monde = json.loads((CORPUS / "world.json").read_text(encoding="utf-8"))

    def test_la_derive_de_51_jours_est_detectee(self):
        rap = C.detecter_derive(CORPUS, self.monde)
        self.assertTrue(rap["derive"])
        self.assertEqual(rap["ecart"], 51)
        self.assertEqual({s["id"] for s in rap["sources"]},
                         {"rules.time.tracking.current_day", "events.json",
                          "narratif", "evenements_programmes.json"})

    def test_les_anomalies_du_corpus_sont_toutes_signalees(self):
        codes = [a["code"] for a in C.detecter_derive(CORPUS, self.monde)["anomalies"]]
        self.assertIn("evenement_resolu_dans_le_futur", codes)
        self.assertIn("echeance_non_datable", codes)

    def test_l_unite_reste_lisible_sans_units_per_day(self):
        """The fixture omits units_per_day, like the campaign that produced it."""
        self.assertNotIn("units_per_day", self.monde["meta"]["time"])
        self.assertEqual(C.unites_par_jour(self.monde), 144)

    def test_clock_py_sort_en_echec(self):
        proc = subprocess.run(
            [sys.executable, str(SCRIPTS_DIR / "clock.py"), str(CORPUS), "--drift"],
            capture_output=True, text=True, env={**os.environ,
                                                 C.ENV_ALLOW_DERIVE: ""})
        self.assertEqual(proc.returncode, 1, proc.stdout)
        self.assertIn("DRIFT", proc.stdout)

    def test_l_echappatoire_rend_la_derive_non_fatale(self):
        proc = subprocess.run(
            [sys.executable, str(SCRIPTS_DIR / "clock.py"), str(CORPUS), "--drift"],
            capture_output=True, text=True,
            env={**os.environ, C.ENV_ALLOW_DERIVE: "1"})
        self.assertEqual(proc.returncode, 0, proc.stdout)
        self.assertIn("DRIFT", proc.stdout)          # still reported…
        self.assertIn(C.ENV_ALLOW_DERIVE, proc.stdout)   # …and the override is traced


# ════════════════════════════════════════════════════════════════════════════
#  The close refuses a divergent clock (TIME-03 / TIME-04)
# ════════════════════════════════════════════════════════════════════════════

class TestFermetureRefuseLaDerive(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.camp = Path(self.tmp.name) / "corpus"
        shutil.copytree(CORPUS, self.camp)

    def tearDown(self):
        self.tmp.cleanup()

    def _fermer(self, **env_sup) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, str(SCRIPTS_DIR / "close_session.py"),
             str(self.camp), "--session", "31", "--json"],
            capture_output=True, text=True,
            env={**os.environ, C.ENV_ALLOW_DERIVE: "", **env_sup})

    def _points(self, proc) -> dict:
        rapport = json.loads(proc.stdout)
        return rapport, {p["id"]: p for p in rapport["points"]}

    def test_p5_et_p11_bloquent_la_fermeture(self):
        rapport, points = self._points(self._fermer())
        self.assertFalse(rapport["ok"])
        for pid in ("P5", "P11"):
            with self.subTest(point=pid):
                self.assertFalse(points[pid]["ok"])
                self.assertTrue(points[pid]["bloquant"])
                self.assertTrue(any(pid in b for b in rapport["bloquants"]))

    def test_le_refus_dit_ce_qu_il_faut_resoudre(self):
        _, points = self._points(self._fermer())
        self.assertIn("Send a runner", points["P5"]["detail"])
        self.assertIn("51 day(s)", points["P11"]["detail"])
        self.assertIn("day 109", points["P11"]["detail"])
        self.assertIn(C.ENV_ALLOW_DERIVE, points["P11"]["detail"])

    def test_le_rapport_porte_la_derive_en_machine(self):
        rapport, _ = self._points(self._fermer())
        self.assertEqual(rapport["derive_temporelle"]["ecart"], 51)
        self.assertFalse(rapport["clock_drift_override"])

    def test_l_echappatoire_degrade_en_alerte_et_la_trace(self):
        rapport, points = self._points(self._fermer(**{C.ENV_ALLOW_DERIVE: "1"}))
        self.assertTrue(rapport["clock_drift_override"])
        for pid in ("P5", "P11"):
            with self.subTest(point=pid):
                self.assertFalse(points[pid]["bloquant"])
                self.assertFalse(any(pid in b for b in rapport["bloquants"]))
                self.assertTrue(any(pid in a for a in rapport["alertes"]))
        self.assertTrue(any("OVERRIDE ACTIVE" in a for a in rapport["alertes"]))

    def test_un_rapport_horloge_illisible_bloque(self):
        """TIME-04: a clock we could not read is not a clock we checked."""
        points = CS.check_pipeline(
            self.camp, self.camp / "sessions" / "031.json",
            json.loads((self.camp / "world.json").read_text(encoding="utf-8")),
            {"exit": 0}, {"exit": 2}, {}, False)
        par_id = {p["id"]: p for p in points}
        for pid in ("P5", "P11"):
            with self.subTest(point=pid):
                self.assertFalse(par_id[pid]["ok"])
                self.assertTrue(par_id[pid]["bloquant"])


class TestCampagneSaineResteFermable(unittest.TestCase):
    """Making P5/P11 blocking must not refuse a coherent campaign."""

    def test_les_points_temporels_passent_sur_une_horloge_unique(self):
        with tempfile.TemporaryDirectory() as d:
            camp = Path(d) / "camp"
            shutil.copytree(CORPUS, camp)
            monde = json.loads((camp / "world.json").read_text(encoding="utf-8"))
            monde["rules"]["time"]["tracking"]["current_day"] = 58
            horloge = monde["global_state"]["faction_actions_horloge"]["actions"][0]
            horloge["actions_en_cours"] = [{
                "action": "Hold the ford",
                "consequence": "The valley stays closed.",
                "echeance": {"texte": "in ten days", "unite": "jour",
                             "min": 10, "max": 10, "ancre": 58,
                             "statut": "en_cours"},
            }]
            (camp / "world.json").write_text(json.dumps(monde), encoding="utf-8")
            (camp / "events.json").write_text(json.dumps(
                {"meta": {}, "events": [{"t": 58 * 144 - 1, "label": "x"}]}),
                encoding="utf-8")
            (camp / "evenements_programmes.json").unlink()

            rap = C.analyser(camp, None)
            self.assertFalse(rap["derive"]["derive"], rap["derive"])
            self.assertEqual(rap["derive"]["anomalies"], [])
            self.assertEqual(rap["n_echue"], 0)
            self.assertEqual(C.code_sortie(rap), 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
