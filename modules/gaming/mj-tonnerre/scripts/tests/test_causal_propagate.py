#!/usr/bin/env python3
"""
test_causal_propagate.py — Tests for causal propagation (contract §12).

STDLIB `unittest` (no pytest required). Run from `scripts/`:
    python3 -m unittest discover

MANDATORY cases (contract §12):
  * `propager` TERMINATES (strictly decreasing significance);
  * `profondeur` bounded by PROFONDEUR_MAX;
  * wave below SEUIL → empty list;
  * all emitted events validate evenement_programme.schema.json;
  * no T earlier than the root.

Also: determinism, atomic append, idempotency, fail-open (campaign without
actors.json), CLI dry-run vs --apply. Data: self-contained INLINE fixture
(the real vertical slice — Bande du Corbeau — reproduced in miniature) +
the real campaign in READ-ONLY mode for fail-open.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent.parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import causal_propagate as C          # noqa: E402
import worldlib as W                  # noqa: E402
import validate_schema as V           # noqa: E402


CAMPAGNE_REELLE = Path(os.environ.get(
    "MJ_TEST_CAMPAIGN",
    str(Path(__file__).resolve().parents[5] / "data" / "mj-tonnerre" / "campaigns" / "la-naissance-dun-roi"),
))


def _acteurs_fixture() -> dict:
    """Miniature actors.json: a causal chain long enough to test bounding.

    bleville --approvisionnement(part .7, delay 4320)--> tonnerre
    tonnerre --vassalite(.8)--> val-perdu
    tonnerre --predation(.5)--> bourg-orme   (under shortage → migrant exodus)
    val-perdu --vassalite(.9)--> royaume     (extra relay for depth)
    royaume  --vassalite(.9)--> empire        (one more step)
    + an intentional CYCLE tonnerre<->val-perdu to verify termination.
    """
    return {
        "meta": {"campagne": "Fixture", "version": 1, "t_reference": 0},
        "acteurs": [
            {
                "id": "ville:bleville", "name": "Bleville", "type": "ville",
                "lod": "froid", "majeur": True, "but_long_terme": "prospérer",
                "situation": "—", "ressources": {}, "trajectoire": [],
                "plan": [],
                "relations": [
                    {"vers": "ville:tonnerre", "type": "approvisionnement",
                     "bien": "ble", "part": 0.7, "delai_ut": 4320, "poids": 0.7},
                ],
            },
            {
                "id": "ville:tonnerre", "name": "Tonnerre", "type": "ville",
                "lod": "tiede", "majeur": True, "but_long_terme": "—",
                "situation": "—", "ressources": {}, "trajectoire": [],
                "plan": [],
                "relations": [
                    {"vers": "comte:val-perdu", "type": "vassalite",
                     "intensite": 0.8, "delai_ut": 680, "poids": 0.8},
                    {"vers": "ville:bourg-orme", "type": "predation",
                     "intensite": 0.6, "delai_ut": 200, "poids": 0.6},
                ],
            },
            {
                "id": "comte:val-perdu", "name": "Val-Perdu", "type": "faction",
                "lod": "froid", "majeur": True, "but_long_terme": "—",
                "situation": "—", "ressources": {}, "trajectoire": [],
                "plan": [],
                "relations": [
                    {"vers": "faction:royaume", "type": "vassalite",
                     "intensite": 0.9, "delai_ut": 100, "poids": 0.9},
                    # Intentional CYCLE: loops back to Tonnerre (anti-loop test).
                    {"vers": "ville:tonnerre", "type": "approvisionnement",
                     "delai_ut": 50, "poids": 0.9},
                ],
            },
            {
                "id": "faction:royaume", "name": "Royaume", "type": "faction",
                "lod": "froid", "majeur": True, "but_long_terme": "—",
                "situation": "—", "ressources": {}, "trajectoire": [],
                "plan": [],
                "relations": [
                    {"vers": "faction:empire", "type": "vassalite",
                     "intensite": 0.9, "delai_ut": 100, "poids": 0.9},
                ],
            },
            {
                "id": "faction:empire", "name": "Empire", "type": "faction",
                "lod": "froid", "majeur": True, "but_long_terme": "—",
                "situation": "—", "ressources": {}, "trajectoire": [],
                "plan": [], "relations": [],
            },
            {
                "id": "ville:bourg-orme", "name": "Bourg-de-l'Orme", "type": "ville",
                "lod": "froid", "majeur": True, "but_long_terme": "—",
                "situation": "—", "ressources": {}, "trajectoire": [],
                "plan": [], "relations": [],
            },
            # — Real vertical slice (miniature): the Bande du Corbeau ---------
            {
                "id": "faction:bande-du-corbeau", "name": "La Bande du Corbeau",
                "type": "faction", "lod": "tiede", "majeur": True,
                "but_long_terme": "Rester maîtres de la Marche",
                "situation": "Campée au Gué.", "ressources": {"vivres_jours": 12},
                "localisation_id": "lieu:marche-aux-trois-rivieres/gue-du-corbeau",
                "trajectoire": [],
                "plan": [
                    {
                        "id": "intent:raid-hivernal",
                        "action": "Raid d'approvisionnement hivernal sur une cible isolée",
                        "lieu": "lieu:marche-aux-trois-rivieres/cabane-berthe",
                        "echeance": 3960,
                        "consequence_attendue": "cabane pillée si non défendue.",
                        "significativite": 0.6,
                        "visible_par_pj": False,
                        "statut": "planifie",
                    }
                ],
                "relations": [
                    {"vers": "acteur:berthe", "type": "predation",
                     "intensite": 0.4, "delai_ut": 0, "poids": 0.4},
                ],
            },
            {
                "id": "acteur:berthe", "name": "Berthe", "type": "pnj",
                "lod": "chaud", "majeur": True, "but_long_terme": "—",
                "situation": "—", "ressources": {}, "trajectoire": [],
                "plan": [], "relations": [],
            },
        ],
    }


def _ecrire_campagne_fixture(racine: Path) -> Path:
    """Creates a throwaway campaign (minimal world.json + actors.json fixture)."""
    racine.mkdir(parents=True, exist_ok=True)
    (racine / "world.json").write_text(
        json.dumps({"meta": {"name": "Fixture"}}, ensure_ascii=False),
        encoding="utf-8",
    )
    (racine / "actors.json").write_text(
        json.dumps(_acteurs_fixture(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return racine


def _evt_incendie() -> dict:
    """Root event for the worked example (doc 04 §4): field fire."""
    return {
        "id": "evt:incendie-4000", "T": 4000, "type": "incendie",
        "cible": "ville:bleville", "significativite": 0.9, "statut": "resolu",
    }


class TestRegleDePropagation(unittest.TestCase):
    """The deterministic table (type_evt, relation.type) → effect."""

    def test_couples_figes(self):
        self.assertEqual(
            C.regle_de_propagation("raid", {"type": "predation"})["type"],
            "pression_locale")
        self.assertEqual(
            C.regle_de_propagation("penurie", {"type": "approvisionnement"})["type"],
            "penurie")
        self.assertEqual(
            C.regle_de_propagation("penurie", {"type": "vassalite"})["type"],
            "appel_a_l_aide")
        self.assertEqual(
            C.regle_de_propagation("incendie", {"type": "approvisionnement"})["type"],
            "penurie")

    def test_couple_inconnu_renvoie_none(self):
        self.assertIsNone(C.regle_de_propagation("inexistant", {"type": "parente"}))
        self.assertIsNone(C.regle_de_propagation("raid", {"type": "parente"}))

    def test_robuste_aux_entrees_invalides(self):
        self.assertIsNone(C.regle_de_propagation("raid", None))
        self.assertIsNone(C.regle_de_propagation(None, {"type": "predation"}))
        self.assertIsNone(C.regle_de_propagation("raid", {"type": None}))

    def test_table_non_mutee(self):
        # Defensive copy: mutating the result does not alter the base table.
        r = C.regle_de_propagation("raid", {"type": "predation"})
        r["type"] = "PIRATÉ"
        self.assertEqual(
            C.regle_de_propagation("raid", {"type": "predation"})["type"],
            "pression_locale")


class TestProgrammerEvenement(unittest.TestCase):
    """Factory for a scheduled event."""

    def test_id_et_champs(self):
        evt = C.programmer_evenement(
            cible="ville:tonnerre", T=8320, type="penurie",
            significativite=0.5, cause="evt:incendie-4000")
        self.assertEqual(evt["id"], "evt:penurie-8320")
        self.assertEqual(evt["T"], 8320)
        self.assertEqual(evt["type"], "penurie")
        self.assertEqual(evt["cible"], "ville:tonnerre")
        self.assertEqual(evt["cause"], "evt:incendie-4000")
        self.assertEqual(evt["statut"], "programme")
        # Narrative qualification is DEFERRED: always None at scheduling time.
        self.assertIsNone(evt["narratif"])
        self.assertEqual(evt["source"], C.SOURCE)

    def test_significativite_bornee(self):
        haut = C.programmer_evenement(cible="x", T=1, type="t",
                                      significativite=5.0, cause="c")
        bas = C.programmer_evenement(cible="x", T=1, type="t",
                                     significativite=-3.0, cause="c")
        self.assertLessEqual(haut["significativite"], 1.0)
        self.assertGreaterEqual(bas["significativite"], 0.0)

    def test_t_zero_padde(self):
        evt = C.programmer_evenement(cible="x", T=7, type="t",
                                     significativite=0.5, cause="c")
        self.assertEqual(evt["id"], "evt:t-0007")


class TestSeamLLM(unittest.TestCase):
    """The narrative qualification seam is DEFERRED (never called here)."""

    def test_qualifier_narratif_renvoie_none(self):
        with tempfile.TemporaryDirectory() as d:
            evt = C.programmer_evenement(cible="x", T=1, type="raid",
                                         significativite=0.6, cause="c")
            self.assertIsNone(C.qualifier_narratif(evt, Path(d)))


class TestPropagation(unittest.TestCase):
    """Core: bounded cascade, deterministic, guaranteed termination."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.camp = _ecrire_campagne_fixture(Path(self._tmp.name))

    def tearDown(self):
        self._tmp.cleanup()

    # — Termination + strictly decreasing significance --------------------

    def test_termine_et_significativite_decroit(self):
        racine = _evt_incendie()
        derives = C.propager(racine, 0, campagne=self.camp)
        self.assertGreater(len(derives), 0, "the cascade must produce derivatives")
        # Each derivative has a significance < that of its cause (chain by id).
        par_id = {racine["id"]: racine}
        for e in derives:
            par_id[e["id"]] = e
        for e in derives:
            cause = par_id.get(e["cause"])
            self.assertIsNotNone(cause, f"cause {e['cause']} found")
            self.assertLess(
                e["significativite"], C._evt_significativite(cause) + 1e-9,
                "significance strictly decreasing along the chain")

    # — Bounded depth --------------------------------------------------------

    def test_profondeur_bornee(self):
        racine = _evt_incendie()
        derives = C.propager(racine, 0, campagne=self.camp)
        profs = [e.get("profondeur", 0) for e in derives]
        self.assertTrue(profs, "derivatives are expected")
        self.assertLessEqual(max(profs), C.PROFONDEUR_MAX + 1,
                             "depth never exceeds PROFONDEUR_MAX (+1 = "
                             "level of the derivative emitted at the threshold)")

    # — Wave below SEUIL → empty list --------------------------------------------

    def test_onde_sous_seuil_liste_vide(self):
        racine = dict(_evt_incendie())
        racine["significativite"] = C.SEUIL - 0.01      # just below the threshold
        derives = C.propager(racine, 0, campagne=self.camp)
        self.assertEqual(derives, [], "below SEUIL the wave dies immediately")

    def test_onde_au_seuil_propage(self):
        racine = dict(_evt_incendie())
        racine["significativite"] = C.SEUIL             # at threshold: it passes
        derives = C.propager(racine, 0, campagne=self.camp)
        self.assertGreater(len(derives), 0)

    # — No T earlier than the root -------------------------------------------

    def test_aucun_t_dans_le_passe(self):
        racine = _evt_incendie()
        derives = C.propager(racine, 0, campagne=self.camp)
        for e in derives:
            self.assertGreaterEqual(
                e["T"], racine["T"],
                f"event {e['id']} scheduled in the past (T={e['T']} < "
                f"{racine['T']})")

    def test_t_egal_t_cause_plus_delai(self):
        # First hop: bleville --approvisionnement(delay 4320)--> tonnerre.
        racine = _evt_incendie()           # T=4000
        derives = C.propager(racine, 0, campagne=self.camp)
        penurie_tonnerre = [e for e in derives if e["cible"] == "ville:tonnerre"]
        self.assertTrue(penurie_tonnerre)
        self.assertEqual(penurie_tonnerre[0]["T"], 4000 + 4320)
        self.assertEqual(penurie_tonnerre[0]["type"], "penurie")

    # — Budget per source --------------------------------------------------------

    def test_budget_respecte(self):
        racine = _evt_incendie()
        derives = C.propager(racine, 0, campagne=self.camp)
        self.assertLessEqual(len(derives), C.BUDGET_PAR_SOURCE)

    # — Determinism -------------------------------------------------------------

    def test_deterministe(self):
        racine = _evt_incendie()
        a = C.propager(racine, 0, campagne=self.camp)
        b = C.propager(racine, 0, campagne=self.camp)
        self.assertEqual([(e["id"], e["T"], e["significativite"]) for e in a],
                         [(e["id"], e["T"], e["significativite"]) for e in b])

    # — Realistic cascade: we find the shortage AND the migrant exodus -------

    def test_cascade_atteint_migrants(self):
        racine = _evt_incendie()
        derives = C.propager(racine, 0, campagne=self.camp)
        cibles = {e["cible"] for e in derives}
        self.assertIn("ville:tonnerre", cibles)        # shortage
        self.assertIn("comte:val-perdu", cibles)       # call for help (vassalage)
        self.assertIn("ville:bourg-orme", cibles)      # migrant exodus (predation)

    # — Schema: all derivatives validate evenement_programme.schema.json -------

    def test_derives_valident_schema(self):
        schema = V.charger_schema("scheduled_event")
        racine = _evt_incendie()
        derives = C.propager(racine, 0, campagne=self.camp)
        self.assertTrue(derives)
        for e in derives:
            ecarts = V.valider(e, schema, schema)
            self.assertEqual(ecarts, [], f"schema discrepancies on {e['id']}: {ecarts}")

    # — Full file also validates the schema (container form) -----------------

    def test_fichier_complet_valide_schema(self):
        racine = _evt_incendie()
        derives = C.propager(racine, 0, campagne=self.camp)
        C.appliquer(self.camp, derives)
        data = W.charger_json(self.camp / C.NOM_FICHIER_PROG, {})
        schema = V.charger_schema("scheduled_event")
        ecarts = V.valider(data, schema, schema)
        self.assertEqual(ecarts, [], f"schema discrepancies in file: {ecarts}")


