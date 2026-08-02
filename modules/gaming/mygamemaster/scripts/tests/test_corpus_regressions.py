"""test_corpus_regressions.py — non-regression corpus distilled from a real
34-session campaign that was retired from play and turned into test data.

Every fixture under `tests/fixtures/corpus_*` is an ANONYMISED, MINIMISED
reproduction of a pathology observed in that campaign. No proper noun, no
narrative text, no player verbatim and no Discord identifier survives: only the
SHAPE of the bug. The campaign itself stays private and git-ignored.

Four pathologies, in the order they cost the most:

  P1  Fail-open on legacy French keys. A campaign whose structural keys are
      still `univers` / `etat_global` / `geo.lieux` / `acteurs` / `evenements`
      is read by the English engine as 38 locations → 0, 10 actors → 0,
      61 events → 0, WITHOUT a single error. The engine must refuse, loudly.

  P2  Temporal drift. Four clocks disagreed (tracking day, global_state hour,
      in-game calendar, actors.meta.t_reference), measured drift +51 days;
      events flagged `resolu` carried a T in the future; faction deadlines had
      been overdue for ~55 days without ever firing.

  P3  One list, three incompatible element shapes. `npcs_met` (ex
      `pnj_rencontres`) appeared as {name,role}, {id,name,role_scene} and
      {npc_id,moment,...} depending on the session. Entries with no `name` are
      currently dropped on the floor.

  P4  Schema anti-patterns. Journals indexed by in-fiction day ({"J18": ...})
      and root keys carrying a session number (`hooks_S33_vers_S34`) grow
      without bound and are invisible to schema validation.

Tests marked `@unittest.expectedFailure` describe behaviour the engine does NOT
have yet; the comment above each one states what is missing. They must be
un-marked, not deleted, when the corresponding guard lands — and unittest will
insist: once a guard makes one of them pass, it is reported as an unexpected
success and the suite goes red until the marker is removed.

Run:  python3 -m unittest discover -s tests   (from scripts/)
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import unittest
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent.parent
FIXTURES = Path(__file__).resolve().parent / "fixtures"

if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import check_session  # noqa: E402
import load_campaign  # noqa: E402
import validate_schema  # noqa: E402
import worldlib  # noqa: E402


def run_script(nom: str, *args: str, env: dict | None = None):
    """Runs a scripts/*.py through its CLI, with a clean legacy-override env."""
    environnement = dict(os.environ)
    environnement.pop("MGM_ALLOW_LEGACY_KEYS", None)
    if env:
        environnement.update(env)
    return subprocess.run(
        [sys.executable, str(SCRIPTS_DIR / nom), *args],
        capture_output=True, text=True, env=environnement,
    )


def sortie(proc) -> str:
    return (proc.stdout or "") + (proc.stderr or "")


def rapport_session(corpus: str, session: int | None = None) -> dict:
    return check_session.analyser(FIXTURES / corpus, session)


def regles(rapport: dict) -> set[str]:
    return {e["regle"] for e in rapport["ecarts"]}


def texte(rapport: dict) -> str:
    """Only the discrepancies: the campaign path would match anything."""
    return json.dumps(rapport["ecarts"], ensure_ascii=False)


def ecarts_schema(chemin_relatif: str, schema: str) -> list[str]:
    data = json.loads((FIXTURES / chemin_relatif).read_text(encoding="utf-8"))
    sch = validate_schema.charger_schema(schema)
    return validate_schema.valider(data, sch, sch)


def charger(chemin_relatif: str):
    return json.loads((FIXTURES / chemin_relatif).read_text(encoding="utf-8"))


class TestLegacyFrenchKeysFailLoud(unittest.TestCase):

    def test_legacy_campaign_is_refused_by_the_cli(self):
        proc = run_script("load_campaign.py", str(FIXTURES / "corpus_fr_keys"))
        assert proc.returncode == 2, (
            "a campaign whose structural keys are still French must NOT load; "
            f"exit code was {proc.returncode}"
        )
        message = sortie(proc)
        for cle in ("univers", "etat_global", "lieux", "acteurs", "evenements"):
            assert cle in message, (
                f"the refusal must name the offending key '{cle}' so the GM knows "
                "which file to migrate, instead of failing opaquely"
            )

    def test_legacy_campaign_raises_at_the_api_level(self):
        with self.assertRaises(Exception) as ctx:
            load_campaign.analyser(FIXTURES / "corpus_fr_keys")
        assert "univers" in str(ctx.exception)

    def test_legacy_guard_is_overridable_for_backup_inspection(self):
        """Reading an un-migrated backup on purpose must stay possible."""
        proc = run_script("load_campaign.py", str(FIXTURES / "corpus_fr_keys"),
                          env={"MGM_ALLOW_LEGACY_KEYS": "1"})
        assert proc.returncode != 2
        assert "refusing to load" not in sortie(proc)

    def test_migrated_campaign_loads_clean(self):
        """Control: identical content in English keys must be READY."""
        rapport = load_campaign.analyser(FIXTURES / "corpus_en_control")
        assert rapport["ok"] is True, rapport
        assert not rapport["cles_inconnues"]
        assert not rapport["donnees_manquantes"]

    def test_legacy_keys_are_invisible_to_english_readers(self):
        """Why the guard is mandatory: no reader can notice the loss itself.

        Both fixtures carry the same 3 locations / 2 actors / 1 event. Read
        through the English accessors, the French one yields nothing at all and
        raises nothing — the exact silence that emptied a live campaign.
        """
        fr, en = FIXTURES / "corpus_fr_keys", FIXTURES / "corpus_en_control"

        assert len(charger("corpus_fr_keys/geo.json")["lieux"]) == 3
        assert worldlib.index_lieux(worldlib.charger_geo(fr)) == {}
        assert len(worldlib.index_lieux(worldlib.charger_geo(en))) == 3

        assert len(charger("corpus_fr_keys/actors.json")["acteurs"]) == 2
        assert worldlib.index_acteurs(worldlib.charger_acteurs(fr)) == {}
        assert len(worldlib.index_acteurs(worldlib.charger_acteurs(en))) == 2

        assert charger("corpus_fr_keys/events.json").get("events") is None
        assert len(charger("corpus_en_control/events.json")["events"]) == 1

    def test_legacy_file_names_are_refused_not_ignored(self):
        """The other half of P1: files still named monde.json / pnj.json."""
        proc = run_script("load_campaign.py",
                          str(FIXTURES / "corpus_fr_filenames"))
        assert proc.returncode == 2
        assert "world.json" in sortie(proc)


class TestTemporalDrift(unittest.TestCase):

    def test_ut_to_day_conversion_is_the_reference(self):
        """144 UT = 1 day is the invariant every clock cross-check rests on.

        In the source campaign the T axis was exact up to T=4500 (day 32), then
        the GM wrote T « by eye »: T=18800 was labelled day 80 while the
        canonical conversion puts it at day 131.
        """
        assert worldlib.UT_PAR_JOUR == 144
        assert worldlib.t_vers_jour_heure(4500)[0] == 32
        assert worldlib.t_vers_jour_heure(18800)[0] == 131
        assert worldlib.jour_heure_vers_t(81, 0) == 11520

    def test_the_drift_fixture_really_holds_four_disagreeing_clocks(self):
        """Guards the fixture itself: it must keep reproducing the pathology."""
        monde = charger("corpus_clock_drift/world.json")
        acteurs = charger("corpus_clock_drift/actors.json")

        jour_suivi = monde["rules"]["time"]["tracking"]["current_day"]
        jour_calendrier = int(
            monde["global_state"]["calendrier_in_game"]["aujourd_hui"].lstrip("J"))
        jour_ancre = worldlib.t_vers_jour_heure(acteurs["meta"]["t_reference"])[0]

        assert jour_suivi == 81
        assert jour_calendrier == 62
        assert jour_ancre == 132
        assert max(jour_suivi, jour_calendrier, jour_ancre) \
            - min(jour_suivi, jour_calendrier, jour_ancre) > 1

    def test_overdue_faction_deadline_is_flagged(self):
        rapport = rapport_session("corpus_clock_drift", 2)
        assert "echeance_depassee" in regles(rapport)
        assert rapport["n_bloquants"] >= 1

    def test_coherent_campaign_reports_nothing(self):
        """Control: aligned clocks must stay silent, or the tests mean nothing."""
        rapport = rapport_session("corpus_clock_coherent", 2)
        assert rapport["ecarts"] == []
        assert rapport["n_bloquants"] == 0

    # EXPECTED FAILURE — No clock cross-check exists yet. rules.time.tracking.current_day  (81), global_state.calendrier_in_game.aujourd_hui (62) and  actors.meta.t_reference (day 132) may disagree by 70 days without  a single warning. Un-mark when the cross-check lands.
    @unittest.expectedFailure
    def test_divergent_clocks_are_flagged(self):
        rapport = rapport_session("corpus_clock_drift", 2)
        motifs = ("horloge", "clock", "derive", "drift", "t_reference")
        assert any(m in texte(rapport).lower() for m in motifs), texte(rapport)

    # EXPECTED FAILURE — No statut/T consistency check exists yet. An event marked  'resolu' with a T in the future breaks any deterministic replay,  and nothing reports it.
    @unittest.expectedFailure
    def test_resolved_event_dated_in_the_future_is_flagged(self):
        rapport = rapport_session("corpus_clock_drift", 2)
        assert "evt:resolved-future-01" in texte(rapport), texte(rapport)

    # EXPECTED FAILURE — scheduled_events.json is never read by the closing check, so an  event still 'programme' whose T is long past is never fired nor  reported.
    @unittest.expectedFailure
    def test_overdue_scheduled_event_is_flagged(self):
        rapport = rapport_session("corpus_clock_drift", 2)
        assert "evt:scheduled-overdue-01" in texte(rapport), texte(rapport)

    # EXPECTED FAILURE — No T-axis drift detector. Event ids carry their intended day  (evt:anchor-d80-01) while T says day 131; two ids claim day 80  with T=18800 and T=24294. A slope check of id-day vs T//144+1  would have caught this at the first drifting session.
    @unittest.expectedFailure
    def test_t_axis_drift_between_event_id_and_T_is_flagged(self):
        rapport = rapport_session("corpus_clock_drift", 2)
        assert "evt:anchor-d80-01" in texte(rapport), texte(rapport)


class TestNpcsMetShapes(unittest.TestCase):

    def test_fixture_holds_three_distinct_shapes(self):
        formes = set()
        for num in (1, 2, 3):
            session = charger(f"corpus_npcs_met_shapes/sessions/00{num}.json")
            formes.add(frozenset(session["npcs_met"][0]))
        assert len(formes) == 3

    def test_name_only_shape_is_resolved(self):
        rapport = rapport_session("corpus_npcs_met_shapes", 1)
        assert rapport["ecarts"] == []

    def test_id_and_name_shape_is_resolved(self):
        rapport = rapport_session("corpus_npcs_met_shapes", 2)
        assert rapport["ecarts"] == []

    def test_mixed_shapes_do_not_crash_and_unknown_name_is_flagged(self):
        """A bare string, an id-only dict and a named dict in the same list."""
        rapport = rapport_session("corpus_npcs_met_shapes", 4)
        assert "pnj_sans_fiche" in regles(rapport)
        assert "NPC_UNKNOWN" in texte(rapport)

    # EXPECTED FAILURE — check_session.nom_de() reads only 'name' (and duplicates that  lookup instead of falling back), so an entry shaped  {npc_id, moment, lieu, interaction} yields '' and is skipped  silently — even when the id resolves to no NPC at all. Either  resolve npc_id against npcs.json or reject the shape, but do  not ignore it.
    @unittest.expectedFailure
    def test_id_only_shape_is_not_silently_ignored(self):
        rapport = rapport_session("corpus_npcs_met_shapes", 3)
        assert rapport["ecarts"] != [], (
            "npc:absent is referenced by session 3 and exists nowhere: "
            "the closing check reported nothing at all"
        )

    # EXPECTED FAILURE — Same blind spot, namespace flavour: a faction id listed among  the NPCs met is neither resolved nor rejected.
    @unittest.expectedFailure
    def test_faction_namespace_listed_as_npc_is_not_silently_ignored(self):
        rapport = rapport_session("corpus_npcs_met_shapes", 4)
        assert "faction:faction_a" in texte(rapport), texte(rapport)


class TestSchemaAntiPatterns(unittest.TestCase):

    def test_schema_validation_still_catches_a_plainly_broken_session(self):
        """Control: the validator is wired, so the xfails below are real gaps."""
        ecarts = ecarts_schema(
            "corpus_schema_antipatterns/sessions/034.json", "session")
        assert any("npcs_met" in e for e in ecarts), ecarts
        assert any("visited_locations" in e for e in ecarts), ecarts

    # EXPECTED FAILURE — npcs.schema.json has no rule against day-indexed maps. A journal  shaped {'J18': ..., 'J37-J62': ..., 'J81': ...} is unqueryable,  unboundable and grows by one key per in-fiction day (it reached  10k tokens in the source campaign). emotions.history is capped  at 20; journal, the field actually used, is capped by nothing.
    @unittest.expectedFailure
    def test_day_indexed_journal_is_flagged(self):
        ecarts = ecarts_schema(
            "corpus_schema_antipatterns/npcs.json", "npcs")
        assert any("journal" in e for e in ecarts), ecarts

    # EXPECTED FAILURE — session.schema.json is additionalProperties:true, so a root key  carrying a session number (hooks_S33_vers_S34,  mystique_signes_S33) validates clean. One new key per session  means the schema can never describe the file.
    @unittest.expectedFailure
    def test_session_numbered_root_keys_are_flagged(self):
        ecarts = ecarts_schema(
            "corpus_schema_antipatterns/sessions/033.json", "session")
        assert any("hooks_S33_vers_S34" in e or "mystique_signes_S33" in e
                   for e in ecarts), ecarts

    def test_fixture_still_carries_the_anti_patterns(self):
        fiche = charger("corpus_schema_antipatterns/npcs.json")[0]
        assert set(fiche["journal"]) == {"J18", "J19", "J37-J62", "J81"}
        session = charger("corpus_schema_antipatterns/sessions/033.json")
        assert "hooks_S33_vers_S34" in session
        assert "mystique_signes_S33" in session


if __name__ == "__main__":
    unittest.main(verbosity=2)
