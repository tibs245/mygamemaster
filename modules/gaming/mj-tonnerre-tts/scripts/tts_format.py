#!/usr/bin/env python3
"""
tts_format.py — "Small model" step: written narration → quality vocal script.

Purpose: OFFLOAD the main model (the GM) from all TTS concerns. The GM writes
their narration normally; this script transforms it, via a dedicated low-cost LLM
call, into a script optimised for Minimax voice synthesis — WITHOUT ever polluting
the written message delivered to the player (the markup lives only in the ephemeral script).

Default model: `minimax/minimax-m3` (same publisher as the TTS engine → knows
its own pause markup `<#x.x#>` and its emotions) with LOW REASONING
(reasoning.effort=low, low temperature) — this is reformatting, not reasoning.
Overridden by the `MJ_TTS_FORMAT_MODEL` env var. Key: `OPENROUTER_API_KEY`.

Output (strict JSON) — the emotional segmentation is a structured ARRAY (not inline
tags): each segment = a dedicated Minimax call, recomposed afterwards.
  {
    "segments": [ {"text": "<spoken portion; pauses <#x.x#> and (sighs)… tags inline>",
                   "emotion": "calm|happy|sad|angry|fearful|disgusted|surprised|fluent"}, … ],
    "emotion":   "calm|…|fluent",   # DOMINANT emotion (mono fallback if segmentation is cut)
    "ambiance":  "foret|taverne|combat|nuit|ville|donjon|mer|aucune",
    "moment_cle": true|false
  }
A "script" field is also derived = concatenation of segment texts (sidecar / mono fallback).

TOTAL FAIL-OPEN: failed/unreadable/ambiguous call → a single segment = lightly
cleaned narration, emotion="calm", ambiance="aucune". The voice of a turn is NEVER broken.
Mockable offline via MJ_TTS_FORMAT_MOCK (an output JSON).

Usable as a module (format_narration(...)) or as a CLI (text on stdin).
"""
import json
import os
import re
import sys
import urllib.error
import urllib.request

DEFAULT_MODEL = os.environ.get("MJ_TTS_FORMAT_MODEL", "minimax/minimax-m3")
DEFAULT_BASE_URL = os.environ.get("MJ_TTS_FORMAT_BASE_URL", "https://openrouter.ai/api/v1")
# Emotions accepted by speech-2.8-turbo. NO `whisper`: it is reserved for
# 2.6 models (2.8-hd/turbo reject it → error 2013). `fluent` = smooth neutral tone.
VALID_EMOTIONS = {"calm", "happy", "sad", "angry", "fearful",
                  "disgusted", "surprised", "fluent"}
# The Minimax app displays "Neutral" for the API value `calm`: we accept both on
# input and normalise to the API value. (The API only knows `calm`.)
EMOTION_ALIASES = {"neutral": "calm"}
VALID_AMBIANCES = {"foret", "taverne", "combat", "nuit", "ville", "donjon", "mer", "aucune"}


def canon_emotion(value, default=None):
    """Normalise an emotion (case, alias Neutral→calm) to a valid API value, otherwise `default`."""
    e = (value or "").strip().lower()
    e = EMOTION_ALIASES.get(e, e)
    return e if e in VALID_EMOTIONS else default

SYSTEM = (
    "Tu prépares la NARRATION d'un Maître du Jeu de jeu de rôle pour une synthèse vocale "
    "(voix féminine française, conteuse). Tu NE réécris PAS l'histoire : tu reformates le texte "
    "pour qu'il sonne juste à l'oral. Tu réponds UNIQUEMENT en JSON strict."
)

