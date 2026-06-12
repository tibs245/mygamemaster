> ⚠️ **OBSOLETE — the Hermes « profiles » feature does not work.** It is replaced by the **one container per campaign** model (see `README.md` and `docs/06-concept-isolation.md`). This document is preserved as a historical design reference; do NOT run `hermes profile create`. For NPC/Faction agents (level 2, approved), the target is one additional container per agent (cf. `specs/profiles-vers-conteneurs.md`).

# 🧩 Hermes Profiles — Multi-Campaign MJ Tonnerre

## Why profiles?

Each Hermes profile = **isolated instance** with its own:
- **Memory** (memory tool) — no pollution between campaigns
- **SOUL.md** — GM personality adapted to the campaign tone
- **Config** — model, provider, terminal.cwd
- **Hermes Sessions** — no contamination of histories

Without profiles, all campaigns share the same memory space → info from Rubis (King) gets mixed with the Abyss (World).

---

## Architecture

```
admin-mj                          ← Base profile (model v4-pro)
├── SOUL.md                       ← GM admin — infrastructure maintenance
├── config.yaml                   ← deepseek/deepseek-v4-pro
├── modules/gaming/mj-tonnerre/  ← Shared modules (runtime: /opt/modules/gaming/mj-tonnerre/)
│
├── [clone-from admin-mj] → naissance-dun-roi   ← Campaign "The Birth of a King"
│   ├── SOUL.md                   ← King campaign GM
│   ├── config.yaml               ← v4-flash, terminal.cwd = campaigns/la-naissance-dun-roi/
│   └── memory/                   ← isolated memory (Rubis, Marche, Cœur…)
│
└── [clone-from admin-mj] → jusquau-bout         ← Campaign "To the End of My World"
    ├── SOUL.md                   ← World campaign GM
    ├── config.yaml               ← v4-flash, terminal.cwd = campaigns/jusquau-bout-de-mon-monde/
    └── memory/                   ← isolated memory (Abyss, Chasm…)
```

### Golden rules

1. **Always clone from `admin-mj`** — never from another campaign profile. Otherwise memory/session customizations propagate.
2. **Never modify `admin-mj` for a specific campaign** — global rules go in admin-mj, customizations in the campaign profile.
3. **Campaign data** (`world.json`, `npcs.json`, `sessions/`) stay in `campaigns/<name>/` — the profile points via `terminal.cwd`.

---

## Create a new campaign profile

```bash
# 1. Clone from admin-mj
hermes profile create <campaign-name> --clone-from admin-mj

# 2. Configure the model (v4-flash unless specific need)
hermes config set model.default deepseek/deepseek-v4-flash --profile <campaign-name>

# 3. Point terminal.cwd to the campaign folder
hermes config set terminal.cwd /opt/data/.hermes/mj-tonnerre/campaigns/<campaign-name> --profile <campaign-name>

# 4. Write the custom SOUL.md
# → ~/.hermes/profiles/<campaign-name>/SOUL.md
# → GM personality, campaign context, custom rules
```

### Post-creation verification

```bash
hermes profile list                    # → model, gateway status, alias
cat profiles/<name>/config.yaml | grep -E 'model|terminal|cwd'
cat profiles/<name>/SOUL.md | head -3
ls profiles/<name>/modules/gaming/      # → MJ Tonnerre modules present
```

---

## Gateway Constraint — Token Lock

**One Discord bot = one active gateway at a time.** Hermes blocks the startup of a second gateway using the same token.

### Why

Each profile has its own gateway (process). If two gateways tried to listen to the same Discord bot, messages would be duplicated or lost — Hermes prevents this via the **token lock**.

### Consequence

To switch campaigns on the same Discord bot, you must **stop the active gateway and start the target profile's gateway**:

```bash
# Stop the current gateway
hermes gateway stop

# Start the target profile's gateway
hermes -p naissance-dun-roi gateway start

# → The Discord bot now responds in the King campaign context
```

### Affected profiles

| Profile | Gateway | Status |
|---------|---------|--------|
| `default` | Currently running | Active on Discord |
| `naissance-dun-roi` | Stopped | Ready to start |
| `jusquau-bout` | Stopped | Ready to start |
| `admin-mj` | Stopped | No gateway (maintenance) |

### `!profile` command (recommended)

To avoid bash commands from Discord, create a MJ Tonnerre command:

```
!profile naissance-dun-roi
→ ✅ Gateway switched to "The Birth of a King"
→ Isolated memory, campaign ready.

!profile jusquau-bout
→ ✅ Gateway switched to "To the End of My World"
```

**Logic**: `!profile <name>` executes in the Hermes session:
1. `hermes gateway stop` (current profile)
2. `hermes -p <name> gateway start` (target profile)
3. Confirmation message in the Discord channel

---

## SOUL.md — Customization per campaign

Each campaign profile has a distinct `SOUL.md`. It contains:

- **GM Persona** (always MJ Tonnerre, adapted to the tone)
- **Campaign context** (players, style, inspirations, system)
- **Custom rules** (e.g., "Rubis does not fight", "Survival — each resource counts")
- **Important reminders** (file path, special players, pitfalls to avoid)

### Recommended structure

```markdown
# Hermes Agent Persona — MJ Tonnerre · [Campaign Name]

You are **MJ Tonnerre**, Game Master of the **"[Name]"** campaign.

## Campaign Context
- **Player(s)** : [username] → [character]
- **Style** : [campaign type]
- **Inspirations** : [key works]
- **System** : [system name]
- **Tone** : [tone description]

## Custom Rules
1. ...
2. ...

## Important Reminders
- **Campaign File** : [absolute path]
- [other reminder]
```

---

## Skills distribution

MJ Tonnerre skills are cloned in each profile from `admin-mj`. They are therefore available in each session, regardless of the active profile.

List of cloned skills:
- `mj-tonnerre` (umbrella)
- `mj-tonnerre-initiation`
- `mj-tonnerre-personnage`
- `mj-tonnerre-inventaire`
- `mj-tonnerre-outils`
- `mj-tonnerre-images`
- `mj-tonnerre-session`
- `mj-tonnerre-intendant`
- `mj-tonnerre-analyste`
- `mj-tonnerre-bug-report`
- `mj-tonnerre-game-report`
- `mj-tonnerre-write-history`
- `mj-tonnerre-help`
- `mj-tonnerre-pnj`
- `mj-tonnerre-faction`

---

## CLI Aliases

Each profile automatically generates an alias (wrapper) in `~/.local/bin/`:

```bash
admin-mj chat              # → infrastructure maintenance
naissance-dun-roi chat     # → King campaign
jusquau-bout chat          # → World campaign
```

Aliases are created by `hermes profile create` — no manual configuration needed.