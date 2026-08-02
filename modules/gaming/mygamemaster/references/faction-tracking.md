# Faction Tracking — JSON Templates (factions module details)

> **Technical details of the `factions` module** (loaded if `world.json > modules.factions.actif`). The **golden rules** of factions are defined once in `references/modules/factions.md`; this file does not duplicate them, but provides the **complete JSON templates** and structural details. Summary of the 4 golden rules below for reference:

1. Each faction always has ≥ 1 short-term objective and ≥ 1 long-term objective.
2. Objectives are INDEPENDENT of PCs.
3. Automatic renewal of a short-term objective that is achieved/countered/supplanted.
4. PCs can influence but not cancel — a countered action transforms.

*(Details and examples: `references/modules/factions.md`.)*

## Structure in `world.json`

### `global_state.factions` (dynamic tracking)

Each faction MUST have the following fields (required):

```json
{
  "name": "Faction Name",
  "importance": "🔘 Discrete | 🔵 Local | 🟣 Regional | ⚪ Major — narrative explanation",
  "attitude_actuelle": "Unknown | Neutral | Observant | Hostile | Friendly | Allied",
  "derniere_interaction": "Session X — summary context",
  "indices_observes": [
    "Specific action or clue (played S{X})",
    "Other clue (played S{Y})"
  ],
  "relations_inter_factions": {
    "OtherFaction": "Alliance | Truce | Hostility | Domination | Competition | Distrust | Neutral | Vassalage",
    "OtherFaction2": "..."
  },
  "short_term_goals": "What it does NOW — independent of PCs. Ex: « Stockpile provisions before winter », not « Observe the character's arrival »",
  "long_term_goals": "Its true long-term ambition. Ex: « Remain the undisputed master of the region »",
  "notes_mj": "Hidden info, real motivations, ongoing plans — including diplomatic intentions toward other factions"
}
```

**Interfaction relations:** Factions have ties with each other (alliances, hostilities, dependencies) which can be:
- **Direct** (known to all) — ex: « [A faction] maintains an informant network in [a region] »
- **Hidden** (GM secrets) — ex: « [A faction leader] shares a past with [another faction], they have scores to settle »
- **Emerging** (created by PC or faction actions) — ex: « After [a PC] fought [a faction], [another] offers its support »

These relationships evolve over time independently of PCs. Diplomatic intentions (sending an emissary, proposing an alliance, declaring war) are stored in `notes_mj` or in `faction_actions_horloge` if a deadline is involved.

### `global_state.faction_actions_horloge` (proactive actions with deadlines)

This section is the heart of the **time pressure** in the world. Each faction does not remain static — it actively pursues its objectives. If PCs do not act within the timeframe, the world moves without them.

Complete structure (with integrated governance):

```json
{
  "gouvernance": {
    "rules": [
      "Each faction ALWAYS has at least 1 short-term action (deadline ≤ 7 days) and 1 long-term action (deadline ≥ 14 days) in its actions_en_cours",
      "Objectives (short and long term in the 'factions' section) are INDEPENDENT of PCs — they exist and evolve even if PCs never intervene",
      "When a short-term objective is achieved, surpassed, or supplanted → renew it immediately with a new objective, consistent with the long term and recent events",
      "PCs can encounter these actions (suffer them, observe them, influence them) but NOT cancel them — an action that becomes impossible transforms, it does not disappear",
      "If a PC radically changes the course of an action (ex: eliminates a faction leader) → the objective remains but the method changes (succession, faction split, power vacuum)"
    ],
    "renouvellement": "At each session, before starting: check each faction. If its short-term objective is moot (achieved, impossible, overtaken by events) → replace it. The history of past objectives is kept in session logs."
  },
  "actions": [
    {
      "faction": "Faction Name",
      "actions_en_cours": [
        {
          "action": "Clear action title",
          "declencheur": "What triggered this action (played S{N} if applicable)",
          "echeance": "When it happens — in game time (Day X, or « in N days », or « in N hours »)",
          "consequence": "What happens if the deadline is reached without intervention",
          "facteurs_modificateurs": [
            "PC condition → consequence",
            "Other condition → other consequence"
          ],
          "visible_par_pj": "☑️ if PCs can detect this action, ✖️ otherwise, followed by a narrative explanation"
        }
      ]
    }
  ]
}
```

#### Clock Rules

