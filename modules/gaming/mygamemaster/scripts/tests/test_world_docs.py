#!/usr/bin/env python3
"""
test_world_docs.py — the SEASON extractor (G4) and its boundaries.

Run from `scripts/`:
    python3 -m unittest discover -s tests

What is worth asserting here is the day→phase resolution, because it is the only
arithmetic in the block and every interval in `table_de_lecture` is INCLUSIVE at
both ends: an off-by-one puts the world one phase ahead of itself, which is the
exact failure `regle_anti_bascule` exists to prevent. The rest of the file covers
the strict fail-open contract — this code runs on the path of every turn.
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

import world_docs as WD  # noqa: E402

CAMPAGNES_DIR = SCRIPTS_DIR.parents[3] / "data" / "mygamemaster" / "campaigns"
NOUVELLE_MARCHE = CAMPAGNES_DIR / "nouvelle-marche"

TABLE = {"J1-J8": "phase:une", "J9-J17": "phase:deux", "J18-J365": "phase:trois"}

SAISONS = {
    "table_de_lecture": TABLE,
    "phases": [
        {"id": "phase:une", "nom": "La première", "lumiere": "lever ~06h07",
         "sol_et_eau": "Sol sec en surface.", "vegetation": "Feuillage vert-jaune.",
         "faune": "Gibier actif.", "phase_suivante": "phase:deux"},
        {"id": "phase:deux", "nom": "La deuxième", "lumiere": "lever ~06h30",
         "sol_et_eau": "Gel au matin.", "vegetation": "Fougères couchées.",
         "phase_suivante": "phase:trois"},
        {"id": "phase:trois", "nom": "La troisième", "lumiere": "lever ~07h00",
         "phase_suivante": "phase:une (cycle suivant)"},
    ],
    "regle_anti_bascule": {"principe": "Le monde ne franchit jamais deux phases d'un coup."},
}


def _campagne(saisons=SAISONS, monde=None) -> Path:
    camp = Path(tempfile.mkdtemp(prefix="mgm-wd-"))
    if saisons is not None:
        (camp / "saisons.json").write_text(json.dumps(saisons, ensure_ascii=False),
                                           encoding="utf-8")
    (camp / "world.json").write_text(json.dumps(monde or {}, ensure_ascii=False),
                                     encoding="utf-8")
    return camp


class TestResolutionPhase(unittest.TestCase):

    def test_jour_au_milieu_dun_intervalle(self):
        self.assertEqual(WD.resoudre_phase(TABLE, 12), ("phase:deux", 9, 17))

    def test_bornes_inclusives(self):
        for jour, attendu in ((1, "phase:une"), (8, "phase:une"),
                              (9, "phase:deux"), (17, "phase:deux"),
                              (18, "phase:trois"), (365, "phase:trois")):
            with self.subTest(jour=jour):
                self.assertEqual(WD.resoudre_phase(TABLE, jour)[0], attendu)

    def test_le_cycle_boucle_a_366(self):
        self.assertEqual(WD.resoudre_phase(TABLE, 366), WD.resoudre_phase(TABLE, 1))
        self.assertEqual(WD.resoudre_phase(TABLE, 731), WD.resoudre_phase(TABLE, 1))

    def test_jour_inutilisable(self):
        for jour in (0, -3, None, "", "lundi", [], {}):
            with self.subTest(jour=jour):
                self.assertIsNone(WD.resoudre_phase(TABLE, jour))

    def test_intervalle_mal_forme_est_ignore_pas_fatal(self):
        table = {"pas un intervalle": "phase:zero", "J1-J8": "phase:une"}
        self.assertEqual(WD.resoudre_phase(table, 4)[0], "phase:une")

    def test_jour_hors_de_toute_plage(self):
        self.assertIsNone(WD.resoudre_phase({"J1-J8": "phase:une"}, 40))


class TestBlocSaison(unittest.TestCase):

    def test_le_bloc_nomme_la_phase_et_ses_sens(self):
        bloc = WD.season_block(_campagne(), 4, "fr")
        self.assertIn("🍂 SAISON J4 — La première (phase:une)", bloc)
        self.assertIn("lumière : lever ~06h07", bloc)
        self.assertIn("sol/eau : Sol sec en surface.", bloc)
        self.assertIn("végétation : Feuillage vert-jaune.", bloc)

    def test_le_bloc_annonce_la_bascule_et_son_jour(self):
        self.assertIn("→ bascule vers phase:deux à J9 (dans 5 j).",
                      WD.season_block(_campagne(), 4, "fr"))

    def test_la_regle_anti_bascule_narrive_quau_bord(self):
        self.assertNotIn("transition imminente", WD.season_block(_campagne(), 6, "fr"))
        for jour in (7, 8):
            with self.subTest(jour=jour):
                bloc = WD.season_block(_campagne(), jour, "fr")
                self.assertIn("transition imminente", bloc)
                self.assertIn("ne franchit jamais deux phases", bloc)

    def test_le_jour_affiche_reste_absolu_apres_un_cycle(self):
        bloc = WD.season_block(_campagne(), 370, "fr")
        self.assertIn("🍂 SAISON J370 — La première", bloc)
        self.assertIn("à J374", bloc)

    def test_la_parenthese_du_cycle_suivant_nest_pas_un_id(self):
        self.assertIn("→ bascule vers phase:une à J366", WD.season_block(_campagne(), 365, "fr"))

    def test_les_champs_longs_sont_condenses(self):
        saisons = json.loads(json.dumps(SAISONS))
        saisons["phases"][0]["sol_et_eau"] = "mot " * 200
        bloc = WD.season_block(_campagne(saisons), 4, "fr")
        self.assertLess(len(bloc), 600)
        self.assertIn("…", bloc)

    def test_le_bloc_reste_court(self):
        self.assertLess(len(WD.season_block(_campagne(), 4, "fr")), 400)

    def test_locale_par_defaut_anglaise(self):
        self.assertIn("🍂 SEASON J4", WD.season_block(_campagne(), 4))


class TestFailOpen(unittest.TestCase):

    def test_pas_de_saisons_json(self):
        self.assertEqual(WD.season_block(_campagne(saisons=None), 4, "fr"), "")

    def test_saisons_json_casse(self):
        camp = _campagne()
        (camp / "saisons.json").write_text("{ not json", encoding="utf-8")
        self.assertEqual(WD.season_block(camp, 4, "fr"), "")

    def test_table_absente(self):
        self.assertEqual(WD.season_block(_campagne({"phases": []}), 4, "fr"), "")

    def test_phase_declaree_mais_sans_fiche(self):
        saisons = {"table_de_lecture": TABLE, "phases": []}
        self.assertEqual(WD.season_block(_campagne(saisons), 4, "fr"), "")

    def test_jour_inutilisable_ne_leve_pas(self):
        for jour in (None, 0, "lundi"):
            with self.subTest(jour=jour):
                self.assertEqual(WD.season_block(_campagne(), jour, "fr"), "")


class TestCli(unittest.TestCase):

    def _run(self, *args):
        return subprocess.run([sys.executable, str(SCRIPTS_DIR / "world_docs.py")] + list(args),
                              capture_output=True, text=True, timeout=20)

    def test_jour_explicite(self):
        r = self._run("season", str(_campagne()), "4", "--lang", "fr")
        self.assertEqual(r.returncode, 0)
        self.assertIn("🍂 SAISON J4", r.stdout)

    def test_jour_par_defaut_lu_dans_world_json(self):
        camp = _campagne(monde={"rules": {"time": {"tracking": {"current_day": 12}}},
                                "meta": {"langue": "fr"}})
        r = self._run("season", str(camp))
        self.assertEqual(r.returncode, 0)
        self.assertIn("🍂 SAISON J12 — La deuxième", r.stdout)

    def test_campagne_absente_code_2(self):
        r = self._run("season", "/nowhere/at/all", "4")
        self.assertEqual(r.returncode, 2)

    def test_document_absent_code_0_sortie_vide(self):
        r = self._run("season", str(_campagne(saisons=None)), "4")
        self.assertEqual(r.returncode, 0)
        self.assertEqual(r.stdout.strip(), "")


@unittest.skipUnless((NOUVELLE_MARCHE / "saisons.json").is_file(),
                     "campaign nouvelle-marche not present")
class TestCampagneReelle(unittest.TestCase):
    """Read-only checks on the document G4 was written against."""

    def test_j251_tombe_dans_lapproche_de_lete(self):
        bloc = WD.season_block(NOUVELLE_MARCHE, 251, "fr")
        self.assertIn("phase:approche-de-lete", bloc)

    def test_le_jour_courant_de_la_campagne_resout(self):
        monde = json.loads((NOUVELLE_MARCHE / "world.json").read_text(encoding="utf-8"))
        jour = monde["rules"]["time"]["tracking"]["current_day"]
        self.assertIn("🍂 SAISON J%s" % jour, WD.season_block(NOUVELLE_MARCHE, jour, "fr"))

    def test_les_365_jours_du_cycle_resolvent(self):
        doc = json.loads((NOUVELLE_MARCHE / "saisons.json").read_text(encoding="utf-8"))
        table = doc["table_de_lecture"]
        manquants = [j for j in range(1, 366) if WD.resoudre_phase(table, j) is None]
        self.assertEqual(manquants, [], "days with no phase: %s" % manquants[:10])


if __name__ == "__main__":
    unittest.main()
