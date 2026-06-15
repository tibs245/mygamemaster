# 00 — Living World: Overview

> This series documents the system that makes the world **coherent in space and
> time**, and **alive even outside sessions** (factions, key NPCs, cities that evolve when
> nobody plays). It builds on the existing foundation (`world.json`, `events.json`,
> hooks, the Steward (Banker), level-2 agents) — this is a **formalization and extension**,
> not a complete overhaul.

## The Two Fundamental Questions

1. **Keep the world alive when the player is not there.** Factions, key NPCs, and cities
   have goals, trajectories, and plans. They must **advance coherently between
   sessions** — and their actions must be able to **intersect with the player** at the right place, at
   the right time, with a story that holds together if we return a week, a year, or three centuries
   later.

2. **Maintain reliable geographic and temporal coherence** — know **who is where**, **what
   exists around a location**, **where an entity is at any given moment** — and this **with
   cheap models**, which are bad at geometry and temporal arithmetic.

## The Unifying Principle: The Steward of Space-Time

The **Steward (Banker)** (`mygamemaster-intendant`) already conserves **resources**: an object leaves
one inventory and appears in another, nothing is created or destroyed without reason. We
**apply exactly this discipline** to three other dimensions:

| Conserved Dimension | Rule | Guaranteed by |
|---|---|---|
| **Resources** (already done) | A good transferred is neither created nor lost | Steward (Banker) |
| **Space** | An entity does not teleport: its position is *continuous in time* | Spatial Validator |
| **Time** | Time advances in **monotone and quantified** fashion (`T` integer, from 0) | World Clock |
| **Causality** | An event has a **cause** and a **delay** (fields burn → famine comes *later*) | Propagation Engine |

**Direct consequence for cheap models**: the LLM never **calculates** these
conservations. It **declares** them (« the village heads east ») and **code** verifies
and applies them. The small model is restricted to what it does well — *« given its situation,
what is its next intention? »* and narration — while geometry, deadlines, and cascades remain
**deterministic**.

```
   LLM (deepseek-flash, gemma…)        CODE (deterministic, verifiable)
   ───────────────────────────         ──────────────────────────────
   • declares intentions               • geometry, distances, trajectories
   • decides local ambiguity           • temporal arithmetic, deadlines
   • qualifies / narrates              • conservation (extended Steward)
                                       • topology of causal cascades
        \                                        /
         \____________  hooks into   ________/
                        existing hooks
              (pre_llm_call, post_tool_call, transform_llm_output)
```

## Enacted Decisions

Four design choices structure the rest (see details in corresponding files):

1. **Clock.** An integer `T` that starts at **0 at campaign creation** and grows monotonically,
   backed by `events.json`. → [`01`](01-horloge-et-espace.md)
2. **Session Boundary First.** The simulation runs **at session boundaries** (pre-processing before,
   post-processing after). Evolution toward **selective** background ticks (by *impact score*)
   will come later. → [`03`](03-moteur-de-tick.md)
3. **Stable IDs + Separate Agents.** Locations and actors receive **stable identifiers**;
   each major actor is carried by an **isolated agent** (level 2). → [`02`](02-acteurs-et-agents.md)
4. **Multi-level Causal Propagation** from the start, with **bounds**. → [`04`](04-propagation-causale.md)

## Glossary

| Term | Meaning |
|---|---|
| **T-world** | The clock: integer ≥ 0 in **UT** (1 UT = 10 min game time), `T=0` at creation. |
| **id** | Stable identifier of a location/actor (`lieu:tonnerre/eglise`, `acteur:berthe`). |
| **Containment** | Nesting of locations (`parent`): the crypt *within* the church *within* Tonnerre. |
| **Adjacency** | Edge of the spatial graph between two locations (direction, distance, time, route). |
| **Anchor** | Rough coordinates `(x,y)` of a location — for **calculations**, never shown to the LLM. |
| **Trajectory** | Position of an entity **as a function of time**: sequence of segments `(location, [t0,t1])`. |
| **Actor** | Entity with a goal and a plan: key NPC, faction, city/community. |
| **Plan** | Sequence of **dated intentions** of an actor (location, action, deadline, expected consequence). |
| **LOD** | *Level of detail*: simulation granularity based on space-time distance to the player. |
| **Hot / Warm / Cold Zone** | The player is here / might encounter / far away. → [`03`](03-moteur-de-tick.md) |
| **Tick** | One beat of the engine: advances plans, applies consequences, emits events. |
| **Projection (pre)** | Before session: tick + calculation of **intersections** with the player → briefing. |
| **Reconciliation (post)** | After session: compares plans to what the player *actually* did. |
| **Propagation** | Causal cascade on the **relationship graph** (trade, vassalage, hostility…). |
| **Context Assembler** | Builds, for each scene, the **relevant slice** injected to the GM. |
| **Impact Score** | Heuristic measure of the probability that an actor crosses/affects the player. |

