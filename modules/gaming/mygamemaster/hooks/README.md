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
| `pre_tool_call.py` | `pre_tool_call` | snapshot of counters; blocks broken JSON in strict mode |
| `post_tool_call.py` | `post_tool_call` | calculates deltas actually persisted → ledger; **auto-commit** git of campaign (valid JSON) |
| `transform_llm_output.py` | `transform_llm_output` | "Persisted" block + verbosity + **LLM judge** + CSV line + **auto narrative voice** (axis `tts` → `mygamemaster-tts`, attached as `MEDIA:`, fail-open) + snapshot `last_narration` (for `!raconte`) |
| `on_session_end.py` | `on_session_end` | timestamped snapshot of campaign |
| `llm_judge.py` | — (lib + CLI) | **LLM judge**: soft steward + strict conduct (`MGM_JUDGE_MOCK` for testing) |
| `agency_gate.py` | — (lib + CLI) | **deterministic AGENCY-01/02/03 gate**: local, stdlib, no model; refuses a PC action, PC dialogue or more than one PC action |
| `mj_checkpoint.py` | — (called by GM) | **gate** per-turn: agency gate first, then LLM judge, each with a loop-prevention budget |
| `scoreboard.py` | — (reader) | metrics by model (`python3 scoreboard.py [campaign]`) |
| `test_hooks.py` | — | out-of-container tests (`python3 test_hooks.py`) — 191 cases (including auto-TTS, persistent pause, admin judge, the agency corpus table and a HELD-OUT false-positive table) |

## Principles

- **Stdlib only**, invoked by explicit interpreter (`/opt/hermes/.venv/bin/python3`).
- **Fail-open**: any exception → `{}` (no-op). A hook bug never breaks a session.
- **Except AGENCY-01/02/03**: `agency_gate.py` is deliberately NOT fail-open. Its verdict does not
  depend on the LLM judge being configured, reachable or in budget — the corpus showed that a
  written-only agency rule is violated again. Ambiguity is still never guessed at: an unrecognised
  construction is handed to the judge rather than blocked. Escape hatches: `MGM_AGENCY_GATE=off`
  (default ON) and `MGM_AGENCY_MAX_ATTEMPTS=N` (default 3, then a loud, logged forced pass).
- **Deterministic only**: apart from the agency gate we only block on JSON integrity; game logic
  ("nonexistent object") remains advisory as long as inventory is free-text (see spec §7).
- Working state under `<campaign>/.banquier/` (ledger, snapshots, sample counter).

## Settings

Everything in `world.json > meta` (read hot): `verbosity`, `diagnostic.active`, `admins`,
`hooks.{injection_state,steward_persist,guard_json_strict,snapshot_end_session,auto_commit,tts_auto}`.
`auto_commit` (default **on**): automatic git commit after each validated write — the model
no longer needs to run `git`; fail-open, never on broken JSON, runtime space (`.banquier/`,
`collecte.csv`) excluded.
One-time bypass: `⏸️` (alias `!pause`) in the message, or author listed in `meta.admins` /
`MGM_ADMIN_IDS`. **Persistent pause**: `⏸️`/`!pause` arms a remembered pause mode for the session
(`.banquier/snap-<sid>.json > pause_mode`) that lasts until `▶️`/`!reprise` — no need to re-apply
the marker each turn. `!reprise` ≠ `!reprendre` (which reloads session context).
**Judge decoupled from admin bypass**: the LLM judge (and reinjection of its correction) also runs
on an admin's turns; only an EXPLICIT pause (`⏸️`/persistent mode) suspends it — like the auto
narrative voice. The scrub / "Persisted" block, themselves, remain reserved for non-bypass.
