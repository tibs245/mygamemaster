#!/usr/bin/env python3
"""
test_worldlib.py — Tests for the shared "living world" library (contract §12).

STDLIB `unittest` (no pytest required). Run from `scripts/`:
    python3 -m unittest discover
or directly by file path:
    python3 modules/gaming/mj-tonnerre/scripts/tests/test_worldlib.py

MANDATORY cases (contract §12, worldlib line):
  * t_vers_jour_heure / jour_heure_vers_t REVERSIBLE;
  * T=0 → (1, 0, 0);
  * jour_heure_vers_t(7, 12, 0) == 936;
  * minutes_vers_ut(40) == 4, (20) == 2, (90) == 9;
  * slug("Sceau n°6 — Limite Nord") DETERMINISTIC ( == "sceau-n-6-limite-nord");
  * SMACOF: stress_normalise < 0.30 on the REAL campaign matrix;
  * position_a on stay AND on travel (interpolation);
  * valider_trajectoire detects gap / overlap / teleportation.

Plus (extended coverage): narrative conversions, parser_duree_minutes,
containment/adjacency helpers (parents/contenus/lieu_racine/voisins),
plus_court_chemin (bidirectional, deterministic), distance_vol_oiseau,
MDS determinism (fixed seed), actor/relation access, echeance_en_t
(int / pinned clock.py format / free string), fail-open JSON loading and
atomic write. Data: self-contained INLINE fixtures + the real campaign
READ-ONLY for MDS stress and t_courant.
"""

from __future__ import annotations

import json
import math
import os
import sys
import tempfile
import unittest
from pathlib import Path

# The `scripts/` directory must be on sys.path to import worldlib as a
# top-level module (the `mj-tonnerre` folder contains a dash: it is NOT a
# Python package importable via dotted notation — so we go through sys.path).
SCRIPTS_DIR = Path(__file__).resolve().parent.parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import worldlib as W  # noqa: E402


CAMPAGNE_REELLE = Path(os.environ.get(
    "MJ_TEST_CAMPAIGN",
    str(Path(__file__).resolve().parents[5] / "data" / "mj-tonnerre" / "campagnes" / "la-naissance-dun-roi"),
))


# ════════════════════════════════════════════════════════════════════════════
# Fixtures inline
# ════════════════════════════════════════════════════════════════════════════

def _geo_jouet() -> dict:
    """Small linear graph A→B→C + one isolated node D, with containment.

    Topology (temps_ut in parentheses):
        REGION (root)
          ├─ A ──(6)── B ──(6)── C        (anchors aligned on the x axis)
          │            └─ B_INT  (contained WITHIN B)
          └─ D  (isolated: no edges)
    """
    return {
        "meta": {"campagne": "Jouet", "version": 1},
        "lieux": [
            {"id": "region:test", "nom": "Région test", "parent": None,
             "type": "region", "altitude": None, "ancrage": {"x": 0, "y": 0},
             "aretes": []},
            {"id": "A", "nom": "Lieu A", "parent": "region:test", "type": "lieu",
             "altitude": None, "ancrage": {"x": 0, "y": 0},
             "aretes": [{"vers": "B", "dir": "E", "distance_m": 100, "temps_ut": 6,
                         "voie": "sentier"}]},
            {"id": "B", "nom": "Lieu B", "parent": "region:test", "type": "lieu",
             "altitude": None, "ancrage": {"x": 60, "y": 0},
             "aretes": [{"vers": "C", "dir": "E", "distance_m": 100, "temps_ut": 6,
                         "voie": "sentier"}]},
            {"id": "C", "nom": "Lieu C", "parent": "region:test", "type": "lieu",
             "altitude": None, "ancrage": {"x": 120, "y": 0}, "aretes": []},
            {"id": "B_INT", "nom": "Salle de B", "parent": "B", "type": "lieu",
             "altitude": None, "ancrage": {"x": 60, "y": 0}, "aretes": []},
            {"id": "D", "nom": "Lieu isolé", "parent": "region:test", "type": "lieu",
             "altitude": None, "ancrage": {"x": 999, "y": 999}, "aretes": []},
        ],
    }


def _acteurs_jouet() -> dict:
    return {
        "meta": {"campagne": "Jouet", "version": 1, "t_reference": 0},
        "acteurs": [
            {
                "id": "acteur:alpha", "nom": "Alpha", "type": "pnj",
                "lod": "tiede", "majeur": True, "but_long_terme": "—",
                "situation": "—", "ressources": {},
                "trajectoire": [{"lieu": "A", "de": 0, "a": None}],
                "plan": [],
                "relations": [
                    {"vers": "acteur:beta", "type": "hostilite", "intensite": 0.6},
                    {"vers": "C", "type": "predation", "intensite": 0.4},
                ],
            },
            {
                "id": "acteur:beta", "nom": "Beta", "type": "pnj",
                "lod": "froid", "majeur": True, "but_long_terme": "—",
                "situation": "—", "ressources": {},
                # No 'trajectoire': only localisation_id (backward-compat).
                "localisation_id": "B",
                "plan": [],
                "relations": [
                    {"vers": "acteur:alpha", "type": "alliance", "intensite": 0.5},
                ],
            },
        ],
    }


