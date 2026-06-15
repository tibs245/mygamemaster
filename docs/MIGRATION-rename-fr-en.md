# Migration — French → English identifiers (complete rename)

This document supersedes PR#12. It records the **complete** rename of the
codebase's structural identifiers — from the original `mj-tonnerre` /
French-key tree to the current `mygamemaster` / English-identifier tree.

It is the union of two refactors:

1. **Namespace + branding** (`refactor/rename-namespace`) — module dirs, data
   root, OCI image / config dir, env-var prefix.
2. **Full FR→EN identifiers** (`refactor/full-fr-en`) — data directory,
   filenames, JSON schema files, and all JSON structural keys (this branch,
   Groups 1–7 below).

The persona proper noun **"MJ Tonnerre"** is intentionally preserved
everywhere (it is a name, not an identifier).

> ⚠️ **Deployed instances need a data migration.** Renaming on-disk
> directories/files and JSON keys is **not** backward-compatible: an existing
> campaign directory created with the old names will not be read correctly by
> the new code. Either run the on-disk migration described at the end of this
> doc, or re-seed the campaign from updated data.

---

## 1. Namespace + branding (from `refactor/rename-namespace`)

| Old | New |
|-----|-----|
| `modules/gaming/mj-tonnerre*` (17 dirs) | `modules/gaming/mygamemaster*` |
| `data/mj-tonnerre/` | `data/mygamemaster/` |
| container/host paths `/opt/data/mj-tonnerre`, `~/.hermes/mj-tonnerre`, `~/.config/…/mj-tonnerre` | `…/mygamemaster` |
| OCI image + config dir `hermes-mj` | `mygamemaster` |
| env-var prefix `MJ_*` | `MGM_*` |
| ansible vars `mj_feature_*` / `mj_judge_*` / `mj_tts_*` | `mgm_*` |

Kept as-is: `mj_checkpoint.py` filename; `hermes-<slug>-data` / `-home`
framework volume names.

---

## 2. Full FR→EN identifiers (this branch — Groups 1–7)

### Group 1 — data directory, filenames, schema files, path consumers

| Old | New |
|-----|-----|
| `data/.../campagnes/` (dir) + container `/opt/data/mygamemaster/campagnes` | `campaigns/` |
| `monde.json` | `world.json` |
| `pnj.json` | `npcs.json` |
| `acteurs.json` | `actors.json` |
| `evenements.json` | `events.json` |
| `personnages/` (dir) | `characters/` |
| `monde.schema.json` | `world.schema.json` |
| `pnj.schema.json` | `npcs.schema.json` |
| `acteur.schema.json` | `actor.schema.json` |
| `personnage.schema.json` | `character.schema.json` |
| `evenements.schema.json` | `events.schema.json` |
| `evenement_programme.schema.json` | `scheduled_event.schema.json` |
| `trajectoire.schema.json` | `trajectory.schema.json` |
| `references/modules/voyage.md` | `travel.md` |
| `references/modules/meteo.md` | `weather.md` |

Schema `$id` values and `validate_schema.py` short-name map / help updated to
match. `_lib.classify` kind labels and `post_tool_call` delta kinds renamed
(`monde/pnj/personnage/evenements` → `world/npcs/character/events`).

### Group 2 — ansible campaign vars + host group + handler + template

| Old | New |
|-----|-----|
| `campagne_slug` | `campaign_slug` |
| `campagne_data_dir` | `campaign_data_dir` |
| `campagne_titre` | `campaign_title` |
| `campagne_src` / `campagne_src_local` | `campaign_src` / `campaign_src_local` |
| host group `campagnes` | `campaigns` |
| handler `restart_campagne` | `restart_campaign` |
| `templates/hermes-campagne.container.j2` | `hermes-campaign.container.j2` |
| `MGM_FEATURE_VERBOSITE` / `…TRACABILITE` / `…TEMPORALITE` / `…PNJ_FACTION_VIVANTS` | `…VERBOSITY` / `…TRACEABILITY` / `…TEMPORALITY` / `…LIVING_NPCS_FACTIONS` |
| ansible `mgm_feature_verbosite` / `…tracabilite` / `…temporalite` / `…pnj_faction_vivants` | `…verbosity` / `…traceability` / `…temporality` / `…living_npcs_factions` |

