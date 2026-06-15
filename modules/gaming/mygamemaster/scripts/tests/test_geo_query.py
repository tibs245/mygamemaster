#!/usr/bin/env python3
"""
test_geo_query.py — Tests of deterministic spatial queries (contract §12).

STDLIB `unittest` (no pytest required). Run from `scripts/`:
    python3 -m unittest discover
or, from the repository root:
    python3 -m unittest -v modules/gaming/mygamemaster/scripts/tests/test_geo_query.py

MANDATORY cases (contract §12):
  * `build` produces a valid geo.json (`valider_geo` ok);
  * `voisins` returns the expected edges for …/cabane-berthe;
  * `chemin(cabane-berthe, vallee-du-coeur)` has a `temps_ut > 0`;
  * `croisement` finds a window on two trajectories that meet;
  * `creer_lieu`/`deplacer` reject (violations) an inconsistent declaration.

Also: nominal paths (`ou_est`, `distance`, `dans_rayon`, `qui_est_a`), edge
cases (unknown entity/location = fail-open, no path, crossing without
overlap), NON-DESTRUCTIVENESS (dry-run writes nothing), and CLI (exit codes).

Data: self-contained INLINE fixture (throwaway campaign built from a copy of
the real world.json to be able to run `build`) + the real campaign in READ-ONLY
mode for nominal queries. NO writes to the real campaign.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

# The component lives in scripts/; we add it to sys.path for importing (the
# repository root has no Python packages — see contract §1).
SCRIPTS_DIR = Path(__file__).resolve().parent.parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import geo_query as G                 # noqa: E402
import worldlib as W                  # noqa: E402


CAMPAGNE_REELLE = Path(os.environ.get(
    "MGM_TEST_CAMPAIGN",
    str(Path(__file__).resolve().parents[5] / "data" / "mygamemaster" / "campaigns" / "la-naissance-dun-roi"),
))

# Fixed ids reused everywhere (contract §2.2).
CABANE_BERTHE = "lieu:marche-aux-trois-rivieres/cabane-berthe"
VALLEE_COEUR = "lieu:marche-aux-trois-rivieres/vallee-du-coeur"
PRUNELLIER = "lieu:marche-aux-trois-rivieres/prunellier-sauvage"
BOIS_CHARMES = "lieu:marche-aux-trois-rivieres/bois-des-charmes"
CHEMIN_HETRES = "lieu:marche-aux-trois-rivieres/chemin-des-hetres"
REGION_MARCHE = "region:marche-aux-trois-rivieres"


def _a_campagne_reelle() -> bool:
    """Is the real campaign (with geo.json + actors.json) available?"""
    return (
        CAMPAGNE_REELLE.is_dir()
        and (CAMPAGNE_REELLE / "geo.json").exists()
        and (CAMPAGNE_REELLE / "world.json").exists()
    )


def _campagne_jetable_avec_monde(racine: Path) -> Path:
    """Copy the real world.json into a throwaway campaign (to test `build`).

    We do NOT fabricate a synthetic world.json: `build` depends on the real format
    of `regles.temps.deplacements` + `universe.regions`. We therefore copy the real
    world.json (read-only from the source) into an isolated temporary directory, so
    that `build --apply` only writes to the temporary location (non-destructive).
    """
    racine.mkdir(parents=True, exist_ok=True)
    shutil.copy(CAMPAGNE_REELLE / "world.json", racine / "world.json")
    return racine


def _geo_fixture() -> dict:
    """Self-contained mini-graph: 1 region + 3 locations aligned on the East axis.

    A(0,0) --E,1UT--> B(10,0) --E,1UT--> C(20,0). Used for query tests that
    do not need the real campaign (croisement, voisins, chemin).
    """
    return {
        "meta": {"campagne": "Fixture", "version": 1},
        "locations": [
            {
                "id": "region:test", "name": "Region Test", "parent": None,
                "type": "region", "altitude": None,
                "ancrage": {"x": 0, "y": 0}, "aretes": [],
            },
            {
                "id": "lieu:test/a", "name": "Location A", "parent": "region:test",
                "type": "lieu", "altitude": None, "ancrage": {"x": 0, "y": 0},
                "aretes": [
                    {"vers": "lieu:test/b", "dir": "E", "distance_m": None,
                     "temps_ut": 6, "voie": "piste"},
                ],
            },
            {
                "id": "lieu:test/b", "name": "Location B", "parent": "region:test",
                "type": "lieu", "altitude": None, "ancrage": {"x": 10, "y": 0},
                "aretes": [
                    {"vers": "lieu:test/c", "dir": "E", "distance_m": None,
                     "temps_ut": 6},
                ],
            },
            {
                "id": "lieu:test/c", "name": "Location C", "parent": "region:test",
                "type": "lieu", "altitude": None, "ancrage": {"x": 20, "y": 0},
                "aretes": [],
            },
        ],
    }


def _acteurs_fixture() -> dict:
    """Minimal actors.json aligned with the mini-graph (_geo_fixture).

    pat stays at A; mathilde also stays at A (→ crossing at distance 0);
    loin stays at C (→ no crossing with a tight threshold)."""
    return {
        "meta": {"campagne": "Fixture", "version": 1, "t_reference": 0},
        "actors": [
            {
                "id": "acteur:pat", "name": "Pat", "type": "npcs", "lod": "tiede",
                "majeur": True, "but_long_terme": "—", "situation": "—",
                "ressources": {}, "localisation_id": "lieu:test/a",
                "trajectory": [{"lieu": "lieu:test/a", "de": 0, "a": None}],
                "plan": [], "relations": [],
            },
            {
                "id": "acteur:mathilde", "name": "Mathilde", "type": "npcs",
                "lod": "tiede", "majeur": True, "but_long_terme": "—",
                "situation": "—", "ressources": {}, "localisation_id": "lieu:test/a",
                "trajectory": [{"lieu": "lieu:test/a", "de": 0, "a": None}],
                "plan": [], "relations": [],
            },
            {
                "id": "acteur:loin", "name": "Loin", "type": "npcs", "lod": "froid",
                "majeur": True, "but_long_terme": "—", "situation": "—",
                "ressources": {}, "localisation_id": "lieu:test/c",
                "trajectory": [{"lieu": "lieu:test/c", "de": 0, "a": None}],
                "plan": [], "relations": [],
            },
        ],
    }


def _ecrire_campagne_fixture(racine: Path) -> Path:
    """Complete throwaway campaign (minimal world + geo + acteurs fixture)."""
    racine.mkdir(parents=True, exist_ok=True)
    (racine / "world.json").write_text(
        json.dumps({"meta": {"name": "Fixture"}}, ensure_ascii=False),
        encoding="utf-8")
    W.sauver_json_atomique(racine / "geo.json", _geo_fixture())
    W.sauver_json_atomique(racine / "actors.json", _acteurs_fixture())
    return racine


# ════════════════════════════════════════════════════════════════════════════
#  BUILD — geo.json generation + validation (contract §4.2, §12)
# ════════════════════════════════════════════════════════════════════════════

@unittest.skipUnless(_a_campagne_reelle(), "real campaign absent")
class TestBuild(unittest.TestCase):
    """`build` produces a valid geo.json; dry-run writes nothing (non-destructive)."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.camp = _campagne_jetable_avec_monde(Path(self._tmp.name))

    def tearDown(self):
        self._tmp.cleanup()

    def test_dry_run_n_ecrit_rien(self):
        res = G.build(self.camp, apply=False)
        self.assertFalse(res["ecrit"], "dry-run must write NOTHING")
        self.assertFalse((self.camp / "geo.json").exists(),
                         "dry-run: geo.json must not exist")
        # The dry-run still populates the report (stress, number of locations/edges).
        self.assertGreater(res["nb_lieux"], 0)
        self.assertGreater(res["nb_aretes"], 0)

    def test_apply_ecrit_un_geo_valide(self):
        res = G.build(self.camp, apply=True)
        self.assertTrue(res["ecrit"], "apply must write geo.json")
        self.assertTrue((self.camp / "geo.json").exists())
        # The produced geo validates structural invariants (no ERROR).
        rapport = G.valider_geo(self.camp)
        self.assertTrue(rapport["ok"],
                        f"geo.json must be valid: {rapport['erreurs']}")
        self.assertEqual(rapport["erreurs"], [])

    def test_build_contient_les_ids_figes_et_contenance(self):
        res = G.build(self.camp, apply=False)
        idx = {l["id"]: l for l in res["geo"]["locations"]}
        # Fixed ids present (contract §2.2).
        for lid in (CABANE_BERTHE, VALLEE_COEUR, REGION_MARCHE):
            self.assertIn(lid, idx, f"fixed id missing: {lid}")
        # Fixed containment: the region is root, the cabin is attached to it.
        self.assertIsNone(idx[REGION_MARCHE]["parent"], "the region is the root")
        self.assertEqual(idx[CABANE_BERTHE]["parent"], REGION_MARCHE)
        # Sub-locations of the Heart are contained in the Valley (contract §2.2).
        salle = VALLEE_COEUR + "/salle-bleutee"
        if salle in idx:
            self.assertEqual(idx[salle]["parent"], VALLEE_COEUR)

    def test_apply_refuse_d_ecraser_sans_force(self):
        # First apply: creates geo.json.
        self.assertTrue(G.build(self.camp, apply=True)["ecrit"])
        # Second apply without --force: does not overwrite.
        res2 = G.build(self.camp, apply=True, force=False)
        self.assertFalse(res2["ecrit"], "without --force, geo.json is not overwritten")
        # With --force: overwrites.
        res3 = G.build(self.camp, apply=True, force=True)
        self.assertTrue(res3["ecrit"], "with --force, geo.json is rewritten")

    def test_build_deterministe(self):
        a = G.construire_geo(self.camp)
        b = G.construire_geo(self.camp)
        # Same ids, same anchors, same edges (determinism: fixed MDS seed).
        ida = [(l["id"], l["ancrage"]["x"], l["ancrage"]["y"],
                tuple(sorted(e["vers"] for e in l["aretes"])))
               for l in a["locations"]]
        idb = [(l["id"], l["ancrage"]["x"], l["ancrage"]["y"],
                tuple(sorted(e["vers"] for e in l["aretes"])))
               for l in b["locations"]]
        self.assertEqual(ida, idb, "build must be deterministic")


