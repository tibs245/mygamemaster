# Hooks runtime MJ Tonnerre

Scripts executed by the Hermes gateway at each exchange (CLI + Discord). They make
**systematic** the Steward report, verbosity, and CSV traceability — without depending on the
model. Architecture and contracts: [`../../../../specs/hooks-runtime.md`](../../../../specs/hooks-runtime.md).
Guide: [`../../../../docs/09-runtime-hooks.md`](../../../../docs/09-runtime-hooks.md).
Hermes docs: <https://hermes-agent.nousresearch.com/docs/user-guide/features/hooks>.

> ⚠️ Do not confuse with `../scripts/install-hooks.sh` + `pre-commit.hook`, which are
> **git hooks** (refuse a commit if JSON is broken). These are **Hermes runtime hooks**.

## Files

| File | Hermes Event | Role |
|---|---|---|
| `_lib.py` | — | common library (stdlib only): payload, state, verbosity, bypass, ledger, CSV |
| `pre_llm_call.py` | `pre_llm_call` | injects authoritative state; records input prompt |
| `pre_tool_call.py` | `pre_tool_call` | snapshot of counters; **blocks a write advancing the game clock without a `⏩`** (`enforce_pacing`, journalled in `.banquier/turn-gate.json`); blocks broken JSON in strict mode |
| `post_tool_call.py` | `post_tool_call` | calculates deltas actually persisted → ledger; **auto-commit** git of campaign (valid JSON) |
| `transform_llm_output.py` | `transform_llm_output` | **deterministic AGENCY gate on the delivered text** (`enforce_agency`, unconditional, journalled in `.banquier/agency-gate.json`) + "Persisted" block + verbosity + **LLM judge** + CSV line + **auto narrative voice** (axis `tts` + **opt-in** `tts_auto`, attached as `MEDIA:`, fail-open, every outcome journalled in `.banquier/tts-status.json`) + snapshot `last_narration` (for `!raconte`) |
| `on_session_end.py` | `on_session_end` | timestamped snapshot of campaign |
| `llm_judge.py` | — (lib + CLI) | **LLM judge**: soft steward + strict conduct (`MGM_JUDGE_MOCK` for testing) |
| `turn_state.py` | — (lib + CLI) | **deterministic pacing gate TURN-01/02/06**: local, stdlib, no model; classifies the player's message (`open_turn`), refuses an unauthorised clock advance (`clock_verdict`), flags an unauthorised ellipse in the delivered text (`check_delivered`) |
| `agency_gate.py` | — (lib + CLI) | **deterministic AGENCY-01/02/03 gate**: local, stdlib, no model; refuses a PC action, PC dialogue or more than one PC action. `analyze()` for the verdict, `redact()` to cut the offending sentence out of a text already produced |
| `dialogue_judge.py` | — (lib + CLI) | **dialogue grader**: quality of NPC dialogue on a 4-criteria rubric (`MGM_DIALOGUE_MOCK` for testing); fail-open |
| `mj_checkpoint.py` | — (called by GM, OPTIONAL) | **gate** per-turn: agency gate, then pacing gate, then LLM judge, then dialogue grader — each with a loop-prevention budget. A chance to fix a draft *before* delivery; not the guarantee (see below) |
| `scoreboard.py` | — (reader) | metrics by model (`python3 scoreboard.py [campaign]`) |
| `section_usage_report.py` | — (reader) | SKILL.md split instrumentation: `section -> turns solicited -> observed trigger` (`python3 section_usage_report.py [campaign ...]`) |
| `test_hooks.py` | — | out-of-container tests (`python3 test_hooks.py`) — 324 cases (including the dialogue rubric, its budget and the summary fallback, the unconditional agency path and the pacing gate) |

## Principles

- **Stdlib only**, invoked by explicit interpreter (`/opt/hermes/.venv/bin/python3`).
- **Fail-open**: any exception → `{}` (no-op). A hook bug never breaks a session.
- **Except AGENCY-01/02/03**: `agency_gate.py` is deliberately NOT fail-open. Its verdict does not
  depend on the LLM judge being configured, reachable or in budget — the corpus showed that a
  written-only agency rule is violated again. Ambiguity is still never guessed at: an unrecognised
  construction is handed to the judge rather than blocked. Escape hatches: `MGM_AGENCY_GATE=off`
  (default ON) and `MGM_AGENCY_MAX_ATTEMPTS=N` (default 3, then a loud, logged forced pass).
