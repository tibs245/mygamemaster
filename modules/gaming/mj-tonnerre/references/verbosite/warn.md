# ⚠️ WARN Level — Alerts only

> ℹ️ **The `transform_llm_output` hook manages the "Persisted" block according to `meta.verbosity`.** The alerts/REFUSALS below remain the responsibility of the GM; format reference = net (hook disabled / bypass `⏸️`).

> **Usage:** Smooth gameplay — the Steward (Banker) only speaks when there is a problem.
> **What is reported:** Only Controls that fail (REFUSAL, inconsistency, missing value).
> **What is NOT reported:** Successes, validations, normal operations.

---

## General format

```
⚠️ Attention:
<emoji> <description of the problem>
💡 Suggestion: <corrective action>
```

---

## Concrete examples

### Missing NPC knowledge

```
⚠️ Attention:
💬 Firmin said he knows the Temple of the Markers, but this knowledge
   is not in established_facts[] nor in connaissances_privees.
   → Source: npcs.json → Firmin → 17 entries scanned, no match.
💡 Suggestion: If Firmin should know this, add the knowledge in npcs.json
   before continuing. Otherwise, have him say "I don't know this temple".
```

### Undocumented travel route

```
⚠️ Attention:
🗺️ The route "Valley of the Heart → Berthe's Cabin in 30min" is not documented
   in rules.temps.movements.
   → Closest known path: Beech Path (2h50).
💡 Suggestion: Add this route in world.json > rules.temps.movements,
   or use the Beech Path (2h50) which is already documented.
```

### Non-existent item

```
⚠️ Attention:
🎒 Rubis is trying to use a "healing potion" but his inventory doesn't contain one.
   → Source: personnages/100000000000000001.json → inventaire[] — "potion" not found.
💡 Suggestion: Check if the potion was consumed during a previous session,
   or if it is in another character's inventory.
```

### Red line approached

```
⚠️ Attention:
🔒 Action close to a red line. Berthe's limit is: "Do not kill the innocent."
   The proposed action could be interpreted as a threat.
💡 Suggestion: Clarify the player's intention before continuing.
```

### Contradictory weather

```
⚠️ Attention:
☀️ The narration mentions rain, but rules.meteo indicates "clear sky, summer".
   → Source: world.json > rules.meteo.conditions_actuelles — "clear sky" (D7).
💡 Suggestion: Update rules.meteo.conditions_actuelles to reflect rain,
   or correct the narration.
```

---

## WARN-specific rules

1. **Never report successes** — only problems are reported
2. **Always include a suggestion** — WARN is not just a statement, it guides
3. **Always cite the source** — file + field, so the GM can correct it
4. **One alert = one problem** — do not group multiple problems into a single WARN
