# NPC Data Governance — Established Facts vs GM Hypotheses

## Context

A recurring NPC (2+ sessions or ally/companion) must have a structured record in `npcs.json` — not just informal GM notes. The classic mistake is writing a personal deduction as if it were an established fact.

## Mandatory NPC Record Structure

```json
{
  "nom": "Prénom",
  "titre": "Rôle / Fonction",
  "premiere_rencontre": "Session X — Lieu",
  "description": "1-2 descriptive sentences (physical appearance, general demeanor). Contain ONLY what was seen/played.",
  "attitude": "Ally | Wary | Neutral | Hostile",
  "relation_niveau": "Unknown | Acquaintance | Ally | Friend | Close | Wary | Hostile | Enemy",
  "localisation_actuelle": "Where the NPC is currently located",
  "established_facts": [
    "What the NPC said or did verbatim in play (traceable to session logs)",
    "Example: 'Identified tracks: 2 people, at night, heading north (played S2)'",
    "Example: 'Knows that [world element] (stated S1)'"
  ],
  "hypotheses_mj": [
    "My deductions/assumptions — I CANNOT use them in narration without validating them in play",
    "Example: 'Perhaps knows [a world secret] better than shown — needs testing'"
  ],
  "stats": {
    "force": 10, "dexterite": 10, "constitution": 10,
    "intelligence": 10, "sagesse": 10, "charisme": 10
  },
  "modificateurs": {
    "force": 0, "dexterite": 0, "constitution": 0,
    "intelligence": 0, "sagesse": 0, "charisme": 0
  },
  "competences_observees": {
    "Survival": {"stat": "Wisdom", "bonus": 3, "maitrise": true},
    "Perception": {"stat": "Wisdom", "bonus": 3, "maitrise": true}
  },
  "limites": {
    "lignes_rouges": [
      "Does not kill innocents — for any reason",
      "Does not abandon their own without guarantee of return"
    ],
    "peurs": [],
    "motivations_personnelles": [
      "Wants to protect their home"
    ]
  },
  "objets_connus": {},
  "derniere_interaction": "Session X — context"
}
```

## Absolute Rules

1. **established_facts** contains ONLY what was played or stated verbatim. Format: `"action/revelation (played S{N})"`. Each fact must be traceable to a session.
2. **hypotheses_mj** contains my speculations. Marked as such. I CANNOT use them in narration as facts. To validate: test them in play.
3. **Stats** defined consistent with the presented character. If the NPC has not shown a skill, stat = 10 without proficiency.
4. **Observed skills**: only those shown in play. An unshown skill = not proficient.
5. **When to add a recurring NPC**: from their 2nd session or if they become an ally/companion.

## Trap — Mixed Notes

❌ `"notes_mj": ["Knows the secret history of the place"]` — presented as fact, this is a deduction

✅ `"established_facts": ["Said that [observable detail] (played S2)"]`
✅ `"hypotheses_mj": ["Perhaps knows the secret history of the place better than shown — needs testing in play"]`

## Quick Test

Before using NPC information in narration:
- Is the fact in `established_facts`? -> ✅ usable
- In `hypotheses_mj`? -> ❌ do not use, test first in play
- Nowhere? -> ❌ do not use, this is pure invention