`hermes_inventory.py` `FIELD_TO_VAR` and group name updated.
**Legacy alias kept:** `-e campagne=<slug>` still works (the playbooks'
`game | default(campagne | default('campaigns'))` pattern is preserved).

### Group 3 — `world.json` structural keys

`systeme→system`, `univers→universe`, `regles→rules`, `etat_global→global_state`,
`lieux→locations` (also `geo.json` graph + scene cone), `deplacements→movements`,
`verbosite→verbosity` (key **and** feature axis, CSV column, `_lib.verbosity()`,
env var, ansible var), `temps→time`, `ton→tone`, `mj→gm` (incl. `meta.mj`,
`meta.mj_discord_id→meta.gm_discord_id`), `faits_etablis→established_facts`,
`etat_global.secrets_mj→global_state.gm_secrets`.

### Group 4 — character / npc / actor / event keys

`nom→name`, `nom_joueur→player_name`, `nom_perso→character_name`,
`notes_perso→personal_notes`, `classe→class_`, `niveau→level`,
`niveau_suivant→next_level`, `historique→history`, `equipement→equipment`,
`inventaire→inventory`, `competences→skills`, `sorts→spells`, `sante→health`,
`pv_max→hp_max`, `pv_actuels→hp_current`, `blessures→wounds`, `etats→conditions`,
`objectifs→goals`, `objectif_court_terme→short_term_goals`,
`objectif_long_terme→long_term_goals`.

### Group 5 — deep cascade keys + feature axes

Wrapper keys: `acteurs→actors`, `acteur→actor` (property), `evenements→events`,
`evenement→event` (property), `pnj→npcs`, `trajectoire→trajectory`. Cascade:
`chronologie→timeline`, `suivi→tracking`, `jour→day`, `heure→hour` (+ composites
`jour_courant→current_day`, `heure_courante→current_hour`, `heure_fin→end_hour`,
`heure_debut→start_hour`, `jour_courant_estime→estimated_current_day`),
`voyage→travel`, `meteo→weather` (module keys + `load_campaign.py` registry +
dotted-path requirements), `lieux_visites→visited_locations`,
`pnj_rencontres→npcs_met`, `hypotheses_mj→gm_hypotheses`,
`<char>_inventaire_note→<char>_inventory_note`. Feature axes:
`tracabilite→traceability`, `temporalite→temporality`,
`pnj_faction_vivants→living_npcs_factions` (FEATURES tuples in `_lib.py`,
`feature_toggle.py`, `worldlib.py`; `world.json meta.features`; env + ansible).
Schema `$defs`/`$ref` names updated to match (`actor`, `event`, `trajectory`,
`fichier_actors`, `npcs_sheet`).

### Group 6 — emotions module keys (PR#11)

`joie→joy`, `confiance→trust`, `peur→fear`, `colere→anger`, `tristesse→sadness`
(`surprise` unchanged); in emotion history: `evenement→event`, `raison→reason`.
Covers `emotions.py` (`EMOTIONS`, `DEFAULT_TEMPERAMENT`, `EVENT_RULES`, palette),
`npcs.schema` emotions `patternProperties`, example NPC data, `test_emotions.py`.

### Group 7 — preferences keys (PR#9)

`rythme→pacing`, `ton_aime→tone_likes`, `ton_evite→tone_dislikes`,
`verbosite_combat→combat_verbosity`, `limites_contenu→content_boundaries`,
`aime_etre_trompe→enjoys_deception`. Kept: `spotlight`, `custom`.

---

## 3. Intentionally kept (NOT renamed)

