#!/usr/bin/env python3
"""
transform_llm_output — after the tool loop, before delivery to the player.

1. Reads (and CLEARS) the turn ledger → factual Steward report "Persisted".
1b. DETERMINISTIC AGENCY GATE (AGENCY-01/02/03) on the text about to be delivered —
   unconditional, local, no model, and the only place these rules are actually enforced.
2. Launches the LLM JUDGE (opt-in): steward domain (lenient) + conduct (strict).
   → stores a corrective feedback re-injected on the next turn (feed-forward);
   → updates the scoreboard per model;
   → exposes NOTHING to the player (technical transparency) except in DEBUG/TRACE.
3. Writes the collecte.csv line (always).
4. Augments the response with the "Persisted" block according to verbosity.
5. Automatic narrative voice (opt-in): decides, records the decision durably in
   .banquier/tts-status.json — configured skip vs failure — and attaches MEDIA:.

INVARIANT: {"response": …} is only emitted if the original text was retrieved.
"""
import os
import re
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _lib as L  # noqa: E402
import agency_gate as A  # noqa: E402
import llm_judge as J  # noqa: E402
import turn_state as T  # noqa: E402

# Player channel: strip what the model (M3) sometimes regurgitates — code blocks
# it executes and tracebacks. Game templates (dice rolls, sheets) use box-drawing
# and emojis, never ``` fences → they are not affected.
_FENCE_RE = re.compile(r"```.*?```|~~~.*?~~~", re.S)
_TRACEBACK_RE = re.compile(
    r"(?ms)^Traceback \(most recent call last\):\n(?:.*\n)*?^[\w.]*(?:Error|Exception|Warning)\b.*$")
# One-shot exception: the user explicitly asks to see behind the scenes.
# Matches EN ("MJ, show/tell/give me…") and FR ("MJ, montre/dis/affiche/donne…").
_SHOW_RE = re.compile(
    r"\bmj\b[\s,]*(montre|dis|affiche|donne|show|tell|give|reveal|display)", re.I)


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


def _agency_trace(camp, payload, outcome, reason, info=None):
    """Durable record first, stderr second — stderr is the channel proven useless.

    A failed journal write is announced and swallowed, never propagated: losing a log line
    must not cost the player his turn (same trade-off, same reasoning as `_tts_trace`)."""
    info = dict(info or {})
    try:
        L.agency_record(camp, payload, outcome, reason, **info)
    except Exception as exc:
        sys.stderr.write(
            "[mj-agency] JOURNAL WRITE FAILED (%s: %s): the agency verdict could not be recorded "
            "in .banquier/agency-gate.json — a cut made here leaves no trace.\n"
            % (type(exc).__name__, exc))
    if outcome != "clean":
        detail = " ".join("%s=%s" % (k, info[k]) for k in sorted(info))
        sys.stderr.write("[mj-agency] %s: %s %s\n" % (outcome, reason, detail))


def enforce_agency(camp, payload, original, paused, lg):
    """AGENCY-01/02/03 on the text about to be DELIVERED. Returns (text, violations).

    THIS is the unconditional path. `mj_checkpoint.py` owns the same verdict but only runs
    when the model decides to run it, and the field report counted eight agency violations
    in one hour under exactly that arrangement — an instruction in a prompt does not execute.
    Here nothing is asked of the model.

    Downstream of inference there is no "rewrite and come back", so the remedy is a CUT
    (`agency_gate.redact`). Anti-loop is structural rather than budgeted: one hook pass per
    turn, no re-inference requested, and the redact/re-check rounds are bounded by
    `A.max_attempts()`. It deliberately does NOT touch `agency_attempts` or
    `checkpoint_attempts` — those are the checkpoint's and the judge's own budgets, and
    consuming another gate's budget is how a gate silently disarms its neighbour.

    Detected violation vs infrastructure failure, never confused:
      * a VIOLATION is always cut — that outcome does not depend on config or network;
      * a CRASH of the analyser is a defect of ours, not a verdict on the turn: the text
        ships unchanged and the turn is journalled `blind`, because breaking every session
        of every campaign is not a proportionate answer to our own bug.

    Never raises: the caller is on the delivery path of every turn of every game.
    """
    if original is None:
        return original, []
    if paused:
        _agency_trace(camp, payload, "skipped", "paused")
        return original, []
    if not A.enabled():
        _agency_trace(camp, payload, "skipped", "gate_off")
        return original, []

    names = L.pc_names(camp)
    declared = L.incoming_message(payload)
    text, violations, rounds = original, [], 0
    try:
        report = A.analyze(text, declared, names)
        while not report["ok"] and rounds < A.max_attempts():
            violations = violations or report["violations"]
            text, _cut = A.redact(text, report)
            rounds += 1
            if not text.strip():
                break
            report = A.analyze(text, declared, names)
        if not report["ok"] or not text.strip():
            # Budget spent and still refused: the offending text is never the one delivered.
            text = ""
    except Exception as exc:
        _agency_trace(camp, payload, "blind", "gate_error",
                      {"error": "%s: %s" % (type(exc).__name__, exc), "chars": len(original)})
        return original, []

    if not violations:
        _agency_trace(camp, payload, "clean", "ok")
        return original, []

    reason = "redacted"
    if not text.strip():
        text, reason = L.t("agency.emptied", lg), "emptied"
    _agency_trace(camp, payload, "enforced", reason,
                  {"rules": ",".join(sorted({v["regle"] for v in violations})),
                   "rounds": rounds, "chars_before": len(original), "chars_after": len(text)})
    return text, violations


