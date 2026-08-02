#!/usr/bin/env python3
"""
test_load_campaign.py — FAIL-LOUD guard against pre-rename FRENCH structural keys.

Run from `scripts/`:
    python3 -m unittest discover -s tests

The guard exists because the fail-open version of this code cost a real campaign
its whole world: reading French keys through English accessors yielded
`geo.locations` 38→0, `actors` 10→0, `events` 61→0 while `meta.features` still
resolved, so the engine happily simulated a living world over nothing.

Covered here:
  * a campaign carrying French structural keys MUST raise / exit non-zero;
  * the message MUST name the file, the offending key, the expected key and the
    migration command (that is what makes it actionable rather than merely loud);
  * the explicit override (env var AND CLI flag) MUST let it through;
  * a clean English campaign MUST be unaffected — no false positive, and in
    particular the French keys the rename deliberately KEPT must stay silent.

Campaigns are built inline in a temp dir; nothing on disk is touched.
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

import load_campaign as LC  # noqa: E402


def _monde_en() -> dict:
    """Minimal, schema-shaped campaign with ENGLISH keys throughout."""
    return {
        "meta": {"name": "T", "time": {"regime": "Narrative"},
                 "features": {"traceability": True, "tts": True}},
        "modules": {
            "travel": {"actif": True, "params": {}},
            "factions": {"actif": False, "params": {}},
            "proactivite_pnj": {"actif": False, "params": {}},
            "artefacts": {"actif": False, "params": {}},
            "politique": {"actif": False, "params": {}},
            "weather": {"actif": False, "params": {}},
            "worldbuilding_lieux": {"actif": False, "params": {}},
            "construction_royaume": {"actif": False, "params": {}},
        },
        "rules": {"time": {"movements": {"depuis_a_vers": {"b": "30min — west"}},
                           "tracking": {"current_day": 1, "current_hour": "morning"}}},
        "global_state": {"factions": [], "timeline": "",
                         "faction_actions_horloge": {"actions": []}},
        "universe": {"regions": [{"id": "region:r", "name": "R",
                                  "locations": [{"id": "lieu:r/a", "name": "A"}]}]},
    }


class _CampagneTemporaire(unittest.TestCase):
    """Builds a throwaway campaign directory per test."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="mgm-load-"))
        self.camp = self.tmp / "campagne"
        self.camp.mkdir()
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def ecrire(self, nom: str, data) -> None:
        (self.camp / nom).write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def cli(self, *args: str, env: dict | None = None):
        """Runs load_campaign.py as a subprocess, override cleared by default."""
        environnement = dict(os.environ)
        environnement.pop(LC.ENV_ALLOW_LEGACY, None)
        if env:
            environnement.update(env)
        return subprocess.run(
            [sys.executable, str(SCRIPTS_DIR / "load_campaign.py"), str(self.camp), *args],
            capture_output=True, text=True, env=environnement)


class TestCampagneSaine(_CampagneTemporaire):
    """The must-PASS side: no false positive on migrated data."""

    def test_campagne_anglaise_ne_leve_pas(self):
        self.ecrire("world.json", _monde_en())
        self.assertEqual(LC.verifier_cles_legacy(self.camp), [])
        rapport = LC.analyser(self.camp)
        self.assertTrue(rapport["ok"], rapport)

    def test_cles_francaises_conservees_ne_declenchent_rien(self):
        """The rename KEPT these French keys on purpose — flagging them would
        make the guard unusable on every real campaign."""
        monde = _monde_en()
        monde["global_state"]["factions"] = [{
            "name": "F", "ressources": "x", "relations": [], "motivations": [],
            "situation": "s", "localisation": "lieu:r/a", "faction": "F",
        }]
        monde["universe"]["regions"][0]["locations"][0].update(
            {"lieu": "x", "vers": "y", "ambiance": "z", "unite": "jour"})
        self.ecrire("world.json", monde)
        self.assertEqual(LC.verifier_cles_legacy(self.camp), [])

    def test_fichier_json_casse_nest_pas_signale_comme_legacy(self):
        """Broken JSON is someone else's error to report — not a legacy finding."""
        self.ecrire("world.json", _monde_en())
        (self.camp / "actors.json").write_text("{ oops", encoding="utf-8")
        self.assertEqual(LC.verifier_cles_legacy(self.camp), [])