# ════════════════════════════════════════════════════════════════════════════
#  VOISINS — expected edges, containment, fail-open (contract §4.1, §12)
# ════════════════════════════════════════════════════════════════════════════

@unittest.skipUnless(_a_campagne_reelle(), "real campaign absent")
class TestVoisinsReel(unittest.TestCase):
    """`voisins` returns the expected edges for …/cabane-berthe."""

    def test_voisins_cabane_berthe(self):
        res = G.voisins(CAMPAGNE_REELLE, CABANE_BERTHE)
        self.assertEqual(res["lieu"], CABANE_BERTHE)
        self.assertEqual(res["parent"], REGION_MARCHE)
        vers = {a["vers"] for a in res["aretes"]}
        # Expected immediate neighbors (from regles.temps.deplacements §5).
        self.assertIn(PRUNELLIER, vers, "the prunellier is a direct neighbor")
        self.assertIn(BOIS_CHARMES, vers, "the bois des charmes is a direct neighbor")
        # Each edge has the fixed shape (vers, dir, temps_ut).
        for a in res["aretes"]:
            self.assertIn("vers", a)
            self.assertIn("dir", a)
            self.assertIn("temps_ut", a)
            self.assertGreaterEqual(a["temps_ut"], 1)

    def test_voisins_lieu_inconnu_fail_open(self):
        # Fail-open: unknown location → empty dict, NEVER an exception.
        self.assertEqual(G.voisins(CAMPAGNE_REELLE, "lieu:n-existe-pas"), {})


