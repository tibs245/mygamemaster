#!/usr/bin/env python3
"""
test_scene_brief.py — Tests for the context assembler « BRIEF DE SCÈNE » (contract §12).

STDLIB `unittest` (no pytest required). Run from `scripts/`:
    python3 -m unittest discover
or from the repository root:
    python3 -m unittest modules.gaming.mj-tonnerre.scripts.tests.test_scene_brief -v

MANDATORY cases (contract §12, last bullet):
  * scene_brief on …/cabane-berthe returns the expected template (columns present);
  * never any (x,y) nor « T= » not preceded by the narrative in `texte`;
  * fail-open: campaign without geo.json → minimal brief, code 0.

Also (component coverage, contract §9 / §14):
  * public signature §9.1: all keys of the return dict present/typed;
  * three axes: SPATIAL (autour/presents), TEMPORAL (recent/imminent),
    RELATIONAL (stakes toward the location + toward the PC, movement/crossings);
  * text rendering: EXACT labels, Unicode frame, header « T=<int> (<narrative>) »,
    « ⏰ » for scheduled events, NARRATIVE durations;
  * strict fail-open (game loop): empty folder / unknown location → never an exception;
  * CLI: text by default, --json (purge of internal fields), codes 0 / 2;
  * NON DESTRUCTIVE: no writes (geo/acteurs/evenements*/monde) — verified.

Data: the real campaign `…/la-naissance-dun-roi` in READ-ONLY for nominal cases,
and throwaway fixtures (tmp copy + inline JSON) to deterministically exercise
IMMINENT / RECENT / MOVEMENT (the real world does not yet have
`scheduled_events.json` nor an actor in movement at `t_courant`).
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

# sys.path: add `scripts/` (parent of tests/) to import worldlib,
# geo_query, scene_brief as existing tests do (cf. test_causal_propagate.py).
SCRIPTS_DIR = Path(__file__).resolve().parent.parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import scene_brief as SB          # noqa: E402
import worldlib as W              # noqa: E402


CAMPAGNE_REELLE = Path(os.environ.get(
    "MJ_TEST_CAMPAIGN",
    str(Path(__file__).resolve().parents[5] / "data" / "mj-tonnerre" / "campaigns" / "la-naissance-dun-roi"),
))

# PC from the real campaign, resolved GENERICALLY (meta.pj_ids > meta.pj_id) — no
# more hardcoded constant in scene_brief: we read the ids as the engine does at
# runtime. PJ_REEL = the first PC (backwards-compat); PJ_REELS = the full set.
PJ_REEL = W.pj_id(W.charger_json(CAMPAGNE_REELLE / "world.json", {}) or {})
PJ_REELS = set(W.pj_ids(W.charger_json(CAMPAGNE_REELLE / "world.json", {}) or {}))

# Pivot location of the vertical slice (cf. contract §10): target of the winter raid.
LIEU_CABANE = "lieu:marche-aux-trois-rivieres/cabane-berthe"
LIEU_GUE = "lieu:marche-aux-trois-rivieres/gue-du-corbeau"
LIEU_MAISON = "lieu:marche-aux-trois-rivieres/maison-pierre"

# EXACT keys of the return contract (contract §9.1) — excluding internal « _… » fields.
CLES_CONTRAT = {
    "T", "lieu", "autour", "contenus", "presents",
    "mouvement", "recent", "imminent", "enjeux", "texte",
}

# EXACT column labels of the text template (contract §9.2).
COLONNES = ["LOCATION", "AROUND", "PRESENT", "MOVEMENT", "RECENT", "IMMINENT", "STAKES"]


def _campagne_reelle_dispo() -> bool:
    return CAMPAGNE_REELLE.is_dir() and (CAMPAGNE_REELLE / "geo.json").exists()


def _copier_campagne(racine_tmp: Path) -> Path:
    """Copy the real campaign into a throwaway tmp directory (for non-destructive fixtures)."""
    dest = racine_tmp / "camp"
    shutil.copytree(CAMPAGNE_REELLE, dest)
    return dest


# ════════════════════════════════════════════════════════════════════════════
#  1. Public signature (contract §9.1) — shape and types of the return dict
# ════════════════════════════════════════════════════════════════════════════

class TestContratRetour(unittest.TestCase):
    """scene_brief returns a dict conforming to contract §9.1 (keys + types)."""

    @classmethod
    def setUpClass(cls):
        if not _campagne_reelle_dispo():
            raise unittest.SkipTest("real campaign (geo.json) absent")
        cls.brief = SB.scene_brief(CAMPAGNE_REELLE, LIEU_CABANE)

    def test_clefs_du_contrat_presentes(self):
        # All keys from contract §9.1 are present (internal « _… » fields may
        # also be present, but the contract must be fully covered).
        self.assertTrue(
            CLES_CONTRAT.issubset(set(self.brief.keys())),
            f"missing keys: {CLES_CONTRAT - set(self.brief.keys())}")

    def test_types_des_champs(self):
        b = self.brief
        self.assertIsInstance(b["T"], int)
        self.assertEqual(b["lieu"], LIEU_CABANE)
        for clef in ("autour", "contenus", "presents", "mouvement",
                     "recent", "imminent", "enjeux"):
            self.assertIsInstance(b[clef], list, f"{clef} must be a list")
        self.assertIsInstance(b["texte"], str)
        self.assertTrue(b["texte"], "the brief text must not be empty")

    def test_t_par_defaut_est_t_courant(self):
        # Default T = worldlib.t_courant (contract §9.1).
        self.assertEqual(self.brief["T"], W.t_courant(CAMPAGNE_REELLE))

    def test_t_explicite_respecte(self):
        b = SB.scene_brief(CAMPAGNE_REELLE, LIEU_CABANE, T=2376)
        self.assertEqual(b["T"], 2376)


# ════════════════════════════════════════════════════════════════════════════
#  2. SPATIAL axis — AUTOUR (edges) + PRÉSENTS (actors at location / radius)
# ════════════════════════════════════════════════════════════════════════════

class TestAxeSpatial(unittest.TestCase):
    """AUTOUR and PRÉSENTS reflect the graph and actors from the real campaign."""

    @classmethod
    def setUpClass(cls):
        if not _campagne_reelle_dispo():
            raise unittest.SkipTest("real campaign (geo.json) absent")
        cls.brief = SB.scene_brief(CAMPAGNE_REELLE, LIEU_CABANE)

    def test_autour_non_vide_et_bien_forme(self):
        # Berthe's cabin has several outgoing edges (cf. geo.json §5).
        autour = self.brief["autour"]
        self.assertGreater(len(autour), 0, "the cabin has neighbours")
        for a in autour:
            self.assertIn("vers", a)
            self.assertIn("dir", a)
            self.assertIn("distance_m", a)
            self.assertIn("temps_ut", a)

    def test_autour_contient_voisins_connus(self):
        cibles = {a.get("vers") for a in self.brief["autour"]}
        # Real direct neighbours of the cabin (cf. contract §5 example).
        self.assertIn("lieu:marche-aux-trois-rivieres/cabane-firmin", cibles)
        self.assertIn("lieu:marche-aux-trois-rivieres/bois-des-charmes", cibles)

    def test_presents_inclut_berthe(self):
        # Berthe is located at her cabin (actors.json §10) → present.
        ids = {p.get("id") for p in self.brief["presents"]}
        self.assertIn("acteur:berthe", ids)

    def test_presents_bien_formes(self):
        for p in self.brief["presents"]:
            self.assertIn("id", p)
            self.assertIn("name", p)
            self.assertIn("type", p)


# ════════════════════════════════════════════════════════════════════════════
#  3. RELATIONAL axis — ENJEUX (toward the location + toward PC Rubis)
# ════════════════════════════════════════════════════════════════════════════

class TestAxeRelationnel(unittest.TestCase):
    """ENJEUX = relations pointing toward the location OR toward acteur:rubis (the PC)."""

    @classmethod
    def setUpClass(cls):
        if not _campagne_reelle_dispo():
            raise unittest.SkipTest("real campaign (geo.json) absent")
        cls.brief = SB.scene_brief(CAMPAGNE_REELLE, LIEU_CABANE)

    def test_enjeux_non_vide(self):
        self.assertGreater(len(self.brief["enjeux"]), 0)

    def test_enjeux_vers_le_pj(self):
        # Several actors have a relation toward the PC (Berthe alliance .8…).
        self.assertIsNotNone(PJ_REEL, "the real campaign declares meta.pj_ids")
        vers_pj = [e for e in self.brief["enjeux"] if e.get("_vers") == PJ_REEL]
        self.assertTrue(vers_pj, "some stakes must point toward the PC (Rubis)")
        # The rendering flag _vers_pj must also be set (FIX 1).
        self.assertTrue(all(e.get("_vers_pj") for e in vers_pj))
        srcs = {e["acteur"] for e in vers_pj}
        self.assertIn("acteur:berthe", srcs)

    def test_enjeux_vers_le_lieu(self):
        # Berthe has a 'tutelle' relation toward the cabin (actors.json §10).
        vers_lieu = [e for e in self.brief["enjeux"] if e.get("_vers") == LIEU_CABANE]
        self.assertTrue(vers_lieu, "des enjeux doivent pointer vers le lieu")
        self.assertTrue(any(e["acteur"] == "acteur:berthe" and e["type"] == "tutelle"
                            for e in vers_lieu))

    def test_enjeux_tries_par_intensite_decroissante(self):
        intens = [e.get("intensite") or 0.0 for e in self.brief["enjeux"]]
        self.assertEqual(intens, sorted(intens, reverse=True),
                         "ENJEUX sorted by descending intensity")

    def test_enjeux_dedupliques(self):
        cles = [(e["acteur"], e["type"], e.get("_vers")) for e in self.brief["enjeux"]]
        self.assertEqual(len(cles), len(set(cles)), "no duplicate stake")


# ════════════════════════════════════════════════════════════════════════════
#  3bis. RELATIONAL axis — MULTI-PC campaign (meta.pj_ids: Oscar AND Cendre)
# ════════════════════════════════════════════════════════════════════════════

class TestAxeRelationnelMultiPj(unittest.TestCase):
    """Relations toward ANY of the PCs feed ENJEUX (_vers_pj=True),
    and ALL pj_ids are excluded from MOUVEMENT. Self-contained synthetic campaign.
    """

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.camp = Path(self._tmp.name)
        (self.camp / "sessions").mkdir(parents=True, exist_ok=True)
        # minimal geo: one scene location + one location from which an actor travels.
        geo = {
            "meta": {"campagne": "multi-pj"},
            "locations": [
                {"id": "lieu:scene", "parent": None, "ancrage": {"x": 0, "y": 0},
                 "aretes": [{"vers": "lieu:loin", "dir": "E",
                             "temps_ut": 6, "distance_m": 100}]},
                {"id": "lieu:loin", "parent": None, "ancrage": {"x": 60, "y": 0},
                 "aretes": []},
            ],
        }
        W.sauver_json_atomique(self.camp / "geo.json", geo)
        # Two PCs declared in canonical list (e.g. Oscar AND Cendre).
        W.sauver_json_atomique(self.camp / "world.json", {
            "meta": {"name": "MultiPJ", "pj_ids": ["acteur:oscar", "acteur:cendre"]},
            "global_state": {"chronologie": "Jour 7 : début."},
        })
        # Actors:
        #  - garde: 'serment' relation toward the SECOND PC (Cendre) → without the
        #    generalisation, this relation would NOT appear in ENJEUX;
        #  - oscar/cendre: PCs, one moving toward the scene (must be EXCLUDED).
        acteurs = {
            "meta": {"campagne": "multi-pj", "version": 1},
            "acteurs": [
                {"id": "acteur:garde", "name": "Le Garde", "type": "pnj",
                 "majeur": True, "trajectoire": [{"lieu": "lieu:scene", "de": 0, "a": None}],
                 "relations": [{"vers": "acteur:cendre", "type": "serment",
                                "intensite": 0.7}]},
                {"id": "acteur:oscar", "name": "Oscar", "type": "pnj", "majeur": True,
                 "trajectoire": [{"lieu": "lieu:scene", "de": 0, "a": None}],
                 "relations": []},
                # Cendre IN MOVEMENT toward the scene: would cross the location, but is a
                # PC → must NEVER appear in MOUVEMENT.
                {"id": "acteur:cendre", "name": "Cendre", "type": "pnj", "majeur": True,
                 "trajectoire": [
                     {"lieu": "lieu:loin", "de": 0, "a": 3},
                     {"type": "deplacement", "de": 3, "a": 9,
                      "chemin": ["lieu:loin", "lieu:scene"], "motif": "test"},
                     {"lieu": "lieu:scene", "de": 9, "a": None}],
                 "relations": []},
            ],
        }
        W.sauver_json_atomique(self.camp / "actors.json", acteurs)

    def tearDown(self):
        self._tmp.cleanup()

    def test_enjeux_vers_second_pj(self):
        # The 'serment' relation toward Cendre (2nd PC) MUST appear, marked _vers_pj.
        b = SB.scene_brief(self.camp, "lieu:scene", T=0)
        vers_cendre = [e for e in b["enjeux"] if e.get("_vers") == "acteur:cendre"]
        self.assertTrue(vers_cendre,
                        "a relation toward the 2nd PC must feed ENJEUX")
        self.assertTrue(all(e.get("_vers_pj") for e in vers_cendre))
        self.assertIn("acteur:garde", {e["acteur"] for e in vers_cendre})

    def test_mouvement_exclut_tous_les_pj(self):
        # Cendre is on her way to the scene but remains a PC → excluded from MOUVEMENT.
        b = SB.scene_brief(self.camp, "lieu:scene", T=0)
        acteurs_mvt = {m["acteur"] for m in b["mouvement"]}
        self.assertNotIn("acteur:cendre", acteurs_mvt)
        self.assertNotIn("acteur:oscar", acteurs_mvt)


# ════════════════════════════════════════════════════════════════════════════
#  4. TEMPORAL axis — RECENT / IMMINENT (with scheduled-events fixture)
# ════════════════════════════════════════════════════════════════════════════

class TestAxeTemporel(unittest.TestCase):
    """RECENT ([T−δ, T]) and IMMINENT ([T, T+δ]) — throwaway fixture of evenements_programmes."""

    def setUp(self):
        if not _campagne_reelle_dispo():
            self.skipTest("real campaign (geo.json) absent")
        self._tmp = tempfile.TemporaryDirectory()
        self.camp = _copier_campagne(Path(self._tmp.name))
        # Two scheduled events around T=1224 (Day 9):
        #   - a 'resolu' at T=1200  → RECENT
        #   - a 'programme' at T=1300 → IMMINENT
        progs = {
            "meta": {"campagne": "x", "version": 1, "note": "Ne JAMAIS fusionner"},
            "evenements": [
                {"id": "evt:raid-1300", "T": 1300, "type": "raid",
                 "cible": LIEU_CABANE, "cause": "intent:raid-hivernal",
                 "significativite": 0.6, "statut": "programme",
                 "label": "Raid imminent de la Bande"},
                {"id": "evt:rumeur-1200", "T": 1200, "type": "rumeur",
                 "cible": LIEU_GUE, "cause": "x", "significativite": 0.3,
                 "statut": "resolu", "label": "Rumeur au Gue"},
            ],
        }
        (self.camp / "scheduled_events.json").write_text(
            json.dumps(progs, ensure_ascii=False), encoding="utf-8")

    def tearDown(self):
        self._tmp.cleanup()

    def test_imminent_capture_le_programme(self):
        b = SB.scene_brief(self.camp, LIEU_CABANE, T=1224, fenetre_ut=432)
        labels = [i.get("label") for i in b["imminent"]]
        self.assertIn("Raid imminent de la Bande", labels)
        # Expected fields (contract §9.1): T + label + type.
        cible = next(i for i in b["imminent"] if i["label"] == "Raid imminent de la Bande")
        self.assertEqual(cible["T"], 1300)
        self.assertEqual(cible["type"], "raid")

    def test_recent_capture_le_resolu(self):
        b = SB.scene_brief(self.camp, LIEU_CABANE, T=1224, fenetre_ut=432)
        labels = [r.get("label") for r in b["recent"]]
        self.assertIn("Rumeur au Gue", labels)

    def test_imminent_trie_et_dans_la_fenetre(self):
        b = SB.scene_brief(self.camp, LIEU_CABANE, T=1224, fenetre_ut=432)
        ts = [i["T"] for i in b["imminent"]]
        self.assertEqual(ts, sorted(ts), "IMMINENT sorted by ascending T")
        for t in ts:
            self.assertGreaterEqual(t, 1224)
            self.assertLessEqual(t, 1224 + 432)

    def test_fenetre_etroite_exclut_evenement_lointain(self):
        # With a tiny δ, the raid at T=1300 (>1224+10) falls OUTSIDE the window.
        b = SB.scene_brief(self.camp, LIEU_CABANE, T=1224, fenetre_ut=10)
        labels = [i.get("label") for i in b["imminent"]]
        self.assertNotIn("Raid imminent de la Bande", labels)

    def test_texte_marque_imminent_par_horloge(self):
        b = SB.scene_brief(self.camp, LIEU_CABANE, T=1224, fenetre_ut=432)
        self.assertIn("IMMINENT", b["texte"])
        self.assertIn("⏰", b["texte"], "scheduled events carry the clock ⏰")


# ════════════════════════════════════════════════════════════════════════════
#  5. RELATIONAL axis — MOUVEMENT (crossing of an actor in motion)
# ════════════════════════════════════════════════════════════════════════════

class TestMouvementCroisement(unittest.TestCase):
    """MOUVEMENT: an actor whose trajectory CROSSES the location appears (fixture)."""

    def setUp(self):
        if not _campagne_reelle_dispo():
            self.skipTest("real campaign (geo.json) absent")
        self._tmp = tempfile.TemporaryDirectory()
        self.camp = _copier_campagne(Path(self._tmp.name))
        # Force Firmin to move toward the cabin just after T=1200:
        # maison-pierre → cabane-berthe (real graph edge).
        acteurs = W.charger_acteurs(self.camp)
        for a in acteurs["acteurs"]:
            if a["id"] == "acteur:firmin":
                a["trajectoire"] = [
                    {"lieu": LIEU_MAISON, "de": 0, "a": 1230},
                    {"type": "deplacement", "de": 1230, "a": 1290,
                     "chemin": [LIEU_MAISON, LIEU_CABANE], "motif": "test croisement"},
                    {"lieu": LIEU_CABANE, "de": 1290, "a": None},
                ]
        (self.camp / "actors.json").write_text(
            json.dumps(acteurs, ensure_ascii=False, indent=2), encoding="utf-8")

    def tearDown(self):
        self._tmp.cleanup()

    def test_mouvement_detecte_le_croisement(self):
        b = SB.scene_brief(self.camp, LIEU_CABANE, T=1200, fenetre_ut=432)
        acteurs_mvt = {m["acteur"] for m in b["mouvement"]}
        self.assertIn("acteur:firmin", acteurs_mvt,
                      "Firmin on his way to the cabin must appear in MOUVEMENT")
        m = next(m for m in b["mouvement"] if m["acteur"] == "acteur:firmin")
        for clef in ("acteur", "T", "lieu", "narratif"):
            self.assertIn(clef, m)

    def test_mouvement_exclut_le_pj(self):
        # No PC (resolved via meta.pj_ids) is a « mouvement-monde » (§2.5).
        b = SB.scene_brief(self.camp, LIEU_CABANE, T=1200, fenetre_ut=432)
        pj_set = set(W.pj_ids(W.charger_json(self.camp / "world.json", {}) or {}))
        acteurs_mvt = {m["acteur"] for m in b["mouvement"]}
        self.assertTrue(pj_set.isdisjoint(acteurs_mvt),
                        "no PC must appear in MOUVEMENT")

    def test_acteur_statique_n_apparait_pas_en_mouvement(self):
        # Berthe has a single permanent stay → no crossing window.
        b = SB.scene_brief(self.camp, LIEU_CABANE, T=1200, fenetre_ut=432)
        self.assertNotIn("acteur:berthe", {m["acteur"] for m in b["mouvement"]})


# ════════════════════════════════════════════════════════════════════════════
#  6. TEXT rendering — EXACT template of the BRIEF DE SCÈNE (contract §9.2)
# ════════════════════════════════════════════════════════════════════════════

class TestRenduTexte(unittest.TestCase):
    """The `texte` follows the fixed template: frame, header, EXACT labels, narrative."""

    @classmethod
    def setUpClass(cls):
        if not _campagne_reelle_dispo():
            raise unittest.SkipTest("real campaign (geo.json) absent")
        cls.brief = SB.scene_brief(CAMPAGNE_REELLE, LIEU_CABANE)
        cls.texte = cls.brief["texte"]

    def test_titre_brief_de_scene(self):
        self.assertIn("SCENE BRIEF", self.texte)

    def test_entete_T_suivi_du_narratif(self):
        # Header « T=<int> (<narrative>) »: the raw T is ALWAYS accompanied by the
        # narrative rendering in parentheses (cf. contract §9.2 + invariant 01§C).
        T = self.brief["T"]
        narr = W.t_vers_narratif(T)
        self.assertIn(f"T={T} ({narr})", self.texte)

    def test_cadre_unicode(self):
        # Framed box (corners + bars) — template §9.2.
        self.assertIn("┌", self.texte)
        self.assertIn("┐", self.texte)
        self.assertIn("└", self.texte)
        self.assertIn("┘", self.texte)
        self.assertTrue(self.texte.lstrip().startswith("┌"))
        self.assertTrue(self.texte.rstrip().endswith("┘"))

    def test_colonnes_obligatoires_presentes(self):
        # LOCATION is always present; AROUND/PRESENT/STAKES are present for the real cabin.
        for col in ("LOCATION", "AROUND", "PRESENT", "STAKES"):
            self.assertIn(col, self.texte, f"colonne {col} attendue")

    def test_libelles_de_colonnes_exacts(self):
        # No unexpected labels: every column label encountered (at the start of
        # a line's content) must belong to the fixed set from contract §9.2.
        autorises = set(COLONNES)
        for ligne in self.texte.splitlines():
            corps = ligne.strip("│ \t")
            tete = corps.split(" ", 1)[0] if corps else ""
            # Only test heads « in UPPERCASE » (column labels).
            if tete.isupper() and len(tete) >= 4 and tete.isalpha():
                self.assertIn(tete, autorises,
                              f"unexpected column label: {tete!r}")

    def test_pas_de_coordonnees_xy(self):
        # INVARIANT (contract §9.2 / 01§C): never expose (x,y) to the player.
        import re
        self.assertIsNone(re.search(r"\bx\s*[:=]\s*-?\d", self.texte),
                          "the text must NEVER expose an x coordinate")
        self.assertIsNone(re.search(r"\by\s*[:=]\s*-?\d", self.texte),
                          "the text must NEVER expose a y coordinate")
        # Also no anchor pair « (5, 22) ».
        self.assertIsNone(re.search(r"\(\s*-?\d+\s*,\s*-?\d+\s*\)", self.texte),
                          "the text must NEVER expose an anchor pair (x, y)")

    def test_un_seul_T_brut_dans_l_entete(self):
        # « T= » appears ONLY in the header (never in a PRÉSENTS/RÉCENT… column).
        self.assertEqual(self.texte.count("T="), 1,
                         "the raw T only appears in the header (followed by the narrative)")


# ════════════════════════════════════════════════════════════════════════════
#  7. Strict FAIL-OPEN (game loop) — contract §9 / §14.6
# ════════════════════════════════════════════════════════════════════════════

class TestFailOpen(unittest.TestCase):
    """No failure must crash scene_brief: coherent minimal brief."""

    def test_dossier_vide_donne_brief_minimal(self):
        # Campaign without geo.json/actors.json → minimal brief, never an exception.
        with tempfile.TemporaryDirectory() as d:
            camp = Path(d)
            b = SB.scene_brief(camp, "lieu:inconnu/xyz")
            self.assertEqual(b["lieu"], "lieu:inconnu/xyz")
            self.assertEqual(b["autour"], [])
            self.assertEqual(b["presents"], [])
            self.assertEqual(b["enjeux"], [])
            self.assertEqual(b["mouvement"], [])
            self.assertEqual(b["recent"], [])
            self.assertEqual(b["imminent"], [])
            # The minimal text still contains the frame + LOCATION.
            self.assertIn("SCENE BRIEF", b["texte"])
            self.assertIn("LOCATION", b["texte"])

    def test_lieu_inconnu_dans_campagne_reelle(self):
        if not _campagne_reelle_dispo():
            self.skipTest("real campaign (geo.json) absent")
        # A location id absent from the graph: no neighbour, no crash.
        b = SB.scene_brief(CAMPAGNE_REELLE, "lieu:marche-aux-trois-rivieres/n-existe-pas")
        self.assertEqual(b["lieu"], "lieu:marche-aux-trois-rivieres/n-existe-pas")
        self.assertEqual(b["autour"], [])
        self.assertIsInstance(b["texte"], str)
        self.assertIn("SCENE BRIEF", b["texte"])

    def test_t_negatif_ne_plante_pas(self):
        # Aberrant input: very negative T → fail-open, text produced.
        with tempfile.TemporaryDirectory() as d:
            b = SB.scene_brief(Path(d), LIEU_CABANE, T=-99999)
            self.assertEqual(b["T"], -99999)
            self.assertIsInstance(b["texte"], str)
            self.assertTrue(b["texte"])


# ════════════════════════════════════════════════════════════════════════════
#  8. NON DESTRUCTIVE — scene_brief NEVER writes any file (contract §0.2/§14.3)
# ════════════════════════════════════════════════════════════════════════════

class TestNonDestructif(unittest.TestCase):
    """Read-only: the campaign folder fingerprint is unchanged after a call."""

    def test_aucune_ecriture_sur_copie(self):
        if not _campagne_reelle_dispo():
            self.skipTest("real campaign (geo.json) absent")
        with tempfile.TemporaryDirectory() as d:
            camp = _copier_campagne(Path(d))

            def empreinte() -> dict:
                emp = {}
                for p in sorted(camp.iterdir()):
                    if p.is_file():
                        st = p.stat()
                        emp[p.name] = (st.st_size, st.st_mtime_ns)
                return emp

            avant = empreinte()
            # Multiple calls (text + json, varied T).
            SB.scene_brief(camp, LIEU_CABANE)
            SB.scene_brief(camp, LIEU_CABANE, T=2376)
            SB.scene_brief(camp, LIEU_GUE, T=1656)
            apres = empreinte()
            self.assertEqual(avant, apres,
                             "scene_brief must not create/modify ANY file")
            # In particular: no new scheduled file created.
            self.assertFalse((camp / "scheduled_events.json").exists())


# ════════════════════════════════════════════════════════════════════════════
#  9. Internal helpers — temporal bridge & labels (edge cases)
# ════════════════════════════════════════════════════════════════════════════

class TestHelpersInternes(unittest.TestCase):
    """Small deterministic bridges (narrative renderings, reverse text dating)."""

    def test_t_textuel_vers_t_jour_et_tranche(self):
        # « Jour 7, fin d'apres-midi » → Day 7 (hour 18) = 6*144 + 18*6 = 972.
        self.assertEqual(SB._t_textuel_vers_t("Jour 7, fin d'apres-midi"), 972)
        # « Jour 7 » alone → noon by default = 936.
        self.assertEqual(SB._t_textuel_vers_t("Jour 7"), 936)

    def test_t_textuel_vers_t_non_datable(self):
        self.assertIsNone(SB._t_textuel_vers_t("un texte sans jour"))
        self.assertIsNone(SB._t_textuel_vers_t(""))
        self.assertIsNone(SB._t_textuel_vers_t(None))

    def test_t_textuel_vers_t_entier_inchange(self):
        # A 't' already an integer is returned as-is (unlikely but robust case).
        self.assertEqual(SB._t_textuel_vers_t(936), 936)

    def test_jour_court(self):
        self.assertEqual(SB._jour_court(1224), "J9")     # 1224 // 144 + 1 = 9
        self.assertEqual(SB._jour_court(0), "J1")
        self.assertEqual(SB._jour_court(None), "?")
        self.assertEqual(SB._jour_court("x"), "?")

    def test_intensite_courte(self):
        # Doc style 05: « .4 », « 1 », « .85 ».
        self.assertEqual(SB._intensite_courte(0.4), ".4")
        self.assertEqual(SB._intensite_courte(1.0), "1")
        self.assertEqual(SB._intensite_courte(0.85), ".85")
        self.assertEqual(SB._intensite_courte(None), "")
        self.assertEqual(SB._intensite_courte("oops"), "")

    def test_duree_narr(self):
        # 2 UT = 20 min; 9 UT = 90 min = 1 h 30.
        self.assertEqual(SB._duree_narr(2), "20 min")
        self.assertEqual(SB._duree_narr(9), "1 h 30")
        self.assertEqual(SB._duree_narr(None), "?")
        self.assertEqual(SB._duree_narr(-1), "?")

    def test_nom_lieu_court(self):
        self.assertEqual(SB._nom_lieu_court(LIEU_CABANE, {}), "cabane berthe")
        self.assertEqual(SB._nom_lieu_court(None, {}), "?")

    def test_nom_acteur_court_depuis_index(self):
        idx = {"acteur:berthe": {"id": "acteur:berthe", "name": "Berthe"}}
        self.assertEqual(SB._nom_acteur_court("acteur:berthe", idx), "Berthe")
        # Not in index: derived from the id suffix.
        self.assertEqual(SB._nom_acteur_court("acteur:la-corneille", {}), "la corneille")
        self.assertEqual(SB._nom_acteur_court(None, {}), "?")


# ════════════════════════════════════════════════════════════════════════════
#  10. CLI — text by default, --json (internal purge), exit codes
# ════════════════════════════════════════════════════════════════════════════

class TestCLI(unittest.TestCase):
    """CLI argparse: first positional = campaign, second = location (contract §9.3)."""

    def test_texte_par_defaut_code_0(self):
        if not _campagne_reelle_dispo():
            self.skipTest("real campaign (geo.json) absent")
        code = SB.main([str(CAMPAGNE_REELLE), LIEU_CABANE])
        self.assertEqual(code, 0)

    def test_json_code_0(self):
        if not _campagne_reelle_dispo():
            self.skipTest("real campaign (geo.json) absent")
        code = SB.main([str(CAMPAGNE_REELLE), LIEU_CABANE, "--json"])
        self.assertEqual(code, 0)

    def test_campagne_introuvable_code_2(self):
        # Only non-zero case (contract §9.3): campaign not found → usage (2).
        code = SB.main(["/chemin/inexistant/xyz", LIEU_CABANE])
        self.assertEqual(code, 2)

    def test_lieu_inconnu_reste_code_0(self):
        # Fail-open: an unknown location is NOT a usage error (code 0).
        if not _campagne_reelle_dispo():
            self.skipTest("real campaign (geo.json) absent")
        code = SB.main([str(CAMPAGNE_REELLE), "lieu:rien/du/tout"])
        self.assertEqual(code, 0)

    def test_json_purge_les_champs_internes(self):
        # The --json output must contain ONLY contract §9.1 (no « _… »
        # nor « _vers » in enjeux). The CLI is run as a subprocess to
        # capture the real stdout.
        if not _campagne_reelle_dispo():
            self.skipTest("real campaign (geo.json) absent")
        import subprocess
        res = subprocess.run(
            [sys.executable, str(SCRIPTS_DIR / "scene_brief.py"),
             str(CAMPAGNE_REELLE), LIEU_CABANE, "--json"],
            capture_output=True, text=True, cwd=str(SCRIPTS_DIR))
        self.assertEqual(res.returncode, 0, res.stderr)
        data = json.loads(res.stdout)
        # No internal « _… » key.
        self.assertFalse([k for k in data if k.startswith("_")],
                         "the JSON output must not contain any internal field")
        self.assertEqual(set(data.keys()), CLES_CONTRAT,
                         "the JSON output exposes EXACTLY the contract §9.1")
        # « _vers » / « _vers_pj » purged from enjeux (internal fields).
        for e in data.get("enjeux", []):
            self.assertNotIn("_vers", e)
            self.assertNotIn("_vers_pj", e)


if __name__ == "__main__":
    unittest.main(verbosity=2)
