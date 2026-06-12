# Modules MJ Tonnerre

The **modules** are our custom Hermes skills — the core value of the project. They live under
`modules/gaming/` and are loaded by Hermes via `skills.external_dirs: [/opt/modules]` (see
`specs/architecture.md`). In the container they are baked into the image (or bind-mounted in
dev mode, see `docs/04-ameliorer-les-modules.md`).

## The umbrella skill

| Skill | Role |
|---|---|
| **mj-tonnerre** | Umbrella skill, always loaded in session: persona, code of conduct, architecture for running a game. Refers to the inviolable rules of `SOUL.md`. |

## Game running

| Skill | Role |
|---|---|
| **mj-tonnerre-initiation** | Questionnaire to create a new campaign (theme, rules, world, players) and initialize its files. |
| **mj-tonnerre-session** | Session wrap-up and resumption: formatted summaries, full state save, stats. |
| **mj-tonnerre-help** | Guides the player in using MJ Tonnerre (how it works, skill list, support). |

## Game mechanics

| Skill | Role |
|---|---|
| **mj-tonnerre-outils** | Dice rolls (Python `secrets` + quantum via qrandom.io) and action resolution (`!jet`, `!jetq`, `!action`). |
| **mj-tonnerre-intendant** | "The Steward (Banker)": transactional checker for every action (inventory, knowledge, consistency, time). Rules engine. |
| **mj-tonnerre-inventaire** | Player inventory: display, add, use, discard, transfer. Evolving YAML item base. |
| **mj-tonnerre-personnage** | Character sheets (`!fiche`, `!perso`, `!notes`) with strict per-player compartmentalization. |

## Living world

| Skill | Role |
|---|---|
| **mj-tonnerre-pnj** | Persistent NPC agent (level 2): embodies ONE non-player character with limited vision, acts like a player toward the GM. |
| **mj-tonnerre-faction** | Persistent Faction agent (level 2): embodies ONE faction as collective intelligence with limited vision. |
| **mj-tonnerre-images** | Image generation (scenes, portraits, maps) via pipeline style → templates → instances (OpenRouter / ComfyUI). |
| **mj-tonnerre-tts** | Qualitative narrative voice: synthesis of ONLY the narration (Minimax T2A v2, `speech-2.8-turbo`, voice `French_Female_Speech_New`). Auto (axis `tts`, hook `transform_llm_output`) + manual (`!raconte`). Two-stage pipeline that offloads the GM model. |

## Quality & reporting

| Skill | Role |
|---|---|
| **mj-tonnerre-analyste** | Inconsistency diagnosis: mode A (bug), B (wrap-up audit), C (pre-session audit). |
| **mj-tonnerre-bug-report** | Allows the player to report an issue (context / expected / actual), stored for deferred processing. |
| **mj-tonnerre-game-report** | Factual session report (actions, locations, NPCs, decisions, inventory) — no spoilers. |
| **mj-tonnerre-write-history** | Narrative session summary, novel style — read like a chapter, no mechanics or spoilers. |

## Shared scripts

The umbrella skill `mj-tonnerre/scripts/` provides Python/Bash tooling: dice rolls (`roll.py`),
narrative clock (`clock.py`), validation (`validate_schema.py`, `validate_json.py`,
`check_session.py`), wrap-up (`close_session.py`), briefs (`build_brief.py`), campaign loading
(`load_campaign.py`), faction slices (`faction_slice.py`), orchestration
(`run_turn.sh`, `ensure_agent.sh`). JSON schemas under `scripts/schemas/`.

> **Portability note**: `ensure_agent.sh` contains a fallback `/opt/hermes/bin/hermes`;
> it prefers `HERMES_BIN`/`$PATH`, so it works in the container (binary under
> `/opt/hermes/.venv/bin`). NPC/Faction agents ("level 2") will be deployed as additional
> containers in a later phase (see `specs/profiles-vers-conteneurs.md`).

## Runtime hooks (systematic mechanisms)

`mj-tonnerre/hooks/` contains the **Hermes runtime hooks** — scripts executed by the gateway
at **every** exchange (CLI + Discord), wired via the `hooks:` block in `config.yaml`. They make
**inviolable** (model-independent): state injection taking precedence before narration
(`pre_llm_call`), JSON integrity guard (`pre_tool_call`), the Steward (Banker) "Persisted" report
computed on real deltas (`post_tool_call` + `transform_llm_output`), verbosity and
CSV collection. Fail-open (stdlib only). See [`specs/hooks-runtime.md`](../specs/hooks-runtime.md)
and [`docs/09-hooks-runtime.md`](../docs/09-hooks-runtime.md).

> Not to be confused with `scripts/install-hooks.sh` (**git** hooks for commit validation).

## Rules reference

`mj-tonnerre/references/` contains foundational rules (data governance, faction tracking, timeline, generic d20 system, verbosity, recurring errors…) and **thematic modules** (`references/modules/`: travel, factions, weather, politics, artifacts, NPC proactivity, worldbuilding, kingdom building) activated per `world.json > modules`.
