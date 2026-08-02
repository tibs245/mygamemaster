# 09 — Runtime Integration (patch PREPARED, NOT applied)

> **Status: BRANCHING PROPOSAL — NOTHING IS APPLIED.** This file describes, in the form of
> **ready-to-copy diffs**, how to wire the "living world" engine (`worldlib.py`,
> `geo_query.py`, `world_tick.py`, `causal_propagate.py`, `scene_brief.py`) into the **existing
> game loop**. **No runtime file is modified by this document**: the patches below
> are to be applied **manually and deliberately** by the admin, outside the scope of
> implementation agents (cf. `08`§9.3 and invariant `08`§14.3 — non-destructive).
>
> Targets: Python **3.11**, **pure stdlib**, **fail-open** strict in the game loop.
> In case of divergence with `08-implementation-contract.md`, **the contract takes precedence**; this file
> merely **wires up** what the contract has frozen.
>
> **Golden rule of wiring:** *a failing branch must NEVER break a turn or a wrap-up.* Each hook point is (a) **behind a toggle** `world.json > meta.hooks`,
> (b) **fail-open** (any failure → silent no-op + `stderr`), (c) **dry-run by default** for
> anything that writes.

---

## 0. Overview of the four branches

| # | Where | What | When | Toggle `meta.hooks` | Fails how |
|---|---|---|---|---|---|
| **B1** | `hooks/pre_llm_call.py` | injects the **SCENE BRIEF** (`scene_brief.py`) into the `context` | at **each turn** | `brief_scene` (default `false`) | **fail-open** (no-op) |
| **B2** | `scripts/close_session.py` | runs `world_tick.py post --apply` (reconciliation) | at **wrap-up** | `tick_post` (default `false`) | **non-blocking** (ALERT) |
| **B3** | skill `mygamemaster-session` (`SKILL.md`) | runs `world_tick.py pre` (projection + staging) | at **session start** | `tick_pre` (default `false`) | **fail-open** (skip) |
| **B4** | `hooks/_lib.py` `hooks_cfg()` | **declares** the three toggles above | — | — | defaults `false` |

> **Recommended application order:** B4 first (otherwise toggles are unknown → everything stays
> `false` by default, thus inactive), then B1/B2/B3 in any order. All four are
> **independent**: you can enable just one.
>
> **Default activation = OFF.** Unlike the five historical toggles in `hooks_cfg`
> (`injection_state`, `steward_persists`, … default `True`), the **three new** living world toggles
> are **`False` by default**: the engine is an **explicit opt-in** per campaign
> (you need `geo.json` + `actors.json` present and aligned for it to make sense). A campaign that
> doesn't yet have its spatial graph continues **exactly** as today, with zero side effects.

---

## 1. B4 — Declare toggles in `hooks/_lib.py` (PREREQUISITE)

`meta.hooks` is read by **only one** point: `_lib.hooks_cfg(world)`. We **add** three keys
(default `False`). This is the single source of truth for toggles; B1/B2/B3 reuse it.

**File:** `modules/gaming/mygamemaster/hooks/_lib.py`
**Function:** `hooks_cfg` (≈ lines 143–153).

```diff
 def hooks_cfg(monde):
     """Toggles meta.hooks with defaults (all enabled, JSON guard advisory)."""
     h = meta(monde).get("hooks")
     h = h if isinstance(h, dict) else {}
     return {
         "injection_etat": h.get("injection_etat", True),
         "banquier_persiste": h.get("banquier_persiste", True),
         "garde_json_strict": h.get("garde_json_strict", False),
         "snapshot_fin_session": h.get("snapshot_fin_session", True),
         "auto_commit": h.get("auto_commit", True),
+        # ── Living world (explicit opt-in, default False; cf. docs/living-world/09) ──
+        # B1 : injection of SCENE BRIEF via pre_llm_call (scene_brief.py).
+        "brief_scene": h.get("brief_scene", False),
+        # B2 : world_tick.py post --apply at wrap-up (close_session.py).
+        "tick_post": h.get("tick_post", False),
+        # B3 : world_tick.py pre at session start (skill mygamemaster-session).
+        "tick_pre": h.get("tick_pre", False),
     }
```

