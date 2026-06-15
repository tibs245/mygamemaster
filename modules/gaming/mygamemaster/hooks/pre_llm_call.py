#!/usr/bin/env python3
"""
pre_llm_call — before the GM's turn:
  1. records the input prompt (for the traceability line written on output);
  2. resets the gate's anti-loop budget (new turn);
  3. RE-INJECTS the corrective feedback from the previous turn (feed-forward) — this is how
     the GM corrects itself without re-inference or looping;
  4. injects the AUTHORITATIVE STATE (offloads factual data from the model).

Output: {"context": "<feedback + state>"} or {}.
"""
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _lib as L  # noqa: E402


def handle(payload):
    camp = L.campaign_dir(payload)
    monde = L.load_monde(camp)
    cfg = L.hooks_cfg(monde)
    bypass = L.is_bypassed(payload, monde, camp)
    paused = L.pause_active(payload, monde, camp)  # explicit pause ⏸️/▶️ (≠ admin bypass)

    L.ledger_append(camp, payload, {
        "input": L.truncate(L.incoming_message(payload), 200),
        "model": L.model_name(payload),
        "ts": L.now_iso(),
        "bypass": bypass,
    })
    L.attempts_reset(camp, payload)  # new turn → gate budget reset to zero

    # Judge feed-forward: the correction from the previous turn is re-injected as long as
    # the turn is NOT explicitly paused — including on an admin turn (otherwise, in a game
    # driven by an admin, the judge detects but never corrects). Read AND cleared → a
    # single injection. The authoritative state remains reserved for non-bypass turns.
    parts = []
    if not paused:
        pending = L.take_pending(camp, payload)
        if pending:
            parts.append(pending)

    if bypass or not cfg["injection_etat"]:
        return {"context": "\n\n".join(parts)} if parts else {}

    parts.append(build_context(camp, monde, payload))
    if cfg.get("brief_scene"):  # gated by features.temporality (see _lib.hooks_cfg)
        brief = build_scene_brief(camp, payload, monde)  # fail-open: "" if unavailable
        if brief:
            parts.append(brief)
    if cfg.get("living_npcs_factions"):  # gated by features.living_npcs_factions
        emo = build_emotions_brief(camp)  # fail-open: "" if unavailable
        if emo:
            parts.append(emo)
    ctx = "\n\n".join(p for p in parts if p)
    return {"context": ctx} if ctx else {}


def build_context(camp, monde, payload=None):
    head = [
        "🧮 AUTHORITATIVE STATE — check the files before narrating "
        "(do not rely on your memory):",
        "• Verbosity: %s" % L.verbosity(monde),
    ]
    # Author + admin status (reliable): lets the GM know who is speaking and only
    # execute !feature <axe> on|off if "admin: oui". Fail-open.
    try:
        aid = L.author_id(payload) if payload is not None else None
        est_admin = bool(aid and aid in L.admins(monde))
        head.append("• Author: %s · admin: %s" % (
            aid or "unknown", "yes" if est_admin else "no"))
    except Exception:
        pass
    sess = L.active_session_number(camp)
    if sess is not None:
        head.append("• Active session: %s" % sess)
    brief = L.etat_brief(camp, monde)
    tail = ""
    if L.load_pnj_list(camp):
        tail = "\n⚠️ A named NPC missing from the list = document it, do not invent it."
    prefs = build_player_prefs(camp)  # fail-open: "" if none
    return "\n".join(head) + "\n" + brief + tail + prefs


def build_player_prefs(camp):
    """Out-of-fiction play preferences (preferences block of each sheet).

    Surfaces per-player, table-style preferences (pacing, tone, combat verbosity,
    spotlight, content boundaries, enjoys-being-deceived, custom keys) so the GM
    tailors the experience. Absolute FAIL-OPEN: no prefs / no sheets / any error
    → "" (the turn is unchanged). Private to each player; only ever surfaced to
    the GM (who already sees every sheet), never cross-shared between players.
    """
    try:
        lignes = []
        for path, fiche in L.iter_characters(camp):
            prefs = fiche.get("preferences")
            if not isinstance(prefs, dict):
                continue
            meta = fiche.get("meta") if isinstance(fiche.get("meta"), dict) else {}
            qui = meta.get("player_name") or meta.get("character_name") or path.stem
            resume = _resumer_prefs(prefs)
            if resume:
                lignes.append("  • %s : %s" % (qui, resume))
        if not lignes:
            return ""
        return ("\n🎚️ PLAYER PREFERENCES (meta — tailor the game, do not narrate them):\n"
                + "\n".join(lignes))
    except Exception:
        return ""