class TestFailLoud(_CampagneTemporaire):
    """The must-RAISE side."""

    def _campagne_legacy(self):
        monde = _monde_en()
        monde["univers"] = monde.pop("universe")
        monde["etat_global"] = monde.pop("global_state")
        self.ecrire("world.json", monde)
        self.ecrire("actors.json", {"acteurs": [{"id": "acteur:x", "nom": "X"}]})
        self.ecrire("events.json", {"evenements": []})
        self.ecrire("geo.json", {"lieux": []})

    def test_cles_fr_levent_une_erreur(self):
        self._campagne_legacy()
        with self.assertRaises(LC.LegacyKeysError):
            LC.verifier_cles_legacy(self.camp)

    def test_analyser_leve_avant_de_produire_un_rapport(self):
        """A legacy campaign must never be reported READY on sections the
        engine cannot see."""
        self._campagne_legacy()
        with self.assertRaises(LC.LegacyKeysError):
            LC.analyser(self.camp)

    def test_message_est_actionnable(self):
        self._campagne_legacy()
        with self.assertRaises(LC.LegacyKeysError) as ctx:
            LC.verifier_cles_legacy(self.camp)
        msg = str(ctx.exception)
        for attendu in ("univers", "universe", "etat_global", "global_state",
                        "acteurs", "actors", "evenements", "events", "lieux", "locations"):
            self.assertIn(attendu, msg, f"message must name '{attendu}'")
        self.assertIn("world.json", msg)
        self.assertIn("actors.json", msg)
        self.assertIn("migrate_campaign_fr_en.py", msg)
        self.assertIn(LC.ENV_ALLOW_LEGACY, msg)
        self.assertIn("--allow-legacy-keys", msg)

    def test_findings_structures_exposes(self):
        self._campagne_legacy()
        with self.assertRaises(LC.LegacyKeysError) as ctx:
            LC.verifier_cles_legacy(self.camp)
        paires = {(f["trouvee"], f["attendue"]) for f in ctx.exception.findings}
        self.assertIn(("univers", "universe"), paires)
        self.assertIn(("acteurs", "actors"), paires)
        self.assertIn(("nom", "name"), paires)

    def test_coexistence_fr_en_est_signalee_comme_ambigue(self):
        """FR and EN side by side: readers take the EN one, writers may keep
        feeding the FR one. Undecidable → blocking, with its own wording."""
        monde = _monde_en()
        monde["univers"] = {"regions": []}
        self.ecrire("world.json", monde)
        with self.assertRaises(LC.LegacyKeysError) as ctx:
            LC.verifier_cles_legacy(self.camp)
        genres = {f["genre"] for f in ctx.exception.findings if f["trouvee"] == "univers"}
        self.assertEqual(genres, {"ambigu"})
        self.assertIn("COEXISTS", str(ctx.exception))

    def test_cles_fr_imbriquees_sont_detectees(self):
        """The rot is not only at the root: `nom` inside a location is the very
        key that made find_pnj return None for every NPC."""
        monde = _monde_en()
        monde["universe"]["regions"][0]["locations"][0] = {"id": "lieu:r/a", "nom": "A"}
        self.ecrire("world.json", monde)
        with self.assertRaises(LC.LegacyKeysError) as ctx:
            LC.verifier_cles_legacy(self.camp)
        chemins = [f["chemin"] for f in ctx.exception.findings]
        self.assertIn("$.universe.regions[0].locations[0].nom", chemins)


class TestContournementExplicite(_CampagneTemporaire):
    """Escape hatch: inspecting an un-migrated backup must stay possible."""

    def setUp(self):
        super().setUp()
        monde = _monde_en()
        monde["univers"] = monde.pop("universe")
        self.ecrire("world.json", monde)

    def test_parametre_explicite(self):
        trouvailles = LC.verifier_cles_legacy(self.camp, autoriser=True)
        self.assertTrue(trouvailles)

    def test_variable_denvironnement(self):
        os.environ[LC.ENV_ALLOW_LEGACY] = "1"
        self.addCleanup(os.environ.pop, LC.ENV_ALLOW_LEGACY, None)
        self.assertTrue(LC.verifier_cles_legacy(self.camp))

    def test_variable_denvironnement_a_zero_ne_contourne_pas(self):
        os.environ[LC.ENV_ALLOW_LEGACY] = "0"
        self.addCleanup(os.environ.pop, LC.ENV_ALLOW_LEGACY, None)
        with self.assertRaises(LC.LegacyKeysError):
            LC.verifier_cles_legacy(self.camp)

    def test_autoriser_false_ignore_lenvironnement(self):
        os.environ[LC.ENV_ALLOW_LEGACY] = "1"
        self.addCleanup(os.environ.pop, LC.ENV_ALLOW_LEGACY, None)
        with self.assertRaises(LC.LegacyKeysError):
            LC.verifier_cles_legacy(self.camp, autoriser=False)


class TestCLI(_CampagneTemporaire):

    def test_campagne_saine_sort_a_zero(self):
        self.ecrire("world.json", _monde_en())
        self.assertEqual(self.cli().returncode, 0)

    def test_campagne_legacy_sort_a_deux(self):
        monde = _monde_en()
        monde["univers"] = monde.pop("universe")
        self.ecrire("world.json", monde)
        proc = self.cli()
        self.assertEqual(proc.returncode, 2)
        self.assertIn("refusing to load", proc.stdout + proc.stderr)

    def test_drapeau_allow_legacy_keys(self):
        monde = _monde_en()
        monde["univers"] = monde.pop("universe")
        self.ecrire("world.json", monde)
        proc = self.cli("--allow-legacy-keys")
        self.assertNotEqual(proc.returncode, 2)
        sortie = proc.stdout + proc.stderr
        self.assertNotIn("refusing to load", sortie)
        self.assertIn("override is active", sortie)

    def test_env_allow_legacy_keys(self):
        monde = _monde_en()
        monde["univers"] = monde.pop("universe")
        self.ecrire("world.json", monde)
        proc = self.cli(env={LC.ENV_ALLOW_LEGACY: "1"})
        self.assertNotEqual(proc.returncode, 2)

    def test_json_reste_exploitable_sur_campagne_saine(self):
        self.ecrire("world.json", _monde_en())
        proc = self.cli("--json")
        self.assertEqual(proc.returncode, 0)
        self.assertTrue(json.loads(proc.stdout)["ok"])


class TestCampagnesLivrees(unittest.TestCase):
    """The two shipped campaigns must never regress into legacy keys."""

    RACINE = SCRIPTS_DIR.parents[3] / "data" / "mygamemaster" / "campaigns"

    def test_template_et_exemple_sont_propres(self):
        for nom in ("_template", "example-mistfall"):
            camp = self.RACINE / nom
            if not camp.is_dir():
                self.skipTest(f"campaign {nom} not present")
            with self.subTest(campagne=nom):
                self.assertEqual(LC.verifier_cles_legacy(camp), [])


if __name__ == "__main__":
    unittest.main()
