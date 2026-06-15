# Spec — Deployment Architecture

## 1. Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│ Host (Linux + Podman)                                                │
│                                                                      │
│  OCI Image « mygamemaster:<tag> »  ── built once ──┐                   │
│   • Hermes installed (install.sh → /opt/hermes)           │           │
│   • Our modules baked (/opt/modules/gaming/mygamemaster*) │           │
│   • entrypoint.sh (launches gateway)                     │           │
│                                                          ▼           │
│  ┌──────────────────────────┐   ┌──────────────────────────┐        │
│  │ container campaign A      │   │ container campaign B      │  …     │
│  │ hermes-naissance-dun-roi  │   │ hermes-jusquau-bout       │        │
│  │                           │   │                           │        │
│  │  config.yaml (rendered)   │   │  config.yaml (rendered)   │        │
│  │  SOUL.md   (rendered)     │   │  SOUL.md   (rendered)     │        │
│  │  volumes:                 │   │  volumes:                 │        │
│  │   • data  (campaign A) ───┼─► │   • data  (campaign B)    │        │
│  │   • memory (isolated A)   │   │   • memory (isolated B)   │        │
│  │  env: DISCORD/OPENROUTER  │   │  env: DISCORD/OPENROUTER  │        │
│  └────────────┬──────────────┘   └────────────┬──────────────┘        │
└───────────────┼─────────────────────────────────┼────────────────────┘
                │ Discord Gateway (WebSocket)       │
                ▼                                   ▼
            Discord Server (channels / threads of the campaign)
```

**Guiding principle** : *one game = one campaign = one Podman container*. Each container is a
standalone Hermes instance with its config, persona, memory, and isolated data. This replaces
the "profiles" functionality (see `profiles-vers-conteneurs.md`).

## 2. Layout within the container

| Path (in the container) | Content | Source | Persistence |
|---|---|---|---|
| `/opt/hermes/` | Hermes (venv, binary) | image (install.sh) | image, immutable |
| `/opt/modules/gaming/mygamemaster*` | our 15 skills | image (COPY modules/) | image, immutable |
| `/opt/hermes-home/` | **Hermes HOME** : `config.yaml`, `SOUL.md` | Ansible-rendered (config volume) | ephemeral, regenerable |
| `/opt/hermes-home/memory/` | campaign Hermes memory | **`memory` volume** | **persistent + backed up** |
| `/opt/data/mygamemaster/campaigns/<slug>/` | game data | **`data` volume** | **persistent + backed up** |
| `/opt/data/mygamemaster/base_items.yaml` | base items (shared) | data volume (or image) | persistent |

`HOME=/opt/hermes-home` is the Hermes anchor. `config.yaml` is read from there; `skills.external_dirs`
points to `/opt/modules`; `terminal.cwd` points to `/opt/data/mygamemaster/campaigns/<slug>`.

## 3. Configuration Model

- `terminal.backend: local` — the agent executes its commands (skill Python scripts:
  `clock.py`, `validate_schema.py`, `close_session.py`…) **within its own container**. No
  Docker-in-Docker: the container IS the sandbox.
- `skills.external_dirs: [/opt/modules]` — loads our modules in addition to stock skills.
- `terminal.cwd: /opt/data/mygamemaster/campaigns/<slug>` — skill scripts use relative
  paths `.hermes/mygamemaster/campaigns/<x>` **or** read from cwd; we align cwd
  with campaign data (borrowed from profile `terminal.cwd` idea).
- `model.default` + `model.provider: openrouter` — configurable per campaign.
- `discord.*` block — `require_mention`, `auto_thread`, `history_backfill`… (see original config).
- `display.language: fr`, `display.personality` — the persona lives mostly in `SOUL.md`.

## 4. Volumes & Data Lifecycle

| Volume | Role | Backed up | Destroyed on redeploy? |
|---|---|---|---|
| `hermes-<slug>-data` | game data (campaign) | ✅ yes | ❌ never |
| `hermes-<slug>-memory` | isolated Hermes memory | ✅ yes | ❌ never |
| config (bind-mount of rendered) | `config.yaml` + `SOUL.md` | ❌ (regenerable) | ✅ re-rendered |

A **redeploy** (module improvement) rebuilds the image and recreates the container, **without
touching** the `data` and `memory` volumes. This is what makes the *improve → re-deploy*
cycle safe.

## 5. Discord Gateway

The container launches, via `entrypoint.sh`, the Hermes **gateway** process that maintains the
Discord WebSocket connection and routes messages to the agent. Required secrets as environment
variables (never in plain text in the image):
`OPENROUTER_API_KEY`, the **Discord bot token** (one shared multi-channel bot *or* one bot per
campaign — choice in `host_vars`), and optionally keys for auxiliary tools (image_gen,
tts) if enabled. Details: `secrets-et-vault.md`.

> **Runtime unknown** : the exact gateway startup command (`hermes setup --portal`
> for OAuth auth then the daemon command) is coded in `entrypoint.sh.j2` per official docs
> and must be validated on first real `podman run` on the host.

## 6. Persistence

Each container is exposed as a **Podman Quadlet unit** (`hermes-<slug>.container` → systemd) :
automatic restart on boot, systemd supervision, journald. This is the persistence mechanism
(see `ansible-suite.md` § Quadlet).
