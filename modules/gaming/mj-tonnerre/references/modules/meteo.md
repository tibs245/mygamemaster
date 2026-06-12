# Module — Weather and Biodiversity

> **Conditional loading.** This module applies only if the campaign declares `world.json > modules.meteo.actif === true`.
>
> **Regional data (climate, conditions, fauna, flora) are GAMEPLAY** : they live in `world.json > rules.meteo` and `world.json > universe.regions[].biodiversite`. This module describes only the generic framework and consistency rules — never the values of a specific campaign.

## Principle

Weather and biodiversity give a **sensory and practical texture** to the world. They are not mere decoration — they affect travel, resources, visibility, and the credibility of the territory.

| | Definition | Scale | When |
|---|---|---|---|
| **🌤️ Weather** | Climate, season, conditions of the day | Region | Determined in advance (season + trend). Then improvised by session or game day |
| **🌿 Biodiversity** | Fauna, flora, natural resources | Region (areas) + Location (rare/specific) | Created as play progresses, but **recorded immediately** to guarantee consistency |

## Weather — Data Structure (in `world.json > rules.meteo`)

```json
{
  "rules": {
    "meteo": {
      "saison_actuelle": "[Season + phase, ex: Autumn (early)]",
      "tendance": "[Expected evolution, ex: gradual cooling]",
      "regions": {
        "[Region name]": {
          "climat": "[Climate type — summers/winters]",
          "conditions_typiques": [
            "[Conditions by season]"
          ],
          "conditions_actuelles": "[Current weather]",
          "prochain_changement": "[Upcoming evolution]"
        }
      }
    }
  }
}
```

**What weather concretely impacts:**
- Travel : waterlogged terrain → duration +25%, swollen river → ford impassable *(if the travel module is active)*
- Visibility : fog → reduced perception, unexpected encounters
- Resources : game hides in rain, mushrooms after autumn rains
- Comfort : night without shelter in rain → fatigue +1

## Biodiversity — Data Structure (in `world.json > universe.regions[].biodiversite`)

```json
{
  "univers": {
    "regions": [
      {
        "nom": "[Region name]",
        "biodiversite": {
          "flore_commune": ["..."],
          "faune_commune": ["..."],
          "ressources": ["..."],
          "especes_rares_liees": [
            {"nom": "[Rare species]", "lieu": "[Precise location]", "note": "[Why rare]"}
          ]
        }
      }
    ]
  }
}
```

## Consistency Rules

1. **Progressive addition** — don't invent *all* biodiversity at creation. Add as play progresses, when the PC interacts with the environment (hunting, gathering, observation). But **record immediately**.
2. **Climate consistency** — a tundra animal does not appear in a temperate forest. If a PC encounters an unexpected creature, it must have an explanation (migration, magic, disturbance).
3. **Real seasons** — fauna and flora change with the season. What is available in autumn (chestnuts, mushrooms) is not available in winter.
4. **Documented rarity** — a rare species or unique material is tied to a **precise location**, not an entire region. That gives a reason to explore.
5. **No empty catalog** — an unexplored region without documented biodiversity ✅ (normal — it will be filled when the PCs go there).
