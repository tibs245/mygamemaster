---
name: mygamemaster-session
description: Manages session wrap-up and resumption for MJ Tonnerre — formatted summaries (strict hat convention), complete state save, session stats.
category: gaming
triggers:
  - "!cloture"
  - "!reprendre"
  - "!session"
  - "clôture de session"
  - "fin de session"
  - "reprise de session"
  - "résumé de session"
  - "correctifs à prioriser"
  - "Problème / Solution proposée / Conséquence"
  - "post-session"
---

# 📋 MJ Tonnerre — Session Management

## Overview

This skill manages the complete lifecycle of a tabletop RPG session: opening, in-session tracking, wrap-up, and resumption. It maintains `sessions/NNN.json` files and orchestrates the saving of global state (world, characters, NPCs) at each wrap-up.

## Commands

| Command | Effect |
|----------|-------|
| `!session info` | Current session stats (duration, actions, participants) |
| `!session resume` | Mid-session summary (what has happened so far) |
| `!cloture` | Wrap up the session → formatted summary + state save + suggestions |
| `!reprendre` | Load context from last session → summary + group state + teaser |

---

## File Architecture

> ✅ **Campaign path discovery (SINGLE DEFINITION — referenced below by `!cloture` and `!reprendre`) :**
> The current directory (`cwd`) **IS** the campaign (provided by runtime, one container per campaign).
> Resolve all files from `./` : `world.json`, `sessions/`, `characters/`, `npcs.json`, etc.
> Use `find` **only as a last resort**, if `cwd` is NOT the campaign :
> ```bash
> # Fallback only — cwd is normally already the campaign
> find . -name "world.json" 2>/dev/null | head -1
> ```

```
<cwd = campaign directory>/
├── world.json              ← Global state, factions, timeline, time config
├── events.json         ← Single timeline, structured in UT (Time Units)
├── npcs.json                ← All NPCs (state, position, relations)
├── characters/<id>.json   ← Player character sheets (HP, inventory, states)
├── sessions/
│   ├── 001.json            ← Detailed log session 1
│   ├── 002.json            ← Detailed log session 2
│   └── ...
├── outils/
│   └── gestion_temps.py    ← Python scripts for timeline querying/validation
└── images/                 ← Campaign illustrations
```

### The UT System (Time Unit)

**1 UT = 10 minutes.** Any significant action consumes at least 1 UT. Multiple quick actions can be grouped into a single descriptive event (e.g.: "I open the door, peek inside, back away" → 1 single event).

| Unit | Value |
|-------|--------|
| 1 day | 144 UT |
| 1 year (365d) | 52 560 UT |
| t=0 | Campaign start (Session 1) |
| t negative | Pre-campaign past (lore, births, eras) |

Possible event types: `globale`, `ville_lieu`, `personnage`, `pnj`, `faction`, `artefact`, `quete`, `meta`.

The scripts in `outils/gestion_temps.py` allow :
- Calculate next available t
- Convert a game date (e.g. "Day 3, morning") to t
- Extract filtered events (by type, entity, location, period)
- Get full entity history (get_entity_history)
- Get interaction history between two entities (get_relation_history)
- Generate world snapshot at time T (get_world_state)
- Validate timeline integrity

---

## Session Format (`sessions/NNN.json`)

```json
{
  "session": 1,
  "date": "2026-05-14",
  "heure_debut": "20:00",
  "heure_fin": "23:30",
  "canal": "Discord #jdr-tonnerre",
  "participants": ["discord_id_1", "discord_id_2"],
  "titre_episode": "",
  "resume": "",
  "actions": [],
  "pnj_rencontres": [],
  "lieux_visites": [],
  "etat_fin": {},
  "teaser": ""
}
```

### Field Details

| Field | Type | Description |
|-------|------|-------------|
| `session` | number | Incremental number (001, 002...) |
| `date` | string | ISO date (YYYY-MM-DD) |
| `heure_debut` | string | Start time HH:MM |
| `heure_fin` | string | Wrap-up time HH:MM (filled at wrap-up) |
| `canal` | string | Discord channel of the session |
| `participants` | string[] | Discord IDs of present players |
| `titre_episode` | string | Episode title (set at wrap-up) |
| `resume` | string | Formatted narrative summary (filled at wrap-up or `!session resume`) |
| `actions` | object[] | Log of all session actions |
| `pnj_rencontres` | object[] | NPCs met with date and notes |
| `lieux_visites` | object[] | Locations visited with date and notes |
| `etat_fin` | object | Global state at session end (snapshot) |
| `teaser` | string | Hook for next session (set at wrap-up) |

### Action Format

```json
{
  "timestamp": "2026-05-14T20:15:00",
  "type": "jet|action|combat|dialogue|modif_perso|meta",
  "joueur": "discord_id",
  "description": "Attempts to pick the lock on the north door",
  "details": {},
  "resultat": "Success — the door creaks open"
}
```

### Met NPC Format

```json
{
  "nom": "Elara",
  "role": "Marsh Guardian",
  "attitude": "Wary → Ally",
  "relation_niveau": "Ally",
  "lieu": "The Raven Tavern",
  "notes": "Gave the amulet quest"
}
```