> **Backward compat guaranteed:** a campaign whose `meta.hooks` does not mention these keys (real case:
> `the-birth-of-a-king` has `meta.hooks = {}`) gets `brief_scene=False`, `tick_post=False`,
> `tick_pre=False` → behavior **identical** to current. No data migration required.

---

## 2. B1 — Inject SCENE BRIEF in `pre_llm_call.py`

### 2.1 Intention

At each turn, **before** the GM's response, call `scene_brief.py <campaign> <location_id>` and
**add** its `text` to the already-injected `context` (time, inventories, NPCs). This is exactly
the extension described in `05`§5: *one extra line, rest of the loop unchanged.*

### 2.2 The lock: where does `location_id` come from?

`scene_brief.py` requires the **location id of the current scene**. **Fact verified on the real
campaign:** the PC `actor:ruby` is **reserved** (contract §2.5) and **is NOT in
`actors.json`** → `geo_query where actor:ruby` returns `{}`. We **cannot therefore** deduce
the player's position from simulated actors. And it's **intentional**: the player decides where they are
(SKILL.md « Default location at startup » l. 602–611) — the code must never
invent it.

**Fail-open resolution, by priority order (first match wins):**

1. **Persisted scene hint** `.steward/scene-<session_id>.json` → key `"lieu_id"`. This hint
   is **written by B3** at session start (resumption location) and **refreshed** by the
   `post_tool_call` hook when the GM declares a `move` (outside scope of this doc, mentioned in
   `07`). This is the **nominal** source.
2. **Environment variable** `MGM_SCENE_LIEU` (deployment/test escape hatch).
3. **Otherwise → do NOT inject the brief** (silent skip). We **never guess** a default location. The turn proceeds as today (state as historical authority remains injected).

> Consequence: as long as B3 (or a played `move`) hasn't placed a location hint, B1 is
> **inert** — which is the safe behavior and respects player agency.

### 2.3 The patch

**File:** `modules/gaming/mygamemaster/hooks/pre_llm_call.py`

**(a) Extend `handle()` to call the brief** (≈ lines 36–42, in the block that assembles
`parts`):

```diff
     parts = []
     pending = L.take_pending(camp, payload)  # read AND cleared → injected once
     if pending:
         parts.append(pending)
     parts.append(build_context(camp, monde))
+    if cfg.get("brief_scene"):
+        brief = build_scene_brief(camp, payload, monde)  # fail-open: "" if unavailable
+        if brief:
+            parts.append(brief)
     ctx = "\n\n".join(p for p in parts if p)
     return {"context": ctx} if ctx else {}
```

**(b) Add the hook function** (new function, place after `build_context`,
≈ after line 58). It is **strictly fail-open**: any failure → `""` (turn continues).

```diff
+def build_scene_brief(camp, payload, monde):
+    """B1 — calls scene_brief.py for the current location and returns its text.
+    ABSOLUTE FAIL-OPEN: any failure (no geo.json, no location hint, script
+    missing, timeout, broken JSON) → "" (turn proceeds without the brief).
+    Current location is NEVER guessed: read from persisted hint/ENV, else skip.
+    """
+    try:
+        lieu_id = _scene_lieu_courant(camp, payload)
+        if not lieu_id:
+            return ""  # player decides where they are — don't invent a default location
+        script = _scripts_dir() / "scene_brief.py"
+        if not script.exists():
+            return ""
+        proc = subprocess.run(
+            [sys.executable, str(script), str(camp), str(lieu_id)],
+            capture_output=True, text=True, timeout=8,
+        )
+        # scene_brief.py: exit 0 ALWAYS (fail-open), 2 if campaign not found.
+        if proc.returncode != 0:
+            return ""
+        return (proc.stdout or "").strip()
+    except Exception:
+        return ""  # never break a turn for a branch
+
+
+def _scene_lieu_courant(camp, payload):
+    """Scene location hint: .banquier/scene-<sid>.json > 'lieu_id', else ENV
+    MGM_SCENE_LIEU, else None. Never guesses."""
+    try:
+        sid = str(payload.get("session_id") or "default")
+        hint = L.load_json(camp / ".banquier" / ("scene-%s.json" % sid))
+        if isinstance(hint, dict) and hint.get("lieu_id"):
+            return str(hint["lieu_id"])
+    except Exception:
+        pass
+    env = os.environ.get("MGM_SCENE_LIEU", "").strip()
+    return env or None
+
+
+def _scripts_dir():
+    """Directory of living-world scripts (sibling of hooks folder)."""
+    from pathlib import Path
+    return Path(os.path.dirname(os.path.abspath(__file__))).parent / "scripts"
```

