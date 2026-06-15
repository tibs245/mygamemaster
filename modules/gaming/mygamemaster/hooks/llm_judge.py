#!/usr/bin/env python3
"""
llm_judge.py — Narrow-responsibility LLM judge: one call, two domains.

  • domain STEWARD: transactional consistency, LENIENT on names/formats
    ("saucisson" covers "saucisson sec dans la poche"). Bias TOWARD VALID when
    in doubt — never block the game incorrectly.
  • domain CONDUCT: inviolable GM rules (law of the game, mirror of SOUL.md).

Normalized output:
  {"ok": bool,
   "violations": [{"domaine":"banquier|conduite","regle":"AGENTIVITE",
                   "extrait":"...","pourquoi":"...","correction":"..."}]}

Tolerant / fail-open: if the call fails, is ambiguous or unreadable → ok=true
(never block on an uncertain judge → no loop). Mockable offline
via the env var MGM_JUDGE_MOCK (a verdict JSON).

Usable as a module (judge(...)) or via CLI for the gate mj_checkpoint.py.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _lib as L  # noqa: E402

# ── Rubric (mirror of SOUL.md "ABSOLUTE RULE — Agency" + header + errors) ──

RUBRIC = """STEWARD RULES (transactional consistency — be LENIENT):
- B1 RESOURCE: if the GM has a PC use/consume/give an item, that PC must own it. TOLERATE name and
  format variations ("sausage" = "a dry sausage in the pocket", "crowns" = "15 silver crowns").
  Refuse ONLY if the resource is clearly absent. When in doubt → VALID.
- B2 KNOWLEDGE: an NPC can only reveal/assert what they actually know (established facts).
  TOLERATE rephrasing. Doubt → VALID.
- B3 PRESENCE/POSSIBLE: the action must be physically possible in the scene (location, witnesses,
  time). Refuse only what is manifestly impossible.
- B4 NONEXISTENT NPC: an NPC named as a real actor but absent from the existing NPC list →
  flag as "to document" (domain banquier, regle DOCUMENTATION), not a hard refusal.

CONDUCT RULES (inviolable — be STRICT):
- AGENTIVITE: the GM NEVER decides/acts on behalf of a PC without validation (no action, decision,
  movement, dialogue or emotional reaction imposed on the PC). Describing what the PC perceives is
  OK ("you hear a creaking"), imposing a reaction is not ("fear grips you and you step back").
- PJ_ABSENT: do not have two PCs act when only one has spoken; do not play an absent PC.
- EMOTION_PNJ: do not assert an NPC's internal emotion as fact; only external signs.
- MECANIQUE_CACHEE: do not expose game mechanics in the narration (DC, modifiers, thresholds,
  encounter rolls, "Update npcs.json", "Sync Monde").