### Visited Location Format

```json
{
  "nom": "The Raven Tavern",
  "type": "Tavern",
  "region": "Lower City",
  "notes": "Quest starting point"
}
```

---

## `!session info` — Current Session Stats

Display the current state of the session without wrapping it up.

### Workflow

1. Identify active campaign (channel context)
2. Determine current session number (last `sessions/NNN.json` with empty `heure_fin`, or new file if needed)
3. Read session file
4. Calculate stats
5. Display

### Output Format

```
╔══════════════════════════════════════════╗
║  📊 SESSION {N} — {DATE}               ║
╚══════════════════════════════════════════╝

⏱️ Duration : {elapsed since heure_debut}
👥 Participants : {count} ({list})
🎬 Actions : {count}
👤 NPCs met : {count}
📍 Locations visited : {count}

💡 `!session resume` for a narrative summary
💡 `!cloture` to end the session
```

---

## `!session resume` — Mid-session Summary

Generate a formatted summary of what has happened **so far** in the current session. Same format as wrap-up but without the `🔮 NEXT` section.

### Workflow

1. Load active campaign
2. Read current session file
3. Iterate through `actions[]`, `pnj_rencontres[]`, `lieux_visites[]`
4. Query group state via `characters/<id>.json` of participants
5. Generate narrative summary (3-5 immersive sentences covering key events)
6. Format per **hat convention** (sections `🎭 SUMMARY`, `📍 LOCATIONS VISITED`, `👤 NPCs MET`, `⚔️ KEY ACTIONS`, `💀 GROUP STATE`)

### Output Format

```
╔══════════════════════════════════════════╗
║  ⚡ SESSION {N} — {DATE}                ║
║  📜 In progress...                      ║
╚══════════════════════════════════════════╝

🎭 SUMMARY
{Narration 3-5 immersive sentences}

📍 LOCATIONS VISITED
• ...

👤 NPCs MET
• ...

⚔️ KEY ACTIONS
• [{Player}] {action} → {result}

💀 GROUP STATE
• {Character} : {HP}/{Max HP} HP, {states}
```

---

## `!cloture` — Session Wrap-up

### This is THE critical command. It locks the session state and prepares the next one.

### Complete Workflow

#### Conversational Triggers

Wrap-up can be requested **without** the explicit `!cloture` command. Detect the following natural phrasings :

| GM Phrase | Action |
|--------------|--------|
| "Save the session" | Trigger full `!cloture` |
| "Let's do the debrief" / "Let's wrap up" | Trigger full `!cloture` |
| "End of session" / "Session over" | Trigger full `!cloture` |
| "Write the summary" / "Final summary" | Trigger full `!cloture` |
| "Wrap-up" / "Wrapping up" | Trigger full `!cloture` |
| "That's where we stop" / "We're done" | Trigger full `!cloture` |

In all cases, execute the complete wrap-up workflow (Phase 1-6). Don't interrupt the GM — let the narrative transition moment happen, then continue.

### Phase 1 — Collection

0. **Campaign path** → The `cwd` IS the campaign. Resolve all files from `./` (see "Campaign path discovery" in *File Architecture* section).

1. **Identify active campaign** (Discord channel context)
2. **Determine session number** — look for `sessions/NNN.json` file with empty `heure_fin`. If multiple sessions have empty `heure_fin` → alert the GM.
3. **Ask for episode title** if not set :
   ```
   📜 Before wrapping up: what title for this episode?
   (or type "skip" for me to choose a default title)
   ```
   ⚠️ **Fallback — no response :** If the GM doesn't respond within 10 minutes, **don't block wrap-up**. Proceed with a default title derived from session events (e.g. *"The Abyss Pact"*, *"The Ruins' Call"*). Tell the GM :
   ```
   (Default title used: "The Abyss Pact" — you can edit it in sessions/NNN.json)
   ```
4. **Ask for teaser** for next session :
   ```
   🔮 A teaser for the next session? (1-2 sentences, or "skip" to skip)
   ```
   ⚠️ **Fallback — no response :** Same rule. Wait max 10 minutes (or 2 follow-up messages), then auto-generate a teaser based on last location visited and active quest. Tell the GM :
   ```
   (Teaser auto-generated — you can edit it)
   ```
5. **Ask for player evaluation** (if `world.json > meta.diagnostic.actif == true`) :
   ```
   ⭐ Session rating — score 1 to 5?
   (1 = frustrating/incoherent, 5 = memorable/immersive. Or "skip" to skip)
   ```
   If player gives a score → ask for optional comment :
   ```
   💬 Comment on this session? (strengths, weaknesses, "skip" if none)
   ```
   ⚠️ **Fallback — no response :** Same rule as title/teaser. If no response in 10 minutes, don't block. Continue without evaluation.
   
   **Storage :** Evaluation is recorded in `collecte.csv` with :
   - `origine_type = "Joueur"`, `origine_detail = <username>`, `action_type = "evaluation_session"`
   - `exactitude = <score>` (reuse column for player score)
   - `notes = <player comment>`

