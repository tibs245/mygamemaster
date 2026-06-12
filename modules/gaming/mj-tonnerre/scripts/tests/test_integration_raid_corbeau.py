#!/usr/bin/env python3
"""
test_integration_raid_corbeau.py — END-TO-END INTEGRATION TEST (contract §10).

Exercise of the VERTICAL SLICE on the REAL DATA of the campaign
`la-naissance-dun-roi` (geo.json + actors.json): the winter raid of the Bande du
Corbeau (`intent:raid-hivernal`, frozen deadline 3960) confronted with a PC who passes
through the Gué du Corbeau, then PREVENTS the raid. This is the "end to end" exercise
required by contract §10.1 and `07`§3.

Three scenarios (one per `test_…`):

  (1) PRE: a player whose trajectory passes through (stays at) the Gué du Corbeau around
      the raid deadline → `world_tick.pre` detects a CROSSING / an encounter with
      `faction:bande-du-corbeau` (and promotes it to `chaud`). A complementary temporal
      assertion (via `geo_query.croisement`) verifies that the encounter window
      falls WITHIN the raid interval.

  (2) POST: a session-log where the player ATTACKS / DISPERSES the Bande at the Gué
      (preventing the raid) → `world_tick.post` marks `intent:raid-hivernal` FAILED,
      signals the plan as DISRUPTED and RENEWS the plan (seam `agent_decide`,
      deterministic offline stub).

  (3) CONSERVATION INVARIANTS on the real data AND after a real resolution:
      no TELEPORTATION (trajectory continuity — `valider_trajectoire`),
      T MONOTONE (segments `de <= a`, derived events never prior to their cause),
      no RESOURCE created from nothing (extended Steward rejects negative balances;
      the raid only increases supplies by the declared delta, no more, no less).

Conventions (aligned with `test_world_tick.py`):
  * STDLIB `unittest` (no pytest);
  * `sys.path` managed here → direct import of `world_tick` / `worldlib` / `geo_query`
    from `scripts/` (no `__init__.py` package exists; we do not create one —
    NON DESTRUCTIVE);
  * the REAL campaign is read as READ ONLY; `--apply` scenarios operate on a
    TEMPORARY COPY (never on the campaign files);
  * `agent_decide` remains a deterministic STUB WITHOUT network (env variable cleared);
  * tests skipped cleanly (`skip`) if the campaign / real files are absent.

Execution:
    cd .../mj-tonnerre/scripts && python3 -m unittest tests.test_integration_raid_corbeau -v
or directly:
    python3 .../tests/test_integration_raid_corbeau.py
"""

from __future__ import annotations

import copy
import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path

# ── sys.path: make the component scripts importable (no package) ──
SCRIPTS_DIR = Path(__file__).resolve().parent.parent
if str(SCRIPTS_DIR) not in __import__("sys").path:
    __import__("sys").path.insert(0, str(SCRIPTS_DIR))

import worldlib as W          # noqa: E402
import world_tick as WT       # noqa: E402

try:
    import geo_query as G     # noqa: E402
except Exception:             # pragma: no cover - geo_query should be present
    G = None


# ── Real campaign + frozen slice ids (contract §2) ──────────────────
CAMPAGNE_REELLE = Path(os.environ.get(
    "MJ_TEST_CAMPAIGN",
    str(Path(__file__).resolve().parents[5] / "data" / "mj-tonnerre" / "campaigns" / "la-naissance-dun-roi"),
))

PREFIXE = "lieu:marche-aux-trois-rivieres/"
GUE = PREFIXE + "gue-du-corbeau"
CABANE = PREFIXE + "cabane-berthe"

BANDE = "faction:bande-du-corbeau"
INTENT_RAID = "intent:raid-hivernal"
ECHEANCE_RAID = 3960          # contract §10: FROZEN value of the raid deadline


def _campagne_reelle_complete() -> bool:
    """True if the real campaign and its two required files exist."""
    return (
        CAMPAGNE_REELLE.is_dir()
        and (CAMPAGNE_REELLE / "geo.json").exists()
        and (CAMPAGNE_REELLE / "actors.json").exists()
    )


_RAISON_SKIP = "real campaign (geo.json + actors.json) absent"