class TestVoisinsFixture(unittest.TestCase):
    """`voisins` on the mini-graph (independent of the real campaign)."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.camp = _ecrire_campagne_fixture(Path(self._tmp.name))

    def tearDown(self):
        self._tmp.cleanup()

    def test_aretes_et_parent(self):
        res = G.voisins(self.camp, "lieu:test/a")
        self.assertEqual(res["parent"], "region:test")
        self.assertEqual([a["vers"] for a in res["aretes"]], ["lieu:test/b"])

    def test_contenus_d_une_region(self):
        # The region contains its 3 locations (adjacency ≠ containment).
        res = G.voisins(self.camp, "region:test")
        self.assertEqual(set(res["contenus"]),
                         {"lieu:test/a", "lieu:test/b", "lieu:test/c"})
        self.assertIsNone(res["parent"])


# ════════════════════════════════════════════════════════════════════════════
#  CHEMIN — shortest path + narrative duration (contract §4.1, §12)
# ════════════════════════════════════════════════════════════════════════════

@unittest.skipUnless(_a_campagne_reelle(), "real campaign absent")
class TestCheminReel(unittest.TestCase):
    """`chemin(cabane-berthe, vallee-du-coeur)` has a temps_ut > 0."""

    def test_chemin_cabane_vers_coeur(self):
        res = G.chemin(CAMPAGNE_REELLE, CABANE_BERTHE, VALLEE_COEUR)
        self.assertGreater(res["temps_ut"], 0, "a path must exist, duration > 0")
        # The path starts at the cabin and ends at the Heart.
        self.assertEqual(res["chemin"][0], CABANE_BERTHE)
        self.assertEqual(res["chemin"][-1], VALLEE_COEUR)
        # The narrative duration is populated (never the raw T on the player side).
        self.assertNotEqual(res["duree_narrative"], "—")

    def test_chemin_symetrique_aller_retour(self):
        # "outbound = return" (bidirectional edges, contract §5).
        aller = G.chemin(CAMPAGNE_REELLE, CABANE_BERTHE, VALLEE_COEUR)["temps_ut"]
        retour = G.chemin(CAMPAGNE_REELLE, VALLEE_COEUR, CABANE_BERTHE)["temps_ut"]
        self.assertEqual(aller, retour)

    def test_chemin_meme_lieu_est_nul(self):
        res = G.chemin(CAMPAGNE_REELLE, CABANE_BERTHE, CABANE_BERTHE)
        self.assertEqual(res["temps_ut"], 0)


class TestCheminFixture(unittest.TestCase):
    """`chemin` multi-hop + "no path" case on the mini-graph."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.camp = _ecrire_campagne_fixture(Path(self._tmp.name))

    def tearDown(self):
        self._tmp.cleanup()

    def test_chemin_multi_sauts(self):
        # A → B → C: two edges of 6 UT = 12 UT.
        res = G.chemin(self.camp, "lieu:test/a", "lieu:test/c")
        self.assertEqual(res["chemin"], ["lieu:test/a", "lieu:test/b", "lieu:test/c"])
        self.assertEqual(res["temps_ut"], 12)

    def test_pas_de_chemin_temps_moins_un(self):
        # region:test has no adjacency edges to the locations → disconnected.
        res = G.chemin(self.camp, "region:test", "lieu:test/c")
        self.assertEqual(res["temps_ut"], -1)
        self.assertEqual(res["chemin"], [])
        self.assertEqual(res["duree_narrative"], "—")


