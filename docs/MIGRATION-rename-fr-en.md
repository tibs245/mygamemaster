# Migration — French → English structural identifiers

This change renames the remaining French **structural identifiers** (on-disk
filenames, the campaign data directory, JSON keys, schema files, Ansible
variables) to English. The persona name **MJ Tonnerre** and the skill module
directories (`mj-tonnerre*`) are intentionally unchanged.

It changes **on-disk filenames** and the **container data path**, so existing
local deployments must rename their data before redeploying. The runtime reads
the new names only — old names are NOT read as a fallback.

## What changed

### Files & directories (per campaign)

| Old                       | New                       |
| ------------------------- | ------------------------- |
| `campagnes/` (data dir)   | `campaigns/`              |
| `monde.json`              | `world.json`              |
| `pnj.json`                | `npcs.json`               |
| `acteurs.json`            | `actors.json`             |
| `evenements.json`         | `events.json`             |
| `personnages/` (dir)      | `characters/`             |

Container data path: `/opt/data/mj-tonnerre/campagnes` → `/opt/data/mj-tonnerre/campaigns`.

### JSON keys

`systeme→system`, `univers→universe`, `regles→rules`, `etat_global→global_state`,
`lieux→locations`, `deplacements→movements`, `nom→name`, `nom_joueur→player_name`,
`nom_perso→character_name`, `classe→class_`, `niveau→level`, `historique→history`,
`equipement→equipment`, `inventaire→inventory`, `competences→skills`,
`sorts→spells`, `notes_perso→personal_notes`, `objectifs→goals`, `sante→health`,
`pv_max→hp_max`, `pv_actuels→hp_current`, `blessures→wounds`, `etats→conditions`,
`niveau_suivant→next_level`, `temps→time`, `ton→tone`, `mj→gm`,
`verbosite→verbosity`, `faits_etablis→established_facts`.

### Schemas (`modules/gaming/mj-tonnerre/scripts/schemas/`)

`monde→world`, `pnj→npcs`, `acteur→actor`, `personnage→character`,
`evenements→events`, `evenement_programme→scheduled_event`, `trajectoire→trajectory`
(`.schema.json`).

### Ansible

- Host group `campagnes` → `campaigns`.
- Hostvars `campagne_slug→campaign_slug`, `campagne_data_dir→campaign_data_dir`,
  `campagne_titre→campaign_title`; role vars `campagne_src*→campaign_src*`.
- `container_data_root` default → `/opt/data/mj-tonnerre/campaigns`.
- Handler `restart_campagne` → `restart_campaign`.
- Template `hermes-campagne.container.j2` → `hermes-campaign.container.j2`.
- Feature env/var `MJ_FEATURE_VERBOSITE`/`mj_feature_verbosite` →
  `MJ_FEATURE_VERBOSITY`/`mj_feature_verbosity`.
- The CLI override `-e campagne=<slug>` is still accepted as a **legacy alias**
  for `-e game=<slug>` (unchanged).

## Migrating an existing local deployment

Each campaign lives under `~/.hermes/mj-tonnerre/campagnes/<slug>/` (or the
container `/opt/data/mj-tonnerre/campagnes/<slug>/`). Rename the directory and
its files, then redeploy:

```bash
cd ~/.hermes/mj-tonnerre
git mv campagnes campaigns                 # or: mv campagnes campaigns

cd campaigns/<slug>
git mv monde.json       world.json         # or plain mv if not a git repo
git mv pnj.json         npcs.json
git mv acteurs.json     actors.json        # if present
git mv evenements.json  events.json        # if present
git mv personnages      characters         # if present
# scheduled events file, if present:
git mv evenements_programmes.json scheduled_events.json
```

The JSON **keys** inside those files must also be renamed (see the tables
above). For a one-shot conversion, apply the key map with your editor or a small
script, then validate:

```bash
python3 -m json.tool world.json >/dev/null && echo OK
```

After renaming, redeploy as usual. On the server the container data path moves
to `/opt/data/mj-tonnerre/campaigns`; redeploy re-seeds from the renamed
repository data, and the rendered `config.yaml` `terminal.cwd` points at the new
`campaigns/<slug>` path.

## Notes / still-French identifiers (out of scope here)

The following French identifiers are **intentionally not** renamed in this pass
(deep cascade / not in the rename glossary) and remain French:

- Wrapper & per-record data keys: `acteurs`/`acteur`, `evenements`/`evenement`,
  `pnj`/`pnjs`, `trajectoire`, plus world-state keys not in the glossary
  (`modules`, `factions`, `chronologie`, `quete_active`, `regime`, `suivi`,
  `jour`, `heure`, `voyage`, `meteo`, `politique`, `artefacts`, `secrets_mj`,
  `diagnostic`, `cloture_auto`).
- Engine feature axes: `tracabilite`, `temporalite`, `pnj_faction_vivants`
  (and their `MJ_FEATURE_*` env vars), and the `MJ_JUDGE_*` keys
  (`modele`, `actif`).
- Internal Python helper/variable names (e.g. `charger_json`, `load_pnj`,
  `iter_*` kept where touched, `campagne_*` locals in `build_brief.py`,
  `trajectoire_de`, `valider_trajectoire`).
- French prose in comments / `_description` / `_note` strings.

These can be addressed in a follow-up; none affects the renames above, which are
internally consistent (producers and consumers agree) and test-guarded.
