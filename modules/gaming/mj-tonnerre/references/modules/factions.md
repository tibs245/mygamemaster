# Module — Factions, proactive clock and PC objectives

> **Conditional loading.** This module only applies if the campaign declares `world.json > modules.factions.actif === true`.
>
> This module is **the single source of truth** for faction and clock golden rules. The references `faction-tracking.md` (complete JSON templates), `pj-objectifs-obstacles.md` (difficulty/danger/notoriety grids) and `cross-check-horloge-vs-session.md` **expand on** these golden rules without duplicating them.

## 1. Faction tracking

**Why it matters:** Factions advance their interests outside of PC actions. If they are not tracked, they become static scenery instead of dynamic forces.

**Structure to maintain in `world.json > global_state.factions`:** each faction must **mandatory have**:
- `nom` — unique identifier
- `attitude_actuelle` — toward the PCs (Unknown, Neutral, Hostile, Friendly, etc.)
- `derniere_interaction` — session and context of the last trace/encounter
- `indices_observes` — array of evidence or signs of their activity (with session reference)
- `relations_inter_factions` — object listing relations with other factions (Alliance, Truce, Hostility, Domination, Competition, Mistrust, Neutral, etc.) — optional if the faction has not yet interacted with others
- `objectif_court_terme` — what it is doing now, **independent of PCs** (e.g. "Stockpile provisions before winter", not "Observe the PC's arrival")
- `objectif_long_terme` — its true long-term ambition
- `notes_mj` — hidden information for the GM only

**Faction objective golden rules (SINGLE SOURCE OF TRUTH):**

1. **Each faction always has ≥ 1 short-term objective and ≥ 1 long-term objective.** A short-term objective has a natural deadline (hours to weeks). A long-term objective is structural (months to years).
2. **Objectives are INDEPENDENT of PCs.** They exist and evolve even if the PCs never intervene. A faction that "observes a newcomer" is a faction without its own objective — this is forbidden.
3. **Automatic renewal:** When a short-term objective is achieved, thwarted, or superseded → immediately replace it with a new objective coherent with the long-term goal and recent events.
4. **PCs can influence but not cancel.** An action thwarted by the PCs transforms (change of method, succession, split) — it does not disappear. The world continues.

**Inter-faction relations:** Factions interact with each other — alliances, rivalries, conflicts, dependencies. These relations evolve independently of PCs, even if PCs can influence them:
- An alliance can break if a faction fails to keep its promises
- Hostility can turn into forced truce faced with a common enemy
- Inter-faction relations are stored in `global_state.factions > relations_inter_factions` (key-value object)
- When a faction attacks another, create an action in the attacking faction's clock
- PCs can discover these relations through investigation, hearsay, intercepted letters, or observation
- A faction may have diplomatic intentions (send an emissary, propose an alliance, declare war) — record them in its `notes_mj`

## 2. Proactive clock (`faction_actions_horloge`)

Each faction may have one or more `actions_en_cours` in `global_state.faction_actions_horloge` — concrete actions with:
- `declencheur` — what triggered the action
- `echeance` — deadline in game time
- `consequence` — what happens if the deadline passes without intervention
- `facteurs_modificateurs` — concrete levers that PCs can activate
- `visible_par_pj` — whether PCs can detect this action

Clock rules:
- Each faction always has ≥ 1 short-term action (deadline ≤ 7 days) and ≥ 1 long-term action (deadline ≥ 14 days)
- A deadline is a hard stop, not a suggestion. It only moves if the PCs activate a `facteur_modificateurs`
- At each narrative downtime (night, travel, transition, interval between sessions): advance the clock, check deadlines
- See `references/faction-tracking.md` for the complete template

**Unassigned leads:** If a clue cannot yet be linked to a specific faction, put it in `global_state.pistes_non_assignees`. When a link is confirmed in play, move it to the relevant faction.

**When to update:**
- ✅ After each session: check if each faction had an interaction, movement, or clue
- ✅ When an NPC mentions a faction
- ✅ When physical traces are discovered
- ✅ When a faction's attitude changes
- ✅ When game time advances at least half a day: check the clock
- ✅ When a short-term objective is fulfilled/superseded: renew it immediately