def _copier_campagne(dst: Path) -> Path:
    """NON DESTRUCTIVE copy of only the useful files from the real campaign into `dst`.

    The `images/` folder is NOT copied (large, unnecessary). `sessions/` is created.
    Returns the path of the copied campaign. The real campaign remains INTACT.
    """
    camp = dst / "camp"
    (camp / "sessions").mkdir(parents=True, exist_ok=True)
    for name in ("geo.json", "actors.json", "world.json", "events.json"):
        src = CAMPAGNE_REELLE / name
        if src.exists():
            shutil.copy2(src, camp / name)
    return camp


# ════════════════════════════════════════════════════════════════════════════
#  (1) PRE — the player passes through the Gué → crossing with the Bande's raid
# ════════════════════════════════════════════════════════════════════════════

@unittest.skipUnless(_campagne_reelle_complete(), _RAISON_SKIP)
class TestIntegrationPreCroisement(unittest.TestCase):
    """The PC stays at the Gué du Corbeau at the raid deadline → encounter detected."""

    def setUp(self):
        self.geo = W.charger_geo(CAMPAGNE_REELLE)
        self.acteurs = W.charger_acteurs(CAMPAGNE_REELLE)
        self.idx = W.index_acteurs(self.acteurs)
        # Slice precondition: the Bande IS camped at the Gué (real data).
        bande = self.idx.get(BANDE)
        self.assertIsNotNone(bande, "faction:bande-du-corbeau absent from real data")
        self.assertEqual(W.position_a(self.geo, W.trajectoire_de(bande),
                                      ECHEANCE_RAID)["lieu"], GUE)
        # … and plans a raid at the frozen deadline 3960.
        raid = next((i for i in bande["plan"] if i.get("id") == INTENT_RAID), None)
        self.assertIsNotNone(raid, "intent:raid-hivernal absent from the Bande's plan")
        self.assertEqual(raid["echeance"], ECHEANCE_RAID)

    def test_pre_detecte_croisement_avec_la_bande(self):
        """`world_tick.pre` (dry-run): the cone at the Gué crosses the Bande → promotion to chaud.

        The cone provides an explicit TRAJECTORY for the player (stay at the Gué covering
        the raid window). `pre` projects player × lukewarm-actor crossings: the
        Bande (at the Gué, at zero anchor distance) must appear in the crossings
        AND be promoted to `chaud`. Dry-run: no writes.
        """
        cone = {
            "locations": [GUE],
            "fenetre": [0, ECHEANCE_RAID],
            "lieu_joueur": GUE,
            # Explicit trajectory: the player is at the Gué (co-located with the Bande).
            "trajectoire": [{"lieu": GUE, "de": 0, "a": None}],
        }
        res = WT.pre(CAMPAGNE_REELLE, t_session=ECHEANCE_RAID, cone=cone, apply=False)

        acteurs_croises = {c.get("acteur") for c in res["croisements"]}
        self.assertIn(
            BANDE, acteurs_croises,
            f"the Bande du Corbeau should have been crossed; crossings={acteurs_croises}",
        )
        # The encounter materialises the Bande as 'chaud' (staged). Here the player
        # is CO-LOCATED at the Gué: the Bande is classified 'chaud' from the outset
        # (by the player's current location) — so it does not need to be "promoted" from lukewarm.
        # We verify the useful invariant: the crossed Bande IS chaud (co-located OR
        # promoted). (`promus_chaud` lists ONLY promotions from a non-chaud state.)
        bande_tick = next((t for t in res["ticks"] if t["acteur"] == BANDE), None)
        self.assertIsNotNone(bande_tick)
        self.assertEqual(bande_tick["lod"], "chaud",
                         "the crossed Bande must be in LOD chaud (encounter materialised)")
        # The staging mechanism did produce a scene for the Bande.
        self.assertIn(BANDE, {s.get("acteur") for s in res["scenes"]})
        # Strict dry-run: NOTHING is written.
        self.assertEqual(res["ecritures"], [])

    def test_croisement_tombe_dans_la_fenetre_du_raid(self):
        """TEMPORAL assertion: the crossing window falls around the deadline.

        Both trajectories are bounded (player AND Bande present at the Gué until after the
        raid) so that sampling actually reaches the deadline — otherwise the
        `a:null` of the Bande's stay bounds the common interval to T=0 (optimization of
        `geo_query._bornes_trajectoire`). Here we verify the SEMANTICS "the player crosses
        the raid at its deadline".
        """
        if G is None:
            self.skipTest("geo_query indisponible")
        traj_joueur = [{"lieu": GUE, "de": ECHEANCE_RAID - 60, "a": ECHEANCE_RAID + 60}]
        traj_bande = [{"lieu": GUE, "de": 0, "a": ECHEANCE_RAID + 60}]
        fenetres = G.croisement(CAMPAGNE_REELLE, traj_joueur, traj_bande,
                                seuil=WT.SEUIL_CROISEMENT, pas_ut=WT.PAS_PROJECTION_UT)
        self.assertTrue(fenetres, "no crossing window at the Gué at the raid deadline")
        # At least one window brackets the raid deadline (±1 sampling step).
        marge = WT.PAS_PROJECTION_UT
        self.assertTrue(
            any(ECHEANCE_RAID - 60 - marge <= f["T"] <= ECHEANCE_RAID + 60 + marge
                for f in fenetres),
            f"windows {[f['T'] for f in fenetres]} do not bracket T={ECHEANCE_RAID}",
        )
        # Within encounter range (anchor distance below threshold).
        self.assertTrue(all(f["distance"] <= WT.SEUIL_CROISEMENT for f in fenetres))

    def test_pre_dry_run_n_ecrit_rien_sur_la_campagne_reelle(self):
        """NON DESTRUCTIVE safeguard: a `pre` dry-run touches no real file."""
        avant_acteurs = (CAMPAGNE_REELLE / "actors.json").read_bytes()
        prog = CAMPAGNE_REELLE / "scheduled_events.json"
        prog_existait = prog.exists()
        prog_avant = prog.read_bytes() if prog_existait else None

        cone = {"locations": [GUE], "lieu_joueur": GUE,
                "trajectoire": [{"lieu": GUE, "de": 0, "a": None}]}
        WT.pre(CAMPAGNE_REELLE, t_session=ECHEANCE_RAID, cone=cone, apply=False)

        self.assertEqual((CAMPAGNE_REELLE / "actors.json").read_bytes(), avant_acteurs)
        if prog_existait:
            self.assertEqual(prog.read_bytes(), prog_avant)
        else:
            self.assertFalse(prog.exists(),
                             "pre dry-run created scheduled_events.json (forbidden)")


