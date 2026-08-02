# 06 — The Isolation Concept (one container per game)

## The original idea

Historical Hermes installations tried to isolate each campaign through a **"profiles"** feature:
one profile = one Hermes instance with its own memory, persona (`SOUL.md`), config, and sessions.
The goal was to prevent **one campaign's memory from polluting another** (a character's info from
one game leaking into another), and to give each campaign a dedicated tone and persona.

**The problem**: this mechanism was unreliable (shared memory pollution, ambiguous sessions,
fragile state). So the **idea was kept, the mechanism replaced**.

## The chosen solution: one container per game

Isolation is now enforced by **Podman**: each campaign runs in its own container, natively
delivering what profiles promised.

| Need (profile idea) | Implementation (container) |
|---|---|
| Isolated memory | dedicated `hermes-<slug>-home` volume |
| Dedicated persona | `SOUL.md` rendered per campaign (shared base + `soul_extra`) |
| Dedicated config (model, cwd) | `config.yaml` rendered from the `games.yml` entry |
| Campaign data pointed at | `terminal.cwd` → `/opt/data/mygamemaster/campaigns/<slug>` |
| Independent lifecycle | start / stop / backup / restore per container |

Full technical detail: [`../specs/profiles-to-containers.md`](../specs/profiles-to-containers.md).

## What we gain

- **True isolation**: two campaigns share **no** state whatsoever (memory, sessions, files).
- **Reproducibility**: everything is described in code (templates + `games.yml` + vault),
  redeployable from scratch.
- **Fault containment**: a crash or data corruption in one campaign does not affect the others.
- **Mental simplicity**: "one game = one container = one entry in `games.yml`".

## What about the `admin-mj` agent?

The old `admin-mj` profile handled cross-cutting rule and module maintenance. That maintenance is
no longer a production agent: **it happens in this repository** (edit `modules/` → `redeploy`,
see [`04-improve-the-modules.md`](04-improve-the-modules.md)). If a maintenance-assistant
agent is ever needed, it is simply another game entry.

## What about NPC / faction "agents"?

The `mygamemaster-npc` and `mygamemaster-faction` skills describe **secondary agents** (an NPC or
faction embodied by their own instance). In the container architecture, these are **future
additional containers** — out of scope for the current phase, but trivially pluggable into the
same Ansible suite.
