---
name: mj-tonnerre-initiation
description: Onboarding questionnaire for creating a new tabletop RPG campaign. Asks essential questions (theme, rules, world, players) and initializes campaign files.
category: gaming
triggers:
  - "!init"
  - "new campaign"
  - "create campaign"
  - "start campaign"
  - "begin campaign"
---

# 🎲 MJ Tonnerre — Campaign Onboarding

## Objective

Guide the GM (or the group) through a structured questionnaire to create a new campaign. At the end, all files are initialized and the group can start playing immediately.

---

## Solo vs Multi-Player Mode

**Important:** The questionnaire adapts to the number of players.

| Configuration | Approach |
|---------------|----------|
| **Multiple players** | Standard questionnaire — each PC gets their time. The link between PCs is a key question. |
| **Solo (1 player)** | Deepen the character further. No inter-PC relationships to manage → more time for background, motivations, personal dilemmas. The world can be more intimate and reactive to the single PC. |
| **Solo (1 player) — Kingdom Building** | The kingdom is the "second character". Give equal attention to the kingdom's foundations and the PC's psyche. Factions react directly to their actions. |

## Independent Campaigns

**Rule:** A single Discord server can host **multiple independent campaigns**. Example: *"To the End of My World"* (dark fantasy Abyss) and *"The Birth of a King"* (political Kingmaker) coexist.

**To distinguish them at onboarding:**
1. Check if the player comes from an existing campaign with MJ Tonnerre
2. If yes → **explicitly specify** that this is a new and COMPLETELY INDEPENDENT campaign
3. Create a separate campaign folder in `campaigns/<campaign-name>/`
4. Update memory with BOTH campaigns (the new + existing) to avoid confusing them
5. Git: separate repository for each campaign (one `git init` per folder)

**During play:** MJ Tonnerre loads the active campaign based on Discord context (thread, channel, interlocutor). Verify before each narrative response which `world.json` from the CORRECT campaign to use.

---

## Workflow

### Step 1 — The Questionnaire

Ask questions in order, one by one or in logical blocks. Let the group answer. Be enthusiastic — a new campaign is an exciting moment!

#### Block 1: Campaign Identity

1. **Campaign name** — A title that pops. "The Shadows of Eryndor", "Chrome & Sacrifices", "The Last Tavern Before the Apocalypse"...
2. **GM** — Who is the Game Master? (You, MJ Tonnerre, or a human? Default: you.)
3. **Players** — How many? Who? Their Discord handles?

#### Block 2: World & Atmosphere

4. **Theme / Setting** — Propose categories and ask to refine:
   - 🏰 Medieval-Fantasy (heroic fantasy, dark fantasy, low fantasy...)
   - 🤖 Cyberpunk / Sci-Fi (space opera, dystopia, post-apocalypse...)
   - 🌃 Contemporary / Urban (investigation, thriller, modern fantasy...)
   - 🦑 Cosmic Horror (Lovecraft, SCP, psychological horror...)
   - 🏴‍☠️ Historical / Alternate History (pirates, romans, 1920s...)
   - 🌀 Other (specify!)

5. **Tone** — What atmosphere for sessions?
   - Epic / Heroic — the PCs are legends in the making
   - Dark / Gritty — the world is harsh, choices are difficult
   - Humorous / Quirky — we're here to laugh first and foremost
   - Investigation / Mystery — every clue matters
   - Survival / Horror — every resource is precious
   - Mix (ex: 70% epic, 30% humor)

6. **Inspirations** — What works, worlds, films, books, games inspire you?
   - Ex: "Tolkien meets Mad Max", "The Dishonored universe", "Pratchett's books"
   - Note them in `world.json > meta > inspirations`

#### Block 3: Game System

7. **Rule system** — Your choice:
   - **Free / narrative system** — simple rolls, focus on story. You improvise resolutions.
   - **Adapted existing system** — D&D 5e, FATE, PBTA, Cthulhu, OSR... you draw from their mechanics.
   - **House system** — the group defines its own rules.
   - **Existing templates** — load `references/systemes/` for complete pre-built systems (ex: `expedition-abime.md` for Made in Abyss / vertical dark fantasy, `pathfinder-d20-simplifie.md` for Kingmaker / kingdom building).

8. **Crunch level** (1 to 5):
   - 1: Almost no dice, everything is narrative
   - 3: Regular rolls, simple stats, light tactical combat
   - 5: Heavy simulation, many stats, resolution tables

9. **Dice rolls** — Format and options:
   - Standard dice: `!roll d20`, `!roll 3d6+2`, `!roll d100`
   - Advantage / Disadvantage: `!roll d20 advantage`
   - Optional quantum rolls: `!quantum_roll d20`
   - Secret rolls (GM only): `!roll d20 secret`

10. **House rules** — Are there special rules to integrate?
    - Ex: "No PC death without consent", "Critical = bonus narrative effect", "You can spend 1 fate point to reroll"

