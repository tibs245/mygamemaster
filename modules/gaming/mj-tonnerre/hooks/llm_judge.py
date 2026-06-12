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
via the env var MJ_JUDGE_MOCK (a verdict JSON).

Usable as a module (judge(...)) or via CLI for the gate mj_checkpoint.py.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _lib as L  # noqa: E402

# ── Rubric (mirror of SOUL.md "ABSOLUTE RULE — Agency" + header + errors) ──

RUBRIC = """RÈGLES BANQUIER (cohérence transactionnelle — sois SOUPLE) :
- B1 RESSOURCE : si le MJ fait utiliser/consommer/donner un objet par un PJ, ce PJ doit le
  posséder. TOLÈRE les variations de nom et de format (« saucisson » = « un saucisson sec »,
  « couronnes » = « 15 couronnes d'argent »). Ne refuse QUE si la ressource est clairement
  absente. En cas de doute → VALIDE.
- B2 CONNAISSANCE : un PNJ ne peut révéler/affirmer que ce qu'il sait réellement (faits établis).
  TOLÈRE les reformulations. Doute → VALIDE.
- B3 PRÉSENCE/POSSIBLE : l'action doit être physiquement possible dans la scène (lieu, témoins,
  temps). Refuse seulement l'impossible manifeste.
- B4 PNJ INEXISTANT : un PNJ nommé comme acteur réel mais absent de la liste des PNJ existants →
  signaler « à documenter » (domaine banquier, regle DOCUMENTATION), pas un refus dur.

RÈGLES CONDUITE (inviolables — sois STRICT) :
- AGENTIVITE : le MJ ne décide/agit JAMAIS à la place d'un PJ sans validation (pas d'action, de
  décision, de déplacement, de dialogue ni de réaction émotionnelle imposés au PJ). Décrire ce que
  le PJ perçoit est OK (« tu entends un grincement »), lui imposer une réaction ne l'est pas
  (« la peur te saisit et tu recules »).
- PJ_ABSENT : ne pas faire agir deux PJ quand un seul a parlé ; ne pas jouer un PJ absent.
- EMOTION_PNJ : ne pas affirmer l'émotion interne d'un PNJ comme un fait ; seulement les signes
  extérieurs.
- MECANIQUE_CACHEE : ne pas exposer les mécaniques dans la narration (DD, modificateurs, seuils,
  jets de rencontre, « Update pnj.json », « Sync Monde »).
- POSSESSIF : ne pas attribuer au PJ une autorité/propriété qu'il n'a pas (« ta cabane, tes
  gens ») ; ne pas écraser les relations entre PNJ pour recentrer sur le PJ.
- COMPARTIMENTATION : ne jamais révéler à un joueur une info qu'il ne doit pas connaître."""

SYSTEM = (
    "Tu es un vérificateur de règles pour un Maître du Jeu de jeu de rôle. Tu as une "
    "responsabilité ÉTROITE : repérer les infractions claires aux règles fournies. Tu ne juges "
    "PAS la qualité narrative, le style ou le rythme. Tu es souple sur le domaine BANQUIER (biais "
    "vers valide) et strict sur le domaine CONDUITE. Tu réponds UNIQUEMENT en JSON."
)

FORMAT = (
    'Réponds en JSON strict. Si aucune infraction claire : {"ok": true}. '
    'Sinon : {"ok": false, "violations": [{"domaine": "banquier|conduite", '
    '"regle": "<code>", "extrait": "<citation exacte du MJ>", "pourquoi": "<1 phrase>", '
    '"correction": "<consigne concrète et actionnable pour réécrire>"}]}. '
    "Ne signale que des infractions CLAIRES. En cas de doute, ne signale rien."
)


def build_messages(draft, declared, etat):
    user = (
        RUBRIC
        + "\n\n--- ÉTAT FAISANT AUTORITÉ ---\n" + (etat or "(non disponible)")
        + "\n\n--- ACTION DÉCLARÉE PAR LE JOUEUR ---\n" + (declared or "(non disponible)")
        + "\n\n--- RÉPONSE DU MJ À VÉRIFIER ---\n" + (draft or "")
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
    mock = os.environ.get("MJ_JUDGE_MOCK")
    if mock:
        try:
            return _normalize(json.loads(mock))
        except Exception:
            return {"ok": True, "violations": []}

    modele = cfg.get("modele")
    api_key = api_key or os.environ.get("OPENROUTER_API_KEY") or os.environ.get("MJ_JUDGE_API_KEY")
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
        return {"ok": True, "violations": [], "_skipped": "indisponible"}
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
        corr = (" À la place : %s" % v["correction"]) if v.get("correction") else ""
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
