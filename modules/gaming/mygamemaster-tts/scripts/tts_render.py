#!/usr/bin/env python3
"""
tts_render.py — Orchestrator of the narrative voice (the NORMAL PATH of the module).

Chains, in a single call, the full quality pipeline — without loading the GM model:
  1. tts_format.format_narration  → vocal script (pauses <#x.x#>, tics preserved,
     mechanics removed) + metadata (emotion, ambiance, key-moment) ;
  2. tts_generate.synthesize      → MP3 voice (Minimax speech-2.8-turbo,
     French_Female_Speech_New). The formatter provides SEGMENTS [{text, emotion}]:
     if >1 → MULTI-EMOTION VOICE (one Minimax clip per segment, own emotion, concatenated
     via ffmpeg). Otherwise: a single mono-emotion call. Emotion is an API PARAMETER per
     call, never a tag in the text. Disabled via MGM_TTS_SEGMENT=0; fallback to mono-call
     if ffmpeg absent (fail-open);
  3. AMBIANCE mixing (ffmpeg, optional): if key-moment OR long narration, and a
     sound bed matches the proposed ambiance → it is slid UNDER the voice (low volume).
     Otherwise: voice only.
  4. sidecar `.json` (script, emotion, ambiance, model, ambiance mixed or not,
     and the PRODUCER that asked for it — cf. producer_name).

FAIL-OPEN everywhere: the format step falls back to the cleaned narration; ambiance
mixing is best-effort (ffmpeg/file absent → voice only); only the failure of
SYNTHESIS (no audio at all) returns exit 1. This code decides whether the auto-TTS
hook attaches a MEDIA: or not.

Usage:
  echo "<narration>" | python3 tts_render.py --out voix.mp3 --json
  python3 tts_render.py --text-file n.txt --out voix.mp3 --no-ambiance

Exit codes:
  0  audio produced (voice only or voice+ambiance) — path in `audio`/`OK:`
  1  synthesis failure (no audio) — caller fail-open (no MEDIA:)
  2  usage error (empty text, invalid argument)

Test modes: MGM_TTS_MOCK=1 (mock synthesis) + MGM_TTS_FORMAT_MOCK=<json> (format).
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tts_format  # noqa: E402
import tts_generate  # noqa: E402

SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_AMBIANCE_DIR = os.path.join(os.path.dirname(SCRIPTS_DIR), "ambiances")
# Volume of the ambiance bed under the voice (the voice stays in the foreground, non-negotiable).
AMBIANCE_VOLUME = float(os.environ.get("MGM_TTS_AMBIANCE_VOLUME", "0.16"))
# Beyond this number of characters, a narration justifies an ambiance even without a key-moment.
DEFAULT_THRESHOLD_CHARS = 320


def _load_monde_json(campaign_dir=None):
    """Load world.json from the campaign directory (or cwd). Returns {} on failure (fail-open)."""
    candidates = []
    if campaign_dir:
        candidates.append(os.path.join(campaign_dir, "world.json"))
    candidates.append(os.path.join(os.getcwd(), "world.json"))
    for path in candidates:
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        except (OSError, json.JSONDecodeError):
            continue
    return {}


def resolve_voice_and_boost(monde=None, explicit_voice=None, explicit_boost=None,
                             campaign_dir=None):
    """Determine the voice_id and language_boost to use for this render call.

    Priority (highest wins):
    1. Caller-supplied explicit_voice / explicit_boost (CLI flags --voice/--language-boost).
    2. world.json > meta.audio.voice / meta.audio.language_boost (campaign override).
    3. Per-language default from ``tts_generate.voice_for_language()`` using
       world.json > meta.langue (or env MGM_LANGUAGE / MGM_LANGUE).
    4. Built-in default (French_Female_Speech_New / "French").

    Always fail-open: missing keys, bad JSON, unknown language → next level.
    """
    # -- level 1: explicit caller override (CLI) ---------------------------------
    if explicit_voice and explicit_boost:
        return explicit_voice, explicit_boost

    # -- load world.json once (cheap; fail-open) ----------------------------------
    if monde is None:
        monde = _load_monde_json(campaign_dir)
    audio_cfg = (monde.get("meta") or {}).get("audio") or {}

    # -- level 2: campaign audio config in world.json ----------------------------
    camp_voice = audio_cfg.get("voice") or None
    camp_boost = audio_cfg.get("language_boost") or None
    if explicit_voice:
        camp_voice = explicit_voice   # CLI flag still wins for voice
    if explicit_boost:
        camp_boost = explicit_boost

    # -- level 3: language-based default -----------------------------------------
    lang = (
        (monde.get("meta") or {}).get("langue")
        or os.environ.get("MGM_LANGUAGE")
        or os.environ.get("MGM_LANGUE")
        or ""
    )
    default_voice, default_boost = tts_generate.voice_for_language(lang)

    voice = camp_voice or default_voice
    boost = camp_boost or default_boost
    return voice, boost


def die(msg, code):
    print("ERROR: %s" % msg, file=sys.stderr)
    sys.exit(code)


def _ffmpeg():
    return shutil.which("ffmpeg")


def _segment_enabled():
    """Multi-emotion voice by segments. ON by default; disabled via MGM_TTS_SEGMENT=0."""
    return os.environ.get("MGM_TTS_SEGMENT", "1").strip().lower() not in (
        "0", "false", "off", "no", "non")


def _concat_mp3(ff, paths, out_path, bitrate=128000):
    """Concatenates MP3 clips (in order) into one, via the ffmpeg concat demuxer.
    Re-encodes (libmp3lame) to avoid join glitches. True if OK."""
    listfile = out_path + ".txt"
    with open(listfile, "w", encoding="utf-8") as f:
        for p in paths:
            f.write("file '%s'\n" % os.path.abspath(p).replace("'", "'\\''"))
    cmd = [ff, "-y", "-f", "concat", "-safe", "0", "-i", listfile,
           "-c:a", "libmp3lame", "-b:a", "%dk" % (bitrate // 1000), out_path]
    try:
        r = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, timeout=120)
    except (OSError, subprocess.TimeoutExpired):
        return False
    return r.returncode == 0 and os.path.isfile(out_path) and os.path.getsize(out_path) > 0


def _synthesize_segmented(segments, api_key, *, model, voice, language_boost="French",
                          retries, timeout):
    """Synthesizes EACH segment with its own emotion, then concatenates into a single MP3.
    Returns (audio_bytes, [emotions]). Raises RuntimeError if a segment or the concat
    fails (the caller then falls back to mono-call = fail-open)."""
    ff = _ffmpeg()
    if not ff:
        raise RuntimeError("ffmpeg absent (segmentation impossible)")
    with tempfile.TemporaryDirectory(prefix="mjtts_") as td:
        paths, emotions = [], []
        for i, seg in enumerate(segments):
            clip = tts_generate.synthesize(
                seg["text"], api_key, model=model, voice=voice, emotion=seg["emotion"],
                language_boost=language_boost,
                retries=retries, timeout=timeout)  # RuntimeError → mono fallback upstream
            p = os.path.join(td, "seg%02d.mp3" % i)
            with open(p, "wb") as f:
                f.write(clip)
            paths.append(p)
            emotions.append(seg["emotion"])
        joined = os.path.join(td, "joined.mp3")
        if not _concat_mp3(ff, paths, joined):
            raise RuntimeError("concat ffmpeg KO")
        with open(joined, "rb") as f:
            return f.read(), emotions


def _ambiance_file(tag, ambiance_dir):
    if not tag or tag == "aucune":
        return None
    path = os.path.join(ambiance_dir, "%s.mp3" % tag)
    return path if os.path.isfile(path) else None


def mix_ambiance(voice_path, ambiance_path, out_path, bitrate=128000):
    """Slides the ambiance (looped, low volume) UNDER the voice. Duration follows the voice.
    Returns True if mixing succeeded, False otherwise (caller keeps voice only)."""
    ff = _ffmpeg()
    if not ff:
        return False
    filt = ("[1:a]volume=%s[bg];[0:a][bg]amix=inputs=2:duration=first:"
            "dropout_transition=0[a]" % AMBIANCE_VOLUME)
    cmd = [ff, "-y", "-i", voice_path, "-stream_loop", "-1", "-i", ambiance_path,
           "-filter_complex", filt, "-map", "[a]",
           "-c:a", "libmp3lame", "-b:a", "%dk" % (bitrate // 1000), out_path]
    try:
        r = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, timeout=60)
    except (OSError, subprocess.TimeoutExpired):
        return False
    return r.returncode == 0 and os.path.isfile(out_path) and os.path.getsize(out_path) > 0


def producer_name(explicit=None):
    """Who asked for this audio: 'manual' (!raconte), 'hook-auto', or a caller tag.

    Both paths write `.mp3` into the same `.banquier/tts/` directory, and a third
    engine (the runtime's own built-in tts_tool) has been observed writing there
    too, under a colliding name. Stamping the producer into the sidecar makes
    "who generated this audio" an answerable question — it was not, and ~32 files
    of a 40-file corpus turned out to come from an engine nobody had chosen."""
    return explicit or os.environ.get("MGM_TTS_PRODUCER") or "manual"


def render(text, out_path, *, voice=None, model=tts_generate.DEFAULT_MODEL,
           ambiance_dir=DEFAULT_AMBIANCE_DIR, allow_ambiance=True,
           threshold_chars=DEFAULT_THRESHOLD_CHARS, retries=2, timeout=120,
           format_model=None, language_boost=None, campaign_dir=None,
           producer=None):
    """Full pipeline. Returns a report dict. Raises RuntimeError on synthesis failure.

    ``voice`` and ``language_boost`` are resolved via ``resolve_voice_and_boost()``:
    explicit args > world.json meta.audio > per-language default > built-in default.
    Pass ``campaign_dir`` to read world.json from a specific path (defaults to cwd).
    """
    voice, language_boost = resolve_voice_and_boost(
        explicit_voice=voice, explicit_boost=language_boost, campaign_dir=campaign_dir)
    fmt = tts_format.format_narration(text, model=format_model)
    script = fmt["script"]
    emotion = fmt["emotion"]
    ambiance = fmt["ambiance"]
    moment_cle = fmt["moment_cle"]

    api_key = os.environ.get("MINIMAX_API_KEY", "")
    # The formatter provides the segments [{text, emotion}] directly (already cleaned).
    segments = fmt.get("segments") or []
    # Clean mono text for the mono-call fallback (concatenation of segment texts).
    clean_text = " ".join(s["text"] for s in segments) or tts_format.strip_emotion_tags(script)

    audio, seg_emotions, segmented = None, [emotion], False
    if _segment_enabled() and len(segments) > 1 and _ffmpeg():
        try:
            audio, seg_emotions = _synthesize_segmented(
                segments, api_key, model=model, voice=voice, language_boost=language_boost,
                retries=retries, timeout=timeout)
            segmented = True
        except RuntimeError:
            audio = None  # fallback to mono-call below (fail-open)
    if audio is None:
        audio = tts_generate.synthesize(
            clean_text, api_key, model=model, voice=voice, emotion=emotion,
            language_boost=language_boost,
            retries=retries, timeout=timeout)  # raises RuntimeError → exit 1 upstream
        seg_emotions = [emotion]

    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)

    # Decide on ambiance: explicitly requested, real tag, and (key-moment OR long narration).
    want_ambiance = (allow_ambiance and ambiance != "aucune"
                     and (moment_cle or len(text) >= threshold_chars))
    amb_path = _ambiance_file(ambiance, ambiance_dir) if want_ambiance else None
    ambiance_mixed = False

    if amb_path:
        voice_tmp = out_path + ".voice.mp3"
        with open(voice_tmp, "wb") as f:
            f.write(audio)
        ambiance_mixed = mix_ambiance(voice_tmp, amb_path, out_path)
        if ambiance_mixed:
            try:
                os.remove(voice_tmp)
            except OSError:
                pass
        else:
            # Mixing unavailable (no ffmpeg / failure) → keep voice only.
            os.replace(voice_tmp, out_path)
    else:
        with open(out_path, "wb") as f:
            f.write(audio)

    report = {
        "ok": True,
        "audio": out_path,
        "emotion": emotion,
        "segmente": segmented,
        "segments": len(seg_emotions) if segmented else 1,
        "emotions": seg_emotions,
        "ambiance": ambiance if ambiance_mixed else "aucune",
        "ambiance_demandee": ambiance,
        "ambiance_mixee": ambiance_mixed,
        "moment_cle": moment_cle,
        "fallback_format": bool(fmt.get("_fallback")),
        "model": model,
        "voice": voice,
        "language_boost": language_boost,
        "bytes": os.path.getsize(out_path),
        "producer": producer_name(producer),
        "script": script,
    }
    return report


def write_sidecar(out_path, report):
    base = os.path.splitext(out_path)[0]
    meta = dict(report)
    meta["generated_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    meta["generator"] = "mygamemaster-tts/render"
    meta.setdefault("producer", producer_name())
    with open(base + ".json", "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)
    return base + ".json"


def main():
    p = argparse.ArgumentParser(
        description="MJ Tonnerre narrative voice: format → synthesis → ambiance (normal path).",
        formatter_class=argparse.RawDescriptionHelpFormatter, epilog=__doc__)
    p.add_argument("--out", required=True, help="Path to the final MP3 file.")
    p.add_argument("--text-file", default="-", help="Text file, or '-' for stdin (default).")
    p.add_argument("--voice", default=None,
                   help="voice_id Minimax (default: resolved from langue/world.json).")
    p.add_argument("--language-boost", default=None,
                   help="Minimax language_boost (default: resolved from langue/world.json).")
    p.add_argument("--model", default=tts_generate.DEFAULT_MODEL, help="Minimax TTS model.")
    p.add_argument("--format-model", default=None,
                   help="Format-step model (default: env MGM_TTS_FORMAT_MODEL / minimax-m3).")
    p.add_argument("--ambiance-dir", default=DEFAULT_AMBIANCE_DIR, help="Directory of sound beds.")
    p.add_argument("--no-ambiance", action="store_true", help="Disable ambiance mixing.")
    p.add_argument("--threshold-chars", type=int, default=DEFAULT_THRESHOLD_CHARS,
                   help="Minimum length (characters) for ambiance outside a key moment.")
    p.add_argument("--no-meta", action="store_true", help="Do not write the sidecar <out>.json.")
    p.add_argument("--retries", type=int, default=2, help="Transient retries (default 2).")
    p.add_argument("--timeout", type=int, default=120, help="Synthesis timeout in s (default 120).")
    p.add_argument("--campaign-dir", default=None,
                   help="Campaign directory (to read world.json from). Defaults to cwd.")
    p.add_argument("--producer", default=None,
                   help="Caller tag stamped in the sidecar (default: env MGM_TTS_PRODUCER "
                        "or 'manual'). The auto hook passes 'hook-auto'.")
    p.add_argument("--json", action="store_true", dest="as_json", help="Machine output on stdout.")
    args = p.parse_args()

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

    if not os.environ.get("MINIMAX_API_KEY") and not os.environ.get("MGM_TTS_MOCK"):
        die("MINIMAX_API_KEY not set (voice disabled).", 2)

    try:
        report = render(
            text, args.out, voice=args.voice, model=args.model,
            ambiance_dir=args.ambiance_dir, allow_ambiance=not args.no_ambiance,
            threshold_chars=args.threshold_chars, retries=args.retries, timeout=args.timeout,
            format_model=args.format_model, language_boost=args.language_boost,
            campaign_dir=args.campaign_dir, producer=args.producer)
    except RuntimeError as e:
        die(str(e), 1)

    meta_path = None if args.no_meta else write_sidecar(args.out, report)

    if args.as_json:
        out = dict(report)
        out["meta"] = meta_path
        out.pop("script", None)  # bulky script: excluded from machine stdout
        print(json.dumps(out, ensure_ascii=False))
    else:
        amb = ("voice+ambiance(%s)" % report["ambiance"]) if report["ambiance_mixee"] else "voice only"
        emo = ("%d segments: %s" % (report["segments"], "→".join(report["emotions"]))
               if report["segmente"] else report["emotion"])
        print("OK: %s (%d bytes, %s, %s, %s)"
              % (report["audio"], report["bytes"], emo, amb, report["model"]))
    sys.exit(0)


if __name__ == "__main__":
    main()
