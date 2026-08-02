#!/usr/bin/env python3
"""
dialogue_judge.py — LLM grader for the QUALITY of NPC dialogue. One call, four criteria.

The sibling `llm_judge.py` deliberately refuses this job ("You do NOT judge narrative
quality"): it guards rules, and it must stay narrow. Nothing, therefore, was watching
the failure the field actually reported — conversations that break no rule and are
still flat, empty, not worth reading.

Rubric (references/dialogue-craft.md §4), each scored 0..5:
  INTENTION   the line pursues the NPC's own goal, not the PC's question
  SOUS_TEXTE  a gap exists between what is said and what is wanted
  VOIX        the mouths are distinguishable, and match the sheet's `voix` block
  ENJEU       something costs, moves, or is refused, visibly

Normalized output:
  {"ok": bool, "score": int, "seuil": int, "criteres": {...},
   "faibles": [{"critere","pourquoi","correction"}]}

FAIL-OPEN like its sibling: an unconfigured, unreachable or unparseable grader returns
ok=true. A grading outage must never DEGRADE the game to the summary fallback — losing
a good scene because a network call timed out is a worse trade than shipping an
ungraded one. Mockable offline via MGM_DIALOGUE_MOCK (a verdict JSON).

Usable as a module (has_dialogue / judge / format_feedback) or via CLI for mj_checkpoint.py.
"""
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _lib as L  # noqa: E402
from llm_judge import _extract_json  # noqa: E402  (same package, one JSON reader)

CRITERES = ("INTENTION", "SOUS_TEXTE", "VOIX", "ENJEU")
MAX_PAR_CRITERE = 5

RUBRIC = """You grade the QUALITY of the NPC DIALOGUE in this narration, and nothing else.
Descriptions, atmosphere, action and pacing are OUT OF SCOPE. Rules, consistency and player
agency are checked elsewhere — do not report them.

Score each criterion from 0 to 5 (0 = absent, 3 = acceptable, 5 = the scene a player quotes
back to their friends afterwards):

INTENTION — Does each NPC line pursue THAT NPC's own goal, instead of merely serving the PC's
  question? 0 = an information vending machine: asked, answers, fully, immediately, for free.
  5 = every line is the NPC working on their own agenda, with the PC's question as the occasion.

SOUS_TEXTE — Is there a gap between what is said and what is wanted? Is something withheld,
  deflected, or answered sideways? 0 = the character is transparent, says exactly what they
  think. 5 = what is not said is what makes the exchange worth reading, and the player can feel
  it is there. (Withholding EVERYTHING scores low too: the player must have something to push against.)

VOIX — With the name tags removed, could a reader tell who is speaking? Does each mouth have
  its own register, rhythm and vocabulary — and does it MATCH the character's recorded voice
  when one is provided below? 0 = interchangeable mouths, all sounding like the narrator.
  5 = unmistakable, and consistent with the sheet. A verbal tic on every single line is NOT a
  voice — it is a parrot; score it down.

ENJEU — By the end of the exchange, does something cost, move, or get refused, VISIBLY to the
  player? (something obtained AND paid for; an explicit refusal with a reason; a relation that
  shifts; a new obligation, threat or deadline.) 0 = polite scene, world unchanged.
  5 = the player leaves the conversation with a different problem than they walked in with.

Grade what is on the page. Do not reward intentions you infer, and do not penalise a scene for
being short if the short scene does its work."""

SYSTEM = (
    "You are a dialogue editor for a tabletop role-playing game. You grade the quality of NPC "
    "dialogue against a fixed rubric, strictly and without flattery, and you propose ONE concrete "
    "fix per weak criterion — an instruction the writer can act on, never a rewrite of the scene. "
    "You respond ONLY in JSON."
)

FORMAT = (
    'Reply in strict JSON: {"scores": {"INTENTION": 0-5, "SOUS_TEXTE": 0-5, "VOIX": 0-5, '
    '"ENJEU": 0-5}, "faibles": [{"critere": "<code>", "pourquoi": "<1 sentence, quote the '
    'weakest line>", "correction": "<one concrete, actionable instruction>"}]}. '
    "List in `faibles` ONLY the criteria you scored 2 or below."
)