def _turn_trace(camp, payload, outcome, reason, info=None):
    info = dict(info or {})
    try:
        L.turn_record(camp, payload, outcome, reason, **info)
    except Exception as exc:
        sys.stderr.write(
            "[mj-turn] JOURNAL WRITE FAILED (%s: %s): the pacing verdict could not be "
            "recorded in .banquier/turn-gate.json.\n" % (type(exc).__name__, exc))
    if outcome != "clean":
        detail = " ".join("%s=%s" % (k, info[k]) for k in sorted(info))
        sys.stderr.write("[mj-turn] %s: %s %s\n" % (outcome, reason, detail))


def enforce_turn(camp, payload, original, paused, monde):
    """TURN-01/02/06 on the text about to be DELIVERED. Returns the violations found.

    LAST-RESORT NET, and explicitly not the enforcing mechanism: the enforcing one is the
    refusal `pre_tool_call` returns when the turn tries to persist its ellipse, because
    that one makes the model rework. Here nothing can be reworked and, unlike the agency
    gate on this same hook, nothing is CUT either — deleting "Trois heures plus tard"
    leaves the sentences after it stranded in a moment that no longer exists, and a turn
    the player cannot follow is worse than a turn that broke the pacing rule.

    So the remedy is the correction fed forward, plus a durable trace. It merges into the
    caller's existing `violations` list, inheriting `set_pending`, the scoreboard and the
    CSV line without a second, divergent pipeline.

    Violation vs infrastructure, kept apart as in `enforce_agency`: a detected violation is
    always fed forward and journalled; a crash of ours ships the turn and is journalled
    `blind`. Never raises.
    """
    if original is None:
        return []
    if paused:
        _turn_trace(camp, payload, "allowed", "paused")
        return []
    try:
        v = T.check_delivered(camp, payload, original, monde)
    except Exception as exc:
        _turn_trace(camp, payload, "blind", "gate_error",
                    {"error": "%s: %s" % (type(exc).__name__, exc)})
        return []
    if "_skipped" in v:
        _turn_trace(camp, payload, "allowed", v["_skipped"])
        return []
    if not v["violations"]:
        _turn_trace(camp, payload, "clean", "ok", {"granted": v["granted"]})
        return []
    _turn_trace(camp, payload, "flagged", "delivered",
                {"rules": ",".join(sorted({x["regle"] for x in v["violations"]})),
                 "granted": v["granted"], "moments": len(v["moments"])})
    return v["violations"]


