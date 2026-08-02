# 07 — Implementation Plan

> How to transition from the current system to this one, **without breaking anything**, through
> deliverable slices. The philosophy remains yours: deterministic in code, LLM at the seams,
> files = truth.

## 1. Existing to reuse vs. to build

| Component | Reuse | Build |
|---|---|---|
| Clock | `events.json` (`t`), `gestion_temps.py` | Unified `T` integer from 0; centralized `T↔day/hour` conversion |
| Space | `regles.temps.deplacements`, `validator-distances.py` | `geo.json` (graph), `geo_query.py`, MDS anchoring, extended validator |
| Actors | `npcs.json`, `global_state.factions`, `faction_actions_horloge` | Unified **plan** schema, `lod`, trajectories, promotion/demotion |
| Agents | `build_brief.py`, `call_npc.py`, `faction_slice.py`, skills `-pnj`/`-faction` | Tick orchestration loop, **intention output** schema |
| Tick | `clock.py` | `world_tick.py` (PRE/POST), LOD, lazy generation |
| Causality | — | Typed `relations`, `causal_propagate.py`, scheduled events |
| GM Context | `pre_llm_call.py` | `scene_brief.py` (spatial/temporal/relational filtering) |
| Safeguards | `llm_judge.py`, Banker | Banker extension for space/time/causality |

## 2. Implementation order (by phases)

Each phase is **deliverable and independently testable**. We move to the next only once the
previous one is green.

### Phase 0 — Foundations: stable ids + `T` clock
- Assign a stable `id` to each location and actor across 2 campaigns (migration script; we
  **preserve narrative names** for narration).
- Unify the clock: `T` integer in UT from 0; back-fill from `events.json`.
- **Done when**: `gestion_temps.py` reads/writes `T` everywhere, ids resolved without ambiguity.

### Phase 1 — Spatial graph + queries
- Generate `geo.json`: containment (`parent`) + adjacency (from `deplacements`) + anchoring (MDS
  on duration matrix) + cardinal direction (extracted from descriptions, completed manually).
- Write `geo_query.py` (sub-commands from table [`01`](01-clock-and-space.md) §6).
- Extend `validator-distances.py` → graph validator (the 5 invariants).
- **Done when**: "who is where / around / path / crossroads" answer correctly on
  `naissance-dun-roi`.

### Phase 2 — Actors & plans
- Migrate `faction_actions_horloge` → **plan** schema (dated intentions); extend to key NPCs
  and cities; add trajectories and `relations`.
- Tools `actor promote/demote`; intention output schema (validated).
- **Done when**: 2-3 major actors from `naissance-dun-roi` have a coherent dated plan.

### Phase 3 — Tick engine (cadence A)
- `world_tick.py pre|post`: LOD, intention resolution, `agent_decide` seam, lazy generation.
- Hooks: session open → `pre`; `close_session.py` → `post`.
- **Done when**: a played session advances plans and reconciles reality, without manual
  intervention.

### Phase 4 — Causal propagation (multi-level, bounded)
- Typed `relations` on actors; `causal_propagate.py` (depth, threshold, attenuation);
  `scheduled` events in `events.json`.
- **Done when**: the fire→shortage→migration scenario ([`04`](04-causal-propagation.md))
  unfolds and stays bounded.

### Phase 5 — Context assembler
- `scene_brief.py`; hook into `pre_llm_call.py`.
- **Done when**: the GM receives the compact SCENE BRIEF each turn, and cost/turn drops.

### Phase 6 — Cadence B (later)
- Timer Quadlet/cron + `score_impact`; only LLM-tick actors above threshold.
- **Done when**: the world evolves between sessions at controlled cost.

## 3. Recommended vertical slice (the first real test)

Rather than doing everything phase-by-phase flat, deliver **a vertical slice** on
**real** data already present:

> **Campaign `naissance-dun-roi`, actor `faction:bande-du-corbeau`, intention "winter
> provisioning raid".** This plan **already exists** in `faction_actions_horloge`
> (deadline "in 2–3 weeks", consequence "farm plundered / Bertha's cabin plundered").

Minimal steps: stable ids on March locations → graph from existing `deplacements` → model the Band as an actor with this plan dated in `T` → hook `world_tick pre`
at session open → verify that a player passing near the Ford at the wrong time **encounters** the raid,
and that `post` reconciles based on whether they stopped it or not. It's small, it's real, and it exercises
**the entire** system end-to-end.

## 4. What changes in existing files

| File | Change |
|---|---|
| `hooks/pre_llm_call.py` | calls `scene_brief.py` and injects the SCENE BRIEF |
| `scripts/close_session.py` | adds `world_tick.py post` step |
| `scripts/validator-distances.py` | becomes the graph validator (5 invariants) |
| `scripts/clock.py` | absorbed by `world_tick.py` (faction clock becomes the tick) |
| `scripts/schemas/*.json` | new schemas: `geo`, `trajectoire`, `plan`, `intention`, `relation` |
| `data/.../world.json` | `regles.temps.deplacements` → graph source; ids added |
| `references/modules/factions.md` | faction clock reformulated as "dated plans" |

**New files**: `geo.json` (per campaign), `geo_query.py`, `world_tick.py`,
`causal_propagate.py`, `scene_brief.py`.

## 5. LLM models by task

Aligned with project preference (**avoid Gemini**, favor **Gemma 4**; **Nano Banana**
reserved for images):

| Task | Model | Why |
|---|---|---|
| GM narration | `deepseek-v4-flash` (current default) | fluent, already in place |
| Actor decision (structured intention) | `gemma-4` | reliable structured output, cheap |
| Coherence judge | `gemma-4` (current judge default) | already configured |
| Narrative qualification of event (propagation) | `deepseek-v4-flash` | short, narrative, deferred |
| Spatial anchoring (MDS), geometry, deadlines | **no LLM** | pure calculation (numpy/scipy) |
| Illustrations | **Nano Banana** | image-only exception |

## 6. Risks and mitigations

| Risk | Mitigation |
|---|---|
| Migration of ids on active campaigns | automatic script + name preservation; commit/snapshot first |
| Incomplete duration matrix → approximate MDS | **coarse** coords suffice; complete missing edges by hand |
| LLM cost if too many "warm" actors | aggressive LOD + `score_impact`; cold ones stay deterministic (0 tokens) |
| Narrative drift under autonomy | extended Banker + judge on **generated** events + cascade bounding |
| Over-engineering | deliver the **vertical slice** (§3) before generalizing |

## 7. Validation loop

At each phase, the existing **judge** and **Banker** serve as live coherence tests.
Add cases to `collecte.csv` (already the diagnostic log) to measure, **by model**, the
rate of first-pass valid intentions — this metric tells whether a given model "holds" the actor role,
and thus how far down we can push costs.

---

**In summary**: Phases 0–1 establish reliable space-time; Phases 2–3 bring actors to life at session bounds; Phase 4 propagates consequences; Phase 5 lightens the GM's load; Phase 6 lets the world breathe between sessions. The "Band of the Raven raid" vertical slice exercises the entire system on your real data by the end of Phase 3.
