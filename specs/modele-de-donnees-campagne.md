# Spec — Campaign Data Model

A campaign lives in `data/mj-tonnerre/campaigns/<slug>/`. During deployment, this folder is copied
(seeded) into the `hermes-<slug>-data` volume, then mounted read/write in the container.
The skeleton of a new campaign is `campaigns/_template/`.

## Campaign Directory Structure

```
<slug>/
├── world.json            # world state + rules + active modules (campaign core)
├── npcs.json              # NPC roster
├── events.json       # event timeline ({ meta, evenements[] })
├── characters/          # 1 JSON file per PC, named <discord_id>.json
│   └── 100000000000000001.json
├── sessions/             # 1 file per game session: NNN.json (001, 002, …)
├── images/               # generated illustrations (portraits, locations, scenes)
├── outils/               # tools/data specific to the campaign
├── collecte.csv          # improvement log / diagnostic (verbosity)
├── MJ-INTENTION-LOG.md    # GM intent notes (internal)
└── analyse-bug-rapport.md # bug reports (optional)
```

## `world.json` — Root Keys

| Key | Content |
|---|---|
| `meta` | campaign identity: `nom`, `mj`, `joueurs[]` (`pseudo`, `discord_id`, `personnage`), `universe`, `ton`, `inspirations`, `style_visuel`, `temps`, `canal_discord`, `cloture_auto`, `verbosity`, `diagnostic` |
| `system` | mechanics: `resolution`, `combat`, `skills`, `health`, `niveaux_difficulte`, `nat1`/`nat20`, `crunch`, `construction_royaume` |
| `rules` | house rules for the campaign |
| `modules` | thematics modules that can be toggled: `factions`, `politique`, `voyage`, `meteo`, `artefacts`, `proactivite_pnj`, `worldbuilding_lieux`, `construction_royaume` (+ `_schema`) |
| `universe` | lore, geography, locations |
| `global_state` | current world state (narrative clock, ongoing situations) |
| `images_auto` | image generation config |

> **Thematic modules** are loaded conditionally by the `mj-tonnerre` skill based on
> `modules.<x>.actif`. References for these modules are in
> `modules/gaming/mj-tonnerre/references/modules/`.

## `npcs.json` — Element (array)

Keys per NPC: `nom`, `titre`, `description`, `attitude`, `relation_niveau`, `localisation_actuelle`,
`stats`, `modificateurs`, `competences_observees`, `inventory`, `established_facts`,
`hypotheses_mj` (internal GM), `limites`, `premiere_rencontre`, `derniere_interaction`,
`illustration`.

## `characters/<discord_id>.json` — A PC

Keys: `meta`, `stats`, `modificateurs`, `skills`, `health`, `equipment`, `inventory`,
`progression`, `historique`, `connaissances_privees`, `personal_notes`.

## `sessions/NNN.json` — A Game Session

Keys: `session`, `titre`, `date`, `canal`, `heure_debut`, `heure_fin`, `participants`,
`lieux_visites`, `pnj_rencontres`, `actions`, `resume`, `etat_fin`, `teaser`.

Numbering is sequential, zero-padded to 3 digits. Session wrap-up is managed by
the `close_session.py` script in the `mj-tonnerre` skill.

## `base_items.yaml` — Shared Items (at `data/mj-tonnerre/` level)

Item catalog **shared across all campaigns**: categories (`armes`, …) → item keys
→ `{ nom, description, valeur_or, poids, effet, rarete }`. Mounted/accessible by all containers.

## Validation

The skill provides `validate_schema.py` / `validate_json.py` (under
`modules/gaming/mj-tonnerre/scripts/`) and schemas under `scripts/schemas/`. The `smoke-test.yml`
can invoke validation to guarantee data integrity after seed/restore.

## Privacy Note

`world.json` and `characters/*.json` contain **Discord identifiers** (`discord_id`,
`canal_discord`) — these are public identifiers, **not credentials**. No tokens or API keys
should ever be stored there (secrets pass through the vault + environment variables).