# ════════════════════════════════════════════════════════════════════════════
#  (2) POST — the player PREVENTS the raid → failed intent + renewed plan
# ════════════════════════════════════════════════════════════════════════════

@unittest.skipUnless(_campagne_reelle_complete(), _RAISON_SKIP)
class TestIntegrationPostEmpecheRaid(unittest.TestCase):
    """The PC disperses the Bande at the Gué: the raid fails and the Bande rethinks its plan."""

    def setUp(self):
        # Clear any injected LLM command → seam = deterministic STUB (offline).
        os.environ.pop(WT._ENV_AGENT_CMD, None)
        # Session-log: the player ATTACKS AND disperses the Bande (PREVENTING the raid).
        self.session = {
            "actions": [
                "Rubis a attaqué et dispersé la Bande du Corbeau au Gué du Corbeau, "
                "empêchant le raid hivernal contre la cabane de Berthe",
            ],
            "pnj_rencontres": ["La Corneille"],
            "lieux_visites": ["Gué du Corbeau"],
            "etat_fin": {"lieu_actuel": "Gué du Corbeau"},
        }

    def tearDown(self):
        os.environ.pop(WT._ENV_AGENT_CMD, None)

    def test_post_marque_le_raid_echoue_et_renouvelle_le_plan(self):
        """`world_tick.post` (dry-run): raid → FAILED, plan disrupted, plan renewed."""
        res = WT.post(CAMPAGNE_REELLE, session=self.session, apply=False)

        # The player's action was recognised as a consequential fact (= cause).
        self.assertTrue(any(f.get("a_consequences") for f in res["faits_joueur"]),
                        "the player's attack should have been a fact with consequences")

        # Reconciliation of the Bande: plan DISRUPTED.
        rec = next((r for r in res["reconciliations"] if r["acteur"] == BANDE), None)
        self.assertIsNotNone(rec, "no reconciliation for the Bande du Corbeau")
        self.assertTrue(rec["plan_perturbe"], "the Bande's plan should have been disrupted")
        # The raid appears explicitly among the intents set to 'echoue'.
        self.assertTrue(
            any(INTENT_RAID in chg for chg in rec["changements"]),
            f"intent:raid-hivernal absent from changes: {rec['changements']}",
        )

        # Plan RENEWED (the deterministic seam proposed a valid continuation).
        self.assertIn(BANDE, res["plans_renouveles"],
                      "the Bande should have renewed its plan after disruption")

        # The player's action becomes a propagated CAUSE (≥ the root event).
        self.assertTrue(res["propagations"],
                        "the player's impactful action should have been propagated")

        # Dry-run: no writes.
        self.assertEqual(res["ecritures"], [])

    def test_post_in_situ_etat_acteur_mute(self):
        """On real actors loaded in memory, reconciliation MUTATES the plan correctly.

        Confirms at the level of internal functions (not just the `post` summary)
        that `intent:raid-hivernal` moves to `echoue` and the plan is rethought via the
        seam — all WITHOUT writing to disk (in-memory objects).
        """
        acteurs = W.charger_acteurs(CAMPAGNE_REELLE)
        geo = W.charger_geo(CAMPAGNE_REELLE)
        bande = copy.deepcopy(W.index_acteurs(acteurs)[BANDE])

        faits = WT.extraire_faits_joueur(self.session)
        faits_bande = WT._faits_concernant(bande, faits)
        self.assertTrue(faits_bande, "no fact explicitly concerns the Bande")

        rec = WT.reconcilier_etat(bande, faits_bande, geo)
        self.assertTrue(rec["plan_perturbe"])
        raid = next(i for i in bande["plan"] if i["id"] == INTENT_RAID)
        self.assertEqual(raid["statut"], "echoue")

        ren = WT.renouveler_plan(bande, faits_bande, CAMPAGNE_REELLE)
        self.assertIsNotNone(ren["intention"], "the seam should have proposed a continuation")
        self.assertTrue(WT.valider_intention(ren["intention"]),
                        "the renewed intention must be valid (schema/invariants)")

    def test_post_sans_action_n_altere_pas_le_raid(self):
        """Counter-test: a session WITHOUT an impactful action leaves the raid intact."""
        session_passive = {
            "actions": ["Le groupe se repose et discute à la cabane de Berthe"],
            "lieux_visites": ["Cabane de Berthe"],
            "etat_fin": {"lieu_actuel": "Cabane de Berthe"},
        }
        res = WT.post(CAMPAGNE_REELLE, session=session_passive, apply=False)
        self.assertFalse(
            any(r.get("plan_perturbe") for r in res["reconciliations"]),
            "aucune action impactante ne devrait perturber un plan",
        )
        self.assertNotIn(BANDE, res["plans_renouveles"])


