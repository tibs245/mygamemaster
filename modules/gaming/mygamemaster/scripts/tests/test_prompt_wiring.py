#!/usr/bin/env python3
"""
test_prompt_wiring.py — the rule catalogue must be reachable from the shipped prompt.

STDLIB `unittest` (no pytest required). Run from `scripts/`:
    python3 -m unittest discover

The field report (`docs/10-field-report.md` §2) records the pathology this guards against:
the ~60 locked lessons lived in a file nothing loaded at play time, and "a rule that is only
written down gets violated again" (8 agency violations within one hour of writing the rule that
forbade them). These checks prove, mechanically, that:

  * `SKILL.md` names `references/locked-lessons.md` and loads it in its Invariant;
  * the five sentences of the catalogue's "prompt core" reach `SKILL.md` verbatim;
  * every rule ID cited anywhere in the shipped prompt is defined in the catalogue
    (traceability: the two documents state the same rule, never a drifted copy);
  * `SKILL.md` stays inside its size budget — the production skill once froze at
    104 162 characters against a hard limit of 100 000 and refused 76 writes. Measured in
    UTF-8 bytes, the conservative reading (the file is emoji-heavy: bytes > characters);
  * the campaign-creation path wires `references/player-profile-template.md`, so a table
    captures its player's preferences instead of rediscovering them over 34 sessions.

ESCAPE HATCHES (an operator must be able to unblock a live campaign):
  * `MYGM_SKIP_PROMPT_WIRING_CHECKS=1` — skip this whole module.
  * `MYGM_SKILL_CHAR_BUDGET=<n>` — raise (or lower) the size budget for `SKILL.md`, in bytes.
    The hard product limit is 100 000; the default budget below keeps a deliberate margin.
"""

import os
import re
import unittest
from pathlib import Path

# tests/ → scripts/ → mygamemaster/ → gaming/ → modules/ → repo root
MODULE = Path(__file__).resolve().parents[2]
RACINE = MODULE.parents[2]

SKILL = MODULE / "SKILL.md"
CATALOGUE = MODULE / "references" / "locked-lessons.md"
PROFIL = MODULE / "references" / "player-profile-template.md"
INITIATION = RACINE / "modules" / "gaming" / "mygamemaster-initiation" / "SKILL.md"
CREER = RACINE / "docs" / "CREATE-A-GAME.md"

# Hard product limit; the budget below keeps a margin so a growth spurt is caught early.
LIMITE_DURE = 100_000
BUDGET_DEFAUT = 92_000

SKIP = os.environ.get("MYGM_SKIP_PROMPT_WIRING_CHECKS") == "1"

# The catalogue's own "prompt core" — five sentences, in this order. Kept verbatim here so a
# reworded catalogue and a stale prompt cannot silently diverge: the test fails on both sides.
NOYAU = [
    ("AGENCY-01/02/03",
     "You never make the player's character act, speak or feel. "
     "You describe what he perceives."),
    ("TURN-01/02",
     "One player input = one moment = one STOP. You stop and you wait. "
     "The fast-forward signal is the only permission to advance."),
    ("TURN-03",
     "At the STOP you describe the state of the world. "
     "You propose nothing and you ask nothing."),
    ("KNOW-01/02",
     "A character knows only what a played scene taught him. "
     "What you know is not what he knows."),
    ("WORLD-07`, `AUDIT-01",
     "You read the sheets before narrating, never your memory."),
]

# Rule IDs as they appear in either document: FAMILY-NN.
RE_ID = re.compile(r"\b(AGENCY|TURN|KNOW|TIME|SPACE|AUDIT|WORLD|META|STYLE|MECH|DATA|CLOSE)-\d{2}\b")


def lire(chemin: Path) -> str:
    return chemin.read_text(encoding="utf-8")


@unittest.skipIf(SKIP, "MYGM_SKIP_PROMPT_WIRING_CHECKS=1")
class TestCatalogueAtteignable(unittest.TestCase):
    """The catalogue is cited by the prompt, not orphaned next to it."""

    def setUp(self):
        self.skill = lire(SKILL)

    def test_skill_cites_le_catalogue(self):
        self.assertIn("references/locked-lessons.md", self.skill,
                      "SKILL.md must point at the rule catalogue — a catalogue no prompt "
                      "names is a catalogue nothing enforces.")

    def test_citation_est_precoce(self):
        # "Prominent and early": inside the header block, before the first conduct section.
        tete = self.skill[:3000]
        self.assertIn("references/locked-lessons.md", tete,
                      "The catalogue reference must sit in the header block, not be buried "
                      "in the middle of an 87 000-character file.")

    def test_invariant_charge_le_catalogue(self):
        invariant = self.skill[self.skill.index("## Invariant"):]
        self.assertIn("references/locked-lessons.md", invariant,
                      "The session-start Invariant must load the catalogue.")

    def test_regle_une_seule_place(self):
        self.assertIn("One rule lives in exactly one place", self.skill,
                      "SKILL.md must carry the catalogue's preamble rule 1, so a future "
                      "editor restates a rule here instead of editing it there.")


