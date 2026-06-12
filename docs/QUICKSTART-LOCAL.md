# Local quickstart — run tests and harness without Docker

This guide lets you validate the engine and run the dev harness on your own machine, with no
Docker, no Discord token, and no external API calls.

## Prerequisites

| Tool | Version | Check |
|---|---|---|
| **Python** | 3.10+ | `python3 --version` |
| **Bash** | any | `bash --version` |

No third-party Python packages are required for the test suites — they use the standard library
only. PyYAML is listed as an optional dependency (`pip install PyYAML`) for some skill scripts,
but the tests pass without it.

---

## Run the three test suites

These three commands exercise the engine at the unit and integration level.
All of them should exit 0. Skipped tests (`s`) are expected — they require real campaign data
that is not committed to the repository.

### Suite 1 — engine scripts (world-tick, geography, causality, …)

```bash
cd modules/gaming/mj-tonnerre/scripts
python3 -m unittest discover -s tests
```

Expected output ends with something like:

```
Ran 239 tests in 0.2s
OK (skipped=46)
```

### Suite 2 — runtime hooks (Steward, judge, CSV collector, …)

```bash
cd modules/gaming/mj-tonnerre/hooks
python3 test_hooks.py
```

Expected output ends with:

```
RESULT : 61/61 tests OK
```

### Suite 3 — TTS pipeline

```bash
cd modules/gaming/mj-tonnerre-tts/tests
python3 test_tts.py
```

Expected output ends with:

```
RESULT: 33/33 tests OK
```

---

## Run the harness (mock LLM, no real keys)

The `harness/` directory contains a local end-to-end harness that replaces the LLM with a
lightweight stdlib mock server.

> **Note**: the harness requires a local Podman machine with the `hermes-mj:latest` image
> already built. See `harness/README.md` for the current status and known blockers.

```bash
bash harness/run.sh
```

If Podman is not available on your machine, you can still inspect the harness config and the
mock LLM server source in `harness/mock_llm.py` and `harness/config.local.yaml`.

---

## What these tests do NOT cover

- A live Discord session (requires a real bot token and the full Ansible deploy — see
  [docs/02-deployer-une-campagne.md](02-deployer-une-campagne.md)).
- LLM quality (the judge, the GM persona, the NPC agents) — these require an OpenRouter key
  and are validated during a real session.
- The image generation pipeline (OpenRouter / ComfyUI access required).

For Docker-based validation see [QUICKSTART-DOCKER.md](QUICKSTART-DOCKER.md).