# ════════════════════════════════════════════════════════════════════════════
#  CROISEMENT — intersection of two trajectories (contract §4.1, §12)
# ════════════════════════════════════════════════════════════════════════════

class TestCroisement(unittest.TestCase):
    """`croisement` finds a window when two trajectories meet."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.camp = _ecrire_campagne_fixture(Path(self._tmp.name))

    def tearDown(self):
        self._tmp.cleanup()

    def test_croisement_trouve_une_fenetre(self):
        # Pat and Mathilde stay at the SAME location (A) → distance 0 → crossing.
        traj = [{"lieu": "lieu:test/a", "de": 0, "a": 1000}]
        fenetres = G.croisement(self.camp, traj, traj, seuil=50.0, pas_ut=100)
        self.assertTrue(fenetres, "two overlapping trajectories must cross")
        f = fenetres[0]
        self.assertLessEqual(f["distance"], 50.0)
        self.assertEqual(f["lieu"], "lieu:test/a")
        # The window rendering carries a narrative (never the raw T on the player side).
        self.assertIn("narratif", f)
        self.assertIsInstance(f["T"], int)

    def test_croisement_via_acteurs_reels(self):
        # Trajectories read from actors.json (pat and mathilde, both at A).
        idx = W.index_acteurs(W.charger_acteurs(self.camp))
        ta = W.trajectoire_de(idx["acteur:pat"])
        tb = W.trajectoire_de(idx["acteur:mathilde"])
        fenetres = G.croisement(self.camp, ta, tb, seuil=50.0, pas_ut=72)
        self.assertTrue(fenetres)

    def test_pas_de_croisement_si_trop_loin(self):
        # A (x=0) vs C (x=20) with a tight threshold (5) → never in range.
        ta = [{"lieu": "lieu:test/a", "de": 0, "a": 1000}]
        tc = [{"lieu": "lieu:test/c", "de": 0, "a": 1000}]
        self.assertEqual(G.croisement(self.camp, ta, tc, seuil=5.0, pas_ut=100), [])

    def test_pas_de_recouvrement_temporel(self):
        # Disjoint time intervals → no window, even at the same location.
        ta = [{"lieu": "lieu:test/a", "de": 0, "a": 100}]
        tb = [{"lieu": "lieu:test/a", "de": 500, "a": 600}]
        self.assertEqual(G.croisement(self.camp, ta, tb, seuil=50.0), [])

    def test_trajectoire_vide(self):
        ta = [{"lieu": "lieu:test/a", "de": 0, "a": 100}]
        self.assertEqual(G.croisement(self.camp, ta, [], seuil=50.0), [])
        self.assertEqual(G.croisement(self.camp, [], ta, seuil=50.0), [])


# ════════════════════════════════════════════════════════════════════════════
#  CREER_LIEU / DEPLACER — declarations: rejected if inconsistent (contract §12)
# ════════════════════════════════════════════════════════════════════════════

class TestCreerLieu(unittest.TestCase):
    """`creer_lieu`: nominal (relative anchor, reciprocal edge) and REJECTION."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.camp = _ecrire_campagne_fixture(Path(self._tmp.name))

    def tearDown(self):
        self._tmp.cleanup()

    def test_nominal_dry_run_n_ecrit_rien(self):
        avant = (self.camp / "geo.json").read_text(encoding="utf-8")
        res = G.creer_lieu(self.camp, nom="Cabane du puits", depuis="lieu:test/a",
                           dir="E", distance_m=1000)
        self.assertEqual(res["violations"], [], "consistent declaration: 0 violation")
        self.assertFalse(res["ecrit"], "dry-run must write NOTHING")
        self.assertIsNotNone(res["id"])
        # Id forged under the region of the departure location (deterministic slug).
        self.assertEqual(res["id"], "lieu:test/cabane-du-puits")
        self.assertEqual(res["noeud"]["parent"], "region:test")
        # Relative anchor: East of A(0,0) → x > 0.
        self.assertGreater(res["noeud"]["ancrage"]["x"], 0)
        # Non-destructive: geo.json unchanged after the dry-run.
        self.assertEqual((self.camp / "geo.json").read_text(encoding="utf-8"), avant)

    def test_apply_ecrit_et_cree_l_arete_reciproque(self):
        res = G.creer_lieu(self.camp, nom="Cabane du puits", depuis="lieu:test/a",
                           dir="E", distance_m=1000, apply=True)
        self.assertEqual(res["violations"], [])
        self.assertTrue(res["ecrit"])
        # Read back from disk: the new location exists AND A is linked to it.
        geo = W.charger_geo(self.camp)
        idx = W.index_lieux(geo)
        self.assertIn(res["id"], idx)
        vers_depuis_a = {a["vers"] for a in idx["lieu:test/a"]["aretes"]}
        self.assertIn(res["id"], vers_depuis_a, "outbound edge placed at the departure")
        vers_depuis_neuf = {a["vers"] for a in idx[res["id"]]["aretes"]}
        self.assertIn("lieu:test/a", vers_depuis_neuf, "reciprocal return edge")

    def test_refus_declaration_incoherente(self):
        # Unknown departure + invalid direction + distance ≤ 0 → REJECTION (violations).
        res = G.creer_lieu(self.camp, nom="X", depuis="lieu:inexistant",
                           dir="ZZ", distance_m=-5, apply=True)
        self.assertTrue(res["violations"], "inconsistent declaration must be rejected")
        self.assertIsNone(res["id"])
        self.assertFalse(res["ecrit"], "nothing written when there are violations")
        # All three causes are reported explicitly.
        joint = " | ".join(res["violations"])
        self.assertIn("direction", joint)
        self.assertIn("departure", joint)
        self.assertIn("distance_m", joint)

    def test_refus_n_ecrit_pas_le_fichier(self):
        avant = (self.camp / "geo.json").read_text(encoding="utf-8")
        G.creer_lieu(self.camp, nom="X", depuis="lieu:inexistant", dir="ZZ",
                     distance_m=-5, apply=True)
        self.assertEqual((self.camp / "geo.json").read_text(encoding="utf-8"), avant,
                         "a rejection must NEVER modify geo.json")


