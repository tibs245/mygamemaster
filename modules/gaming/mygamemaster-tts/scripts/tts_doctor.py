#!/usr/bin/env python3
"""
tts_doctor.py — the one command that answers "why is there no voice?".

The narrative voice failed for three sessions of real play and was then switched
off for good, because nothing anywhere could say WHY it was silent: the axis, the
opt-in, the API key, the length threshold and the generation budget all produce
the same observable — no audio. This script reports the five of them at once,
plus what the hook itself actually recorded during play, plus a real end-to-end
render, and names the first thing that would keep the game silent.

It reads the SAME resolution code as the runtime (`hooks/_lib.py`), so it cannot
disagree with the hook about whether the axis is on.

Usage:
  python3 tts_doctor.py [CAMPAIGN_DIR]        # defaults to cwd; renders if a key is set
  python3 tts_doctor.py . --mock              # no key, no cost, no network
  python3 tts_doctor.py . --no-render --json  # machine output for a report

Exit codes:
  0  nothing found that would silence the game
  1  a defect was found (it is printed, and the fix with it)
  2  usage error (campaign directory unreadable)
"""
import argparse
import glob
import json
import os
import shutil
import subprocess
import sys
import tempfile

SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
HOOKS_DIR = os.path.normpath(os.path.join(SCRIPTS_DIR, "..", "..", "mygamemaster", "hooks"))
RENDERER = os.path.join(SCRIPTS_DIR, "tts_render.py")
SAMPLE = ("The mist thickens over the black water. Somewhere behind you, a stone "
          "rolls and stops. You hold your breath, and the silence answers.")

sys.path.insert(0, HOOKS_DIR)
try:
    import _lib as L
except Exception:  # pragma: no cover - the TTS module must stay usable alone
    L = None


def _mask(value):
    if not value:
        return "absent"
    return "present (%d chars, …%s)" % (len(value), value[-4:])


def _line(label, value, flag=" "):
    print("  %s %-34s %s" % (flag, label, value))


def axis_state(camp):
    """Axis `tts` and toggle `tts_auto`, resolved exactly as the hook resolves them."""
    if L is None:
        return {"error": "hooks/_lib.py not importable — cannot resolve the axis"}
    monde = L.load_monde(L.campaign_dir({"cwd": camp}))
    cfg = L.hooks_cfg(monde)
    return {
        "tts": bool(cfg["features"].get("tts", True)),
        "tts_auto": bool(cfg["tts_auto"]),
        "world_tts": ((monde.get("meta") or {}).get("features") or {}).get("tts"),
        "world_tts_auto": ((monde.get("meta") or {}).get("hooks") or {}).get("tts_auto"),
        "env_feature_tts": os.environ.get("MGM_FEATURE_TTS"),
        "env_tts_auto": os.environ.get("MGM_TTS_AUTO"),
    }


def journal(camp):
    """What the hook itself recorded during play (.banquier/tts-status.json).

    This is the only honest source on the HOOK's environment: the shell you run
    this doctor from is not the environment the hook subprocess ran in, and that
    difference is the most plausible single cause of a voice that "works when I
    test it" and never works in play."""
    if L is None:
        return {}
    return L.tts_status(camp)


def artefacts(camp):
    """Audit .banquier/tts: who actually produced the audio sitting there.

    A file with no sidecar was written by something that is not this module —
    typically the runtime's own built-in tts_tool, which uses a different engine
    (Edge TTS) and lands on the same `raconte_*.mp3` naming. That substitution
    went unnoticed for a whole campaign and was mistaken for a degraded MiniMax."""
    d = os.path.join(str(camp), ".banquier", "tts")
    out = {"dir": d, "mp3": 0, "ours": 0, "foreign": 0, "by_producer": {}, "examples": []}
    if not os.path.isdir(d):
        return out
    for mp3 in sorted(glob.glob(os.path.join(d, "*.mp3"))):
        if mp3.endswith(".voice.mp3"):
            continue
        out["mp3"] += 1
        meta = None
        try:
            with open(os.path.splitext(mp3)[0] + ".json", encoding="utf-8") as f:
                meta = json.load(f)
        except (OSError, ValueError):
            meta = None
        if isinstance(meta, dict) and str(meta.get("generator", "")).startswith("mygamemaster-tts"):
            who = meta.get("producer") or "unrecorded"
            out["ours"] += 1
        else:
            who = "FOREIGN (no sidecar)"
            out["foreign"] += 1
            if len(out["examples"]) < 3:
                out["examples"].append(os.path.basename(mp3))
        out["by_producer"][who] = out["by_producer"].get(who, 0) + 1
    return out


