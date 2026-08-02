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
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _lib as L  # noqa: E402

MEMORY_TAG_RE = re.compile(r"^[a-z0-9-]{4,24} \|")


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
    _open_turn(camp, payload, paused)
    triggers = _section_triggers(camp, payload, monde, paused)

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
        L.section_usage_record(camp, payload, triggers)
        return {"context": "\n\n".join(parts)} if parts else {}

    parts.append(build_context(camp, monde, payload))
    if cfg.get("fiche_memoire"):
        fiche = build_memory_card(monde)  # "" below the threshold and while the format holds
        if fiche:
            parts.append(fiche)
            triggers["memory_card_active"] = True
    if cfg.get("docs_monde"):  # gated by features.temporality (see _lib.hooks_cfg)
        saison = build_season_brief(camp, monde)  # fail-open: "" if unavailable
        if saison:
            parts.append(saison)
    if cfg.get("brief_scene"):  # gated by features.temporality (see _lib.hooks_cfg)
        brief = build_scene_brief(camp, payload, monde)  # fail-open: "" if unavailable
        if brief:
            parts.append(brief)
    if cfg.get("living_npcs_factions"):  # gated by features.living_npcs_factions
        emo = build_emotions_brief(camp)  # fail-open: "" if unavailable
        if emo:
            parts.append(emo)
    L.section_usage_record(camp, payload, triggers)
    ctx = "\n\n".join(p for p in parts if p)
    return {"context": ctx} if ctx else {}


def _open_turn(camp, payload, paused):
    """Arms or clears the fast-forward grant from the player's VERBATIM message (TURN-02).

    This is the only place a grant can be created. Before it, the sole way to arm one was
    a `--declared` string the model typed itself — which it could forget, and could forge.
    FAIL-OPEN: a failure here leaves no runtime record, and `turn_state.clock_verdict`
    treats a missing record as "do not gate" rather than as "no signal".
    """
    try:
        import turn_state as T
        T.open_turn(camp, payload, L.incoming_message(payload), paused=paused)
    except Exception as exc:
        sys.stderr.write("[mj-turn] turn not opened (%s: %s): pacing is unguarded this "
                         "turn.\n" % (type(exc).__name__, exc))


def _section_triggers(camp, payload, monde, paused):
    """Cheap, shallow detection of the events tied to the 13 SKILL.md sections
    MESURE-SKILL.md §3 flagged as unmeasured. Fail-open: {} on any failure."""
    try:
        msg = L.incoming_message(payload)
        msg_l = msg.strip().lower()
        out = {
            "cmd_cloture": msg_l.startswith("!cloture"),
            "cmd_game_report": msg_l.startswith("!game-report"),
            "cmd_reprendre": msg_l.startswith("!reprendre"),
            "pause_marker": bool(paused),
            "question_mark": msg.rstrip().endswith("?"),
        }
        regime = (((monde or {}).get("meta") or {}).get("time") or {}).get("regime")
        out["regime_non_narratif"] = bool(regime) and str(regime) != "Narratif"
        noms = [str(f.get("name")) for f in L.load_pnj_list(camp)
                if isinstance(f, dict) and f.get("name")]
        hits = sum(1 for n in noms if n and n.lower() in msg.lower())
        out["npc_any_named"] = hits >= 1
        out["npc_multi_named"] = hits >= 2
        return out
    except Exception:
        return {}


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


