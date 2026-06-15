# 04 — Causal Propagation (wheat, famine, and beyond)

> How an event **causes** others — **elsewhere** (at a distance, via relations) and
> **later** (with a delay). This is what allows "finding the traces" of a tragedy:
> long-term coherence almost **free**, without simulating every detail.

## 1. A second graph: typed relations

The **spatial** graph ([`01`](01-horloge-et-espace.md)) says who is *next to* whom. The
**causal** graph says who *depends on* whom. These are different edges, on the **actors**
([`02`](02-acteurs-et-agents.md)).

```json
{
  "id": "ville:tonnerre",
  "relations": [
    { "vers": "ville:bleville",     "type": "approvisionnement", "bien": "ble", "part": 0.7, "delai_ut": 4320 },
    { "vers": "comte:val-perdu",    "type": "vassalite",         "intensite": 0.8 },
    { "vers": "faction:bande-du-corbeau", "type": "predation",   "intensite": 0.4 }
  ]
}
```

Common edge types (extensible per campaign):

| Type | Meaning | Propagates… |
|---|---|---|
| `approvisionnement` | A receives goods from B | shortage / abundance, after `delai_ut` |
| `vassalite` | A is vassal of B | obligations, requisitions, calls for aid |
| `alliance` / `hostilite` | power relation | entering war, aid, betrayal |
| `route_commerciale` | mutual flow | prosperity / collapse, smuggling |
| `parente` / `rivalite` | personal link (NPC) | revenge, inheritance, loyalty |
| `predation` | A pillages B | raids, flight, fortification |

> **The `delai_ut` is central.** Fields burn at `T`, but famine only strikes after
> **reserves are exhausted**: `delai_ut` encodes this lag. This is **causal
> conservation**: no instantaneous effects at a distance.

## 2. The propagation algorithm (multi-level, bounded)

Decision made: **multi-level cascades from the start**, but **bounded** to avoid
combinatorial explosion.

```
function propagate(evt, depth = 0):
    if depth > MAX_DEPTH:                      return          # safeguard 1
    if evt.significance < THRESHOLD:           return          # safeguard 2: wave dissipates

    for each outgoing relation of evt's node:
        effect = propagation_rule(evt.type, relation)          # DETERMINISTIC: who, what, when
        if effect is null:  continue

        derived_evt = schedule_event(
            target         = relation.vers,
            T              = evt.T + relation.delai_ut,         # later
            type           = effect.type,
            significance   = evt.significance * relation.weight * ATTENUATION,  # safeguard 3
            cause          = evt.id,
            status         = "scheduled"                        # not yet "arrived"
        )
        propagate(derived_evt, depth + 1)                       # bounded recursion
```

- **DETERMINISTIC**: *who* is affected, *when*, *with what intensity* — pure graph traversal.
  A small model doesn't need to remember it: code cannot "forget" a chain.
- **LLM (deferred)**: *how* the target reacts (riot? rationing? call for aid?) — the
  **narrative qualification**, done **only at resolution**, and **only if** it
  becomes observable by the player (lazy generation, [`03`](03-moteur-de-tick.md)).

### Safeguards, explained

| Safeguard | Effect |
|---|---|
| `MAX_DEPTH` (≈ 3–4) | cascade doesn't go infinite |
| `THRESHOLD` of significance | below threshold, wave **dissipates** (a pebble doesn't make a tsunami) |
| `ATTENUATION` (× < 1 per hop) | each relay weakens the effect → **guaranteed termination** |
| budget per source | max number of derived events per root event |
| anti-cycle | strictly decreasing significance prevents infinite loops |

## 3. Scheduled events: cold-zone coherence, free

The cascade doesn't wait for the player: it **writes future dated events** (`status:
"scheduled"`) in [`events.json`](../../data/mygamemaster/campaigns/la-naissance-dun-roi/events.json).
The tick engine **resolves** them when `T` reaches them:

- if the target is **cold** → the event stays a **macro fact** ("Tonnerre experienced a
  famine in the winter of year 1"): no forged detail, but **the trace exists**;
- if the target **becomes warm** (the player approaches it) → we **materialize** the detail (empty
  granaries, lines at the church, bread prices).

This is exactly your requirement: come back later and **find the traces** of an event
you didn't experience — without having to simulate those years continuously.

## 4. Worked example: field fire

```
T = 4000   evt:field-fire @ city:bleville          significance 0.90
           │ (direct cause — a storm, sabotage, doesn't matter)
           │
           ├─ relation  bleville ──approvisionnement(wheat, share .7, delay 4320)──► tonnerre
           ▼
T = 8320   evt:wheat-shortage @ city:tonnerre              significance 0.90·0.7·0.8 ≈ 0.50
           │  (reserves exhausted ~30 days after the fire)
           │  → LLM (at resolution) qualifies: "rationing + price surge"
           │
           ├─ relation  tonnerre ──vassalite(.8)──► comte:val-perdu
           │    ▼
           │  T = 9000  evt:call-for-aid @ comte:val-perdu   ≈ 0.32
           │            → the County requisitions grain elsewhere (new wave, attenuated)
           │
           └─ internal effect  tonnerre → pressure on its dependents
                ▼
              T = 9200  evt:migrant-departure @ city:bourg-de-l-orme   ≈ 0.30
                        (a town living under Tonnerre can't feed itself → it MIGRATES)
                        → creates the TRAJECTORY of migration from file 03 example!
                        → if the player passes through the pass at this T: they ENCOUNTER the column (05 + 03)

T = 9600   significance of following relays < THRESHOLD → wave dissipates.
```

> **Loop closed.** The same cascade starting from a fire produces, three relays down, the
> **migrant column** that preprocessing stages and the player can encounter. Space
> ([`01`](01-horloge-et-espace.md)), actors ([`02`](02-acteurs-et-agents.md)), tick
> ([`03`](03-moteur-de-tick.md)) and causality lock together on **a single timeline `T`**.

## 5. When propagation triggers

- **Post-session** ([`03`](03-moteur-de-tick.md)): each player action with "consequences"
  is a **cause** → we propagate (player burns a bridge → roads cut → trade diverted).
- **During a tick**: any accomplished actor **intention** whose `consequence_expected`
  is significant.
- **Never in open loop**: propagation schedules **future** events, it doesn't
  recalculate the past.

→ Next: [`05-assembleur-de-contexte.md`](05-assembleur-de-contexte.md) — how all this
reaches the GM **without drowning them**.
