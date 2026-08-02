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


# Agency corpus tables (label, draft, declared[, rules]) — mined from docs/10-field-report.md,
# the AGENCY-01/02/03 evidence column of locked-lessons.md and the worked examples of references/.
PC_NAMES = ["Rubis"]

AGENCY_VIOLATIONS = [
    ("FR two chained PC actions (S23 pattern)",
     "Tu t'approches de la pierre et tu poses la main dessus.", "", ["AGENCY-01", "AGENCY-03"]),
    ("FR single imposed movement",
     "Tu recules d'un pas.", "", ["AGENCY-01"]),
    ("FR imposed gesture + posture",
     "Tu hoches la tête et tu souris.", "", ["AGENCY-01", "AGENCY-03"]),
    ("FR imposed breath (AGENCY-01 verbatim: breath)",
     "Tu retiens ton souffle.", "", ["AGENCY-01"]),
    ("FR imposed gaze (AGENCY-01 verbatim: gaze)",
     "Tu détournes le regard.", "", ["AGENCY-01"]),
    ("FR three stacked actions (S16 pattern)",
     "Tu ouvres la porte, tu franchis le seuil, puis tu descends l'escalier.", "",
     ["AGENCY-01", "AGENCY-03"]),
    ("FR PC dialogue invented (S21/S23)",
     "Tu dis à Berthe que tu acceptes.", "", ["AGENCY-02"]),
    ("FR PC dialogue by narrative inversion",
     "« Je viendrai », dis-tu.", "", ["AGENCY-02"]),
    ("FR PC named in third person",
     "Rubis s'agenouille devant le feu.", "", ["AGENCY-01"]),
    ("FR action beyond the declared one",
     "Tu t'approches de la pierre et tu poses la main dessus.", "je m'approche de la pierre",
     ["AGENCY-01", "AGENCY-03"]),
    ("EN imposed movement (the corpus 1/5 pattern, English locale)",
     "You step back into the shadows.", "", ["AGENCY-01"]),
    ("EN gesture + action in one turn",
     "You nod slowly and place your hand on the stone.", "", ["AGENCY-01", "AGENCY-03"]),
    ("EN PC dialogue invented",
     "You say that you accept.", "", ["AGENCY-02"]),
    ("EN PC named in third person",
     "Rubis kneels by the fire.", "", ["AGENCY-01"]),
    ("EN six unvalidated actions (narrative-pacing-concrete ❌ regression)",
     "You pull the first trap — it's heavy. Full of silvery perch.\n"
     "You move to the snares next — a hare hangs there, stiff.\n"
     "You bring it all back to the cabin. Berthe has already prepared the smoker.",
     "I go to the traps", ["AGENCY-01", "AGENCY-03"]),
    ("EN action beyond a declared move",
     "You pull the first one. It's full of silvery perch.", "I go to the traps", ["AGENCY-01"]),
    ("FR action smuggled in front of the handoff question",
     "Tu recules d'un pas — que fais-tu ?", "", ["AGENCY-01"]),
    ("FR action before a comma-attached question",
     "Tu poses la main sur la pierre, que fais-tu ?", "", ["AGENCY-01"]),
    ("EN action before a comma-attached question",
     "You step back into the shadows, what do you do?", "", ["AGENCY-01"]),
]