def handle(payload):
    camp = L.campaign_dir(payload)
    monde = L.load_monde(camp)
    lg = L.lang(monde)                              # active UI language (fail-open → 'en')
    cfg = L.hooks_cfg(monde)
    bypass = L.is_bypassed(payload, monde, camp)   # pause OR admin → scrub / block / CSV
    paused = L.pause_active(payload, monde, camp)   # pause ONLY → judge gate (decoupled from admin)
    lvl = L.verbosity(monde)

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

    # Runs BEFORE the judge, the CSV, the !raconte snapshot and the auto-voice, so that none
    # of them records or speaks a sentence the player will not receive.
    guarded, agency_viols = enforce_agency(camp, payload, original, paused, lg)
    if guarded != original:
        original, forced_rewrite = guarded, True
    turn_viols = enforce_turn(camp, payload, original, paused, monde)

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

    # Merged so the agency verdict inherits the whole existing pipeline — feed-forward,
    # scoreboard, CSV — instead of a second, divergent one.
    violations = agency_viols + turn_viols + violations

    banquier_viols = [v for v in violations if v.get("domaine") == "banquier"]
    conduite_viols = [v for v in violations if v.get("domaine") == "conduite"]
    banquier_n = len(banquier_viols) + len(errors)   # judge + JSON integrity
    conduite_n = len(conduite_viols)
    clean = (banquier_n == 0 and conduite_n == 0)

    # Feed-forward: store the corrective feedback for the NEXT turn.
    if violations:
        L.set_pending(camp, payload, J.format_feedback(violations))

    # Scoreboard per model (only if the judge actually ran, or for integrity).
    if judged or errors or agency_viols or turn_viols:
        L.scoreboard_update(camp, model, clean and judged, banquier_n, conduite_n,
                            [v.get("regle", "?") for v in violations])

    # CSV traceability (always, even on bypass).
    _write_csv(camp, monde, payload, input_entry, original, persisted, errors, violations, bypass)

    # ── Narration snapshot for the !raconte command (always) ──
    # The mygamemaster-tts skill reads this snapshot to voice the LAST narration on demand.
    if original is not None:
        try:
            L.snap_set(camp, payload, "last_narration", original)
        except Exception:
            pass

    # ── AUTO narrative voice: fail-open on the PLAYER channel only (cf. _tts_trace) ──
    media_line = ""
    if original is not None:
        outcome, reason, info = _tts_gate(payload, original, cfg, paused)
        if outcome is None:
            outcome, reason, info = _voice_narration(camp, payload, original)
            if outcome == "ok":
                media_line = "MEDIA:" + info["audio"]
        _tts_trace(camp, payload, outcome, reason, original, info)

    # ── Response augmentation (Steward "Persisted" block) ──
    block = ""
    if not bypass and cfg["banquier_persiste"] and original is not None:
        block = render_block(lvl, persisted, errors, lg)
        # Judge feedback is NOT shown to the player (transparency) — except in debug.
        if violations and lvl in ("DEBUG", "TRACE"):
            note = J.format_feedback(violations, prefix="🔧 Judge (internal)")
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


SKIP = "skipped"    # configured silence — normal operation
FAIL = "failed"     # defect — the feature was asked to speak and could not
RENDERER = os.path.normpath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "..", "..", "mygamemaster-tts", "scripts", "tts_render.py"))


def _tts_min_chars():
    """Soft threshold: no voice on short/mechanical turns. Override via env."""
    try:
        return max(0, int(os.environ.get("MGM_TTS_MIN_CHARS", "280")))
    except ValueError:
        return 280


def _tts_timeout():
    """WALL-CLOCK budget for the whole generation in the hook, in seconds.

    Stays well under the runtime's own hook timeout (45 s, see
    ansible/templates/config.yaml.j2): overrunning it kills the whole hook, which
    costs the CSV line and the Steward block, not merely the audio.

    This value alone is what bounds the child, via subprocess.run(timeout=…). The
    `--timeout` we also pass to tts_render.py is a PER-CALL budget and segmented
    synthesis (MGM_TTS_SEGMENT, ON by default) applies it once per segment, so N
    segments can and will exceed it — the kill here is the real deadline, and it
    is recorded as `failed:timeout`."""
    try:
        return max(5, int(os.environ.get("MGM_TTS_TIMEOUT", "40")))
    except ValueError:
        return 40


def _tts_gate(payload, original, cfg, paused):
    """Decide whether the automatic voice runs. (None, None, {}) = run.

    Otherwise returns (SKIP|FAIL, reason, info). SKIP is a configured silence and
    means nothing is broken; FAIL means the campaign asked for a voice and the
    runtime cannot deliver one. Reasons are stable identifiers, meant to be
    counted in .banquier/tts-status.json and read back by tts_doctor.py.

    Deliberately NO guard on admin bypass: a narration deserves a voice for what
    it is, not for who prompted it — otherwise the GM-admin who tests never hears
    the auto-voice and concludes it is broken."""
    msg = L.incoming_message(payload)
    if paused or L.PAUSE in msg or L.PAUSE_CMD in msg.lower():
        return SKIP, "paused", {}
    if not cfg.get("features", {}).get("tts", True):
        return SKIP, "axis_tts_off", {}
    if not cfg.get("tts_auto"):
        return SKIP, "tts_auto_off", {}
    if not os.environ.get("MINIMAX_API_KEY"):
        # A hook subprocess does not inherit the interactive shell that the owner
        # tests from: the key can be present for him and absent here.
        return FAIL, "key_missing", {}
    if len(original) < _tts_min_chars():
        return SKIP, "too_short", {"min_chars": _tts_min_chars()}
    return None, None, {}