# ════════════════════════════════════════════════════════════════════════════
#  (3) CONSERVATION INVARIANTS (space, time, resources) on real data
# ════════════════════════════════════════════════════════════════════════════

@unittest.skipUnless(_campagne_reelle_complete(), _RAISON_SKIP)
class TestIntegrationConservation(unittest.TestCase):
    """No teleportation, T monotone, no resource created from nothing."""

    def setUp(self):
        self.geo = W.charger_geo(CAMPAGNE_REELLE)
        self.acteurs = W.charger_acteurs(CAMPAGNE_REELLE)
        self.idx = W.index_acteurs(self.acteurs)

    # --- Space: trajectory continuity (no teleportation) ---

    def test_aucune_teleportation_dans_les_trajectoires_reelles(self):
        """Each real actor trajectory validates continuity (contract §3.7).

        `valider_trajectoire` detects gaps, overlaps, impossible paths and
        teleportations (duration < sum of edges). On the delivered data: ZERO
        violations for all actors.
        """
        for aid, acteur in self.idx.items():
            traj = W.trajectoire_de(acteur)
            violations = W.valider_trajectoire(self.geo, traj)
            self.assertEqual(
                violations, [],
                f"trajectory of « {aid} » invalid: {violations}",
            )

    def test_segments_de_deplacement_monotones(self):
        """Time: every segment respects `de <= a` (local monotonicity, contract §14.5).

        Covers in particular Firmin, the only real actor with a 'deplacement' segment
        (Vallée du Cœur → cabane), hence the non-trivial case.
        """
        a_vu_deplacement = False
        for aid, acteur in self.idx.items():
            for seg in W.trajectoire_de(acteur):
                if not isinstance(seg, dict):
                    continue
                de = seg.get("de")
                a = seg.get("a")
                if seg.get("type") == "deplacement":
                    a_vu_deplacement = True
                if isinstance(de, int) and isinstance(a, int):
                    self.assertLessEqual(
                        de, a, f"non-monotone segment in « {aid} »: de={de} a={a}")
        self.assertTrue(a_vu_deplacement,
                        "no 'deplacement' segment found (Firmin expected)")

    # --- Resources: no creation from nothing (extended Steward) ---

    def test_banquier_refuse_ressource_negative(self):
        """Resource conservation: a negative balance is REJECTED (contract §7.3).

        The extended Steward rejects any consequence that would make a resource
        negative, and the actor remains UNCHANGED (atomicity) — no resource is created
        or destroyed from nothing.
        """
        bande = copy.deepcopy(self.idx[BANDE])
        vivres0 = bande["ressources"]["vivres_jours"]
        intention_absurde = {
            "consequence_effets": {"ressources": {"vivres_jours": -(vivres0 + 9999)}}
        }
        res = WT.appliquer_consequence(bande, intention_absurde, {}, self.geo)
        self.assertFalse(res["ok"], "the Banker should have rejected a negative balance")
        self.assertEqual(bande["ressources"]["vivres_jours"], vivres0,
                         "resources must remain intact after a rejection")

    def test_raid_conserve_exactement_le_delta_declare(self):
        """The raid adds ONLY the declared supplies delta (no more, no less).

        Real resolution of `intent:raid-hivernal` at its deadline: the consequence
        declares `+30` supplies; we verify exact equality (conservation: no resource
        "created from nothing" beyond the declared effect).
        """
        bande = copy.deepcopy(self.idx[BANDE])
        raid = next(i for i in bande["plan"] if i["id"] == INTENT_RAID)
        delta = raid["consequence_effets"]["ressources"]["vivres_jours"]
        vivres0 = bande["ressources"]["vivres_jours"]

        # Real precondition: vivres_jours < 14 (12 < 14 → the raid is triggered).
        self.assertTrue(WT.evaluer_preconditions(raid, bande, ECHEANCE_RAID))

        res = WT.appliquer_consequence(bande, raid, {}, self.geo)
        self.assertTrue(res["ok"], "the raid's consequence should have been applied")
        self.assertEqual(
            bande["ressources"]["vivres_jours"], vivres0 + delta,
            "the raid must add EXACTLY the declared delta (conservation)",
        )

    # --- Causality: derived events never prior to their cause ---

    def test_propagation_jamais_anterieure_a_la_cause(self):
        """Time/causality: no scheduled event is prior to its cause.

        Full PRE cycle on a COPY of the campaign (apply): we verify that for
        each derived event, `T >= T(cause)` (the cascade never "recalculates the
        past", contract §8.2) and that no event emitted during this tick is prior
        to the tick's current `t_de` (before writing).
        """
        with tempfile.TemporaryDirectory() as d:
            camp = _copier_campagne(Path(d))
            t_de = W.t_courant(camp)   # present BEFORE any writing of scheduled events

            res = WT.pre(camp, t_session=ECHEANCE_RAID, cone=None, apply=True)
            self.assertTrue(res["ecritures"], "the --apply cycle should have written")

            prog_path = camp / "scheduled_events.json"
            self.assertTrue(prog_path.exists())
            prog = W.charger_json(prog_path, {}).get("evenements", [])
            self.assertTrue(prog, "no scheduled event written")

            par_id = {e["id"]: e["T"] for e in prog if "id" in e and "T" in e}
            for e in prog:
                # (a) no event emitted this tick is in the tick's past.
                self.assertGreaterEqual(
                    e["T"], t_de,
                    f"event « {e['id']} » (T={e['T']}) is prior to the current t_de={t_de}",
                )
                # (b) a derived event is never before its cause (causal chaining).
                cause = e.get("cause")
                if cause in par_id:
                    self.assertGreaterEqual(
                        e["T"], par_id[cause],
                        f"« {e['id']} » (T={e['T']}) is prior to its cause "
                        f"« {cause} » (T={par_id[cause]})",
                    )

    # --- Non-destructive (apply): events.json / world.json intact ---

    def test_apply_non_destructif_sur_fichiers_proteges(self):
        """PRE+POST --apply cycle: `events.json` and `world.json` remain INTACT.

        On a COPY: we run a resolved raid (PRE apply) then a propagated player action
        (POST apply) and verify that the PROTECTED files are never rewritten —
        only `actors.json` and `scheduled_events.json` change.
        """
        with tempfile.TemporaryDirectory() as d:
            camp = _copier_campagne(Path(d))
            ev_avant = (camp / "events.json").read_bytes() \
                if (camp / "events.json").exists() else None
            monde_avant = (camp / "world.json").read_bytes() \
                if (camp / "world.json").exists() else None

            WT.pre(camp, t_session=ECHEANCE_RAID, cone=None, apply=True)
            session = {
                "actions": ["Rubis a incendié le campement de la Bande du Corbeau au Gué"],
                "etat_fin": {"lieu_actuel": "Gué du Corbeau"},
            }
            WT.post(camp, session=session, apply=True)

            if ev_avant is not None:
                self.assertEqual((camp / "events.json").read_bytes(), ev_avant,
                                 "events.json was modified (forbidden)")
            if monde_avant is not None:
                self.assertEqual((camp / "world.json").read_bytes(), monde_avant,
                                 "world.json was modified (forbidden)")
            # The ALLOWED files, for their part, must exist.
            self.assertTrue((camp / "actors.json").exists())
            self.assertTrue((camp / "scheduled_events.json").exists())