# ════════════════════════════════════════════════════════════════════════════
# 3.2bis — Campaign PCs: pj_ids (list, multi-PC) + pj_id (backward-compat)
# ════════════════════════════════════════════════════════════════════════════

class TestPjIds(unittest.TestCase):
    """GENERIC PC resolution (cascade meta.pj_ids > meta.pj_id > MJ_PJ_ID > [])."""

    def setUp(self):
        # Isolate MJ_PJ_ID: save/restore to avoid polluting other tests.
        self._env_sauve = os.environ.pop("MJ_PJ_ID", None)

    def tearDown(self):
        if self._env_sauve is None:
            os.environ.pop("MJ_PJ_ID", None)
        else:
            os.environ["MJ_PJ_ID"] = self._env_sauve

    # --- pj_ids: the 3 required cases ----------------------------------------
    def test_pj_ids_liste_canonique(self):
        # meta.pj_ids:["a","b"] (canonical form, multi-PC) → ["a","b"].
        monde = {"meta": {"pj_ids": ["acteur:a", "acteur:b"]}}
        self.assertEqual(W.pj_ids(monde), ["acteur:a", "acteur:b"])

    def test_pj_ids_retrocompat_pj_id_unique(self):
        # Only meta.pj_id:"x" (old form) → ["x"].
        monde = {"meta": {"pj_id": "acteur:x"}}
        self.assertEqual(W.pj_ids(monde), ["acteur:x"])

    def test_pj_ids_monde_vide(self):
        # World with no PC meta and no env → [].
        self.assertEqual(W.pj_ids({}), [])
        self.assertEqual(W.pj_ids({"meta": {}}), [])

    # --- pj_ids: cascade, env, robustness ------------------------------------
    def test_pj_ids_priorite_pj_ids_sur_pj_id(self):
        # If both are present, pj_ids (canonical) wins (no merge).
        monde = {"meta": {"pj_ids": ["acteur:a"], "pj_id": "acteur:z"}}
        self.assertEqual(W.pj_ids(monde), ["acteur:a"])

    def test_pj_ids_depuis_env_splitte_virgules(self):
        # No PC meta → env MJ_PJ_ID split on commas, spaces stripped.
        os.environ["MJ_PJ_ID"] = " acteur:a , acteur:b ,"
        self.assertEqual(W.pj_ids({}), ["acteur:a", "acteur:b"])

    def test_pj_ids_meta_prime_sur_env(self):
        # meta (pj_ids/pj_id) takes priority over env.
        os.environ["MJ_PJ_ID"] = "acteur:env"
        self.assertEqual(W.pj_ids({"meta": {"pj_id": "acteur:meta"}}), ["acteur:meta"])

    def test_pj_ids_dedup_preserve_ordre_et_ignore_vides(self):
        # Duplicates removed (1st occurrence kept), empty/non-str entries ignored.
        monde = {"meta": {"pj_ids": ["acteur:a", "  ", "acteur:b", "acteur:a", 42, None]}}
        self.assertEqual(W.pj_ids(monde), ["acteur:a", "acteur:b"])

    def test_pj_ids_liste_vide_retombe_sur_pj_id(self):
        # meta.pj_ids present but WITH NO useful entry → fall back to meta.pj_id.
        monde = {"meta": {"pj_ids": ["", "   "], "pj_id": "acteur:x"}}
        self.assertEqual(W.pj_ids(monde), ["acteur:x"])

    def test_pj_ids_fail_open_non_dict(self):
        # non-dict world → [] (never raises).
        self.assertEqual(W.pj_ids(None), [])
        self.assertEqual(W.pj_ids("nope"), [])
        self.assertEqual(W.pj_ids(123), [])

    # --- pj_id: backward-compat = first of pj_ids ----------------------------
    def test_pj_id_premier_de_pj_ids(self):
        monde = {"meta": {"pj_ids": ["acteur:a", "acteur:b"]}}
        self.assertEqual(W.pj_id(monde), "acteur:a")

    def test_pj_id_retrocompat_pj_id(self):
        self.assertEqual(W.pj_id({"meta": {"pj_id": "acteur:x"}}), "acteur:x")

    def test_pj_id_none_si_aucun(self):
        self.assertIsNone(W.pj_id({}))
        self.assertIsNone(W.pj_id(None))


# ════════════════════════════════════════════════════════════════════════════
# 3.3 — Time conversion (MANDATORY cases + reversibility)
# ════════════════════════════════════════════════════════════════════════════

