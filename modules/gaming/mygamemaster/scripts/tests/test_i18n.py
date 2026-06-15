#!/usr/bin/env python3
"""
test_i18n.py — Tests for the runtime UI-string localization helper (i18n.py).

STDLIB `unittest` (no pytest required). Run from `scripts/`:
    python3 -m unittest discover

Proves the FAIL-OPEN, English-first contract:
  * default/fallback locale = English (unknown lang / unknown key → en / raw key);
  * `t()` returns FR strings when lang='fr', and tolerant lang tags ('FR', 'fr-FR');
  * a French locale lacking a key falls back to the English string;
  * resolve_lang cascade: env MGM_LANGUAGE > monde.meta.langue > 'en';
  * scene_brief renders FR column labels when meta.langue='fr'.
"""

import os
import unittest

import i18n
import scene_brief as SB


class TestTranslate(unittest.TestCase):
    def test_default_is_english(self):
        # No lang → English reference string.
        self.assertEqual(i18n.t("brief.location"), "LOCATION")
        self.assertEqual(i18n.t("brief.location", None), "LOCATION")
        self.assertEqual(i18n.t("brief.location", "en"), "LOCATION")

    def test_french_strings(self):
        self.assertEqual(i18n.t("brief.location", "fr"), "LIEU")
        self.assertEqual(i18n.t("brief.title", "fr"), "BRÈVE DE SCÈNE")
        self.assertEqual(i18n.t("pause.resumed", "fr"), "▶️ *Partie reprise.*")
        self.assertEqual(i18n.t("persisted.header", "fr"), "💾 Persisté :")

    def test_unknown_lang_falls_back_to_english(self):
        self.assertEqual(i18n.t("brief.stakes", "de"), "STAKES")
        self.assertEqual(i18n.t("brief.stakes", "zz-XX"), "STAKES")

    def test_unknown_key_returns_key(self):
        self.assertEqual(i18n.t("nope.missing", "fr"), "nope.missing")
        self.assertEqual(i18n.t("nope.missing"), "nope.missing")

    def test_missing_fr_key_falls_back_to_english(self):
        # Simulate a partial locale: inject a key only present in 'en'.
        i18n.TABLES["en"]["_probe.only_en"] = "ONLY_EN"
        try:
            self.assertEqual(i18n.t("_probe.only_en", "fr"), "ONLY_EN")
        finally:
            i18n.TABLES["en"].pop("_probe.only_en", None)

    def test_format_kwargs(self):
        self.assertEqual(i18n.t("brief.more", "en", n=3), "(+3 more)")
        self.assertEqual(i18n.t("brief.more", "fr", n=3), "(+3 autres)")

    def test_tolerant_lang_tags(self):
        self.assertEqual(i18n.normalize_lang("FR"), "fr")
        self.assertEqual(i18n.normalize_lang("fr-FR"), "fr")
        self.assertEqual(i18n.normalize_lang("fr_FR"), "fr")
        self.assertEqual(i18n.normalize_lang(""), "en")
        self.assertEqual(i18n.normalize_lang(None), "en")
        self.assertEqual(i18n.normalize_lang(123), "en")


class TestResolveLang(unittest.TestCase):
    def setUp(self):
        self._saved = os.environ.pop("MGM_LANGUAGE", None)

    def tearDown(self):
        if self._saved is not None:
            os.environ["MGM_LANGUAGE"] = self._saved
        else:
            os.environ.pop("MGM_LANGUAGE", None)

    def test_default_en(self):
        self.assertEqual(i18n.resolve_lang(None), "en")
        self.assertEqual(i18n.resolve_lang({}), "en")
        self.assertEqual(i18n.resolve_lang({"meta": {}}), "en")

    def test_meta_langue(self):
        self.assertEqual(i18n.resolve_lang({"meta": {"langue": "fr"}}), "fr")
        self.assertEqual(i18n.resolve_lang({"meta": {"langue": "FR"}}), "fr")

    def test_env_overrides_meta(self):
        os.environ["MGM_LANGUAGE"] = "en"
        self.assertEqual(i18n.resolve_lang({"meta": {"langue": "fr"}}), "en")
        os.environ["MGM_LANGUAGE"] = "fr"
        self.assertEqual(i18n.resolve_lang({"meta": {"langue": "en"}}), "fr")


class TestSceneBriefFrench(unittest.TestCase):
    """End-to-end: meta.langue='fr' localizes the brief frame + column labels."""

    def test_minimal_brief_fr_labels(self):
        # No geo.json → minimal brief (fail-open), still rendered in FR.
        txt = SB._rendre_texte_minimal({"T": 0, "lieu": "lieu:x/y"}, "fr")
        self.assertIn("BRÈVE DE SCÈNE", txt)
        self.assertIn("LIEU", txt)
        self.assertNotIn("SCENE BRIEF", txt)
        self.assertNotIn("LOCATION", txt)

    def test_minimal_brief_en_unchanged(self):
        # Default (en / None) stays byte-identical to the historical output.
        txt_none = SB._rendre_texte_minimal({"T": 0, "lieu": "lieu:x/y"})
        txt_en = SB._rendre_texte_minimal({"T": 0, "lieu": "lieu:x/y"}, "en")
        self.assertEqual(txt_none, txt_en)
        self.assertIn("SCENE BRIEF", txt_none)
        self.assertIn("LOCATION", txt_none)

    def test_more_marker_fr(self):
        self.assertEqual(SB._joindre(["a", "b"], " · ", 2, "fr"),
                         "a · b · (+2 autres)")
        self.assertEqual(SB._joindre(["a", "b"], " · ", 2),
                         "a · b · (+2 more)")


if __name__ == "__main__":
    unittest.main()