class TestDeplacer(unittest.TestCase):
    """`deplacer`: nominal (segments added) and REJECTION (inconsistencies)."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.camp = _ecrire_campagne_fixture(Path(self._tmp.name))

    def tearDown(self):
        self._tmp.cleanup()

    def test_nominal_construit_le_chemin(self):
        # pat is at A; we move him toward C in the FUTURE (t_courant=0 here).
        res = G.deplacer(self.camp, entite_id="acteur:pat", vers="lieu:test/c",
                         depart_t=200)
        self.assertEqual(res["violations"], [], "consistent movement: 0 violation")
        self.assertFalse(res["ecrit"], "dry-run must write NOTHING")
        # A → C = 12 UT; arrival = 200 + 12.
        self.assertEqual(res["arrivee_t"], 212)
        # One travel segment + one final stay.
        self.assertEqual(len(res["segments_ajoutes"]), 2)
        depl = res["segments_ajoutes"][0]
        self.assertEqual(depl.get("type"), "deplacement")
        self.assertEqual(depl["chemin"], ["lieu:test/a", "lieu:test/b", "lieu:test/c"])

    def test_apply_ecrit_la_trajectoire(self):
        res = G.deplacer(self.camp, entite_id="acteur:pat", vers="lieu:test/c",
                         depart_t=200, apply=True)
        self.assertEqual(res["violations"], [])
        self.assertTrue(res["ecrit"])
        # Read back: pat's trajectory does end at the destination.
        idx = W.index_acteurs(W.charger_acteurs(self.camp))
        traj = W.trajectoire_de(idx["acteur:pat"])
        pos = W.position_a(W.charger_geo(self.camp), traj, 1000)
        self.assertEqual(pos["lieu"], "lieu:test/c")

    def test_refus_acteur_inconnu(self):
        res = G.deplacer(self.camp, entite_id="acteur:n-existe-pas",
                         vers="lieu:test/c", depart_t=200, apply=True)
        self.assertTrue(res["violations"])
        self.assertFalse(res["ecrit"])

    def test_refus_destination_inconnue(self):
        res = G.deplacer(self.camp, entite_id="acteur:pat",
                         vers="lieu:n-existe-pas", depart_t=200, apply=True)
        self.assertTrue(res["violations"])
        self.assertFalse(res["ecrit"])

    def test_refus_depart_dans_le_passe(self):
        # t_courant of this fixture = 0 (no timeline); a negative depart_t
        # is before the present → monotonicity violation.
        res = G.deplacer(self.camp, entite_id="acteur:pat", vers="lieu:test/c",
                         depart_t=-50)
        self.assertTrue(any("monotonicity" in v for v in res["violations"]),
                        "a departure in the past must be rejected (monotonicity)")


# ════════════════════════════════════════════════════════════════════════════
#  NOMINAL QUERIES — ou_est / distance / dans_rayon / qui_est_a
# ════════════════════════════════════════════════════════════════════════════

class TestRequetesFixture(unittest.TestCase):
    """ou_est, distance, dans_rayon, qui_est_a on the mini-graph."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.camp = _ecrire_campagne_fixture(Path(self._tmp.name))

    def tearDown(self):
        self._tmp.cleanup()

    def test_ou_est_acteur(self):
        res = G.ou_est(self.camp, "acteur:pat", T=0)
        self.assertEqual(res["lieu"], "lieu:test/a")
        self.assertFalse(res["en_mouvement"])
        self.assertIn("narratif", res)
        self.assertEqual(res["T"], 0)

    def test_ou_est_lieu_statique(self):
        # A location is its own position (stationary).
        res = G.ou_est(self.camp, "lieu:test/b", T=0)
        self.assertEqual(res["lieu"], "lieu:test/b")
        self.assertEqual(res["x"], 10)

    def test_ou_est_inconnu_fail_open(self):
        self.assertEqual(G.ou_est(self.camp, "rien:du:tout"), {})

    def test_distance_graphe_et_vol_oiseau(self):
        res = G.distance(self.camp, "lieu:test/a", "lieu:test/c", vol_oiseau=True)
        self.assertEqual(res["temps_ut"], 12)            # 2 hops of 6 UT
        self.assertAlmostEqual(res["vol_oiseau"], 20.0)  # A(0,0)→C(20,0)

    def test_distance_deconnectee(self):
        res = G.distance(self.camp, "region:test", "lieu:test/c")
        self.assertEqual(res["temps_ut"], -1)

    def test_dans_rayon(self):
        # Around A(0,0), radius 12: B(10,0) is inside, C(20,0) is outside.
        res = G.dans_rayon(self.camp, "lieu:test/a", rayon=12.0, T=0)
        lieux = {l["id"] for l in res["locations"]}
        self.assertIn("lieu:test/b", lieux)
        self.assertNotIn("lieu:test/c", lieux)
        self.assertNotIn("lieu:test/a", lieux, "the center point must not list itself")
        # Pat and Mathilde (at A) are within radius; Loin (at C) is not.
        acteurs = {a["id"] for a in res["actors"]}
        self.assertIn("acteur:pat", acteurs)
        self.assertNotIn("acteur:loin", acteurs)

    def test_dans_rayon_point_inconnu(self):
        res = G.dans_rayon(self.camp, "rien:du:tout", rayon=10.0)
        self.assertEqual(res, {"locations": [], "actors": []})

    def test_qui_est_a_presence_exacte(self):
        # Without radius: exact presence at the location (Pat + Mathilde at A).
        res = G.qui_est_a(self.camp, "lieu:test/a", T=0)
        ids = {p["id"] for p in res}
        self.assertEqual(ids, {"acteur:pat", "acteur:mathilde"})

    def test_qui_est_a_avec_rayon(self):
        # With radius 12 around A: also captures… no one extra (C too far).
        res = G.qui_est_a(self.camp, "lieu:test/a", T=0, rayon=12.0)
        ids = {p["id"] for p in res}
        self.assertIn("acteur:pat", ids)
        self.assertNotIn("acteur:loin", ids)

    def test_qui_est_a_lieu_inconnu(self):
        self.assertEqual(G.qui_est_a(self.camp, "lieu:n-existe-pas"), [])