1. **The deadline is a hard date, not a suggestion.** It only moves if PCs actively intervene via a `facteur_modificateur`.
2. **Short term vs long term:** Each faction always has ≥ 1 short-term action (deadline ≤ 7 days) and ≥ 1 long-term action (deadline ≥ 14 days) in its `actions_en_cours`.
3. **Objectives independent of PCs:** Faction actions and objectives exist and evolve even if PCs never intervene — the faction has its own needs.
4. **Automatic renewal:** When a short-term objective is achieved, countered, or supplanted → replace it immediately with a new objective consistent with the long term and recent events.
5. **PCs transform, they do not cancel:** A faction countered by PCs does not disappear — it changes method (succession, split, forced alliance).
6. **One action can lead to another.** When a deadline is reached, the `consequence` can create a new entry in `actions_en_cours` (ex: scout report → intimidation raid).
7. **Modifying factors are explicit levers for PCs.** They must be concrete and actionable, not vague (« if the PC makes a good impression » → too vague — prefer « if the PC negotiates with or impresses the faction leader »).
8. **The `visible_par_pj` guides narration.** An invisible action (✖️) only manifests through its consequences — but PCs can discover it through investigation (intercepting a messenger, observing traces, hearsay).
9. **At each narrative downtime (nightfall, travel, scene transition), advance the clock.** Check which deadlines are reached or approaching.

#### When to Add / Remove Actions

- **Add:** when a faction must act (trigger identified → action created in progress)
- **Remove:** when the action has occurred (its consequence has taken place) → archived in the faction's `history` field
- **Modify:** when a `facteur_modificateur` is activated → update the deadline or cancel the action

### `global_state.pistes_non_assignees` (unlinked clues)

```json
{
  "indice_1": "Clue description (played S{X}) — hypotheses about the faction",
  "indice_2": "Description (played S{Y}) — other hypothesis"
}
```

## Rules — Overview

1. **`universe.factions`** = lore (initial description, does not change)
2. **`global_state.factions`** = dynamic tracking (what happens in game, changes with each interaction)
3. **Each faction always has ≥ 1 short-term objective AND ≥ 1 long-term objective** — mandatory, even without PC interaction
4. **Objectives independent of PCs** — never define a short-term objective as « Observe the character's arrival »
5. **Interfaction relations** — each faction has links (direct or hidden) with others, stored in `relations_inter_factions`
6. **Interfaction relations evolve** — alliances, betrayals, conflicts independent of PCs, to be updated in the clock
7. **`global_state.faction_actions_horloge`** = proactive actions with deadlines (the world moves without PCs)
8. **Automatic renewal** — when a short-term objective becomes moot, replace it immediately
9. **`pistes_non_assignees`** = clues where we don't yet know which faction produced them
10. When a clue is confirmed → move it from `pistes_non_assignees` to the concerned faction
11. When a faction interacts → update `attitude_actuelle` and `derniere_interaction`
12. When a clock deadline is reached → play the consequence + update `global_state.factions` if needed

## When to Create an Entry

- At the first observable trace of a faction in play
- If a faction defined in `universe.factions` does not yet have an entry in `global_state.factions` → that is normal, it has not interacted
- As soon as a narrative trigger justifies a faction acting → create an entry in `faction_actions_horloge`

## Concrete Clock Example (Generic)

Example of a bandit faction — **objectives independent of PCs**:

```json
{
  "gouvernance": {
    "rules": [
      "Each faction ALWAYS has at least 1 short-term action and 1 long-term action",
      "Objectives are INDEPENDENT of PCs"
    ],
    "renouvellement": "To check at each session start"
  },
  "actions": [
    {
      "faction": "[Bandit Faction]",
      "short_term_goals": "Stockpile provisions before winter — ransom travelers at the passage point",
      "long_term_goals": "Remain undisputed masters of the region — control the passages",
      "actions_en_cours": [
        {
          "action": "Scout report and deliberation at camp",
          "declencheur": "Scouts spot unusual activity south of their hunting ground (played S2)",
          "echeance": "Day 4, late morning",
          "consequence": "[The leader] learns of strangers in the region. Decision to make: observe, embassy, or raid.",
          "facteurs_modificateurs": [
            "If PCs follow the traces and catch the scouts → [the leader] knows nothing",
            "If PCs take a different direction → approximate report"
          ],
          "visible_par_pj": "☑️ — Fresh tracks to the north"
        }
      ]
    }
  ]
}
```