def _voice_narration(camp, payload, narration):
    """Run the mygamemaster-tts renderer. Returns (outcome, reason, info).

    Never raises. Every failure is NAMED and carries the child's return code and
    stderr in `info` — the historical bug was to pipe that stderr and never read
    it, while telling the operator to go and look at it."""
    # Every early return reuses this dict: a failure event missing `timeout_s`
    # reads as a different schema in the journal.
    info = {"timeout_s": _tts_timeout()}
    if not os.path.isfile(RENDERER):
        info["renderer"] = RENDERER
        return FAIL, "renderer_missing", info
    out_dir = os.path.join(str(camp), ".banquier", "tts")
    sess = L.active_session_number(camp) or 0
    out = os.path.join(out_dir, "auto_s%s_%d.mp3" % (sess, int(time.time())))
    try:
        os.makedirs(out_dir, exist_ok=True)
    except OSError as e:
        info["error"] = str(e)
        return FAIL, "workspace_unwritable", info
    env = dict(os.environ)
    env["MGM_TTS_PRODUCER"] = "hook-auto"
    try:
        r = subprocess.run(
            [sys.executable, RENDERER, "--out", out, "--json",
             "--producer", "hook-auto", "--campaign-dir", str(camp),
             "--timeout", str(max(5, info["timeout_s"] - 5)), "--retries", "1"],
            input=narration.encode("utf-8"), env=env,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=info["timeout_s"])
    except subprocess.TimeoutExpired:
        return FAIL, "timeout", info
    except Exception as e:
        info["error"] = "%s: %s" % (type(e).__name__, e)
        return FAIL, "spawn_error", info
    info["rc"] = r.returncode
    info["stderr"] = L.truncate((r.stderr or b"").decode("utf-8", "replace"), 300, keep="tail")
    if r.returncode != 0:
        return FAIL, "exit_%d" % r.returncode, info
    if not (os.path.isfile(out) and os.path.getsize(out) > 0):
        return FAIL, "no_audio_file", info
    info["audio"] = out
    info["bytes"] = os.path.getsize(out)
    return "ok", "ok", info


def _tts_trace(camp, payload, outcome, reason, narration, info):
    """Record the auto-voice outcome durably, then echo it on stderr.

    Order matters: the durable record comes first, because stderr is the channel
    that was proven useless (34 sessions, not one `[mj-tts]` line ever surfaced).

    A journal write that FAILS is announced, never swallowed: an empty
    .banquier/tts-status.json is read by tts_doctor.py as "the hook never ran on
    this campaign", so a silent loss here would answer a live defect with a clean
    bill of health. The exception is caught rather than propagated for one reason
    only — a lost log line must not cost the player his turn — and the doctor
    cross-checks by testing `.banquier` for writability instead of trusting the
    absence of records."""
    info = dict(info or {})
    info["chars"] = len(narration)
    info["key"] = bool(os.environ.get("MINIMAX_API_KEY"))
    try:
        L.tts_record(camp, payload, outcome, reason, **info)
    except Exception as e:
        sys.stderr.write(
            "[mj-tts] JOURNAL WRITE FAILED (%s: %s): the auto-voice outcome could not be "
            "recorded in .banquier/tts-status.json — the journal is NOT a record of what "
            "happened here. Run tts_doctor.py.\n" % (type(e).__name__, e))
    detail = " ".join("%s=%s" % (k, info[k]) for k in
                      ("rc", "stderr", "chars", "min_chars", "timeout_s", "audio")
                      if k in info)
    label = {"ok": "attached", SKIP: "skipped (configured)"}.get(outcome, "FAILED")
    sys.stderr.write("[mj-tts] auto-voice %s: %s %s\n" % (label, reason, detail))


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
        cons += (" | " if cons else "") + "violations: " + ", ".join(
            "%s/%s" % (v.get("domaine", "?"), v.get("regle", "?")) for v in violations)
    if not cons:
        cons = "error" if has_error else "nothing persisted"
    type_err = ""
    if errors:
        type_err = errors[0].get("type_erreur", "")
    elif violations:
        type_err = "%s:%s" % (violations[0].get("domaine", "?"), violations[0].get("regle", "?"))
    row = {
        "timestamp": L.now_iso(),
        "session": L.active_session_number(camp) or "",
        "verbosity": L.verbosity(monde),
        "origine_type": "GM",
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
