# MJ Tonnerre — AI Game Master for Discord

**A production-ready, LLM-powered tabletop RPG Game Master that runs on Discord,
isolated per campaign, deployed in minutes with a single declarative table.**

<!-- Placeholder demo — replace with a real recording once available -->
<!-- ![demo](docs/assets/demo.gif) -->

---

## What is this?

**MJ Tonnerre** is an AI Game Master built on the [Hermes](https://hermes-agent.nousresearch.com/docs/) agent framework.
It runs live sessions on Discord, narrates in **the players' language** (configurable per game),
rolls dice, tracks inventory and character sheets, animates persistent NPCs and factions,
and keeps the world coherent across sessions — even when nobody is playing.

Each game runs as its own **rootless Podman container**, deployed and managed by **Ansible**.
The stack is intentionally minimal: one declarative table, one vault, one command.

> "MJ Tonnerre" is a proper name and is not translated.

---

## Features

### 16 Skill Modules

**Session management**
- `mj-tonnerre-initiation` — `!init` onboarding questionnaire: theme, rules, world, players → generates all campaign files
- `mj-tonnerre-session` — structured session wrap-up and resume: formatted summaries, full state snapshots, stats
- `mj-tonnerre-help` — in-Discord guide: how to use the GM, available commands

**Game mechanics**
- `mj-tonnerre-outils` — dice rolls (`!jet`, `!jetq`, `!action`) using Python `secrets` + optional quantum entropy via qrandom.io
- `mj-tonnerre-intendant` — **the Steward**: a transactional rules verifier ("Banker") that checks every action against the canonical state (inventory, knowledge, time, coherence). Fail-soft: tolerates name variations, never false-refuses
- `mj-tonnerre-inventaire` — player inventories: display, add, use, discard, transfer; extensible YAML item base
- `mj-tonnerre-personnage` — per-player character sheets (`!fiche`, `!perso`, `!notes`) with strict compartmentalization

**Living world**
- `mj-tonnerre-pnj` — persistent NPC agents: each key NPC runs as an isolated agent with its own limited viewpoint, goals, and plans
- `mj-tonnerre-faction` — persistent Faction agents: each faction runs as a collective intelligence agent
- `mj-tonnerre-images` — image generation pipeline: deterministic map layer (`carte_schema.py`) + image-model embellishment via OpenRouter / ComfyUI
- `mj-tonnerre-tts` — narrative TTS: MiniMax `speech-2.8-turbo` synthesizes narration only (auto via hook + manual `!raconte`)

**Quality and output**
- `mj-tonnerre-analyste` — consistency auditor: mode A (bug), B (session-close audit), C (pre-session audit)
- `mj-tonnerre-bug-report` — players can file structured bug reports (context / expected / got) for deferred review
- `mj-tonnerre-game-report` — factual session report: actions, locations, NPCs, decisions, inventory — no spoilers
- `mj-tonnerre-write-history` — novelization of the session as a readable chapter, no mechanics, no spoilers

### Runtime Hooks (systematic, model-independent)

- **State injection** (`pre_llm_call`): real campaign state (time, inventories, present NPCs) is injected before every GM response — the model narrates from authoritative data, not its memory
- **JSON integrity guard** (`pre_tool_call`): malformed JSON is flagged before it can corrupt campaign files
- **Steward report** (`post_tool_call` + `transform_llm_output`): every response is augmented with a "persisted" block listing real deltas; a CSV row is appended for traceability
- **LLM judge** (`llm_judge.py`): an independent model checks each GM response on two axes — Steward compliance (soft) and conduct rules (strict: agency, NPC emotions, hidden mechanics, compartmentalization). Corrections are feed-forward (next turn), never blocking. Gate mode (`mj_checkpoint.py`) lets the GM validate a draft before delivering; after 2 failures it passes anyway (logged as "forced"), so sessions never hang
- **Persistent pause mode**: prefix a message with `⏸️` (or be listed in `meta.admins`) to bypass the Steward display for debugging — tracing still runs, marked `bypass`

### Feature Flags (6 axes, all ON by default)

Traceability · Verbosity · Living NPCs · Living Factions · Temporality · Images · Voice

All flags fail-open (absent = ON). Toggled live in `world.json > meta.features` — no redeploy needed.

### Living-World Engine

A 4D space-time model that keeps the world coherent across sessions:
- **Monotone clock** (`T` integer, 1 UT = 10 min game time, `T=0` at campaign creation)
- **Spatial graph** with stable IDs, containment, adjacency, anchor coordinates (used by code only, never sent to the LLM)
- **Actor trajectories** — position as a function of time; factions, key NPCs, and cities have dated goals and plans
- **LOD tick engine** — pre-session projection + post-session reconciliation, level-of-detail simulation by proximity to players
- **Causal propagation** — events trigger cascades across the relationship graph (burnt fields → famine, weeks later)

The LLM declares intentions; deterministic code enforces geometry, deadlines, and conservation. Works reliably with cheap models.

---

## How it Works

```
Discord channel
      │
      ▼
┌─────────────────────────────────────────────────┐
│  Podman container  (one per game)               │
│                                                 │
│  ┌──────────────┐    hooks     ┌─────────────┐  │
│  │  Hermes      │◄────────────►│  Runtime    │  │
│  │  agent       │              │  hooks      │  │
│  │  (GM soul)   │              │  (Steward,  │  │
│  └──────┬───────┘              │  judge,     │  │
│         │ skills               │  TTS, ...)  │  │
│  ┌──────▼───────────────────┐  └─────────────┘  │
│  │  16 skill modules        │                   │
│  │  (mj-tonnerre-*)         │                   │
│  └──────────────────────────┘                   │
│                                                 │
│  Volumes:                                       │
│    hermes-<slug>-home    (agent memory + state) │
│    hermes-<slug>-data    (campaign files)       │
└─────────────────────────────────────────────────┘
      │
      ▼
  LLM API (OpenRouter) + optional TTS (MiniMax)
```

**One game = one campaign = one container.**
Campaigns share no state — memory, sessions, and files are fully isolated.
A crash in one campaign cannot affect another.
Each container is a systemd Quadlet unit: games survive reboots without an open session.

Deployment is driven by a **single declarative table** (`ansible/inventory/games.yml`).
The dynamic inventory (`ansible/inventory/hermes_inventory.py`) turns each row into an Ansible host automatically.
Nothing else to touch.

---

## Quickstart

### Prerequisites (on the deployment host — Linux)

| Tool | Purpose |
|---|---|
| **Podman ≥ 4** (rootless) | runs the containers |
| **systemd user** + Quadlet | auto-restart on reboot |
| **Ansible ≥ 2.16** | orchestration |
| **ansible-vault** | encrypted secrets (bundled with Ansible) |
| **rsync, gzip, tar** | seed and backups |

Enable linger so containers survive logout:
```bash
loginctl enable-linger $USER
```

Install Ansible collections:
```bash
ansible-galaxy collection install -r ansible/requirements.yml
```

### 1 — Clone and configure

```bash
git clone <this-repo>
cd hermesv5/ansible

# Declare your games (one-time)
cp inventory/games.example.yml inventory/games.yml
# Edit games.yml: set the connection block + your first game entry

# Set up secrets
cd inventory/group_vars/all
cp vault.example.yml vault.yml
ansible-vault encrypt vault.yml
ansible-vault edit vault.yml   # fill in your real API keys and Discord tokens
```

### 2 — Build the image

```bash
cd ansible
ansible-playbook playbooks/build-image.yml
```

### 3 — Deploy

```bash
# Deploy all games declared in games.yml
ansible-playbook playbooks/deploy.yml

# Deploy a single game
ansible-playbook playbooks/deploy.yml -e game=mistfall
```

### Day-to-day operations

```bash
ansible-playbook playbooks/status.yml                         # status of all games
ansible-playbook playbooks/backup.yml                         # hybrid backup (data + memory)
ansible-playbook playbooks/update.yml                         # safe rolling update
ansible-playbook playbooks/teardown.yml -e game=<slug> -e confirm=yes
```

---

## Add a New Game

Adding a game is **one row** in `games.yml` + one Discord token in the vault:

```yaml
# ansible/inventory/games.yml
games:
  - slug: emberfall
    data_dir: example-emberfall
    title: "Emberfall"
    model: minimax/minimax-m3       # any OpenRouter model id
    provider: openrouter
    language: en                    # language the GM speaks to players
    discord_secret_key: discord_token_emberfall
    soul_extra: |
      ## Persona of this instance
      You are MJ Tonnerre the Ember: warm, conspiratorial, fond of secrets.
      ...
```

Then add `discord_token_emberfall` to your vault and run `deploy.yml`. Nothing else to touch.

For the full walkthrough (world files, data structure, NPC setup):
- [docs/CREATE-A-GAME.md](docs/CREATE-A-GAME.md)
- [docs/AI-ONBOARDING-PROMPT.md](docs/AI-ONBOARDING-PROMPT.md) — an AI-assisted prompt that writes the campaign files for you

---

## Project Layout

```
hermesv5/
├── modules/gaming/          # the 16 skill modules (mj-tonnerre-*)
│   └── mj-tonnerre/
│       ├── hooks/           # runtime hooks (pre_llm_call, post_tool_call, …)
│       ├── scripts/         # shared Python/Bash utilities (roll.py, clock.py, …)
│       └── references/      # rules, thematic modules, JSON schemas
├── data/                    # campaign data (one subfolder per game slug)
│   └── mj-tonnerre/campaigns/<slug>/
│       ├── world.json       # world config, rules, feature flags
│       ├── npcs.json         # NPC sheets
│       ├── events.json  # event timeline (T clock)
│       └── ...
├── ansible/                 # deployment suite
│   ├── inventory/
│   │   ├── games.example.yml        # declarative game table (copy → games.yml)
│   │   ├── hermes_inventory.py      # dynamic inventory (reads games.yml)
│   │   └── group_vars/all/
│   │       └── vault.example.yml    # secrets template
│   ├── playbooks/           # build-image, deploy, status, backup, teardown, …
│   ├── roles/               # Ansible roles
│   └── templates/           # config.yaml.j2, SOUL.md.j2, …
├── docs/                    # operator documentation
│   └── monde-vivant/        # living-world engine design docs (English)
├── specs/                   # architecture and design specs
│   ├── architecture.md
│   ├── hooks-runtime.md
│   ├── secrets-et-vault.md
│   └── ...
└── harness/                 # local dev harness (mock LLM, test runner)
```

Full documentation index: [docs/00-vue-densemble.md](docs/00-vue-densemble.md).

---

## Configuration & Secrets

All secrets live in an **Ansible vault** — never in plain text, never committed unencrypted.

```
ansible/inventory/group_vars/all/vault.yml  (encrypted — git-ignored)
```

See [ansible/inventory/group_vars/all/vault.example.yml](ansible/inventory/group_vars/all/vault.example.yml) for the template and setup instructions.

**What goes in the vault:**

| Key | Purpose |
|---|---|
| `openrouter_api_key` | LLM access for the GM + voice formatting |
| `minimax_api_key` | Optional — narrative TTS; absent = TTS silently disabled (fail-open) |
| `discord_token_<slug>` | One Discord bot token per game instance |

The default GM model is `minimax/minimax-m3` (via OpenRouter). The LLM judge ideally runs on a
separate, smaller model (default: `google/gemma-4-31b-it`) to keep costs low and avoid self-grading.

In-game toggles (`world.json > meta`) are read at runtime — no redeploy needed to change verbosity,
enable/disable the judge, or adjust feature flags.

---

## Cost Disclaimer

MJ Tonnerre calls **commercial LLM and TTS APIs** at runtime. You are responsible for the costs
incurred on your OpenRouter and MiniMax accounts.

- The GM makes one LLM call per player message.
- The LLM judge makes an additional call per turn (configurable `echantillon` to sample 1-in-N turns).
- TTS generates audio for narration passages above a character threshold (default: 100 chars).
- Image generation is triggered per explicit request or scene event.

Use the `echantillon` setting on the judge and the feature flags to control spending.
The [scoreboard script](modules/gaming/mj-tonnerre/hooks/scoreboard.py) helps you find the cheapest model that maintains quality.

---

## Documentation

| Doc | Topic |
|---|---|
| [docs/00-vue-densemble.md](docs/00-vue-densemble.md) | Overview and vocabulary |
| [docs/01-prerequis-et-installation.md](docs/01-prerequis-et-installation.md) | Prerequisites and installation |
| [docs/02-deployer-une-campagne.md](docs/02-deployer-une-campagne.md) | Deploy a campaign |
| [docs/03-backup-et-restauration.md](docs/03-backup-et-restauration.md) | Backup and restore |
| [docs/05-cycle-de-vie.md](docs/05-cycle-de-vie.md) | Full operational lifecycle |
| [docs/06-concept-isolation.md](docs/06-concept-isolation.md) | Isolation model (one container per game) |
| [docs/09-hooks-runtime.md](docs/09-hooks-runtime.md) | Runtime hooks (Steward, judge, verbosity) |
| [docs/monde-vivant/](docs/monde-vivant/00-vue-densemble.md) | Living-world engine (space, time, causality) |
| [specs/architecture.md](specs/architecture.md) | System architecture |
| [specs/hooks-runtime.md](specs/hooks-runtime.md) | Hook internals |
| [specs/secrets-et-vault.md](specs/secrets-et-vault.md) | Secrets management |

---

## License

MJ Tonnerre is licensed under the **GNU Affero General Public License v3.0** (AGPL-3.0).
See [LICENSE](LICENSE).

The copyright is held by a single author. The maintainer reserves the right to offer the project
under a dual license (including a commercial or closed license) for specific use cases. Contributions
are accepted under the terms described in [CONTRIBUTING.md](CONTRIBUTING.md) — contributors grant
the maintainer the right to relicense their contributions. See [SECURITY.md](SECURITY.md) for the
responsible disclosure policy.
