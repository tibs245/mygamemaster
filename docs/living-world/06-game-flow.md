# 06 — The complete flow of a session

> Everything comes together here, on **a single timeline `T`**. This file provides the **master
> diagram** of a session—from creation to distant resumption—then three zooms (session,
> turn, tick).

## Component legend

```
  ▣ DETERMINISTIC CODE (geometry, deadlines, conservation, cascades)
  ◆ LLM at seams (declares intent · qualifies · narrates)
  ▤ FILES = source of truth (world.json, geo.json, npcs.json, events.json)
  ⏰ SCHEDULED EVENT (clock that "rings" at a future T)
```

## 1. Master diagram—the lifecycle of a campaign

```
╔══════════════════════════════════════════════════════════════════════════════╗
║  T = 0   ▣ CAMPAIGN CREATION                                                   ║
║   • initial spatial graph: places + ids + anchoring (MDS on durations)        ║
║   • major actors: goal · plan (dated intents) · trajectory · relations        ║
║   • world clock initialized to T = 0                                     ▤    ║
╚══════════════════════════════════════════════════════════════════════════════╝
                                       │
   ┌───────────────────────────────────┴────────────────────────────────────────┐
   │                          SESSION LOOP  (repeated each session)               │
   │                                                                              │
   │   ┌─ OPENING ─────────────────────────────────────────────────────────────┐ │
   │   │ ▣ world_tick.py  PRE  (projection + staging)                           │ │
   │   │    1. tick(T_last → T_session)   — world catches up to elapsed time    │ │
   │   │    2. ◆ warm actors "think" their next intent if needed                │ │
   │   │    3. ▣ crossings: player trajectory × actor trajectories              │ │
   │   │    4. ▣ promotion to "hot" + materialization of crossed scenes         │ │
   │   │    └──────────────►  BRIEFING handed to GM                             │ │
   │   └────────────────────────────────────────────────────────────────────────┘ │
   │                                   │                                          │
   │   ┌─ PLAY ── hot zone ── sequence of TURNS ────────────────────────────────┐  │
   │   │   (see Zoom 2: the game turn)                                           │  │
   │   │   player acts · GM narrates · state persisted at each action            │  │
   │   └────────────────────────────────────────────────────────────────────────┘ │
   │                                   │                                          │
   │   ┌─ CLOSURE ─────────────────────────────────────────────────────────────┐ │
   │   │ ▣ close_session.py                                                      │ │
   │   │    • validations (json · distances · clock · cross-check)              │ │
   │   │    • ▣ world_tick.py  POST  (reconciliation)                           │ │
   │   │        - confronts PLANNED plans × what player ACTUALLY did             │ │
   │   │        - ◆ renews plans of disturbed actors                            │ │
   │   │        - ▣ propagates player actions (player becomes a cause)          │ │
   │   │    • timestamped snapshot + git commit                             ▤   │ │
   │   └────────────────────────────────────────────────────────────────────────┘ │
   └───────────────────────────────────┬──────────────────────────────────────────┘
                                       │
              ┌────────────────────────┴─────────────────────────┐
              │  BETWEEN SESSIONS                                  │
              │   Cadence A ▸ world "sleeps" (0 tokens)            │
              │   Cadence B ▸ selective background tick:           │
              │               only actors with score_impact>threshold
              │               "think"; others = ▣ cold             │
              └────────────────────────┬─────────────────────────┘
                                       │
                    return +1 week / +1 year / +3 centuries?
                                       │
              ┌────────────────────────┴─────────────────────────┐
              │  LONG TIME JUMP                                    │
              │   ▣ multi-scale tick (jumps to milestones, aggregates)
              │   ⏰ resolves scheduled events (famines,            │
              │      dynasties, ruins) into MACRO FACTS            │
              │   ▣ lazily generates DETAIL of the only             │
              │      zone where player reappears                   │
              └────────────────────────┬─────────────────────────┘
                                       │
                          ◄── return to SESSION LOOP ──►
```

## 2. Zoom 1 — A session (pre → play → post)

```
  OPENING                   PLAY (hot)                       CLOSURE
  ───────                   ──────────                       ───────
  world_tick PRE  ──►  [turn][turn][turn] … [turn]  ──►  close_session
       │                      │                                 │
   world catches up      each turn replays                 actual is
   elapsed time,         assembler + Steward (Banker)      reconciled to
   stages                (Zoom 2)                          planned; plans
   encounters                                              restart; propagate;
                                                           commit
  ───────────────────────────────────────────────────────────────────────►  T
```

## 3. Zoom 2 — A game turn (the existing loop, spatialized)

```
   player message (Discord)
        │
        ▼
   ▣ pre_llm_call.py ──► calls scene_brief.py
        │                   ├─ ▣ geo_query: AROUND · PRESENT · MOVEMENT
        │                   ├─ ▤ evenements: RECENT · ⏰ IMMINENT
        │                   └─ ▤ relations: STAKES
        │                 = SCENE BRIEF (~1 screen, filtered)        ◄── new (file 05)
        ▼
   ◆ LLM GM  (deepseek-flash)  ── narrates + declares symbolic mutations
        │        (move, give object, create location relative…)
        ▼
   ▣ pre_tool_call → tool → post_tool_call   (ledger of actual deltas + auto-commit)
        │        + ▣ spatial validator (no teleportation, graph attachment)
        ▼
   ▣ transform_llm_output ──► "Persisted" block (Steward/Banker) + ◆ judge (coherence)
        ▼
   response to player (Discord)
```

> What **changes** from today: one line only — `pre_llm_call` calls
> the assembler. Everything else in the loop (Steward/Banker, ledger, judge, commit) is **unchanged**.

## 4. Zoom 3 — A tick (deterministic first, LLM minimal)

```
   for each actor:
        │
        ▼
   ▣ classify_LOD(actor, player) ──────────────┐
        │                                       │
     cold ▼                              warm/hot ▼
   ▣ advances abstract                  ▣ resolves DUE intents (deadline ≤ T)
     clock (0 LLM)                        │   ├─ ▣ applies consequence (Steward/Banker)
        │                                   │   ├─ ▤ emits dated event
        │                                   │   └─ ▣ propagates causality (file 04, bounded)
        │                                   ▼
        │                                 plan exhausted / goal reached / shock?
        │                                   │ yes
        │                                   ▼
        │                                 ◆ agent_decide(brief)  ── next intent (structured)
        │                                   │
        │                                   ▼
        │                                 ▣ validates (schema + invariants) → inserts; refusal → rethinks
        └───────────────────────────────────┘
```

## 5. Big picture

- **A single clock `T`** ties everything together: positions, intents, events, cascades.
- **Code holds coherence** (space, time, resources, causality); **the LLM only
  declares and narrates**, on tiny slices.
- **Pre and post are the same engine**: project the world onto the player, then reconcile
  the player into the world.
- **We only pay for detail where a gaze lands**—which makes both tonight's
  session and the return three centuries later sustainable.

→ Next: [`07-implementation-plan.md`](07-implementation-plan.md) — where to start.