- **…and it runs whether or not the model cooperates.** `mj_checkpoint.py` is triggered by a bash
  line printed in `SKILL.md`, i.e. by text the model may skip — and the field report counted 8
  agency violations in one hour under that arrangement. The enforcing call is therefore in
  `transform_llm_output.py` (`enforce_agency`), the one hook the runtime invokes on every turn.
  Downstream of inference nothing can be re-generated, so the remedy there is a **cut**
  (`agency_gate.redact`), fed forward to the next turn like the judge's corrections.
  - a **detected violation** is always cut — it never depends on config, network or budget;
  - an **infrastructure failure** (analyser crash) ships the turn unchanged and journals it
    `blind`: our own bug is not a proportionate reason to break every session.
  - anti-loop is structural — one pass per turn, no re-inference requested, redact/re-check rounds
    bounded by `MGM_AGENCY_MAX_ATTEMPTS`, and **no** shared counter with the other gates.
  - every verdict (`clean` / `enforced` / `skipped` / `blind`) is journalled in
    `.banquier/agency-gate.json`: a cut the player can see must leave a trace an auditor can read.
    Added cost measured at ~0.6 ms/turn (analysis + journal).
- **TURN-01/02/06 is the same story with the opposite remedy.** `turn_state.py` is wired to
  `pre_llm_call` (the grant is armed from the player's verbatim message — unforgeable and
  un-skippable), to `pre_tool_call` (a write advancing `current_day` without a `⏩` is **refused**,
  and the runtime makes the model rework the turn: this is the only forced rework the runtime can
  do) and to `transform_llm_output` (the delivered text is **flagged, never cut** — removing an
  ellipse marker strands the sentences after it). Same fail-open boundary as above: a missing turn
  record means `pre_llm_call` did not run, so no `⏩` could have been seen — the write is allowed and
  journalled `blind` rather than refused. Budget `turn_gate_max_tentatives` (default 2), escape
  hatch `MGM_TURN_GATE=0` / `meta.hooks.turn_gate:false`, journal `.banquier/turn-gate.json`,
  ~0.8 ms/turn.
- **Deterministic only**: apart from the agency and pacing gates we only block on JSON integrity; game logic
  ("nonexistent object") remains advisory as long as inventory is free-text (see spec §7).
- Working state under `<campaign>/.banquier/` (ledger, snapshots, sample counter).
- `pre_llm_call.py` also journals, per turn, which of a fixed set of observable
  triggers fired (`.banquier/section-usage.json`, ~0.17 ms/turn measured) — the
  data behind `section_usage_report.py`. It proves a trigger CONDITION was true
  for the turn, never that SKILL.md was actually read — see the instrumentation
  note (job 8e5baaf2) for the method and its limits.

## Settings

Everything in `world.json > meta` (read hot): `verbosity`, `diagnostic.active`, `admins`,
`hooks.{injection_state,steward_persist,guard_json_strict,snapshot_end_session,auto_commit,tts_auto}`.
`auto_commit` (default **on**): automatic git commit after each validated write — the model
no longer needs to run `git`; fail-open, never on broken JSON, runtime space (`.banquier/`,
`collecte.csv`) excluded.
`tts_auto` (default **off**, the only toggle that is): automatic narrative voice, opt-in via
`MGM_TTS_AUTO=1` or `meta.hooks.tts_auto=true` — reasons in `_lib.tts_auto_default()`. Diagnose
with `modules/gaming/mygamemaster-tts/scripts/tts_doctor.py`.
One-time bypass: `⏸️` (alias `!pause`) in the message, or author listed in `meta.admins` /
`MGM_ADMIN_IDS`. **Persistent pause**: `⏸️`/`!pause` arms a remembered pause mode for the session
(`.banquier/snap-<sid>.json > pause_mode`) that lasts until `▶️`/`!reprise` — no need to re-apply
the marker each turn. `!reprise` ≠ `!reprendre` (which reloads session context).
**Judge decoupled from admin bypass**: the LLM judge (and reinjection of its correction) also runs
on an admin's turns; only an EXPLICIT pause (`⏸️`/persistent mode) suspends it — like the auto
narrative voice. The scrub / "Persisted" block, themselves, remain reserved for non-bypass.
`hooks.dialogue` (axis `dialogue`, default **on**): grades NPC dialogue quality at the checkpoint —
active as soon as a model is reachable (`meta.hooks.dialogue.modele`, `MGM_DIALOGUE_MODEL`, else the
judge's). A flat scene is sent back once, then switched to a dry summary; every grading is journalled
in `.banquier/dialogue-scores.json`. Contract and settings: `specs/hooks-runtime.md` §11, writing
rules: `../references/dialogue-craft.md`.