10bis. **Thematic modules to activate** — Ask which modules the GM wants for this campaign. Each module is a rules block that the main skill loads **only if active** (same pattern as `meta.temps.regime`). Present the list, note the choices (they will go in `world.json > modules` at Step 4).

    > Catalog of available modules (role of each + when to activate): `/opt/modules/gaming/mj-tonnerre/references/modules/README.md` and `references/modules/<x>.md`. The JSON block to write is given in Step 4 (question 2bis).

#### Block 4: Visual & Audio Identity

> **Important:** This block defines the visual and audio DNA of the entire campaign. Once set, all images, character sheets, maps, and audio will inherit from it. The pattern: **style → templates → instances**.

11. **Graphic style** — Choose an artistic direction:
    - 🎨 **Technique**: watercolor, comic book, oil painting, pixel art, line art, dark fantasy digital, anime, photo-realistic, sketch, ink journal...
    - 🌈 **Palette**: autumnal (oranges/browns), icy (blues/whites), infernal (reds/blacks), pastel, cyberpunk neon, vintage sepia...
    - ⚡ **Emotional palette** (new): colors shift based on narrative state — warm and vibrant when the group is safe or happy, cold and dark when anxious or in danger. Perfect for psychological horror or survival atmospheres.
    - ✨ **Visual atmosphere**: epic and grandiose, intimate and melancholic, chaotic and oppressive, dreamlike...
    - Note them in `world.json > meta > visual_style`

12. **Template priorities** — In what order to generate templates?
    - [ ] Character sheet (card/frame design)
    - [ ] World / region map
    - [ ] Portrait frame (vignette style)
    - [ ] Location map (dungeon, tavern, forest...)

13. **Automatic images** — When does the AI generate visuals without being asked?
    - [ ] PC portraits at creation
    - [ ] Illustrated session summary at wrap-up
    - [ ] Encountering a major NPC
    - [ ] Victory against a boss
    - [ ] None (command only via `!image`)

14. **MJ Tonnerre voice** — Audio profiles to configure:
    - `narrator` — storyteller voice, for descriptions and summaries
    - `npc_deep` — male NPCs, authority figures, imposing creatures
    - `npc_high` — female NPCs, children, lively creatures
    - `npc_monster` — distorted voices, growls, entities
    - *Configure on the Hermes side (TTS providers). The skill will call them by name.*

15. **Audio moments** — Which events trigger audio narration?
    - [ ] Session intro (narrative hook)
    - [ ] Descriptions of important locations (first visit)
    - [ ] Boss / major NPC speeches
    - [ ] End of session (audio cliffhanger)
    - [ ] Command only (`!audio`)

#### Block 5: Logistics

16. **Session style**:
    - **Live text** — everyone online at the same time, brisk pace
    - **Post-by-post** — everyone responds when they can, asynchronous
    - **Mixed** — live sessions + ability to play asynchronously between sessions

17. **Discord channel** — Where do we play?
    - Existing channel → note its name
    - New channel → **suggest to the GM/admin to create a dedicated channel** (ex: `#rpg-shadows-eryndor`). Explain why it's better: clean history, no clutter, pins, etc.
    - Thread in existing channel → lightweight alternative
    - **Important:** If this is a different campaign from an existing one on the same server, MAKE CLEAR it's a separate thread/channel.

18. **Frequency** — How often do live sessions happen? (optional — for reference)

---

### Step 2 — World Generation & Visual Templates

Once answers are collected, generate a coherent world based on the inspirations:

**Part A — World:**

1. **Global description** (3-5 hook sentences)
2. **1-3 key regions or locations** (name, atmosphere, feature)
3. **2-4 factions** (name, short_term_objective, long_term_objective, method, attitude). **Objectives are independent of the PCs** — each faction has its own needs (food, territory, survival). Short term objective = what it's doing now (ex: "Stockpile provisions before winter"). Long term objective = its ambition (ex: "Control the region's trade routes").
4. **1 immediate adventure hook** — why the PCs are together and what awaits them at Session 1
5. **2-3 world secrets** — reserved for the GM, stored in `global_state.gm_secrets`

**Part B — Visual templates (style → templates → instances):**

6. **Define the master visual prompt** from `visual_style`:
   - Combine technique + palette + atmosphere into a ~30-word prompt
   - Example: *"Dark fantasy watercolor painting, autumn palette of burnt orange, deep browns and crimson, moody chiaroscuro lighting, epic scale, painterly brushstrokes, high fantasy aesthetic, dramatic skies"*
   - Store it in `meta.visual_style.full_description`

7. **Generate templates in requested order** (block 4, question 12):
   - **Character sheet template**: A blank card/frame in the style, with placeholders for portrait, name, stats — but NO specific character content
   - **World map template**: A map of the main region in the style, with topography but location names as placeholders
   - **Portrait template**: A generic "hero" and "heroine" face in the style, serving as the base for individual portraits
   - Store these templates in `campaigns/<name>/images/templates/`