- **`MJ Tonnerre`** — persona proper noun.
- **`mj_checkpoint.py`** — filename (kept per the namespace refactor).
- **Already-English keys** — `meta`, `stats`, `relations`, `secrets`,
  `modules`, `factions`, `regions`, `discord_id`, `race`, `xp`, `progression`,
  `audio`, `voice`, `temperament`, `deltas`, `spotlight`, `custom`.
- **ID-prefix VALUES** — e.g. `"acteur:berthe"`, `"faction:pale-court"`,
  `"lieu:..."`, `"evt:..."`, `"rel:..."`. These are data *values* (identifiers
  inside the world), not structural keys; renaming them would change logic.
- **Enum / unit VALUES** — `"unite": "jour"` / `"ut"`, and the unit-keyed
  `temps_courant` dict `{"ut": …, "jour": …}` (the `"jour"` key is the unit
  value).
- **Discord / CLI command tokens** — the `!verbosite` Discord command and the
  `geo_query.py creer-lieu --nom` CLI flag are user-facing tokens, left as-is.
- **`close_session.py` status dict** — its internal `{"lance":…, "raison":…}`
  fields (a separate structure, not the emotions `raison`).

## 4. Known remaining French identifiers (out of the 7-group scope)

These were **not** enumerated in any group and remain French (a follow-up if
"100% English" is desired). They do not affect the 3 green suites:

- **Internal Python helper/function & local-variable names**, e.g.
  `valider_trajectoire`, `trajectoire_de`, `jour_courant`, `temps_courant`,
  `charger`, `valider`, `valider_campagne`, `sauver_json_atomique`,
  `_sortir_json`, `classer_LOD`, `lancer`, and most `*.py` local variables
  (`nom`, `noms`, `acteurs`, `suivi`, …). These are not data/schema contracts.
- **Deeper simulation/geo/actor/faction JSON keys** not listed in the groups,
  e.g. `aretes`, `ancrage`, `altitude`, `contenus`, `parent`, `vers`,
  `intensite`, `poids`, `delai_ut`, `significativite`, `consequence_effets`,
  `relation_effet`, `but_long_terme`, `situation`, `ressources`, `motif`,
  `chemin`, `localisation`, `principe`, `regime`, `gouvernance`,
  `echeance_jours`, `renouvellement`, `quete_active`, `jalons_temporels`,
  `statut`, `texte`, `seuil_min/max`, `cible`, `connaissances_privees`,
  `motivations_personnelles`, `souverainete`, `biodiversite`,
  `empreinte_source`, `artefacts_connus`, `faction_actions_horloge`,
  `date_creation`, `langue`, `theme`, `inspirations`, `cloture_auto`,
  `delai_inactivite_minutes`. The schemas + code for these are internally
  consistent (producers and consumers all still use the French spelling).
- **Doc prose** in `docs/`, `specs/`, module `references/*.md` — natural-language
  French is preserved; only *path-literals* and unambiguous *key references*
  were updated.

---

## 5. On-disk data migration for deployed instances

For each deployed campaign directory (`<campaign>/`):

```bash
# 1. Directory / file renames
mv campagnes            campaigns          # (data root level)
cd campaigns/<campaign>
mv monde.json           world.json
mv pnj.json             npcs.json
mv acteurs.json         actors.json
mv evenements.json      events.json
mv personnages          characters

# 2. JSON key renames inside each file
#    Apply the Group 3–7 key mappings above to world.json / npcs.json /
#    actors.json / events.json / characters/*.json / sessions/*.json / geo.json.
#    (Use jq or a small script; keys only — never the "acteur:"/"faction:" VALUES.)
```

Alternatively, **re-seed** the campaign from the updated `data/mygamemaster/
campaigns/_template` (or `example-mistfall`) and re-enter campaign-specific
content.

For Ansible: re-render with `ansible/playbooks/update-config.yml` after pulling
the renamed role (the new `campaign_*` vars + `campaigns` host group + the
`hermes-campaign.container.j2` quadlet); the `-e campagne=<slug>` legacy alias
still resolves.