**(c) Imports** — at the top of the file (≈ lines 12–16), add `subprocess` (the others,
`os`/`sys`, are already present):

```diff
 import os
+import subprocess
 import sys

 sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
 import _lib as L  # noqa: E402
```

### 2.4 Guarantees of B1

- **Toggle OFF (default)** → the block `if cfg.get("brief_scene")` is skipped: **zero** calls,
  **zero** cost, behavior identical to current.
- **Admin bypass / ⏸️** → `handle()` already returns `{}` **before** reaching the `parts` block
  (line `if bypass or not cfg["injection_state"]: return {}`): the brief is thus **not** injected
  in pause/admin mode. Consistent.
- **`scene_brief.py` is itself fail-open** (contract §9.3: exit 0 always, minimal brief on
  failure). The double safeguard (here + in the script) makes the injection harmless.
- **8 s timeout** aligned with the judge's network calls (`_lib.http_json` timeout 8). In practice
  `scene_brief` is purely local (reads `geo.json`/`actors.json`/`scheduled_events.json`)
  so well within.
- **No writes**: B1 only **reads** and **injects** text.

---

## 3. B2 — Run `world_tick.py post` at wrap-up (`close_session.py`)

### 3.1 Intention

At wrap-up, **after** the existing validations (json · distances · cross-check · clock) and
**before** proposing the commit, execute `world_tick.py post --apply`: reconcile the planned
**intentions** with what the player actually **did**, renew perturbed intentions, propagate
player actions (the player becomes a **cause**). This is the step `▣ world_tick.py POST` from
diagram `06`§1.

### 3.2 Where, exactly

`close_session.py` chains its guards via the `launch(script, args)` helper (subprocess,
capture exit/stdout/stderr) in `execute()`. The current step 4 is `clock.py` (≈ line 218).
We insert a **step 5** right after, **guarded by the toggle `tick_post`**, and **non-blocking**
(a reconciliation that fails must not prevent wrap-up — it just **alerts**).

### 3.3 The patch

**File:** `modules/gaming/mygamemaster/scripts/close_session.py`

**(a) In `executer()`**, after step 4 `clock` (≈ line 218):

```diff
     # 4. clock --dry-run (ALERT)
     res_clock = lancer("clock.py", [str(campagne)])

+    # 5. world_tick post --apply (LIVING WORLD) — reconciliation. NON-BLOCKING:
+    #    guarded by meta.hooks.tick_post AND by presence of actors.json.
+    #    A failure here NEVER prevents wrap-up (just an alert).
+    res_tick = _tick_post_si_actif(campagne, monde, num)
+
     # Check pipeline ~10 points (unless JSON broken: we don't read further)
     points = []
     if res_json["exit"] == 0:
         points = check_pipeline(campagne, session_path, monde,
                                 res_check, res_clock)
```

**(b) Still in `executer()`**, wire the alert (≈ after the existing `alertes` block,
just before `ok = len(blocs) == 0`):

