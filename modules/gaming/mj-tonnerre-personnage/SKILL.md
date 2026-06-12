---
name: mj-tonnerre-personnage
description: Manages character sheet display and editing — !sheet, !char, !notes. Strict per-player compartmentalization.
category: gaming
triggers:
  - "!sheet"
  - "!char"
  - "!notes"
  - "character"
  - "character sheet"
  - "my sheet"
  - "my stats"
---

# ⚡ MJ Tonnerre — Character Sheets

## Objective

Manage player character sheets: formatted display, attribute modification, reading personal notes. Everything goes through JSON files stored per player in the active campaign.

---

## File Architecture

```
~/.hermes/mj-tonnerre/campaigns/<campaign-name>/characters/<discord_id>.json
```

Each player has ONE file. The filename = their Discord ID (ex: `123456789012345678.json`).

---

## Character Template (format v2 — with history + session)

> The `historique`, `session_id`, `notes_privees` fields are part of format v2. Old sheets may not have them: with each significant update, **add missing fields one by one**, without breaking existing fields. **Soft** migration — no forced rewrites.

```json
{
  "meta": {
    "player_name": "",
    "discord_id": "",
    "character_name": "",
    "race": "",
    "class_": "",
    "level": 1
  },
  "stats": {},
  "equipment": [],
  "inventory": [],
  "skills": [],
  "spells": [],
  "historique": [
    "Entry added automatically during migration — traceable",
    "Each entry is a persistent fact or event of the character"
  ],
  "personal_notes": {
    "objectifs": [],
    "relations": {
      "<nom>": {
        "level": "Unknown|Acquaintance|Ally|Friend|Close|Wary|Hostile|Enemy",
        "description": ""
      }
    },
    "secrets": []
  },
  "connaissances_privees": [],
  "notes_privees": [
    "(private layer — character's inner thoughts, seeded by the GM or persisted by the coordinator)"
  ],
  "health": {
    "hp_max": 10,
    "hp_current": 10,
    "wounds": [],
    "conditions": []
  },
  "progression": {
    "xp": 0,
    "next_level": 100
  },
  "session_id": ""
}
```

### New Fields — Explanation

| Field | Type | Usage |
|-------|------|-------|
| `historique[]` | array of strings | Character's persistent facts/events — migrated from timeline and session actions. Each entry is a traceable fact (ex: "Repaired [a site] S1", "Met [an NPC] S4"). |
| `connaissances_privees[]` | array of strings | Knowledge the character **has** but **has not revealed** in play. Seeded by the GM (not by the agent). A layer between public info and absolute secret. |
| `notes_privees[]` | array of strings | Character's inner thoughts — thoughts, suspicions, plans. Appended by the coordinator (or by the GM in play). Invisible to other players. |
| `session_id` | string | ID of the Hermes session dedicated to the character (linked to approved level-2 agents NPC/Faction). Allows resuming the persistent session with `-c`. Empty if no dedicated session. |

### Soft Migration — Procedure

When you **modify** an existing sheet (HP update, inventory, level, etc.), **add missing fields at the same time** :

1. ✅ **Keep** all existing fields (`meta`, `stats`, `equipment`, `inventory`, etc.)
2. ✅ **Add** `historique` if absent → populate from `world.json > global_state.chronologie` and session logs
3. ✅ **Add** `connaissances_privees` and `notes_privees` if absent → leave them empty (`[]`)
4. ✅ **Add** `session_id` if absent → leave empty (`""`) — filled when a dedicated level-2 agent session (NPC/Faction) is created for this character
5. ❌ **Don't** rewrite the entire sheet — only touch modified fields + add missing ones
6. 🔄 **With each new session played**, enrich `historique` with the session entry

---

## Commands

### `!sheet` — Display the player's sheet

**Who can use it:** Any player (sees THEIR sheet) or the GM (sees all sheets).

**Flow:**

1. Get the `discord_id` of the message author
2. Determine the active campaign for this channel (via `world.json` — find `campaigns/*/world.json`, or session memory)
3. If no active campaign → reply: *"No active campaign on this channel. Run `!init` to create one."*
4. Read `campaigns/<name>/characters/<discord_id>.json`
5. If the file doesn't exist → reply: *"You don't have a character yet. DM me and we'll create one together!"* + offer to run `!init` if the campaign is in onboarding
6. If the file exists → format and display (see format below)

**Compartmentalization rule** (general rule: header `mj-tonnerre/SKILL.md §2/§9`) — specific to sheet:
- In **DM** → full display. In **public channel** → everything in `||Discord spoiler tags||`, and suggest first: *"DM me to see your sheet clearly!"*
- A player who runs `!sheet` sees **only their own sheet**. NEVER another's.

**Display Format:**

> **Base frame (boxed with `┏━━┓` + HP / Stats / Equipment / Skills lines): single source = header `mj-tonnerre/SKILL.md → Formatting Conventions → Character Sheet`. Inviolable format — apply it as-is.**