AGENCY_LEGITIMATE = [
    ("EN sensory anchor (scene-output-template filled example)",
     "The forge has gone cold; only embers remain, and the iron smell hangs heavy in the dark.", ""),
    ("EN NPC behaviour + speech with the PC as object",
     "Hadrec the smith looks up from the bench, hammer still in hand. \"We're closed,\" he says — "
     "then his eyes flick to the road behind you before settling back on your faces.", ""),
    ("EN standing facts of the scene",
     "A half-finished horseshoe lies abandoned on the anvil, the quench-bucket beside it untouched.", ""),
    ("EN handoff question", "What do you do?", ""),
    ("EN held beat STOP", "🛑 Drageon looks at you. He waits.", ""),
    ("EN corrected verb (narrative-recurring-errors #1)",
     "Firmin spent twenty years maintaining the seals.", ""),
    ("EN corrected possessive (narrative-recurring-errors #2)",
     "Berthe looks at you — not because it belongs to you, but because you are the initiator.", ""),
    ("EN corrected object position (narrative-recurring-errors #5)",
     "Firmin sits by the window, hands empty — the journal is beside you, on your pallet.", ""),
    ("EN corrected temporality (narrative-recurring-errors #4)",
     "For a few days, a stranger has been cleaning them.", ""),
    ("EN perception only", "You hear a creaking above the beams, and the smell of wet ash reaches you.", ""),
    ("EN two perceptions are not two actions",
     "You see the cracked stone; you feel the cold rising through your soles.", ""),
    ("EN world acting without the PC",
     "The wind drops. Three silhouettes wait by the fire in the clearing.", ""),
    ("EN hypothetical clause", "If you step through, the seal will hold — that is what Firmin claims.", ""),
    ("FR sensory anchor", "La lanterne crache une flamme basse. L'air sent la pierre mouillée.", ""),
    ("FR NPC gesture + dialogue", "Berthe repose le couteau sans lever les yeux. « On ferme », dit-elle.", ""),
    ("FR world sound", "Un craquement monte de l'escalier, puis plus rien.", ""),
    ("FR NPC acting on the PC (object clitic, allowed)", "Firmin te tend le journal, la main tremblante.", ""),
    ("FR NPC gaze toward the PC (allowed)", "Drageon te regarde. Il attend.", ""),
    ("FR perception only", "Tu entends un bruit de sabots sur le chemin ; l'odeur de fumée arrive.", ""),
    ("FR two perceptions", "Tu vois la pierre fendue, et tu sens le froid remonter par les semelles.", ""),
    ("FR STOP on world state", "🛑 Berthe attend ta réponse.", ""),
    ("FR NPC dialogue addressing the PC as 'tu'", "« Tu poses trop de questions », lâche Rousset.", ""),
    ("FR dash dialogue line", "— Tu devrais dormir, dit Berthe. Elle remonte la couverture.", ""),
    ("FR PC name in a non-subject position", "Rubis, la petite lame de Berthe, brille sur la table.", ""),
    ("FR NPC-to-NPC relationship (narrative-recurring-errors #3)",
     "Berthe a connu Firmin pendant des années — c'est elle qu'il a prévenue en premier.", ""),
    ("FR ambient state", "Il fait nuit depuis deux heures. La neige tient sur les toits de la Marche.", ""),
    ("FR question to the player", "Que fais-tu ?", ""),
    ("FR negated construction", "Tu ne sais pas encore ce qui t'attend derrière la porte.", ""),
    ("FR hypothetical clause", "Tu peux voir la lueur au bout du couloir, si tu avances.", ""),
    ("FR NPC acting on the party", "Berthe nous regarde tous les deux, puis hausse les épaules.", ""),
    ("FR declared action executed (AGENCY-03 bounded exception)",
     "Tu t'approches de la pierre. Le froid monte du sol.", "je m'approche de la pierre"),
    ("FR declared action executed, English locale",
     "You step through the doorway. The air is colder here.", "I step through the doorway"),
    ("FR verbatim placeholder instead of an invented line",
     "Tu dis [VERBATIM À FOURNIR PAR LE JOUEUR] et Berthe attend.", ""),
    ("FR player's own words quoted back",
     "« Je viendrai », dis-tu, et Berthe hoche la tête.", "je réponds « je viendrai »"),
    ("EN scene state before the PC (narrative-pacing-concrete ✅)",
     "The fire crackles. The cabin smokes softly in the autumn. Before you, Rousset has already "
     "left to cut wood. You hear the murmur of the Douce. What do you do?", ""),
    ("EN state of the world rather than assigned actions",
     "The Douce flows before you, the traps are further down on the left bank. The smoker is "
     "ready. Berthe is working on the turnips. What do you do?", ""),
    ("EN NPC offer is dialogue, not a menu", "Rousset suggests going to cut wood.", ""),
    ("EN corrected turn executing the declaration (narrative-pacing-concrete ✅)",
     "You pull the first one. It's full of silvery perch. The second one too, a bit less. "
     "What do you do with all this?", "I go to the traps and I pull in the fish"),
    ("FR scene state before the PC",
     "Le feu crépite. La cabane fume doucement dans l'automne. Devant toi, Rousset est déjà parti "
     "couper du bois. Tu entends le murmure de la Douce. Que fais-tu ?", ""),
]

