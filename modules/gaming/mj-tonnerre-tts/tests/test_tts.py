#!/usr/bin/env python3
"""
test_tts.py — Offline tests for the mj-tonnerre-tts module (stdlib only, no network).

Everything is mocked: MJ_TTS_MOCK (fake synthesis) + MJ_TTS_FORMAT_MOCK (format output).
Covers: format (mock + fallback + cleanup), generation (mp3 + usage codes),
orchestration (voice only, fail-open ambiance), last_narration retrieval.

Run: python3 modules/gaming/mj-tonnerre-tts/tests/test_tts.py
"""
import json
import os
import subprocess
import sys
import tempfile

SCRIPTS = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts"))
sys.path.insert(0, SCRIPTS)
import tts_format  # noqa: E402
import tts_generate  # noqa: E402
import tts_render  # noqa: E402

_OK = 0


def check(label, cond, detail=""):
    global _OK
    mark = "✅" if cond else "❌"
    print("  %s %s%s" % (mark, label, "" if cond else "  — %s" % detail))
    if cond:
        _OK += 1
    return cond


def run(script, args, stdin_text="", env=None):
    e = dict(os.environ)
    if env:
        e.update(env)
    p = subprocess.run([sys.executable, os.path.join(SCRIPTS, script)] + args,
                       input=stdin_text, capture_output=True, text=True, env=e, timeout=30)
    return p.returncode, p.stdout, p.stderr


