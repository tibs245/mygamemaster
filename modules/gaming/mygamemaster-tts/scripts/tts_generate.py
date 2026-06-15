#!/usr/bin/env python3
"""
tts_generate.py — Low-level building block: text-to-speech via Minimax T2A v2.

Single, definitive script (stdlib only) that:
  1. builds the Minimax T2A v2 request (model speech-2.8-turbo by default,
     voice French_Female_Speech_New, hex output);
  2. calls the API, with retries on transient errors (429 / 5xx / network);
  3. decodes the `data.audio` field (hex) and writes it as MP3;
  4. optionally writes the `.json` metadata sidecar next to the MP3.

The key is read from the environment (`MINIMAX_API_KEY`) — NEVER as an argument:
in the Hermes container it is injected via EnvironmentFile (cf. ansible/roles/
hermes_deploy/tasks/credentials.yml). No key → exit 2 (caller fail-open).

Text is supplied via file (`--text-file`) or stdin (`--text-file -`), never as
an argument: it may contain the pause markup `<#x.x#>` and special characters.

Minimax pause markup: `<#0.8#>` inserts 0.8 s of silence (0.01–99.99). Must be
placed BETWEEN pronounceable text, never two consecutive markers.

Usage:
  echo "Text <#0.8#> to speak." | python3 tts_generate.py --out voix.mp3
  python3 tts_generate.py --text-file script.txt --out voix.mp3 \
      --voice French_Female_Speech_New --emotion fearful --speed 0.95

Exit codes:
  0  audio generated (MP3 written)
  1  generation failure (response without audio / HTTP / network)
  2  usage error (missing key, empty text, invalid argument)

Offline test mode: MGM_TTS_MOCK=1 writes a dummy MP3 without any network call.
"""
import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request

# International endpoint (api-uw.minimax.io = reduced-latency US-West variant).
API_URL = os.environ.get("MINIMAX_API_URL", "https://api.minimax.io/v1/t2a_v2")
DEFAULT_MODEL = "speech-2.8-turbo"
DEFAULT_VOICE = "French_Female_Speech_New"

# ── Per-language voice/language_boost defaults ───────────────────────────────
# Each entry: (voice_id, language_boost).  Override per-campaign in
# world.json > meta.audio.voice (and optionally meta.audio.language_boost).
# Add new languages here: structure is trivial — one line per language code.
# Language codes are lower-cased ISO-639-1 (e.g. "fr", "en", "de", "es").
#
# voice_id catalogue (Minimax T2A v2):
#   French_Female_Speech_New  — female, native French, warm narrator
#   Serene_Female             — female, smooth, language-neutral (good default for EN)
#   (add more as Minimax releases them; keep this table the single source of truth)
LANGUAGE_DEFAULTS = {
    "fr": {
        "voice": "French_Female_Speech_New",
        "language_boost": "French",
    },
    "en": {
        "voice": "Serene_Female",
        "language_boost": "English",
    },
    # Sentinel: used when the language code is unknown/absent (fail-open).
    "_default": {
        "voice": DEFAULT_VOICE,
        "language_boost": "French",
    },
}


def voice_for_language(language_code=None):
    """Return ``(voice_id, language_boost)`` for a given BCP-47/ISO-639-1 code.

    Resolution order (fail-open — never raises):
    1. ``language_code`` looked up in ``LANGUAGE_DEFAULTS`` (lower-cased, only the
       primary subtag, e.g. ``"fr-CA"`` → ``"fr"``).
    2. ``_default`` entry if the code is unknown or absent.

    The caller (tts_render) may still override both values when
    ``world.json > meta.audio.voice`` is set explicitly.
    """
    lang = (language_code or "").strip().lower().split("-")[0].split("_")[0]
    entry = LANGUAGE_DEFAULTS.get(lang) or LANGUAGE_DEFAULTS["_default"]
    return entry["voice"], entry["language_boost"]


# Emotions supported by T2A v2 (see Minimax docs). Any other value → ignored.
VALID_EMOTIONS = {"happy", "sad", "angry", "fearful", "disgusted",
                  "surprised", "calm", "fluent", "whisper"}
# The app displays "Neutral"; the API value is `calm`. Normalise before validation.
EMOTION_ALIASES = {"neutral": "calm"}
# `whisper` exists ONLY on 2.6 models; speech-2.8-hd/turbo reject it
# (error 2013 "invalid input parameters"). Silently drop it for other models.
WHISPER_ONLY_MODELS = {"speech-2.6-turbo", "speech-2.6-hd"}
VALID_SAMPLE_RATES = {8000, 16000, 22050, 24000, 32000, 44100}
VALID_BITRATES = {32000, 64000, 128000, 256000}

