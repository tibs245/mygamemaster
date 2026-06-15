---
name: mygamemaster-personnage
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
~/.hermes/mygamemaster/campaigns/<campaign-name>/characters/<discord_id>.json
```

Each player has ONE file. The filename = their Discord ID (ex: `123456789012345678.json`).

---

## Character Template (format v2 — with history + session)

> The `historique`, `session_id`, `notes_privees` fields are part of format v2. Old sheets may not have them: with each significant update, **add missing fields one by one**, without breaking existing fields. **Soft** migration — no forced rewrites.

```json
{
  "meta": {
    "nom_joueur": "",
    "discord_id": "",
    "nom_perso": "",
    "race": "",
    "classe": "",
    "niveau": 1
  },
  "stats": {},
  "equipement": [],
  "inventaire": [],
  "competences": [],
  "sorts": [],
  "historique": [
    "Entry added automatically during migration — traceable",
    "Each entry is a persistent fact or event of the character"
  ],
  "notes_perso": {
    "objectifs": [],
    "relations": {
      "<nom>": {
        "niveau": "Unknown|Acquaintance|Ally|Friend|Close|Wary|Hostile|Enemy",
        "description": ""
      }
    },
    "secrets": []
  },
  "connaissances_privees": [],
  "notes_privees": [
    "(private layer — character's inner thoughts, seeded by the GM or persisted by the coordinator)"
  ],
  "sante": {
    "pv_max": 10,
    "pv_actuels": 10,
    "blessures": [],
    "etats": []
  },
  "progression": {
    "xp": 0,
    "niveau_suivant": 100
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

1. ✅ **Keep** all existing fields (`meta`, `stats`, `equipement`, `inventaire`, etc.)
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

**Compartmentalization rule** (general rule: header `mygamemaster/SKILL.md §2/§9`) — specific to sheet:
- In **DM** → full display. In **public channel** → everything in `||Discord spoiler tags||`, and suggest first: *"DM me to see your sheet clearly!"*
- A player who runs `!sheet` sees **only their own sheet**. NEVER another's.

**Display Format:**

> **Base frame (boxed with `┏━━┓` + HP / Stats / Equipment / Skills lines): single source = header `mygamemaster/SKILL.md → Formatting Conventions → Character Sheet`. Inviolable format — apply it as-is.**

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
- If author is the GM (detected via `world.json > meta > gm_discord_id`), they can see any sheet by mentioning the player: `!sheet <@discord_id>`
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
| `!char hp -8` | Reduces `sante.pv_actuels` by 8 |
| `!char hp +5` | Increases `sante.pv_actuels` by 5 |
| `!char hp 20` | Sets `sante.pv_actuels` to 20 (validated against hp_max) |
| `!char hp_max 25` | Sets `sante.pv_max = 25` |
| `!char class "Arcane Rogue"` | Sets `meta.classe` (strings in quotes) |
| `!char spell "Fireball" add` | Adds `"Fireball"` to `sorts[]` |
| `!char spell "Fireball" remove` | Removes `"Fireball"` from `sorts[]` |
| `!char equip "Longsword" add` | Adds to `equipement[]` |
| `!char equip "Longsword" remove` | Removes from `equipement[]` |
| `!char skill "Stealth +2" add` | Adds to `competences[]` |
| `!char skill "Stealth +2" remove` | Removes from `competences[]` |
| `!char level 3` | Sets `meta.niveau = 3` |
| `!char xp 150` | Sets `progression.xp = 150` |
| `!char state "Poisoned" add` | Adds to `sante.etats[]` |
| `!char state "Poisoned" remove` | Removes from `sante.etats[]` |
| `!char name "New Name"` | Changes character name (rarely used, typically init) |

**Recognized Attributes (auto-mapping):**

| Keyword | JSON Path | Type |
|---------|-----------|------|
| `strength`, `dex`, `constitution`, `intelligence`, `wisdom`, `charisma`, etc. (anything not reserved) | `stats.<word>` | number |
| `hp` | `sante.pv_actuels` | number |
| `hp_max` | `sante.pv_max` | number |
| `class` | `meta.classe` | string |
| `race` | `meta.race` | string |
| `name` | `meta.nom_perso` | string |
| `level` | `meta.niveau` | number (≥1) |
| `xp` | `progression.xp` | number (≥0) |
| `next_level` | `progression.niveau_suivant` | number |
| `spell` | `sorts[]` | array operation |
| `equip` | `equipement[]` | array operation |
| `skill` | `competences[]` | array operation |
| `inventory` | `inventaire[]` | array operation |
| `state` | `sante.etats[]` | array operation |
| `wound` | `sante.blessures[]` | array operation |
| `goal` | `notes_perso.objectifs[]` | array operation |
| `relation` | `notes_perso.relations` | key:value |
| `secret` | `notes_perso.secrets[]` | array operation |

---

### `!notes` — Display Personal Notes

**Who can use it:** The player (their notes) or the GM.

**Flow:**

1. Load the player's sheet
2. Extract `notes_perso`
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

### `!prefs` — Custom Play Preferences (per player, persistent)

Out-of-fiction, **table-style** preferences for a player: how they like to be run. These are **not** in-fiction data — they describe the *experience* (pacing, tone, combat verbosity, spotlight, content boundaries, "enjoys being deceived"…). They are stored in the `preferences` block of that player's sheet (`characters/<discord_id>.json`), persist across sessions, and are **automatically surfaced to the GM each turn** (hook `pre_llm_call`) so play is tailored without the player having to repeat themselves.

**Storage** — one block per player, fully compartmentalized (same isolation rules as the rest of the sheet). Documented keys (all optional; an empty/missing block changes nothing — fail-open):

| Key | Type | Meaning |
|-----|------|---------|
| `rythme` | string | Preferred pacing (e.g. "slow-burn investigation", "fast and reactive") |
| `ton_aime` | list | Tone the player enjoys (mystery, tension, lore…) |
| `ton_evite` | list | Tone to avoid (slapstick, bookkeeping…) |
| `verbosite_combat` | string | Combat verbosity (`concise` \| `vivid`) |
| `spotlight` | string | Spotlight preferences (shy, loves solo moments, never at others' expense…) |
| `limites_contenu` | list | Content boundaries (hard lines — always respected) |
| `aime_etre_trompe` | bool | Enjoys being deceived (a fair, foreshadowed twist) |
| `custom` | object | Any extra free-form keys the player asks to remember |

> Keys are kept in French to match the sibling sheet keys (`notes_perso`, `objectifs`, …). A later PR handles the FR→EN rename across the schema.

**Saving a preference** — when a player expresses one in play (*"remember that I like slow investigation"*, *"please keep combat short"*, *"I love being fooled by a good twist"*, *"no harm to children on screen"*), the GM saves it immediately with the script (no manual JSON editing):

```bash
python3 /opt/modules/gaming/mygamemaster/scripts/prefs.py <campaign> <discord_id> set rythme "slow-burn investigation"
python3 /opt/modules/gaming/mygamemaster/scripts/prefs.py <campaign> <discord_id> set verbosite_combat concise
python3 /opt/modules/gaming/mygamemaster/scripts/prefs.py <campaign> <discord_id> set aime_etre_trompe true
python3 /opt/modules/gaming/mygamemaster/scripts/prefs.py <campaign> <discord_id> set ton_aime '["mystery","lore"]'
# An unknown key lands under preferences.custom automatically:
python3 /opt/modules/gaming/mygamemaster/scripts/prefs.py <campaign> <discord_id> set music_cues "play a sting on a critical hit"
```

Values are parsed as JSON when possible (`true`, `["a","b"]`, numbers), else stored as a raw string. Confirm briefly to the player: *"Noted — I'll keep that in mind."* The auto-commit hook persists the change like any sheet write.

**Recalling a preference** — preferences are injected into the GM's authoritative-state context on **every** turn, so the GM should already be applying them. To read explicitly:

```bash
python3 /opt/modules/gaming/mygamemaster/scripts/prefs.py <campaign> <discord_id> get          # whole block
python3 /opt/modules/gaming/mygamemaster/scripts/prefs.py <campaign> <discord_id> get rythme    # one key
```

**Removing** a preference (player changes their mind):

```bash
python3 /opt/modules/gaming/mygamemaster/scripts/prefs.py <campaign> <discord_id> unset rythme
```

**Compartmentalization** — a player's preferences are **private to that player**. The GM (who already sees all sheets) uses them to run the table; they are NEVER shown to or shared with other players. Only ever set/get the file named by the requesting player's own `discord_id`.

**Fail-open** — no `preferences` block, an empty block, or any read error = no change to play. Never block a turn over preferences.

---

## Validation Rules

**CRITICAL — Verify each modification before applying it.**

| Rule | Detail |
|-------|--------|
| **Max HP** | `pv_actuels` cannot exceed `pv_max` (except temporary effect → add to `states`). Message if exceeded: *"Your max HP is {max}. Cannot exceed this limit."* |
| **Negative HP** | `pv_actuels` can drop to minimum 0 (no negative HP except custom system). If ≤ 0 → automatically add `unconscious` state to `sante.etats`. Message: *"💀 {Name} drops to 0 HP and loses consciousness!"* |
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
- `references/npc-loyalty-limits.md` (in the `mygamemaster` skill) — loyalty system, individual limits, evolution factors for allied NPCs
- `references/verbosity/README.md` (in the `mygamemaster` skill) — emoji convention for change notifications (❤️ HP, 📚 skills, 🔋 states). Use for any sheet modification reported during play.

---

## Integration with Header Skill

This skill is a sub-skill of `mygamemaster`. It loads automatically when the triggers `!sheet`, `!char`, `!notes` are detected.

**Before each action:**
1. Load `mygamemaster` for persona and global conventions
2. Determine the active campaign (check `world.json`)
3. Verify the relevant sheet (`characters/<discord_id>.json`)

**Always respect the header skill principles** (`mygamemaster/SKILL.md` §2 compartmentalization / §9 secrets): players only see their sheets, validation before writing, log every modification, spoiler tags in public channel.

---

## Pitfalls

| ❌ Pitfall | ✅ Solution |
|----------|------------|
| **Discord ID confusion at creation**: a ping `<@ID>` in a message doesn't reveal the message author's ID, but the person mentioned's ID. Don't infer a player's ID from a ping by someone else. | **Always ask each player for their own ID explicitly.** Create the sheet immediately under the correct ID before moving to the next player. |
| Creating a sheet under the wrong ID then needing to move/delete it | Check: *"Your Discord ID is really XXXXX?"* before writing the file |
| **❗ Making up stats for an existing character** — The GM creates a sheet for an already-played character without checking if stats already exist (agent memory, player messages, prior conversation). Ex.: creating [the PC] with [stats A] when the player had defined it with [stats B] earlier. Critical error. | **BEFORE creating or modifying a PC sheet, check IN ORDER:** (1) Agent memory — are stats recorded there? (2) Player messages in history — have they already mentioned stats, class, or inventory? (3) File on disk — does `characters/<discord_id>.json` exist? If yes → read it, don't recreate it. (4) Campaign repo git logs (`git log --all --diff-filter=A -- 'characters/*.json'`) — did a sheet exist then get deleted? If nothing found → ASK the player: "What are your character's stats?" NEVER start from an empty template. NEVER make up stats. |
| **❗ Using the sheet without player confirmation** — The GM narrates actions assuming PC stats without validating them with the player. | After creating or updating a sheet, confirm the stats with the player BEFORE using them in narration. A simple "Here's your sheet, is this right?" is enough. |
| **❗ NPC and location inventory not documented** — The GM tracks the PC's inventory but forgets that of accompanying NPCs and inhabited locations. Inconsistency guaranteed. | **Requirement:** Each recurring NPC (2+ sessions) has an `inventaire` field (free strings) in npc.json. Each key location (cabin, camp, base) has an `inventaire_<location>` field (ex. `inventaire_cabane`) = `{description, contents[]}`. Update with each transfer (via Steward). See `mygamemaster-inventory`. |
