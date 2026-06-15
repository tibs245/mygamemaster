#!/usr/bin/env python3
"""
test_hooks.py — Out-of-container tests for MJ Tonnerre runtime hooks.

Runs each hook as a subprocess (real contract: stdin JSON → stdout JSON) against
a temporary campaign fixture. No external dependencies.

Usage :  python3 test_hooks.py
Output:  list of PASS/FAIL ; exit 0 if all pass, 1 otherwise.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile

HOOKS_DIR = os.path.dirname(os.path.abspath(__file__))
PY = sys.executable

_results = []


def check(name, cond, detail=""):
    _results.append((name, bool(cond), detail))
    print(("  ✅ " if cond else "  ❌ ") + name + (("  — " + detail) if detail and not cond else ""))


def run_hook(script, payload, env=None):
    """Runs a hook (JSON payload on stdin), returns (output_dict, stderr)."""
    e = dict(os.environ)
    if env:
        e.update(env)
    proc = subprocess.run(
        [PY, os.path.join(HOOKS_DIR, script)],
        input=json.dumps(payload),
        capture_output=True, text=True, timeout=30, env=e,
    )
    out = {}
    if proc.stdout.strip():
        try:
            out = json.loads(proc.stdout)
        except Exception:
            out = {"__raw__": proc.stdout}
    return out, proc.stderr


def run_cli(script, args=None, stdin_text="", cwd=None, env=None):
    """Runs a CLI script (checkpoint/scoreboard), returns (stdout, returncode)."""
    e = dict(os.environ)
    if env:
        e.update(env)
    proc = subprocess.run(
        [PY, os.path.join(HOOKS_DIR, script)] + (args or []),
        input=stdin_text, capture_output=True, text=True, timeout=30, cwd=cwd, env=e,
    )
    return proc.stdout, proc.returncode


def write_json(path, obj):
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, ensure_ascii=False, indent=2)


def _pending_has_text(path):
    if not os.path.exists(path):
        return False
    try:
        return bool(json.load(open(path, encoding="utf-8")).get("text"))
    except Exception:
        return False


def build_fixture(root, strict=False, judge=False, auto_commit=False):
    camp = os.path.join(root, "campagne")
    os.makedirs(os.path.join(camp, "characters"), exist_ok=True)
    os.makedirs(os.path.join(camp, "sessions"), exist_ok=True)
    hooks_cfg = {"garde_json_strict": strict}
    # auto_commit=None → key absent (tests default on) ; bool → explicit key.
    if auto_commit is not None:
        hooks_cfg["auto_commit"] = auto_commit
    if judge:
        hooks_cfg["judge"] = {"actif": True, "modele": "test/mock", "gate_max_tentatives": 2}
    write_json(os.path.join(camp, "world.json"), {
        "meta": {
            "name": "Test",
            "time": {"regime": "Narratif"},
            "verbosity": "INFO",
            "admins": ["999000111"],
            "hooks": hooks_cfg,
            "diagnostic": {
                "actif": True, "fichier": "collecte.csv",
                "rules": {"echantillon_frequence": 1},
            },
        },
        "modules": {}, "global_state": {}, "universe": {"regions": []},
    })
    write_json(os.path.join(camp, "npcs.json"), [
        {"name": "Berthe", "established_facts": ["x"], "gm_hypotheses": []},
        {"name": "Firmin", "established_facts": ["y", "z"], "gm_hypotheses": []},
    ])
    write_json(os.path.join(camp, "characters", "403.json"), {
        "meta": {"character_name": "Rubis", "discord_id": "403"},
        "stats": {}, "inventory": ["saucisson", "corde", "lanterne"],
        "health": {"hp_current": 10, "hp_max": 10},
    })
    write_json(os.path.join(camp, "sessions", "009.json"), {
        "session": 9, "date": None, "participants": ["403"],
        "actions": [], "npcs_met": [], "visited_locations": [],
    })
    return camp


def main():
    root = tempfile.mkdtemp(prefix="mjt-hooks-")
    sid = "sess_test"
    try:
        camp = build_fixture(root)
        persoj = os.path.join(camp, "characters", "403.json")

        # ── 1. pre_llm_call : state injection ───────────────────────────────
        print("\n[1] pre_llm_call — state injection")
        out, err = run_hook("pre_llm_call.py", {
            "hook_event_name": "pre_llm_call", "cwd": camp, "session_id": sid,
            "message": "Rubis eats a sausage", "extra": {"model": "deepseek/x"},
        })
        ctx = out.get("context", "")
        check("context injected", "AUTHORITATIVE STATE" in ctx, ctx[:80])
        check("PC Rubis present in context", "Rubis" in ctx)
        check("real inventory exposed", "saucisson" in ctx)
        check("NPCs listed", "Berthe" in ctx and "Firmin" in ctx)

        # ── 2. pre_llm_call : bypass ⏸️ ─────────────────────────────────────
        print("\n[2] pre_llm_call — bypass ⏸️")
        out, _ = run_hook("pre_llm_call.py", {
            "cwd": camp, "session_id": "sess_bypass",
            "message": "⏸️ debug", "extra": {"model": "m"},
        })
        check("no context injected in bypass", out == {}, json.dumps(out)[:80])

        # ── 3. Full turn : snapshot → mutation → delta → report ─────────────
        print("\n[3] full turn — consuming an item")
        # pre_tool_call : snapshot (path only, no guard)
        run_hook("pre_tool_call.py", {
            "cwd": camp, "session_id": sid, "tool_name": "write_file",
            "tool_input": {"path": "characters/403.json"},
        })
        # real mutation : remove the saucisson (3 → 2 items)
        data = json.load(open(persoj, encoding="utf-8"))
        data["inventory"] = ["corde", "lanterne"]
        write_json(persoj, data)
        # post_tool_call : compute the delta
        run_hook("post_tool_call.py", {
            "cwd": camp, "session_id": sid, "tool_name": "write_file",
            "tool_input": {"path": "characters/403.json"},
        })
        # transform_llm_output : augments the response + CSV
        out, err = run_hook("transform_llm_output.py", {
            "cwd": camp, "session_id": sid,
            "response": "Rubis bites into the sausage.",
            "extra": {"model": "deepseek/x"},
        })
        check("INFO transaction → no-op (Persisted block internal, not shown to player)",
              out == {}, json.dumps(out)[:80])
        check("collecte.csv created", os.path.exists(os.path.join(camp, "collecte.csv")))
        if os.path.exists(os.path.join(camp, "collecte.csv")):
            csv_txt = open(os.path.join(camp, "collecte.csv"), encoding="utf-8").read()
            check("CSV contains model", "deepseek/x" in csv_txt)
            check("CSV contains input prompt", "saucisson" in csv_txt or "MJ Tonnerre" in csv_txt)
            check("factual delta traced in CSV (3 → 2)", "3 → 2" in csv_txt, csv_txt[:200])
        # render_block : INTERNAL at INFO level, exposed only in DEBUG/TRACE (R4)
        sys.path.insert(0, HOOKS_DIR)
        import transform_llm_output as _T
        _pd = [{"emoji": "🎒", "phrase": "Rubis inventory: 3 → 2 item(s)"}]
        check("render_block INFO → empty (internal)", _T.render_block("INFO", _pd, []) == "")
        _bd = _T.render_block("DEBUG", _pd, [])
        check("render_block DEBUG → exposes the delta", "Persisted" in _bd and "3 → 2" in _bd, _bd[:80])

        # ── 4. transform bypass : response intact, CSV written anyway ────────
        print("\n[4] transform_llm_output — bypass ⏸️")
        run_hook("pre_llm_call.py", {
            "cwd": camp, "session_id": "sess_b2", "message": "⏸️ check", "extra": {"model": "m"},
        })
        out, _ = run_hook("transform_llm_output.py", {
            "cwd": camp, "session_id": "sess_b2", "message": "⏸️ check",
            "response": "Raw narration.", "extra": {"model": "m"},
        })
        resp = out.get("response", "")
        check("pause ⏸️ : narration preserved + resume banner",
              "Raw narration." in resp and "▶️" in resp, json.dumps(out)[:120])

        # ── 4a. bypass !pause : ASCII text alias, identical to ⏸️ ───────────
        print("\n[4a] bypass !pause — text alias")
        out, _ = run_hook("pre_llm_call.py", {
            "cwd": camp, "session_id": "sess_pause_cmd",
            "message": "!pause debug", "extra": {"model": "m"},
        })
        check("!pause : no context injected", out == {}, json.dumps(out)[:80])
        out, _ = run_hook("transform_llm_output.py", {
            "cwd": camp, "session_id": "sess_pause_cmd", "message": "!pause check",
            "response": "Raw narration.", "extra": {"model": "m"},
        })
        resp = out.get("response", "")
        check("!pause : narration preserved + resume banner",
              "Raw narration." in resp and "▶️" in resp, json.dumps(out)[:120])

        # ── 4b. auto-TTS (tts axis) : MEDIA: appended, gating, snapshot ──────
        print("\n[4b] transform_llm_output — narrative voice (auto-TTS, mocked)")
        narration = ("You push the heavy dungeon door. The icy air grips you, laden "
                     "with the smell of damp stone and an even older secret. At the far "
                     "end of the hall, a broken throne waits in the shadows, and an invisible gaze "
                     "slowly settles on you.")
        tts_env = {
            "MINIMAX_API_KEY": "test", "MGM_TTS_MOCK": "1", "MGM_TTS_MIN_CHARS": "100",
            "MGM_TTS_FORMAT_MOCK": json.dumps({
                "script": "You push the door. <#1.0#> A broken throne.", "emotion": "fearful",
                "ambiance": "dungeon", "moment_cle": True}),
        }
        out, err = run_hook("transform_llm_output.py", {
            "cwd": camp, "session_id": "sess_tts", "response": narration,
            "extra": {"model": "m"}}, env=tts_env)
        resp = out.get("response", "")
        check("auto-TTS appends a MEDIA:", "MEDIA:" in resp, resp[-80:] if resp else "(empty)")
        check("original narration preserved", "broken throne waits" in resp)

        # tts axis OFF (env MGM_FEATURE_TTS=0) → no voice
        off_env = dict(tts_env); off_env["MGM_FEATURE_TTS"] = "0"
        out, _ = run_hook("transform_llm_output.py", {
            "cwd": camp, "session_id": "sess_tts2", "response": narration,
            "extra": {"model": "m"}}, env=off_env)
        check("tts axis OFF → no MEDIA:", "MEDIA:" not in json.dumps(out))

        # short narration → silent even with tts axis ON
        out, _ = run_hook("transform_llm_output.py", {
            "cwd": camp, "session_id": "sess_tts3", "response": "Ok, that works.",
            "extra": {"model": "m"}}, env=tts_env)
        check("short narration → no MEDIA:", "MEDIA:" not in json.dumps(out))

        # snapshot last_narration written (feeds !raconte), even when Minimax key absent
        nokey = {"MINIMAX_API_KEY": ""}
        run_hook("transform_llm_output.py", {
            "cwd": camp, "session_id": "sess_tts4", "response": "A brief nocturnal scene.",
            "extra": {"model": "m"}}, env=nokey)
        snap = os.path.join(camp, ".banquier", "snap-sess_tts4.json")
        snap_ok = os.path.exists(snap) and "last_narration" in open(snap, encoding="utf-8").read()
        check("snapshot last_narration written (for !raconte)", snap_ok)

        # ── 4c. player channel scrub : code/traceback removed, templates intact ─
        print("\n[4c] transform_llm_output — player channel scrub")
        out, _ = run_hook("transform_llm_output.py", {
            "cwd": camp, "session_id": "sess_scrub1",
            "response": "Berthe hands you an eel.\n\n```python\nx = load_pnj()\n```\n\nShe smiles.",
            "extra": {"model": "m"}})
        resp = out.get("response", "")
        check("code block removed from player channel", "```" not in resp and "load_pnj" not in resp, resp[:120])
        check("narration preserved around code", "eel" in resp and "smiles" in resp)

        # 100% code response → neutral fallback, never a no-op (original would leak otherwise)
        out, _ = run_hook("transform_llm_output.py", {
            "cwd": camp, "session_id": "sess_scrub2",
            "response": "```python\nimport json\njson.load(open('npcs.json'))\n```",
            "extra": {"model": "m"}})
        check("all-code response → rewritten (not a no-op)", out != {}, json.dumps(out)[:80])
        check("all-code response → no code delivered", "import json" not in out.get("response", ""))

        # bypass ⏸️ : admin sees everything, no scrub (but pause banner added)
        out, _ = run_hook("transform_llm_output.py", {
            "cwd": camp, "session_id": "sess_scrub3", "message": "⏸️ debug",
            "response": "Text.\n```python\nprint(1)\n```", "extra": {"model": "m"}})
        resp = out.get("response", "")
        check("bypass ⏸️ → code not scrubbed", "print(1)" in resp and "```" in resp, json.dumps(out)[:120])
        check("pause ⏸️ → resume banner added", "▶️" in resp, json.dumps(out)[:120])

        # explicit exception "MJ, show me" : no scrub (no-op → original delivered as-is),
        # whereas the same all-code response is rewritten outside the exception (cf. sess_scrub2).
        out, _ = run_hook("transform_llm_output.py", {
            "cwd": camp, "session_id": "sess_scrub4", "message": "MJ, show me the script",
            "response": "```python\nimport json\njson.load(open('npcs.json'))\n```", "extra": {"model": "m"}})
        check("explicit request → no scrub (no-op)", out == {}, json.dumps(out)[:80])

        # ── 5. strict JSON guard : blocks broken content ─────────────────────
        print("\n[5] pre_tool_call — strict JSON guard")
        camp2 = build_fixture(os.path.join(root, "strict"), strict=True)
        out, _ = run_hook("pre_tool_call.py", {
            "cwd": camp2, "session_id": "s", "tool_name": "write_file",
            "tool_input": {"path": "sessions/009.json", "content": "{ broken: not json"},
        })
        check("write blocked (action=block)", out.get("action") == "block", json.dumps(out)[:120])
        # advisory mode : non-blocking
        camp3 = build_fixture(os.path.join(root, "advisory"), strict=False)
        out, _ = run_hook("pre_tool_call.py", {
            "cwd": camp3, "session_id": "s", "tool_name": "write_file",
            "tool_input": {"path": "sessions/009.json", "content": "{ broken"},
        })
        check("not blocked in advisory mode", out.get("action") != "block", json.dumps(out)[:120])

        # ── 6. robustness : empty payload → safe no-op ──────────────────────
        print("\n[6] robustness — degenerate payloads")
        for script in ("pre_llm_call.py", "pre_tool_call.py", "post_tool_call.py",
                       "transform_llm_output.py", "on_session_end.py"):
            out, err = run_hook(script, {})
            check("%s tolerates an empty payload" % script, isinstance(out, dict) and "__raw__" not in out, err[:120])

        # ── 7. LLM judge (mocked) : violation → feed-forward + scoreboard ────
        print("\n[7] LLM judge (mocked) — conduct violation")
        campj = build_fixture(os.path.join(root, "judge"), judge=True)
        sidj = "sess_judge"
        VIOL = json.dumps({"ok": False, "violations": [{
            "domaine": "conduite", "regle": "AGENTIVITE",
            "extrait": "fear grips you and you step back",
            "pourquoi": "imposed reaction on the PC", "correction": "describe only what they perceive",
        }]})
        long_resp = ("Fear grips you and you step back into the shadows as the wind "
                     "howls between the frozen stones of the forgotten old temple.")
        # turn 1 : pre_llm_call then transform with mocked violation
        run_hook("pre_llm_call.py", {"cwd": campj, "session_id": sidj,
                                     "message": "I advance carefully", "extra": {"model": "deepseek/x"}})
        out, _ = run_hook("transform_llm_output.py",
                          {"cwd": campj, "session_id": sidj, "response": long_resp,
                           "extra": {"model": "deepseek/x"}},
                          env={"MGM_JUDGE_MOCK": VIOL})
        pend = os.path.join(campj, ".banquier", "pending-%s.json" % sidj)
        check("deferred feedback stored (pending)", os.path.exists(pend))
        sb = os.path.join(campj, ".banquier", "scoreboard.json")
        check("scoreboard created", os.path.exists(sb))
        if os.path.exists(sb):
            data = json.load(open(sb, encoding="utf-8")).get("deepseek/x", {})
            check("conduct violation counted", data.get("infractions_conduite", 0) == 1, json.dumps(data))
        # turn 2 : pre_llm_call reinjects the feedback and clears it
        out, _ = run_hook("pre_llm_call.py", {"cwd": campj, "session_id": sidj,
                                              "message": "I continue", "extra": {"model": "deepseek/x"}},
                          env={})
        check("feedback reinjected on next turn", "CORRECTION" in out.get("context", ""), out.get("context", "")[:80])
        check("pending cleared after reinjection", not _pending_has_text(pend))

        # ── 8. LLM judge (mocked) : clean turn → scoreboard 'propres' ────────
        print("\n[8] LLM judge (mocked) — clean turn")
        run_hook("pre_llm_call.py", {"cwd": campj, "session_id": "sess_clean",
                                     "message": "x", "extra": {"model": "modele/propre"}})
        run_hook("transform_llm_output.py",
                 {"cwd": campj, "session_id": "sess_clean", "response": long_resp,
                  "extra": {"model": "modele/propre"}},
                 env={"MGM_JUDGE_MOCK": json.dumps({"ok": True})})
        data = json.load(open(sb, encoding="utf-8")).get("modele/propre", {})
        check("clean turn counted", data.get("propres", 0) == 1 and data.get("infractions_conduite", 0) == 0, json.dumps(data))

        # ── 9. mj_checkpoint gate : anti-loop budget ────────────────────────
        print("\n[9] mj_checkpoint — gate + anti-loop budget (max 2)")
        out1, code1 = run_cli("mj_checkpoint.py", args=["--draft", long_resp], cwd=campj,
                              env={"MGM_JUDGE_MOCK": VIOL})
        check("1st attempt : violation reported (exit 1)", code1 == 1 and "AGENTIVITE" in out1, out1[:80])
        out2, code2 = run_cli("mj_checkpoint.py", args=["--draft", long_resp], cwd=campj,
                              env={"MGM_JUDGE_MOCK": VIOL})
        check("2nd attempt : FORCED to avoid looping (exit 0)", code2 == 0 and "FORCED" in out2, out2[:80])
        outok, codeok = run_cli("mj_checkpoint.py", args=["--draft", long_resp], cwd=campj,
                                env={"MGM_JUDGE_MOCK": json.dumps({"ok": True})})
        check("checkpoint OK when nothing to report (exit 0)", codeok == 0 and "OK" in outok, outok[:80])

        # ── 10. scoreboard.py : read ─────────────────────────────────────────
        print("\n[10] scoreboard.py — read")
        sbout, sbcode = run_cli("scoreboard.py", args=[campj])
        check("scoreboard readable", sbcode == 0 and "Scoreboard" in sbout and "deepseek/x" in sbout, sbout[:80])

        # ── 11. judge activation via ENV (deployment) without world config ────
        print("\n[11] judge activation via MGM_JUDGE_ACTIF (deployment env)")
        campe = build_fixture(os.path.join(root, "envjudge"))  # NO meta.hooks.judge
        run_hook("pre_llm_call.py", {"cwd": campe, "session_id": "se",
                                     "message": "x", "extra": {"model": "m"}},
                 env={"MGM_JUDGE_ACTIF": "1"})
        run_hook("transform_llm_output.py",
                 {"cwd": campe, "session_id": "se", "response": long_resp, "extra": {"model": "m"}},
                 env={"MGM_JUDGE_ACTIF": "1", "MGM_JUDGE_MODEL": "x/y", "MGM_JUDGE_MOCK": VIOL})
        check("judge activated by env → deferred feedback created",
              _pending_has_text(os.path.join(campe, ".banquier", "pending-se.json")))

        # ── 11b. PERSISTENT pause mode ⏸️ … ▶️ (pause lasts until resume) ─────
        print("\n[11b] pre_llm_call — persistent pause mode ⏸️ … ▶️")
        sidp = "sess_pausemode"
        out, _ = run_hook("pre_llm_call.py", {"cwd": camp, "session_id": sidp,
                                              "message": "⏸️ pausing now", "extra": {"model": "m"}})
        check("⏸️ arms the mode (no context)", out == {}, json.dumps(out)[:80])
        # NEXT turn without marker, same session → still paused (persistent).
        out, _ = run_hook("pre_llm_call.py", {"cwd": camp, "session_id": sidp,
                                              "message": "out-of-game note", "extra": {"model": "m"}})
        check("next turn without marker → still paused", out == {}, json.dumps(out)[:80])
        # ▶️ lifts the mode → state injection resumes from this turn.
        out, _ = run_hook("pre_llm_call.py", {"cwd": camp, "session_id": sidp,
                                              "message": "▶️ resuming now", "extra": {"model": "m"}})
        check("▶️ lifts the mode → context reinjected",
              "AUTHORITATIVE STATE" in out.get("context", ""), json.dumps(out)[:80])
        # Text alias : !pause … !reprise.
        sidp2 = "sess_pausemode2"
        run_hook("pre_llm_call.py", {"cwd": camp, "session_id": sidp2,
                                     "message": "!pause", "extra": {"model": "m"}})
        out, _ = run_hook("pre_llm_call.py", {"cwd": camp, "session_id": sidp2,
                                              "message": "!reprise", "extra": {"model": "m"}})
        check("!reprise also lifts the mode",
              "AUTHORITATIVE STATE" in out.get("context", ""), json.dumps(out)[:80])
        # On the transform side : pause banner on each persistent turn, then confirmation at ▶️.
        run_hook("pre_llm_call.py", {"cwd": camp, "session_id": "sess_pm3",
                                     "message": "⏸️ aside", "extra": {"model": "m"}})
        out, _ = run_hook("transform_llm_output.py", {"cwd": camp, "session_id": "sess_pm3",
                                                      "response": "Technical note.", "extra": {"model": "m"}})
        check("turn in persistent pause (without marker) → ▶️ banner displayed",
              "▶️" in out.get("response", "") and "Technical note." in out.get("response", ""),
              json.dumps(out)[:100])
        out, _ = run_hook("transform_llm_output.py", {"cwd": camp, "session_id": "sess_pm3",
                                                      "message": "▶️ resuming now", "response": "Back to the adventure.",
                                                      "extra": {"model": "m"}})
        check("▶️ turn → game resume confirmation",
              "Game resumed" in out.get("response", ""), json.dumps(out)[:100])

        # ── 11c. judge DECOUPLED from admin bypass (admin playing is still judged) ──
        print("\n[11c] judge active on an ADMIN turn (decoupled from bypass)")
        campa = build_fixture(os.path.join(root, "adminjudge"), judge=True)
        ADMIN = "999000111"  # listed in meta.admins of the fixture
        run_hook("pre_llm_call.py", {"cwd": campa, "session_id": "sa", "author_id": ADMIN,
                                     "message": "I am testing", "extra": {"model": "deepseek/x"}})
        run_hook("transform_llm_output.py",
                 {"cwd": campa, "session_id": "sa", "author_id": ADMIN, "response": long_resp,
                  "extra": {"model": "deepseek/x"}},
                 env={"MGM_JUDGE_MOCK": VIOL})
        check("judge runs on an admin turn → pending created",
              _pending_has_text(os.path.join(campa, ".banquier", "pending-sa.json")))
        # The correction is reinjected even on the next admin turn (otherwise it would never be corrected).
        out, _ = run_hook("pre_llm_call.py", {"cwd": campa, "session_id": "sa", "author_id": ADMIN,
                                              "message": "continuing", "extra": {"model": "deepseek/x"}})
        check("correction reinjected even on admin turn",
              "CORRECTION" in out.get("context", ""), out.get("context", "")[:80])
        # BUT an EXPLICIT pause ⏸️ does suspend the judge, admin or not.
        run_hook("pre_llm_call.py", {"cwd": campa, "session_id": "sp", "author_id": ADMIN,
                                     "message": "⏸️ aside", "extra": {"model": "deepseek/x"}})
        run_hook("transform_llm_output.py",
                 {"cwd": campa, "session_id": "sp", "author_id": ADMIN, "message": "⏸️ aside",
                  "response": long_resp, "extra": {"model": "deepseek/x"}},
                 env={"MGM_JUDGE_MOCK": VIOL})
        check("explicit pause ⏸️ suspends the judge (no pending)",
              not _pending_has_text(os.path.join(campa, ".banquier", "pending-sp.json")))

        # ── 12. versioned auto-commit (post_tool_call) ──────────────────────
        print("\n[12] post_tool_call — git auto-commit")

        def git_log(c):
            r = subprocess.run(["git", "-C", c, "log", "--oneline"],
                               capture_output=True, text=True)
            return r.stdout if r.returncode == 0 else ""

        def git_lsfiles(c):
            r = subprocess.run(["git", "-C", c, "ls-files"],
                               capture_output=True, text=True)
            return r.stdout if r.returncode == 0 else ""

        # 12a — default ON (key absent) : one validated write → one auto-commit.
        campg = build_fixture(os.path.join(root, "autocommit"), auto_commit=None)
        pjg = os.path.join(campg, "characters", "403.json")
        dg = json.load(open(pjg, encoding="utf-8"))
        dg["inventory"] = ["corde"]
        write_json(pjg, dg)
        _, err_g = run_hook("post_tool_call.py", {
            "cwd": campg, "session_id": "sg", "tool_name": "write_file",
            "tool_input": {"path": "characters/403.json"},
        })
        check("git repo initialized (auto-commit default ON)",
              os.path.isdir(os.path.join(campg, ".git")))
        log_g = git_log(campg)
        check("auto-commit created", "auto" in log_g, log_g[:120])
        check("auto-commit traced on stderr (observability)",
              "[mj-git] auto-commit committed" in err_g, err_g[:120])
        check(".banquier excluded from versioning", ".banquier" not in git_lsfiles(campg))
        check("collecte.csv excluded from versioning", "collecte.csv" not in git_lsfiles(campg))

        # 12b — toggle OFF : no git write.
        campo = build_fixture(os.path.join(root, "nocommit"), auto_commit=False)
        pjo = os.path.join(campo, "characters", "403.json")
        do = json.load(open(pjo, encoding="utf-8"))
        do["inventory"] = ["x"]
        write_json(pjo, do)
        run_hook("post_tool_call.py", {
            "cwd": campo, "session_id": "so", "tool_name": "write_file",
            "tool_input": {"path": "characters/403.json"},
        })
        check("no repo when auto_commit=false",
              not os.path.isdir(os.path.join(campo, ".git")))

        # 12c — broken JSON : never commit an inconsistent state.
        campb = build_fixture(os.path.join(root, "brokencommit"), auto_commit=None)
        sb_path = os.path.join(campb, "sessions", "009.json")
        with open(sb_path, "w", encoding="utf-8") as fh:
            fh.write("{ broken not json")
        run_hook("post_tool_call.py", {
            "cwd": campb, "session_id": "sb", "tool_name": "write_file",
            "tool_input": {"path": "sessions/009.json"},
        })
        check("no auto-commit on broken JSON",
              not os.path.isdir(os.path.join(campb, ".git")))

        # ── 13. i18n — UI strings localized at runtime (en default, fr locale) ──
        print("\n[13] i18n — runtime localization of UI strings")
        sys.path.insert(0, HOOKS_DIR)
        import _lib as L  # noqa: E402

        # English (default): byte-identical to historical output.
        check("t() default = English", L.t("pause.resumed") == "▶️ *Game resumed.*")
        check("t() fr returns French", L.t("pause.resumed", "fr") == "▶️ *Partie reprise.*")
        check("t() unknown lang → English fallback", L.t("brief.stakes", "de") == "STAKES")

        # lang() cascade: meta.langue resolves the campaign language.
        check("lang() reads meta.langue", L.lang({"meta": {"langue": "fr"}}) == "fr")
        check("lang() default en", L.lang({}) == "en")

        # etat_brief localized: FR campaign → French labels, EN unchanged.
        campfr = build_fixture(os.path.join(root, "fr"))
        write_json(os.path.join(campfr, "world.json"), {
            "meta": {"name": "Test", "time": {"regime": "Narratif"},
                     "verbosity": "INFO", "langue": "fr"},
            "modules": {}, "global_state": {}, "universe": {"regions": []},
        })
        mfr = L.load_monde(L.campaign_dir({"cwd": campfr}))
        eb_fr = L.etat_brief(L.campaign_dir({"cwd": campfr}), mfr)
        check("etat_brief FR labels", "Temps :" in eb_fr and "PJ Rubis" in eb_fr, eb_fr[:60])
        mfr["meta"]["langue"] = "en"
        eb_en = L.etat_brief(L.campaign_dir({"cwd": campfr}), mfr)
        check("etat_brief EN labels unchanged", "Time:" in eb_en and "PC Rubis" in eb_en, eb_en[:60])

        # transform_llm_output: FR pause banner end-to-end (subprocess).
        outfr, _ = run_hook("transform_llm_output.py", {
            "cwd": campfr, "session_id": "sfr", "message": "⏸️ aside",
            "response": "A long narration." * 5, "extra": {"model": "m"}})
        check("FR pause banner via transform", "Pause active — la partie" in outfr.get("response", ""),
              json.dumps(outfr)[:120])
        # ── 14. NPC emotions injection (skill mygamemaster-emotions) ─────────
        print("\n[14] pre_llm_call — NPC emotions brief (fail-open)")
        campm = build_fixture(os.path.join(root, "emotions"))
        # 13a — no emotions data → no block (absent emotions = no behavior change).
        out, _ = run_hook("pre_llm_call.py", {
            "cwd": campm, "session_id": "sm", "message": "x", "extra": {"model": "m"}})
        check("no emotions data → no NPC EMOTIONS block",
              "NPC EMOTIONS" not in out.get("context", ""))
        # 13b — Berthe carries an `emotions` object → one concise line injected.
        pnjm = os.path.join(campm, "npcs.json")
        datam = json.load(open(pnjm, encoding="utf-8"))
        datam[0]["emotions"] = {
            "etat": {"joy": 0.3, "trust": 0.1, "fear": 0.7,
                     "anger": 0.2, "sadness": 0.2, "surprise": 0.0},
            "temperament": {"joy": 0.3, "trust": 0.3, "fear": 0.2,
                            "anger": 0.1, "sadness": 0.2, "surprise": 0.0},
            "history": [{"event": "threat", "deltas": {"fear": 0.3},
                            "reason": "bandits at the mill", "session": 9}],
        }
        write_json(pnjm, datam)
        out, _ = run_hook("pre_llm_call.py", {
            "cwd": campm, "session_id": "sm", "message": "x", "extra": {"model": "m"}})
        ctxm = out.get("context", "")
        check("emotions block injected", "NPC EMOTIONS" in ctxm, ctxm[:120])
        check("emotional Berthe listed with reason",
              "Berthe" in ctxm and "bandits at the mill (S9)" in ctxm)
        check("NPC without emotions data not listed in the block",
              "Firmin" not in ctxm.split("NPC EMOTIONS")[-1])
        # 13c — axis living_npcs_factions OFF → block gated off.
        mondem = json.load(open(os.path.join(campm, "world.json"), encoding="utf-8"))
        mondem["meta"]["features"] = {"living_npcs_factions": False}
        write_json(os.path.join(campm, "world.json"), mondem)
        out, _ = run_hook("pre_llm_call.py", {
            "cwd": campm, "session_id": "sm", "message": "x", "extra": {"model": "m"}})
        check("axis OFF → no emotions block, turn intact",
              "NPC EMOTIONS" not in out.get("context", "")
              and "AUTHORITATIVE STATE" in out.get("context", ""))
        # 13d — broken npcs.json → fail-open (state injection survives, no block).
        mondem["meta"]["features"] = {}
        write_json(os.path.join(campm, "world.json"), mondem)
        with open(pnjm, "w", encoding="utf-8") as fh:
            fh.write("{ not json")
        out, _ = run_hook("pre_llm_call.py", {
            "cwd": campm, "session_id": "sm", "message": "x", "extra": {"model": "m"}})
        check("broken npcs.json → fail-open (no block, no crash)",
              "NPC EMOTIONS" not in out.get("context", "")
              and "AUTHORITATIVE STATE" in out.get("context", ""))

    finally:
        shutil.rmtree(root, ignore_errors=True)

    print("\n" + "=" * 60)
    passed = sum(1 for _, ok, _ in _results if ok)
    total = len(_results)
    failed = [n for n, ok, _ in _results if not ok]
    print("RESULT : %d/%d tests OK" % (passed, total))
    if failed:
        print("FAILURES : " + ", ".join(failed))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