```diff
     alertes = []
     if res_dist["exit"] == 1:
         alertes.append("validator-distances : warnings (human review)")
     for p in points:
         if not p["bloquant"] and not p["ok"]:
             alertes.append(f"{p['id']} {p['label']} — {p['detail']}")
+    # Living world: reconciliation is informative, never blocking.
+    if res_tick.get("lance"):
+        if res_tick["exit"] == 0:
+            alertes.append("world_tick post : world reconciled (see detail).")
+        elif res_tick["exit"] == 1:
+            alertes.append("world_tick post : reconciliations applied "
+                           "(perturbed intentions renewed / propagations).")
+        else:
+            alertes.append("world_tick post : non-blocking failure "
+                           f"(exit {res_tick['exit']}) — reconciliation to replay by hand.")

     ok = len(blocs) == 0
```

**(c) Expose the exit in `etapes` and the sub-report** (in the `return {…}` of `executer`):

```diff
         "etapes": {
             "validate_json": res_json["exit"],
             "validator_distances": res_dist["exit"],
             "check_session": res_check["exit"],
             "clock": res_clock["exit"],
+            "world_tick_post": res_tick.get("exit") if res_tick.get("lance") else None,
         },
```

```diff
         "_sous_rapports": {
             "validate_json": res_json,
             "validator_distances": res_dist,
             "check_session": res_check,
             "clock": res_clock,
+            "world_tick_post": res_tick,
         },
```

**(d) New hook function** (place near `lancer`, ≈ after line 67):

```diff
+def _tick_post_si_actif(campagne: Path, monde: dict, num: int) -> dict:
+    """B2 — runs `world_tick.py post --apply` if meta.hooks.tick_post is true AND
+    if actors.json exists. NON-BLOCKING: returns a trace dict, never raises.
+    {'lance':bool,'exit':int,'stdout':str,'stderr':str,'raison':str}."""
+    hooks = (monde.get("meta") or {}).get("hooks") or {}
+    if not hooks.get("tick_post", False):
+        return {"lance": False, "raison": "toggle meta.hooks.tick_post=false"}
+    if not (campagne / "actors.json").exists():
+        return {"lance": False, "raison": "actors.json missing (living world not initialized)"}
+    # ⚠️ world_tick.py has SUB-COMMANDS: the verb 'post' comes FIRST,
+    #    before the positional <campagne> (cf. §3.4). DO NOT write [campagne, "post", …].
+    r = lancer("world_tick.py",
+               ["post", str(campagne), "--session", str(num), "--apply"])
+    # Usage error (exit 2) or script missing (127) → we do NOT raise: alert above.
+    return {"lance": True, "exit": r["exit"], "stdout": r["stdout"],
+            "stderr": r["stderr"], "raison": ""}
```

### 3.4 ⚠️ Argument order trap (must respect)

`close_session.py` usually calls scripts **without** sub-commands
(`validate_json.py <campagne>`). `world_tick.py`, on the other hand, has **sub-commands**: the verb
(`pre`/`post`) comes **before** the positional `campagne`. The **exact** form expected by its
parser is:

```
world_tick.py post <campagne> --session <N> --apply
```

So the list passed to `lancer` is **`["post", str(campagne), "--session", str(num),
"--apply"]`** — the **verb first** (already written this way in patch (d) above). Writing
`[str(campagne), "post", …]` would fail argparse (`campagne` interpreted as verb) → exit 2
→ non-blocking alert, but reconciliation **not played**. This is the only subtlety of B2.

### 3.5 CLI output (optional but recommended)

In `main()` of `close_session.py`, after the line `clock (dry-run) : exit …` (≈ line 341):

```diff
     print(f"  clock (dry-run)      : exit {et['clock']}")
+    if et.get("world_tick_post") is not None:
+        print(f"  world_tick post      : exit {et['world_tick_post']} (living world)")
```

### 3.6 Guarantees of B2

- **Toggle OFF (default)** → `_tick_post_si_actif` returns `{"lance": False}` immediately:
  wrap-up **identical** to current.
- **`actors.json` missing** → same, clean skip (a campaign without living world is never
  penalized).
- **Never blocking**: the result of `world_tick post` feeds **only** `alertes`, **never**
  `blocs`. The verdict `ok`/exit code of `close_session.py` is **unchanged** by B2. (A reconciliation
  failure is a GM matter, not a wrap-up refusal — consistent with the ALERT handling of `clock.py`, P5.)
