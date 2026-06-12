# 02 — Actors, Intentions, and Separated Agents

> Who *moves* and *decides* in the world? The **major actors**: key NPCs, factions,
> cities/communities. They share a **common structure** (goal → plan → trajectory) and are
> driven by **isolated agents**. This file generalizes what `faction_actions_horloge` already does
> for factions.

## 1. The Unified Actor Model

A key NPC, a faction, and a city are the **same thing** viewed at different scales: an
entity with a **goal**, possessing **resources**, following a **plan** of dated intentions,
moving along a **trajectory** ([`01`](01-horloge-et-espace.md)) and maintaining
**relationships** ([`04`](04-propagation-causale.md)).

```json
{
  "id": "faction:bande-du-corbeau",
  "type": "faction",                       // npc | faction | city
  "lod": "warm",                          // hot | warm | cold (calculated, see 03)
  "long_term_goal": "Hold the passages of the Marches before winter",
  "motivations": ["winter survival", "territory"],
  "situation": "Camped at the Raven Ford, ~20 members, morale fair",
  "resources": { "food_days": 12, "men": 20, "gold": 40 },
  "plan": [
    {
      "id": "intent:winter-raid",
      "action": "Provisioning raid on an isolated farm",
      "location": "location:marches/rousset-farm",
      "deadline": 43200,                    // T (UT) — deterministic
      "preconditions": ["resources.food_days < 14"],
      "expected_consequence": "+30 food_days; +hostility from farmers; rumor in Tonnerre",
      "visible_to_pc": true,
      "status": "planned"                  // planned | ongoing | completed | failed | cancelled
    }
  ],
  "relationships": [
    { "to": "faction:tonnerre-militia", "type": "hostility", "intensity": 0.6 },
    { "to": "city:tonnerre",          "type": "predation", "intensity": 0.4 }
  ]
}
```

> **Continuity with existing code.** The fields `goal`, `motivations`, `situation`, `relationships`
> already exist in `npcs.json` and `global_state.factions`. The **plan** is the generalization
> of `faction_actions_horloge` (`trigger` → `preconditions`, `deadline` → `deadline` in
> `T`, `consequence` → `expected_consequence`). The **`lod`** and **trajectory** are new.

### The Plan = Dated Intentions

An **intention** is the atomic unit of the living world. It states *what*, *where*, *when at the latest*
(`deadline` in `T`), *under which conditions*, and *with what expected consequence*.
This is what the tick engine **consumes** ([`03`](03-moteur-de-tick.md)) and what
preprocessing **projects** onto the player.

Rule inherited from factions, preserved: a goal must be **independent of the player**
(✅ "build reserves before winter"; ❌ "wait for the PC to arrive"). The player can
**delay, divert, accelerate** a plan — but not cancel it through mere absence.

## 2. Identifiers and Granularity

- **Stable `id`** per actor (`actor:berthe`, `faction:raven-gang`, `city:tonnerre`).
- Not every NPC is a **major** actor. A minor character (the innkeeper met once) remains a
  simple **reactive** sheet, without plan or agent. An NPC is **promoted** to major actor when it
  acquires **influence** or a **trajectory of its own**.

### Who is "major"? — GM's choice, by criteria

The GM must **understand** these notions to decide (this is a point you raised). We give them
an explicit grid. An actor is **major** if it meets at least one criterion:

| Criterion | Example |
|---|---|
| **Scope** — can change world state beyond itself | a faction, a lord, a guild |
| **Own trajectory** — moves independently of the player | a caravan, an army, a migrating village |
| **Narrative Stakes** — bearer of a plot thread | the rival, the missing mentor, the usurper |
| **Causal Node** — others depend on it | the city that supplies the region's grain |

Promotion/demotion are **explicit operations** (`actor promote <id>` /
`actor demote <id>`), tracked in the timeline. A demoted actor **freezes its trajectory**
and becomes a reactive sheet again (simulation economy).

## 3. Orchestration by Separated Agents

Each major actor is driven by an **isolated agent** — exactly the **level 2** already started
in the project (skills [`mj-tonnerre-pnj`](../../modules/gaming/mj-tonnerre-pnj/SKILL.md) and
[`mj-tonnerre-faction`](../../modules/gaming/mj-tonnerre-faction/SKILL.md)).

```
                       ┌───────────────────────────────────────────┐
                       │        TICK ENGINE (deterministic)          │
                       │  selects actors to "think"                 │
                       └───────────────────────────────────────────┘
        build_brief.py │            │ call_npc.py / hermes -p        │ faction_slice.py
        (limited brief)▼            ▼ (isolated invocation)          ▼ (safe write)
   ┌──────────────┐  ┌──────────────┐  ┌──────────────┐      ┌─────────────────────┐
   │ agent:berthe │  │ agent:raven  │  │ agent:tonnerre│ ...  │  files = truth      │
   │ (isolated    │  │ (isolated    │  │ (isolated     │      │  (Steward + valid)  │
   │  memory)     │  │  memory)     │  │  memory)      │      └─────────────────────┘
   └──────────────┘  └──────────────┘  └──────────────┘
        └─ NEVER see the player or other actors ─┘
```

### Why **isolated** agents (one profile per actor)

- **No knowledge leak.** The `berthe` agent only knows what Berthe knows (its
  `build_brief.py` contains only her `established_facts` + `private_knowledge`). A small
  model, shown *little* and *only what's relevant*, hallucinates much less.
- **Own memory.** Each profile `hermes -p actor-<slug>` has its session and memory — actor
  continuity from tick to tick is free.
- **The GM remains the sole player interface.** Actor agents have no messaging tools
  to Discord; they **produce intentions**, the GM **narrates**.

### The LLM Seam: One Question, Structured Output

When the engine decides an actor should **think** (plan exhausted, goal reached/blocked, or
significant event concerning it), it invokes it with a minimal brief and **one** question:

```
INPUT (build_brief.py):   goal + situation + resources + recent events concerning it
QUESTION:                 "What is your next intention?"
OUTPUT (imposed schema):   { action, location, deadline, preconditions, expected_consequence, visible_to_pc }
```

The output is **validated against a schema** (as the Steward already enforces formats), then
against invariants ([`01`](01-horloge-et-espace.md) §5) before entering the plan. If it
violates a conservation law (teleportation, resource created), it is **rejected** and the actor
"rethinks" with the rejection reason — feed-forward, exactly like `llm_judge.py` today.

> **Cost.** A **cold** actor triggers **no** LLM calls (its clock advances by calculation).
> A warm/hot actor, **at most one** call per tick, on a tiny context → ideal for
> `deepseek-flash` (narration) or `gemma` (structured decision). See the model table in
> [`07`](07-plan-de-mise-en-oeuvre.md).

## 4. Safe Writing and Anti-Divergence

- **Single source of truth: files.** An agent never mutates state directly; the
  engine applies the validated intention via [`faction_slice.py`](../../modules/gaming/mj-tonnerre/scripts/faction_slice.py)
  (slice reintegration, anti-concurrency) and `geo_query.py` (trajectories).
- **The extended Steward** verifies each consequence (resources, position, relationships) before
  writing.
- **The judge** ([`llm_judge.py`](../../modules/gaming/mj-tonnerre/hooks/llm_judge.py)) controls
  **plausibility** of generated intentions (a pauper does not raise an army in one night).
- **Deterministic dominates**: the LLM only proposes at *seams*; everything else is code.

→ Next: [`03-moteur-de-tick.md`](03-moteur-de-tick.md) — when and how these plans advance.
