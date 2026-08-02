#!/usr/bin/env python3
"""
pre_tool_call — executed before a write tool (matched in config.yaml).

1. Snapshot of the counters for the targeted file (baseline for post-write deltas).
2. PACING GATE (TURN-02): a write that pushes `rules.time.tracking.current_day` forward
   with no fast-forward signal from the player is BLOCKED — the model receives the refusal
   and must rework the turn. This is the only hook that can force a rework at all.
3. JSON integrity guard: if a `write_file` provides broken JSON content and
   `meta.hooks.garde_json_strict` is true → we BLOCK (the model receives the refusal and corrects).
   Otherwise → simple warning appended to the ledger.

Output: {} (let through) or {"action":"block","message":"<reason>"}.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _lib as L  # noqa: E402
import turn_state as T  # noqa: E402

WRITE_KEYS = ["path", "file_path", "filename", "file", "target", "name"]
CONTENT_KEYS = ["content", "text", "new_content", "data", "contents"]


def _turn_trace(camp, payload, outcome, reason, info=None):
    """Durable record first, stderr second (same trade-off as `transform_llm_output`)."""
    info = dict(info or {})
    try:
        L.turn_record(camp, payload, outcome, reason, **info)
    except Exception as exc:
        sys.stderr.write(
            "[mj-turn] JOURNAL WRITE FAILED (%s: %s): a pacing verdict could not be "
            "recorded in .banquier/turn-gate.json.\n" % (type(exc).__name__, exc))
    if outcome != "clean":
        detail = " ".join("%s=%s" % (k, info[k]) for k in sorted(info))
        sys.stderr.write("[mj-turn] %s: %s %s\n" % (outcome, reason, detail))


def enforce_pacing(camp, payload, monde, kind, path, content):
    """TURN-02 on the game clock this write is about to move. Returns a block dict or {}.

    THIS is where the doctrine's "forbidden action → rework the response AND the actions"
    becomes real. `transform_llm_output` cannot ask for a rewrite (rewrite-only, it cannot
    restart the model); `pre_tool_call` can, and an ellipse's one persistent effect — the
    integer `current_day` — is exactly the kind of unambiguous data specs/hooks-runtime.md
    §2 allows a hook to block on. A turn that cannot persist its ellipse has to rework it.

    Scope is deliberately narrow, because a false rejection is worse than the original
    defect: world.json only, full parseable JSON content only (a patch carries no clock to
    compare), day counters only (`current_hour` is free text), and only when the day moves
    FORWARD. Everything else, and every failure of ours, lets the write through.

    Never raises: this runs before every write of every campaign.
    """
    if kind != "world" or not isinstance(content, str) or not content.strip():
        return {}
    try:
        after = T.current_day(json.loads(content))
        before = T.current_day(L.load_json(path) or {})
        v = T.clock_verdict(camp, payload, monde, before, after)
    except Exception as exc:
        _turn_trace(camp, payload, "blind", "clock_gate_error",
                    {"error": "%s: %s" % (type(exc).__name__, exc)})
        return {}

    info = {k: v[k] for k in ("before", "after", "attempts") if v.get(k) is not None}
    if v["action"] == "block":
        _turn_trace(camp, payload, "blocked", v["reason"], info)
        return {"action": "block", "message": v["message"]}
    if v["reason"] == "forced":
        _turn_trace(camp, payload, "forced", v["reason"], info)
    elif v["reason"].startswith("blind"):
        _turn_trace(camp, payload, "blind", v["reason"], info)
    elif v["reason"] in ("granted", "gate_off", "paused"):
        _turn_trace(camp, payload, "allowed", v["reason"], info)
    return {}


def handle(payload):
    camp = L.campaign_dir(payload)
    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, dict):
        return {}
    raw_path = L.first_present(tool_input, WRITE_KEYS)
    if not raw_path:
        return {}
    kind, path = L.classify(raw_path, camp)
    if kind is None:
        return {}  # outside campaign scope

    # 1) Baseline before write.
    try:
        L.snap_set(camp, payload, str(path), L.file_counts(kind, path))
    except Exception:
        pass

    monde = L.load_monde(camp)
    content = L.first_present(tool_input, CONTENT_KEYS)

    # 2) Pacing gate. Suspended by an explicit ⏸️ pause only — an admin who plays gets the
    #    check, like the judge and the agency gate.
    if not L.pause_active(payload, monde, camp):
        blocked = enforce_pacing(camp, payload, monde, kind, path, content)
        if blocked:
            return blocked

    # 3) JSON guard (only if full content is provided — write_file).
    if L.is_bypassed(payload, monde, camp):
        return {}
    if isinstance(content, str) and content.strip():
        try:
            json.loads(content)
        except Exception as e:
            rel = _rel(path, camp)
            if L.hooks_cfg(monde)["garde_json_strict"]:
                L.ledger_append(camp, payload, {
                    "erreur": True, "type_erreur": "json_casse", "emoji": "🛑",
                    "phrase": "🛑 Write refused — invalid JSON: %s" % rel,
                })
                return {
                    "action": "block",
                    "message": ("Invalid JSON for %s (%s). Fix the syntax "
                                "before rewriting the file." % (rel, e)),
                }
            L.ledger_append(camp, payload, {
                "erreur": True, "type_erreur": "json_casse", "emoji": "⚠️",
                "phrase": "⚠️ Potentially invalid JSON written: %s" % rel,
            })
    return {}


def _rel(path, camp):
    try:
        return str(path.relative_to(camp.resolve()))
    except Exception:
        return path.name


if __name__ == "__main__":
    L.run(handle)