### Phase 2 — Summary Generation

1. **Compile key actions** — iterate through `actions[]`, select most narrative/impactful (not minor rolls)
2. **List visited locations** from `lieux_visites[]`
3. **List met NPCs** from `pnj_rencontres[]`
4. **Collect group state** — read ALL `characters/<id>.json` of participants, extract `sante.pv_actuels`, `sante.pv_max`, `sante.etats`
5. **Calculate elapsed session time** — sum `duree_ut` of logged actions. Use `outils/gestion_temps.py` to convert if needed.
6. **Write narrative summary** (3-5 sentences) — immersive style, MJ Tonnerre tone
7. **Store complete formatted summary** in `resume` field of session file

### ⚠️ ABSOLUTE RULE — Timeline Data Integrity

**NEVER INVENT GAME EVENTS THAT WERE NOT PLAYED.**

This is the most dangerous pitfall in timeline management. Here's what happened (and was corrected) :

```
❌ ERROR: Sessions 1 and 2 are separated by a night.
I invented a "Day 2" that didn't exist.
→ The admin corrected me: "we only played half a day"

✅ CORRECTION: Sessions 1 and 2 occur on the SAME half-day.
Session 2 resumes where Session 1 ended, same day.
t=36 (end S1) → t=36 (start S2, no time jump)
```

**Concrete rules :**

1. **Base ONLY on data from played sessions.** Every event in `events.json` must be traceable to an action in `sessions/NNN.json` or explicit info in `world.json`/`npcs.json`.

2. **NEVER assume time passage between sessions.** If Session 1 ended at noon and Session 2 starts, game time has NOT advanced unless the GM explicitly says so. Real time between sessions (24h, 3 days) is NOT game time.

3. **Pre-campaign events (negative t) are the only ones "invented" from lore.** But even they must be based on established facts in `world.json` (eras, dates, descriptions). No free extrapolation.

4. **When building or updating the timeline, verify each event against its source** (session data, world.json, npcs.json). If you can't trace an event, it's probably invented → delete it.

5. **When in doubt, add a source comment** (field `source` in events.json) : `source: "session_001"` or `source: "campaign_lore"` or `source: "manual"`. Events with `source: "manual"` must be validated by the admin before being considered canon.

### Phase 3 — State Save (Data Verification)

**⚠️ MANDATORY PRE-PHASE — DATA VERIFICATION :**
Before any save, verify these critical points. This is the iron rule — no wrap-up without it.

```
🛡️ DATA VERIFICATION — PRE-WRAP-UP
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
□ INVENTORIES — Every item used, given, lost, or found during session
   → Read characters/<id>.json of each participant
   → Verify item-by-item what changed
   → Ex: consumable used → removed from inventory
   → Commit after correction

□ LOCATIONS — Every location visited during session
   → Read lieux_visites[] in session file
   → Verify their presence in world.json > universe.regions > lieux
   → If a location is missing → add it with MINIMUM description in living format (conflit_central, questions_vitales, pnjs_cles, ambiance, horloge with evenement/echeance/consequence)
   → Each existing location that changed state in session must have conflit_central or horloge updated to reflect new state (ex: a cabin's lean-to advancing, a bucket cleaned, a road discovered)
   → Locations must be "living" — their state changes with game time and PC actions. Don't leave them in simple static format (description + conflict + ownership). ALL locations, without exception (including minor resources like Wild Privet), must have full format: conflit_central, questions_vitales (governance, reason_existence, critical_need, shameful_secret), pnjs_cles, ambiance, horloge with evenement/echeance/consequence. A location in simple static format is one that will be forgotten during updates.

□ DISTANCES — Every journey narrated during session
   → Verify world.json > regles.temps.deplacements
   → If journey durations were mentioned in narration
     but not in file → add them
   → Verify indirect ≥ direct rule for any new route
   → Commit after correction

□ NPCs — Every NPC met or mentioned
   → Verify npcs.json for each pnj_rencontres[] entry
   → If NPC already exists → update position/attitude/last interaction
   → If NPC doesn't exist → create sheet (stats, skills, limits, inventory)
   → Commit after correction

□ OBJECT/SITE STATE — Everything that changed physically
   → Verify world.json > global_state (state section specific to campaign, ex. tracked sites/structures)
   → Each visited site/object whose state changed (cleaned, repaired, activated, destroyed)

□ ARTIFACTS — Important objects discovered or moved during session
   → Verify world.json > global_state.artefacts_connus
   → If important object discovered → create entry with description, source, location, hypotheses
   → If existing object changed hands or location → update localisation_actuelle
   → Links between artifacts must be marked UNCONFIRMED HYPOTHESIS — never presented as facts
   → If no artefacts_connus section exists in world.json → create it

□ FACTIONS — Direct interactions with factions
   → Update attitude, last interaction, observed clues
   → Advance clock: move deadlines closer by session duration
   → If deadline reached → note consequence
   → Verify each faction has ≥ 1 short-term + ≥ 1 long-term objective

□ CROSS-CHECK CLOCK vs SESSION — NARRATIVE VERIFICATION (⚠️ MANDATORY)
   ⚠️ Don't confuse "valid file" with "consequences played".
   → Open faction_actions_horloge.actions
   → For EACH active action, verify if ITS TRIGGER occurred
     during session (not just if deadline was reached)
     → If yes → was consequence played in THIS session?
       → If NO → THIS IS A PROBLEM. Play it NOW in narration,
         or note as critical priority for next session opening.
   → For each facteur_modificateur saying "immediate, major reaction":
     verify if condition was met. If yes and not played → critical priority.
   → Generic error example: modifier "If [NPC] reaches [key objective] → immediate,
     major reaction". Trigger met. Nothing played. Discovered 3
     checks later. Don't repeat.
   → See also factions module (`references/modules/factions.md`, Pitfall "CROSS-CHECK
     CLOCK vs SESSION") for complete example + rules.

→ Once all points checked and committed → proceed to save
```