# A small valid silent MP3 (MPEG-1 Layer III frame), repeated, for mock mode.
_MOCK_MP3_FRAME = bytes.fromhex("fffb9064") + b"\x00" * 414


def die(msg, code):
    print("ERROR: %s" % msg, file=sys.stderr)
    sys.exit(code)


def build_payload(text, model, voice, emotion, speed, vol, pitch,
                  sample_rate, bitrate, channel, language_boost):
    voice_setting = {
        "voice_id": voice,
        "speed": speed,
        "vol": vol,
        "pitch": pitch,
    }
    emotion = EMOTION_ALIASES.get((emotion or "").strip().lower(), emotion)
    if emotion in VALID_EMOTIONS and not (
            emotion == "whisper" and model not in WHISPER_ONLY_MODELS):
        voice_setting["emotion"] = emotion
    return {
        "model": model,
        "text": text,
        "stream": False,
        "language_boost": language_boost,
        "output_format": "hex",
        "voice_setting": voice_setting,
        "audio_setting": {
            "sample_rate": sample_rate,
            "bitrate": bitrate,
            "format": "mp3",
            "channel": channel,
        },
    }


def call_api(payload, api_key, retries, timeout):
    """Call Minimax. Retry on 429/5xx/network errors. Return the JSON dict or raise RuntimeError."""
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    headers = {"Authorization": "Bearer " + api_key, "Content-Type": "application/json"}
    last_err = None
    for attempt in range(1, retries + 2):
        try:
            req = urllib.request.Request(API_URL, data=body, headers=headers)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            detail = e.read().decode(errors="replace")[:500]
            last_err = "HTTP %s: %s" % (e.code, detail)
            if not (e.code == 429 or 500 <= e.code < 600):
                raise RuntimeError(last_err)
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            last_err = "network: %s" % e
        if attempt <= retries:
            backoff = 2 ** (attempt - 1)
            print("  (attempt %d failed: %s — retrying in %ds)"
                  % (attempt, last_err, backoff), file=sys.stderr)
            time.sleep(backoff)
    raise RuntimeError(last_err or "unknown failure")


def extract_audio(data):
    """Return the decoded MP3 bytes from `data.audio` (hex), or raise RuntimeError."""
    base = (data or {}).get("base_resp") or {}
    if base.get("status_code") not in (0, None):
        raise RuntimeError("API Minimax: %s (%s)"
                           % (base.get("status_msg", "?"), base.get("status_code")))
    audio_hex = ((data or {}).get("data") or {}).get("audio")
    if not audio_hex:
        raise RuntimeError("no audio returned. Response: %s"
                           % json.dumps(data, ensure_ascii=False)[:400])
    try:
        return bytes.fromhex(audio_hex)
    except ValueError as e:
        raise RuntimeError("unreadable audio hex: %s" % e)


