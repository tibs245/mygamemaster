#!/usr/bin/env python3
"""
test_world_tick.py — Tests for the tick engine (contract §12).

STDLIB `unittest` (no pytest required). Run from `scripts/`:
    python3 -m unittest discover

MANDATORY cases (contract §12):
  * `classer_LOD` (hot/warm/cold) on the vertical slice;
  * `resoudre_intentions` marks `intent:raid-hivernal` 'accomplished' when T_a >= 3960;
  * `pre` dry-run writes NOTHING;
  * `agent_decide` (deterministic stub) returns an intent conforming to the schema.

Also: Steward (refusal of negative resource), preconditions (fail-open),
post reconciliation (PC action → disrupted plan → renewal), isolated seam
without network, crossing, fail-open (campaign without actors.json), CLI exit
codes. Data: self-contained INLINE fixtures (the real vertical slice — Bande du
Corbeau — reproduced in miniature) + the real campaign in READ-ONLY mode.
"""

from __future__ import annotations

import copy
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent.parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import world_tick as WT          # noqa: E402
import worldlib as W             # noqa: E402

# Custom schema validation (best-effort: may differ depending on the environment).
try:
    import validate_schema as VS  # noqa: E402
except Exception:                 # pragma: no cover
    VS = None


CAMPAGNE_REELLE = Path(os.environ.get(
    "MGM_TEST_CAMPAIGN",
    str(Path(__file__).resolve().parents[5] / "data" / "mygamemaster" / "campaigns" / "la-naissance-dun-roi"),
))

_PREFIXE = "lieu:marche-aux-trois-rivieres/"
_CABANE = _PREFIXE + "cabane-berthe"
_GUE = _PREFIXE + "gue-du-corbeau"
_BOIS = _PREFIXE + "bois-des-charmes"


# ════════════════════════════════════════════════════════════════════════════
#  Inline fixtures (self-contained)
# ════════════════════════════════════════════════════════════════════════════

def _geo_fixture() -> dict:
    """Small graph: region + cabane-berthe — bois-des-charmes — gue (gue isolated)."""
    return {
        "meta": {"campagne": "Fixture", "version": 1},
        "locations": [
            {"id": "region:marche-aux-trois-rivieres", "name": "Marche", "parent": None,
             "type": "region", "altitude": None, "ancrage": {"x": 0, "y": 0}, "aretes": []},
            {"id": _CABANE, "name": "Cabane de Berthe",
             "parent": "region:marche-aux-trois-rivieres", "type": "habitation",
             "altitude": None, "ancrage": {"x": 0, "y": 0},
             "aretes": [{"vers": _BOIS, "dir": "O", "distance_m": None, "temps_ut": 4}]},
            {"id": _BOIS, "name": "Bois des charmes",
             "parent": "region:marche-aux-trois-rivieres", "type": "foret",
             "altitude": None, "ancrage": {"x": -40, "y": 0},
             "aretes": [{"vers": _CABANE, "dir": "E", "distance_m": None, "temps_ut": 4}]},
            {"id": _GUE, "name": "Gué du Corbeau",
             "parent": "region:marche-aux-trois-rivieres", "type": "riviere",
             "altitude": None, "ancrage": {"x": 200, "y": 200}, "aretes": []},
        ],
    }


def _acteur_bande() -> dict:
    """La Bande du Corbeau — vertical slice (winter raid dated T=3960)."""
    return {
        "id": "faction:bande-du-corbeau", "name": "La Bande du Corbeau",
        "type": "faction", "lod": "tiede", "majeur": True,
        "but_long_terme": "Rester maîtres de la Marche",
        "motivations": ["survie hivernale"],
        "situation": "Campée au Gué.",
        "ressources": {"vivres_jours": 12, "hommes": 18, "or": 40},
        "localisation_id": _GUE,
        "trajectory": [{"lieu": _GUE, "de": 0, "a": None}],
        "plan": [
            {
                "id": "intent:raid-hivernal",
                "action": "Raid d'approvisionnement hivernal sur une cible isolée",
                "lieu": _CABANE, "echeance": 3960,
                "preconditions": ["ressources.vivres_jours < 14"],
                "consequence_attendue": "Cabane pillée si non défendue.",
                "consequence_effets": {
                    "ressources": {"vivres_jours": 30},
                    "relations": [{"vers": "acteur:berthe", "type": "predation",
                                   "intensite": 0.7}],
                    "event": {"type": "raid"},
                },
                "significativite": 0.6, "visible_par_pj": False, "statut": "planifie",
            }
        ],
        "relations": [
            {"vers": "acteur:berthe", "type": "predation", "intensite": 0.4, "poids": 0.4},
        ],
        "source": "fixture",
    }