## 3. Pitfalls

**⚠️ Pitfall — PC-centered objectives:** Never define a short-term objective as "Observe the character's arrival" or "Monitor PC movements". This is a faction without its own life. A good objective:
- ❌ "Watch new arrivals" → PC-centered
- ✅ "Stockpile provisions before winter" → the faction is cold, that is its problem
- ✅ "Extend territory southward to secure a hunting zone" → the faction has needs

**⚠️ Pitfall — Not advancing the clock:** Entries in `faction_actions_horloge` do not resolve on their own. At each narrative downtime (night, transition, travel, interval between sessions), **manually check each entry** and advance approaching deadlines. A faction whose action reaches deadline without consequence being played = silent inconsistency that players will not forgive.

**⚠️ Pitfall — Static factions by oversight:** Factions defined in `universe.factions` are LORE (initial description). `global_state.factions` is DYNAMIC TRACKING (what happens in play). Do not confuse the two. If a faction has no entry in `global_state.factions`, it means it has not yet interacted with the PCs — this is normal, and it must be created at first interaction.

**⚠️ Pitfall — CROSS-CHECK CLOCK vs SESSION (missed narrative verification):**
**The problem:** The GM reads the clock data, confirms the file is well-formed (valid JSON, keys present, coherent deadlines), and concludes "all is well". But they do NOT verify whether the **promised consequences** of the clock actions have **actually been played in the session**.

**Generic example:**
```json
// In faction_actions_horloge → [a faction]
"action": "Deliberation ongoing",
"facteurs_modificateurs": [
  "If [the PC] reaches [a key location] → immediate, major reaction"
]
```
→ The PC reached the key location during the session. The consequence was NOT played.
→ The GM checked the file several times without noticing.

**Root cause:** The GM performs a **structural verification** (the file is coherent) but not a **narrative verification** (was what the file promises actually played in session?). The two are independent.

**Rules:**
1. ✅ Structural verification is not enough. After reading the data, **do the narrative cross-check**: for each action whose trigger has occurred, was the consequence played?
2. ✅ When a `facteur_modificateur` says "immediate, major reaction" → play it IN THE SAME SESSION, not later.
3. ❌ Assume "the file is up to date" = "the narrative followed". These two statements refer to different things.
4. ✅ See the header checklist (§7) → `□ CROSS-CHECK CLOCK vs SESSION`

**Error-prevention test:** Before saying "all is consistent", ask yourself: *"Did an event scheduled in my notes occur in play without me playing it?"* If yes → correct before proceeding.

→ See `references/cross-check-horloge-vs-session.md` for the complete example, quick checklist, and detailed pitfalls.

## 4. PC objectives — Difficulty, danger, and obstacles

**Principle:** Players define their own objectives. The GM evaluates difficulty, danger, and required notoriety — then places obstacles in their path.

**Three independent axes** to evaluate for each obstacle:

| Axis | Question | Scale |
|-----|----------|-------|
| 🎯 **Difficulty** | How many obstacles? | Tier 0 (daily) → 5 (legendary) |
| 💀 **Danger** | Physical risk? | 🟢 Green → 🟡 Yellow → 🟠 Orange → 🔴 Red |
| 🌐 **Notoriety** | Scope of consequences? | 🔘 Unknown → 🔵 Known → 🟣 Important → ⚪ Legendary |

**Role distribution:**
- **Player**: defines what their character wants, changes mind, achieves objectives through their own means
- **GM**: determines difficulty tier (secretly), creates proportioned obstacles, modulates by danger and notoriety

**Progression:**
1. The player expresses an objective
2. The GM evaluates tier + danger + notoriety threshold
3. The GM identifies obstacles in the world (factions, season, PCs, secrets)
4. The GM creates clock entries, encounters, dilemmas
5. Obstacles reveal themselves progressively through PC actions

See complete grids (tiers, danger, notoriety, combinations, examples, pitfalls) in `references/pj-objectifs-obstacles.md`.
