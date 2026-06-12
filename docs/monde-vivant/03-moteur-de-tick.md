# 03 — The tick engine (LOD, pre-processing, post-processing)

> The **heartbeat** of the world. It advances actor plans, applies consequences deterministically,
> calls the LLM only at *seams*, emits timestamped events, and triggers causal cascades. Invoked
> in **two ways**: in **projection** (before the session) and in **reconciliation** (after).

## 1. The LOD: simulating at the right granularity

You had intuited it ("the distant, we take a shortcut"). We refine it: the distant is not
*frozen*, it advances in **coarse abstract steps**. Three zones, defined by **spatio-temporal
distance to the player**.

```
 HOT    ── the player is here, now
         → fine simulation, narrative, turn-by-turn     (what the GM already does)

 WARM   ── can cross the player in the session window (nearby space OR nearby deadline)
         → intentions resolved into concrete TIMESTAMPED EVENTS; detail generated just-in-time
         → TARGET of pre-processing

 COLD   ── far in space AND time
         → we advance ONLY clocks (long-term goals), in coarse steps, 0 LLM
         → detail is forged only if the player approaches it (lazy generation)
```

**Decisive economic principle:** *we never simulate in detail what no one will observe.*
If the player returns in 10 years, we don't calculate day-by-day: we keep a few **consistent
macro facts** (famine in year 3 → migration → new lord) that we **materialize in a single jump**
the moment a gaze falls upon them.

## 2. The tick algorithm

```
function tick(T_from, T_to, player_context):
    for each actor:
        zone = classify_LOD(actor, player_context)        # hot | warm | cold

        if zone == cold:
            advance_abstract_clock(actor, T_to)            # deterministic — NO LLM calls
            continue

        # --- warm or hot: resolve due intentions ---
        for each intention in actor.plan where status=planned and deadline <= T_to:
            if preconditions_met(intention, T_to):
                apply_consequence(intention)               # Extended Steward (resources/position/relations)
                evt = emit_event(intention, T)             # → events.json
                propagate_causality(evt)                   # → file 04 (bounded)
                intention.status = "accomplished"
            else:
                intention.status = "failed"                # or postponed if deadline allows

        # --- should the actor "think" about what comes next? ---
        if plan_empty(actor) or goal_reached(actor) or recent_shock(actor):
            brief     = build_brief(actor, recent_events_concerning_them)
            intention = agent_decide(actor, brief)        # Structured LLM — AT MOST 1 call
            validate_and_insert(intention)                # schema + invariants; refusal → rethink
```

`classify_LOD` combines **spatial distance** (`geo_query.py distance`) and **temporal imminence**
(deadline near `T_to`). An actor far away but whose deadline falls during the session remains
**warm** (their action can produce an event the player will encounter).

### Lazy generation

A **cold** place/actor remains in **summary** state (a few macro facts). We **materialize**
their detail (named NPCs, sub-locations, inventories) only the moment they **become warm**. This
is what makes **long jumps** tenable: we only pay for detail where the player looks.

## 3. Pre-processing = projection + staging

Before the player plays, we **project** the plans onto them and **stage** what they can
encounter.

```
function pre_session(player, T_session):
    cone = cone_probable_destinations(player)              # where they risk going (places + T window)
    tick(T_last, T_session, context={cone})               # the world catches up to elapsed time

    crossings = []
    for each warm actor:
        crossings += geo_query.crossing(traj(cone), traj(actor), threshold)

    for each significant crossing:
        promote(actor, "hot")                              # just-in-time detail generation
        materialize_scene(crossing)                        # e.g.: the migrant column, here, at T

    return assemble_briefing(crossings, player_zone)      # → file 05
```

This is where **"the village migrates east; if the player crosses the trajectory, they see them"**
is resolved: the `crossing` is **calculated**, not guessed. The briefing tells the GM: *"about
2 hours' walk northeast, a column of roughly thirty inhabitants of Bourg-de-l'Orme heads toward
the pass; they flee a famine; you can encounter them if the player takes the pass road."*