def end_to_end(camp, mock=False):
    """Really render a short narration through the normal path."""
    env = dict(os.environ)
    if mock:
        env["MGM_TTS_MOCK"] = "1"
    env["MGM_TTS_PRODUCER"] = "doctor"
    with tempfile.TemporaryDirectory(prefix="mjtts_doctor_") as td:
        out = os.path.join(td, "doctor.mp3")
        try:
            r = subprocess.run(
                [sys.executable, RENDERER, "--out", out, "--json", "--producer", "doctor",
                 "--campaign-dir", str(camp), "--retries", "1", "--timeout", "60"],
                input=SAMPLE.encode("utf-8"), env=env,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=120)
        except subprocess.TimeoutExpired:
            return {"ok": False, "reason": "timeout", "stderr": "no answer in 120 s"}
        except Exception as e:
            return {"ok": False, "reason": "spawn_error", "stderr": str(e)}
        err = (r.stderr or b"").decode("utf-8", "replace").strip()
        if r.returncode != 0:
            return {"ok": False, "reason": "exit_%d" % r.returncode, "stderr": err[-300:]}
        rep = {}
        try:
            rep = json.loads((r.stdout or b"").decode("utf-8", "replace"))
        except ValueError:
            pass
        return {"ok": True, "bytes": rep.get("bytes"), "voice": rep.get("voice"),
                "model": rep.get("model"), "mock": bool(mock)}


