> ⚠️ **OBSOLETE — the Hermes "profiles" feature does not work.** It has been replaced by the **one container per campaign** model (see `README.md` and `docs/06-concept-isolation.md`). This document is kept as a historical design reference; do NOT run `hermes profile create`. For autonomous NPC/Faction agents (level 2, approved), the target is one additional container per agent (cf. `specs/profiles-vers-conteneurs.md`).

# 🧩 Hermes Profiles — Architecture for MJ Tonnerre

> **Architecture reference.** Documents the discovery and proposed use of Hermes profiles
> to isolate MJ Tonnerre campaigns. Not yet implemented — to be validated with the admin
> before integration into the standard onboarding workflow.

## Context

Currently, all MJ Tonnerre campaigns live under the same Hermes profile
(`default`):

```
~/.hermes/
├── config.yaml          ← shared (model, provider)
├── memory/              ← shared (memory from ALL campaigns mixed together)
├── sessions/            ← shared (Hermes sessions, not game sessions)
├── skills/              ← shared
└── mygamemaster/
    └── campaigns/
        ├── la-naissance-dun-roi/     ← campaign A
        └── jusquau-bout-de-mon-monde/ ← campaign B
```

**Problems:**
- Mixed persistent memory — campaign A info pollutes campaign B
- Shared Hermes sessions — `/resume` between two campaigns is ambiguous
- Single config — impossible to use a different model per campaign
- No SOUL.md per campaign — the GM persona is identical everywhere

## Solution: One Profile per Campaign

Each campaign becomes an **independent Hermes profile**, with its own `config.yaml`,
`.env`, `SOUL.md`, memory, and Hermes sessions.

```
~/.hermes/
├── config.yaml              ← default profile (Discord connection, etc.)
├── skills/                  ← shared skills (always visible to all)
└── profiles/
    ├── admin-mj/            ← "GM Admin" profile
    │   ├── config.yaml      ← flash model for maintenance
    │   ├── .env
    │   ├── SOUL.md          ← "You are the architect of the rules..."
    │   ├── memory/
    │   └── sessions/
    ├── naissance-dun-roi/   ← profile campaign A
    │   ├── config.yaml      ← deepseek/deepseek-v4-flash (or other)
    │   ├── .env
    │   ├── SOUL.md          ← "You are the GM of The Birth of a King..."
    │   ├── memory/          ← isolated memory (Rubis, NPCs, campaign A lore)
    │   └── sessions/        ← isolated Hermes sessions
    └── jusquau-bout/        ← profile campaign B
        ├── config.yaml
        ├── .env
        ├── SOUL.md
        ├── memory/
        └── sessions/
```

### Where does game data live?

**Campaign data** (`world.json`, `npcs.json`, `sessions/NNN.json`) remain
in the centralized folder `~/.hermes/mygamemaster/campaigns/<campaign>/` — **not**
in the profile. The profile provides only **Hermes memory isolation**
and **campaign-specific configuration**.

To point the profile to the correct data folder, configure
`terminal.cwd` in the profile's `config.yaml`:

```yaml
terminal:
  backend: local
  cwd: /opt/data/.hermes/mygamemaster/campaigns/la-naissance-dun-roi
```

## Admin-mj Profile

A profile dedicated to **maintaining rules and cross-cutting modules**:
- MJ Tonnerre skills (overview, onboarding, steward, dice, images, etc.)
- Shared scripts (validate_schema.py, clock.py, faction_slice.py, etc.)
- Campaign template (`_template/`)
- Item base and system references
- No gameplay — no campaign memory

Usage: `hermes -p admin-mj chat`

## Onboarding Workflow (Proposed)

When a new campaign is created via `!init`:

1. Normal questionnaire (skills `mygamemaster-initiation`)
2. At **Step 4 — Technical Initialization**, also create:
   ```bash
   hermes profile create <campaign-slug> --clone-from admin-mj
   hermes -p <campaign-slug> config set terminal.cwd /opt/data/.hermes/mygamemaster/campaigns/<campaign-slug>
   echo "# SOUL — MJ Tonnerre for [Campaign Name]" > ~/.hermes/profiles/<campaign-slug>/SOUL.md
   ```
3. The GM uses `hermes -p <campaign-slug>` to play this campaign
4. Other campaigns are unaffected (isolated memory)

## Profile Naming (Convention)

| Entity | Profile Name | Example |
|--------|--------------|---------|
| GM Admin | `admin-mj` | `admin-mj` |
| Campaign A | campaign name slug | `naissance-dun-roi`, `jusquau-bout` |
| Autonomous NPC | `pnj-<name>` | `pnj-firmin`, `pnj-kreevix` |
| Autonomous Faction | `faction-<name>` | `faction-test` |

## Management Commands

```bash
# Create
hermes profile create <name> --clone-from admin-mj

# List
hermes profile list

# Use (single session)
hermes -p <name> chat

# Configure the profile
hermes -p <name> config set model.default <model>
hermes -p <name> config set terminal.cwd <campaign-folder-path>

# Set as sticky (always use this profile thereafter)
hermes profile use <name>

# View details
hermes profile show <name>

# Export / Import
hermes profile export <name>
hermes profile import <archive>.tar.gz
```

## Notes

- Skills are **shared** across all profiles — no need to reinstall
  MJ Tonnerre skills in each profile
- Memory (`memory tool`) is **isolated** — each profile has its own database
- Hermes sessions (`/resume`, `/title`) are **isolated**
- The .env (API keys) must be copied to each profile or be identical to default
- The Discord gateway remains on the `default` profile — campaign profiles
  are used CLI-only (unless you want dedicated Discord bots)