def _acteur_berthe() -> dict:
    return {
        "id": "acteur:berthe", "name": "Berthe", "type": "npcs",
        "lod": "chaud", "majeur": True,
        "but_long_terme": "Que la Marche reste libre",
        "situation": "À la cabane.", "ressources": {"vivres_jours": 6},
        "localisation_id": _CABANE,
        "trajectory": [{"lieu": _CABANE, "de": 0, "a": None}],
        "plan": [
            {"id": "intent:garder-cabane", "action": "Veiller sur la cabane",
             "lieu": _CABANE, "echeance": 3960, "preconditions": [],
             "consequence_attendue": "Détecte les signes d'un raid.",
             "significativite": 0.3, "visible_par_pj": True, "statut": "planifie"},
        ],
        "relations": [{"vers": "acteur:rubis", "type": "alliance", "intensite": 0.8}],
        "source": "fixture",
    }


def _acteurs_fixture() -> dict:
    return {
        "meta": {"campagne": "Fixture", "version": 1, "t_reference": 936},
        "actors": [_acteur_bande(), _acteur_berthe()],
    }


def _ecrire_campagne_temp(tmp: Path, *, avec_acteurs: bool = True) -> Path:
    """Creates a mini campaign on disk (geo.json + actors.json + sessions/)."""
    camp = tmp
    (camp / "sessions").mkdir(parents=True, exist_ok=True)
    W.sauver_json_atomique(camp / "geo.json", _geo_fixture())
    if avec_acteurs:
        W.sauver_json_atomique(camp / "actors.json", _acteurs_fixture())
    # Minimal world.json (for t_courant: sets the "Jour N"). meta.pj_ids declares
    # the PC(s) generically and CANONICALLY (list; the engine no longer hard-codes
    # "acteur:rubis" and tolerates multiple PCs).
    W.sauver_json_atomique(camp / "world.json", {
        "meta": {"name": "Fixture", "pj_ids": ["acteur:rubis"]},
        "global_state": {"timeline": "Jour 7 : la campagne commence."},
    })
    return camp


# ════════════════════════════════════════════════════════════════════════════
#  classer_LOD
# ════════════════════════════════════════════════════════════════════════════

class TestClasserLOD(unittest.TestCase):

    def setUp(self):
        self.geo = _geo_fixture()

    def test_chaud_co_localise(self):
        """Actor at the player's current location → hot."""
        bande = _acteur_bande()
        ctx = {"cone": {"locations": []}, "T_de": 3960, "T_a": 3960,
               "lieu_joueur": _GUE, "croisements_ids": set()}
        self.assertEqual(WT.classer_LOD(bande, ctx, self.geo, 3960), "chaud")

    def test_chaud_croisement_materialise(self):
        """Crossing already known (forces hot)."""
        bande = _acteur_bande()
        ctx = {"cone": None, "T_de": 0, "T_a": 100, "lieu_joueur": None,
               "croisements_ids": {"faction:bande-du-corbeau"}}
        self.assertEqual(WT.classer_LOD(bande, ctx, self.geo, 100), "chaud")

    def test_tiede_imminence_temporelle(self):
        """Deadline falls within [T_de, T_a] → warm (even without spatial cone)."""
        bande = _acteur_bande()
        ctx = {"cone": None, "T_de": 3900, "T_a": 4000,
               "lieu_joueur": None, "croisements_ids": set()}
        self.assertEqual(WT.classer_LOD(bande, ctx, self.geo, 4000), "tiede")

    def test_tiede_proximite_spatiale(self):
        """Actor at <= SEUIL_TIEDE_UT from the cone → warm."""
        berthe = _acteur_berthe()
        # Cone over the woods (4 UT from the cabin, well < 864).
        ctx = {"cone": {"locations": [_BOIS]}, "T_de": 500, "T_a": 600,
               "lieu_joueur": None, "croisements_ids": set()}
        self.assertEqual(WT.classer_LOD(berthe, ctx, self.geo, 600), "tiede")

    def test_froid_loin_et_pas_imminent(self):
        """No deadline in the window, no cone → cold."""
        bande = _acteur_bande()
        ctx = {"cone": None, "T_de": 500, "T_a": 600,
               "lieu_joueur": None, "croisements_ids": set()}
        self.assertEqual(WT.classer_LOD(bande, ctx, self.geo, 600), "froid")

    def test_froid_si_majeur_false(self):
        """majeur:false → always cold (reactive sheet)."""
        react = {"id": "x", "majeur": False, "plan": [], "trajectory": []}
        ctx = {"cone": None, "T_de": 3960, "T_a": 3960,
               "lieu_joueur": _GUE, "croisements_ids": set()}
        self.assertEqual(WT.classer_LOD(react, ctx, self.geo, 3960), "froid")