# ════════════════════════════════════════════════════════════════════════════
#  FAIL-OPEN — reads without geo.json / without actors.json (contract §0.6)
# ════════════════════════════════════════════════════════════════════════════

class TestFailOpen(unittest.TestCase):
    """READ queries never crash on missing data."""

    def test_requetes_sans_aucun_fichier(self):
        with tempfile.TemporaryDirectory() as d:
            camp = Path(d)
            (camp / "world.json").write_text("{}", encoding="utf-8")
            # No geo.json / actors.json: everything returns a consistent empty value.
            self.assertEqual(G.voisins(camp, "lieu:x"), {})
            self.assertEqual(G.ou_est(camp, "acteur:x"), {})
            self.assertEqual(G.qui_est_a(camp, "lieu:x"), [])
            self.assertEqual(G.croisement(camp, [], [], seuil=10.0), [])
            ch = G.chemin(camp, "lieu:a", "lieu:b")
            self.assertEqual(ch["temps_ut"], -1)

    def test_valider_geo_sans_geo_signale_sans_planter(self):
        with tempfile.TemporaryDirectory() as d:
            camp = Path(d)
            (camp / "world.json").write_text("{}", encoding="utf-8")
            rapport = G.valider_geo(camp)
            # geo.json absent → invalid structure reported, but no exception raised.
            self.assertIn("ok", rapport)
            self.assertFalse(rapport["ok"])


