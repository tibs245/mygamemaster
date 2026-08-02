# 📐 Verbosity — Emoji & Format Convention

> ℹ️ **Verbosity is now managed automatically by the `transform_llm_output` hook** (Persisted block + label per `meta.verbosite`). The canonical emoji table lives in `modules/gaming/mygamemaster/hooks/_lib.py`. The GM does NOT need to produce this block by hand. What follows is only a format reference (maintainers) and a fallback if hooks are disabled (`meta.hooks.banquier_persiste=false`) or in bypass mode `⏸️`.

> **Index + shared emoji table.** One file per verbosity level.
> The active level lives in `world.json > meta.verbosite` ; the player changes it with `!verbosite <niveau>` (command / `mygamemaster-steward`).

---

## Files by Level

| Level | File | Usage |
|--------|---------|-------|
| TRACE | [`trace.md`](trace.md) | Each detailed sub-step — complete audit, data debugging |
| DEBUG | [`debug.md`](debug.md) | Persistence operations only — save verification |
| INFO | [`info.md`](info.md) | PC-oriented summary — **DEFAULT** — normal play |
| WARN | [`warn.md`](warn.md) | Alerts only — smooth gameplay |
| ERROR | [`error.md`](error.md) | Blockers only — radio silence except crisis |

---

## Mapping Table — Emoji by Data Type

> **One line = one emoji + one natural language sentence.** No JSON, no code.

| Emoji | Data Type | Category | Source (file) |
|-------|---------------|-----------|------------------|
| 🕒 | Time / Clock | `temps` | `world.json > regles.temps.suivi` |
| ❤️ | Health / HP | `sante` | `characters/<id>.json > sante` |
| 🥦 | Consumable / Food | `inventaire` | `characters/<id>.json > inventaire` |
| 🎒 | Non-consumable Object | `inventaire` | `characters/<id>.json > inventaire` |
| ⚔️ | Weapon / Combat Gear | `inventaire` | `characters/<id>.json > inventaire` |
| ☀️ | Weather | `meteo` | `world.json > regles.meteo` |
| 🌙 | Night / Rest | `temps` | `world.json > regles.temps.suivi` |
| 🔋 | Energy / Fatigue | `etat` | `characters/<id>.json > etats` |
| 📚 | Skill / Learning | `competence` | `characters/<id>.json > competences` |
| 🗺️ | Movement / Position | `position` | `npcs.json > localisation_actuelle` |
| 💬 | Knowledge / Information | `connaissance` | `npcs.json > established_facts` |
| 🤝 | Relation / Attitude | `relation` | `npcs.json > relations` |
| ⭐ | Artifact / Special Object | `artefact` | `world.json > global_state.artefacts_connus` |
| 🏗️ | Construction / Building | `construction` | `world.json > global_state.royaume` |
| ⚡ | Faction / Faction Clock | `faction` | `world.json > faction_actions_horloge` |
| 💀 | Death / Permanent Loss | `sante` | `characters/<id>.json > sante` |
| 🔒 | Red Line / Limit | `limite` | `npcs.json > limites` |
| ❌ | Error / REFUSAL | `erreur` | (Steward) |
| ✅ | Validation / Success | `succes` | (Steward) |
| 🛑 | Blocker | `bloquant` | (Steward) |

---

## Universal Rules (all levels)

> Format reference. Normally applied by the hook; useful only as fallback (hook disabled / bypass).

1. **One line = one emoji + one sentence** in natural language. Never JSON or code.
2. **Numeric values in parentheses**: `❤️ Ruby wounded (7/10 HP)`, `🥦 Sausage consumed (remaining: x1)`.
3. **Source mentioned in INFO+** (the PC involved is named). The lower the level (DEBUG/TRACE), the more technical the output.
4. **No duplicate emoji** on the same line.
5. **A REFUSAL is ALWAYS reported**, regardless of level — even ERROR. An unreported refusal = blocked player.

---

## Integration with Skills

| Skill | Data Types Reported | Levels Affected |
|-------|---------------------------|-------------------|
| `mygamemaster-steward` | All (Steward) | TRACE → ERROR |
| `mygamemaster-character` | ❤️ HP, 📚 skills, 🔋 states | INFO (change notifications) |
| `mygamemaster-inventory` | 🥦, 🎒, ⚔️ objects | INFO (change notifications) |
| `mygamemaster-session` | 🕒 time, 🗺️ positions | INFO |
| `mygamemaster-tools` | Dice rolls (no persistence) | — |
| `mygamemaster-images` | None (no persistence) | — |