class TestConversionTemps(unittest.TestCase):

    def test_t0_vers_jour_heure(self):
        self.assertEqual(W.t_vers_jour_heure(0), (1, 0, 0))

    def test_ancre_jour7_midi_vaut_936(self):
        # PINNED value from the contract (§3.3, §10).
        self.assertEqual(W.jour_heure_vers_t(7, 12, 0), 936)

    def test_reversibilite_aller_retour(self):
        # For every valid (day, hour, minute), t_vers_jour_heure ∘ jour_heure_vers_t
        # is the identity.
        for jour in (1, 2, 7, 28, 100):
            for heure in (0, 1, 11, 12, 17, 23):
                for minute in (0, 10, 30, 50):
                    T = W.jour_heure_vers_t(jour, heure, minute)
                    self.assertEqual(W.t_vers_jour_heure(T), (jour, heure, minute),
                                     f"not reversible for ({jour},{heure},{minute})")

    def test_reversibilite_depuis_t(self):
        # And in the other direction: jour_heure_vers_t ∘ t_vers_jour_heure == identity on T.
        for T in (0, 1, 5, 143, 144, 936, 3960, 12345):
            jour, heure, minute = W.t_vers_jour_heure(T)
            self.assertEqual(W.jour_heure_vers_t(jour, heure, minute), T,
                             f"T={T} not reconstructed")

    def test_bornes_journee(self):
        # 144 UT = exactly one day: T=143 stays Day 1 (23h50), T=144 flips to Day 2.
        self.assertEqual(W.t_vers_jour_heure(143), (1, 23, 50))
        self.assertEqual(W.t_vers_jour_heure(144), (2, 0, 0))

    def test_minutes_dans_journee(self):
        # minute ∈ {0,10,20,30,40,50} only.
        for T in range(0, 144):
            _, _, minute = W.t_vers_jour_heure(T)
            self.assertIn(minute, (0, 10, 20, 30, 40, 50))


class TestNarratif(unittest.TestCase):

    def test_narratif_tranches(self):
        # A few key hours from the pinned time slots (§3.3).
        cas = {
            0: "nuit",            # 00h
            6: "aube",            # 06h
            10: "matin",          # 10h
            12: "midi",           # 12h
            16: "après-midi",     # 16h
            18: "fin d'après-midi",  # 18h
            20: "soir",           # 20h
            23: "nuit",           # 23h
        }
        for heure, libelle in cas.items():
            T = W.jour_heure_vers_t(1, heure, 0)
            self.assertIn(libelle, W.t_vers_narratif(T),
                          f"incorrect time slot at {heure}h")

    def test_narratif_format_jour(self):
        # "Jour N, …" and NEVER the raw T.
        txt = W.t_vers_narratif(W.jour_heure_vers_t(58, 18, 0))
        self.assertTrue(txt.startswith("Jour 58, "), txt)
        self.assertIn("fin d'après-midi", txt)


class TestDureesEtUT(unittest.TestCase):

    def test_minutes_vers_ut_valeurs_figees(self):
        # PINNED values from the contract (§3.3 / §12).
        self.assertEqual(W.minutes_vers_ut(40), 4)
        self.assertEqual(W.minutes_vers_ut(20), 2)
        self.assertEqual(W.minutes_vers_ut(90), 9)

    def test_minutes_vers_ut_arrondi_banquier_et_minimum(self):
        # round() "Steward" (banker's rounding): 5min → 0.5 UT rounded to even → 0, but the
        # FORCED minimum is 1 when minutes > 0 (a travel never lasts 0 UT).
        self.assertEqual(W.minutes_vers_ut(5), 1)
        self.assertEqual(W.minutes_vers_ut(1), 1)
        # 0 or negative → 0 (no duration).
        self.assertEqual(W.minutes_vers_ut(0), 0)
        self.assertEqual(W.minutes_vers_ut(-30), 0)
        # 345 min = 34.5 → banker's rounding to even → 34.
        self.assertEqual(W.minutes_vers_ut(345), 34)

    def test_parser_duree_minutes_formats(self):
        cas = {
            "2h": 120,
            "30min": 30,
            "1h30": 90,
            "1h30min": 90,
            "~4h": 240,
            "5h45 — desc": 345,
            "20min": 20,
        }
        for texte, attendu in cas.items():
            self.assertEqual(W.parser_duree_minutes(texte), attendu,
                             f"incorrect parsing for « {texte} »")

    def test_parser_duree_minutes_non_parsable(self):
        for texte in ("Distance inconnue", "", "à vol d'oiseau", "plusieurs jours"):
            self.assertEqual(W.parser_duree_minutes(texte), -1,
                             f"should be non-parsable: « {texte} »")


# ════════════════════════════════════════════════════════════════════════════
# 3.2 — Slug, safe JSON, atomic write
# ════════════════════════════════════════════════════════════════════════════

