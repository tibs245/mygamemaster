# Thematics modules activable per campaign

This folder groups the **thematic blocks** of the MJ Tonnerre system, extracted from the umbrella skill to be **loaded conditionally** based on what each campaign declares.

## Why `references/modules/*.md` instead of sub-skills `mygamemaster-<module>`?

The existing sub-skills (`mygamemaster-onboarding`, `-character`, `-inventory`, `-tools`, `-images`, `-session`) are **triggered by command/keyword** (`!sheet`, `!roll`, `!wrap-up`…). They are functional and cross-cutting: any player of any campaign has access to them as soon as they type the command.

Thematic modules (travel, factions, politics…) are **not triggered by a command**: they activate based on the **campaign's declaration**. The only precedent for per-campaign configuration in the system is `world.json > meta.temps.regime` (UT), which the umbrella skill **reads conditionally**. We reproduce exactly this pattern: the umbrella skill reads `world.json > modules.<x>.actif` and loads the module's reference file only if the module is active. This keeps the tree structure consistent (the `references/` are already loaded by reference from the umbrella skill) without diverting the sub-skill trigger mechanism.

## Schema of the `modules` block (in `world.json`)

To be added at the root of each `world.json` (at the same level as `meta`, `systeme`, `regles`, `global_state`, `universe`):

```json
"modules": {
  "voyage":              { "actif": true,  "params": {} },
  "factions":            { "actif": true,  "params": {} },
  "proactivite_pnj":     { "actif": true,  "params": {} },
  "artefacts":           { "actif": true,  "params": {} },
  "politique":           { "actif": false, "params": {} },
  "meteo":               { "actif": true,  "params": {} },
  "worldbuilding_lieux": { "actif": true,  "params": {} },
  "construction_royaume":{ "actif": false, "params": {} }
}
```

| Field | Type | Role |
|-------|------|------|
| `<module>.actif` | boolean | The umbrella skill loads/applies the module **only if `true`**. Reproduces the pattern of `meta.temps.regime`. |
| `<module>.params` | object (optional) | Value **overrides per campaign without modifying the skill** (e.g., `voyage.params.terrains`, `voyage.params.rencontres`). Empty `{}` = module defaults. |

A module **absent** from the block or with `actif: false` is considered **inactive** — its rules do not apply and the module file is not loaded.

## Module catalogue

| Key `modules.<x>` | File | Covers | Associated GAME source (values) |
|---|---|---|---|
| `voyage` | `voyage.md` | Pace, fatigue, encounters, orientation | `regles.temps.deplacements`, `voyage.params` |
| `factions` | `factions.md` | Faction tracking, proactive clock, PC objectives | `global_state.factions`, `faction_actions_horloge` |
| `proactivite_pnj` | `proactivite-pnj.md` | 5 pillars of NPC proactivity | `npcs.json > motivations_personnelles` |
| `artefacts` | `artefacts.md` | Tracking important objects | `global_state.artefacts_connus` |
| `politique` | `politique.md` | World layers, sovereignty, political entities | `universe.entites_politiques`, `souverainete` |
| `meteo` | `meteo.md` | Weather and biodiversity | `regles.meteo`, `universe.regions[].biodiversite` |
| `worldbuilding_lieux` | `worldbuilding-locations.md` | Framework 10 points of place creation | `universe.regions[].lieux` |
| `construction_royaume` | `construction-royaume.md` | Domain/kingdom construction | `systeme.construction_royaume`, `regles.construction`, `global_state.royaume` |

## LOSSLESS migration

Each module was **extracted** from the umbrella skill (skill `mygamemaster`) without loss of rules — only relocated and scrubbed of campaign proper nouns (replaced with neutral placeholders `[NPC]`, `[the PC]`, `[a place]`). Details of the migrations are recorded in `audit/01b-migration-modularite.md`.