class TestAppliquer(unittest.TestCase):
    """Atomic append, file creation, idempotency, non-destructiveness."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.camp = _ecrire_campagne_fixture(Path(self._tmp.name))

    def tearDown(self):
        self._tmp.cleanup()

    def test_cree_le_fichier_avec_meta(self):
        racine = _evt_incendie()
        derives = C.propager(racine, 0, campagne=self.camp)
        n = C.appliquer(self.camp, derives)
        self.assertEqual(n, len(derives))
        data = W.charger_json(self.camp / C.NOM_FICHIER_PROG, None)
        self.assertIsInstance(data, dict)
        self.assertIn("meta", data)
        self.assertIn("evenements", data)
        self.assertEqual(data["meta"]["version"], C.PROG_VERSION)
        self.assertIn("Ne JAMAIS fusionner", data["meta"]["note"])

    def test_idempotent_sur_id(self):
        racine = _evt_incendie()
        derives = C.propager(racine, 0, campagne=self.camp)
        C.appliquer(self.camp, derives)
        # Re-applying the SAME derivatives must add NOTHING (same ids).
        n2 = C.appliquer(self.camp, derives)
        self.assertEqual(n2, 0)
        data = W.charger_json(self.camp / C.NOM_FICHIER_PROG, {})
        ids = [e["id"] for e in data["evenements"]]
        self.assertEqual(len(ids), len(set(ids)), "no duplicate ids")

    def test_append_preserve_existant(self):
        # Pre-fills with a "manual" event.
        prealable = {
            "meta": {"campagne": "Fixture", "version": 1, "note": "Ne JAMAIS fusionner"},
            "evenements": [{
                "id": "evt:manuel-0001", "T": 1, "type": "manuel",
                "cible": "x", "cause": "—", "significativite": 0.5, "statut": "programme",
            }],
        }
        W.sauver_json_atomique(self.camp / C.NOM_FICHIER_PROG, prealable)
        derives = C.propager(_evt_incendie(), 0, campagne=self.camp)
        C.appliquer(self.camp, derives)
        data = W.charger_json(self.camp / C.NOM_FICHIER_PROG, {})
        ids = {e["id"] for e in data["evenements"]}
        self.assertIn("evt:manuel-0001", ids, "the existing entry is preserved")

    def test_n_ecrit_jamais_evenements_json(self):
        # Non-destructive safeguard: events.json must not be touched.
        (self.camp / "events.json").write_text(
            json.dumps({"evenements": [{"id": "ORIGINAL"}]}, ensure_ascii=False),
            encoding="utf-8")
        avant = (self.camp / "events.json").read_text(encoding="utf-8")
        derives = C.propager(_evt_incendie(), 0, campagne=self.camp)
        C.appliquer(self.camp, derives)
        apres = (self.camp / "events.json").read_text(encoding="utf-8")
        self.assertEqual(avant, apres, "events.json must NEVER be modified")

    def test_appliquer_liste_vide(self):
        self.assertEqual(C.appliquer(self.camp, []), 0)


class TestAmorceIntention(unittest.TestCase):
    """Seeding from an intention (CLI --intention) on the vertical slice."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.camp = _ecrire_campagne_fixture(Path(self._tmp.name))

    def tearDown(self):
        self._tmp.cleanup()

    def test_raid_hivernal_propage_predation(self):
        acteurs = W.charger_acteurs(self.camp)
        racine = C._evt_racine_depuis_intention(
            self.camp, "faction:bande-du-corbeau", "intent:raid-hivernal", acteurs)
        self.assertIsNotNone(racine)
        self.assertEqual(racine["type"], "raid")
        self.assertEqual(racine["T"], 3960)
        self.assertEqual(racine["cible"],
                         "lieu:marche-aux-trois-rivieres/cabane-berthe")
        derives = C.propager(racine, 0, campagne=self.camp)
        # raid + predation(berthe) → pression_locale @ berthe.
        cibles = {(e["cible"], e["type"]) for e in derives}
        self.assertIn(("acteur:berthe", "pression_locale"), cibles)

    def test_intention_introuvable(self):
        acteurs = W.charger_acteurs(self.camp)
        self.assertIsNone(C._evt_racine_depuis_intention(
            self.camp, "faction:bande-du-corbeau", "intent:inexistant", acteurs))
        self.assertIsNone(C._evt_racine_depuis_intention(
            self.camp, "acteur:inexistant", "intent:raid-hivernal", acteurs))


