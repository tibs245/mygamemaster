# d20 System — Generic Framework

> **Single source of values: `world.json > system`.** This sheet describes the **generic framework** of a d20 system (resolution, difficulty tiers, skills, natural die). The **stats, skills, HP and campaign-specific rules** live in `world.json > system` (and each character's numerical skills in `characters/<id>.json`). Never hardcode the values of a specific campaign here — a starter template for creating a campaign lives in `/opt/modules/gaming/mygamemaster-initiation/references/systemes/`.

## Generic Resolution

**d20 + stat modifier + skill bonus (if applicable) ≥ DC.**

The **number and names of stats** depend on the system declared by the campaign (`world.json > system.stats`) — for example a restricted set of custom stats, or a classic set of six attributes. Always read `system.stats` to know which stats to use; never assume them.

## Difficulty Tiers (DC)

Generic scale (exact labels can be overridden by `system.niveaux_difficulte`) :

| DC | Level |
|----|--------|
| 10 | Easy — obvious action, little pressure |
| 12 | Standard — risky action, normal conditions |
| 15 | Difficult — complex action, unfavorable conditions |
| 18 | Very Difficult — exceptional action |
| 20+ | Heroic / Legendary — nearly impossible for a mortal |

## Skills

- **Proficient** : fixed bonus to d20 (added to stat modifier) — the exact value is defined by `world.json > system.skills`
- **Non-proficient** : just the stat modifier
- A character starts with a few specialties (the number is defined by the campaign system)
- The actual skills of a PC and their total bonus are in their `characters/<id>.json` sheet, not here

## Natural Die

See the **natural die rule in `SOUL.md`** (rule of the game) : a natural 1 is always negative, a natural 20 always positive, regardless of the total. The **exact formulation** ("worst/best possible for the situation", critical, etc.) is specified per campaign in `world.json > system.nat1` / `system.nat20`.

## Flexibility Rule (Alternative Stat)

If a player describes a creative approach using a different stat than expected, allow it when it makes sense :
- ✅ "I want to force the door with my shoulder" → physical strength stat, even if the expected skill was different
- ✅ "I want to analyze the tracks based on my knowledge of creatures" → knowledge stat instead of perception stat

## Health and Combat

HP and combat style are defined per campaign in `world.json > system.health` and `system.combat`. The generic framework: health is measured in Hit Points; combat leans toward narration and choice rather than calculations, unless the campaign declares a higher crunch level (`system.crunch`).
