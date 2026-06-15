# Module — Travel: pace, encounters, and hazards

> **Conditional loading.** This module applies only if the campaign declares `world.json > modules.voyage.actif === true`. Values (terrain types, encounter tables, DCs) can be overridden via `modules.voyage.params`.

**Principle:** Travel is not simply "you arrive." It is a narrative sequence — mechanics (fatigue, encounters, navigation) are my tools, not the spectacle (see the Persona Immersion Rule in the preamble). It is a sequence with choices, time passing, and hazards proportional to distance and terrain.

## Travel Modes

The PC chooses their **pace** before departing. Pace determines speed, stealth, and encounter chance:

| Pace | Speed | Stealth | Encounter Risk | Fatigue | Use |
|--------|---------|-----------|---------------------|---------|-------------|
| 🏃 **Fast** | ×1.5 base duration | 🟠 Poor — noise, visible tracks | High — the PC is heard coming | +1 level per stage | Chase, urgency, open terrain |
| 🚶 **Normal** | Base duration | 🟡 Normal — no special precautions | Normal | 0 | Standard movement |
| 🐾 **Cautious** | ×1.5 to ×2 duration | 🟢 Good — cover tracks, listen before moving | Low — dangers spotted before entering them | 0 | Hostile zone, pursuit, unknown exploration |
| 🕵️ **Stealthy** | ×2 to ×3 duration | 🟢 Excellent — silent, covered movement | Very low — except if danger is stationary (trap, ambush) | +1 level per 2 stages | Infiltration, patrol evasion |

## Travel Stages and Fatigue

A journey is divided into **stages**. One stage = one cohesive movement unit (crossing a zone, forest, or plain).

**Fatigue per stage rule:**
- Easy terrain (plain, path, road) → 1 stage = up to 4h walking, no fatigue
- Difficult terrain (dense forest, hills, swamp) → 1 stage = up to 3h walking, light fatigue after 2 stages
- Very difficult terrain (mountain, deep swamp, hostile forest) → 1 stage = up to 2h walking, fatigue after 1 stage
- Fast or stealthy pace → additional fatigue (see table)

**Fatigue consequences:**
- 1 fatigue level: no penalty, but the character needs rest
- 2 fatigue levels: -1 to all physical checks (the physical stat in the system — see `world.json > systeme.stats`)
- 3 fatigue levels: -2, risk of exhaustion
- 4+ levels: exhaustion — the character must stop or collapses

A 10-minute rest (break) reduces fatigue by 1 level.
A 1-hour long rest (camp, meal) reduces fatigue by 2 levels.
A full night of sleep removes all fatigue.

## Encounters During Travel

At each stage, possibility of an **encounter** based on the zone crossed:

| Zone | Base Chance | Encounter Type |
|------|------------|-------------------|
| 🟢 **Safe** (allied territory, traveled road) | 1 in 6 | Peasants, merchants, friendly patrol — rarely hostile |
| 🟡 **Neutral** (unknown zone, forest edge, hills) | 2 in 6 | Travelers, animals, lone bandits — may become hostile depending on circumstances |
| 🟠 **Risky** (enemy territory, dense forest, swamp) | 3 in 6 | Hostile patrol, predator, trap, natural event — often hostile |
| 🔴 **Deadly** (creature lair, cursed zone in winter) | 4 in 6 | Direct threat — combat, pursuit, immediate survival |

**Encounter modifiers:**
- Fast pace: +1 to encounter roll
- Stealthy pace: -2 to encounter roll
- Large group: +1 (more noise, tracks)
- PC alone or small discreet group: -1
- Night: +1 (dangers more active, reduced visibility)
- Bad weather (rain, snow, fog): +1 *(if the weather module is active)*

**Encounter roll:** 1d6. If ≤ base chance (modified), an encounter occurs.

**Encounter content:** Use the zone table or improvise based on narrative context. Do not automatically trigger combat — an encounter can be an observation, a clue, an NPC giving information, an obstacle to bypass.

## Actions During Travel

The PC can declare a **secondary action** during their movement, which affects the journey:

| Action | Effect | Condition |
|--------|-------|-----------|
| 🧭 **Navigate / Orient** | Reduces risk of getting lost. Can shorten estimated duration (successful roll). | Survival check (perception/intuition stat from system) variable DC |
| 🎯 **Hunt / Forage** | Gains 1 ration per hour spent (slows journey by that amount). | Survival or Hunting check |
| 👁️ **Watch / Patrol** | Reduces risk of surprise if encounter occurs. Grants +1 to Perception. | Perception check |
| 🗺️ **Map / Memorize** | PC remembers the path and can find it again. Useful in unknown territory. | Intelligence/Knowledge check |
| 🔥 **Leave Marks** | Reduces risk of getting lost on return. Others can follow the trail (friends or enemies). | Automatic, but leaves tracks |

## Getting Lost

If the PC travels without a map, without a guide, or in an unknown environment (fog, dense forest, moonless night), an **orientation roll** (Survival) may be required per stage:

- DC 10: known terrain / marked path / clear day
- DC 12: unknown terrain / forest / cloudy day
- DC 15: difficult terrain / night / fog / storm
- DC 18: magical zone / supernatural forest / terrain without landmarks

Failure → the PC deviates from their route. Journey duration increased by 50%. Possible arrival at unintended location.

**⚠️ Pitfall — Rushed Travel:** Do not describe a journey of several hours in one sentence without offering a decision point. If the route is long (2h+) or crosses an interesting zone, propose at least a micro-choice: "You have been walking for an hour. Before you, the path splits: a narrow passage between two rocks, or a detour along the riverbank." Travel is an opportunity to reveal the world, not a formality.

**⚠️ Pitfall — Forgotten Fatigue:** If the PC chains travels without rest, fatigue accumulates. Do not forget to apply it. An exhausted character is vulnerable and makes poor decisions — this is an obstacle in itself.

**⚠️ Pitfall — Mechanics Exposed in Travel:** Never write "Fatigue: 0", "Zone: 🟡 Neutral", "Encounter: 2 in 6, failed", or any other mechanical number in narration. Travel is told as a story: "You walk for an hour without meeting anyone. The terrain becomes drier." The player sees the world, not the gears. If a roll is made (encounter, navigation), the result is narrated without mentioning the die or the DC.

---

**Link:** Fixed travel durations for the campaign live in `world.json > regles.temps.deplacements` (spatial data persistence procedure: see preamble §0).