- **`--apply`** is deliberate here (wrap-up **is** the moment to write `actors.json` /
  `evenements_programmes.json`). The timestamped snapshot (`on_session_end.py`) and the commit (proposed)
  capture these writes just after. Writes **only** to allowed files
  (contract §0.2 / §14.3) — `world_tick post` doesn't touch `world.json`/`events.json`.

---

## 4. B3 — Session-start hook (`world_tick.py pre`)

### 4.1 Intention

At **session start**, **before** the first narration, project the world to the present: resolve
due intentions, make "warm" actors think, calculate **intersections** with the player's cone,
promote to **hot**, and give the GM a **LIVING WORLD BRIEFING**. This is the step `▣ world_tick.py PRE`
from diagram `06`§1 and `06`§3.

### 4.2 Why in the skill and not in a hook

There is **no** runtime hook for "session start" on the pre-narration side (hooks are
`pre_llm_call` / `pre_tool_call` / `post_tool_call` / `transform_llm_output` / `on_session_end`).
The session start is a **procedural moment** driven by the skill `mygamemaster-session`. We thus add
a **procedural step** (instruction to the GM), not hook code. This aligns with the
existing protocol "Starting a new session" (`SKILL.md` l. 602–611).

### 4.3 The patch (procedure, in `SKILL.md`)

**File:** `modules/gaming/mygamemaster/SKILL.md`
**Section:** "Protocol — Starting a new session" (≈ l. 605–611).

We **add a step 0** (before the existing steps), **guarded** by `meta.hooks.tick_pre`:

```diff
 **Protocol — Starting a new session:**
+0. ✅ **(Living world — if `world.json > meta.hooks.tick_pre` = true AND `actors.json` present)**
+   Before any narration, run the **world projection**:
+   ```
+   python3 <scripts>/world_tick.py pre <campagne> --apply
+   ```
+   - Read the returned **LIVING WORLD BRIEFING** (upcoming intersections, actors promoted to "hot",
+     LOD distribution): this is the **opening context** that the world produced **without you**.
+   - **DO NOT narrate the briefing as-is** to the player: it's a GM sheet. Use it to
+     know *which clocks are ringing* and *who crosses the player's path*.
+   - `--apply` persists advances (`actors.json`, `evenements_programmes.json`); if unsure, run
+     **without** `--apply` first (dry-run, writes nothing).
+   - **Player cone (optional):** if you know where the player plans to go, pass it as
+     `--cone -` (JSON `{"lieux":["lieu:…"],"fenetre":[T0,T1]}` on stdin) to **sharpen** the
+     intersections. Without a cone, the projection is still valid (global intersections).
+   - **FAIL-OPEN:** if the script fails / `geo.json` or `actors.json` missing → **ignore** and
+     start normally (living world is a bonus, never a game prerequisite).
+   - **Scene hint (for B1):** once the player has **said where they are** (steps 2–3
+     below), write their location in `.banquier/scene-<session_id>.json` (`{"lieu_id":"lieu:…"}`)
+     so that the SCENE BRIEF per turn (B1) targets the right place. NEVER write this hint
+     **before** the player has chosen their position.
 1. ✅ Load the `situation_initiale` as **general context only** (what happened, where the world stands)
 2. ✅ **Do NOT infer the PC's exact position**. The player decides where they are and what they do.
 3. ✅ If the player's first message is an action without location info → ask them: "Where are you? What exactly are you doing?"
```

> `<scripts>` = `modules/gaming/mygamemaster/scripts/` ; `<campagne>` = current campaign folder
> (cf. skill README, path conventions). In containerized deployment, these are paths
> mounted in the campaign container.

### 4.4 Guarantees of B3

- **Toggle OFF (default)** → step 0 is explicitly conditioned "if `tick_pre` = true":
  a campaign without living world follows the protocol **unchanged** (steps 1→6 historical).
- **Respects player agency:** step 0 **does not set** the PC's position; it projects
  the **world** (actors, clocks). The player's position remains their choice (steps 2–3),
  **then** only recorded as a scene hint. The order is locked to avoid
  reintroducing the "default location" pitfall.