8. **Remind of the pipeline**: each future generation (`!portrait`, `!sheet`, `!map`) will use these templates as style reference, ensuring visual consistency.

### Step 3 — Character Creation

For each player, create a character sheet. Two modes:

**Guided mode** (recommended): Ask 5-6 questions per player:
- Character name
- Race / Origin
- Class / Archetype / Concept
- Primary personality trait + flaw
- Appearance in one sentence
- Link to another PC (optional but recommended)

**Manual mode**: The player fills it in themselves via `!character`

**Solo mode:** Deepen the questions. The solo player has more room for psyche, backstory, dilemmas. Inter-PC links replaced by link to the world (why this land? why now?).

For each character, generate:
- Base stats adapted to the chosen system
- Starting equipment coherent with the world
- A personal hook tied to the world

### Step 4 — Technical Initialization

Create the files:

1. Copy template → `campaigns/<campaign-name>/world.json`
2. Fill `world.json` with questionnaire answers + generated world
2bis. **Write the `modules` block** at the root of `world.json` (at the same level as `meta`, `system`, `rules`, `global_state`, `world`), based on choices from question 10bis. Repeat the `_schema` from the template below **word for word** (it documents the contract for the main skill), and set `active: true/false` according to what the GM requested. Empty `params: {}` = module defaults.

   ```json
   "modules": {
     "_schema": "Each module is loaded/applied by the main skill only if active==true (pattern from meta.temps.regime). params={} = module defaults; override here to adjust without touching the skill. See /opt/modules/gaming/mj-tonnerre/references/modules/README.md",
     "travel":               { "active": true,  "params": {} },
     "factions":             { "active": true,  "params": {} },
     "npc_proactivity":      { "active": true,  "params": {} },
     "artifacts":            { "active": true,  "params": {} },
     "politics":             { "active": false, "params": {} },
     "weather":              { "active": true,  "params": {} },
     "worldbuilding_places": { "active": true,  "params": {} },
     "kingdom_building":     { "active": false, "params": {} }
   }
   ```

   > A module missing from the block or with `active: false` is inactive: its rules don't apply. The reference schema for this block is in `/opt/modules/gaming/mj-tonnerre/references/modules/README.md` and is validated by `scripts/validate_schema.py` (the `modules` key is required in `world.json`).
3. Create empty `npcs.json` (ready for session 1)
4. Create character sheets in `characters/<discord_id>.json`
5. Create `sessions/` and `images/` folders
6. Initialize `sessions/001.json` with the preamble
7. Initialize git: `git init && git add . && git commit -m "🎲 Campaign initialized"`
8. **Campaign isolation** — No action needed: memory/config isolation is ensured by the **one-container-per-campaign** model (see README). No `hermes profile create` to run.
   > _(History: `references/profiles-multi-campaign.md` described the old Hermes profile mechanism. It's replaced by container-level isolation.)_

9. **If independent campaign:** separate git and separate folder (memory isolation is already ensured by the container)

Announce completion with a stylized message:

```
⚡ CAMPAIGN INITIALIZED ⚡

📜 Name: The Shadows of Eryndor
🌍 World: Dark Fantasy
🎨 Style: Watercolor — autumn palette
🎲 System: Custom D20 — crunch 3/5
🎵 Audio: Narrator + 3 NPC voices
👥 Players: 3 (Gronk, Lyra, Zeph)

📂 Files ready in ~/.hermes/mj-tonnerre/campaigns/shadows-eryndor/
🖼️ Visual templates generated in images/templates/
   • character-sheet.png
   • world-map.png
   • portrait-hero.png / portrait-heroine.png

Thunder rumbles... Session 1 can begin! ⚡
```

---

## Post-Onboarding

After onboarding, update memory (memory tool) with:
- The active campaign name for this Discord channel
- Campaign file path
- Players and their associated characters
- If campaigns coexist → keep track of BOTH to avoid confusing them

Then send a message in the channel: "The campaign is ready. Type `!sheet` to see your character, and when you're ready... let the adventure begin!"

---

## References & Templates

Complete and reusable systems are stored in `references/systemes/`. When a player requests a custom system during onboarding, first check if an existing template fits before creating a new one.

| File | Description |
|------|-------------|
| `references/systemes/expedition-abime.md` | D20 system — Expedition & Abyss (vertical dark fantasy, Mark of the Abyss, Treasure, Fear). Inspired by *Made in Abyss*. Crunch 3/5. |
| `references/systemes/pathfinder-d20-simplifie.md` | Simplified D20 Pathfinder (6 stats: Strength, Dexterity, Constitution, Intelligence, Wisdom, Charisma). Kingmaker/kingdom building inspiration. Crunch 2-3/5. |

> **Isolation:** Campaign memory isolation is ensured by the dedicated container (one container per campaign, see README) — nothing to configure at onboarding. _(History: `mj-tonnerre/references/profiles-multi-campagne.md`, old profile mechanism, now replaced.)_