@unittest.skipIf(SKIP, "MYGM_SKIP_PROMPT_WIRING_CHECKS=1")
class TestNoyauDePrompt(unittest.TestCase):
    """The five prompt-core sentences reach the shipped prompt, ID-anchored."""

    def setUp(self):
        self.skill = lire(SKILL)
        self.catalogue = lire(CATALOGUE)

    def test_les_cinq_phrases_sont_dans_le_catalogue(self):
        noyau = self.catalogue[self.catalogue.index("## The prompt core"):]
        for ids, phrase in NOYAU:
            self.assertIn(phrase, noyau,
                          f"'{phrase[:40]}…' is no longer the catalogue's wording — update "
                          "NOYAU in this test and the prompt together.")

    def test_les_cinq_phrases_sont_dans_le_skill(self):
        for ids, phrase in NOYAU:
            self.assertIn(phrase, self.skill,
                          f"prompt-core sentence missing from SKILL.md: '{phrase[:40]}…'")

    def test_les_phrases_sont_ancrees_sur_leurs_ids(self):
        for ids, phrase in NOYAU:
            debut = self.skill.index(phrase)
            fin = self.skill.index("\n", debut + len(phrase))
            self.assertIn(ids, self.skill[debut:fin],
                          f"prompt-core sentence is not anchored to {ids} — without the ID "
                          "the prompt and the catalogue are two rules, not one.")

    def test_ordre_du_noyau_respecte(self):
        positions = [self.skill.index(phrase) for _, phrase in NOYAU]
        self.assertEqual(positions, sorted(positions),
                         "The prompt core must appear in the catalogue's order.")

    def test_disciplines_ancrees_dans_le_corps_du_skill(self):
        # Beyond the header summary, the operational sections must carry the IDs too.
        corps = self.skill[self.skill.index("## Foundational Rules"):]
        for rid in ("AGENCY-01", "AGENCY-03", "TURN-01", "TURN-02", "TURN-03",
                    "KNOW-01", "WORLD-07", "AUDIT-01"):
            self.assertIn(rid, corps,
                          f"{rid} is stated in SKILL.md's body without its ID — anchor it.")


@unittest.skipIf(SKIP, "MYGM_SKIP_PROMPT_WIRING_CHECKS=1")
class TestIdsTracables(unittest.TestCase):
    """No prompt may cite a rule ID the catalogue does not define."""

    def setUp(self):
        self.catalogue = lire(CATALOGUE)
        self.definis = {m.group(0) for m in RE_ID.finditer(self.catalogue)}

    def test_le_catalogue_definit_des_ids(self):
        self.assertGreaterEqual(len(self.definis), 50,
                                "The catalogue should define ~61 rule IDs.")

    def test_aucun_id_orphelin(self):
        for chemin in (SKILL, INITIATION, PROFIL):
            texte = lire(chemin)
            cites = {m.group(0) for m in RE_ID.finditer(texte)}
            orphelins = sorted(cites - self.definis)
            self.assertEqual(orphelins, [],
                             f"{chemin.name} cites rule IDs absent from "
                             f"locked-lessons.md: {orphelins}")


@unittest.skipIf(SKIP, "MYGM_SKIP_PROMPT_WIRING_CHECKS=1")
class TestBudgetTaille(unittest.TestCase):
    """The shipped prompt has a size budget; it once froze at 104 162 characters."""

    def test_skill_tient_dans_le_budget(self):
        budget = int(os.environ.get("MYGM_SKILL_CHAR_BUDGET", BUDGET_DEFAUT))
        taille = len(SKILL.read_bytes())  # bytes, the conservative reading
        self.assertLessEqual(
            taille, budget,
            f"SKILL.md is {taille} bytes, over the {budget} budget "
            f"(hard product limit {LIMITE_DURE}). Replace prose with a rule ID and a "
            "pointer into references/locked-lessons.md rather than appending. "
            "To unblock a live campaign: MYGM_SKILL_CHAR_BUDGET=<n>.")

    def test_budget_sous_la_limite_dure(self):
        self.assertLess(BUDGET_DEFAUT, LIMITE_DURE,
                        "The budget must keep a margin under the hard limit.")


@unittest.skipIf(SKIP, "MYGM_SKIP_PROMPT_WIRING_CHECKS=1")
class TestProfilJoueurCable(unittest.TestCase):
    """The player profile template is consumed by the campaign-creation path."""

    def test_le_gabarit_existe(self):
        self.assertTrue(PROFIL.is_file())

    def test_onboarding_cree_le_profil(self):
        texte = lire(INITIATION)
        self.assertIn("player-profile-template.md", texte,
                      "The onboarding skill must copy the player profile template.")
        self.assertIn("player-profile.md", texte,
                      "The onboarding skill must name the file it writes into the campaign.")

    def test_doc_creation_partie_cite_le_gabarit(self):
        texte = lire(CREER)
        self.assertIn(
            "modules/gaming/mygamemaster/references/player-profile-template.md", texte,
            "docs/CREATE-A-GAME.md must tell the GM to capture player preferences.")
        self.assertIn("locked-lessons.md", texte,
                      "docs/CREATE-A-GAME.md must separate taste (profile) from doctrine "
                      "(catalogue), so neither file absorbs the other.")


if __name__ == "__main__":
    unittest.main()