### Phase 4 — Scripts Pipeline (Transactional Audit)

Before closing, apply the Steward verification pipeline to all session actions.
It uses available scripts, including `build_brief.py` to verify each NPC met.

```
SCRIPTS=/opt/modules/gaming/mygamemaster/scripts
CAMP=.                 # cwd IS the campaign

# Structural validation (JSON, distances, clock, session gaps)
python3 $SCRIPTS/close_session.py $CAMP --titre "<episode title>" --teaser "<teaser>"
```

`close_session.py` chains `validate_json.py`, `validator-distances.py`,
`check_session.py`, `clock.py --dry-run` then ~10-point pipeline check.
Exit != 0 = wrap-up refused: fix listed points then re-run.

**Available audit scripts (see also `mygamemaster-analyste` for 3 layers) :**
- `build_brief.py <campaign> <npc> --cache` : extract NPC brief (MD5 cache)
- `call_pnj.py <campaign> <npc> <context> --dry-run` : simulate RP response

Pipeline report goes to GM, never to players.

### Phase 5 — Orchestration !cloture (4 Components)

`!cloture` chains 4 sub-commands in order. Each sub-command is
an independent, reusable skill.

#### Step 1 — 🐞 Steward Audit (`!analyse-bug`)

Calls `mygamemaster-analyste/SKILL.md` in **wrap-up audit mode**.
Verifies ALL points: weather, time, inventories, NPCs, locations, factions,
clock, artifacts.

Output : `sessions/NNN-audit.md`

GM reads audit with player and validates each proposed correction
before moving to next step.

**Rule :** If audit detects blocking gap → report to player.
Wrap-up doesn't continue until gap is resolved or explicitly
ignored by player.

#### Step 2 — 📋 Factual Report (`!game-report`)

Calls `mygamemaster-game-report/SKILL.md`.
Generates factual report: actions, locations, NPCs, decisions, inventory.
No spoilers. Nothing the player doesn't already know.

Output : `sessions/NNN-rapport.md`

#### Step 3 — 📖 Narrative Account (`!write-history`)

Calls `mygamemaster-write-history/SKILL.md`.
GM writes narrative summary novel-style (or uses LLM from session).
No game mechanics.

Output : `sessions/NNN-recit.md`

#### Step 4 — 🎨 Illustration (`!image`)

Calls `mygamemaster-images/SKILL.md` (use: session-end illustration).
Generates session-end image based on key moment.

Output : `images/scenes/session_{NNN}_recap.png`

### Phase 6 — Save, Commit & Summary

> ℹ️ The timestamped session-end snapshot is **automatic** (hook `on_session_end`, ON by default). Your responsibility is **data propagation** (locations, distances, NPCs) and **commit** below. Don't add any manual snapshot orders.