**Skill-specific additional lines** (add after the header frame):
```
✨ Spells: {list or "None"}
📦 Inventory: {list or "Empty"}
⭐ XP: {xp}/{next_level}
```

**Visual health bar (enrichment):**
- `❤️ HP: ████████░░ 8/10` (10 blocks, filled = current HP, empty = missing HP, proportional)
- If special state (ex: `poisoned`, `unconscious`, `blessed`) → badge after bar: `❤️ HP: ████░░░░░░ 4/12 ⚠️ Poisoned`

**GM Case:**
- If author is the GM (detected via `world.json > meta > mj_discord_id`), they can see any sheet by mentioning the player: `!sheet <@discord_id>`
- Display remains spoilered in public channel

---

### `!char <attribute> <value>` — Modify an attribute

**Who can use it:** The player (their stats) or the GM (all stats).

**General Flow:**

1. Get the `discord_id` of the author
2. Load the player's sheet
3. Parse `<attribute>` and `<value>` — supports multiple syntaxes (see below)
4. **Validate** the modification (see validation rules)
5. Apply the modification
6. Save the JSON file
7. **Log the modification** in the session log (`sessions/<session>.json > actions`)
8. Display a short confirmation message

**Supported Syntaxes:**

| Command | Effect |
|----------|--------|
| `!char strength 16` | Sets `stats.strength = 16` |
| `!char hp -8` | Reduces `health.hp_current` by 8 |
| `!char hp +5` | Increases `health.hp_current` by 5 |
| `!char hp 20` | Sets `health.hp_current` to 20 (validated against hp_max) |
| `!char hp_max 25` | Sets `health.hp_max = 25` |
| `!char class "Arcane Rogue"` | Sets `meta.class_` (strings in quotes) |
| `!char spell "Fireball" add` | Adds `"Fireball"` to `spells[]` |
| `!char spell "Fireball" remove` | Removes `"Fireball"` from `spells[]` |
| `!char equip "Longsword" add` | Adds to `equipment[]` |
| `!char equip "Longsword" remove` | Removes from `equipment[]` |
| `!char skill "Stealth +2" add` | Adds to `skills[]` |
| `!char skill "Stealth +2" remove` | Removes from `skills[]` |
| `!char level 3` | Sets `meta.level = 3` |
| `!char xp 150` | Sets `progression.xp = 150` |
| `!char state "Poisoned" add` | Adds to `health.conditions[]` |
| `!char state "Poisoned" remove` | Removes from `health.conditions[]` |
| `!char name "New Name"` | Changes character name (rarely used, typically init) |

**Recognized Attributes (auto-mapping):**

| Keyword | JSON Path | Type |
|---------|-----------|------|
| `strength`, `dex`, `constitution`, `intelligence`, `wisdom`, `charisma`, etc. (anything not reserved) | `stats.<word>` | number |
| `hp` | `health.hp_current` | number |
| `hp_max` | `health.hp_max` | number |
| `class` | `meta.class_` | string |
| `race` | `meta.race` | string |
| `name` | `meta.character_name` | string |
| `level` | `meta.level` | number (≥1) |
| `xp` | `progression.xp` | number (≥0) |
| `next_level` | `progression.next_level` | number |
| `spell` | `spells[]` | array operation |
| `equip` | `equipment[]` | array operation |
| `skill` | `skills[]` | array operation |
| `inventory` | `inventory[]` | array operation |
| `state` | `health.conditions[]` | array operation |
| `wound` | `health.wounds[]` | array operation |
| `goal` | `personal_notes.objectifs[]` | array operation |
| `relation` | `personal_notes.relations` | key:value |
| `secret` | `personal_notes.secrets[]` | array operation |

---

### `!notes` — Display Personal Notes

**Who can use it:** The player (their notes) or the GM.

**Flow:**

1. Load the player's sheet
2. Extract `personal_notes`
3. Always spoilered in public channel (or offer DM)

**Display Format:**

```
📝 PERSONAL NOTES — {CHARACTER NAME}

🎯 GOALS
• {goal 1}
• {goal 2}

👥 RELATIONS
• {name}: {description}
• {name}: {description}

🔒 SECRETS
• {secret 1}
• {secret 2}
```

If empty: *"You haven't noted anything yet. Use `!char goal "..." add` to get started!"*

---

## Validation Rules

**CRITICAL — Verify each modification before applying it.**

| Rule | Detail |
|-------|--------|
| **Max HP** | `hp_current` cannot exceed `hp_max` (except temporary effect → add to `states`). Message if exceeded: *"Your max HP is {max}. Cannot exceed this limit."* |
| **Negative HP** | `hp_current` can drop to minimum 0 (no negative HP except custom system). If ≤ 0 → automatically add `unconscious` state to `health.conditions`. Message: *"💀 {Name} drops to 0 HP and loses consciousness!"* |
| **Level** | Cannot drop below 1. Message: *"Minimum level is 1."* |
| **XP** | Cannot be negative. If XP ≥ `next_level` → suggest leveling up. *"⚡ You have enough XP to reach level {n+1}! Use `!char level {n+1}` if you want to level up."* |
| **Stats** | Stat values must be numeric. If value is not a number → *"Value must be a number. Ex: `!char strength 16`"* |
| **Strings** | If `<value>` contains spaces and isn't quoted → ambiguous. *"Use quotes: `!char class "Arcane Rogue"`"* |
| **Array add** | Check element doesn't already exist. If yes → *"Already present."* |
| **Array remove** | Check element exists. If not → *"Not found in list."* |
| **Owner** | A player cannot modify another's sheet. Detect via `discord_id` ≠ author. Message: *"That's not your sheet. Only the player or GM can modify this character."* |

