# Modules MJ Tonnerre

The **modules** are our custom Hermes skills — the core value of the project. They live under
`modules/gaming/` and are loaded by Hermes via `skills.external_dirs: [/opt/modules]` (see
`specs/architecture.md`). In the container they are baked into the image (or bind-mounted in
dev mode, see `docs/04-improve-the-modules.md`).

## The umbrella skill

| Skill | Role |
|---|---|
| **mygamemaster** | Umbrella skill, always loaded in session: persona, code of conduct, architecture for running a game. Refers to the inviolable rules of `SOUL.md`. |

## Game running

| Skill | Role |
|---|---|
| **mygamemaster-initiation** | Questionnaire to create a new campaign (theme, rules, world, players) and initialize its files. |
| **mygamemaster-session** | Session wrap-up and resumption: formatted summaries, full state save, stats. |
| **mygamemaster-help** | Guides the player in using MJ Tonnerre (how it works, skill list, support). |

## Game mechanics

| Skill | Role |
|---|---|
| **mygamemaster-outils** | Dice rolls (Python `secrets` + quantum via qrandom.io) and action resolution (`!jet`, `!jetq`, `!action`). |
| **mygamemaster-intendant** | "The Steward (Banker)": transactional checker for every action (inventory, knowledge, consistency, time). Rules engine. |
| **mygamemaster-inventaire** | Player inventory: display, add, use, discard, transfer. Evolving YAML item base. |
| **mygamemaster-personnage** | Character sheets (`!fiche`, `!perso`, `!notes`) with strict per-player compartmentalization. |

## Living world

| Skill | Role |
|---|---|
| **mygamemaster-pnj** | Persistent NPC agent (level 2): embodies ONE non-player character with limited vision, acts like a player toward the GM. |
| **mygamemaster-faction** | Persistent Faction agent (level 2): embodies ONE faction as collective intelligence with limited vision. |
| **mygamemaster-emotions** | Character emotions (primarily NPCs): compact model (6 emotions 0..1 + temperament baseline + explainable history) that evolves via deterministic event rules and decays toward temperament; concise summary injected into the GM context (`pre_llm_call`, fail-open) so portrayal stays consistent — shown through behavior, never told as stats. |
| **mygamemaster-images** | Image generation (scenes, portraits, maps) via pipeline style → templates → instances (OpenRouter / ComfyUI). |
| **mygamemaster-tts** | Qualitative narrative voice: synthesis of ONLY the narration (Minimax T2A v2, `speech-2.8-turbo`, voice `French_Female_Speech_New`). Auto (axis `tts`, hook `transform_llm_output`) + manual (`!raconte`). Two-stage pipeline that offloads the GM model. |

## Quality & reporting

| Skill | Role |
|---|---|
| **mygamemaster-analyste** | Inconsistency diagnosis: mode A (bug), B (wrap-up audit), C (pre-session audit). |
| **mygamemaster-bug-report** | Allows the player to report an issue (context / expected / actual), stored for deferred processing. |
| **mygamemaster-game-report** | Factual session report (actions, locations, NPCs, decisions, inventory) — no spoilers. |
| **mygamemaster-write-history** | Narrative session summary, novel style — read like a chapter, no mechanics or spoilers. |

## Shared scripts

The umbrella skill `mygamemaster/scripts/` provides Python/Bash tooling: dice rolls (`roll.py`),
narrative clock (`clock.py`), validation (`validate_schema.py`, `validate_json.py`,
`check_session.py`), wrap-up (`close_session.py`), briefs (`build_brief.py`), campaign loading
(`load_campaign.py`), faction slices (`faction_slice.py`), character emotions (`emotions.py`),
orchestration (`run_turn.sh`, `ensure_agent.sh`). JSON schemas under `scripts/schemas/`.

> **Portability note**: `ensure_agent.sh` contains a fallback `/opt/hermes/bin/hermes`;
> it prefers `HERMES_BIN`/`$PATH`, so it works in the container (binary under
> `/opt/hermes/.venv/bin`). NPC/Faction agents ("level 2") will be deployed as additional
> containers in a later phase (see `specs/profiles-to-containers.md`).

## UI strings localization (runtime i18n)

The GM's **narration** comes from the LLM in the player's language. The engine's
**fixed scaffolding strings** (scene-brief column labels, the Steward "Persisted"
block, pause/resume notes, scoreboard headers, the compact state labels) are
localized at runtime by the dependency-free helper `mygamemaster/scripts/i18n.py`:

- `t(key, lang=None, **kwargs)` looks up a translation table. The **default and
  fallback locale is English** (`en`): an unknown key, an unknown language, or a
  locale lacking the key all degrade to the English string — **fail-open**, so
  the output is byte-identical when the language is `en` or unresolved.
- The active language is resolved by `resolve_lang(monde)` from a **single
  cascade**: env `MGM_LANGUAGE` > `world.json > meta.langue` > `en`. Hooks reach
  it through `_lib.lang(monde)` and `_lib.t(...)`.
- Locales shipped: `en` (reference) and `fr` (first additional locale).

**Adding a locale**: in `scripts/i18n.py`, add a `<code>` dict to `TABLES`
mapping the same keys as the `en` table (translate only what you need — missing
keys fall back to English). Then expose the language via `world.json > meta.langue`
(e.g. `"de"`) or the `MGM_LANGUAGE` env var. Tag normalization is tolerant
(`fr-FR`, `FR`, `fr_FR` → `fr`). Covered by `scripts/tests/test_i18n.py`.

## Runtime hooks (systematic mechanisms)

`mygamemaster/hooks/` contains the **Hermes runtime hooks** — scripts executed by the gateway
at **every** exchange (CLI + Discord), wired via the `hooks:` block in `config.yaml`. They make
**inviolable** (model-independent): state injection taking precedence before narration
(`pre_llm_call`), JSON integrity guard (`pre_tool_call`), the Steward (Banker) "Persisted" report
computed on real deltas (`post_tool_call` + `transform_llm_output`), verbosity and
CSV collection. Fail-open (stdlib only). See [`specs/hooks-runtime.md`](../specs/hooks-runtime.md)
and [`docs/09-runtime-hooks.md`](../docs/09-runtime-hooks.md).

> Not to be confused with `scripts/install-hooks.sh` (**git** hooks for commit validation).

## Rules reference

`mygamemaster/references/` contains foundational rules (data governance, faction tracking, timeline, generic d20 system, verbosity, recurring errors…) and **thematic modules** (`references/modules/`: travel, factions, weather, politics, artifacts, NPC proactivity, worldbuilding, kingdom building) activated per `world.json > modules`.