## 4. Post-processing = reconciliation

After the session, we have what the player **actually** did (`sessions/NNN.json` + Steward ledger).
We **confront** the planned against the real.

```
function post_session(session_log, ledger):
    facts = extract_player_facts(session_log, ledger)     # what REALLY happened

    for each actor affected by facts:
        reconcile_state(actor, facts)                      # actual position/resources/relations
        if plan_disturbed(actor):                          # blocked / diverted / accelerated / ignored
            renew_plan(actor)                              # Structured LLM (short goal → new)

    for each player_action with consequences:
        propagate_causality(player_action)                 # file 04 — player becomes a cause

    write_sheets_and_chronology()                          # actor sheets + events.json up-to-date
```

Examples of reconciliation:

| The player… | Effect on the actor's plan |
|---|---|
| aided the migration (escort) | migration **accelerated**, losses avoided → relation +, new goal (settle) |
| attacked the column | migration **scattered** → survivors, hostility, rumor, possible vengeance |
| ignored / didn't encounter | plan **unchanged**, executed as-is by the tick — column arrives alone at the pass |

**Pre = project intentions onto the player. Post = reconcile reality and restart.** Both
are the **same engine**, with different inputs.

## 5. Cadence: A now, B next

### Cadence A — at session boundaries (chosen to start)

```
   !resume / open     ─►  pre_session()   ─►  briefing to GM
        … the session plays (the GM is in hot zone) …
   !wrap-up / close_session ─►  post_session()  ─►  sheets + chronology + renewed plans
```

Concrete hooks in the existing system:
- **Open**: the skill [`mj-tonnerre-session`](../../modules/gaming/mj-tonnerre-session/SKILL.md)
  calls `world_tick.py pre`.
- **Wrap-up**: [`close_session.py`](../../modules/gaming/mj-tonnerre/scripts/close_session.py)
  adds a `world_tick.py post` step to its pipeline.

Cost: **zero tokens outside session**. Simple, predictable, sufficient to validate the entire system.

### Cadence B — selective background (evolution)

Later, a **timer** (Quadlet/cron, in the spirit of the project's systemd permanence) ticks the
world even without a player — but **only** actors whose **impact score** exceeds a threshold:

```
impact_score(actor) =  w1·spatial_proximity(actor, player)
                    +  w2·deadline_imminence(actor)
                    +  w3·consequence_scope(actor)
                    +  w4·causal_links_toward(player)
```

Actors below the threshold remain **cold** (pure deterministic). We only "burn" LLM in the
background where it **will change what the player experiences**. This is the natural evolution of A,
without breaking anything: the engine is the same, only the **trigger** and **selection** change.

## 6. Long jumps (return a week / year / three centuries later)

When `T_to − T_from` is large, the tick **does not traverse** each UT:

1. **Jump to milestones**: plan deadlines, scheduled events ([`04`](04-propagation-causale.md)),
   season/harvest changes.
2. **Aggregate** by increasing scale (day → week → year → decade): the farther, the coarser.
3. **Generate lazily** detail only for the zone where the player reappears.

Result: returning "three centuries later" costs **a handful of consistent macro milestones**,
forged in a single jump, not three centuries of simulation.

## 7. Anti-drift guardrails

The more we simulate autonomously, the greater the risk of cumulative incoherence. Four safeguards:

1. **Extended Steward** — no conservation (resources/space/time) is violated.
2. **Coherence Judge** ([`llm_judge.py`](../../modules/gaming/mj-tonnerre/hooks/llm_judge.py))
   on events **generated** by the tick (plausibility, scale, rhythm).
3. **Bounding** of propagation ([`04`](04-propagation-causale.md)): depth, significance threshold,
   attenuation.
4. **Deterministic dominates** — the LLM proposes at seams; it never controls the state.

→ Next: [`04-propagation-causale.md`](04-propagation-causale.md) — how an event **causes**
others, elsewhere and later.
