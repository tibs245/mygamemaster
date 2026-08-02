#!/usr/bin/env python3
"""
test_build_brief.py — NPC/actor name lookup must survive the FR→EN rename.

Run from `scripts/`:
    python3 -m unittest discover -s tests

Regression under test: readers kept asking for the French key `nom` while the
migrated data carries `name`. Measured effect on a real campaign — `find_pnj`
returned None for EVERY NPC (the engine then invented them), and the `--list`
path raised KeyError. Both forms must now be accepted on READ; `name` stays the
form that gets written.

Also covers the same defect in geo_query (`qui_est_a` result rendering) and
world_tick (actor brief / tick summary), which read dicts whose producers
already emit `name`.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent.parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import build_brief as BB  # noqa: E402

PNJ_EN = [
    {"name": "Elder Mosswick", "titre": "Warden", "localisation_actuelle": "lieu:thornwick/village-hall"},
    {"name": "Petra Dawnhollow", "titre": "Innkeeper"},
]
PNJ_FR = [{"nom": "Elder Mosswick", "titre": "Warden"}]


class TestNomPnj(unittest.TestCase):

    def test_lit_la_forme_anglaise(self):
        self.assertEqual(BB.nom_pnj({"name": "A"}), "A")

    def test_lit_encore_la_forme_francaise(self):
        self.assertEqual(BB.nom_pnj({"nom": "A"}), "A")

    def test_anglais_prioritaire_si_les_deux(self):
        self.assertEqual(BB.nom_pnj({"name": "EN", "nom": "FR"}), "EN")

    def test_defaut_si_aucun_nom(self):
        self.assertEqual(BB.nom_pnj({"titre": "x"}, "UNKNOWN"), "UNKNOWN")

    def test_entree_non_dict_ne_leve_pas(self):
        self.assertEqual(BB.nom_pnj("not a dict", "?"), "?")


class TestFindPnj(unittest.TestCase):
    """The bug that mattered: None for every NPC of a migrated campaign."""

    def test_trouve_sur_donnees_migrees(self):
        trouve = BB.find_pnj(PNJ_EN, "Elder Mosswick")
        self.assertIsNotNone(trouve, "migrated NPCs must be findable")
        self.assertEqual(trouve["name"], "Elder Mosswick")

    def test_trouve_sur_donnees_non_migrees(self):
        self.assertIsNotNone(BB.find_pnj(PNJ_FR, "Elder Mosswick"))

    def test_insensible_a_la_casse_et_aux_espaces(self):
        self.assertIsNotNone(BB.find_pnj(PNJ_EN, "  eLDeR mOSSwick "))

    def test_correspondance_partielle(self):
        trouve = BB.find_pnj(PNJ_EN, "Mosswick")
        self.assertEqual(trouve["name"], "Elder Mosswick")

    def test_inconnu_reste_none(self):
        self.assertIsNone(BB.find_pnj(PNJ_EN, "Wren"))

    def test_nom_vide_ne_matche_pas_tout_le_monde(self):
        self.assertIsNone(BB.find_pnj(PNJ_EN, "   "))


class TestBuildBrief(unittest.TestCase):

    def test_entete_porte_le_nom_migre(self):
        self.assertIn("Elder Mosswick", BB.build_brief(PNJ_EN[0]))

    def test_entete_tolere_la_forme_francaise(self):
        self.assertIn("Elder Mosswick", BB.build_brief(PNJ_FR[0]))

    def test_fiche_sans_nom_ne_leve_pas(self):
        self.assertIn("UNKNOWN", BB.build_brief({"titre": "x"}))

    def test_inventaire_lu_dans_les_deux_formes(self):
        self.assertIn("Cold-Iron Bell", BB.build_brief({"name": "A", "inventory": ["Cold-Iron Bell"]}))
        self.assertIn("Cold-Iron Bell", BB.build_brief({"name": "A", "inventaire": ["Cold-Iron Bell"]}))


class TestListePnj(unittest.TestCase):
    """Both accepted containers, so `--list` never silently shows nothing."""

    def test_liste_nue(self):
        self.assertEqual(BB.liste_pnj(PNJ_EN), PNJ_EN)

    def test_conteneur_npcs(self):
        self.assertEqual(BB.liste_pnj({"npcs": PNJ_EN}), PNJ_EN)

    def test_conteneur_inconnu_donne_liste_vide(self):
        self.assertEqual(BB.liste_pnj({"autre": 1}), [])
        self.assertEqual(BB.liste_pnj(None), [])


class TestGeoQueryRendu(unittest.TestCase):
    """`_present` emits 'name'; the CLI used to print p['nom'] → KeyError."""

    def test_present_emet_name_et_le_rendu_le_consomme(self):
        import geo_query as GQ
        entree = GQ._present({"id": "acteur:x", "name": "X", "type": "npcs"}, "lieu:r/a", 0.0)
        self.assertEqual(entree["name"], "X")
        self.assertNotIn("nom", entree)
        source = (SCRIPTS_DIR / "geo_query.py").read_text(encoding="utf-8")
        self.assertNotIn("p['nom']", source)

    def test_present_retombe_sur_lid_sans_nom(self):
        import geo_query as GQ
        entree = GQ._present({"id": "acteur:x"}, "lieu:r/a", 0.0)
        self.assertEqual(entree["name"], "acteur:x")


class TestWorldTickRendu(unittest.TestCase):
    """`_resume_tick` emits 'name'; the briefing used to read t['nom'] → None."""

    def test_resume_tick_emet_name(self):
        import world_tick as WT
        tick = WT._resume_tick({"id": "acteur:x", "name": "X"}, "chaud", [], True)
        self.assertEqual(tick["name"], "X")
        self.assertNotIn("nom", tick)

    def test_brief_acteur_accepte_les_deux_formes(self):
        import world_tick as WT
        self.assertIn("X", WT._brief_acteur(Path("."), {"id": "acteur:x", "name": "X"}, []))
        self.assertIn("X", WT._brief_acteur(Path("."), {"id": "acteur:x", "nom": "X"}, []))
        self.assertIn("acteur:x", WT._brief_acteur(Path("."), {"id": "acteur:x"}, []))


if __name__ == "__main__":
    unittest.main()