INSTRUCTION = """Transforme la narration ci-dessous en un SCRIPT VOCAL de qualité.

RÈGLES IMPÉRATIVES :
1. PRÉSERVE le texte narratif, son ton, son vocabulaire et surtout les TICS DE LANGAGE et
   tournures de la conteuse (« voyez-vous », « ah… », interjections, répétitions stylistiques).
   Ne paraphrase pas, ne résume pas, ne censure pas le récit.
2. RETIRE tout ce qui n'est PAS de la narration parlée : notations de dés (1d20, +3, DD15),
   chiffres de stats entre crochets, mentions techniques (« Update pnj.json »), libellés de
   commandes (!jet), marqueurs d'admin, émojis décoratifs. Garde les nombres prononçables en
   toutes lettres si naturel.
3. La voix RESPIRE DÉJÀ NATURELLEMENT sur la ponctuation (« . », « , », « … », « ? »,
   « ! ») : ne double pas ces silences. N'ajoute une pause Minimax `<#x.x#>` (secondes,
   0.3 à 0.8 — max 1.0 pour un effet exceptionnel) QUE sur un vrai temps dramatique :
   avant une révélation, sur une bascule de ton brutale. RARE : au plus 1 toutes les 4-6
   phrases, JAMAIS comme substitut à une ponctuation. Place-les ENTRE deux passages
   prononçables, jamais deux à la suite, jamais en tout début/fin. En cas de doute : pas de pause.
4. DÉCOUPE la narration en SEGMENTS d'émotion : un tableau "segments", chaque entrée étant
   {"text": "<portion parlée>", "emotion": "<une des 8>"}. L'émotion PEUT et DOIT changer d'un
   segment à l'autre quand la scène bascule (apparition → surprised, danger → fearful, accalmie
   → calm) : c'est ce qui rend le récit JOUÉ plutôt que plat. Émotions valides : calm
   (= « Neutral » dans l'app), happy, sad, angry, fearful, disgusted, surprised, fluent. Couvre
   TOUT le texte parlé, dans l'ordre, sans trou. Si l'émotion ne bouge pas, UN seul segment
   suffit. Renseigne AUSSI le champ "emotion" = l'émotion DOMINANTE (repli si la segmentation
   est coupée). Ne te limite pas à calm/fluent sans raison.
5. POSE, avec PARCIMONIE, des tags d'interjection — sons non verbaux glissés INLINE dans le
   "text" du segment concerné, entre parenthèses, avec l'orthographe EXACTE (jetons de contrôle,
   sinon lus tels quels). Liste valide (speech-2.8 uniquement) :
     (laughs) (chuckle) (coughs) (clear-throat) (groans) (breath) (pant) (inhale) (exhale)
     (gasps) (sniffs) (sighs) (snorts) (burps) (lip-smacking) (humming) (hissing) (emm) (sneezes)
   Pour une conteuse, privilégie les souffles/émotions : (sighs) (gasps) (breath) (inhale)
   (exhale) (chuckle) (clear-throat) (sniffs) (groans). Réserve les autres (burps, sneezes,
   hissing…) au cas où un personnage le fait VRAIMENT. Place-les là où ELLE le ferait : un
   souffle avant une révélation, un hoquet à une apparition. Au plus 1-2 par passage, JAMAIS
   sur chaque phrase, jamais décoratif. Orthographe inexacte = pas de tag. En cas de doute : aucun.
6. PROPOSE un fond sonore d'ambiance parmi : foret, taverne, combat, nuit, ville, donjon, mer,
   aucune. Mets "aucune" si la scène n'a pas d'ancrage sonore évident.
7. INDIQUE moment_cle=true seulement si c'est un moment marquant (révélation, climax, scène
   d'ambiance forte) qui justifie le fond sonore ; sinon false.

Réponds STRICTEMENT en JSON :
{"segments":[{"text":"...","emotion":"..."}, ...], "emotion":"...", "ambiance":"...", "moment_cle":true|false}
Exemple : {"segments":[{"text":"Un monstre surgit des ombres ! (gasps)","emotion":"surprised"},
{"text":"<#0.6#> Les pierres tombent autour de toi.","emotion":"fearful"},
{"text":"Puis le silence revient.","emotion":"calm"}], "emotion":"fearful", "ambiance":"combat",
"moment_cle":true}
Aucun texte hors du JSON.

--- NARRATION ---
"""

# Minimal fallback cleanup (fail-open): removes dice roll notations and obvious emojis.
_DICE_RE = re.compile(r"\b\d*d\d+([+-]\d+)?\b", re.I)
_BRACKET_RE = re.compile(r"\[[^\]]*\]")
_CMD_RE = re.compile(r"(?m)^\s*![a-zA-Zéè-]+.*$")


def _basic_clean(text):
    t = _CMD_RE.sub("", text or "")
    t = _DICE_RE.sub("", t)
    t = _BRACKET_RE.sub("", t)
    t = re.sub(r"[ \t]{2,}", " ", t)
    return t.strip()


def _fallback(text):
    clean = _basic_clean(text)
    return {"segments": [{"emotion": "calm", "text": clean}] if clean else [],
            "script": clean, "emotion": "calm",
            "ambiance": "aucune", "moment_cle": False, "_fallback": True}


def _extract_json(text):
    """Extracts the first JSON object from a string (the model may produce surrounding chatter)."""
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


