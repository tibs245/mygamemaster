---
name: mygamemaster-outils
description: Dice rolls (classic via Python secrets and quantum via qrandom.io) and action resolution for MJ Tonnerre. Parses !jet/!jetq formulas and orchestrates !action.
category: gaming
triggers:
  - "!jet"
  - "!jetq"
  - "!action"
  - "dice"
  - "roll the dice"
  - "dice roll"
  - "quantum roll"
  - "action resolution"
---

# 🎲 MJ Tonnerre — Tools (Dice & Actions)

## Overview

This skill handles three commands:

| Command | Examples | Effect |
|---------|----------|--------|
| `!jet <formula>` | `!jet d20`, `!jet 2d6+3`, `!jet d20 advantage` | Classic roll (`roll.py`, real dice via `secrets`) |
| `!jetq <formula>` | `!jetq d20`, `!jetq 3d8-1` | Quantum roll (`roll.py --quantique`, qrandom.io + fallback secrets) |
| `!action <description>` | `!action I force the door` | Narrative resolution + automatic roll if relevant |

---

## Step 0 — Campaign Context

Before any roll, load the active campaign file:

**Path:** `~/.hermes/mygamemaster/campaigns/<campaign-name>/world.json`

**Useful fields for rolls:**
- `system` — rule system (top-level: `system.name`, `system.stats`, `system.resolution`, `system.nat20`, `system.nat1`)
- `rules` — campaign rules (top-level: `rules.time`, `rules.weather`; house rules live under `rules.*`)
- `system.crunch` — 1 to 5 (influences roll frequency and detail level)

**To identify the active campaign:** MJ Tonnerre (umbrella skill) maintains the active campaign for the Discord channel. Consult memory or session context.

---

## Step 1 — Formula Parsing

The **dice formula** (`1d20+3`, `d20`, `2d6`, `1d100`…) is passed as-is to `roll.py` (the "1" before `d` is optional; the script validates syntax). On the skill side, only identify any **option** at the end of the command:

### Grammar

```
<command> := <formula> [<option>]
<formula> := [<quantity>]d<faces>[+-<modifier>]   → passed to roll.py
<option>  := "advantage" | "disadvantage" | "secret"    → handled on skill side
```

- **advantage / disadvantage** (on 1 die): call `roll.py` twice, keep the max (advantage) / min (disadvantage).
- **secret**: GM roll, output wrapped in `|| … ||` (see Step 5).

### Parsed Examples

| Input | Num Dice | Faces | Modifier | Option |
|-------|----------|-------|----------|--------|
| `d20` | 1 | 20 | +0 | — |
| `2d6+3` | 2 | 6 | +3 | — |
| `3d8-1` | 3 | 8 | -1 | — |
| `d100` | 1 | 100 | +0 | — |
| `d20 advantage` | 1 | 20 | +0 | advantage |
| `d20 disadvantage` | 1 | 20 | +0 | disadvantage |
| `d20 secret` | 1 | 20 | +0 | secret |
| `2d6+3 advantage` | 2 | 6 | +3 | advantage |

---

## Step 2 — Classic Roll (`!jet`)

**The roll ALWAYS goes through the script** (real dice via `secrets`, natural die rule + logging managed by script). Do not re-implement anything manually.

```
python3 /opt/modules/gaming/mygamemaster/scripts/roll.py "<formula>" --dc <DC> --stat <Stat> --json
```

- `--dc` and `--stat` are optional (omit `--dc` if there is no threshold).
- `--json` output → fields `des`, `total`, `nat` (`FUMBLE`/`CRITICAL`/null), `resultat`, `ecart`, `rng`.
- Advantage/disadvantage and the `secret` option are handled on the skill side (see Step 1 and output format): for advantage/disadvantage, call the script twice and keep the max/min.

### Natural Results — ABSOLUTE RULE

