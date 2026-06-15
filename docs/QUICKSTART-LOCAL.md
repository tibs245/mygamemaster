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
cd modules/gaming/mygamemaster/scripts
python3 -m unittest discover -s tests
```

Expected output ends with something like (exact counts may vary as suites grow):

```
Ran NNN tests in 0.2s
OK (skipped=N)
```

### Suite 2 — runtime hooks (Steward, judge, CSV collector, …)

```bash
cd modules/gaming/mygamemaster/hooks
python3 test_hooks.py
```

Expected output ends with (exact count may vary):

```
RESULT : NN/NN tests OK
```

### Suite 3 — TTS pipeline

```bash
cd modules/gaming/mygamemaster-tts/tests
python3 test_tts.py
```

Expected output ends with (exact count may vary):

```
RESULT: NN/NN tests OK
```

---

## Advanced: local end-to-end harness

> **This section is for advanced users only.**
> The harness requires the `mygamemaster:latest` image, which is built by the Ansible playbook
> `ansible-playbook playbooks/build-image.yml` — it is not a credential-free path.
> See [`harness/README.md`](../harness/README.md) for current status, prerequisites, and known
> blockers before attempting to run it.

The `harness/` directory contains a local end-to-end harness that replaces the LLM with a
lightweight stdlib mock server. Once `mygamemaster:latest` is available locally:

```bash
bash harness/run.sh
```

---

## What these tests do NOT cover

- A live Discord session (requires a real bot token and the full Ansible deploy — see
  [docs/02-deployer-une-campagne.md](02-deployer-une-campagne.md)).
- LLM quality (the judge, the GM persona, the NPC agents) — these require an OpenRouter key
  and are validated during a real session.
- The image generation pipeline (OpenRouter / ComfyUI access required).

For Docker-based validation see [QUICKSTART-DOCKER.md](QUICKSTART-DOCKER.md).
