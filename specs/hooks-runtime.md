# Spec — Hooks runtime MJ Tonnerre

> **Goal**: make **systematic and inviolable** mechanisms that were previously dependent on
> the model's goodwill (Steward report, verbosity, traceability). We move them to the
> **Hermes runtime** via its *event hooks* — scripts executed by the gateway at each
> event, both in CLI and Discord gateway.
>
> Core objective: **offload weak models** (e.g., `deepseek-v4-flash`) from mechanical tasks
> so they can focus on narration, and **improve reliability**.

Official reference (to be kept, see README):
[Event Hooks — Hermes](https://hermes-agent.nousresearch.com/docs/user-guide/features/hooks).

---

## 1. What the Hermes runtime actually allows

Hermes declares shell hooks in `config.yaml` under the key `hooks:`. At each event, the
gateway **spawns a subprocess**, sends it a **JSON payload on stdin**, and reads a **JSON on
stdout** to decide what comes next. Events used here:

| Event | Trigger | Power exploited |
|---|---|---|
| `pre_llm_call` | 1×/message, before tool loop | **inject context** (`{"context": "…"}`) — prefixed to message, ephemeral (not persisted) |
| `pre_tool_call` | before a tool (filtered by `matcher` regex) | **block** (`{"action":"block","message":"…"}`) → model receives refusal and **must adapt** |
| `post_tool_call` | after a tool | observe (logging, snapshot, deltas) |
| `transform_llm_output` | after tool loop, **before delivery** to player | **rewrite/augment** response (`{"response":"…"}`) |
| `on_session_end` | end of session | snapshot, archiving |

**Structural constraint** (verified in the docs): `transform_llm_output` is *rewrite-only*
— it **cannot restart** the LLM. The only "refuses → model tries again" mechanism is
`pre_tool_call` (model-driven retry on **a tool call**). Therefore:

- we **augment** the response downstream (`transform_llm_output`) and upstream (`pre_llm_call`);
- we only **block/force a correction** at the level of a **mutation** (`pre_tool_call`).

---

## 2. Deterministic boundary — major design decision

The real data model imposes a boundary that must be respected to avoid **false rejections**
(worse than the original problem):

| Real data | Form | Consequence |
|---|---|---|
| `characters/<id>.json > inventaire` | **array of free strings** (`"15 silver crowns"`, `"Rations (~1 day…)"`) | no `{name, qty}` → a check "does they have object X?" is **fuzzy** (substring at best) |
| `meta.temps.regime` | often `"Narratif"` — "the GM estimates durations" | **time/travel** checks are **not hard** |
| `npcs.json > established_facts / connaissances_privees` | arrays of free strings | knowledge check is **fuzzy** |

**Golden rule: a hook blocks ONLY on unambiguous deterministic data.** Three levels:

| Level | Mechanism | Action | False positive risk |
|---|---|---|---|
| **T1 — Hard** | JSON integrity / schema on write (`pre_tool_call`/`post_tool_call`), CSV traceability, state injection (read-only), verbosity, admin bypass/⏸️ | blocks (integrity) / augments / observes | **null** |
| **T2 — Factual** | "Persisted" report calculated from the **real diff** of session files | augments response with what **actually** changed | null (we report the fact, not a judgment) |
| **T3 — Judgment** | transactional consistency on free-text, agentivity, conduct | **narrow-scope LLM judge** (§10): soft on Steward (bias toward VALID), strict on conduct | managed by bias-toward-valid + fail-open |

> Game logic blocking **"nonexistent object"** becomes *hard* **after migration** to a
> structured inventory (`{name, qty, type}`). This is the path to "Level 4" of the Steward SKILL.
> See §7.

What each initial request concretely becomes:

- *"Steward validates systematically"* → **T1** integrity (blocks broken JSON) + **T2**
  systematic Persisted report. The **judgment** of consistency remains with the GM but becomes **visible
  and traced**.
- *"Refuses nonexistent object and explains"* → **T3 advisory** by default (⚠️ annotation);
  **hard** only in strict mode + structured data (§7).
- *"Automatic verbosity"* → **T1**: `transform_llm_output` reads `meta.verbosite` and formats.
- *"CSV traceability"* → **T1**: never dependent on the LLM.
- *"Admin bypass / ⏸️"* → **T1**: short-circuit in all augmentation hooks.

---

## 3. Hooks map

```
                 ┌─────────────────────── game turn ───────────────────────┐
Discord message →│ pre_llm_call → [loop: pre_tool_call → tool → post_tool_call]* → transform_llm_output │→ response
                 └────────────────────────────────────────────────────────────┘
                         │                    │            │                     │
   inject. state + ──────┘        JSON guard ─┘   deltas ──┘   Steward report ──┘
   trace(in)              (blocks if broken)    persisted    + verbosity + trace(out)
```

| File (`modules/gaming/mygamemaster/hooks/`) | Event | Role |
|---|---|---|
| `_lib.py` | — | common library (payload, state, verbosity, bypass, ledger, CSV) |
| `pre_llm_call.py` | `pre_llm_call` | injects the **authoritative state** (time/day, PCs present + inventories, NPCs present); memorizes input prompt for traceability |
| `pre_tool_call.py` | `pre_tool_call` | **snapshot** of counters in the targeted file; **blocks** a `write_file` write whose JSON content is broken/nonconforming (strict mode) |
| `post_tool_call.py` | `post_tool_call` | reloads written file, calculates **deltas** (actions +N, inventory X→Y, time), stacks them in the **ledger**; reports broken JSON (advisory); **auto-commit** git of the campaign (if JSON valid) |
| `transform_llm_output.py` | `transform_llm_output` | builds the **"Persisted" Steward block** from ledger, applies **verbosity**, **augments** response, writes **CSV line** (in+out); **auto narrative voice** (axis `tts` + opt-in `tts_auto`: generates narration audio via `mygamemaster-tts` and attaches as `MEDIA:`, best-effort fail-open, outcome journalled in `.banquier/tts-status.json`) + memorizes `last_narration` (for `!raconte`) |
| `on_session_end.py` | `on_session_end` | **timestamped snapshot** of campaign JSON (safety net) |

---

## 4. Input/output contracts

### 4.1 Payload (stdin) — exploited fields

```json
{
  "hook_event_name": "pre_tool_call",
  "tool_name": "write_file",
  "tool_input": { "path": "...", "content": "..." },
  "session_id": "sess_abc",
  "cwd": "/opt/data/mygamemaster/campaigns/<slug>",
  "extra": { "model": "deepseek/...", "platform": "discord", "author_id": "..." }
}
```

- **`cwd`** = campaign directory (= `terminal.cwd`) → anchor for `world.json`, `npcs.json`,
  `characters/`, `sessions/`, `collecte.csv`, `.banquier/`.
- The exact locations of the **incoming message** (player text) and **response text** are
  not guaranteed by the docs → **defensive multi-key** reading (`first_present`), with **safe no-op**
  if not found (see §6 runtime unknowns).

### 4.2 Outputs (stdout) — per hook

| Hook | Expected output | Safe fallback |
|---|---|---|
| `pre_llm_call` | `{"context": "<state>"}` | `{}` (nothing injected) |
| `pre_tool_call` | `{}` or `{"action":"block","message":"<reason>"}` | `{}` (allow through) |
| `post_tool_call` | `{}` (effect = ledger write) | `{}` |
| `transform_llm_output` | `{"response": "<original text + block>"}` | `{}` (response **unchanged**) |
| `on_session_end` | `{}` | `{}` |

> **Safety invariant**: `transform_llm_output` emits `{"response": …}` **only if** it successfully
> retrieved the original text. Otherwise `{}` — we **never destroy** the GM's response.

### 4.3 Bypass (`meta.admins` / `⏸️`)

Any augmentation hook short-circuits (no-op) if:
- the message author is in `world.json > meta.admins` (list of Discord IDs) **or** `MGM_ADMIN_IDS`
  (env, comma-separated); **or**
- the incoming message contains `⏸️`.

**CSV traceability** remains active in bypass mode (pure observation), with `origine_detail` marked
`bypass`.

---

## 5. Configuration

### 5.1 Toggles per campaign — `world.json > meta.hooks` (all optional)

```jsonc
"meta": {
  "verbosite": "INFO",                 // controls Steward block (existing)
  "diagnostic": { "actif": true, ... },// controls CSV traceability (existing)
  "admins": ["100000000000000001"],    // Discord bypass IDs (NEW, optional)
  "hooks": {                            // NEW, optional — defaults = all enabled
    "injection_etat": true,            // pre_llm_call
    "banquier_persiste": true,         // Persisted block in response
    "garde_json_strict": false,        // true = blocks broken JSON write (T1 hard)
    "snapshot_fin_session": true,
    "auto_commit": true                // automatic git commit after each valid write
  }
}
```

Defaults if absent: injection **on**, Steward **on**, JSON guard **advisory** (non-blocking),
end-of-session snapshot **on**, **auto-commit on**, traceability follows `diagnostic.actif`, verbosity
follows `meta.verbosite`.

**Auto-commit (`post_tool_call`)** — offloads the model from manual `git add/commit` (which it often forgets).
After **each campaign file write**: if the JSON is **valid**, `git -C <campaign> add -A && commit` with
a message derived from **real deltas** (`🔄 auto [S<n>]: inventory X→Y ; +1 action`). Properties:
**fail-open** (git missing/error → no commit, never an exception); **never on broken JSON** (we don't
freeze an incoherent state); **no empty commits**; **lazy initialization** of repo + **inline identity**
(`MJ Tonnerre <mygamemaster@hermes.local>`, no infrastructure dependency); the **runtime space**
(`.banquier/`, `collecte.csv`) is gitignored so we only version **session content**. `git -C <campaign>`
always operates in the campaign repo → avoids nested git repos pitfall.

### 5.2 `hooks:` block (rendered by `config.yaml.j2`)

```yaml
hooks:
  pre_llm_call:
    - command: "<py> <mods>/gaming/mygamemaster/hooks/pre_llm_call.py"
      timeout: 10
  pre_tool_call:
    - matcher: "write_file|patch|edit|apply_patch|str_replace"
      command: "<py> <mods>/gaming/mygamemaster/hooks/pre_tool_call.py"
      timeout: 10
  post_tool_call:
    - matcher: "write_file|patch|edit|apply_patch|str_replace"
      command: "<py> <mods>/gaming/mygamemaster/hooks/post_tool_call.py"
      timeout: 10
  transform_llm_output:
    - command: "<py> <mods>/gaming/mygamemaster/hooks/transform_llm_output.py"
      timeout: 15
  on_session_end:
    - command: "<py> <mods>/gaming/mygamemaster/hooks/on_session_end.py"
      timeout: 30
hooks_auto_accept: true   # non-interactive in container (otherwise first-run consent prompt)
```

- `<py>` = `hooks_python` (default `/opt/hermes/.venv/bin/python3`); `<mods>` = `container_modules`.
- Scripts **baked into image** (already via `COPY modules/`), invoked by explicit interpreter →
  no dependency on executable bit or shebang.
- **stdlib only** — no pip dependencies.

---

## 6. Runtime unknowns (to validate on first real run, see architecture §5)

| Unknown | Coded assumption | Fallback if false |
|---|---|---|
| Key for **response text** in `transform_llm_output` payload | `response`/`output`/`content`/`text`/`message` (+ `extra.*`) | `{}` → response unchanged (never destroyed) |
| Key for **incoming message** (`pre_llm_call`) | `message`/`text`/`content`/`prompt`/`user_message` (+ `extra.*`) | partial trace, injection still emitted |
| Key for **author** (bypass) | `author_id`/`user_id`/`extra.author_id`/`extra.author` | bypass via `⏸️` + `MGM_ADMIN_IDS` remains operational |
| Exact names of **write tools** | `write_file|patch|edit|apply_patch|str_replace` | widen the `matcher` after log observation |

All hooks **fail silently (`{}`)** on exception → a hook bug never breaks a session
(principle *fail-open*, consistent with `security.tirith_fail_open: true`).

---

## 7. Path to "hard" logic blocking (Level 4)

To transform "nonexistent object → hard REFUSAL" from advisory to reliable blocking:

1. **Migrate inventory** to structured format: `{ "name": "sausage", "qty": 2, "type": "consumable" }`
   (migration script + `base_items.yaml` as canonical name reference).
2. Route inventory mutations through **a single scripted command**
   (`banquier apply <transaction.json>`) → clean, **idempotent** target for `pre_tool_call`.
3. Enable `meta.hooks.garde_json_strict` + structured SOURCE check in `pre_tool_call`.

**Chosen approach (validated by the admin):** rather than waiting for migration to enable
*deterministic* blocking, we entrust transactional consistency to a **soft LLM judge** (§10) —
a small model with narrow scope that tolerates name/format variations (e.g., "sausage" ≈ "sausage
in back pocket"), because in a TTRPG that happens constantly. Migration to structured inventory
remains useful for **free and deterministic** checks (pre-filtering), but is no longer a
prerequisite for blocking. See §10.

---

## 10. LLM Judge — Soft Steward + strict conduct

A **single LLM call** (`llm_judge.py`), two domains, with **narrow responsibility**: it judges
neither style nor pacing, only **clear** violations of the provided rules.

| Domain | Rule source | Posture |
|---|---|---|
| **steward** | resource possession, NPC knowledge, action feasibility, NPC existence | **soft** — tolerates name/format variations, **bias toward VALID** when in doubt (never false rejection) |
| **conduct** | `SOUL.md` "ABSOLUTE RULE — Agentivity" + preamble + `narrative-recurring-errors.md` | **strict** — agentivity, NPC emotions, hidden mechanics, possessiveness/spotlight, compartmentalization |

**Normalized verdict**: `{"ok":bool,"violations":[{domain,rule,excerpt,why,correction}]}`.
`correction` is a **concrete, actionable instruction** → this is what allows the GM to
self-correct.

### 10.0 Layer 0 — deterministic agency (AGENCY-01/02/03), enforced unconditionally

Everything in §10 is fail-open by design and therefore cannot own the rules whose violation
costs the most. `agency_gate.py` owns those: stdlib, local, no network, no config to enable.

**Call site is the whole point.** The judge and the checkpoint are invoked by the model reading
`SKILL.md`; the field report measured what that is worth (8 violations in one hour). The
enforcing call is therefore `transform_llm_output.enforce_agency()`, on the hook the runtime
runs on the finished text of every turn. No prompt participates.

**Remedy at that call site is a CUT, not a refusal.** Nothing downstream of inference can request
a new narration (see the reminder under §10.1), so `agency_gate.redact()` removes the flagged
sentences — spans come back from `analyze()` in `_spans` — the remainder of the turn is delivered,
and `set_pending()` feeds the correction forward exactly as the judge's. A narration reduced to
nothing is replaced by the localized `agency.emptied` hand-back: never empty, never an error
message, and the player is never told (same posture as the dialogue fallback, §11).

| Situation | Behaviour | Journal (`.banquier/agency-gate.json`) |
|---|---|---|
| no violation | delivered unchanged | `clean:ok` |
| violation detected | flagged sentences cut, feedback fed forward, counted in `scoreboard.json` | `enforced:redacted` |
| whole narration flagged | replaced by `agency.emptied` | `enforced:emptied` |
| `MGM_AGENCY_GATE=off`, or explicit ⏸️ pause | delivered unchanged, announced on stderr | `skipped:gate_off` / `skipped:paused` |
| analyser crash | **delivered unchanged** — infrastructure failure, not a verdict | `blind:gate_error` |
| journal unwritable | announced on stderr, turn proceeds | — |

The last two rows are the fail-open boundary: a **detected violation** never passes, an **outage of
ours** never costs every campaign its turn. An admin bypass does **not** suspend the gate (only an
explicit pause does), like the judge.

**Anti-loop is structural, not budgeted**: one pass per turn, no re-inference requested, and the
cut/re-check rounds are bounded by `MGM_AGENCY_MAX_ATTEMPTS` (default 3). It reads and writes
**none** of `agency_attempts`, `checkpoint_attempts` or `turn_gate_attempts` — a gate that consumes
another gate's budget disarms it silently (cf. `turn_state.py`).

Measured added cost: ~0.5 ms of analysis + ~0.1 ms of journal per turn.

### 10.1 Two correction mechanisms (neither loops)

1. **Feed-forward (always active, no re-inference).** `transform_llm_output` judges the
   delivered response; if violation → `set_pending()`. Next turn, `pre_llm_call` **re-injects**
   this feedback (`take_pending` = read **and deleted**) at the top of context. The GM corrects
   on the next turn. *Bounding: one note, injected once, then cleared — no loop possible.*
2. **In-turn gate (`mj_checkpoint.py`, true immediate self-correction).** The GM pipes their
   draft **before** delivering; judge responds OK / VIOLATION (explicit feedback, exit 1) /
   **FORCED** after `gate_max_tentatives` (default 2, exit 0 + log). *Bounding: attempt budget
   → after N, it passes with "forced" log.* Reset on each PASS and each new turn
   (`pre_llm_call` → `attempts_reset`).

> Reminder: a hook **cannot** regenerate a finished narration. Feed-forward corrects on the
> **next turn**; gate corrects **in the turn** but assumes the GM calls the checkpoint (instruction
> in the preamble SKILL). Both are complementary. Layer 0 (§10.0) is what covers the case where
> that assumption fails: it cannot regenerate either, so it **cuts** instead.

### 10.2 Per-model metrics (`scoreboard.json` + `scoreboard.py`)

At each judged turn: `turns`, `clean` (judge passes **and** Steward doesn't intervene),
`steward_interventions` (steward domain violations + JSON integrity), `conduct_violations`,
`by_rule`, `strengths`. Reader `scoreboard.py` prints a table **per model** with
`%clean` → feeds directly into **model choice** (cheapest that maintains high % clean).
The same signals feed `collecte.csv` (columns `error`, `error_type`, `model`).

### 10.3 Configuration — `world.json > meta.hooks.judge` (default: inactive)

```jsonc
"judge": {
  "actif": false,                 // true to enable LLM judge
  "modele": "",                   // dedicated small model; else env MGM_JUDGE_MODEL (required to enable)
  "base_url": "https://openrouter.ai/api/v1",
  "timeout": 8,                   // s (call stays under hook timeout)
  "echantillon": 1,               // judge 1 turn in N (cost lever)
  "min_chars": 40,                // don't judge very short responses
  "gate_max_tentatives": 2        // anti-loop budget for gate
}
```

API key: `OPENROUTER_API_KEY` (already required by entrypoint) or `MGM_JUDGE_API_KEY`.

### 10.4 Cost, latency, safety

- **Opt-in**: inactive by default (one LLM call/turn costs money). Levers: `echantillon`,
  `min_chars`, a **small** dedicated model.
- **Total fail-open**: call fails / unreadable / ambiguous → `ok=true` (never blocking on an
  uncertain judge → reinforces anti-loop).
- **Not exposed to player**: judge feedback is internal (feed-forward / log) — aligns with
  "technical transparency" rule. Visible only at DEBUG/TRACE verbosity.
- **Testable offline**: `MGM_JUDGE_MOCK=<verdict JSON>` short-circuits the network call.

---

## 11. Dialogue grader — quality, and the dry-summary fallback

`llm_judge.py` guards rules and deliberately refuses to grade quality. Nothing was therefore
watching the failure the field reported: conversations that break no rule and are still flat.
`dialogue_judge.py` is the answer — a **separate call**, on **turns that contain dialogue only**
(deterministic `has_dialogue()` detection, so a narration with no spoken line never pays for it).

**Rubric** (`references/dialogue-craft.md` §4), each 0..5: `INTENTION` (the line pursues the NPC's
own goal), `SOUS_TEXTE` (a gap between said and wanted), `VOIX` (mouths distinguishable, and
matching the sheet's `voix` block, which is passed in the prompt), `ENJEU` (something costs, moves
or is refused). **Verdict**: `{"ok",score,seuil,criteres,faibles}` — fails below `seuil` (12/20)
**or** on any criterion ≤ `plancher` (1).

**Layer 3 of `mj_checkpoint.py`**, after the agency gate and the rule judge, and only on the paths
that were about to clear the turn (a FORCED pass is already an escape from a loop — it is not made
harder). Budget `max_tentatives` (default 2 = first draft + one rewrite):

| Attempt | Outcome |
|---|---|
| 1st failure | exit 1 + feedback naming the weak criteria and one concrete fix each |
| 2nd failure | exit 0 + instruction to deliver the **DRY SUMMARY** instead of the dialogue |
| pass | exit 0, score appended to the checkpoint line |

The fallback is a **narrative register, not an error message**: reported speech, no quoted line,
the outcome stated (obtained / refused / at what price / what changed), persisted exactly as if
played, and the player is never told a scene was rejected.

**Configuration** — `world.json > meta.hooks.dialogue`, gated by the `dialogue` feature axis
(ON by default). Unlike `judge`, it is active as soon as it CAN run — a recurring, reported defect
does not ship behind a second opt-in:

```jsonc
"dialogue": {
  "actif": true,          // axis `dialogue` is the main switch above this
  "modele": "",           // else env MGM_DIALOGUE_MODEL, else the judge's model
  "base_url": "",         // else the judge's
  "timeout": 16,          // grading reads a whole scene, not a rule
  "seuil": 12,            // out of 20
  "plancher": 1,          // any criterion ≤ this fails, whatever the total
  "max_tentatives": 2,    // drafts, not rewrites
  "min_chars": 120
}
```

- **Fail-open**: unconfigured, unreachable or unparseable grader → the turn clears, with the reason
  stated on the checkpoint line. A grading outage must never degrade a good scene to a summary.
- **Journalled**: every grading lands in `.banquier/dialogue-scores.json` (capped 100) with its
  outcome (`passed` / `rewrite` / `summarised`). A campaign summarising half its conversations does
  not have a grading problem — it has a briefing problem (`modules/gaming/mygamemaster/scripts/dialogue_brief.py`).
- **Testable offline**: `MGM_DIALOGUE_MOCK=<verdict JSON>`.

---

## 8. Security & performance

- `hooks:` is a **privileged config**: only reference scripts from the repo (audited).
  Allowlist persisted by Hermes (`~/.hermes/shell-hooks-allowlist.json`); `hooks_auto_accept`
  bypasses prompt in container.
- `transform_llm_output` runs **at each response** → keep < ~150 ms (reading a few JSON files).
  Timeout clamped to 300 s on Hermes side, but we aim for reflexes.
- **Concurrency**: CSV/ledger writes protected by `flock`. Ledger is **per session_id**.
- **Idempotence**: ledger is *consumed* (read then cleared) by `transform_llm_output` each turn
  → no double-report.

---

## 9. Tests

`hooks/test_hooks.py` replays synthetic payloads against a **campaign fixture** and verifies:
non-empty state injection, JSON guard (blocks broken content), persisted deltas (inventory,
actions), Steward block present per verbosity, CSV line written, admin bypass/⏸️ neutralizes
augmentation but not traceability. Runnable outside container: `python3 hooks/test_hooks.py`.