def synthesize(text, api_key, *, model=DEFAULT_MODEL, voice=DEFAULT_VOICE, emotion="calm",
               speed=1.0, vol=1.0, pitch=0, sample_rate=32000, bitrate=128000,
               channel=1, language_boost="French", retries=2, timeout=120):
    """Generate audio. Return MP3 bytes. Raise RuntimeError on failure.
    Reusable by the tts_render.py orchestrator (no duplicated call logic)."""
    if os.environ.get("MGM_TTS_MOCK"):
        # Dummy duration ~ proportional to text length (for tests).
        return _MOCK_MP3_FRAME * max(1, min(50, len(text) // 40))
    payload = build_payload(text, model, voice, emotion, speed, vol, pitch,
                            sample_rate, bitrate, channel, language_boost)
    data = call_api(payload, api_key, retries, timeout)
    return extract_audio(data)


def write_metadata(meta_path, base_meta_json, model, voice, emotion, text, nbytes):
    meta = {}
    if base_meta_json:
        try:
            meta = json.loads(base_meta_json)
        except json.JSONDecodeError as e:
            die("--meta-json invalid: %s" % e, 2)
    meta.update({
        "model": model,
        "voice": voice,
        "emotion": emotion,
        "text": text,
        "bytes": nbytes,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "generator": "minimax-t2a-v2",
    })
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)
    return meta_path


def main():
    p = argparse.ArgumentParser(
        description="Text-to-speech via Minimax T2A v2 (MJ Tonnerre narrative voice).",
        formatter_class=argparse.RawDescriptionHelpFormatter, epilog=__doc__)
    p.add_argument("--list-voices", action="store_true",
                   help="Print the per-language voice/language_boost table and exit.")
    p.add_argument("--out", default=None, help="Output MP3 path (required unless --list-voices).")
    p.add_argument("--text-file", default="-",
                   help="Text file, or '-' for stdin (default: stdin).")
    p.add_argument("--model", default=DEFAULT_MODEL, help="Minimax model (default %s)." % DEFAULT_MODEL)
    p.add_argument("--voice", default=DEFAULT_VOICE, help="voice_id (default %s)." % DEFAULT_VOICE)
    p.add_argument("--emotion", default="calm",
                   help="Emotion: %s (default calm)." % " ".join(sorted(VALID_EMOTIONS)))
    p.add_argument("--speed", type=float, default=1.0, help="Speed [0.5, 2] (default 1.0).")
    p.add_argument("--vol", type=float, default=1.0, help="Volume (0, 10] (default 1.0).")
    p.add_argument("--pitch", type=int, default=0, help="Pitch [-12, 12] (default 0).")
    p.add_argument("--sample-rate", type=int, default=32000,
                   help="Sample rate (default 32000).")
    p.add_argument("--bitrate", type=int, default=128000, help="MP3 bitrate (default 128000).")
    p.add_argument("--channel", type=int, default=1, choices=(1, 2), help="1 mono / 2 stereo.")
    p.add_argument("--language-boost", default="French", help="Language bias (default French).")
    p.add_argument("--meta-json", default=None, help="Base metadata JSON (merged).")
    p.add_argument("--no-meta", action="store_true", help="Do not write the <out>.json sidecar.")
    p.add_argument("--retries", type=int, default=2, help="Transient retries (default 2).")
    p.add_argument("--timeout", type=int, default=120, help="HTTP timeout in s (default 120).")
    p.add_argument("--json", action="store_true", dest="as_json", help="Machine-readable output on stdout.")
    args = p.parse_args()

    # ── Guided selector: list known voices/boosts then exit ─────────────────
    if args.list_voices:
        print("Per-language MiniMax voice defaults (LANGUAGE_DEFAULTS table):")
        print("")
        print("  %-6s  %-32s  %-10s" % ("lang", "voice_id", "language_boost"))
        print("  " + "-" * 56)
        for lang, cfg in LANGUAGE_DEFAULTS.items():
            if lang == "_default":
                label = "(fallback)"
            else:
                label = lang
            print("  %-6s  %-32s  %-10s" % (label, cfg["voice"], cfg["language_boost"]))
        print("")
        print("To override for a campaign, set in world.json > meta.audio:")
        print('  "audio": { "voice": "<voice_id>", "language_boost": "<boost>" }')
        print("")
        print("To set the language (auto-selects voice), set world.json > meta.langue:")
        print('  "langue": "en"   (or "fr", etc.)')
        print("")
        print("Environment overrides: MGM_LANGUAGE or MGM_LANGUE (same codes).")
        sys.exit(0)

    if not args.out:
        die("--out is required (or use --list-voices).", 2)

    api_key = os.environ.get("MINIMAX_API_KEY")
    if not api_key and not os.environ.get("MGM_TTS_MOCK"):
        die("MINIMAX_API_KEY not set in the environment.", 2)

    if args.text_file == "-":
        text = sys.stdin.read().strip()
    else:
        try:
            with open(args.text_file, encoding="utf-8") as f:
                text = f.read().strip()
        except OSError as e:
            die("reading text file: %s" % e, 2)
    if not text:
        die("empty text.", 2)

    if args.sample_rate not in VALID_SAMPLE_RATES:
        die("sample_rate %s not supported (%s)."
            % (args.sample_rate, " ".join(map(str, sorted(VALID_SAMPLE_RATES)))), 2)
    if args.bitrate not in VALID_BITRATES:
        die("bitrate %s not supported (%s)."
            % (args.bitrate, " ".join(map(str, sorted(VALID_BITRATES)))), 2)

    try:
        audio = synthesize(
            text, api_key or "", model=args.model, voice=args.voice, emotion=args.emotion,
            speed=args.speed, vol=args.vol, pitch=args.pitch, sample_rate=args.sample_rate,
            bitrate=args.bitrate, channel=args.channel, language_boost=args.language_boost,
            retries=args.retries, timeout=args.timeout)
    except RuntimeError as e:
        die(str(e), 1)

    out_path = args.out
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    with open(out_path, "wb") as f:
        f.write(audio)

    meta_path = None
    if not args.no_meta:
        base = os.path.splitext(out_path)[0]
        meta_path = write_metadata(base + ".json", args.meta_json, args.model, args.voice,
                                   args.emotion, text, len(audio))

    if args.as_json:
        print(json.dumps({"ok": True, "audio": out_path, "meta": meta_path,
                          "model": args.model, "voice": args.voice, "emotion": args.emotion,
                          "bytes": len(audio)}))
    else:
        print("OK: %s (%d bytes, %s, %s, %s)"
              % (out_path, len(audio), args.model, args.voice, args.emotion))
    sys.exit(0)


if __name__ == "__main__":
    main()