def main():
    p = argparse.ArgumentParser(description="Diagnose the MJ Tonnerre narrative voice.",
                                epilog=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("campaign", nargs="?", default=".", help="Campaign directory (default: cwd).")
    p.add_argument("--mock", action="store_true", help="Render with MGM_TTS_MOCK=1 (no key, no cost).")
    p.add_argument("--no-render", action="store_true", help="Skip the end-to-end render.")
    p.add_argument("--json", action="store_true", dest="as_json", help="Machine output.")
    args = p.parse_args()

    camp = os.path.abspath(args.campaign)
    if not os.path.isdir(camp):
        print("ERROR: not a directory: %s" % camp, file=sys.stderr)
        sys.exit(2)

    key = os.environ.get("MINIMAX_API_KEY", "")
    rep = {
        "campaign": camp,
        "axis": axis_state(camp),
        "key": {"this_shell": bool(key), "renderer": os.path.isfile(RENDERER),
                "openrouter": bool(os.environ.get("OPENROUTER_API_KEY")),
                "ffmpeg": bool(shutil.which("ffmpeg"))},
        "thresholds": {
            "MGM_TTS_MIN_CHARS": os.environ.get("MGM_TTS_MIN_CHARS", "280 (default)"),
            "MGM_TTS_TIMEOUT": os.environ.get("MGM_TTS_TIMEOUT", "40 (default)"),
            "MGM_TTS_SEGMENT": os.environ.get("MGM_TTS_SEGMENT", "1 (default)"),
        },
        "journal": journal(camp),
        "artefacts": artefacts(camp),
    }
    rep["render"] = ({"skipped": "no key and no --mock"} if (not key and not args.mock)
                     else {"skipped": "--no-render"} if args.no_render
                     else end_to_end(camp, mock=args.mock))

    problems, notes = [], []
    ax = rep["axis"]
    if ax.get("error"):
        problems.append(ax["error"])
    elif not ax["tts"]:
        notes.append("axis `tts` is OFF: no voice at all, auto or `!raconte` "
                     "(`!feature tts on`, or meta.features.tts=true).")
    elif not ax["tts_auto"]:
        notes.append("auto-voice is OFF — this is the DEFAULT, not a fault. "
                     "`!raconte` still works. Opt in with MGM_TTS_AUTO=1 or "
                     "meta.hooks.tts_auto=true in world.json.")
    if not rep["key"]["renderer"]:
        problems.append("renderer missing: %s" % RENDERER)
    if not key:
        (problems if ax.get("tts") else notes).append(
            "MINIMAX_API_KEY absent from THIS shell — nothing can be generated, auto or "
            "`!raconte`. An unconfigured voice says so; it does not pretend to be off.")
    last_fail = rep["journal"].get("last_failure")
    if last_fail:
        problems.append("the hook recorded a failure at %s: %s%s"
                        % (last_fail.get("ts"), last_fail.get("reason"),
                           "" if last_fail.get("key", True) else
                           " (and the HOOK's own environment had no MINIMAX_API_KEY — "
                           "the key must be exported to the runtime, not just to your shell)"))
    if not rep["journal"]:
        notes.append("the hook has never recorded an auto-voice decision here: it never "
                     "ran on this campaign, or this deployment predates the journal.")
    if isinstance(rep["render"], dict) and rep["render"].get("ok") is False:
        problems.append("end-to-end render FAILED (%s): %s"
                        % (rep["render"].get("reason"), rep["render"].get("stderr", "")))
    if rep["artefacts"]["foreign"]:
        problems.append(
            "%d audio file(s) in %s were NOT produced by this module (no sidecar) — another "
            "engine is writing there; check whether the model is calling the runtime's "
            "built-in tts_tool instead of tts_render.py. Examples: %s"
            % (rep["artefacts"]["foreign"], rep["artefacts"]["dir"],
               ", ".join(rep["artefacts"]["examples"])))
    rep["verdict"] = {"ok": not problems, "problems": problems, "notes": notes}

    if args.as_json:
        print(json.dumps(rep, ensure_ascii=False, indent=2))
        sys.exit(0 if not problems else 1)

    print("=== MJ Tonnerre — narrative voice doctor ===")
    print("campaign: %s\n" % camp)
    print("[1] axis & opt-in")
    _line("features.tts", "ON" if ax.get("tts") else "OFF", " " if ax.get("tts") else "!")
    _line("hooks.tts_auto (auto-voice)", "ON" if ax.get("tts_auto") else "OFF (opt-in)")
    _line("  world.json meta.hooks.tts_auto", ax.get("world_tts_auto"))
    _line("  env MGM_TTS_AUTO", ax.get("env_tts_auto") or "unset")
    print("\n[2] credentials")
    _line("MINIMAX_API_KEY (this shell)", _mask(key), " " if key else "!")
    hook_key = (rep["journal"].get("last") or {}).get("key")
    _line("MINIMAX_API_KEY (hook env)",
          "unknown — never observed" if hook_key is None
          else ("present at %s" % (rep["journal"].get("last") or {}).get("ts") if hook_key
                else "ABSENT at %s" % (rep["journal"].get("last") or {}).get("ts")),
          " " if hook_key in (None, True) else "!")
    _line("OPENROUTER_API_KEY (format step)",
          "present" if rep["key"]["openrouter"] else "absent (fail-open: flat voice script)")
    _line("ffmpeg (ambiance + segments)", "found" if rep["key"]["ffmpeg"] else "absent (fail-open)")
    print("\n[3] thresholds in effect")
    for k, v in rep["thresholds"].items():
        _line(k, v)
    print("\n[4] what the hook recorded (%s)"
          % os.path.join(camp, ".banquier", "tts-status.json"))
    counts = rep["journal"].get("counts") or {}
    _line("outcomes", ", ".join("%s=%d" % kv for kv in sorted(counts.items())) or "(nothing yet)")
    if rep["journal"].get("last"):
        _line("last", json.dumps(rep["journal"]["last"], ensure_ascii=False)[:200])
    if last_fail:
        _line("last FAILURE", json.dumps(last_fail, ensure_ascii=False)[:200], "!")
    print("\n[5] audio artefacts")
    _line("mp3 in .banquier/tts", rep["artefacts"]["mp3"])
    _line("produced by this module", rep["artefacts"]["ours"])
    _line("produced by something else", rep["artefacts"]["foreign"],
          "!" if rep["artefacts"]["foreign"] else " ")
    for who, n in sorted(rep["artefacts"]["by_producer"].items()):
        _line("  producer=%s" % who, n)
    print("\n[6] end-to-end render")
    _line("result", json.dumps(rep["render"], ensure_ascii=False)[:300],
          "!" if rep["render"].get("ok") is False else " ")
    print("\n=== verdict ===")
    for n in notes:
        print("  · %s" % n)
    for pb in problems:
        print("  ✗ %s" % pb)
    if not problems:
        print("  ✓ nothing found that would silence the game.")
    sys.exit(0 if not problems else 1)


if __name__ == "__main__":
    main()
