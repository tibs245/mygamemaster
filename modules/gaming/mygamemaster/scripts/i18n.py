#!/usr/bin/env python3
"""
i18n.py — Tiny, dependency-free runtime localization of the engine's UI strings.

The GM's NARRATION already comes from the LLM in the player's language. This
helper covers ONLY the engine's fixed scaffolding strings shown to players
(scene-brief column labels, the Steward "Persisted" block, pause/resume notes,
scoreboard headers, the compact state labels).

Design (fail-open, English-first):
  * `t(key, lang=None)` looks up a translation table. The default and FALLBACK
    locale is English ("en"): an unknown `key`, an unknown `lang`, or a `lang`
    that simply lacks an entry all degrade to the English string (and the raw
    key as a last resort). Behaviour is therefore BYTE-IDENTICAL to before when
    lang is "en" or unresolved — existing tests stay green.
  * The active language is resolved from a SINGLE source (`resolve_lang`):
    env override MGM_LANGUAGE first, then world.json > meta.langue, then "en".
  * Pure stdlib. No file is written. Any failure → "en".

To add a locale: add a `<code>` dict to TABLES mapping the SAME keys as `en`
(only translate what you need — missing keys fall back to English). Then expose
the language via world.json > meta.langue (e.g. "de") or the MGM_LANGUAGE env var.
"""

from __future__ import annotations

import os

# ════════════════════════════════════════════════════════════════════════════
#  Translation tables — keys are STABLE identifiers, values are display strings.
# ════════════════════════════════════════════════════════════════════════════
#
# English ("en") is the reference table: every key used by the engine MUST exist
# here. Other locales only need to override the strings they translate.

_EN = {
    # ── scene_brief.py — column labels + frame title + inline fragments ──
    "brief.title": "SCENE BRIEF",
    "brief.location": "LOCATION",
    "brief.around": "AROUND",
    "brief.present": "PRESENT",
    "brief.movement": "MOVEMENT",
    "brief.recent": "RECENT",
    "brief.imminent": "IMMINENT",
    "brief.stakes": "STAKES",
    "brief.unknown_location": "(unknown location)",
    "brief.crosses": "crosses",            # "<actor> crosses <place> (<when>)"
    "brief.toward_player": " (toward the player)",
    "brief.more": "(+{n} more)",           # capped-column overflow marker
    # ── transform_llm_output.py — Persisted block + pause/resume notes ──
    "persisted.header": "💾 Persisted:",
    "persisted.trace_header": "🔎 Persistence trace:",
    "pause.active": ("⏸️ *Pause active — the game is suspended. "
                     "Send ▶️ (or `!reprise`) to resume.*"),
    "pause.resumed": "▶️ *Game resumed.*",
    # ── scoreboard.py — headers + helpers ──
    "scoreboard.none": "No metrics yet (scoreboard.json missing).",
    "scoreboard.title": "📊 Scoreboard per model — campaign {name}",
    "scoreboard.col_model": "model",
    "scoreboard.col_turns": "turns",
    "scoreboard.col_clean": "clean",
    "scoreboard.col_pct_clean": "%clean",
    "scoreboard.col_banker": "banker",
    "scoreboard.col_conduct": "conduct",
    "scoreboard.col_forced": "forced",
    "scoreboard.top_rules": "    top rules: ",
    # ── _lib.etat_brief — authoritative state summary labels ──
    "etat.time_dated": "Time: day {day}, {hour}",
    "etat.time_regime": "Time: regime {regime} (estimated durations)",
    "etat.pc": "PC {name}",
    "etat.has": "  has: ",
    "etat.existing_npcs": "Existing NPCs: ",
}

# French locale — first additional locale. Only UI strings (no data values).
_FR = {
    "brief.title": "BRÈVE DE SCÈNE",
    "brief.location": "LIEU",
    "brief.around": "AUTOUR",
    "brief.present": "PRÉSENTS",
    "brief.movement": "MOUVEMENT",
    "brief.recent": "RÉCENT",
    "brief.imminent": "IMMINENT",
    "brief.stakes": "ENJEUX",
    "brief.unknown_location": "(lieu inconnu)",
    "brief.crosses": "croise",
    "brief.toward_player": " (vers le joueur)",
    "brief.more": "(+{n} autres)",
    "persisted.header": "💾 Persisté :",
    "persisted.trace_header": "🔎 Trace de persistance :",
    "pause.active": ("⏸️ *Pause active — la partie est suspendue. "
                     "Envoyez ▶️ (ou `!reprise`) pour reprendre.*"),
    "pause.resumed": "▶️ *Partie reprise.*",
    "scoreboard.none": "Aucune métrique pour l'instant (scoreboard.json absent).",
    "scoreboard.title": "📊 Tableau de bord par modèle — campagne {name}",
    "scoreboard.col_model": "modèle",
    "scoreboard.col_turns": "tours",
    "scoreboard.col_clean": "propres",
    "scoreboard.col_pct_clean": "%propres",
    "scoreboard.col_banker": "banquier",
    "scoreboard.col_conduct": "conduite",
    "scoreboard.col_forced": "forcés",
    "scoreboard.top_rules": "    top règles : ",
    "etat.time_dated": "Temps : jour {day}, {hour}",
    "etat.time_regime": "Temps : régime {regime} (durées estimées)",
    "etat.pc": "PJ {name}",
    "etat.has": "  possède : ",
    "etat.existing_npcs": "PNJ existants : ",
}

TABLES = {
    "en": _EN,
    "fr": _FR,
}

DEFAULT_LANG = "en"


def normalize_lang(lang) -> str:
    """Normalize a language tag to a known locale code, else DEFAULT_LANG.

    Accepts e.g. 'FR', 'fr-FR', 'fr_FR' → 'fr'. Unknown/empty → 'en' (fail-open).
    """
    if not lang or not isinstance(lang, str):
        return DEFAULT_LANG
    code = lang.strip().lower().replace("_", "-").split("-", 1)[0]
    return code if code in TABLES else DEFAULT_LANG


def t(key: str, lang=None, **kwargs) -> str:
    """Translate `key` into `lang` (default/fallback = English).

    Lookup order: TABLES[lang][key] → TABLES['en'][key] → `key` itself.
    `**kwargs` are applied with str.format (e.g. t('brief.more', n=3)); a
    formatting error degrades to the unformatted string (fail-open).
    """
    code = normalize_lang(lang)
    value = TABLES.get(code, {}).get(key)
    if value is None:
        value = _EN.get(key, key)
    if kwargs:
        try:
            return value.format(**kwargs)
        except Exception:
            return value
    return value


def resolve_lang(monde=None) -> str:
    """Resolve the active UI language from a single source (fail-open → 'en').

    Cascade (most specific first):
        env MGM_LANGUAGE  >  world.json > meta.langue  >  'en'.
    `monde` is the already-loaded world.json dict (engine code always has it on
    hand); we never read the file here to keep this helper dependency-free.
    """
    env = os.environ.get("MGM_LANGUAGE")
    if env:
        return normalize_lang(env)
    try:
        meta = monde.get("meta") if isinstance(monde, dict) else None
        if isinstance(meta, dict) and meta.get("langue"):
            return normalize_lang(meta.get("langue"))
    except Exception:
        pass
    return DEFAULT_LANG
