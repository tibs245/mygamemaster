# Contributing to MyGameMaster

Thank you for your interest in contributing. This document explains how to set up a development
environment, the coding conventions we follow, and the legal terms that govern contributions.

---

## Developer Certificate of Origin (DCO) and Contributor License Agreement (CLA)

**All contributions to this project are governed by the following terms.**

### Developer Certificate of Origin 1.1

By making a contribution to this project, I certify that:

(a) The contribution was created in whole or in part by me and I have the right to submit it
under the open source license indicated in the file; or

(b) The contribution is based upon previous work that, to the best of my knowledge, is covered
under an appropriate open source license and I have the right under that license to submit that
work with modifications, whether created in whole or in part by me, under the same open source
license (unless I am permitted to submit under a different license), as indicated in the file; or

(c) The contribution was provided directly to me by some other person who certified (a), (b) or
(c) and I have not modified it.

(d) I understand and agree that this project and the contribution are public and that a record of
the contribution (including all personal information I submit with it, including my sign-off) is
maintained indefinitely and may be redistributed consistent with this project or the open source
license(s) involved.

*Source: [developercertificate.org](https://developercertificate.org/)*

### Contributor License Agreement (lightweight)

**By submitting a pull request or patch to this repository, you additionally agree that:**

> Your contributions are licensed under the AGPL-3.0, AND you grant the maintainer (the sole
> copyright holder) the irrevocable right to relicense your contributions, including under a
> proprietary or commercial license, without further notice or compensation.

This dual-licensing right exists solely to allow the maintainer to sustain the project.
The AGPL-3.0 version of the code and all its history remain public.

### How to sign off

Add a `Signed-off-by` trailer to your commits using `git commit -s`:

```
git commit -s -m "feat(skill): add my improvement"
```

This produces:
```
feat(skill): add my improvement

Signed-off-by: Your Name <your@email.example>
```

Pull requests without a sign-off on every commit will not be merged.

---

## Development Setup

### Prerequisites

- Python 3.11+
- A Hermes installation (see [Hermes docs](https://hermes-agent.nousresearch.com/docs/))
- Podman (rootless) + Ansible ≥ 2.16 (for deployment testing)
- `ansible-vault` (bundled with Ansible)

### Local harness

The `harness/` directory contains a mock LLM and a local runner for fast iteration without
a real Discord bot or API key:

```bash
cd harness
./run.sh
```

See `harness/README.md` for configuration options.

### Running tests

Three test suites cover the core engine, runtime hooks, and TTS module.
Run them from the repo root:

```bash
# Core engine (unittest discover)
cd modules/gaming/mygamemaster/scripts && python3 -m unittest discover -s tests

# Runtime hooks
cd modules/gaming/mygamemaster/hooks && python3 test_hooks.py

# TTS module
cd modules/gaming/mygamemaster-tts/tests && python3 test_tts.py
```

JSON schema validation (requires a local campaign directory):
```bash
python3 modules/gaming/mygamemaster/scripts/validate_schema.py <campaign-dir>
```

All tests must pass before opening a pull request.

### Linting

```bash
pip install ruff yamllint

ruff check .     # Python lint (configured in ruff.toml)
yamllint .       # YAML lint (configured in .yamllint)
```

### pre-commit

Install the pre-commit hooks to catch issues before they reach CI:

```bash
pip install pre-commit
pre-commit install          # installs commit-time hooks
pre-commit install --hook-type pre-push   # installs the push-time test guard
```

Or run all hooks at once against the full tree:

```bash
pre-commit run --all-files
```

---

## Coding Conventions

- **Match the surrounding code.** Style, indentation, naming conventions, and patterns of the
  file you are editing take precedence over personal preference.
- **Keys stay as-is.** JSON/YAML keys in campaign data files (`world.json`, `npcs.json`,
  `events.json`, …) are in French and must not be renamed — downstream code depends on them.
- **Fail-open.** Hooks and validators must never crash a session. Use `try/except` broadly in
  hook scripts; log the error and return a neutral result.
- **Stdlib only in hooks.** Runtime hooks (`hooks/*.py`) must use only the Python standard
  library — no third-party imports, as hooks run inside the container without a full venv.
- **No secrets in code.** Never hard-code API keys, tokens, or passwords. All secrets go
  through Ansible vault (see `specs/secrets-and-vault.md`).
- **Document your module.** Every new skill module must have an entry in `modules/MODULES.md`.

---

## How to Add a Skill Module

1. Create a directory under `modules/gaming/mygamemaster-<your-skill>/`.
2. Follow the structure of an existing module (e.g. `mygamemaster-inventory/`) for the
   `skill.yaml` manifest and entry point.
3. Add your module to the Hermes `skills.external_dirs` path (already configured in the image).
4. Write at least one test that exercises the happy path.
5. Add an entry to `modules/MODULES.md` describing the role of your skill.
6. If your module introduces new JSON keys into campaign data files, add or update the relevant
   schema under `modules/gaming/mygamemaster/scripts/schemas/`.

---

## Pull Request Process

1. **Fork** the repository and create a feature branch:
   ```bash
   git checkout -b feat/my-feature
   ```
2. **Write tests** for your changes and make sure all existing tests still pass.
3. **Sign off** every commit with `git commit -s`.
4. **Open a pull request** against the `main` branch. Fill in the PR description:
   - What problem does this solve?
   - How was it tested?
   - Any known limitations or follow-up work?
5. A maintainer will review within a reasonable time. Expect requests for changes — this is
   normal and constructive.
6. Once approved, the maintainer will merge. Squash commits may be applied for a clean history.

### What makes a good PR

- Small and focused: one concern per PR.
- Includes tests (or a clear explanation of why none are needed).
- Does not break existing campaigns (backwards-compatible data format changes only).
- Does not include unencrypted secrets, personal data, or campaign save files.

---

## Reporting Bugs

Use the GitHub issue tracker. For security vulnerabilities, follow the process described in
[SECURITY.md](SECURITY.md) instead — do not open a public issue.
