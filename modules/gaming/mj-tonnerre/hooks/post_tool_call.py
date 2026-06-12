#!/usr/bin/env python3
"""
post_tool_call — executed after a write tool (matcher in config.yaml).

Reloads the written file, computes REAL DELTAS vs the baseline set by
pre_tool_call, and stacks "persisted" entries into the turn ledger.
This is what makes the Steward report factual (what actually changed).

Output: {} (effect = ledger write).
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _lib as L  # noqa: E402

WRITE_KEYS = ["path", "file_path", "filename", "file", "target", "name"]


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
        return {}

    rel = _rel(path, camp)
    before = L.snap_get(camp, payload, str(path)) or {}
    after = L.file_counts(kind, path)

    # Broken JSON after write (patch/edit case not guarded upstream).
    json_casse = path.exists() and L.load_json(path) is None
    if json_casse:
        L.ledger_append(camp, payload, {
            "erreur": True, "type_erreur": "json_casse", "emoji": "⚠️",
            "phrase": "⚠️ JSON broken after write: %s" % rel,
        })

    deltas = compute_deltas(kind, before, after, rel)
    for entry in deltas:
        L.ledger_append(camp, payload, entry)

    # New baseline (multiple writes can chain within the same turn).
    L.snap_set(camp, payload, str(path), after)

    # Versioned auto-commit (meta.hooks.auto_commit, default on). NEVER on a
    # broken JSON: we do not freeze an incoherent state. Fail-open (git_autocommit
    # never raises).
    if not json_casse:
        monde = L.load_monde(camp)
        if L.hooks_cfg(monde).get("auto_commit"):
            statut = L.git_autocommit(camp, _commit_message(camp, payload, deltas, rel))
            # Observability: auto-commit is fail-open and silent by design.
            # This trace (runtime/journald logs, NEVER the player) makes failures
            # visible — the cause of a "0 commit" would otherwise be undetectable.
            # 'nothing' (nothing to commit) is normal → silent.
            if statut != "nothing":
                sys.stderr.write("[mj-git] auto-commit %s: %s\n" % (statut, rel))
    return {}


def _commit_message(camp, payload, deltas, rel):
    """Commit message derived from the real deltas of the turn (factual)."""
    n = L.active_session_number(camp)
    head = "🔄 auto" + ((" [S%d]" % n) if n else "")
    parts = [e.get("phrase", "") for e in (deltas or []) if e.get("phrase")]
    body = " ; ".join(p for p in parts if p) or ("%s modified" % rel)
    return "%s : %s" % (head, body)


def compute_deltas(kind, b, a, rel):
    out = []

    def d(emoji, phrase, k=None):
        out.append({"emoji": emoji, "phrase": phrase, "kind": k or kind, "file": rel})

    if kind == "session":
        da = (a.get("actions") or 0) - (b.get("actions") or 0)
        if da > 0:
            d("📝", "%s +%d action(s)" % (rel, da))
        if a.get("cloturee") and not b.get("cloturee"):
            d("🏁", "Session closed (%s)" % rel)

    elif kind == "personnage":
        nom = a.get("nom") or b.get("nom") or "PJ"
        if "inventaire" in a and "inventaire" in b and a["inventaire"] != b["inventaire"]:
            d("🎒", "Inventory of %s: %s → %s item(s)" % (nom, b["inventaire"], a["inventaire"]), "inventaire")
        elif "inventaire" in a and "inventaire" not in b:
            d("🎒", "Inventory of %s modified (%s item(s))" % (nom, a["inventaire"]), "inventaire")
        if "pv" in a and "pv" in b and a["pv"] != b["pv"]:
            d("❤️", "%s — PV : %s → %s" % (nom, b["pv"], a["pv"]), "sante")
        if "equipement" in a and "equipement" in b and a["equipement"] != b["equipement"]:
            d("⚔️", "Equipment of %s: %s → %s" % (nom, b["equipement"], a["equipement"]), "inventaire")

    elif kind == "pnj":
        df = (a.get("faits_total") or 0) - (b.get("faits_total") or 0)
        if df > 0:
            d("💬", "+%d knowledge(s) propagated to NPCs" % df, "connaissance")
        elif df < 0:
            d("💬", "%d knowledge(s) removed" % (-df), "connaissance")

    elif kind == "monde":
        if a.get("jour") is not None and a.get("jour") != b.get("jour"):
            d("🕒", "Day: %s → %s" % (b.get("jour"), a.get("jour")), "temps")
        if a.get("heure") is not None and a.get("heure") != b.get("heure"):
            d("🕒", "Time: %s → %s" % (b.get("heure"), a.get("heure")), "temps")

    # Fallback: change detected but untyped → generic mention.
    if not out and a != b:
        emoji = {"session": "📝", "personnage": "🎒", "pnj": "💬",
                 "monde": "🕒", "evenements": "📜"}.get(kind, "💾")
        d(emoji, "%s modified" % rel)
    return out


def _rel(path, camp):
    try:
        return str(path.relative_to(camp.resolve()))
    except Exception:
        return path.name


if __name__ == "__main__":
    L.run(handle)