def _resumer_prefs(prefs):
    """One-line summary of a player's preferences block. Skips empty values."""
    morceaux = []

    def ajouter(label, valeur):
        if valeur is None or valeur == "" or valeur == [] or valeur == {}:
            return
        if isinstance(valeur, list):
            valeur = ", ".join(str(v) for v in valeur)
        elif isinstance(valeur, bool):
            valeur = "yes" if valeur else "no"
        morceaux.append("%s : %s" % (label, valeur))

    ajouter("pacing", prefs.get("pacing"))
    ajouter("tone liked", prefs.get("tone_likes"))
    ajouter("tone avoided", prefs.get("tone_dislikes"))
    ajouter("combat verbosity", prefs.get("combat_verbosity"))
    ajouter("spotlight", prefs.get("spotlight"))
    ajouter("content boundaries", prefs.get("content_boundaries"))
    ajouter("enjoys deception", prefs.get("enjoys_deception"))
    custom = prefs.get("custom")
    if isinstance(custom, dict):
        for k, v in custom.items():
            ajouter(k, v)
    return " · ".join(morceaux)


def build_scene_brief(camp, payload, monde):
    """B1 — calls scene_brief.py for the current location and returns its text.
    Absolute FAIL-OPEN: any failure (no geo.json, no location hint, missing script,
    timeout, broken JSON) → "" (the turn proceeds without the brief).
    The current location is NEVER guessed: it is read from a persisted hint/ENV, otherwise skip.
    """
    try:
        lieu_id = _scene_lieu_courant(camp, payload)
        if not lieu_id:
            return ""  # the player decides where they are — no default location is invented
        script = _scripts_dir() / "scene_brief.py"
        if not script.exists():
            return ""
        proc = subprocess.run(
            [sys.executable, str(script), str(camp), str(lieu_id)],
            capture_output=True, text=True, timeout=8,
        )
        # scene_brief.py: code 0 ALWAYS (fail-open), 2 if campaign not found.
        if proc.returncode != 0:
            return ""
        return (proc.stdout or "").strip()
    except Exception:
        return ""  # never break a turn for a branch


def build_emotions_brief(camp):
    """Compact NPC emotional summary (skill mygamemaster-emotions) — calls
    emotions.py `summary`, which prints one line per NPC carrying an
    `emotions` object (capped, no context bloat) so the GM portrays them
    consistently: show through behavior, never state feelings to players.
    Absolute FAIL-OPEN: no emotions data / missing script / timeout → ""
    (the turn proceeds without the block)."""
    try:
        script = _scripts_dir() / "emotions.py"
        if not script.exists():
            return ""
        proc = subprocess.run(
            [sys.executable, str(script), "summary", str(camp)],
            capture_output=True, text=True, timeout=8,
        )
        if proc.returncode != 0:  # emotions.py summary: code 0 ALWAYS (fail-open)
            return ""
        return (proc.stdout or "").strip()
    except Exception:
        return ""  # never break a turn for a branch


def _scene_lieu_courant(camp, payload):
    """Scene location hint: .banquier/scene-<sid>.json > 'lieu_id', otherwise ENV
    MGM_SCENE_LIEU, otherwise None. Never guesses."""
    try:
        sid = str(payload.get("session_id") or "default")
        hint = L.load_json(camp / ".banquier" / ("scene-%s.json" % sid))
        if isinstance(hint, dict) and hint.get("lieu_id"):
            return str(hint["lieu_id"])
    except Exception:
        pass
    env = os.environ.get("MGM_SCENE_LIEU", "").strip()
    return env or None


def _scripts_dir():
    """Directory of the living-world scripts (sibling of the hooks/ folder)."""
    from pathlib import Path
    return Path(os.path.dirname(os.path.abspath(__file__))).parent / "scripts"


if __name__ == "__main__":
    L.run(handle)
