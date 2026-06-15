#!/usr/bin/env python3
"""
pre_tool_call — executed before a write tool (matched in config.yaml).

1. Snapshot of the counters for the targeted file (baseline for post-write deltas).
2. JSON integrity guard: if a `write_file` provides broken JSON content and
   `meta.hooks.garde_json_strict` is true → we BLOCK (the model receives the refusal and corrects).
   Otherwise → simple warning appended to the ledger.

Output: {} (let through) or {"action":"block","message":"<reason>"}.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _lib as L  # noqa: E402

WRITE_KEYS = ["path", "file_path", "filename", "file", "target", "name"]
CONTENT_KEYS = ["content", "text", "new_content", "data", "contents"]


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

    # 2) JSON guard (only if full content is provided — write_file).
    monde = L.load_monde(camp)
    if L.is_bypassed(payload, monde, camp):
        return {}
    content = L.first_present(tool_input, CONTENT_KEYS)
    if isinstance(content, str) and content.strip():
        try:
            json.loads(content)
        except Exception as e:
            rel = _rel(path, camp)
            if L.hooks_cfg(monde)["garde_json_strict"]:
                L.ledger_append(camp, payload, {
                    "erreur": True, "type_erreur": "json_casse", "emoji": "🛑",
                    "phrase": "🛑 Écriture refusée — JSON invalide : %s" % rel,
                })
                return {
                    "action": "block",
                    "message": ("Invalid JSON for %s (%s). Fix the syntax "
                                "before rewriting the file." % (rel, e)),
                }
            L.ledger_append(camp, payload, {
                "erreur": True, "type_erreur": "json_casse", "emoji": "⚠️",
                "phrase": "⚠️ JSON potentiellement invalide écrit : %s" % rel,
            })
    return {}


def _rel(path, camp):
    try:
        return str(path.relative_to(camp.resolve()))
    except Exception:
        return path.name


if __name__ == "__main__":
    L.run(handle)