# A dialogue marker, not an em dash: a speech dash opens a line (or follows sentence-final
# punctuation), possibly through markdown emphasis. "his eyes — pale green — moved" is prose.
_TIRET_RE = re.compile(r"(?:^|[\n.!?…:»])\s*[*_>\s]*[—–]\s+\S", re.M)
_GUILLEMETS_RE = re.compile(r"[«»]")
_CITATION_RE = re.compile(r"[\"“][^\"“”\n]{6,}[\"”]")


def has_dialogue(texte):
    """True when the narration contains at least one spoken line.

    Deterministic and cheap: it decides whether the grading call happens at all, so a
    narration with no dialogue never pays for a judge that has nothing to grade.
    """
    if not isinstance(texte, str) or not texte.strip():
        return False
    return bool(_TIRET_RE.search(texte) or _GUILLEMETS_RE.search(texte)
                or _CITATION_RE.search(texte))


def voices_context(camp, draft, max_npc=4, max_chars=1200):
    """Recorded `voix` blocks of the NPCs actually named in the draft.

    Without this the VOIX criterion is a matter of taste; with it the grader compares the
    scene against what the campaign already decided this mouth sounds like — which is also
    how voice drift between sessions gets caught.
    """
    if not isinstance(draft, str) or not draft:
        return ""
    blocs = []
    for fiche in L.load_pnj_list(camp):
        if not isinstance(fiche, dict):
            continue
        nom = str(fiche.get("name") or fiche.get("nom") or "").strip()
        voix = fiche.get("voix")
        if not nom or not isinstance(voix, dict) or nom not in draft:
            continue
        bits = []
        for cle in ("registre", "rythme", "sous_tension"):
            val = voix.get(cle)
            if isinstance(val, str) and val.strip():
                bits.append("%s: %s" % (cle, L.truncate(val.strip(), 200)))
        for cle in ("tics", "ne_dit_jamais"):
            val = voix.get(cle)
            if isinstance(val, list) and val:
                bits.append("%s: %s" % (cle, L.truncate(" ; ".join(str(v) for v in val), 200)))
        if bits:
            blocs.append("• %s — %s" % (nom, " | ".join(bits)))
        if len(blocs) >= max_npc:
            break
    if not blocs:
        return ""
    return L.truncate("RECORDED VOICES (the scene must match these):\n" + "\n".join(blocs), max_chars)


def build_messages(draft, declared, voix):
    user = (
        RUBRIC
        + "\n\n--- ACTION DECLARED BY THE PLAYER ---\n" + (declared or "(not available)")
        + (("\n\n--- " + voix) if voix else "")
        + "\n\n--- NARRATION TO GRADE ---\n" + (draft or "")
        + "\n\n" + FORMAT
    )
    return [{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}]


def _note(valeur):
    try:
        n = int(round(float(valeur)))
    except (TypeError, ValueError):
        return None
    return max(0, min(MAX_PAR_CRITERE, n))


def _normalize(verdict, cfg):
    """Verdict → normalized dict. A missing criterion is not graded rather than scored 0:
    a grader that answered partially must not be able to condemn a scene by omission."""
    seuil = int(cfg.get("seuil", 12))
    plancher = int(cfg.get("plancher", 1))
    if not isinstance(verdict, dict):
        return {"ok": True, "score": None, "seuil": seuil, "criteres": {}, "faibles": [],
                "_skipped": "format"}

    brut = verdict.get("scores")
    brut = brut if isinstance(brut, dict) else verdict
    criteres = {}
    for code in CRITERES:
        n = _note(brut.get(code))
        if n is not None:
            criteres[code] = n
    if not criteres:
        return {"ok": True, "score": None, "seuil": seuil, "criteres": {}, "faibles": [],
                "_skipped": "unscored"}

    manquants = [c for c in CRITERES if c not in criteres]
    score = sum(criteres.values())
    # Missing criteria are credited at par so a partial answer cannot fail the scene alone.
    score_effectif = score + len(manquants) * 3
    faible = min(criteres.values()) <= plancher
    ok = (score_effectif >= seuil) and not faible

    faibles = []
    for v in verdict.get("faibles") or []:
        if not isinstance(v, dict):
            continue
        code = str(v.get("critere") or "?").upper()
        faibles.append({
            "critere": code if code in CRITERES else "?",
            "pourquoi": L.truncate(v.get("pourquoi", ""), 220),
            "correction": L.truncate(v.get("correction", ""), 260),
        })
    if not ok and not faibles:
        for code, n in sorted(criteres.items(), key=lambda kv: kv[1]):
            if n <= plancher or score_effectif < seuil:
                faibles.append({"critere": code, "pourquoi": "scored %d/5" % n, "correction": ""})
            if len(faibles) >= 2:
                break

    return {"ok": bool(ok), "score": score_effectif, "seuil": seuil,
            "criteres": criteres, "faibles": faibles}