After Phase 5's 4 steps, GM :
1. Verify `sessions/NNN.json` has current `heure_fin`, `resume`, `etat_fin`
2. Update global data (timeline, faction clock, NPC positions)
3. **Validate JSON** of each modified file (commit is **automatic** — hook `auto_commit` — but doesn't freeze broken JSON)
4. Prepare `sessions/{NNN+1}.json`
5. Display summary

#### Final Summary

```
╔══════════════════════════════════════════╗
║  ⚡ SESSION {N} WRAPPED UP              ║
╚══════════════════════════════════════════╝

🐞 Audited : {X} points, {Y} gap(s) → ✅ resolved
📋 Report : sessions/NNN-rapport.md
📖 Account :   sessions/NNN-recit.md
🎨 Image :   images/scenes/session_NNN_recap.png
📊 Collection : {Z} entries in collecte.csv {+ player rating if given}

✅ Session {N} wrapped up and saved.
🔄 Session {N+1} ready. `!reprendre` to start.
```

---

## `!reprendre` — Session Resumption

Load context from last session to resume narration.

### Workflow

0. **Campaign path** → The `cwd` IS the campaign. Resolve all files from `./` (see "Campaign path discovery" in *File Architecture* section).

0bis. **Living World Projection (B3) — if `meta.features.temporalite` != false AND `actors.json` present.** *(Everything ON by default: act on this only if explicitly `false`.)* Before ANY opening narration, project world to now :
   ```bash
   python3 /opt/modules/gaming/mygamemaster/scripts/world_tick.py pre . --apply
   ```
   - **Read returned LIVING WORLD BRIEFING** (upcoming crossings, actors promoted "hot", LOD distribution) : this is context produced by the world **without you**. It tells you *which clocks chime* and *who crosses the player's path*.
   - **DON'T narrate this briefing as-is** : it's a GM sheet, not player text. Use it to shape the scene.
   - **Respect player agency** : this step projects the **world** (actors, clocks), it **doesn't decide** where the PC is. Player chooses position (next steps / hat section "Default Location at Start"). Write the **scene clue** `.banquier/scene-<session_id>.json` (`{"lieu_id":"lieu:…"}`) **only after** player says where they are.
   - **FAIL-OPEN** : `world_tick.py` is fail-open and guards itself on `temporalite` (inert without `geo.json`/`actors.json`). If script fails or files missing → **ignore** and start normally. Living world is a bonus, never a requirement.

1. **Identify active campaign**
2. **Find last session** — look for `sessions/NNN.json` with highest number **with filled `heure_fin`** (previous session). Don't take a session with empty `heure_fin` (would be current session, not previous).
3. **Read session file**
4. **Load player character sheets** of participants for current state
5. **Handle time gap between sessions** — if game time elapsed between wrap-up and resumption :
   - **Rations** — recalculate consumed rations if GM announces ellipse (e.g. "you camped one night")
   - **NPCs** — GM decides if important NPCs acted in interval
   - **Campaign time mechanics** — extra night may advance own mechanic (curse, gauge, cyclic magic defined in `world.json > regles.temps`)
   - **Rest** — long rest between sessions heals minor wounds
   - **If no game time elapsed** (immediate resumption) → nothing to adjust
   - **⚠️ Critical distinction** : real time between sessions is NOT game time. If players resume next day in same room, 0 minutes passed in game, regardless of 24h real time. Game time only advances if GM explicitly decides.

5.5. **⚠️ CROSS-CHECK CLOCK vs SESSION on Resumption** — Verify unplayed triggers from previous session :
   → Open `faction_actions_horloge.actions` and clues from previous session
   → For EACH active action, verify if its **trigger occurred during previous session**
     without consequence being played
   → Unplayed consequence = play it **immediately** at new session opening
     (in narration, not just notes)
   → Generic example : "If [NPC] reaches [key objective] → immediate, major reaction"
     — trigger met in Session N. Nothing played. To play at Session N+1 opening.
   → References : `references/modules/factions.md` (Pitfall "CROSS-CHECK CLOCK vs SESSION") and
     hat checklist (`mygamemaster` §7, item `Cross-check horloge vs session`)
   ⚠️ DON'T confuse "structural verification" (file well-formed)
     and "narrative verification" (promised consequences were played in session).
     Both independent and both MANDATORY.
6. **Update `world.json > regles.temps.suivi`** if game time advanced

### 5.7. **⚠️ STRUCTURAL VERIFICATION PRE-RESUMPTION — PERSISTENCE AUDIT**

Before initializing new session, verify **persistence structures** are in place. A session can be narratively complete (`resume`, `etat_fin`, `teaser`) but have missing structural data that breaks coherence next turn.

```txt
🛡️ PERSISTENCE AUDIT — PRE-RESUMPTION (short checklist)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
□ regles.temps.suivi present in world.json (else: create from etat_fin, don't invent date)
□ events.json present (else: optional, don't block)
□ sessions/{NNN+1}.json ready (else: step 7 creates it)
□ global_state synced with sessions/NNN.json > etat_fin (quete_active, population, phase…)
□ Character sheet in new format (historique[], connaissances_privees[], notes_privees[], session_id)
□ Campaign git clean (working tree clean; commit untracked/modified before resumption)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

> 📄 **Complete procedure** (minimal structure `regles.temps.suivi`, gentle migration of sheets, parent git handling, documented gaps) : `references/audit-persistance-dry-run.md`.

**Process :** DON'T block resumption for these gaps. FIX them before sending opening narration (between step 5.7 and 6.5).

### 6.5. **⚠️ NARRATIVE DETAIL VERIFICATION BEFORE NARRATION — MANDATORY**
Before writing any opening narrative phrase (the reminder with summary, the scene, the question to player), verify EVERY factual detail mentioned against source files :
   → **Clock :** `sessions/NNN.json → heure_fin` — don't advance time without explicit ellipse. Resumption picks up exactly where we stopped.
   → **Actions :** `sessions/NNN.json → actions[]` — don't invent, don't mix actions from different sessions
   → **Locations/Objects :** `sessions/NNN.json → lieux_visites[]` + action logs — verify WHAT happened WHERE. A bouquet isn't in the same bucket as a vial.
   → **NPCs :** position, attitude, what was said — don't assume unplayed changes

   ⚠️ Typical trap : narrative summary feels like we "know" the story. Write fast. Mix things up. THIS is exactly when to slow down, read logs, verify each fact BEFORE writing. 4 bug categories at this weakness moment :

   **a) Time advanced without reason** — open at different time than `heure_fin` without played ellipse.
   **b) Objects mixed between locations** — assign object to wrong location/scene.
   **c) Words put in NPC mouth** — make NPC say a summary the PC didn't express that way.
   **d) Object/relation characterization minimized** — reduce emotional weight of object played as important.

   (Real cases documented : `references/audit-persistance-dry-run.md`.)

   → **Cure :** before writing opening narration, read `sessions/NNN.json → actions[]` + `etat_fin` entirely + `characters/<id>.json` + faction clock. For each factual detail (time, object, location, NPC words), verify trace in logs. No trace = probably invented. Don't start narrative sentence before checking these 4 points.

7. **Display reminder**

### Output Format

```
╔══════════════════════════════════════════╗
║  🔄 RESUMPTION — SESSION {N+1}          ║
║  📅 {DATE}                              ║
╚══════════════════════════════════════════╝

📜 LAST EPISODE : {Title}
{Narrative summary from previous session}

💀 GROUP STATE (current)
• {Character} : {HP}/{Max HP} HP{states}

🔮 TEASER REMINDER
{Teaser}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━
What do you do?
```

### New Session Initialization

1. If `sessions/{NNN+1}.json` doesn't exist → create with :
   - `session: N+1`
   - `date: today`
   - `heure_debut: now`
   - `canal: current channel`
   - `participants: participants from previous session`
   - Empty fields for rest
2. If file already exists (created at wrap-up) → update `heure_debut` with current time
3. Ping participants : `@participant1 @participant2 — session resumes!`

---

## Auto Wrap-up

Configurable option for the GM. If enabled in campaign context :

### Rules

1. **Inactivity delay** : 2 hours without message in campaign channel → suggest automatically :
   ```
   ⏰ No activity for 2h.
   Wrap up the session? (!cloture / continue)
   ```

2. **Explicit signal** : If GM or player explicitly requests wrap-up (even without exact `!cloture`), suggest command.

3. **Configuration** : store in `world.json` :
   ```json
   {
     "meta": {
       "cloture_auto": true,
       "delai_inactivite_minutes": 120
     }
   }
   ```

---

## Systematic Logging

Each session event is logged **in two places** :

### 1. `events.json` (structured timeline)
- **Session start** → event type `meta` : `t=current, label="START Session N — ..."`
- **Player action** → event type `personnage` : t, label, desc, participants, roll, duree_ut
- **Location visit** → event type `ville_lieu` : t, label with location description
- **NPC meeting** → event type `pnj` or `personnage` depending on focus
- **Session end** → event type `meta` : `t=current, label="END Session N — ...", fin_session=true`
- **Global event** (quest advances, faction reacts, phenomenon) → type `globale` or `quete`

Use `outils/gestion_temps.py` (CLI or Python module) to add and validate events.

### 2. `sessions/NNN.json` (detailed narrative log)
- **Session start** → action type `meta` : `"Start of session {N}"`
- **Player action** → action type `roll|action|combat|dialogue` with player and description
- **Sheet modification** → action type `modif_perso` (see `mygamemaster-personnage` skill)
- **NPC meeting** → add to `pnj_rencontres[]`
- **Location visit** → add to `lieux_visites[]`
- **Wrap-up** → action type `meta` : `"Session {N} wrapped up"`

**Rule :** `events.json` captures factual truth (what, who, where, when, result). `sessions/NNN.json` captures narrative (how, why, reactions, mood). Both are complementary.

**⚠️ TIMING REQUIREMENT :** NPC interactions (questions, answers, dialogues) must be recorded in `sessions/NNN.json` **at the moment they are narrated**, not deferred until wrap-up. Don't delay — risk of forgetting is maximal between narration turns. If you narrate an NPC question without adding it to actions, stop, add it, then continue. Players checking files (via `!analyse-bug`) expect to find each interaction immediately.

### 🔴 Real-time Recording Procedure — Multi-NPC

When a scene involves **multiple NPCs speaking in turn**, risk of forgetting is maximal because narration flows fast. Apply this procedure BEFORE sending the response :

1. WRITE the narration (NPC dialogue + PC reaction)
2. STOP — before sending, verify :
   - Each speaking NPC → an action in actions[] ?
   - Each named NPC → an entry in pnj_rencontres[] ?
   - Unknown NPC until now? → sheet in npcs.json (name, role, description, attitude)
   - Did PC respond to NPC? → record response in same action
3. SEND the response

**⚠️ "Onion" trap :** After `!analyse-bug` flagging missing interaction, don't fix just that point. Reread ENTIRE current session before replying — isolated fix often hides 2-3 other omissions in same scene. After 1st report, read `actions[]` entirely, `pnj_rencontres[]`, ask player if anything else missing. Fix everything in ONE commit, not 4.

---

## Integration with Other Skills

| Skill | Interaction |
|-------|-------------|
| `mygamemaster` (hat) | This skill auto-loads on `!cloture`, `!reprendre`, `!session` |
| `mygamemaster-personnage` | `!cloture` reads all sheets for group state; `!reprendre` too |
| `mygamemaster-inventaire` | `!cloture` saves inventories via character sheets |
| `mygamemaster-outils` | Rolls/actions logged in `actions[]` formatted by `mygamemaster-outils` |
| `mygamemaster-intendant` | `!cloture` writes player evaluation to `collecte.csv` (Phase 1 step 5) |
| `mygamemaster-initiation` | Campaign first session created after `!init` |

---

## Anti-Patterns

| ❌ Avoid | ✅ Do |
|------------|---------|
| Wrap-up without saving character sheets | Save ALL `characters/<id>.json` of participants |
| Forget to ask for title and teaser | Ask both questions before displaying summary |
| Generate summary without rereading actions | Go through `actions[]` and select key moments |
| Create duplicate session | Check file existence before incrementing |
| Display summary in DM | Always in public channel (it's the session end wall, everyone must see) |
| `!reprendre` without checking current state | Load character sheets for real state (not just `etat_fin`) |
| Leave `heure_fin` empty indefinitely | Auto wrap-up after 2h inactivity if enabled |
| Log in wrong session file | Always identify correct `NNN.json` via last created file |
| **Forget to update `events.json` at wrap-up** | **Add session events to `events.json` (key actions, locations, NPCs, session end)** |
| **Calculate t manually** | **Use `outils/gestion_temps.py` (CLI or module) to avoid calculation errors** |
| **Log same event differently in both files** | **Keep same factual info (t, participants, location, result) in events.json and session/NNN.json** |
| **Forget to update time tracking** | **After EVERY session, update `world.json > regles.temps.suivi` : t_current, rations, mission constraint** |
| **Treat real time as game time** | **24h real between sessions ≠ 1 game day. Game time only advances if GM explicitly decides.** |
| **Invent time jumps or unplayed days in events.json** | **Only add what was ACTUALLY played. If session continues same instant, t doesn't change. Only events traceable to played action are canon.** |
| **Narrate `!reprendre` opening without checking logs first** | **Before any narrative sentence, check 4 points from step 6.5 (`actions[]`, `lieux_visites[]`, `pnj_rencontres[]`, `etat_fin`, `heure_fin`).** |

> **General** anti-patterns (narrating without saving, words put in NPC mouth, minimize played object, forget NPC interaction) are defined in hat `mygamemaster/SKILL.md` §4 and §6 — don't recoppy here. Real cases documented : `references/audit-persistance-dry-run.md`.

---

## 🔧 Post-session Corrective Maintenance

> Between sessions, GM or player may request a **series of file corrections** that are neither wrap-up (session already done) nor resumption (next one hasn't started). This workflow covers that scenario.

### Conversational Triggers

| User Signal | Action |
|---|---|
| "Create a Problem/Solution/Consequence file" | Use `references/template-probleme-solution-consequence.md` |
| "Did you note our previous points?" + list | Apply checklist below on each listed point |
| "Fixes to prioritize before resumption" | Treat as post-session checklist, commit before replying |

### Procedure

1. **Parse checklist** — extract each fix as independent entry (target filename, change nature)
2. **Group by file** — multiple fixes in same file = single `patch` or logical grouping
3. **Apply each fix** — in order, committing after each modified file
4. **Document in Problem/Solution/Consequence file** — create or update `probleme-session<N>.md` with reference template structure
5. **Verify with local git** — `git status` must be clean. Commit with descriptive message.
6. **Summarize for requester** — table of fixes with status (✅ applied / ❌ blocked)

### Typical Checklist

| # | Point | Target File | Typical Command |
|---|-------|--------------|---------------|
| 1 | Add `regles.temps.suivi` | `world.json` | `patch` / `write_file` |
| 2 | Sync `global_state` | `world.json` | `patch` (quete, pop, phase, influence) |
| 3 | Create next session | `sessions/NNN+1.json` | `write_file` (from last `etat_fin`) |
| 4 | Migrate character sheet | `characters/<id>.json` | `patch` (historique, connaissances_privées) |
| 5 | Create/update NPC | `npcs.json` | `patch` (attitude, position) |

### Pitfalls

**⚠️ Don't confuse "maintenance" and "resumption" :** This workflow applies TO FILES, not narration. No scene is played. If requester also wants to resume game, that's resumption (`!reprendre`) including structural verification (step 5.7 of `!reprendre`).

**⚠️ Don't invent data :** Extract values from existing sessions. If info missing, ask GM. Don't replace food dates with current day.

**ℹ️ Auto commits :** each **valid** campaign file write auto-commits (hook `auto_commit`, one commit per mutation) — git log serves as fine audit trail. You don't launch `git`; just ensure JSON valid after each write.

---

## Complete Workflows

### Typical Session Wrap-up

```
GM: !cloture

1. [Identify campaign] → "Shadows of Valombre"
2. [Find session] → sessions/003.json (empty heure_fin)
3. [GM Questions]
   Bot: 📜 What title for this episode?
   GM: The Guardian's Awakening
   Bot: 🔮 A teaser for next session?
   GM: The ruins collapse... but something glimmers in the rubble.

4. [Generate summary]
   - Actions: 12 actions including 3 key ones
   - Locations: Guardian's Crypt, Sunken Temple
   - NPCs: Spectral Guardian, Lyra the Ferryman
   - Group state: Kael 7/12 HP (Poisoned), Lyra 15/15, Thorn 3/10 (Unconscious)

5. [Save]
   - sessions/003.json → heure_fin, resume, teaser, etat_fin
   - world.json → global state saved
   - npcs.json → NPCs saved
   - characters/123.json, characters/456.json, characters/789.json → sheets saved
   - Create sessions/004.json (empty, ready)

6. [Display formatted summary]

7. [Suggestions]
   Bot: 🎙️ Offer audio reading of summary?
   Bot: 🎨 Generate session-end illustration?

8. [Confirmation]
   Bot: ✅ Session 3 wrapped up. Session 4 ready.
```

### Typical Session Resumption

```
GM: !reprendre

1. [Identify campaign] → "Shadows of Valombre"
2. [Find last session] → sessions/003.json (most recent with filled heure_fin)
3. [Load context] → resume, teaser, participants
4. [Load character sheets] → current state of Kael, Lyra, Thorn
5. [Handle time gap] → rations, NPCs, rest, Mark
5.5. [CROSS-CHECK CLOCK vs SESSION] → Verify unplayed triggers from previous session.
     Ex: "If [NPC] reaches [key objective] → immediate reaction"
     was triggered but not played → play at opening.
6. [Init new session] → sessions/004.json, heure_debut = now
7. [Display formatted reminder]
8. [Ping participants] → @Kael @Lyra @Thorn
```

---

## Multi-Agent Loop

> The multi-agent turn loop (GM / player / Steward / NPC and Faction agents) is defined in hat `mygamemaster/SKILL.md §3.3`. Refer there — don't recoppy here.

Minimal reminder : Steward applies its 3 transactional controls (SOURCE → TRANSFER → COHERENCE) regardless of action sender.

---

## References

- `references/audit-persistance-dry-run.md` — Complete campaign data persistence audit methodology (step-by-step checklist, documented pitfalls, report format). From S7 dry-run audit (2026-05-30). Use for proactive verification.
- `references/template-probleme-solution-consequence.md` — Problem/Solution/Consequence format to document post-session fixes. Includes usage rules and example. Use in corrective maintenance passes.

## Dependencies

- **Parent skill** : `mygamemaster` (auto-loads in RPG session — provides general time management, coherence checklist, multi-agent turn loop §3.3)
> All paths below relative to `cwd` (= campaign directory).
- **Files** : `./sessions/NNN.json`
- **Files** : `./world.json` (including `regles.temps.suivi` for game time tracking)
- **Files** : `./events.json` (timeline structured in UT)
- **Files** : `./npcs.json`
- **Files** : `./characters/<id>.json`
- **Scripts** : `./outils/gestion_temps.py` (t calculations, validation, queries)
- **Required skills** : `mygamemaster-personnage` (sheet reading), `mygamemaster-outils` (action formatting), `mygamemaster-intendant` (Steward — CSV collection)
- **Files** : `collecte.csv` — diagnostic data (player evaluation written at wrap-up, Phase 1 step 5)
- **Files** : `world.json > meta.diagnostic` — enable/disable player collection at wrap-up
- **References** : `references/template-probleme-solution-consequence.md` (post-session fix template)
- **No external tools** needed — everything via JSON files

---

## Verification

- [ ] `!session info` displays stats without error
- [ ] `!session resume` generates formatted mid-session summary
- [ ] `!cloture` asks title + teaser questions before summary
- [ ] `!cloture` saves `world.json`, `npcs.json`, and ALL character sheets
- [ ] **`!cloture` updates `world.json > regles.temps.suivi` (game date/time, t_current, rations, mission constraint)**
- [ ] `!cloture` increments session number and creates next file
- [ ] **`!cloture` adds session events to `events.json`**
- [ ] `!cloture` verifies rations consumed passively during session
- [ ] **`!cloture` verifies spatial data current (routes, locations, NPCs) in world.json and npcs.json**
- [ ] **`!cloture` advances `faction_actions_horloge`** and verifies reached deadlines
- [ ] `!reprendre` finds correct session (last with filled `heure_fin`)
- [ ] `!reprendre` initializes new session (`heure_debut`)
- [ ] **`!reprendre` handles time gap between sessions (rations, NPCs, Mark, rest)**
- [ ] **`!reprendre` performs pre-resumption structural verification (step 5.7) — regles.temps.suivi, events.json, global_state vs etat_fin sync, character sheet, git**
- [ ] **`!reprendre` performs cross-check clock vs session (step 5.5)** to play unplayed consequences from previous session
- [ ] **`!reprendre` doesn't confuse real time and game time**
- [ ] **`!reprendre` checks 4 narrative points (step 6.5) before writing opening**
- [ ] Summary respects **exactly** hat convention (frame ╔═╗, sections with emojis)
- [ ] Spoilers used if sensitive info appears in public channel