class TestFailOpen(unittest.TestCase):
    """Fail-open: without actors.json, propagation does not crash (empty list)."""

    def test_sans_acteurs_json(self):
        with tempfile.TemporaryDirectory() as d:
            camp = Path(d)
            (camp / "world.json").write_text("{}", encoding="utf-8")
            derives = C.propager(_evt_incendie(), 0, campagne=camp)
            self.assertEqual(derives, [])

    def test_campagne_reelle_lecture_seule(self):
        # The real campaign may not (yet) have an actors.json → fail-open;
        # either way, propager() returns a list WITHOUT ever writing (we
        # do not call appliquer()).
        if not CAMPAGNE_REELLE.is_dir():
            self.skipTest("campagne réelle absente")
        prog_avant = (CAMPAGNE_REELLE / C.NOM_FICHIER_PROG).exists()
        derives = C.propager(_evt_incendie(), 0, campagne=CAMPAGNE_REELLE)
        self.assertIsInstance(derives, list)
        # propager() alone writes nothing: the file's presence is unchanged.
        prog_apres = (CAMPAGNE_REELLE / C.NOM_FICHIER_PROG).exists()
        self.assertEqual(prog_avant, prog_apres,
                         "propager() must write NOTHING in the real campaign")


class TestCLI(unittest.TestCase):
    """CLI: dry-run vs --apply, exit codes, seed exclusivity."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.camp = _ecrire_campagne_fixture(Path(self._tmp.name))

    def tearDown(self):
        self._tmp.cleanup()

    def _evt_fichier(self) -> Path:
        p = self.camp / "_racine.json"
        p.write_text(json.dumps(_evt_incendie(), ensure_ascii=False), encoding="utf-8")
        return p

    def test_dry_run_n_ecrit_rien(self):
        p = self._evt_fichier()
        code = C.main(["propager", str(self.camp), "--evt", str(p)])
        self.assertEqual(code, 0)
        self.assertFalse((self.camp / C.NOM_FICHIER_PROG).exists(),
                         "dry-run must write NOTHING")

    def test_apply_ecrit(self):
        p = self._evt_fichier()
        code = C.main(["propager", str(self.camp), "--evt", str(p), "--apply"])
        self.assertEqual(code, 0)
        self.assertTrue((self.camp / C.NOM_FICHIER_PROG).exists())
        data = W.charger_json(self.camp / C.NOM_FICHIER_PROG, {})
        self.assertGreater(len(data["evenements"]), 0)

    def test_onde_eteinte_code_1(self):
        racine = dict(_evt_incendie())
        racine["significativite"] = 0.05
        p = self.camp / "_faible.json"
        p.write_text(json.dumps(racine, ensure_ascii=False), encoding="utf-8")
        code = C.main(["propager", str(self.camp), "--evt", str(p)])
        self.assertEqual(code, 1, "wave below SEUIL → business code 1")

    def test_amorces_exclusives(self):
        p = self._evt_fichier()
        # Providing BOTH seeds → code 2 (usage).
        code = C.main(["propager", str(self.camp), "--evt", str(p),
                       "--intention", "faction:bande-du-corbeau:intent:raid-hivernal"])
        self.assertEqual(code, 2)
        # Providing NONE → code 2 (usage).
        code = C.main(["propager", str(self.camp)])
        self.assertEqual(code, 2)

    def test_campagne_introuvable_code_2(self):
        code = C.main(["propager", "/chemin/inexistant/xyz", "--evt", "-"])
        self.assertEqual(code, 2)

    def test_intention_via_cli_apply(self):
        code = C.main(["propager", str(self.camp), "--intention",
                       "faction:bande-du-corbeau:intent:raid-hivernal", "--apply"])
        self.assertEqual(code, 0)
        data = W.charger_json(self.camp / C.NOM_FICHIER_PROG, {})
        self.assertTrue(any(e["cible"] == "acteur:berthe"
                            for e in data["evenements"]))


if __name__ == "__main__":
    unittest.main(verbosity=2)