> Law: `SOUL.md` (the GM's inviolable rule). Do not deviate.

Regardless of bonus or DC, these two results **override everything**:

| Raw Die | Rule | Consequence |
|---------|------|-------------|
| **1** (natural) | Always negative — even if total exceeds DC | 💀 **FUMBLE**. Something goes wrong on top of it. |
| **20** (natural) | Always positive — even if total is below DC | ✨ **CRITICAL** or ✅ **EXCEPTIONAL SUCCESS**. The best possible version of the action. |

⚠️ **Important:** A natural 1 does not negate a success that became impossible to fail (e.g., picking a barn lock with +15 when DC is 5 → roll=1 → the pick breaks, you lose time, but the lock finally yields — the narrative adapts). It is always negative, but proportioned to context.

### Critical / Success / Failure (non-natural)

On a **d20** (standard D&D-like):
- 🎯 **Critical**: raw value = 20 (die faces)
- ✅ **Success**: total ≥ threshold (default 10, or defined by `system.resolution` / `rules`)
- ❌ **Failure**: total < threshold
- 💀 **Fumble**: raw value = 1

For other dice (2d6, 3d8, d100, etc.): no automatic critical unless `rules` specifies it. Display just the total.

---

## Step 3 — Quantum Roll (`!jetq`)

Identical to `!jet`, **with the `--quantique` flag**:

```
python3 /opt/modules/gaming/mygamemaster/scripts/roll.py "<formula>" --dc <DC> --stat <Stat> --quantique --json
```

### qrandom.io API

- **Endpoint:** `https://qrandom.io/api/random/int?min=1&max={faces}` (one call per die).
- Handled by `roll.py --quantique`: quantum draw with automatic fallback to `secrets` per die if network fails. The actual source is returned in the `rng` field (`quantique` / `quantique(fallback:secrets)`) — if fallback, signal it discreetly to the player: *"(quantum API unavailable — classic roll used)"*.

---

## Step 4 — Action Resolution (`!action`)

### Logic

`!action <description>` combines narrative and mechanics:

1. **Parse the description** — what is the PC attempting?
2. **Determine if a roll is needed** based on context:
   - Trivial action (talk, walk, pick up object) → no roll, direct narrative
   - Risky/uncertain action (pick lock, climb, persuade) → roll required
   - Impossible action → say so, no roll
3. **Choose the formula** based on the system (`system.name` / `system.resolution`):
   - **D20 / D&D-like system**: `d20` + ability modifier
   - **2d6 / PbtA system**: `2d6` + modifier
   - **3d8 / house system**: per `rules`
   - **Free system (crunch 1)**: no roll, just narrative interpretation + possibly a % chance
4. **Determine the modifier** from the character sheet:
   - `characters/<discord_id>.json` — stats, skills, bonuses
5. **⚠️ TIME & INCREASING COST of retries** — single source: umbrella `mygamemaster/SKILL.md → §10` (§10.1 every roll advances time; §10.2 retrying costs more). Apply it, do not copy it.
6. **Launch the roll** via the same function as `!jet`
7. **Interpret the result** and deliver the narrative

### Decision Tree

```
!action "I pick the lock"
  → D20 system, character has +4 in dexterity
  → Roll: d20+4 against DC 15 (set by the GM)
  → Standard output format
```

### Roll-First Default

**When uncertain, roll.** The dice tools exist precisely so that uncertain player actions produce
real, unpredictable outcomes rather than authored ones. An automatic success or failure should only
appear when the narrative *requires* a fixed outcome (a scripted betrayal, a trivial action with no
meaningful failure state). For everything else — a climb, a bluff, a risky search — call for a
roll: it is faster, fairer, and makes the game feel alive.

---

## Step 5 — Output Format

> **Format "Dice Roll" + rule "stat in parentheses": single source = umbrella `mygamemaster/SKILL.md` → `Formatting Conventions` → `### Dice Roll`.** Apply it as-is (inviolable format). Below: only what is SPECIFIC to this skill (dice detail, secret format).

**Dice detail (to insert in `{dice value}` of umbrella format):**
- 1 die: `12`
- Multiple dice: `[3, 5, 2] = 10`
- Advantage/disadvantage: `[7, 14] → 14`

### Secret Format

For `!jet d20 secret` (GM roll, invisible to players):

```
🎲 {GM} rolls d20 (secret):
   ||🎯 15 + 3 = 18 — Success||
```

All content after `🎲` is wrapped in `|| ... ||`.

### Possible Results

| Type | Display | Condition (d20) |
|------|---------|-----------------|
| Critical | `✨ CRITICAL!` | die = 20, OR extended range if `rules.critique_etendu` |
| Success | `✅ SUCCESS (≥ {DC})` | total ≥ threshold, comfortable margin |
| Partial Success | `⚠️ PARTIAL SUCCESS` | total ≥ threshold but margin < 3, OR partial info |
| Success (perception) | `✅ SUCCESS — you notice obvious elements and some details` | Perception/Intuition: gradation by margin |
| Failure | `❌ FAILURE (< {DC})` | total < threshold |
| Fumble | `💀 FUMBLE...` | die = 1, OR extended range if `rules.fumble_etendu` |
| Simple | *(no result line)* | other dice (2d6, etc.) |

**Nuances by roll type:**

- **Knowledge / Analysis**: a critical → full info + hidden detail. Partial success → correct info but with gap or ambiguity.
- **Perception / Intuition**: modulate detail level — "you notice obvious elements" (bare success), "you notice obvious elements and some details" (good margin), "you notice down to the finest details" (critical).
- **Social (Persuasion, Intimidation)**: no automatic narrative critical — the NPC reacts per personality, not die alone.
- **Combat**: critical → damage + narrative effect if `critique_narratif` enabled in world.json.

**DC reading rule:** Always pull DC from scene context (defined by you before the roll). Do not reveal DC to player unless asked. Display threshold in parentheses in result.

```json
// Example in session actions
{
  "details": {
    "formule": "d20+7",
    "dé": 3,
    "total": 10,
    "résultat": "⚠️ PARTIAL SUCCESS"
  },
  // Knowledge of the Void Raiders — partial info
}

{
  "details": {
    "formule": "d20+6",
    "dé": 13,
    "total": 19,
    "résultat": "✅ SUCCESS — you notice obvious elements and some details"
  },
  // Perception of dangers — good margin
}
```

---

## Step 6 — House Rules

Before applying critical/fumble/thresholds, **always check** the system and house rules of the campaign in `world.json`: `system` (`system.resolution`, `system.nat20`, `system.nat1`) and `rules` (house rules under `rules.*`). Possible keys depending on campaign:

- `seuil_defaut` — default DC (e.g.: 10, 12, 15)
- `critique_etendu` — extended critical range (e.g.: 18-20 instead of 20)
- `fumble_etendu` — extended fumble range (e.g.: 1-3 instead of 1)
- `critique_narratif` — true → bonus narrative effect on critical (not just doubled damage)
- `relance_destin` — true → players can spend a fate point to reroll
- `des_explosifs` — true → if die hits max, reroll and add

---

## Summary: Executing a `!jet`

```
1. Parse formula → (qty, faces, modifier, option)   [see Step 1]
2. If !jet  → roll.py "<formula>" --dc <DC> --stat <Stat> --json
3. If !jetq → same + --quantique
   (advantage/disadvantage: 2 calls, keep max/min; script does the rest)
4. Read JSON → nat (FUMBLE/CRITICAL), resultat, ecart, rng, des, total
5. Format output → emoji, alignment, secret option in ||spoiler||
6. Log action in sessions/NNN.json (field "actions")
```

**No overkill.** The script does the draw, natural die rule, and logging. The skill just calls `roll.py`, reads its JSON, and formats. No dice re-implementation.

---

## References

- `references/dice-system-player-guide.md` — explanation of dice system for players (cite when a player asks how it works)
