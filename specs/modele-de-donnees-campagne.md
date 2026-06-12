# Spec — Campaign Data Model

A campaign lives in `data/mj-tonnerre/campagnes/<slug>/`. During deployment, this folder is copied
(seeded) into the `hermes-<slug>-data` volume, then mounted read/write in the container.
The skeleton of a new campaign is `campagnes/_template/`.

## Campaign Directory Structure

```
<slug>/
├── monde.json            # world state + rules + active modules (campaign core)
├── pnj.json              # NPC roster
├── evenements.json       # event timeline ({ meta, evenements[] })
├── personnages/          # 1 JSON file per PC, named <discord_id>.json
│   └── 100000000000000001.json
├── sessions/             # 1 file per game session: NNN.json (001, 002, …)
├── images/               # generated illustrations (portraits, locations, scenes)
├── outils/               # tools/data specific to the campaign
├── collecte.csv          # improvement log / diagnostic (verbosity)
├── MJ-INTENTION-LOG.md    # GM intent notes (internal)
└── analyse-bug-rapport.md # bug reports (optional)
```

## `monde.json` — Root Keys

| Key | Content |
|---|---|
| `meta` | campaign identity: `nom`, `mj`, `joueurs[]` (`pseudo`, `discord_id`, `personnage`), `univers`, `ton`, `inspirations`, `style_visuel`, `temps`, `canal_discord`, `cloture_auto`, `verbosite`, `diagnostic` |
| `systeme` | mechanics: `resolution`, `combat`, `competences`, `sante`, `niveaux_difficulte`, `nat1`/`nat20`, `crunch`, `construction_royaume` |
| `regles` | house rules for the campaign |
| `modules` | thematics modules that can be toggled: `factions`, `politique`, `voyage`, `meteo`, `artefacts`, `proactivite_pnj`, `worldbuilding_lieux`, `construction_royaume` (+ `_schema`) |
| `univers` | lore, geography, locations |
| `etat_global` | current world state (narrative clock, ongoing situations) |
| `images_auto` | image generation config |

> **Thematic modules** are loaded conditionally by the `mj-tonnerre` skill based on
> `modules.<x>.actif`. References for these modules are in
> `modules/gaming/mj-tonnerre/references/modules/`.

## `pnj.json` — Element (array)

Keys per NPC: `nom`, `titre`, `description`, `attitude`, `relation_niveau`, `localisation_actuelle`,
`stats`, `modificateurs`, `competences_observees`, `inventaire`, `faits_etablis`,
`hypotheses_mj` (internal GM), `limites`, `premiere_rencontre`, `derniere_interaction`,
`illustration`.

## `personnages/<discord_id>.json` — A PC

Keys: `meta`, `stats`, `modificateurs`, `competences`, `sante`, `equipement`, `inventaire`,
`progression`, `historique`, `connaissances_privees`, `notes_perso`.

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

`monde.json` and `personnages/*.json` contain **Discord identifiers** (`discord_id`,
`canal_discord`) — these are public identifiers, **not credentials**. No tokens or API keys
should ever be stored there (secrets pass through the vault + environment variables).
