# 00 — Overview

## What is MJ Tonnerre?

**MJ Tonnerre** is a [Hermes](https://hermes-agent.nousresearch.com/docs/) agent that acts as a
**tabletop RPG Game Master on Discord**. It runs campaigns: narration, NPCs, dice rolls, inventory
and character-sheet management, and world-state tracking.

This repository lets you **deploy, back up, test, improve, and re-deploy** a campaign inside a
**Podman container**, driven entirely by **Ansible**.

## The three pillars

```
modules/   →  THE SKILLS : the mj-tonnerre* modules (the GM's intelligence)
data/      →  GAME DATA  : campaigns (world, NPCs, sessions, characters …)
ansible/   →  DEPLOYMENT : deploy/backup/restore inside Podman
```

- **modules/** — see [`../modules/MODULES.md`](../modules/MODULES.md).
- **data/** — one campaign per folder under `data/mj-tonnerre/campagnes/<slug>/`. Full structure in
  [`../specs/modele-de-donnees-campagne.md`](../specs/modele-de-donnees-campagne.md).
- **ansible/** — the playbook suite. Technical details in
  [`../specs/ansible-suite.md`](../specs/ansible-suite.md).

## Key concept: one container per game

Each campaign runs in its **own Podman container**, with its own config, persona (`SOUL.md`),
**isolated memory**, and data volume. This replaces the old "profiles" feature (which was
unreliable). See [`06-concept-isolation.md`](06-concept-isolation.md).

## Declaring games: the single table (`games.yml`)

All games are declared in **one file**: `ansible/inventory/games.yml` (git-ignored; the committed
example is `games.example.yml`). A dynamic inventory script (`hermes_inventory.py`) reads this
table and exposes each entry as an Ansible host in the `campagnes` group.

**Adding a game = adding one entry in `games.yml` + adding its Discord token to the vault. Nothing
else to touch.**

See [`02-deployer-une-campagne.md`](02-deployer-une-campagne.md) for the step-by-step procedure.

## Vocabulary

| Term | Meaning |
|---|---|
| **Campaign / game** | A single game instance (e.g. "Mistfall"). One slug, one container, one dataset. |
| **Module / skill** | A GM capability (`mj-tonnerre-outils`, `-pnj`, …). |
| **Slug** | Short campaign identifier (`mistfall`). Names the container, volumes, and systemd unit. |
| **Volume** | Persistent Podman storage: `data` (game data) and `home` (Hermes agent state) per campaign. |
| **Vault** | Ansible-encrypted file holding all secrets (API keys, Discord tokens). |
| **Quadlet** | Podman systemd unit → the campaign restarts automatically (persistence across reboots). |
| **`campagne_slug`** | Variable name used inside templates/playbooks for the slug value. |

## Where to start?

1. [`01-prerequis-et-installation.md`](01-prerequis-et-installation.md) — install tools, set up the vault.
2. [`02-deployer-une-campagne.md`](02-deployer-une-campagne.md) — launch a game.
3. [`05-cycle-de-vie.md`](05-cycle-de-vie.md) — the full daily loop.

Or jump straight to the guided walkthrough: [`CREATE-A-GAME.md`](CREATE-A-GAME.md).

**Just want to explore locally or run the tests?**
- [`QUICKSTART-LOCAL.md`](QUICKSTART-LOCAL.md) — run the three engine test suites with plain `python3`, no credentials.
- [`QUICKSTART-DOCKER.md`](QUICKSTART-DOCKER.md) — build the dev image with Docker and validate with `docker run`.

## Design: the living world (space-time & simulation)

The [`monde-vivant/`](monde-vivant/00-vue-densemble.md) series documents the system that keeps the
world **consistent in space and time** and **alive between sessions** (factions, key NPCs, and
cities that evolve when nobody is playing; reliable 4D geographic consistency even with cheap
models). Start with [`monde-vivant/00-vue-densemble.md`](monde-vivant/00-vue-densemble.md).