def build_memory_card(monde):
    """Entry-format card for the agent memory tool, injected ONLY when it is needed.

    The card is silent while the stores are healthy and appears at the one moment the
    agent is about to fail: over `seuil` occupancy, or with an entry that cannot be
    edited by anchor. Which is the point — a manual written into SKILL.md is read at
    startup and forgotten by the turn it serves, and a memory entry written mid-session
    does not reach the system prompt until the NEXT session (memory_tool.py: the
    snapshot is frozen at session start).

    The format itself is what the field corpus asks for. A 640-char entry stacking 8
    rules can only be edited whole, which produced `replace` payloads of 838 chars
    median that minimax-m3 truncated into `content is required`; and 39 of 85
    `No entry matched` used a `**bold**` anchor while 13 typed the `§` Hermes uses as
    its own delimiter. Small entries with a plain-ASCII tag remove both mechanically.

    Read faults degrade to "" (a missing HERMES_HOME is not this hook's business).
    Saturation does NOT: it is a state fault, and it stayed silent for 55 days.
    """
    try:
        cfg = L.memory_cfg(monde)
        mdir = L.memory_dir()
        stores = []
        for cle, nom, _ in L.MEMORY_STORES:
            entries = L.memory_entries(Path(mdir) / nom)
            if entries is None:
                continue
            limite = cfg["%s_char_limit" % cle]
            stores.append({
                "cible": cle,
                "used": L.memory_used(entries),
                "limite": limite,
                "pct": L.memory_used(entries) / float(limite),
                "hors_norme": _memory_off_format(entries, cfg["entry_max"]),
            })
        if not stores:
            return ""
        sature = [s for s in stores if s["pct"] >= cfg["seuil"]]
        hors_norme = [h for s in stores for h in s["hors_norme"]]
        if not sature and not hors_norme:
            return ""
        return _memory_card_text(stores, hors_norme, cfg)
    except Exception:
        return ""


def _memory_off_format(entries, entry_max):
    """Entries that cannot be edited by anchor: too long, or with no leading tag."""
    out = []
    for e in entries:
        motifs = []
        if len(e) > entry_max:
            motifs.append("%d chars" % len(e))
        if not MEMORY_TAG_RE.match(e):
            motifs.append("no tag")
        if motifs:
            label = "%s (%s)" % (L.truncate(e, 34), ", ".join(motifs))
            if label not in out:
                out.append(label)
    return out


def _memory_card_text(stores, hors_norme, cfg):
    usage = " · ".join(
        "%s %d%% (%d/%d)" % (s["cible"].upper(), round(100 * s["pct"]), s["used"], s["limite"])
        for s in stores
    )
    lignes = [
        "🧠 AGENT MEMORY — %s — free space BEFORE writing." % usage,
        "MANDATORY ENTRY FORMAT:  short-tag | text of at most %d chars" % cfg["entry_max"],
        "  · short-tag = [a-z0-9-]{4,24}, unique, FIRST on the line. It is ALWAYS your old_text.",
        "  · one entry = ONE rule. Never stack several.",
        "  · NEVER type the § character (Hermes internal delimiter) nor **bold** in an anchor.",
        "CALL:  memory(action=, target=, content=, old_text=)",
        "  action ∈ add | replace | remove   (there is NO \"read\" action)",
        "  target ∈ memory | user",
        "  add → content required · replace → old_text AND content required "
        "(content, not new_text) · remove → old_text required",
        "EVICTION: above %d%%, every add is preceded by a remove. Every tool reply prints "
        "`usage` — read it." % round(100 * cfg["seuil"]),
    ]
    if hors_norme:
        lignes.append("⚠️ OFF-FORMAT, rewrite one per turn: " + " · ".join(hors_norme[:3]))
    lignes.append(
        "NOT HERE: GM conduct rules (→ references/locked-lessons.md), game data "
        "(→ campaign files). Allowed: player meta-preferences, operational state.")
    return "\n".join(lignes)


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


def build_season_brief(camp, monde):
    """G4 — calls world_docs.py `season` for the current fiction day.

    `saisons.json` is 50 048 chars the GM was expected to open on its own initiative
    before describing weather, ground or light; ~340 chars are injected instead.
    Absolute FAIL-OPEN: no saisons.json, no current day, missing script, timeout,
    unusable output → "" (the turn proceeds without the block).
    """
    try:
        suivi = (((monde.get("rules") or {}).get("time") or {}).get("tracking")) or {}
        jour = suivi.get("current_day")
        if jour in (None, ""):
            return ""
        script = _scripts_dir() / "world_docs.py"
        if not script.exists():
            return ""
        proc = subprocess.run(
            [sys.executable, str(script), "season", str(camp), str(jour)],
            capture_output=True, text=True, timeout=8,
        )
        if proc.returncode != 0:  # world_docs.py season: code 0 ALWAYS (fail-open)
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
    return Path(os.path.dirname(os.path.abspath(__file__))).parent / "scripts"


if __name__ == "__main__":
    L.run(handle)