# ════════════════════════════════════════════════════════════════════════════
#  CLI — exit codes + dry-run/apply (contract §4.2)
# ════════════════════════════════════════════════════════════════════════════

class TestCLI(unittest.TestCase):
    """The CLI maps to functions and respects exit codes."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.camp = _ecrire_campagne_fixture(Path(self._tmp.name))

    def tearDown(self):
        self._tmp.cleanup()

    def test_voisins_code_0(self):
        code = G.main(["voisins", str(self.camp), "lieu:test/a", "--json"])
        self.assertEqual(code, 0)

    def test_chemin_inexistant_code_1(self):
        # region:test → lieu:test/c: disconnected → business condition (code 1).
        code = G.main(["chemin", str(self.camp), "region:test", "lieu:test/c"])
        self.assertEqual(code, 1)

    def test_chemin_existant_code_0(self):
        code = G.main(["chemin", str(self.camp), "lieu:test/a", "lieu:test/c"])
        self.assertEqual(code, 0)

    def test_creer_lieu_incoherent_code_1(self):
        # Violations rejecting the write → business code 1.
        code = G.main(["creer-lieu", str(self.camp), "--nom", "X",
                       "--depuis", "lieu:inexistant", "--dir", "ZZ",
                       "--distance-m", "-5"])
        self.assertEqual(code, 1)

    def test_campagne_introuvable_code_2(self):
        code = G.main(["voisins", "/chemin/inexistant/xyz", "lieu:test/a"])
        self.assertEqual(code, 2)

    def test_build_dry_run_n_ecrit_rien(self):
        # build on the fixture (minimal world): produces few locations but does not
        # crash; most importantly, dry-run does not write (re-verifies CLI non-destructiveness).
        # We first write a fixture geo; the build dry-run must not overwrite it.
        avant = (self.camp / "geo.json").read_text(encoding="utf-8")
        code = G.main(["build", str(self.camp)])
        self.assertEqual(code, 0)
        self.assertEqual((self.camp / "geo.json").read_text(encoding="utf-8"), avant,
                         "build dry-run must not touch geo.json")


if __name__ == "__main__":
    unittest.main(verbosity=2)