# ════════════════════════════════════════════════════════════════════════════
#  Preconditions + extended Steward
# ════════════════════════════════════════════════════════════════════════════

class TestPreconditionsAndSteward(unittest.TestCase):

    def test_precondition_vraie(self):
        acteur = {"id": "f", "ressources": {"vivres_jours": 12}}
        it = {"preconditions": ["ressources.vivres_jours < 14"]}
        self.assertTrue(WT.evaluer_preconditions(it, acteur, 0))

    def test_precondition_fausse(self):
        acteur = {"id": "f", "ressources": {"vivres_jours": 20}}
        it = {"preconditions": ["ressources.vivres_jours < 14"]}
        self.assertFalse(WT.evaluer_preconditions(it, acteur, 0))

    def test_precondition_inconnue_fail_open(self):
        """Unparsable precondition / absent resource → True (fail-open)."""
        acteur = {"id": "f", "ressources": {}}
        it = {"preconditions": ["la lune est gibbeuse", "ressources.absente < 3"]}
        self.assertTrue(WT.evaluer_preconditions(it, acteur, 0))

    def test_banquier_refuse_negatif(self):
        acteur = {"id": "f", "ressources": {"or": 5}}
        it = {"consequence_effets": {"ressources": {"or": -10}}}
        res = WT.appliquer_consequence(acteur, it, {}, {})
        self.assertFalse(res["ok"])
        self.assertEqual(acteur["ressources"]["or"], 5)   # unchanged (atomicity)

    def test_banquier_applique_delta(self):
        acteur = {"id": "f", "ressources": {"vivres_jours": 12}}
        it = {"consequence_effets": {"ressources": {"vivres_jours": 30}}}
        res = WT.appliquer_consequence(acteur, it, {}, {})
        self.assertTrue(res["ok"])
        self.assertEqual(acteur["ressources"]["vivres_jours"], 42)

    def test_banquier_mute_relation(self):
        acteur = {"id": "f", "ressources": {}, "relations": []}
        it = {"consequence_effets": {"relations": [
            {"vers": "acteur:berthe", "type": "predation", "intensite": 0.7}]}}
        res = WT.appliquer_consequence(acteur, it, {}, {})
        self.assertTrue(res["ok"])
        self.assertEqual(len(acteur["relations"]), 1)
        self.assertEqual(acteur["relations"][0]["vers"], "acteur:berthe")


# ════════════════════════════════════════════════════════════════════════════
#  resoudre_intentions
# ════════════════════════════════════════════════════════════════════════════