# ════════════════════════════════════════════════════════════════════════════
#  End-to-end: PRE (crossing) → POST (prevention) on a COPY, --apply
# ════════════════════════════════════════════════════════════════════════════

@unittest.skipUnless(_campagne_reelle_complete(), _RAISON_SKIP)
class TestIntegrationBoutEnBout(unittest.TestCase):
    """Full sequence: the player crosses then PREVENTS the raid, state persisted."""

    def tearDown(self):
        os.environ.pop(WT._ENV_AGENT_CMD, None)

    def test_cycle_complet_pre_puis_post_apply(self):
        os.environ.pop(WT._ENV_AGENT_CMD, None)
        with tempfile.TemporaryDirectory() as d:
            camp = _copier_campagne(Path(d))

            # 1) PRE apply at the deadline: the raid resolves (the Bande acts BEFORE the PC).
            cone = {"locations": [GUE], "fenetre": [0, ECHEANCE_RAID], "lieu_joueur": GUE,
                    "trajectoire": [{"lieu": GUE, "de": 0, "a": None}]}
            res_pre = WT.pre(camp, t_session=ECHEANCE_RAID, cone=cone, apply=True)
            # The Bande was crossed and the raid resolved (accomplished) → persisted.
            self.assertIn(BANDE, {c["acteur"] for c in res_pre["croisements"]})
            idx = W.index_acteurs(W.charger_acteurs(camp))
            raid = next(i for i in idx[BANDE]["plan"] if i["id"] == INTENT_RAID)
            self.assertIn(raid["statut"], ("accompli", "echoue"))

            # 2) POST apply: the player reacts and disperses the Bande → propagation.
            session = {
                "actions": [
                    "Rubis a attaqué et dispersé la Bande du Corbeau au Gué, "
                    "stoppant définitivement la menace du raid",
                ],
                "lieux_visites": ["Gué du Corbeau"],
                "etat_fin": {"lieu_actuel": "Gué du Corbeau"},
            }
            res_post = WT.post(camp, session=session, apply=True)
            self.assertTrue(res_post["ecritures"])
            self.assertTrue(res_post["propagations"])

            # 3) Final invariant: all persisted trajectories remain valid
            #    (no teleportation introduced by successive writes).
            geo = W.charger_geo(camp)
            for aid, acteur in W.index_acteurs(W.charger_acteurs(camp)).items():
                self.assertEqual(
                    W.valider_trajectoire(geo, W.trajectoire_de(acteur)), [],
                    f"trajectory of « {aid} » corrupted after the full cycle",
                )


if __name__ == "__main__":
    unittest.main(verbosity=2)
