# Module — Kingdom / Domain Construction

> **Conditional loading.** This module applies only if the campaign declares `world.json > modules.construction_royaume.active === true`. Relevant for campaigns where PCs build and govern (camp, outpost, village, kingdom).
>
> **The concrete campaign parameters are IN THE GAME** : they live in `world.json > systeme.construction_royaume` (type, principle, phases) and `world.json > regles.construction` (resources, first steps, domain state in `global_state.royaume`). This module describes only the generic framework. This is the **reference for proper separation** already praised by the audit — do not copy values into it.

## Principle

Domain construction transforms the PC from an adventurer into a builder: their decisions (alliances, constructions, laws) make a location, community, then territory evolve. Depending on the `type` declared by the campaign, this tracking can be:
- **Narrative and diplomatic** — no resource table; each choice has visible consequences
- **Numerical / management** — resources, population, treasure tracked numerically

## Generic Phases (to be overridden by `systeme.construction_royaume.phases`)

1. **Establish a camp** — first shelter, first fire, secure a point
2. **Build a permanent outpost** — durable structures, first settlers
3. **Attract a population** — promise of a better life, management of mouths to feed
4. **Define laws and alliances** — governance, inter-faction diplomacy (module `politique` if active)
5. **Manage crises and threats** — harsh seasons, raids, intrigues (module `factions` if active)

## Domain State Tracking

The living state of the domain is maintained in `world.json > global_state` (e.g. `royaume` / `phase_construction`) with, depending on the type:
- `nom`, `taille`, `population`, `tresor`/resources, `influence`
- Progress of ongoing constructions (narrative or numerical sliders)

## Consistency Rules

1. **Every decision has a cost and a visible consequence** — nothing is free; time, resources, and trust are invested.
2. **Time makes growth and weight** — more time = more settlers = more labor, but also more mouths to feed and more outside attention.
3. **Links with other modules** — the domain's sovereignty (module `politique`) and the reactions of neighboring factions (module `factions`) must be kept up to date with each evolution.
4. **Persistence** — any domain evolution is written to `world.json` immediately, never kept in agent memory (see data governance in section §4).
