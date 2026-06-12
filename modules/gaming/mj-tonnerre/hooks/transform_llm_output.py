#!/usr/bin/env python3
"""
transform_llm_output — after the tool loop, before delivery to the player.

1. Reads (and CLEARS) the turn ledger → factual Steward report "Persisted".
2. Launches the LLM JUDGE (opt-in): steward domain (lenient) + conduct (strict).
   → stores a corrective feedback re-injected on the next turn (feed-forward);
   → updates the scoreboard per model;
   → exposes NOTHING to the player (technical transparency) except in DEBUG/TRACE.
3. Writes the collecte.csv line (always).
4. Augments the response with the "Persisted" block according to verbosity.

INVARIANT: {"response": …} is only emitted if the original text was retrieved.
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _lib as L  # noqa: E402
import llm_judge as J  # noqa: E402

# Player channel: strip what the model (M3) sometimes regurgitates — code blocks
# it executes and tracebacks. Game templates (dice rolls, sheets) use box-drawing
# and emojis, never ``` fences → they are not affected.
_FENCE_RE = re.compile(r"```.*?```|~~~.*?~~~", re.S)
_TRACEBACK_RE = re.compile(
    r"(?ms)^Traceback \(most recent call last\):\n(?:.*\n)*?^[\w.]*(?:Error|Exception|Warning)\b.*$")
# One-shot exception: the user explicitly asks to see behind the scenes.
_SHOW_RE = re.compile(r"\bmj\b[\s,]*(montre|dis|affiche|donne)", re.I)


def _scrub_player_channel(text):
    """Remove content outside the player channel. Returns (text, modified?)."""
    if not text:
        return text, False
    cleaned = _TRACEBACK_RE.sub("", _FENCE_RE.sub("", text))
    if cleaned == text:
        return text, False
    return re.sub(r"\n{3,}", "\n\n", cleaned).strip(), True


def _player_asked_internals(payload):
    return bool(_SHOW_RE.search(L.incoming_message(payload)))


def handle(payload):
    camp = L.campaign_dir(payload)
    monde = L.load_monde(camp)
    lg = L.lang(monde)                              # active UI language (fail-open → 'en')
    cfg = L.hooks_cfg(monde)
    bypass = L.is_bypassed(payload, monde, camp)   # pause OR admin → scrub / block / CSV
    paused = L.pause_active(payload, monde, camp)   # pause ONLY → judge gate (decoupled from admin)
    lvl = L.verbosite(monde)

    entries = L.ledger_read_clear(camp, payload)
    input_entry = next((e for e in entries if isinstance(e, dict) and "input" in e), {})
    persisted = [e for e in entries
                 if isinstance(e, dict) and e.get("phrase") and "input" not in e and not e.get("erreur")]
    errors = [e for e in entries if isinstance(e, dict) and e.get("erreur")]

    original = L.response_text(payload)
    forced_rewrite = False
    if original is not None and not bypass and not _player_asked_internals(payload):
        original, forced_rewrite = _scrub_player_channel(original)
        if forced_rewrite and not original:
            original = "*(The narrative resumes in a moment.)*"
    model = input_entry.get("model") or L.model_name(payload)

    # ── LLM Judge (opt-in, suspended only by an explicit pause ⏸️/▶️ — NOT by
    #    admin bypass: an admin who plays deserves the check, cf. auto-voice) ──
    violations = []
    judged = False
    jcfg = L.judge_config(monde)
    if (jcfg["actif"] and not paused and original is not None
            and len(original) >= jcfg["min_chars"] and _judge_sample(camp, payload, jcfg["echantillon"])):
        verdict = J.judge(original, input_entry.get("input", ""),
                          L.etat_brief(camp, monde, for_judge=True), jcfg)
        violations = verdict.get("violations", [])
        judged = "_skipped" not in verdict

    banquier_viols = [v for v in violations if v.get("domaine") == "banquier"]
    conduite_viols = [v for v in violations if v.get("domaine") == "conduite"]
    banquier_n = len(banquier_viols) + len(errors)   # judge + JSON integrity
    conduite_n = len(conduite_viols)
    clean = (banquier_n == 0 and conduite_n == 0)

    # Feed-forward: store the corrective feedback for the NEXT turn.
    if violations:
        L.set_pending(camp, payload, J.format_feedback(violations))

    # Scoreboard per model (only if the judge actually ran, or for integrity).
    if judged or errors:
        L.scoreboard_update(camp, model, clean and judged, banquier_n, conduite_n,
                            [v.get("regle", "?") for v in violations])

    # CSV traceability (always, even on bypass).
    _write_csv(camp, monde, payload, input_entry, original, persisted, errors, violations, bypass)

    # ── Narration snapshot for the !raconte command (always) ──
    # The mj-tonnerre-tts skill reads this snapshot to voice the LAST narration on demand.
    if original is not None:
        try:
            L.snap_set(camp, payload, "last_narration", original)
        except Exception:
            pass

    # ── AUTO narrative voice (best-effort, never blocking) ──
    # Conditions: `tts` axis ON (→ tts_auto) + Minimax key + narration long enough, and
    # turn NOT paused (⏸). NB: NOT coupled to admin bypass — a narration
    # deserves voice based on ITS content, not who prompted; otherwise the GM-admin who
    # plays/tests never hears the auto-voice (cause of "it doesn't activate"). Any
    # failure = unchanged response (fail-open): audio simply not attached.
    media_line = ""
    skip = _tts_auto_skip_reason(payload, original, cfg)
    if skip is None and paused:
        # The ⏸️ marker is no longer in the message during a PERSISTENT pause:
        # auto-voice is still cut as long as pause mode is not lifted.
        skip = "turn paused (persistent mode)"
    if skip is None:
        media_line = _voice_narration(camp, payload, original)
        if not media_line:
            skip = "generation failed (fail-open, see stderr of tts_render)"
    if skip:
        # Diagnostic: the auto path is silent by design; this trace (runtime logs)
        # makes failures visible without ever polluting the player's message.
        sys.stderr.write("[mj-tts] auto-voice not attached: %s\n" % skip)

    # ── Response augmentation (Steward "Persisted" block) ──
    block = ""
    if not bypass and cfg["banquier_persiste"] and original is not None:
        block = render_block(lvl, persisted, errors, lg)
        # Judge feedback is NOT shown to the player (transparency) — except in debug.
        if violations and lvl in ("DEBUG", "TRACE"):
            note = J.format_feedback(violations, prefix="🔧 Juge (interne)")
            block = (block + "\n\n" + note) if block else note

    # ── VISIBLE pause reminder (anti-forgotten-bypass) ──
    # As long as an explicit pause is active (one-shot ⏸️ or persistent mode not lifted),
    # it is repeated each turn: the game stays suspended until an explicit ▶️/!reprise.
    # On the turn carrying ▶️/!reprise, the resumption is confirmed. (Not on a simple
    # admin bypass without pause — `paused` excludes that case.)
    msg = L.incoming_message(payload)
    just_resumed = (L.RESUME in msg or L.RESUME_CMD in msg.lower())
    pause_note = ""
    if original is not None:
        if paused:
            pause_note = L.t("pause.active", lg)
        elif just_resumed:
            pause_note = L.t("pause.resumed", lg)

    # INVARIANT: {"response": …} is only emitted if the original was retrieved.
    if original is None:
        return {}
    suffix = ("\n\n" + block if block else "") + ("\n" + media_line if media_line else "")
    if pause_note:
        suffix += "\n\n" + pause_note
    if not suffix and not forced_rewrite:
        return {}
    return {"response": original.rstrip() + suffix}


def _tts_min_chars():
    """Soft threshold: no voice on short/mechanical turns. Override via env."""
    try:
        return max(0, int(os.environ.get("MJ_TTS_MIN_CHARS", "280")))
    except ValueError:
        return 280


def _tts_auto_skip_reason(payload, original, cfg):
    """Why auto-voice does NOT trigger (None = it triggers). Diagnostic.
    Deliberately NO guard on admin bypass: only the pause marker (⏸) cuts it."""
    if original is None:
        return "no response text"
    msg = L.incoming_message(payload)
    if L.PAUSE in msg or L.PAUSE_CMD in msg.lower():
        return "turn paused (⏸ / !pause)"
    if not cfg.get("tts_auto"):
        return "tts axis / tts_auto OFF"
    if not os.environ.get("MINIMAX_API_KEY"):
        return "MINIMAX_API_KEY missing from hook env"
    if len(original) < _tts_min_chars():
        return "narration too short (%d < %d chars)" % (len(original), _tts_min_chars())
    return None


def _voice_narration(camp, payload, narration):
    """Generate the narration voice via the mj-tonnerre-tts module.
    Returns a 'MEDIA:<path>' line to attach, or '' (total fail-open)."""
    import subprocess
    import time
    try:
        script = os.path.normpath(os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "..", "..", "mj-tonnerre-tts", "scripts", "tts_render.py"))
        if not os.path.isfile(script):
            return ""
        out_dir = os.path.join(camp, ".banquier", "tts")
        os.makedirs(out_dir, exist_ok=True)
        sess = L.active_session_number(camp) or 0
        out = os.path.join(out_dir, "s%s_%d.mp3" % (sess, int(time.time())))
        try:
            timeout = max(5, int(os.environ.get("MJ_TTS_TIMEOUT", "40")))
        except ValueError:
            timeout = 40
        r = subprocess.run(
            [sys.executable, script, "--out", out, "--json"],
            input=narration.encode("utf-8"),
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout)
        if r.returncode == 0 and os.path.isfile(out) and os.path.getsize(out) > 0:
            return "MEDIA:" + out
    except Exception:
        pass
    return ""


def _judge_sample(camp, payload, n):
    if n <= 1:
        return True
    c = int(L.snap_get(camp, payload, "judge_n") or 0) + 1
    L.snap_set(camp, payload, "judge_n", c)
    return c % n == 0


def render_block(lvl, persisted, errors, lang=None):
    err_lines = [e.get("phrase") for e in errors if e.get("phrase")]
    # The "Persisted" block is INTERNAL by default (player channel consistency, R4):
    # only DEBUG/TRACE expose deltas in the thread. At other levels, only
    # errors surface. Deltas remain tracked in collecte.csv at all levels.
    if lvl not in ("DEBUG", "TRACE"):
        return "\n".join(err_lines) if err_lines else ""
    body = ["%s %s" % (e.get("emoji", "•"), e.get("phrase")) for e in persisted]
    body.extend(err_lines)
    if not body:
        return ""
    header = (L.t("persisted.trace_header", lang) if lvl == "TRACE"
              else L.t("persisted.header", lang))
    return header + "\n" + "\n".join(body)


def _write_csv(camp, monde, payload, input_entry, original, persisted, errors, violations, bypass):
    has_error = bool(errors) or bool(violations)
    cons = "; ".join(e.get("phrase", "") for e in persisted)
    if violations:
        cons += (" | " if cons else "") + "infractions: " + ", ".join(
            "%s/%s" % (v.get("domaine", "?"), v.get("regle", "?")) for v in violations)
    if not cons:
        cons = "erreur" if has_error else "rien persisté"
    type_err = ""
    if errors:
        type_err = errors[0].get("type_erreur", "")
    elif violations:
        type_err = "%s:%s" % (violations[0].get("domaine", "?"), violations[0].get("regle", "?"))
    row = {
        "timestamp": L.now_iso(),
        "session": L.active_session_number(camp) or "",
        "verbosite": L.verbosite(monde),
        "origine_type": "MJ",
        "origine_detail": "bypass" if bypass else "MJ Tonnerre",
        "action_type": "transaction" if persisted else "dialogue",
        "prompt_resume": input_entry.get("input", ""),
        "sortie": L.truncate(original, 500) if original is not None else "",
        "consequence": L.truncate(cons, 500),
        "erreur": "true" if has_error else "false",
        "type_erreur": type_err,
        "correction_immediate": "",
        "exactitude": "",
        "completude": "",
        "conteste": "",
        "modele": input_entry.get("model") or L.model_name(payload),
        "notes": "",
    }
    L.csv_append(camp, monde, payload, row, has_error=has_error)


if __name__ == "__main__":
    L.run(handle)