- POSSESSIF: do not grant the PC authority/ownership they do not have ("your hut, your
  people"); do not overwrite NPC relationships to re-center them on the PC.
- COMPARTIMENTATION: never reveal to a player information they should not know."""

SYSTEM = (
    "You are a rules checker for a tabletop role-playing game Master. You have a NARROW "
    "responsibility: spot clear violations of the provided rules. You do NOT judge narrative "
    "quality, style, or pacing. You are lenient on the STEWARD domain (bias toward valid) and "
    "strict on the CONDUCT domain. You respond ONLY in JSON."
)

FORMAT = (
    'Reply in strict JSON. If no clear violation: {"ok": true}. '
    'Otherwise: {"ok": false, "violations": [{"domaine": "banquier|conduite", '
    '"regle": "<code>", "extrait": "<exact GM quote>", "pourquoi": "<1 sentence>", '
    '"correction": "<concrete, actionable instruction for rewriting>"}]}. '
    "Only flag CLEAR violations. When in doubt, flag nothing."
)


def build_messages(draft, declared, etat):
    user = (
        RUBRIC
        + "\n\n--- AUTHORITATIVE STATE ---\n" + (etat or "(not available)")
        + "\n\n--- ACTION DECLARED BY THE PLAYER ---\n" + (declared or "(not available)")
        + "\n\n--- GM RESPONSE TO VERIFY ---\n" + (draft or "")
        + "\n\n" + FORMAT
    )
    return [{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}]


def _extract_json(text):
    """Extracts the first JSON object from a string (the model may include surrounding chatter)."""
    if not isinstance(text, str):
        return None
    start = text.find("{")
    while start != -1:
        depth = 0
        for i in range(start, len(text)):
            if text[i] == "{":
                depth += 1
            elif text[i] == "}":
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(text[start:i + 1])
                    except Exception:
                        break
        start = text.find("{", start + 1)
    return None


def _normalize(verdict):
    if not isinstance(verdict, dict):
        return {"ok": True, "violations": []}
    viols = verdict.get("violations")
    viols = viols if isinstance(viols, list) else []
    clean = []
    for v in viols:
        if not isinstance(v, dict):
            continue
        clean.append({
            "domaine": (v.get("domaine") or "conduite"),
            "regle": (v.get("regle") or "?"),
            "extrait": L.truncate(v.get("extrait", ""), 200),
            "pourquoi": L.truncate(v.get("pourquoi", ""), 200),
            "correction": L.truncate(v.get("correction", ""), 240),
        })
    ok = bool(verdict.get("ok", not clean)) and not clean
    return {"ok": ok, "violations": clean}


def judge(draft, declared, etat, cfg, api_key=None):
    """Returns a normalized verdict. Fail-open (ok=true) on any uncertainty."""
    # Test/offline mode: verdict injected by the environment.
    mock = os.environ.get("MGM_JUDGE_MOCK")
    if mock:
        try:
            return _normalize(json.loads(mock))
        except Exception:
            return {"ok": True, "violations": []}

    modele = cfg.get("modele")
    api_key = api_key or os.environ.get("OPENROUTER_API_KEY") or os.environ.get("MGM_JUDGE_API_KEY")
    if not modele or not api_key:
        return {"ok": True, "violations": [], "_skipped": "config"}

    url = cfg["base_url"].rstrip("/") + "/chat/completions"
    body = {
        "model": modele,
        "messages": build_messages(draft, declared, etat),
        "temperature": 0,
        "max_tokens": 600,
    }
    resp = L.http_json(url, body, headers={"Authorization": "Bearer " + api_key},
                       timeout=cfg.get("timeout", 8))
    if not resp:
        return {"ok": True, "violations": [], "_skipped": "unavailable"}
    try:
        content = resp["choices"][0]["message"]["content"]
    except Exception:
        return {"ok": True, "violations": [], "_skipped": "format"}
    return _normalize(_extract_json(content) or {"ok": True})


def format_feedback(violations, prefix="⚠️ CORRECTION"):
    """Explicit, numbered, actionable feedback — so the GM can self-correct."""
    if not violations:
        return ""
    lines = ["%s — you broke the rules. Correct yourself, do not repeat this :" % prefix]
    for i, v in enumerate(violations, 1):
        tag = "%s/%s" % (v.get("domaine", "?").upper(), v.get("regle", "?"))
        extrait = (" You wrote « %s »." % v["extrait"]) if v.get("extrait") else ""
        pourquoi = (" Problem: %s." % v["pourquoi"]) if v.get("pourquoi") else ""
        corr = (" Instead: %s" % v["correction"]) if v.get("correction") else ""
        lines.append("%d. [%s]%s%s%s" % (i, tag, extrait, pourquoi, corr))
    return "\n".join(lines)


# ── CLI (for mj_checkpoint.py): reads a payload {draft,declared,cwd} from stdin ──

if __name__ == "__main__":
    payload = L.read_payload()
    camp = L.campaign_dir(payload)
    monde = L.load_monde(camp)
    cfg = L.judge_config(monde)
    verdict = judge(
        payload.get("draft", ""),
        payload.get("declared", ""),
        L.etat_brief(camp, monde, for_judge=True),
        cfg,
    )
    L.emit(verdict)