class TestSlug(unittest.TestCase):

    def test_slug_exemples_figes(self):
        # PINNED examples from the contract (§2.1 / §12).
        self.assertEqual(W.slug("Cabane de Berthe"), "cabane-de-berthe")
        self.assertEqual(W.slug("Sceau n°6 — Limite Nord"), "sceau-n-6-limite-nord")

    def test_slug_deterministe(self):
        # Idempotence + determinism: two calls return the same result.
        s1 = W.slug("Sceau n°6 — Limite Nord")
        s2 = W.slug("Sceau n°6 — Limite Nord")
        self.assertEqual(s1, s2)

    def test_slug_preserve_hierarchie(self):
        # The '/' (level separators) are PRESERVED, the rest is slugified.
        self.assertEqual(
            W.slug("lieu:marche-aux-trois-rivieres/Vallée du Cœur"),
            "lieu-marche-aux-trois-rivieres/vallee-du-c-ur",
        )

    def test_slug_diacritiques_et_squeeze(self):
        self.assertEqual(W.slug("Éléonore   d'Argent!!"), "eleonore-d-argent")
        self.assertEqual(W.slug("---bord---"), "bord")
        self.assertEqual(W.slug(""), "")


class TestJsonSur(unittest.TestCase):

    def test_charger_json_absent_renvoie_defaut(self):
        # Fail-open: missing file → default, never raises.
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "absent.json"
            self.assertEqual(W.charger_json(p, {"ok": True}), {"ok": True})
            self.assertIsNone(W.charger_json(p))

    def test_charger_json_corrompu_renvoie_defaut(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "casse.json"
            p.write_text("{ ceci n'est pas du JSON ", encoding="utf-8")
            self.assertEqual(W.charger_json(p, []), [])

    def test_sauver_json_atomique_roundtrip(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "sous" / "data.json"   # also creates the subdirectory
            donnees = {"é": 1, "liste": [1, 2, 3], "accent": "Cœur"}
            W.sauver_json_atomique(p, donnees)
            self.assertTrue(p.exists())
            texte = p.read_text(encoding="utf-8")
            self.assertTrue(texte.endswith("\n"), "doit finir par un saut de ligne")
            self.assertIn("Cœur", texte, "ensure_ascii=False : accents conservés bruts")
            self.assertEqual(W.charger_json(p), donnees)

    def test_sauver_json_atomique_pas_de_tmp_residuel(self):
        # After a successful write, no temporary file should remain.
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "data.json"
            W.sauver_json_atomique(p, {"a": 1})
            restants = [f for f in os.listdir(d) if f != "data.json"]
            self.assertEqual(restants, [], f"residual tmp: {restants}")

    def test_chemin_campagne_absolu(self):
        res = W.chemin_campagne("data/mj-tonnerre/campagnes/la-naissance-dun-roi")
        self.assertTrue(res.is_absolute(), "chemin_campagne doit rendre un Path absolu")


# ════════════════════════════════════════════════════════════════════════════
# 3.4 / 3.5 — Graph: containment and adjacency
# ════════════════════════════════════════════════════════════════════════════

class TestContenance(unittest.TestCase):

    def setUp(self):
        self.geo = _geo_jouet()

    def test_index_lieux(self):
        idx = W.index_lieux(self.geo)
        self.assertIn("A", idx)
        self.assertIn("region:test", idx)
        self.assertEqual(idx["B"]["nom"], "Lieu B")

    def test_parents_chaine_ascendante(self):
        # B_INT ⊂ B ⊂ region:test (B's parent is the region).
        self.assertEqual(W.parents(self.geo, "B_INT"), ["B", "region:test"])
        self.assertEqual(W.parents(self.geo, "A"), ["region:test"])
        # Root: no ascent.
        self.assertEqual(W.parents(self.geo, "region:test"), [])
        # Unknown: empty list (fail-open).
        self.assertEqual(W.parents(self.geo, "inexistant"), [])

    def test_contenus_directs_et_recursifs(self):
        directs = set(W.contenus(self.geo, "region:test"))
        self.assertEqual(directs, {"A", "B", "C", "D"})  # NOT B_INT (under B)
        # B contains B_INT.
        self.assertEqual(W.contenus(self.geo, "B"), ["B_INT"])
        # Recursive from the region: includes B_INT.
        rec = set(W.contenus(self.geo, "region:test", recursif=True))
        self.assertEqual(rec, {"A", "B", "C", "D", "B_INT"})

    def test_lieu_racine(self):
        self.assertEqual(W.lieu_racine(self.geo, "B_INT"), "region:test")
        self.assertEqual(W.lieu_racine(self.geo, "A"), "region:test")
        # A root returns itself.
        self.assertEqual(W.lieu_racine(self.geo, "region:test"), "region:test")
        # Unknown → None.
        self.assertIsNone(W.lieu_racine(self.geo, "inexistant"))


class TestAdjacenceChemins(unittest.TestCase):

    def setUp(self):
        self.geo = _geo_jouet()

    def test_voisins_ids(self):
        self.assertEqual(W.voisins_ids(self.geo, "A"), ["B"])
        # C has no declared outgoing edge.
        self.assertEqual(W.voisins_ids(self.geo, "C"), [])

    def test_aretes_sortantes(self):
        ar = W.aretes_sortantes(self.geo, "A")
        self.assertEqual(len(ar), 1)
        self.assertEqual(ar[0]["vers"], "B")
        self.assertEqual(ar[0]["temps_ut"], 6)

    def test_plus_court_chemin_direct(self):
        res = W.plus_court_chemin(self.geo, "A", "B")
        self.assertEqual(res["chemin"], ["A", "B"])
        self.assertEqual(res["temps_ut"], 6)
        self.assertEqual(res["distance_m"], 100)

    def test_plus_court_chemin_multi_sauts(self):
        # A → B → C: two edges of 6 UT.
        res = W.plus_court_chemin(self.geo, "A", "C")
        self.assertEqual(res["chemin"], ["A", "B", "C"])
        self.assertEqual(res["temps_ut"], 12)

    def test_plus_court_chemin_bidirectionnel(self):
        # "outbound = return": C → A must exist at the same cost even though no edge
        # is declared IN the return direction.
        res = W.plus_court_chemin(self.geo, "C", "A")
        self.assertEqual(res["temps_ut"], 12)
        self.assertEqual(res["chemin"], ["C", "B", "A"])

    def test_plus_court_chemin_identite(self):
        res = W.plus_court_chemin(self.geo, "B", "B")
        self.assertEqual(res["temps_ut"], 0)
        self.assertEqual(res["chemin"], ["B"])

    def test_plus_court_chemin_deconnecte(self):
        # D is isolated: no path.
        res = W.plus_court_chemin(self.geo, "A", "D")
        self.assertEqual(res["temps_ut"], -1)
        self.assertEqual(res["chemin"], [])
        self.assertEqual(W.distance_graphe_ut(self.geo, "A", "D"), -1)

    def test_plus_court_chemin_inconnu(self):
        self.assertEqual(W.plus_court_chemin(self.geo, "A", "ZZZ")["temps_ut"], -1)

    def test_distance_graphe_ut(self):
        self.assertEqual(W.distance_graphe_ut(self.geo, "A", "C"), 12)

    def test_distance_vol_oiseau(self):
        # Anchors A(0,0) and C(120,0) → Euclidean distance = 120.
        self.assertAlmostEqual(W.distance_vol_oiseau(self.geo, "A", "C"), 120.0)
        # Unknown id → -1.0.
        self.assertEqual(W.distance_vol_oiseau(self.geo, "A", "ZZZ"), -1.0)


# ════════════════════════════════════════════════════════════════════════════
# 3.6 — Anchor MDS (SMACOF stdlib): quality + determinism
# ════════════════════════════════════════════════════════════════════════════

class TestMDS(unittest.TestCase):

    def test_matrice_durees_carre_jouet(self):
        # Four corners of a square (durations in minutes) → symmetric matrix, diag 0.
        # Labels are resolved via a labels→id index passed explicitly
        # (matrice_durees no longer guesses the geography: it receives it).
        dep = {
            "depuis_a_vers": {
                "b": "40min",
                "c": "20min",
                "d": "1h30",
            },
        }
        idx = {lab: f"lieu:test/{lab}" for lab in ("a", "b", "c", "d")}
        ids, D = W.matrice_durees(dep, idx)
        self.assertGreaterEqual(len(ids), 3)
        n = len(ids)
        for i in range(n):
            self.assertEqual(D[i][i], 0.0)
            for j in range(n):
                self.assertAlmostEqual(D[i][j], D[j][i], msg="non-symmetric matrix")
                self.assertFalse(math.isinf(D[i][j]), "no cell should remain infinite")

    def test_mds_deterministe_seed(self):
        # Same seed → IDENTICAL coordinates (reproducibility, contract guarantee).
        dep = {
            "depuis_a_vers": {
                "b": "40min",
                "c": "20min",
                "d": "1h30",
                "e": "1h30",
            },
        }
        idx = {lab: f"lieu:test/{lab}" for lab in ("a", "b", "c", "d", "e")}
        ids, D = W.matrice_durees(dep, idx)
        c1 = W.ancrer_mds(ids, D, iterations=200, seed=42)
        c2 = W.ancrer_mds(ids, D, iterations=200, seed=42)
        self.assertEqual(c1, c2, "MDS non-deterministic with fixed seed")
        # Centroid ≈ origin (centered).
        sx = sum(v["x"] for v in c1.values())
        sy = sum(v["y"] for v in c1.values())
        self.assertLessEqual(abs(sx), len(ids), "centroid x not recentered")
        self.assertLessEqual(abs(sy), len(ids), "centroid y not recentered")

    def test_mds_cas_limites(self):
        # 0 locations → {}; 1 location → (0,0).
        self.assertEqual(W.ancrer_mds([], []), {})
        self.assertEqual(W.ancrer_mds(["seul"], [[0.0]]), {"seul": {"x": 0, "y": 0}})

    def test_stress_normalise_matrice_reelle_sous_seuil(self):
        # MANDATORY CASE (§12): on the REAL campaign matrix, the normalised stress
        # of a coarse anchor must remain below 0.30.
        if not (CAMPAGNE_REELLE / "monde.json").exists():
            self.skipTest("real campaign absent")
        monde = W.charger_json(CAMPAGNE_REELLE / "monde.json", {})
        dep = monde.get("regles", {}).get("temps", {}).get("deplacements")
        self.assertTrue(dep, "regles.temps.deplacements not found in monde.json")
        # The labels→id index is built FROM monde.json (names + aliases).
        idx = W.index_labels(monde)
        ids, D = W.matrice_durees(dep, idx)
        self.assertGreaterEqual(len(ids), 10, "too few locations extracted")
        coords = W.ancrer_mds(ids, D, iterations=300, seed=42)
        stress = W.stress_normalise(ids, D, coords)
        self.assertLess(stress, 0.30,
                        f"MDS stress too high on real data: {stress:.4f}")
        self.assertGreaterEqual(stress, 0.0)

    def test_mds_preserve_ordre_proximite(self):
        # Property ACTUALLY guaranteed by this coarse anchor (and the one on which
        # downstream code depends — crossing, dans_rayon, proximity sort): the ORDER
        # of proximities is preserved. On a collinear chain P0-P1-P2-P3
        # (10 UT per hop), the anchor distance must grow monotonically with the
        # graph distance (P1 closer to P0 than P2, itself closer than P3).
        # NOTE: raw normalised stress is NOT a good criterion here because
        # this MDS reconstructs the SHAPE but not the absolute SCALE (coordinates
        # explicitly "non-metric", code-only use, cf. §3.6); the sole
        # numerical milestone in the contract is the real matrix (test above).
        geo = {
            "lieux": [
                {"id": "P0", "parent": None, "ancrage": {"x": 0, "y": 0},
                 "aretes": [{"vers": "P1", "dir": "E", "temps_ut": 10,
                             "distance_m": None}]},
                {"id": "P1", "parent": None, "ancrage": {"x": 0, "y": 0},
                 "aretes": [{"vers": "P2", "dir": "E", "temps_ut": 10,
                             "distance_m": None}]},
                {"id": "P2", "parent": None, "ancrage": {"x": 0, "y": 0},
                 "aretes": [{"vers": "P3", "dir": "E", "temps_ut": 10,
                             "distance_m": None}]},
                {"id": "P3", "parent": None, "ancrage": {"x": 0, "y": 0},
                 "aretes": []},
            ],
        }
        ids, D = W.matrice_durees(geo)
        coords = W.ancrer_mds(ids, D, iterations=300, seed=42)
        # All coordinates are finite integers.
        for nid, xy in coords.items():
            self.assertIsInstance(xy["x"], int)
            self.assertIsInstance(xy["y"], int)

        def d_anc(a, b):
            return math.hypot(coords[a]["x"] - coords[b]["x"],
                              coords[a]["y"] - coords[b]["y"])

        # Monotonicity of proximities from P0: d(P0,P1) < d(P0,P2) < d(P0,P3).
        self.assertLess(d_anc("P0", "P1"), d_anc("P0", "P2"),
                        "direct neighbor must be anchored closer than the next")
        self.assertLess(d_anc("P0", "P2"), d_anc("P0", "P3"),
                        "the anchor must preserve the order of graph distances")


# ════════════════════════════════════════════════════════════════════════════
# 3.7 — Trajectories: position_a and valider_trajectoire
# ════════════════════════════════════════════════════════════════════════════

class TestPositionA(unittest.TestCase):

    def setUp(self):
        self.geo = _geo_jouet()
        # Stay at A [0,10), travel A→B [10,16), stay at B [16,∞).
        self.traj = [
            {"lieu": "A", "de": 0, "a": 10},
            {"type": "deplacement", "de": 10, "a": 16, "chemin": ["A", "B"],
             "motif": "test"},
            {"lieu": "B", "de": 16, "a": None},
        ]

    def test_position_sejour(self):
        p = W.position_a(self.geo, self.traj, 5)
        self.assertEqual(p["lieu"], "A")
        self.assertFalse(p["en_mouvement"])
        self.assertEqual((p["x"], p["y"]), (0.0, 0.0))

    def test_position_deplacement_interpole(self):
        # At mid-travel (T=13, i.e. 50% of [10,16]), x must be ≈ 30 (between 0 and 60).
        p = W.position_a(self.geo, self.traj, 13)
        self.assertTrue(p["en_mouvement"])
        self.assertGreater(p["x"], 0.0)
        self.assertLess(p["x"], 60.0)
        self.assertAlmostEqual(p["x"], 30.0, delta=1.0)

    def test_position_apres_dernier(self):
        # After the last stay (a=null) → remains at the last location.
        p = W.position_a(self.geo, self.traj, 999)
        self.assertEqual(p["lieu"], "B")
        self.assertFalse(p["en_mouvement"])

    def test_position_avant_premier(self):
        # Negative T (before the 1st segment) → first location.
        p = W.position_a(self.geo, self.traj, -5)
        self.assertEqual(p["lieu"], "A")

    def test_position_trajectoire_vide(self):
        self.assertEqual(W.position_a(self.geo, [], 10), {})

    def test_position_borne_bascule(self):
        # At exactly T=16, the stay at B (and no longer the travel) is active.
        p = W.position_a(self.geo, self.traj, 16)
        self.assertEqual(p["lieu"], "B")
        self.assertFalse(p["en_mouvement"])


class TestValiderTrajectoire(unittest.TestCase):

    def setUp(self):
        self.geo = _geo_jouet()

    def test_trajectoire_valide(self):
        traj = [
            {"lieu": "A", "de": 0, "a": 10},
            {"type": "deplacement", "de": 10, "a": 16, "chemin": ["A", "B"]},
            {"lieu": "B", "de": 16, "a": None},
        ]
        self.assertEqual(W.valider_trajectoire(self.geo, traj), [])

    def test_detecte_trou(self):
        # a=10 then de=20: temporal gap.
        traj = [
            {"lieu": "A", "de": 0, "a": 10},
            {"lieu": "B", "de": 20, "a": None},
        ]
        violations = W.valider_trajectoire(self.geo, traj)
        self.assertTrue(any("time gap" in v.lower() for v in violations),
                        f"trou non détecté : {violations}")

    def test_detecte_chevauchement(self):
        # a=15 then de=10: overlap.
        traj = [
            {"lieu": "A", "de": 0, "a": 15},
            {"lieu": "B", "de": 10, "a": 20},
        ]
        violations = W.valider_trajectoire(self.geo, traj)
        self.assertTrue(any("overlap" in v.lower() for v in violations),
                        f"chevauchement non détecté : {violations}")

    def test_detecte_teleportation(self):
        # Travel A→B (cost 6 UT) but declared duration 2 UT: teleportation.
        traj = [
            {"lieu": "A", "de": 0, "a": 4},
            {"type": "deplacement", "de": 4, "a": 6, "chemin": ["A", "B"]},
            {"lieu": "B", "de": 6, "a": None},
        ]
        violations = W.valider_trajectoire(self.geo, traj)
        self.assertTrue(any("teleportation" in v.lower() for v in violations),
                        f"téléportation non détectée : {violations}")

    def test_detecte_reference_inconnue(self):
        traj = [{"lieu": "FANTOME", "de": 0, "a": None}]
        violations = W.valider_trajectoire(self.geo, traj)
        self.assertTrue(any("unknown" in v.lower() or "reference" in v.lower()
                            for v in violations),
                        f"référence inconnue non détectée : {violations}")

    def test_detecte_chemin_sans_arete(self):
        # A→C is not a DIRECT edge (must go through B).
        traj = [
            {"lieu": "A", "de": 0, "a": 10},
            {"type": "deplacement", "de": 10, "a": 30, "chemin": ["A", "C"]},
            {"lieu": "C", "de": 30, "a": None},
        ]
        violations = W.valider_trajectoire(self.geo, traj)
        self.assertTrue(any("no edge" in v.lower() or "edge" in v.lower()
                            for v in violations),
                        f"arête manquante non détectée : {violations}")

    def test_detecte_monotonie(self):
        # a < de within a segment.
        traj = [{"lieu": "A", "de": 10, "a": 5}]
        violations = W.valider_trajectoire(self.geo, traj)
        self.assertTrue(any("monotonicity" in v.lower() for v in violations),
                        f"violation de monotonie non détectée : {violations}")

    def test_trajectoire_vide_pas_de_violation(self):
        self.assertEqual(W.valider_trajectoire(self.geo, []), [])


# ════════════════════════════════════════════════════════════════════════════
# 3.8 — Actors and relations
# ════════════════════════════════════════════════════════════════════════════

class TestActeursRelations(unittest.TestCase):

    def setUp(self):
        self.acteurs = _acteurs_jouet()

    def test_index_acteurs(self):
        idx = W.index_acteurs(self.acteurs)
        self.assertIn("acteur:alpha", idx)
        self.assertIn("acteur:beta", idx)

    def test_trajectoire_de_directe(self):
        idx = W.index_acteurs(self.acteurs)
        traj = W.trajectoire_de(idx["acteur:alpha"])
        self.assertEqual(traj, [{"lieu": "A", "de": 0, "a": None}])

    def test_trajectoire_de_retrocompat_localisation(self):
        # beta has no 'trajectoire' but has a 'localisation_id' → synthetic stay.
        idx = W.index_acteurs(self.acteurs)
        traj = W.trajectoire_de(idx["acteur:beta"])
        self.assertEqual(len(traj), 1)
        self.assertEqual(traj[0]["lieu"], "B")
        self.assertEqual(traj[0]["de"], 0)
        self.assertIsNone(traj[0]["a"])

    def test_trajectoire_de_absente(self):
        self.assertEqual(W.trajectoire_de({"id": "x"}), [])

    def test_relations_de(self):
        idx = W.index_acteurs(self.acteurs)
        rels = W.relations_de(idx["acteur:alpha"])
        self.assertEqual(len(rels), 2)
        self.assertEqual(rels[0]["vers"], "acteur:beta")

    def test_relations_vers(self):
        # Who points to alpha? → beta (alliance).
        sources = W.relations_vers(self.acteurs, "acteur:alpha")
        self.assertEqual(len(sources), 1)
        src_id, rel = sources[0]
        self.assertEqual(src_id, "acteur:beta")
        self.assertEqual(rel["type"], "alliance")
        # Who points to location C? → alpha (predation).
        vers_c = W.relations_vers(self.acteurs, "C")
        self.assertEqual([s for s, _ in vers_c], ["acteur:alpha"])


# ════════════════════════════════════════════════════════════════════════════
# 3.9 — Pinned deadlines (clock.py bridge)
# ════════════════════════════════════════════════════════════════════════════

class TestEcheanceEnT(unittest.TestCase):

    def test_int_deja_en_ut(self):
        self.assertEqual(W.echeance_en_t(3960, CAMPAGNE_REELLE), 3960)
        self.assertEqual(W.echeance_en_t(0, CAMPAGNE_REELLE), 0)

    def test_bool_rejete(self):
        # A boolean is an int in Python: it MUST NOT be taken as a deadline.
        self.assertIsNone(W.echeance_en_t(True, CAMPAGNE_REELLE))

    def test_format_epingle_jour(self):
        # {unite:'jour', max:21, ancre:7} → noon of day (7+21)=28 → 3960 (cf. §10).
        ech = {"texte": "Dans 2-3 semaines", "unite": "jour", "min": 14, "max": 21,
               "ancre": 7, "statut": "en_cours"}
        self.assertEqual(W.echeance_en_t(ech, CAMPAGNE_REELLE),
                         W.jour_heure_vers_t(28, 12, 0))
        self.assertEqual(W.echeance_en_t(ech, CAMPAGNE_REELLE), 3960)

    def test_format_epingle_ut(self):
        # {unite:'ut', max:100, ancre:936} → 1036 (direct sum in UT).
        ech = {"texte": "bientôt", "unite": "ut", "min": 50, "max": 100, "ancre": 936}
        self.assertEqual(W.echeance_en_t(ech, CAMPAGNE_REELLE), 1036)

    def test_format_epingle_borne_haute(self):
        # Without 'max', 'min' acts as the upper bound.
        ech = {"texte": "x", "unite": "jour", "min": 5, "ancre": 0}
        self.assertEqual(W.echeance_en_t(ech, CAMPAGNE_REELLE),
                         W.jour_heure_vers_t(5, 12, 0))

    def test_chaine_libre_non_datable(self):
        self.assertIsNone(W.echeance_en_t("Dans 2-3 semaines de jeu", CAMPAGNE_REELLE))
        self.assertIsNone(W.echeance_en_t(None, CAMPAGNE_REELLE))


# ════════════════════════════════════════════════════════════════════════════
# 3.3 — t_courant on the real campaign (read-only, deterministic, fail-open)
# ════════════════════════════════════════════════════════════════════════════

class TestTCourant(unittest.TestCase):

    def test_t_courant_fail_open_campagne_vide(self):
        # No file → 0 (never raises).
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(W.t_courant(Path(d)), 0)

    def test_t_courant_priorite_evenements_programmes(self):
        # Rule 1 (§3.3): the max of integer T values in evenements_programmes.json wins.
        with tempfile.TemporaryDirectory() as d:
            camp = Path(d)
            prog = {"meta": {}, "evenements": [
                {"id": "e1", "T": 5000, "type": "x", "cible": "y", "cause": "—",
                 "significativite": 0.5, "statut": "resolu"},
                {"id": "e2", "T": 7200, "type": "x", "cible": "y", "cause": "—",
                 "significativite": 0.5, "statut": "resolu"},
            ]}
            W.sauver_json_atomique(camp / "evenements_programmes.json", prog)
            # Even with a "Day 3" world present, the integer T values win.
            W.sauver_json_atomique(
                camp / "monde.json",
                {"etat_global": {"chronologie": "On en est au Jour 3."}})
            self.assertEqual(W.t_courant(camp), 7200)

    def test_t_courant_derive_jour_narratif(self):
        # Rule 2: without scheduled events, derive from the max "Day N" → noon.
        with tempfile.TemporaryDirectory() as d:
            camp = Path(d)
            W.sauver_json_atomique(
                camp / "monde.json",
                {"etat_global": {"chronologie": "Jour 1 ... puis Jour 9 enfin."}})
            self.assertEqual(W.t_courant(camp), W.jour_heure_vers_t(9, 12, 0))

    def test_t_courant_campagne_reelle_coherent(self):
        # On the REAL campaign: an integer ≥ 936 (at least Day 7), aligned to noon
        # of a whole day (multiple of 144 + 72) OR from a scheduled event.
        if not CAMPAGNE_REELLE.is_dir():
            self.skipTest("real campaign absent")
        t = W.t_courant(CAMPAGNE_REELLE)
        self.assertIsInstance(t, int)
        self.assertGreaterEqual(t, 936, "the real campaign is at least at Day 7")
        # Reproducible.
        self.assertEqual(t, W.t_courant(CAMPAGNE_REELLE))


if __name__ == "__main__":
    unittest.main(verbosity=2)