class TestResoudreIntentions(unittest.TestCase):

    def setUp(self):
        self.geo = _geo_fixture()
        self.tmp = tempfile.TemporaryDirectory()
        self.camp = _ecrire_campagne_temp(Path(self.tmp.name))

    def tearDown(self):
        self.tmp.cleanup()

    def test_raid_accompli_a_echeance(self):
        """Contract §12: raid 'accomplished' when T_a >= 3960."""
        bande = _acteur_bande()
        emis = WT.resoudre_intentions(bande, 3960, 3960, self.camp, self.geo, {})
        raid = next(i for i in bande["plan"] if i["id"] == "intent:raid-hivernal")
        self.assertEqual(raid["statut"], "accompli")
        # A resolved event was emitted for the raid.
        ids = [e["id"] for e in emis]
        self.assertTrue(any("raid" in i for i in ids))
        # Consequence applied: +30 food.
        self.assertEqual(bande["ressources"]["vivres_jours"], 42)

    def test_raid_pas_du_avant_echeance(self):
        """Before the deadline, the intent remains 'planifie'."""
        bande = _acteur_bande()
        WT.resoudre_intentions(bande, 1000, 2000, self.camp, self.geo, {})
        raid = next(i for i in bande["plan"] if i["id"] == "intent:raid-hivernal")
        self.assertEqual(raid["statut"], "planifie")

    def test_intention_echoue_si_precondition_non_remplie(self):
        """Preconditions not met at deadline → 'echoue'."""
        bande = _acteur_bande()
        bande["ressources"]["vivres_jours"] = 50    # 50 < 14 is false
        WT.resoudre_intentions(bande, 3960, 3960, self.camp, self.geo, {})
        raid = next(i for i in bande["plan"] if i["id"] == "intent:raid-hivernal")
        self.assertEqual(raid["statut"], "echoue")

    def test_evenement_emis_format(self):
        """The emitted event has the §8.3 fields (id/T/type/cible/statut)."""
        bande = _acteur_bande()
        emis = WT.resoudre_intentions(bande, 3960, 3960, self.camp, self.geo, {})
        evt = next(e for e in emis if "raid" in e["id"])
        for clef in ("id", "T", "type", "cible", "significativite", "statut"):
            self.assertIn(clef, evt)
        self.assertEqual(evt["statut"], "resolu")
        self.assertEqual(evt["T"], 3960)
        self.assertGreaterEqual(evt["T"], 3960)   # never earlier than the deadline


# ════════════════════════════════════════════════════════════════════════════
#  agent_decide (LLM seam — deterministic stub, WITHOUT network)
# ════════════════════════════════════════════════════════════════════════════

