#!/usr/bin/env python3
"""
test_dialogue_brief.py — Tests for `dialogue_brief.py` (GM-side conversation slice).

STDLIB `unittest` (no pytest required). Run from `scripts/`:
    python3 -m unittest discover -s tests

What matters here is what the brief SELECTS, not how it is worded: a brief that dumps
everything reproduces the failure it exists to fix (references/dialogue-craft.md §1) —
a character who says everything. So the cases below cover the stake-based filtering of
`established_facts`, the fail-open behaviour of every optional block (`voix`, emotions,
`connaissances_privees`), and the ordering guarantee that the facts come LAST.

Also covers the `voix` rendering in `build_brief.py` (the NPC-agent brief), because both
readers must survive a sheet that has no voice recorded yet.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS_DIR))

import build_brief as BB  # noqa: E402
import dialogue_brief as DB  # noqa: E402

FICHE = {
    "name": "Elder Mosswick",
    "titre": "Elder of Thornwick",
    "attitude": "Wary ally",
    "relation_niveau": "Neutral",
    "derniere_interaction": "Session 1",
    "established_facts": [
        "Holds the cold-iron bell",
        "Knows the Veil is fae-caused",
        "Sent people out to warn newcomers",
        "Claims the charter predates him — a lie",
        "Has never left Thornwick",
        "Keeps the hall keys",
    ],
    "gm_hypotheses": ["He is the third soul the Court seeks"],
    "connaissances_privees": ["The bell only works three more times"],
    "limites": {
        "lignes_rouges": ["Will not reveal his true age"],
        "peurs": ["Fears the charter's destruction ends his life"],
        "motivations_personnelles": ["Wants Thornwick safe at any personal cost"],
    },
    "voix": {
        "registre": "Careful, old-fashioned",
        "tics": ["Calls people 'child'"],
        "ne_dit_jamais": ["Never says 'fae'"],
    },
}

NUE = {"name": "Wren", "established_facts": [], "gm_hypotheses": []}


class TestVoix(unittest.TestCase):

    def test_bloc_normalise(self):
        v = DB.voix(FICHE)
        self.assertEqual(v["registre"], "Careful, old-fashioned")
        self.assertEqual(v["tics"], ["Calls people 'child'"])

    def test_absent_ne_leve_pas(self):
        self.assertEqual(DB.voix(NUE), {})

    def test_bloc_malforme_ignore(self):
        self.assertEqual(DB.voix({"voix": "brusque"}), {})
        self.assertEqual(DB.voix("not a dict"), {})

    def test_champs_vides_ecartes(self):
        self.assertEqual(DB.voix({"voix": {"registre": "  ", "tics": []}}), {})

    def test_build_brief_rend_la_voix(self):
        self.assertIn("VOICE", BB.build_brief(FICHE))
        self.assertIn("Calls people 'child'", BB.build_brief(FICHE))

    def test_build_brief_sans_voix_ne_rend_pas_la_section(self):
        self.assertNotIn("VOICE", BB.build_brief(NUE))


class TestFaitsPertinents(unittest.TestCase):

    def test_filtre_sur_l_enjeu(self):
        gardes, restants = DB.faits_pertinents(FICHE, "the players ask about the bell", 2)
        self.assertIn("Holds the cold-iron bell", gardes)
        self.assertEqual(restants, 4)

    def test_sans_enjeu_garde_les_plus_recents(self):
        gardes, _ = DB.faits_pertinents(FICHE, "", 2)
        self.assertEqual(gardes, ["Has never left Thornwick", "Keeps the hall keys"])

    def test_ordre_de_la_fiche_preserve(self):
        gardes, _ = DB.faits_pertinents(FICHE, "charter bell", 3)
        self.assertEqual(gardes, [f for f in FICHE["established_facts"] if f in gardes])

    def test_liste_courte_intacte(self):
        self.assertEqual(DB.faits_pertinents(NUE, "anything", 5), ([], 0))

    def test_enjeu_sans_mot_utile_ne_filtre_pas_au_hasard(self):
        gardes, _ = DB.faits_pertinents(FICHE, "what about that", 2)
        self.assertEqual(gardes, ["Has never left Thornwick", "Keeps the hall keys"])


class TestCollecte(unittest.TestCase):

    def test_separe_ce_qu_il_cache_de_ce_qui_est_hypothetique(self):
        b = DB.collecter(FICHE, "bell")
        self.assertEqual(b["cache"], ["The bell only works three more times"])
        self.assertEqual(b["pression"], ["He is the third soul the Court seeks"])

    def test_refus_agrege_lignes_rouges_et_peurs(self):
        b = DB.collecter(FICHE, "")
        self.assertTrue(b["refuse"]["lignes_rouges"] and b["refuse"]["peurs"])

    def test_fiche_nue_ne_leve_pas(self):
        b = DB.collecter(NUE, "")
        self.assertEqual(b["name"], "Wren")
        self.assertEqual(b["voix"], {})
        self.assertEqual(b["humeur"], "")


class TestRendu(unittest.TestCase):

    def test_les_faits_viennent_apres_ce_qu_il_veut(self):
        texte = DB.rendre(DB.collecter(FICHE, "bell"))
        self.assertLess(texte.index("WANTS HERE"), texte.index("FACTS RELEVANT"))

    def test_sans_voix_le_rendu_reclame_de_l_ecrire(self):
        texte = DB.rendre(DB.collecter(NUE, ""))
        self.assertIn("No `voix` block", texte)

    def test_rappelle_les_quatre_regles(self):
        texte = DB.rendre(DB.collecter(FICHE, "bell"))
        for marque in ("①", "②", "③", "④"):
            self.assertIn(marque, texte)

    def test_les_autres_bouches_sont_listees_une_fois(self):
        autres = [DB.collecter(dict(FICHE, name=n), "") for n in ("A", "B", "C", "D")]
        texte = DB.rendre(DB.collecter(FICHE, ""), autres)
        self.assertEqual(texte.count("ALSO IN THE SCENE"), 1)


class TestCLI(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory(prefix="mjt-dialbrief-")
        cls.camp = Path(cls._tmp.name)
        (cls.camp / "npcs.json").write_text(
            json.dumps([FICHE, NUE], ensure_ascii=False), encoding="utf-8")

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def _run(self, *args):
        return subprocess.run(
            [sys.executable, str(SCRIPTS_DIR / "dialogue_brief.py"), str(self.camp), *args],
            capture_output=True, text=True, timeout=20)

    def test_sortie_humaine(self):
        proc = self._run("Mosswick", "--stake", "the bell")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("DIALOGUE BRIEF", proc.stdout)

    def test_sortie_json_exploitable(self):
        proc = self._run("Mosswick", "--json")
        data = json.loads(proc.stdout)
        self.assertEqual(data["brief"]["name"], "Elder Mosswick")

    def test_pnj_inconnu_code_1(self):
        self.assertEqual(self._run("Nobody").returncode, 1)

    def test_campagne_absente_code_2(self):
        proc = subprocess.run(
            [sys.executable, str(SCRIPTS_DIR / "dialogue_brief.py"), "/nope/nope", "X"],
            capture_output=True, text=True, timeout=20)
        self.assertEqual(proc.returncode, 2)

    def test_liste_marque_les_voix_manquantes(self):
        out = self._run("--list").stdout
        self.assertIn("🗣 Elder Mosswick", out)
        self.assertIn("· Wren", out)


if __name__ == "__main__":
    unittest.main()
