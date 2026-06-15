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
Overridden by the `MGM_TTS_FORMAT_MODEL` env var. Key: `OPENROUTER_API_KEY`.

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
Mockable offline via MGM_TTS_FORMAT_MOCK (an output JSON).

Usable as a module (format_narration(...)) or as a CLI (text on stdin).
"""
import json
import os
import re
import sys
import urllib.error
import urllib.request

DEFAULT_MODEL = os.environ.get("MGM_TTS_FORMAT_MODEL", "minimax/minimax-m3")
DEFAULT_BASE_URL = os.environ.get("MGM_TTS_FORMAT_BASE_URL", "https://openrouter.ai/api/v1")
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
    "You are preparing a tabletop-RPG Game Master's NARRATION for text-to-speech synthesis "
    "(female French storyteller voice). You do NOT rewrite the story: you reformat the text "
    "so it sounds right when spoken aloud. You reply ONLY in strict JSON."
)

INSTRUCTION = """Transform the narration below into a high-quality VOCAL SCRIPT.

MANDATORY RULES:
1. PRESERVE the narrative text, its tone, its vocabulary, and above all the storyteller's
   VERBAL TICS and turns of phrase ("voyez-vous", "ah…", interjections, stylistic repetitions).
   Do not paraphrase, summarise, or censor the story.
2. REMOVE everything that is NOT spoken narration: dice-roll notations (1d20, +3, DD15),
   bracketed stat numbers, technical references ("Update npcs.json"), command labels (!jet),
   admin markers, decorative emojis. Keep pronounceable numbers written out in words where natural.
3. The voice ALREADY BREATHES NATURALLY on punctuation (".", ",", "…", "?", "!"):
   do not double those silences. Only add a Minimax pause `<#x.x#>` (seconds, 0.3–0.8 —
   max 1.0 for an exceptional effect) for a GENUINE dramatic beat: before a revelation, on
   a sudden tonal shift. RARE: at most 1 every 4–6 sentences, NEVER as a substitute for
   punctuation. Place them BETWEEN two pronounceable passages, never two in a row, never
   at the very start/end. When in doubt: no pause.
4. SPLIT the narration into emotion SEGMENTS: a "segments" array, each entry being
   {"text": "<spoken portion>", "emotion": "<one of the 8>"}. The emotion CAN and MUST change
   from one segment to the next when the scene shifts (apparition → surprised, danger → fearful,
   calm return → calm): this is what makes the story PERFORMED rather than flat. Valid emotions:
   calm (= "Neutral" in the app), happy, sad, angry, fearful, disgusted, surprised, fluent. Cover
   ALL the spoken text, in order, with no gaps. If the emotion does not change, ONE segment is
   enough. Also fill the "emotion" field = the DOMINANT emotion (fallback if segmentation is cut).
   Do not default to calm/fluent without reason.
5. SPARINGLY add interjection tags — non-verbal sounds placed INLINE in the "text" of the
   relevant segment, in parentheses, with EXACT spelling (control tokens; otherwise read aloud
   literally). Valid list (speech-2.8 only):
     (laughs) (chuckle) (coughs) (clear-throat) (groans) (breath) (pant) (inhale) (exhale)
     (gasps) (sniffs) (sighs) (snorts) (burps) (lip-smacking) (humming) (hissing) (emm) (sneezes)
   For a storyteller, favour breaths/emotions: (sighs) (gasps) (breath) (inhale)
   (exhale) (chuckle) (clear-throat) (sniffs) (groans). Reserve the others (burps, sneezes,
   hissing…) for when a character ACTUALLY does it. Place them where SHE would: a breath before
   a revelation, a gasp at an apparition. At most 1–2 per passage, NEVER on every sentence,
   never decorative. Inexact spelling = no tag. When in doubt: none.
6. SUGGEST a background ambiance sound from: foret, taverne, combat, nuit, ville, donjon, mer,
   aucune. Use "aucune" if the scene has no obvious sonic anchor.
7. SET moment_cle=true only if this is a standout moment (revelation, climax, strong atmosphere
   scene) that justifies the background sound; otherwise false.

Reply STRICTLY in JSON:
{"segments":[{"text":"...","emotion":"..."}, ...], "emotion":"...", "ambiance":"...", "moment_cle":true|false}
Example: {"segments":[{"text":"A monster surges from the shadows! (gasps)","emotion":"surprised"},
{"text":"<#0.6#> Stones fall all around you.","emotion":"fearful"},
{"text":"Then silence returns.","emotion":"calm"}], "emotion":"fearful", "ambiance":"combat",
"moment_cle":true}
No text outside the JSON.

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

    mock = os.environ.get("MGM_TTS_FORMAT_MOCK")
    if mock:
        try:
            return _normalize(json.loads(mock), text)
        except Exception:
            return _fallback(text)

    model = model or DEFAULT_MODEL
    api_key = api_key or os.environ.get("OPENROUTER_API_KEY") or os.environ.get("MGM_TTS_FORMAT_API_KEY")
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