class TestAgentDecide(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.camp = _ecrire_campagne_temp(Path(self.tmp.name))

    def tearDown(self):
        self.tmp.cleanup()
        os.environ.pop(WT._ENV_AGENT_CMD, None)

    def test_stub_deterministe_conforme(self):
        """Contract §12: the stub returns an intent conforming to the schema."""
        # Ensure no LLM command is wired (pure stub).
        os.environ.pop(WT._ENV_AGENT_CMD, None)
        bande = _acteur_bande()
        intention = WT.agent_decide(bande, "brief", self.camp)
        self.assertTrue(WT.valider_intention(intention))
        self.assertEqual(intention["statut"], "planifie")
        self.assertIsInstance(intention["echeance"], int)
        self.assertIn("(à décider)", intention["action"])

    def test_stub_reconduit_but(self):
        """The stub derives its intent from the actor's long-term goal."""
        bande = _acteur_bande()
        intention = WT.agent_decide(bande, "brief", self.camp)
        self.assertIn(bande["but_long_terme"], intention["action"])

    def test_deterministe_repetable(self):
        """Two identical calls → same intent (deterministic)."""
        bande = _acteur_bande()
        i1 = WT.agent_decide(copy.deepcopy(bande), "brief", self.camp)
        i2 = WT.agent_decide(copy.deepcopy(bande), "brief", self.camp)
        self.assertEqual(i1["id"], i2["id"])
        self.assertEqual(i1["echeance"], i2["echeance"])

    def test_seam_sousprocessus_injectable(self):
        """The seam can be wired to an external command (env) that returns
        a JSON intent. We inject a small helper script (temporary file)
        that reads the brief from stdin and prints the intent — avoids the headache
        of escaping nested quotes under shlex.split."""
        intention_externe = {
            "id": "intent:llm-test", "action": "Décision LLM simulée",
            "lieu": _GUE, "echeance": 5000,
            "consequence_attendue": "test", "visible_par_pj": True,
            "statut": "planifie",
        }
        camp_dir = Path(self.camp)
        intent_path = camp_dir / "_intent_externe.json"
        intent_path.write_text(json.dumps(intention_externe), encoding="utf-8")
        helper = camp_dir / "_agent_helper.py"
        helper.write_text(
            "import sys\n"
            "sys.stdin.read()\n"            # consume the brief (like a real agent)
            f"sys.stdout.write(open(r'{intent_path}', encoding='utf-8').read())\n",
            encoding="utf-8",
        )
        # {slug} is substituted by agent_decide; we ignore it here.
        os.environ[WT._ENV_AGENT_CMD] = f"{sys.executable} {helper}"
        bande = _acteur_bande()
        intention = WT.agent_decide(bande, "brief", self.camp)
        self.assertEqual(intention["id"], "intent:llm-test")
        self.assertEqual(intention["echeance"], 5000)

    def test_seam_repli_si_sortie_invalide(self):
        """Invalid LLM output → fallback to the deterministic stub (code wins)."""
        helper = Path(self.camp) / "_agent_helper_bad.py"
        helper.write_text(
            "import sys\nsys.stdin.read()\nprint('pas du json')\n",
            encoding="utf-8",
        )
        os.environ[WT._ENV_AGENT_CMD] = f"{sys.executable} {helper}"
        bande = _acteur_bande()
        intention = WT.agent_decide(bande, "brief", self.camp)
        # Fell back to the stub (id 'intent:suite-…').
        self.assertTrue(intention["id"].startswith("intent:suite"))
        self.assertTrue(WT.valider_intention(intention))


# ════════════════════════════════════════════════════════════════════════════
#  pre (projection) — dry-run vs apply
# ════════════════════════════════════════════════════════════════════════════

class TestPre(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.camp = _ecrire_campagne_temp(Path(self.tmp.name))

    def tearDown(self):
        self.tmp.cleanup()

    def test_dry_run_n_ecrit_rien(self):
        """Contract §12: `pre` dry-run writes nothing."""
        avant = (self.camp / "actors.json").read_bytes()
        res = WT.pre(self.camp, t_session=3960, cone=None, apply=False)
        apres = (self.camp / "actors.json").read_bytes()
        self.assertEqual(avant, apres)                       # actors.json intact
        self.assertFalse((self.camp / "evenements_programmes.json").exists())
        self.assertEqual(res["ecritures"], [])

    def test_apply_ecrit_acteurs_et_programmes(self):
        """--apply persists actors.json (raid accomplished) + evenements_programmes.json."""
        res = WT.pre(self.camp, t_session=3960, cone=None, apply=True)
        self.assertTrue((self.camp / "evenements_programmes.json").exists())
        acteurs = W.charger_acteurs(self.camp)
        idx = W.index_acteurs(acteurs)
        raid = next(i for i in idx["faction:bande-du-corbeau"]["plan"]
                    if i["id"] == "intent:raid-hivernal")
        self.assertEqual(raid["statut"], "accompli")
        self.assertTrue(res["ecritures"])

    def test_briefing_sans_t_brut_ni_xy(self):
        """The briefing never shows the raw T nor the (x,y) coordinates (invariant 01§C)."""
        res = WT.pre(self.camp, t_session=3960, cone=None, apply=False)
        texte = res["briefing"]
        # No pattern "(x=" / "y="; T values are rendered narratively.
        self.assertNotIn("x=", texte)
        self.assertNotIn("y=", texte)
        self.assertIn("Jour", texte)   # narrative rendering present

    def test_croisement_detecte(self):
        """A moving actor crossing the cone produces a crossing."""
        # Berthe moves cabin → woods; cone over the woods on the same window.
        acteurs = W.charger_acteurs(self.camp)
        idx = W.index_acteurs(acteurs)
        idx["acteur:berthe"]["trajectory"] = [
            {"lieu": _CABANE, "de": 0, "a": 100},
            {"type": "deplacement", "de": 100, "a": 200,
             "chemin": [_CABANE, _BOIS], "motif": "test"},
            {"lieu": _BOIS, "de": 200, "a": None},
        ]
        out = dict(acteurs)
        out["actors"] = list(idx.values())
        W.sauver_json_atomique(self.camp / "actors.json", out)

        cone = {"locations": [_BOIS], "fenetre": [0, 300], "lieu_joueur": _BOIS}
        res = WT.pre(self.camp, t_session=300, cone=cone, apply=False)
        # Berthe must be crossed (she ends up in the woods, where the player is).
        acteurs_croises = {c["actor"] for c in res["croisements"]}
        self.assertIn("acteur:berthe", acteurs_croises)


# ════════════════════════════════════════════════════════════════════════════
#  post (reconciliation)
# ════════════════════════════════════════════════════════════════════════════

class TestPost(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.camp = _ecrire_campagne_temp(Path(self.tmp.name))

    def tearDown(self):
        self.tmp.cleanup()

    def _ecrire_session(self, num: int, contenu: dict):
        W.sauver_json_atomique(self.camp / "sessions" / f"{num:03d}.json", contenu)

    def test_extraire_faits_joueur(self):
        session = {
            "actions": ["Rubis a attaqué la Bande du Corbeau"],
            "npcs_met": ["Berthe"],
            "visited_locations": ["Gué du Corbeau"],
            "etat_fin": {"lieu_actuel": "Cabane de Berthe"},
        }
        faits = WT.extraire_faits_joueur(session)
        self.assertTrue(any(f["a_consequences"] for f in faits))
        libelles = " ".join(f["libelle"] for f in faits)
        self.assertIn("attaqué", libelles)

    def test_reconciliation_action_impactante_perturbe_plan(self):
        """PC action targeting the actor → intents 'echoue', plan disrupted."""
        self._ecrire_session(50, {
            "actions": ["Rubis a attaqué la Bande du Corbeau au Gué"],
            "etat_fin": {"lieu_actuel": "Gué"},
        })
        res = WT.post(self.camp, session="050", apply=False)
        rec = next((r for r in res["reconciliations"]
                    if r["actor"] == "faction:bande-du-corbeau"), None)
        self.assertIsNotNone(rec)
        self.assertTrue(rec["plan_perturbe"])
        # The plan has been renewed (seam).
        self.assertIn("faction:bande-du-corbeau", res["plans_renouveles"])

    def test_reconciliation_sans_action_n_altere_pas(self):
        """No consequential action → plan unchanged (ignored)."""
        self._ecrire_session(51, {
            "actions": ["Le groupe se repose à la cabane"],
            "etat_fin": {"lieu_actuel": "Cabane de Berthe"},
        })
        res = WT.post(self.camp, session="051", apply=False)
        # No disruptive reconciliation.
        self.assertFalse(any(r["plan_perturbe"] for r in res["reconciliations"]))

    def test_propagation_action_joueur(self):
        """A consequential action becomes a cause (propagated event)."""
        self._ecrire_session(52, {
            "actions": ["Rubis a incendié le pont du Gué"],
            "etat_fin": {"lieu_actuel": "Gué"},
        })
        res = WT.post(self.camp, session="052", apply=False)
        self.assertTrue(res["propagations"])   # at least the root event

    def test_post_apply_ecrit(self):
        self._ecrire_session(53, {
            "actions": ["Rubis a attaqué la Bande du Corbeau"],
            "etat_fin": {"lieu_actuel": "Gué"},
        })
        res = WT.post(self.camp, session="053", apply=True)
        self.assertTrue((self.camp / "actors.json").exists())
        self.assertTrue(res["ecritures"])


# ════════════════════════════════════════════════════════════════════════════
#  Fail-open & non-destructive
# ════════════════════════════════════════════════════════════════════════════

class TestFailOpen(unittest.TestCase):

    def test_pre_campagne_sans_acteurs(self):
        """Campaign without actors.json → pre does not crash (degraded briefing)."""
        with tempfile.TemporaryDirectory() as d:
            camp = _ecrire_campagne_temp(Path(d), avec_acteurs=False)
            res = WT.pre(camp, t_session=3960, cone=None, apply=False)
            self.assertIn("briefing", res)
            self.assertEqual(res["ticks"], [])

    def test_rubis_jamais_classe(self):
        """The PC (acteur:rubis) is never included in pre ticks."""
        with tempfile.TemporaryDirectory() as d:
            camp = _ecrire_campagne_temp(Path(d))
            acteurs = W.charger_acteurs(camp)
            acteurs["actors"].append({
                "id": "acteur:rubis", "name": "Rubis", "type": "npcs", "lod": "chaud",
                "majeur": True, "but_long_terme": "—", "situation": "—",
                "ressources": {}, "trajectory": [{"lieu": _CABANE, "de": 0, "a": None}],
                "plan": [], "relations": [],
            })
            W.sauver_json_atomique(camp / "actors.json", acteurs)
            res = WT.pre(camp, t_session=3960, cone=None, apply=False)
            ids = {t["actor"] for t in res["ticks"]}
            self.assertNotIn("acteur:rubis", ids)

    def test_tous_les_pj_exclus_multi_pj(self):
        """With MULTIPLE PCs (meta.pj_ids), NONE is included in the ticks."""
        with tempfile.TemporaryDirectory() as d:
            camp = _ecrire_campagne_temp(Path(d))
            # Campaign with two PCs (e.g. Oscar AND Cendre) declared in canonical list.
            W.sauver_json_atomique(camp / "world.json", {
                "meta": {"name": "Fixture", "pj_ids": ["acteur:oscar", "acteur:cendre"]},
                "global_state": {"timeline": "Jour 7 : la campagne commence."},
            })
            acteurs = W.charger_acteurs(camp)
            for pid, nom in (("acteur:oscar", "Oscar"), ("acteur:cendre", "Cendre")):
                acteurs["actors"].append({
                    "id": pid, "name": nom, "type": "npcs", "lod": "chaud",
                    "majeur": True, "but_long_terme": "—", "situation": "—",
                    "ressources": {}, "trajectory": [{"lieu": _CABANE, "de": 0, "a": None}],
                    "plan": [], "relations": [],
                })
            W.sauver_json_atomique(camp / "actors.json", acteurs)
            res = WT.pre(camp, t_session=3960, cone=None, apply=False)
            ids = {t["actor"] for t in res["ticks"]}
            self.assertNotIn("acteur:oscar", ids)
            self.assertNotIn("acteur:cendre", ids)
            # La Bande (major non-PC actor) is still classified.
            self.assertIn("faction:bande-du-corbeau", ids)

    def test_ne_touche_pas_evenements_json(self):
        """--apply NEVER writes to events.json (non-destructive)."""
        with tempfile.TemporaryDirectory() as d:
            camp = _ecrire_campagne_temp(Path(d))
            # Pre-existing events.json (legacy format): must remain intact.
            ev_path = camp / "events.json"
            contenu_origine = {"events": [{"id": "legacy", "t": "Jour 7"}]}
            W.sauver_json_atomique(ev_path, contenu_origine)
            avant = ev_path.read_bytes()
            WT.pre(camp, t_session=3960, cone=None, apply=True)
            self.assertEqual(ev_path.read_bytes(), avant)   # unchanged


# ════════════════════════════════════════════════════════════════════════════
#  Schema validation (best-effort)
# ════════════════════════════════════════════════════════════════════════════

class TestSchema(unittest.TestCase):

    @unittest.skipIf(VS is None, "validate_schema unavailable")
    def test_stub_intention_valide_schema(self):
        """The stub intent validates against intention.schema.json (custom validator)."""
        schema_path = SCRIPTS_DIR / "schemas" / "intention.schema.json"
        if not schema_path.exists():
            self.skipTest("intention.schema.json absent")
        with tempfile.TemporaryDirectory() as d:
            camp = _ecrire_campagne_temp(Path(d))
            intention = WT.agent_decide(_acteur_bande(), "brief", camp)
        schema = VS.charger_schema("intention")
        erreurs = VS.valider(intention, schema, schema)
        self.assertEqual(erreurs, [], f"schema deviations: {erreurs}")


# ════════════════════════════════════════════════════════════════════════════
#  Real campaign (READ-ONLY)
# ════════════════════════════════════════════════════════════════════════════

class TestCampagneReelle(unittest.TestCase):

    @unittest.skipUnless(CAMPAGNE_REELLE.is_dir(), "real campaign absent")
    def test_lod_reel_ne_plante_pas(self):
        geo = W.charger_geo(CAMPAGNE_REELLE)
        acteurs = W.charger_acteurs(CAMPAGNE_REELLE)
        T = 3960
        ctx = WT._contexte_joueur(None, T, T)
        for aid, acteur in W.index_acteurs(acteurs).items():
            lod = WT.classer_LOD(acteur, ctx, geo, T)
            self.assertIn(lod, ("chaud", "tiede", "froid"))

    @unittest.skipUnless(CAMPAGNE_REELLE.is_dir(), "real campaign absent")
    def test_pre_reel_dry_run_ne_plante_pas(self):
        """pre dry-run on the real campaign: no crash, no writes."""
        if not (CAMPAGNE_REELLE / "actors.json").exists():
            self.skipTest("real actors.json absent")
        res = WT.pre(CAMPAGNE_REELLE, t_session=3960, cone=None, apply=False)
        self.assertIn("briefing", res)
        self.assertEqual(res["ecritures"], [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
