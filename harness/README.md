# Harness E2E — reveal/validate hook invocation (R1)

Goal: prove, in a **hermetic and reproducible** way, whether the Hermes
gateway **actually invokes** the runtime hooks (`pre_llm_call`, `transform_llm_output`,
`post_tool_call`, `on_session_end`) — a diagnosis having shown that in prod they
never run (`collecte.csv` empty, `.banquier/` empty, 0 auto-commit).

No real keys, no Discord: a local **mock LLM** replaces the provider.

## Contents

| File | Role |
|---|---|
| `mock_llm.py` | OpenAI-compatible server (stdlib): `GET /v1/models` + `POST /v1/chat/completions`. Canned narrative response containing a ` ```python ` block (to test the R4b scrub end-to-end). Logs each request to stderr. |
| `config.local.yaml` | Rendered `config.yaml` (Ansible-free equivalent of `config.yaml.j2`): `model.base_url` → mock, hooks wired as in prod, `hooks_auto_accept: true`. |
| `run.sh` | Mounts a throwaway campaign + a `HERMES_HOME`, starts the mock and the gateway on a **shared podman network**, plays ONE one-shot CLI turn (`hermes -z … --accept-hooks`), then checks observable effects. |

## Usage

```bash
bash harness/run.sh        # requires podman machine running + image localhost/mygamemaster:latest
```

Assertions (valid **only if the turn completes**, exit 0):
- `collecte.csv` gains ≥ 1 line ⇒ `transform_llm_output` invoked (proof R1);
- `.banquier/` populated ⇒ `post_tool_call` invoked;
- auto-commit `🔄 auto` ⇒ auto-commit (R3);
- (to extend) player response without ` ``` ` block ⇒ scrub R4b.

## Status as of 2026-06-10

**What works (hard parts resolved):**
- `mygamemaster:latest` image can be started locally.
- Network: mock + gateway are two containers on the same podman network (both
  inside the `podman-machine` VM) → the macOS↔VM network layer is bypassed. Container→mock
  reachability **confirmed** (`GET /v1/models` and `POST` respond correctly).
- Hermes **correctly loads** `config.local.yaml` (`hermes config` shows provider
  `openrouter`, `base_url` → mock, model `mock`).

**Known blocker — must be resolved to reveal R1:**
The gateway **aborts before any network call to the LLM**: the mock receives **zero**
requests (neither `GET /v1/models` nor `POST /chat/completions`), even with
`-m mock --provider openrouter`. The message `hermes -z: no final response was
produced` stems from this — **not** from the hooks.

Likely cause: **provider initialisation/auth** fails offline with a `dummy`
key (the `openrouter` provider likely validates the key / makes a resolution call
before the chat). Until this link is fixed, **R1 remains undetermined** (no turn
completes, so nothing can be concluded about the hooks).

**Next steps to unblock (require knowledge of Hermes auth setup):**
1. Use a Hermes provider of type "OpenAI-compatible / local" that accepts an
   arbitrary `base_url` **without key validation** (instead of `openrouter`).
2. Or supply real provider auth (valid key / `hermes login`) — at the cost of
   hermeticity.
3. Or find the Hermes flag that **skips provider validation** at startup
   (`hermes doctor` / `hermes model --help` mention a live `/v1/models` check).

Once a turn completes, the assertions in `run.sh` resolve R1 immediately,
and the `[mock]` stderr trace confirms the network path.