def main():
    total = 0
    print("=== mj-tonnerre-tts : offline tests ===\n")

    # ── 1. tts_format : mock → normalised JSON ───────────────────────────────
    print("[1] tts_format — normalised mock output")
    os.environ["MJ_TTS_FORMAT_MOCK"] = json.dumps({
        "segments": [{"text": "La porte grince. <#0.8#> Tu avances.", "emotion": "fearful"}],
        "emotion": "fearful", "ambiance": "donjon", "moment_cle": True})
    out = tts_format.format_narration("Tu ouvres la porte.")
    total += 5
    check("segments exposed", out["segments"][0]["emotion"] == "fearful", str(out.get("segments")))
    check("script derived from segments", out["script"].startswith("La porte grince"), out["script"])
    check("valid emotion retained", out["emotion"] == "fearful")
    check("valid ambiance retained", out["ambiance"] == "donjon")
    check("moment_cle bool", out["moment_cle"] is True)

    # invalid values → clamped to defaults
    os.environ["MJ_TTS_FORMAT_MOCK"] = json.dumps({
        "segments": [{"text": "Texte.", "emotion": "euphorique"}],
        "emotion": "euphorique", "ambiance": "volcan", "moment_cle": "oui"})
    out = tts_format.format_narration("x")
    total += 2
    check("unknown emotion → calm", out["emotion"] == "calm")
    check("unknown ambiance → aucune", out["ambiance"] == "aucune")
    del os.environ["MJ_TTS_FORMAT_MOCK"]

    # ── 2. tts_format : fallback (no key, no mock) + cleanup ──────
    print("[2] tts_format — fail-open fallback + mechanical cleanup")
    env_nokey = dict(os.environ)
    env_nokey.pop("OPENROUTER_API_KEY", None)
    env_nokey.pop("MJ_TTS_FORMAT_API_KEY", None)
    saved = {k: os.environ.pop(k) for k in ("OPENROUTER_API_KEY", "MJ_TTS_FORMAT_API_KEY")
             if k in os.environ}
    out = tts_format.format_narration("Tu lances 1d20+3 et [FOR 14] ouvre la porte sombre.")
    total += 3
    check("fallback marked", out.get("_fallback") is True)
    check("dice removed", "1d20" not in out["script"], out["script"])
    check("bracket removed", "[FOR" not in out["script"], out["script"])
    os.environ.update(saved)

    # ── 3. tts_generate : mock → mp3 + usage codes ────────────────────────
    print("[3] tts_generate — mocked synthesis + exit codes")
    with tempfile.TemporaryDirectory() as d:
        out_mp3 = os.path.join(d, "v.mp3")
        rc, so, se = run("tts_generate.py", ["--out", out_mp3, "--json"],
                         stdin_text="Bonjour <#0.5#> aventurier.", env={"MJ_TTS_MOCK": "1"})
        total += 3
        check("exit 0 in mock", rc == 0, se[:120])
        check("mp3 written non-empty", os.path.isfile(out_mp3) and os.path.getsize(out_mp3) > 0)
        check("sidecar json written", os.path.isfile(os.path.join(d, "v.json")))

        # empty text → usage (exit 2), even in mock mode
        rc, _, _ = run("tts_generate.py", ["--out", os.path.join(d, "x.mp3")],
                       stdin_text="   ", env={"MJ_TTS_MOCK": "1"})
        total += 1
        check("empty text → exit 2", rc == 2)

        # no key and no mock → usage (exit 2)
        env_nokey = {"MINIMAX_API_KEY": "", "MJ_TTS_MOCK": ""}
        rc, _, _ = run("tts_generate.py", ["--out", os.path.join(d, "y.mp3")],
                       stdin_text="Texte.", env=env_nokey)
        total += 1
        check("no key / no mock → exit 2", rc == 2)

        # whisper guard: dropped for 2.8 (otherwise error 2013), kept for 2.6
        total += 2
        p28 = tts_generate.build_payload("Hé.", "speech-2.8-turbo", "v", "whisper",
                                         1.0, 1.0, 0, 32000, 128000, 1, "French")
        check("whisper removed on 2.8-turbo",
              "emotion" not in p28["voice_setting"])
        p26 = tts_generate.build_payload("Hé.", "speech-2.6-turbo", "v", "whisper",
                                         1.0, 1.0, 0, 32000, 128000, 1, "French")
        check("whisper kept on 2.6-turbo",
              p26["voice_setting"].get("emotion") == "whisper")

    # ── 4. tts_render : voice-only orchestration (ambiance fail-open) ───────
    print("[4] tts_render — voice only (no ambiance file → fail-open)")
    with tempfile.TemporaryDirectory() as d:
        out_mp3 = os.path.join(d, "r.mp3")
        env = {"MJ_TTS_MOCK": "1",
               "MJ_TTS_FORMAT_MOCK": json.dumps({
                   "script": "Un trône brisé. <#1.0#> Le silence.", "emotion": "surprised",
                   "ambiance": "donjon", "moment_cle": True})}
        rc, so, se = run("tts_render.py", ["--out", out_mp3, "--json"],
                         stdin_text="Tu entres dans la grande salle du donjon abandonné.", env=env)
        total += 4
        check("exit 0", rc == 0, se[:160])
        rep = json.loads(so) if so.strip().startswith("{") else {}
        check("mp3 produced", os.path.isfile(out_mp3) and os.path.getsize(out_mp3) > 0)
        check("ambiance not mixed (no file)", rep.get("ambiance_mixee") is False)
        check("emotion propagated", rep.get("emotion") == "surprised", str(rep))

    # ── 4b. normalize_segments : structured array {text, emotion} ──────────
    print("[4b] tts_format.normalize_segments — segment array")
    segs = tts_format.normalize_segments(
        [{"text": "Un monstre !", "emotion": "surprised"},
         {"text": "La pierre tombe.", "emotion": "fearful"}], "calm")
    total += 5
    check("2 segments ordered", [s["emotion"] for s in segs] == ["surprised", "fearful"], str(segs))
    check("adjacent same emotion merged",
          len(tts_format.normalize_segments(
              [{"text": "A.", "emotion": "calm"}, {"text": "B.", "emotion": "calm"}], "calm")) == 1)
    check("invalid emotion → default", tts_format.normalize_segments(
        [{"text": "X.", "emotion": "bizarre"}], "sad")[0]["emotion"] == "sad")
    check("tag residue cleaned from text", "{" not in tts_format.normalize_segments(
        [{"text": "{calm}Salut{/calm}", "emotion": "calm"}], "calm")[0]["text"])
    # App alias "Neutral" → API value `calm`, in both segments AND synthesis.
    ali = tts_format.normalize_segments(
        [{"text": "Posé.", "emotion": "neutral"}, {"text": "Tendu.", "emotion": "fearful"}], "calm")
    check("emotion=neutral normalised to calm",
          [s["emotion"] for s in ali] == ["calm", "fearful"], str(ali))
    total += 1
    pn = tts_generate.build_payload("Hé.", "speech-2.8-turbo", "v", "neutral",
                                    1.0, 1.0, 0, 32000, 128000, 1, "French")
    check("emotion=neutral → API calm", pn["voice_setting"].get("emotion") == "calm", str(pn))

    # ── 4c. segmented render: 1 Minimax call per segment, concat (simulated ffmpeg) ──
    print("[4c] tts_render — multi-emotion voice (segmented)")
    with tempfile.TemporaryDirectory() as d:
        out_mp3 = os.path.join(d, "seg.mp3")
        calls = []
        real_synth = tts_render.tts_generate.synthesize
        real_ff = tts_render._ffmpeg
        real_concat = tts_render._concat_mp3
        try:
            def spy(text, key, **kw):
                calls.append((kw.get("emotion"), text))
                return real_synth(text, key, **kw)
            tts_render.tts_generate.synthesize = spy
            tts_render._ffmpeg = lambda: "/usr/bin/ffmpeg"
            tts_render._concat_mp3 = lambda ff, paths, out, bitrate=128000: (
                open(out, "wb").write(b"".join(open(p, "rb").read() for p in paths)) or True)
            os.environ["MJ_TTS_MOCK"] = "1"
            os.environ["MJ_TTS_FORMAT_MOCK"] = json.dumps({
                "segments": [{"text": "Un monstre !", "emotion": "surprised"},
                             {"text": "La pierre tombe.", "emotion": "fearful"}],
                "emotion": "fearful", "ambiance": "aucune", "moment_cle": False})
            rep = tts_render.render("Un monstre surgit, la pierre tombe sur toi.", out_mp3)
            total += 4
            check("segmented=True, 2 segments", rep.get("segmente") and rep.get("segments") == 2, str(rep))
            check("emotions per segment", rep.get("emotions") == ["surprised", "fearful"], str(rep))
            check("1 Minimax call per segment, correct emotion",
                  [e for e, _ in calls] == ["surprised", "fearful"], str(calls))
            check("clean text sent to Minimax", all("{" not in t for _, t in calls), str(calls))
        finally:
            tts_render.tts_generate.synthesize = real_synth
            tts_render._ffmpeg = real_ff
            tts_render._concat_mp3 = real_concat
            os.environ.pop("MJ_TTS_FORMAT_MOCK", None)

    # ── 5. last_narration : snapshot first, then CSV fallback ─────────────────────────
    print("[5] last_narration — snapshot first, CSV fallback")
    with tempfile.TemporaryDirectory() as d:
        bq = os.path.join(d, ".banquier")
        os.makedirs(bq)
        with open(os.path.join(bq, "snap-s1.json"), "w", encoding="utf-8") as f:
            json.dump({"last_narration": "La forêt murmure autour de toi."}, f)
        rc, so, _ = run("last_narration.py", [d])
        total += 2
        check("snapshot returned (exit 0)", rc == 0 and "forêt murmure" in so, so[:80])

        # empty campaign → exit 1
        with tempfile.TemporaryDirectory() as d2:
            rc, _, _ = run("last_narration.py", [d2])
            check("no narration → exit 1", rc == 1)

    print("\n" + "=" * 56)
    print("RESULT: %d/%d tests OK" % (_OK, total))
    return 0 if _OK == total else 1


if __name__ == "__main__":
    sys.exit(main())
