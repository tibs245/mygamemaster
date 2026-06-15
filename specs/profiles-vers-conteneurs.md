# Spec — From "profiles" to "one container per campaign"

## Why abandon profiles

The **profiles** feature in Hermes aimed to isolate each campaign (memory, persona, config,
sessions) in a distinct instance. In the original installation it **did not work reliably**
(shared memory polluted between campaigns, ambiguous sessions at `/resume`, fragile state
management). The **idea** of isolation remains relevant; we re-implement it with a robust and
reproducible mechanism: **isolation via Podman container**.

## Correspondence table

| "profile" concept (old) | "container" equivalent (new) |
|---|---|
| `profiles/<campaign>/` (Hermes instance) | container `hermes-<slug>` |
| `profiles/<campaign>/config.yaml` | `config.yaml` rendered by Ansible (template + host_vars) |
| `profiles/<campaign>/SOUL.md` | `SOUL.md` rendered (common base + campaign's `soul_extra`) |
| `profiles/<campaign>/memory/` (isolated) | volume `hermes-<slug>-memory` |
| `profiles/<campaign>/sessions/` | runtime state in the container (volume if needed) |
| `config.model.default` per profile | `host_vars/<campaign>.model` |
| `terminal.cwd` → campaign folder | `terminal.cwd: /opt/data/mygamemaster/campaigns/<slug>` |
| profile `admin-mj` (maintenance) | not carried forward in runtime: **module maintenance**
  is done in this repository (editing `modules/` → `redeploy`). See note below. |
| `hermes profile create … --clone-from admin-mj` | `ansible-playbook deploy.yml -e campaign=<slug>` |
| alias `~/.local/bin/<campaign>` | `systemctl --user {start,stop} hermes-<slug>` |

## What container isolation guarantees (and what profiles promised)

- **Unpolluted memory**: distinct `memory` volume per campaign → one campaign's info never leaks
  into another. (This was the #1 issue motivating profiles.)
- **Dedicated persona**: `SOUL.md` specific to each campaign (tone, world, house rules).
- **Dedicated config**: model, `terminal.cwd`, Discord settings per campaign.
- **Independent lifecycle**: start/stop/backup/restore a campaign without touching others.

## The "admin-mj" case

The old `admin-mj` profile served to **maintain cross-cutting rules and modules**. In the
new architecture, this maintenance is **no longer a production agent** but a **development
workflow on this repository**:
1. edit a skill under `modules/gaming/mygamemaster*`;
2. `redeploy.yml` (rebuild image + recreate containers);
3. campaigns run on the improved modules, with no data loss.

If a Hermes agent for maintenance assistance is desired later, it will simply become a
special `admin` campaign (one more container), not a separate mechanism.

## Migration of the NPC/faction-agents concept

The old `ensure_agent.sh` created profiles `pnj-<x>` / `faction-<x>` (secondary agents).
Same principle: these are potential additional containers, configurable via `host_vars`.
Out of scope for phase 1 — the container architecture makes them trivial to add later.