def judge(draft, declared, voix, cfg, api_key=None):
    """Returns a normalized verdict. Fail-open (ok=true) on any uncertainty."""
    mock = os.environ.get("MGM_DIALOGUE_MOCK")
    if mock:
        try:
            return _normalize(json.loads(mock), cfg)
        except Exception:
            return {"ok": True, "score": None, "seuil": int(cfg.get("seuil", 12)),
                    "criteres": {}, "faibles": [], "_skipped": "mock"}

    modele = cfg.get("modele")
    api_key = api_key or os.environ.get("OPENROUTER_API_KEY") or os.environ.get("MGM_JUDGE_API_KEY")
    base = {"ok": True, "score": None, "seuil": int(cfg.get("seuil", 12)),
            "criteres": {}, "faibles": []}
    if not modele or not api_key:
        return dict(base, _skipped="config")

    url = str(cfg.get("base_url", "")).rstrip("/") + "/chat/completions"
    body = {
        "model": modele,
        "messages": build_messages(draft, declared, voix),
        "temperature": 0,
        "max_tokens": 700,
    }
    resp = L.http_json(url, body, headers={"Authorization": "Bearer " + api_key},
                       timeout=cfg.get("timeout", 16))
    if not resp:
        return dict(base, _skipped="unavailable")
    try:
        content = resp["choices"][0]["message"]["content"]
    except Exception:
        return dict(base, _skipped="format")
    parsed = _extract_json(content)
    if parsed is None:
        return dict(base, _skipped="format")
    return _normalize(parsed, cfg)


_RAPPELS = {
    "INTENTION": "give the NPC something to get out of this exchange, and write the line from that",
    "SOUS_TEXTE": "have them answer beside the question, or give a partial truth they let stand",
    "VOIX": "write the line only this character could say — register, rhythm, what they never say",
    "ENJEU": "make it cost, move or be refused: a price, an explicit no with a reason, a new obligation",
}


def format_feedback(verdict, prefix="🎭 DIALOGUE — too flat to ship"):
    """Named, actionable feedback: which criterion failed, on which line, and what to do."""
    criteres = verdict.get("criteres") or {}
    detail = ", ".join("%s %d/5" % (c, criteres[c]) for c in CRITERES if c in criteres)
    lines = ["%s (%s/%s%s). Rewrite the dialogue — not the description:"
             % (prefix, verdict.get("score", "?"), verdict.get("seuil", "?"),
                (" — " + detail) if detail else "")]
    for i, v in enumerate(verdict.get("faibles") or [], 1):
        code = v.get("critere", "?")
        pourquoi = (" %s." % v["pourquoi"]) if v.get("pourquoi") else ""
        corr = v.get("correction") or _RAPPELS.get(code, "")
        lines.append("%d. [%s]%s Fix: %s" % (i, code, pourquoi, corr))
    lines.append("Reference: references/dialogue-craft.md §2.")
    return "\n".join(lines)


FALLBACK = (
    "🎭 DIALOGUE — second attempt still below the bar. Do NOT ship the dialogue: deliver the "
    "DRY SUMMARY instead (references/dialogue-craft.md §5).\n"
    "  • Reported speech only — no quoted line, no speech dash, no quotation marks.\n"
    "  • State the outcome: what was asked, what was granted or refused, at what price, and "
    "what changed (relation, obligation, information, deadline).\n"
    "  • Persist it exactly as if it had been played (npcs.json / world.json, same response).\n"
    "  • Never tell the player a scene was rejected, and do not offer to replay it."
)


if __name__ == "__main__":
    payload = L.read_payload()
    camp = L.campaign_dir(payload)
    monde = L.load_monde(camp)
    cfg = L.dialogue_config(monde)
    draft = payload.get("draft", "")
    if not cfg["actif"]:
        L.emit({"ok": True, "_skipped": "inactive"})
    elif not has_dialogue(draft):
        L.emit({"ok": True, "_skipped": "no-dialogue"})
    else:
        L.emit(judge(draft, payload.get("declared", ""), voices_context(camp, draft), cfg))