---

## Logging

Each modification must be logged in the active session file:

```json
{
  "action": "modif_perso",
  "timestamp": "2026-05-14T16:22:00Z",
  "joueur": "<discord_id>",
  "auteur": "<discord_id_of_modifier>",
  "attribut": "stats.force",
  "ancienne_valeur": 14,
  "nouvelle_valeur": 16,
  "contexte": "!char strength 16"
}
```

If no session is active, log to `sessions/journal_libre.json`.

---

## Confirmation Message

After a successful modification, reply briefly:

```
✅ {human_attribute}: {old} → {new}
```

Examples:
- `✅ Strength: 14 → 16`
- `✅ HP: -8 (12 → 4)`
- `✅ Spell added: "Fireball"`

---

## Sheet Retrieval — Error Cases

| Error | Message |
|--------|---------|
| Campaign not found | *"No active campaign on this channel. Run `!init` to create one."* |
| Sheet doesn't exist | *"You don't have a character yet. DM me and we'll create one together!"* in DM / *"No sheet found — DM me!"* in public |
| Corrupted JSON file | *"⚠️ Corrupted sheet. The GM needs to check the file."* — log the error |
| Unknown attribute | *"Attribute "{attribute}" not recognized. Valid attributes: {keyword list}"* |
| Unauthorized modification | *"That's not your sheet. Only the player or GM can modify this character."* |

---

## References

- `references/relation-levels.md` — definition and usage of relation levels (Unknown → Enemy), with evolution examples and asymmetry principle
- `references/npc-loyalty-limits.md` (in the `mj-tonnerre` skill) — loyalty system, individual limits, evolution factors for allied NPCs
- `references/verbosity/README.md` (in the `mj-tonnerre` skill) — emoji convention for change notifications (❤️ HP, 📚 skills, 🔋 states). Use for any sheet modification reported during play.

---

## Integration with Header Skill

This skill is a sub-skill of `mj-tonnerre`. It loads automatically when the triggers `!sheet`, `!char`, `!notes` are detected.

**Before each action:**
1. Load `mj-tonnerre` for persona and global conventions
2. Determine the active campaign (check `world.json`)
3. Verify the relevant sheet (`characters/<discord_id>.json`)

**Always respect the header skill principles** (`mj-tonnerre/SKILL.md` §2 compartmentalization / §9 secrets): players only see their sheets, validation before writing, log every modification, spoiler tags in public channel.

---

## Pitfalls

| ❌ Pitfall | ✅ Solution |
|----------|------------|
| **Discord ID confusion at creation**: a ping `<@ID>` in a message doesn't reveal the message author's ID, but the person mentioned's ID. Don't infer a player's ID from a ping by someone else. | **Always ask each player for their own ID explicitly.** Create the sheet immediately under the correct ID before moving to the next player. |
| Creating a sheet under the wrong ID then needing to move/delete it | Check: *"Your Discord ID is really XXXXX?"* before writing the file |
| **❗ Making up stats for an existing character** — The GM creates a sheet for an already-played character without checking if stats already exist (agent memory, player messages, prior conversation). Ex.: creating [the PC] with [stats A] when the player had defined it with [stats B] earlier. Critical error. | **BEFORE creating or modifying a PC sheet, check IN ORDER:** (1) Agent memory — are stats recorded there? (2) Player messages in history — have they already mentioned stats, class, or inventory? (3) File on disk — does `characters/<discord_id>.json` exist? If yes → read it, don't recreate it. (4) Campaign repo git logs (`git log --all --diff-filter=A -- 'characters/*.json'`) — did a sheet exist then get deleted? If nothing found → ASK the player: "What are your character's stats?" NEVER start from an empty template. NEVER make up stats. |
| **❗ Using the sheet without player confirmation** — The GM narrates actions assuming PC stats without validating them with the player. | After creating or updating a sheet, confirm the stats with the player BEFORE using them in narration. A simple "Here's your sheet, is this right?" is enough. |
| **❗ NPC and location inventory not documented** — The GM tracks the PC's inventory but forgets that of accompanying NPCs and inhabited locations. Inconsistency guaranteed. | **Requirement:** Each recurring NPC (2+ sessions) has an `inventory` field (free strings) in npc.json. Each key location (cabin, camp, base) has an `inventaire_<location>` field (ex. `inventaire_cabane`) = `{description, contents[]}`. Update with each transfer (via Steward). See `mj-tonnerre-inventory`. |