# Leftover emotion tag {emotion}/{/emotion} that a chatty model might leave
# in a "text" field: cleaned out as a safety measure (never sent to/read by Minimax).
_STRAY_TAG_RE = re.compile(r"\{/?\s*[a-zA-Z]+\s*\}")


def strip_emotion_tags(text):
    """Removes any leftover {emotion}/{/emotion} tags from spoken text (defensive)."""
    return _STRAY_TAG_RE.sub("", text or "").strip()


def normalize_segments(raw, default_emotion="calm", *, max_segments=12):
    """Validates/normalises the segment list produced by the model (see tts_render).

    Input: list of dicts {"text", "emotion"}. Returns a clean list
    [{"text": <no leftover tags>, "emotion": <valid>}]:
      - emotion normalised (case, alias Neutral→calm); invalid → `default_emotion`;
      - empty segments discarded, leftover {…} tags cleaned from text;
      - adjacent segments with the SAME emotion merged;
      - beyond `max_segments` → mono-segment fallback (over-fragmentation: a unified
        voice is preferred over a patchwork).
    Fail-open: non-list / empty input → [].
    """
    default_emotion = canon_emotion(default_emotion, "calm")
    merged = []
    if isinstance(raw, list):
        for item in raw:
            if not isinstance(item, dict):
                continue
            txt = item.get("text")
            txt = strip_emotion_tags(txt) if isinstance(txt, str) else ""
            if not txt:
                continue
            emo = canon_emotion(item.get("emotion"), default_emotion)
            if merged and merged[-1]["emotion"] == emo:
                merged[-1]["text"] = (merged[-1]["text"] + " " + txt).strip()
            else:
                merged.append({"emotion": emo, "text": txt})
    if len(merged) > max_segments:
        whole = " ".join(s["text"] for s in merged).strip()
        return [{"emotion": default_emotion, "text": whole}] if whole else []
    return merged


def _normalize(out, original):
    """Validates/bounds the model output; field-by-field fallback (fail-open)."""
    if not isinstance(out, dict):
        return _fallback(original)
    emotion = canon_emotion(out.get("emotion"), "calm")
    segments = normalize_segments(out.get("segments"), emotion)
    if not segments:
        # No usable segment → mono fallback on the cleaned original text.
        clean = _basic_clean(original)
        if not clean:
            return _fallback(original)
        segments = [{"emotion": emotion, "text": clean}]
    ambiance = out.get("ambiance")
    ambiance = ambiance if ambiance in VALID_AMBIANCES else "aucune"
    return {
        "segments": segments,
        "script": " ".join(s["text"] for s in segments).strip(),
        "emotion": emotion,
        "ambiance": ambiance,
        "moment_cle": bool(out.get("moment_cle", False)),
    }


def _http_json(url, body, headers, timeout):
    data = json.dumps(body, ensure_ascii=False).encode("utf-8")
    hdr = dict(headers)
    hdr.setdefault("Content-Type", "application/json")
    try:
        req = urllib.request.Request(url, data=data, headers=hdr)
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.load(r)
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, OSError, ValueError):
        return None


def format_narration(text, *, model=None, api_key=None, base_url=None, timeout=20):
    """Returns {segments, script, emotion, ambiance, moment_cle}. Fail-open to _basic_clean(text)."""
    if not text or not text.strip():
        return _fallback(text or "")

    mock = os.environ.get("MJ_TTS_FORMAT_MOCK")
    if mock:
        try:
            return _normalize(json.loads(mock), text)
        except Exception:
            return _fallback(text)

    model = model or DEFAULT_MODEL
    api_key = api_key or os.environ.get("OPENROUTER_API_KEY") or os.environ.get("MJ_TTS_FORMAT_API_KEY")
    base_url = base_url or DEFAULT_BASE_URL
    if not api_key:
        return _fallback(text)

    url = base_url.rstrip("/") + "/chat/completions"
    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": INSTRUCTION + text},
        ],
        "temperature": 0.4,
        "max_tokens": 1600,
        # LOW reasoning: this is reformatting, not reasoning (low cost/latency).
        "reasoning": {"effort": "low"},
    }
    resp = _http_json(url, body, {"Authorization": "Bearer " + api_key}, timeout)
    if not resp:
        return _fallback(text)
    try:
        content = resp["choices"][0]["message"]["content"]
    except Exception:
        return _fallback(text)
    return _normalize(_extract_json(content) or {}, text)


def main():
    text = sys.stdin.read()
    out = format_narration(text)
    print(json.dumps(out, ensure_ascii=False))


if __name__ == "__main__":
    main()
