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
    if cfg.get("brief_scene"):  # gated by features.temporalite (see _lib.hooks_cfg)
        brief = build_scene_brief(camp, payload, monde)  # fail-open: "" if unavailable
        if brief:
            parts.append(brief)
    ctx = "\n\n".join(p for p in parts if p)
    return {"context": ctx} if ctx else {}


def build_context(camp, monde, payload=None):
    head = [
        "🧮 ÉTAT FAISANT AUTORITÉ — vérifie les fichiers avant de narrer "
        "(ne te fie pas à ta mémoire) :",
        "• Verbosité : %s" % L.verbosite(monde),
    ]
    # Author + admin status (reliable): lets the GM know who is speaking and only
    # execute !feature <axe> on|off if "admin: oui". Fail-open.
    try:
        aid = L.author_id(payload) if payload is not None else None
        est_admin = bool(aid and aid in L.admins(monde))
        head.append("• Auteur : %s · admin : %s" % (
            aid or "inconnu", "oui" if est_admin else "non"))
    except Exception:
        pass
    sess = L.active_session_number(camp)
    if sess is not None:
        head.append("• Session active : %s" % sess)
    brief = L.etat_brief(camp, monde)
    tail = ""
    if L.load_pnj_list(camp):
        tail = "\n⚠️ Un PNJ nommé absent de la liste = à documenter, pas à inventer."
    return "\n".join(head) + "\n" + brief + tail


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


def _scene_lieu_courant(camp, payload):
    """Scene location hint: .banquier/scene-<sid>.json > 'lieu_id', otherwise ENV
    MJ_SCENE_LIEU, otherwise None. Never guesses."""
    try:
        sid = str(payload.get("session_id") or "default")
        hint = L.load_json(camp / ".banquier" / ("scene-%s.json" % sid))
        if isinstance(hint, dict) and hint.get("lieu_id"):
            return str(hint["lieu_id"])
    except Exception:
        pass
    env = os.environ.get("MJ_SCENE_LIEU", "").strip()
    return env or None


def _scripts_dir():
    """Directory of the living-world scripts (sibling of the hooks/ folder)."""
    from pathlib import Path
    return Path(os.path.dirname(os.path.abspath(__file__))).parent / "scripts"


if __name__ == "__main__":
    L.run(handle)