- **`world_tick pre` is fail-open** (verified: without `evenements_programmes.json`, it prints a
  minimal briefing, exit 0). The instruction "ignore if fails" doubles this safeguard procedurally.
- **Optional cone:** aligns with contract §7.1 (`--cone <file|->`) and the script's `_charger_cone_arg`
  (JSON file or stdin, `None` if absent → global projection).

---

## 5. Summary of toggles `world.json > meta.hooks`

Block to **add** in a campaign's `world.json` to **activate** the living world (all three
`false` = current behavior; set them to `true` one by one, in order B4→B3→B2→B1):

```json
{
  "meta": {
    "hooks": {
      "brief_scene": false,
      "tick_post": false,
      "tick_pre":  false
    }
  }
}
```

| Toggle | Branch | Effect when `true` | Effect when `false` (default) |
|---|---|---|---|
| `brief_scene` | **B1** `pre_llm_call.py` | injects SCENE BRIEF per turn (if a scene location is known) | no calls, historical context only |
| `tick_post` | **B2** `close_session.py` | `world_tick post --apply` at wrap-up (reconciliation, alert) | wrap-up unchanged |
| `tick_pre` | **B3** skill session | `world_tick pre --apply` at session start (GM briefing) | session start unchanged |

> **All defaults are `false`** (cf. B4): *wiring the engine is an explicit,
> reversible choice per campaign*. Disable = set the toggle to `false` (no data purge:
> `geo.json`/`actors.json`/`evenements_programmes.json` remain in place, simply ignored by
> the loop).
>
> **Recommended joint activation:** `tick_pre` + `brief_scene` form the pair "the world
> catches up on time at session start, then each turn sees the right window". `tick_post` closes the
> loop (the player becomes a cause). You can activate `tick_pre` alone to test without touching
> the per-turn flow.

---

## 6. What is NOT touched (branch invariants)

- **No runtime file modified by this document.** The diffs above are **proposed**, to
  be applied manually. (Aligns with task instructions and invariant `08`§14.3.)
- **`world.json`, `npcs.json`, `events.json`** remain **read-only, never written** by the
  branches. The only writes (B2/B3 `--apply`) target `actors.json` and
  `evenements_programmes.json`, via `world_tick.py` (which already respects this rule).
- **The turn loop is intact** except for B1: `post_tool_call` (ledger + auto-commit),
  `transform_llm_output` (Steward + judge), `pre_tool_call` — **none** is modified. B1 only adds
  **one** call **after** the historical context (`05`§5: "one extra line").
- **Fail-open everywhere in the game loop** (B1, B3); **non-blocking** outside the loop (B2). No
  branch can fail a turn or refuse wrap-up.
- **Pure stdlib**: B1 only adds `subprocess` (already used everywhere in `_lib`/`close_session`).
  No external dependencies introduced.

---

## 7. Application checklist (for the admin)

1. ☐ **B4** — patch `_lib.hooks_cfg` (3 toggles, default `False`). *Without this, nothing activates.*
2. ☐ **B3** — patch `SKILL.md` (step 0 at session start, guarded by `tick_pre`).
3. ☐ **B2** — patch `close_session.py` (step 5 `world_tick post`, **verb first**:
   `["post", str(campagne), …]`, non-blocking). Re-read **§3.4 (argument trap)**.
4. ☐ **B1** — patch `pre_llm_call.py` (`import subprocess` + `build_scene_brief` +
   `_scene_lieu_courant` + block in `handle`, guarded by `brief_scene`).
5. ☐ Activate **progressively** in `world.json > meta.hooks`: `tick_pre` → verify session-start briefing;
   `brief_scene` → verify per-turn injection; `tick_post` → verify reconciliation at wrap-up.
6. ☐ Run existing **tests** (`python3 -m unittest discover` in `scripts/`) **unchanged**:
   the branches don't alter the engine scripts, only their **callers**.

> **Final reminder:** this file is a **proposal**. As long as the diffs are not applied
> **and** the toggles are not set to `true`, the runtime behaves **exactly** as before.