## What I would have wanted on arrival: The System Map

During exploration, the most useful thing would have been a map of « **what lives where** » and « **what
already exists vs what is missing** ». Here it is.

### Current State ✅ vs To Build 🔨

| Component | State | Where / What |
|---|---|---|
| Narrative Clock | ✅ partial | `events.json` (`t`), `suivi.jour_courant` ; to **unify** into `T` integer |
| Distances between Locations | ✅ | `world.json > regles.temps.deplacements` (duration matrix) |
| Spatial Validation | ✅ | `scripts/validator-distances.py` (4 governance rules) |
| **Explicit Spatial Graph** | 🔨 | containment + adjacency + anchor; **stable ids** → [`01`](01-horloge-et-espace.md) |
| **Position = Function of Time** | 🔨 | trajectories; today `localisation_actuelle` is plain text |
| Actor Goals / Motivations | ✅ partial | `npcs.json`, `global_state.factions`, `faction_actions_horloge` |
| **Generalized Dated Plans** | 🔨 | extend faction clock to NPCs and cities → [`02`](02-acteurs-et-agents.md) |
| Clock Advancement | ✅ partial | `scripts/clock.py` (`approche`/`echue`) ; to integrate into **tick engine** |
| **LOD Tick Engine (pre/post)** | 🔨 | heart of « living world » → [`03`](03-moteur-de-tick.md) |
| **Causal Propagation** | 🔨 | relationship graph + dated cascade → [`04`](04-propagation-causale.md) |
| State Injection to GM | ✅ partial | `hooks/pre_llm_call.py` ; to **spatialize** → [`05`](05-assembleur-de-contexte.md) |
| Isolated Actor Agents | ✅ started | `build_brief.py`, `call_pnj.py`, `faction_slice.py`, skills `-pnj` / `-faction` |
| Coherence Judge | ✅ | `hooks/llm_judge.py` (reused as anti-drift safeguard) |
| Snapshot/Timeline | ✅ | `outils/gestion_temps.py` (snapshot of world at instant T) |

### Code Files to Know (Repository « Table of Contents »)

```
modules/gaming/mygamemaster/
├── hooks/
│   ├── pre_llm_call.py          # injects state → BECOMES context assembler (05)
│   ├── post_tool_call.py        # ledger of real deltas + auto-commit git
│   ├── transform_llm_output.py  # Steward report + judge → post-turn hook point
│   └── llm_judge.py             # coherence judge (anti-drift safeguard)
├── scripts/
│   ├── clock.py                 # advances faction clock → merged into tick (03)
│   ├── validator-distances.py   # spatial validation → extended as graph validator (01)
│   ├── close_session.py         # wrap-up pipeline → triggers post-processing (03)
│   ├── build_brief.py           # limited brief of an actor → input to agents (02)
│   ├── call_pnj.py              # invokes isolated NPC agent (02)
│   ├── faction_slice.py         # race-free slice write (02)
│   └── schemas/*.schema.json    # JSON schemas → to extend (geo, trajectory, plan)
└── references/modules/          # thematics modules activable (factions, travel, …)

data/mygamemaster/campaigns/<slug>/
├── world.json        # universe.regions, regles.temps.deplacements, global_state.factions…
├── npcs.json          # NPC sheets (established_facts, motivations, localisation_actuelle)
├── events.json   # timeline (t, type, entity) → T clock support
└── outils/gestion_temps.py  # timeline queries + world snapshot at T
```

## Reading Map

| File | Answers |
|---|---|
| [`01-horloge-et-espace.md`](01-horloge-et-espace.md) | The 4D model: clock `T`, spatial graph, trajectories, query tools, invariants. |
| [`02-acteurs-et-agents.md`](02-acteurs-et-agents.md) | What an actor is, its plan, and how **separate agents** carry it. |
| [`03-moteur-de-tick.md`](03-moteur-de-tick.md) | LOD, tick, **pre-processing** (projection) and **post-processing** (reconciliation). |
| [`04-propagation-causale.md`](04-propagation-causale.md) | How an event causes others, at distance and in time (wheat → famine). |
| [`05-assembleur-de-contexte.md`](05-assembleur-de-contexte.md) | How the GM is **briefed** per scene without drowning (key for small models). |
| [`06-flux-dune-partie.md`](06-flux-dune-partie.md) | **The complete flow diagram** of a session, from creation to distant resumption. |
| [`07-plan-de-mise-en-oeuvre.md`](07-plan-de-mise-en-oeuvre.md) | Implementation order, migration, what changes in existing code, models per task. |
| [`10-features.md`](10-features.md) | **Unified feature flags** (`meta.features`): 6 axes ON by default, cascade `world > env > True`, fail-open, typical configs. |

## The Red Thread in One Sentence

> **Externalize space, time, and causality into versioned structures; enforce them with deterministic code;
> and ask the LLM only to declare intentions and narrate the relevant slice we present to it.**
