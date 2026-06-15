# 01 — The World's Clock and Spatial Graph (the 4D Model)

> Objective: a representation of space **and** time that reliably answers
> "who is where?", "what is around X?", "where is X at time T?" — **without ever
> asking the LLM to hold the map in its head**.

## 1. The World's Clock: `T`

### Definition

`T` is an **integer ≥ 0**, expressed in **UT** (time unit already present in the project:
1 UT = 10 game minutes, 144 UT = 1 day). `T = 0` is the moment of **campaign creation**.
Time **never moves backward** (monotonicity). Everything — event, position, intention,
consequence — is **timestamped on this single line**.

```
T = 0 ───────────────────────────────────────────────────────────►  T increases
  campaign        S1        S2            S3                  (never backward)
   creation    [─play─]   [──play──]     [─play─]
               t=0..18   t=180..210     t=288..300
                      \________/   \________/
                       ellipsis    ellipsis  (time passing off-scene)
```

### Two Times, Not One

We **explicitly separate**:

- **simulation time** — `T`, quantified, for *calculating* (deadlines, crossings, delays);
- **narrative time** — fuzzy, for *telling* the player ("late afternoon", "three
  days later").

The player never sees `T`. The engine sees only `T`. The conversion `T ↔ day/hour` is already
done by [`outils/gestion_temps.py`](../../data/mygamemaster/campaigns/jusquau-bout-de-mon-monde/outils/gestion_temps.py)
and remains the only bridge between the two.

> **Why quantify.** Trajectory intersections and causal delays require
> numbers. "Late afternoon" does not intersect with "soon". `T` makes these questions
> computable — thus reliable, even with a small model that doesn't do arithmetic itself.

### Scales and Granularity

`T` is continuous, but we **never go below useful granularity**:

| Scale | Simulation Step | Usage |
|---|---|---|
| Intra-session | 1 UT (10 min) | scenes, short movements, encounters |
| Inter-session | hour / day | actor plans, travel, faction deadlines |
| Long jump (season, year) | day / week | long-term goals, weather, harvests |
| Very long jump (decade, century) | year + milestones | dynasties, foundations, ruins → **lazy** generation (see [`03`](03-moteur-de-tick.md)) |

## 2. The Spatial Graph: Three Layers

An LLM has no stable geometric representation: it confabulates positions. **Golden rule:
never ask it to emit coordinates.** Space lives in a **graph with three layers**, each
answering one precise question.

```
  CONTAINMENT ("where is X")          ADJACENCY ("around X")
  climb/descend parents               graph neighbors

  ville:tonnerre                        lieu:…/place-du-marche
   └─ …/quartier-nord                     ├─(S, 60 m)─ lieu:…/eglise
       └─ …/place-du-marche               └─(O, 90 m)─ lieu:…/forge
           └─ …/eglise        ◄───────────────────────────┘
               └─ …/crypte
                  {acteur:cure @ T}    ANCHOR (x,y) → computations (trajectories, radius)
```

### Layer A — Containment (the useful "z" + the "where")

Each location has a **stable `id`** and a **`parent`**. This is the nesting tree. It answers
"where is X?" (climb the parents) and "what is *in* X?" (descend).

- Physical "z" (mountain vs valley, floor, basement) is managed **95%** by containment
  (indoor/outdoor, level) + an optional **`altitude`** scalar. **No true 3D**:
  unnecessary and costly to maintain consistency.

### Layer B — Adjacency (the "around")

**Directed edges** between locations. This is **your `regles.temps.deplacements` matrix
promoted to first-class graph**, enriched with a **cardinal direction** (often
already in your descriptions: "to the west, follow the stream").

"What is around the church?" = `neighbors(lieu:…/eglise)` → outgoing edges + present entities.
**Exact answer, deterministic, zero hallucination.**

### Layer C — Anchor (coordinates, code only)

Each location gets **coarse `(x, y)` coordinates** — non-metric, just coherent.
**You don't have to enter them**: we **derive them from the existing duration matrix** via
*multidimensional scaling* (a 2D placement that best respects all known durations).
These coordinates are **never** seen or produced by the LLM; they serve only
code tools (as-the-crow-flies distance, "who is in a radius", **trajectory
intersections**).

## 3. The 4th Dimension: Position as a Function of Time

An entity's position is **not** a scalar (`current_location: "Cabin"`) but a
**trajectory**: a sequence of segments `(location/point, [t_start, t_end])`. This is what makes
space **4D** and solves the migration example.

```json
{
  "id": "ville:bourg-de-l-orme",
  "trajectoire": [
    { "lieu": "lieu:vallee-est/bourg-de-l-orme", "de": 0,     "a": 41040 },
    { "type": "deplacement", "de": 41040, "a": 41760,
      "chemin": ["lieu:vallee-est/gue", "lieu:plateau-est/col"],
      "motif": "migration — famine after the field fire (evt:incendie-champs)" },
    { "lieu": "lieu:plateau-est/nouveau-bourg", "de": 41760, "a": null }
  ]
}
```

- `"a": null` = "until now / undefined" (current segment).
- "Where is the borough at `T = 41500`?" → the active segment is the **movement** → the tool
  interpolates a position `(x,y)` between `gue` and `col` → the borough is **moving along the
  trajectory**, and a player passing through the col at that moment **meets it**.

## 4. Concrete Data Schemas

### A Location (graph node)

```json
{
  "id": "lieu:tonnerre/place-du-marche/eglise",
  "nom": "Saint-Aubin Church",
  "parent": "lieu:tonnerre/place-du-marche",
  "type": "edifice",
  "altitude": 215,
  "ancrage": { "x": 1240, "y": 880 },
  "aretes": [
    { "vers": "lieu:tonnerre/place-du-marche", "dir": "S", "distance_m": 60, "temps_ut": 1, "voie": "parvis" },
    { "vers": "lieu:tonnerre/presbytere",       "dir": "E", "distance_m": 40, "temps_ut": 1, "voie": "ruelle" }
  ],
  "description_narrative": "A squat nave, vaulted in gray stone; the smell of cold wax."
}
```

> **Where to store it.** Either a `universe.graphe` section in `world.json`, or a dedicated
> `geo.json` file per campaign (recommended: isolates the graph, simplifies validation and
> concurrent writes). To decide in [`07`](07-plan-de-mise-en-oeuvre.md).

### A Mobile Entity (NPC, City, Marching Column…)

The trajectory **replaces** `current_location` (which we can keep as a *derived* field,
computed at current `T` for display backward compatibility).

### Stable Identifiers

Format `type:kebab-path`, hierarchical for locations (reflects containment):

```
lieu:tonnerre/place-du-marche/eglise      acteur:berthe
ville:bourg-de-l-orme                      faction:bande-du-corbeau
evt:incendie-champs-0412                   region:vallee-est
```

**Free names** ("Bertha's Cabin") remain for narration, but **all machine relations**
pass through the `id`. This is what allows a small model to **never** confuse
two locations with the same name (reliable entity resolution).

## 5. The Invariants (the Spatial Validator)

In the spirit of [`validator-distances.py`](../../modules/gaming/mygamemaster/scripts/validator-distances.py),
the code **refuses writes** that would violate a conservation:

1. **Attachment** — every new location has a valid `parent` **and** ≥ 1 edge (no islands).
2. **Reference** — every position/trajectory points to an existing `id`.
3. **Continuity** — a trajectory has no gaps or overlaps; a `deplacement` follows a
   `chemin` of real edges, and its duration ≥ sum of `temps_ut` along the path (**no
   teleportation**).
4. **Monotonicity** — no segment or event timestamps at a `T` below now.
5. **Duration Governance** — the 4 existing rules (fixed durations, indirect ≥ direct,
   go = return, distant point ≥ close point) become graph constraints.

## 6. Query Tools (Deterministic)

A single `geo_query.py` script with subcommands, callable by the GM **and** by the
tick engine. The LLM **queries** and **narrates**; it computes nothing.

| Call | Returns | Answers |
|---|---|---|
| `ou_est <entite> --t T` | location `id` + `(x,y)` (interpolated if moving) | "where is X now?" |
| `qui_est_a <lieu> --t T [--rayon r]` | list of present entities | "who is here?" |
| `voisins <lieu>` | edges + contained locations | "what is around?" |
| `chemin <a> <b>` | edge sequence + total duration | "how to go from A to B, in how much time?" |
| `distance <a> <b> [--vol-d-oiseau]` | meters + UT | sort by proximity |
| `dans_rayon <point> <r> --t T` | locations + entities in radius | spatial context filtering |
| `croisement <trajA> <trajB> --seuil d` | list of `(T, lieu, distance)` | **"does the player cross the migration?"** |

### How the LLM **Declares** a Movement (No Coordinates)

```
# the LLM never writes (x,y). It declares relatively, code computes:
geo_query.py creer_lieu  --nom "Chapelle du col" --depuis lieu:…/col --dir N --distance_m 300
geo_query.py deplacer    --entite ville:bourg-de-l-orme --vers lieu:plateau-est/nouveau-bourg \
                         --depart T=41040 --motif "migration (famine)"
```

The code places the chapel 300 m north of the col (anchor calculation), builds the edge `chemin`
for the migration, infers the duration, writes the trajectory — **and the validator
refuses** if anything breaks a conservation.

## What This Gives, Concretely

- **"Who is in the church?"** → `qui_est_a lieu:…/eglise --t now`: exact.
- **"What is around the church?"** → `voisins lieu:…/eglise`: market square (S),
  presbytery (E), crypt (contained), + present actors: exact.
- **"Does the player cross the migrants?"** → `croisement` between their trajectory and the
  borough's: the engine knows **where** and **when**, and preprocessing sets up the scene
  ([`03`](03-moteur-de-tick.md)).

→ Next: [`02-acteurs-et-agents.md`](02-acteurs-et-agents.md) — who *moves* on this graph, and
why.
