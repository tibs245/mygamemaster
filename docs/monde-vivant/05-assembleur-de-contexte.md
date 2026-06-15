# 05 — The context assembler (the GM briefed, not omniscient)

> You've seen it clearly: *the GM must know these concepts to judge what applies*. But you can't
> load everything into a small model's head — it drowns and hallucinates. The solution:
> **assemble the relevant slice** for it before each scene. This is the evolution of your
> [`pre_llm_call.py`](../../modules/gaming/mygamemaster/hooks/pre_llm_call.py).

## 1. The problem: knowing without drowning

`world.json` can contain dozens of locations, actors, and events. Injecting **everything** at
each turn means:

- **expensive** (tokens) and **slow** ;
- **counterproductive**: the larger the context, the more a small model **confuses** and
  **hallucinates** ;
- **pointless**: 95% has no bearing on the current scene.

The GM should not **carry** the world. Show them the **right window, at the right time**.

## 2. The solution: a scene brief filtered on three axes

Before the scene, `scene_brief.py` queries the three sources and **filters**:

```
                         player position (location id, current T)
                                          │
          ┌───────────────────────────────┼───────────────────────────────┐
          ▼                                ▼                               ▼
   SPATIAL FILTER                   TEMPORAL FILTER                RELATIONAL FILTER
   geo_query: neighbors +           events.json: window            relations: edges
   who_is_at + within_radius        [T−δ, T+δ] + scheduled        pointing here / to player
          │                                │                               │
          └───────────────────────────────┼───────────────────────────────┘
                                           ▼
                                  SCENE BRIEF (~1 screen)
                                  injected to GM via pre_llm_call
```

- **Spatial** — *where* and *around what*: the current location, its neighbors (directions, distances),
  its contained locations, and **who is present** at `T` (`geo_query.py who_is_at`).
- **Temporal** — *what is recent and imminent*: events from recent days in the area, and
  especially the **scheduled events** ([`04`](04-propagation-causale.md)) that will "ring"
  during the session (the clocks).
- **Relational** — *who has a stake here*: actors whose relation points to this location or to
  the player, and **moving actors** whose trajectory **crosses** the player
  ([`03`](03-moteur-de-tick.md)).

## 3. The structure of the scene brief

A compact, stable format that the GM learns to read (like the "Persisted" block in the Steward):

```
┌─ SCENE BRIEF ─ T=8320 (Day 58, late afternoon) ───────────────────────┐
│ LOCATION  location:tonnerre/place-du-marche — « the grand square, gray│
│ AROUND    S 60 m → church · W 90 m → forge · contains: stall, well     │
│ PRESENT   actor:gautier (merchant, wary — last action: S7)             │
│           actor:milicien-bost (neutral)                                │
│ MOVEMENT  column bourg-de-l-orme ~2 h NE, climbing to pass (famine) →  │
│           possible crossing if player takes the pass road              │
│ RECENT    D55 market brawl ; D52 bread price increase                  │
│ IMMINENT  ⏰ wheat-shortage "rings" at T≈8320 → rationing (scheduled)   │
│ STAKES    tonnerre depends on wheat from bleville (burned D28) ;       │
│           bande-du-corbeau (predation .4) prowls at ford              │
└────────────────────────────────────────────────────────────────────────┘
```

The GM receives **exactly** what they need to judge "what applies here, now" — no more, no less.
They can then decide, for example, to have a crier announce the rationing, or let the player feel
the tension without naming it.

## 4. Why this is key for cheaper models

| Without assembler | With assembler |
|---|---|
| entire `world.json` injected | ~1 screen filtered |
| model searches for the needle | needle is **already** presented |
| hallucinations of positions/relations | facts **exact**, from code |
| high token cost each turn | minimal and stable cost |

The **spatial + temporal + relational** filtering is precisely what transforms a problem
"too hard for a small model" into "trivial for any model".

## 5. Hook into existing

`pre_llm_call.py` **already** injects context (time, inventories, NPCs present). We **extend** it:

```
pre_llm_call.py
   ├─ (already) time/day, group inventories
   └─ (new) calls scene_brief.py(player_position, T) :
        ├─ geo_query.py  → AROUND + PRESENT + MOVEMENT
        ├─ events.json → RECENT + IMMINENT
        └─ relations      → STAKES
      then injects the SCENE BRIEF into `context`
```

- **Session opening** first calls `world_tick.py pre` ([`03`](03-moteur-de-tick.md)),
  which **feeds** what the assembler will find (hot-promoted actors, materialized scenes).
- Nothing else changes in the loop: `post_tool_call.py` and `transform_llm_output.py`
  continue their work (ledger, Steward, judge).

→ Next: [`06-flux-dune-partie.md`](06-flux-dune-partie.md) — everything assembles in the
complete flow of a session.