# HELD-OUT false-positive table: the reported rate is measured HERE, never on AGENCY_LEGITIMATE,
# which is the table the lexicons were tuned against and so cannot falsify them.
AGENCY_HELDOUT = [
    ("EN PC as object of a preposition, inverted subject",
     "Behind you stands a hooded figure.", ""),
    ("EN PC as object, NPC subject after the verb",
     "Opposite you sits a man in a grey cloak.", ""),
    ("EN world rising around the PC", "Around you rise the black walls of the keep.", ""),
    ("EN NPC acts on the PC then acts on itself",
     "Berthe hands you a bowl of broth and sits down opposite.", ""),
    ("EN NPC yields to the PC then gestures",
     "The guard steps aside for you and gestures at the stairs.", ""),
    ("EN NPC watches the PC and stays silent", "The old man watches you and says nothing.", ""),
    ("EN scene-output-template block 2 verbatim",
     "Berthe sets down the knife and does not meet your eyes.", ""),
    ("EN scene-output-template block 1 verbatim",
     "The lantern gutters; cold damp rises from the stairwell.", ""),
    ("EN scene-output-template ✅ showing rewrite",
     "Hadrec sets the hammer down a little too fast. \"We're closed,\" he says, already "
     "half-turning back to the forge — though the forge is dark and there is nothing left to "
     "work.", ""),
    ("EN NPC declines to ask", "He doesn't ask what you want.", ""),
    ("EN narrative-pacing state of the world",
     "The traps are further down on the left bank; the smoker is ready.", ""),
    ("EN world moving on without the PC",
     "Rousset returns with more perch. Evening falls. Firmin hasn't come back.", ""),
    ("EN NPC improvises with what they own",
     "The blanket spread on the ground serves as a gathering mat.", ""),
    ("EN weather acting near the PC",
     "Rain finds the gap in the roof and pools on the flagstones by your boots.", ""),
    ("EN offstage sound", "A dog barks somewhere past the gate, then falls quiet.", ""),
    ("EN NPC leaning toward the PC",
     "The innkeeper leans over the counter toward you and lowers his voice.", ""),
    ("FR perception then an NPC gaze as new subject",
     "Tu sens le froid et le regard de Berthe pèse sur ta nuque.", ""),
    ("FR perception then an NPC cry as new subject",
     "Tu entends un bruit avant le cri de Berthe.", ""),
    ("FR perception then a noun colliding with an action stem (bois)",
     "Tu entends un craquement et le bois de la charpente travaille.", ""),
    ("FR perception then a noun colliding with an action stem (serrure)",
     "Tu entends la clé et la serrure joue dans le bois gonflé.", ""),
    ("FR perception then a noun colliding with an action stem (poussière)",
     "Tu vois la lueur au bout du couloir et la poussière danse dedans.", ""),
    ("FR perception then a noun colliding with an action stem (lit)",
     "Tu entends un râle et le lit grince dans le noir.", ""),
    ("FR world acting on itself across a conjunction",
     "Le vent tombe d'un coup et la porte de la grange bat contre le mur.", ""),
    ("FR PC name as object of a preposition",
     "Berthe tend le journal à Rubis, la main tremblante.", ""),
    ("FR NPC speaks to the PC then resumes its own business",
     "Firmin te parle sans lever les yeux, puis retourne à son établi.", ""),
    ("FR landscape before the PC", "Devant toi, la Douce charrie des branches noires.", ""),
    ("FR offstage animal", "Un chien aboie derrière la palissade, puis se tait.", ""),
    ("FR ambient state across a conjunction",
     "La neige tient sur les toits et le froid monte des dalles.", ""),
    ("FR NPC offer inside the fiction", "Rousset propose d'aller couper du bois.", ""),
    ("FR two world facts across a conjunction",
     "L'odeur de fumée arrive du fournil et les braises rougeoient sous la cendre.", ""),
]


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

        # ── 4b. auto-TTS : opt-in default, and every outcome recorded ────────
        print("\n[4b] transform_llm_output — narrative voice (auto-TTS, mocked)")
        narration = ("You push the heavy dungeon door. The icy air grips you, laden "
                     "with the smell of damp stone and an even older secret. At the far "
                     "end of the hall, a broken throne waits in the shadows, and an invisible gaze "
                     "slowly settles on you.")
        # Neutralised, not just unset: run_hook inherits os.environ, so an exported
        # MGM_TTS_AUTO=1 would quietly turn the default-off checks into opt-in checks.
        base_env = {
            "MINIMAX_API_KEY": "test", "MGM_TTS_MOCK": "1", "MGM_TTS_MIN_CHARS": "100",
            "MGM_TTS_AUTO": "", "MGM_TTS_TIMEOUT": "", "MGM_FEATURE_TTS": "",
            "MGM_TTS_FORMAT_MOCK": json.dumps({
                "script": "You push the door. <#1.0#> A broken throne.", "emotion": "fearful",
                "ambiance": "dungeon", "moment_cle": True}),
        }
        tts_env = dict(base_env, MGM_TTS_AUTO="1")   # explicit opt-in

        def tts_status(c):
            p = os.path.join(c, ".banquier", "tts-status.json")
            return json.load(open(p, encoding="utf-8")) if os.path.exists(p) else {}

        def last_tts(c):
            return tts_status(c).get("last") or {}

        # DEFAULT (no opt-in): silent, and the silence is recorded as CONFIGURED.
        campt = build_fixture(os.path.join(root, "tts"))
        out, err = run_hook("transform_llm_output.py", {
            "cwd": campt, "session_id": "sess_tts_default", "response": narration,
            "extra": {"model": "m"}}, env=base_env)
        check("auto-TTS OFF by default → no MEDIA:", "MEDIA:" not in json.dumps(out))
        ev = last_tts(campt)
        check("default recorded as a configured skip, not a failure",
              ev.get("outcome") == "skipped" and ev.get("reason") == "tts_auto_off", json.dumps(ev))
        check("skip also traced on stderr", "[mj-tts]" in err and "tts_auto_off" in err, err[:160])

        # Opt-in via env → voice attached, outcome 'ok', artefact self-identifying.
        out, err = run_hook("transform_llm_output.py", {
            "cwd": campt, "session_id": "sess_tts", "response": narration,
            "extra": {"model": "m"}}, env=tts_env)
        resp = out.get("response", "")
        check("opt-in MGM_TTS_AUTO=1 → MEDIA: appended", "MEDIA:" in resp,
              resp[-80:] if resp else "(empty)")
        check("original narration preserved", "broken throne waits" in resp)
        ev = last_tts(campt)
        check("success recorded (outcome ok, bytes, audio path)",
              ev.get("outcome") == "ok" and ev.get("bytes", 0) > 0, json.dumps(ev))
        audio = ev.get("audio", "")
        check("auto artefact named for its producer", os.path.basename(audio).startswith("auto_"),
              audio)
        side = os.path.splitext(audio)[0] + ".json" if audio else ""
        sidecar = json.load(open(side, encoding="utf-8")) if side and os.path.exists(side) else {}
        check("sidecar records who produced the audio",
              sidecar.get("producer") == "hook-auto"
              and sidecar.get("generator") == "mygamemaster-tts/render", json.dumps(sidecar)[:120])

        # Opt-in via world.json (campaign wins, no env needed).
        campw = build_fixture(os.path.join(root, "ttsworld"))
        mw = json.load(open(os.path.join(campw, "world.json"), encoding="utf-8"))
        mw["meta"]["hooks"]["tts_auto"] = True
        write_json(os.path.join(campw, "world.json"), mw)
        out, _ = run_hook("transform_llm_output.py", {
            "cwd": campw, "session_id": "sess_ttsw", "response": narration,
            "extra": {"model": "m"}}, env=base_env)
        check("meta.hooks.tts_auto=true opts in without env",
              "MEDIA:" in json.dumps(out), json.dumps(out)[-100:])

        # tts axis OFF → no voice at all, and a reason distinct from tts_auto_off.
        off_env = dict(tts_env); off_env["MGM_FEATURE_TTS"] = "0"
        out, _ = run_hook("transform_llm_output.py", {
            "cwd": campt, "session_id": "sess_tts2", "response": narration,
            "extra": {"model": "m"}}, env=off_env)
        check("tts axis OFF → no MEDIA:", "MEDIA:" not in json.dumps(out))
        check("axis OFF recorded as its own reason",
              last_tts(campt).get("reason") == "axis_tts_off", json.dumps(last_tts(campt)))

        # Below threshold → skip carries the numbers that explain it.
        out, _ = run_hook("transform_llm_output.py", {
            "cwd": campt, "session_id": "sess_tts3", "response": "Ok, that works.",
            "extra": {"model": "m"}}, env=tts_env)
        check("short narration → no MEDIA:", "MEDIA:" not in json.dumps(out))
        ev = last_tts(campt)
        check("threshold skip explains itself (chars < min_chars)",
              ev.get("reason") == "too_short" and ev.get("chars") == 15
              and ev.get("min_chars") == 100, json.dumps(ev))

        # Key missing while opted in → FAILURE, never a configured skip.
        nokey_env = dict(tts_env); nokey_env["MINIMAX_API_KEY"] = ""
        out, err = run_hook("transform_llm_output.py", {
            "cwd": campt, "session_id": "sess_tts5", "response": narration,
            "extra": {"model": "m"}}, env=nokey_env)
        ev = last_tts(campt)
        check("missing key recorded as a FAILURE (not silence by choice)",
              ev.get("outcome") == "failed" and ev.get("reason") == "key_missing", json.dumps(ev))
        check("failure states the hook env had no key", ev.get("key") is False, json.dumps(ev))
        check("failure shouted on stderr too", "FAILED" in err and "key_missing" in err, err[:160])
        check("failed turn still delivers the narration untouched",
              "MEDIA:" not in json.dumps(out))

        # Renderer exits non-zero (unroutable endpoint, no mock) → rc AND stderr kept.
        ko_env = dict(tts_env)
        ko_env.pop("MGM_TTS_MOCK")
        ko_env["MINIMAX_API_URL"] = "http://127.0.0.1:1/t2a"
        out, err = run_hook("transform_llm_output.py", {
            "cwd": campt, "session_id": "sess_tts6", "response": narration,
            "extra": {"model": "m"}}, env=ko_env)
        ev = last_tts(campt)
        check("non-zero renderer exit recorded with its return code",
              ev.get("outcome") == "failed" and ev.get("reason", "").startswith("exit_")
              and ev.get("rc"), json.dumps(ev))
        check("renderer stderr captured, not thrown away",
              "network" in (ev.get("stderr") or "").lower(), json.dumps(ev)[:200])
        check("renderer failure never breaks the turn", "MEDIA:" not in json.dumps(out))

        # last_failure survives a later success (evidence must not be overwritten).
        run_hook("transform_llm_output.py", {
            "cwd": campt, "session_id": "sess_tts7", "response": narration,
            "extra": {"model": "m"}}, env=tts_env)
        st = tts_status(campt)
        check("a success does not erase the last failure",
              st.get("last", {}).get("outcome") == "ok"
              and st.get("last_failure", {}).get("outcome") == "failed", json.dumps(st)[:200])
        check("outcomes counted per reason",
              st.get("counts", {}).get("skipped:too_short") == 1
              and st.get("counts", {}).get("failed:key_missing") == 1, json.dumps(st.get("counts")))

        # Timeout is its own reason (in-process: the child is stubbed out).
        sys.path.insert(0, HOOKS_DIR)
        import transform_llm_output as _TT
        _real_run = _TT.subprocess.run

        def _timeout(*a, **k):
            raise _TT.subprocess.TimeoutExpired(cmd="tts_render.py", timeout=1)
        try:
            _TT.subprocess.run = _timeout
            oc, rs, nfo = _TT._voice_narration(
                _TT.L.campaign_dir({"cwd": campt}), {"session_id": "x"}, narration)
        finally:
            _TT.subprocess.run = _real_run
        check("timeout is a named failure carrying its budget",
              (oc, rs) == ("failed", "timeout") and nfo.get("timeout_s") == 40, "%s %s" % (rs, nfo))

        campd = _TT.L.campaign_dir({"cwd": build_fixture(os.path.join(root, "ttsunit"))})
        _real_renderer = _TT.RENDERER
        try:
            _TT.RENDERER = os.path.join(root, "does-not-exist.py")
            oc, rs, nfo = _TT._voice_narration(campd, {"session_id": "x"}, narration)
        finally:
            _TT.RENDERER = _real_renderer
        check("a missing renderer is named, and keeps the common event shape",
              (oc, rs) == ("failed", "renderer_missing") and nfo.get("timeout_s") == 40
              and nfo.get("renderer"), "%s %s" % (rs, nfo))

        def _ok_but_silent(*a, **k):
            return _TT.subprocess.CompletedProcess(args=[], returncode=0, stdout=b"", stderr=b"")
        try:
            _TT.subprocess.run = _ok_but_silent
            oc, rs, nfo = _TT._voice_narration(campd, {"session_id": "x"}, narration)
        finally:
            _TT.subprocess.run = _real_run
        check("renderer exiting 0 without producing audio is a failure, not a success",
              (oc, rs) == ("failed", "no_audio_file") and nfo.get("rc") == 0, "%s %s" % (rs, nfo))

        # The diagnosis is the LAST stderr line; tts_generate prints a retry warning
        # per attempt before it, so a head-clip keeps the noise and drops the answer.
        noisy = os.path.join(root, "noisy_renderer.py")
        with open(noisy, "w", encoding="utf-8") as fh:
            fh.write("import sys\n"
                     "sys.stderr.write('attempt 1 failed: HTTP 401 ' + 'x' * 400 + '\\n')\n"
                     "sys.stderr.write('ERROR: synthesis failed after 2 attempts\\n')\n"
                     "sys.exit(1)\n")
        try:
            _TT.RENDERER = noisy
            oc, rs, nfo = _TT._voice_narration(campd, {"session_id": "x"}, narration)
        finally:
            _TT.RENDERER = _real_renderer
        check("the child's LAST stderr line survives truncation (tail, not head)",
              (oc, rs) == ("failed", "exit_1")
              and "synthesis failed after 2 attempts" in (nfo.get("stderr") or ""),
              json.dumps(nfo)[:200])

        # An unwritable .banquier must not be silent: an empty journal is read by
        # tts_doctor.py as "the hook never ran here" — the opposite of the truth.
        if os.geteuid() != 0:
            campro = build_fixture(os.path.join(root, "ttsro"))
            bq = os.path.join(campro, ".banquier")
            os.makedirs(bq, exist_ok=True)
            os.chmod(bq, 0o500)
            try:
                out, err = run_hook("transform_llm_output.py", {
                    "cwd": campro, "session_id": "sess_ttsro", "response": narration,
                    "extra": {"model": "m"}}, env=tts_env)
            finally:
                os.chmod(bq, 0o700)
            check("an unwritable journal never breaks the turn",
                  isinstance(out, dict) and "__raw__" not in out and "Traceback" not in err,
                  (json.dumps(out)[:120] + " | " + err[-200:]))
            check("a lost journal write is announced, not swallowed",
                  "JOURNAL WRITE FAILED" in err, err[:200])
            check("and the underlying defect is still named on the only channel left",
                  "workspace_unwritable" in err, err[-200:])

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

        # ── 9. judge layer : anti-loop budget, on a draft the agency gate clears ──
        print("\n[9] mj_checkpoint — judge layer + anti-loop budget (max 2)")
        judge_resp = ("You hear the wind howl between the frozen stones of the forgotten old "
                      "temple, and the smell of wet ash reaches the doorway.")
        out1, code1 = run_cli("mj_checkpoint.py", args=["--draft", judge_resp], cwd=campj,
                              env={"MGM_JUDGE_MOCK": VIOL})
        check("1st attempt : violation reported (exit 1)", code1 == 1 and "AGENTIVITE" in out1, out1[:80])
        out2, code2 = run_cli("mj_checkpoint.py", args=["--draft", judge_resp], cwd=campj,
                              env={"MGM_JUDGE_MOCK": VIOL})
        check("2nd attempt : FORCED to avoid looping (exit 0)", code2 == 0 and "FORCED" in out2, out2[:80])
        outok, codeok = run_cli("mj_checkpoint.py", args=["--draft", judge_resp], cwd=campj,
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

        # ── 15. deterministic agency gate (AGENCY-01/02/03) ──────────────────
        print("\n[15] agency_gate — deterministic AGENCY-01/02/03")
        sys.path.insert(0, HOOKS_DIR)
        import agency_gate as AG  # noqa: E402

        blocked, fp = 0, []
        for label, draft, declared, rules in AGENCY_VIOLATIONS:
            rep = AG.analyze(draft, declared, PC_NAMES)
            got = [v["regle"] for v in rep["violations"]]
            ok = (not rep["ok"]) and all(r in got for r in rules)
            blocked += 1 if ok else 0
            check("blocks %s" % label, ok, "%s → %s" % (draft[:60], got))
        for label, draft, declared in AGENCY_LEGITIMATE:
            rep = AG.analyze(draft, declared, PC_NAMES)
            if not rep["ok"]:
                fp.append((label, [v["regle"] for v in rep["violations"]]))
            check("passes (tuned) %s" % label, rep["ok"],
                  "%s → %s" % (draft[:60], [v["regle"] for v in rep["violations"]]))
        check("no false positive on the tuned table", not fp, json.dumps(fp)[:160])
        check("violation recall is total on the corpus table",
              blocked == len(AGENCY_VIOLATIONS), "%d/%d" % (blocked, len(AGENCY_VIOLATIONS)))

        held_fp = []
        for label, draft, declared in AGENCY_HELDOUT:
            rep = AG.analyze(draft, declared, PC_NAMES)
            if not rep["ok"]:
                held_fp.append((label, [v["regle"] for v in rep["violations"]]))
            check("passes (held-out) %s" % label, rep["ok"],
                  "%s → %s" % (draft[:60], [v["regle"] for v in rep["violations"]]))
        rate = 100.0 * len(held_fp) / max(1, len(AGENCY_HELDOUT))
        print("     measured false-positive rate: %.1f%% (%d/%d HELD-OUT narrations blocked) — "
              "the tuned table is excluded, it cannot falsify the lexicons it produced"
              % (rate, len(held_fp), len(AGENCY_HELDOUT)))
        check("false-positive rate is zero on the HELD-OUT table", not held_fp,
              json.dumps(held_fp)[:200])

        # An ambiguous construction is NOT decided here: it is handed to the LLM judge.
        amb = AG.analyze("Tu as le pas lourd de celui qui n'a pas dormi.", "", PC_NAMES)
        check("ambiguous verb → no deterministic verdict (handed to the judge)",
              amb["ok"] and amb["ambiguous"] >= 1, json.dumps(amb)[:120])
        collide = AG.analyze("Berthe regarde la porte.", "", ["Regarde"])
        check("PC name colliding with a verb is not used as an anchor", collide["ok"],
              json.dumps(collide)[:120])

        # Shipped campaign sheets carry two-word names ("Oryn Ashveil"), tokens are single words.
        two = AG.analyze("Oryn kneels by the fire and draws his blade.", "", ["Oryn Ashveil"])
        check("multi-word PC name : each part anchors (first name)", not two["ok"],
              json.dumps(two)[:140])
        full = AG.analyze("Oryn Ashveil s'agenouille devant le feu.", "", ["Oryn Ashveil"])
        check("multi-word PC name : the scan walks over the other part", not full["ok"],
              json.dumps(full)[:140])
        obj = AG.analyze("Berthe tend le journal à Oryn Ashveil.", "", ["Oryn Ashveil"])
        check("PC name in object position is not a PC action", obj["ok"], json.dumps(obj)[:140])
        check("English `you` only anchors in subject position",
              AG.analyze("Behind you stands a hooded figure.", "", PC_NAMES)["ok"]
              and not AG.analyze("You stand by the fire.", "", PC_NAMES)["ok"])
        check("a clause break restores the subject reading of `you`",
              not AG.analyze("Berthe steps back, you follow her.", "", PC_NAMES)["ok"])
        check("conjunction inheritance stops at a determiner",
              AG.analyze("Tu entends un bruit et le regard de Berthe se lève.", "", PC_NAMES)["ok"]
              and not AG.analyze("Tu ouvres la porte et franchis le seuil.", "", PC_NAMES)["ok"])
        mk = AG.analyze("You make your way across the bridge.", "", PC_NAMES)
        check("« make » is not whitelisted as perception", mk["ambiguous"] >= 1, json.dumps(mk)[:140])

        # ── 15b. end-to-end : the gate is independent of the LLM judge ───────
        print("\n[15b] mj_checkpoint — agency gate with the judge switched OFF")
        campag = build_fixture(os.path.join(root, "agency"))  # NO meta.hooks.judge at all
        noj = {"MGM_JUDGE_ACTIF": "0", "MGM_JUDGE_MODEL": "", "OPENROUTER_API_KEY": "",
               "MGM_JUDGE_API_KEY": ""}
        BAD = "Tu t'approches de la pierre et tu poses la main dessus."
        out, code = run_cli("mj_checkpoint.py", args=["--draft", BAD], cwd=campag, env=noj)
        check("judge OFF : PC action refused with a rule ID (exit 1)",
              code == 1 and "AGENCY-01" in out, out[:120])
        check("refusal names the offending sentence", "poses la main" in out, out[:120])
        out, code = run_cli("mj_checkpoint.py", args=[
            "--draft", "La lanterne vacille. Tu entends un craquement dans l'escalier."],
            cwd=campag, env=noj)
        check("judge OFF : perception-only draft passes (exit 0)", code == 0 and "✅" in out, out[:120])
        out, code = run_cli("mj_checkpoint.py", args=[
            "--draft", "Tu t'approches de la pierre. Le froid monte du sol.",
            "--declared", "je m'approche de la pierre"], cwd=campag, env=noj)
        check("judge OFF : declared action executed passes and cites the declaration",
              code == 0 and "je m'approche de la pierre" in out, out[:160])
        # The judge approving is not enough: the deterministic verdict is not negotiable.
        out, code = run_cli("mj_checkpoint.py", args=["--draft", BAD], cwd=campag,
                            env={"MGM_JUDGE_MOCK": json.dumps({"ok": True}),
                                 "MGM_JUDGE_ACTIF": "1", "MGM_JUDGE_MODEL": "x/y"})
        check("judge says OK : agency violation STILL refused (non-fail-open)",
              code == 1 and "AGENCY-01" in out, out[:120])
        out, code = run_cli("mj_checkpoint.py", args=["--file", os.path.join(root, "absent.txt")],
                            cwd=campag, env=noj)
        check("unreadable draft : refused instead of waved through", code == 1, out[:120])
        # End to end with a two-word sheet name, as both shipped campaigns have.
        write_json(os.path.join(campag, "characters", "404.json"), {
            "meta": {"character_name": "Oryn Ashveil", "discord_id": "404"},
            "stats": {}, "inventory": [], "health": {"hp_current": 10, "hp_max": 10}})
        out, code = run_cli("mj_checkpoint.py", args=[
            "--draft", "Oryn Ashveil s'agenouille devant le feu."], cwd=campag, env=noj)
        check("two-word sheet name : third-person PC action refused",
              code == 1 and "AGENCY-01" in out, out[:120])
        out, code = run_cli("mj_checkpoint.py", args=[
            "--draft", "Berthe tend le journal à Oryn Ashveil, la main tremblante."],
            cwd=campag, env=noj)
        check("two-word sheet name : PC as object still passes", code == 0, out[:120])
        # A gate bug must refuse, not approve: it does not get to be the reason a turn passes.
        import io, contextlib  # noqa: E402
        import mj_checkpoint as MC  # noqa: E402
        boom = MC.A.analyze
        MC.A.analyze = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom"))
        buf = io.StringIO()
        try:
            with contextlib.redirect_stdout(buf):
                ccode, _rep = MC.run_agency_gate(BAD, "", L.campaign_dir({"cwd": campag}),
                                                 {"session_id": "crash"}, "m")
        finally:
            MC.A.analyze = boom
        check("agency gate crash : refused, escape hatch named",
              ccode == 1 and "MGM_AGENCY_GATE" in buf.getvalue(), buf.getvalue()[:140])

        # ── 15c. anti-loop budget + operator escape hatch ────────────────────
        print("\n[15c] agency gate — loud forced pass and escape hatch")
        campab = build_fixture(os.path.join(root, "agencybudget"))
        budget = dict(noj); budget["MGM_AGENCY_MAX_ATTEMPTS"] = "2"
        out1, c1 = run_cli("mj_checkpoint.py", args=["--draft", BAD], cwd=campab, env=budget)
        out2, c2 = run_cli("mj_checkpoint.py", args=["--draft", BAD], cwd=campab, env=budget)
        check("attempt 1/2 refused (exit 1)", c1 == 1 and "attempt 1/2" in out1, out1[-80:])
        check("attempt 2/2 forced, LOUD and named (exit 0)",
              c2 == 0 and "FORCED" in out2 and "AGENCY-01" in out2, out2[:120])
        check("forced pass traced as feed-forward (pending)",
              _pending_has_text(os.path.join(campab, ".banquier", "pending-gate.json")))
        sbag = json.load(open(os.path.join(campab, ".banquier", "scoreboard.json"), encoding="utf-8"))
        forced = sum(int(m.get("forces", 0)) for m in sbag.values() if isinstance(m, dict))
        check("forced pass counted in the scoreboard", forced == 1, json.dumps(sbag)[:160])
        out3, c3 = run_cli("mj_checkpoint.py", args=["--draft", BAD], cwd=campab, env=budget)
        check("budget reset after a forced pass (no permanent amnesty)",
              c3 == 1 and "attempt 1/2" in out3, out3[-80:])
        esc = dict(noj); esc["MGM_AGENCY_GATE"] = "off"
        out4, c4 = run_cli("mj_checkpoint.py", args=["--draft", BAD], cwd=campab, env=esc)
        check("MGM_AGENCY_GATE=off unblocks the campaign, loudly",
              c4 == 0 and "AGENCY GATE DISABLED" in out4, out4[:120])
        check("gate default is ON", AG.enabled({}) and not AG.enabled({"MGM_AGENCY_GATE": "off"}))

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
