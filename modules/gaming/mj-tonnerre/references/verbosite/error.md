# 🛑 ERROR Level — Blocking issues only

> ℹ️ **The `transform_llm_output` hook manages the "Persisted" block according to `meta.verbosity`.** Blocking issues below remain the responsibility of the GM; format reference = baseline (hook disabled / bypass `⏸️`).

> **Usage:** Radio silence except in crisis. The Steward speaks only if the game is blocked.
> **What is reported:** Actions impossible without GM intervention.
> **What is NOT reported:** Everything else — minor refusals, inconsistencies, warnings.

---

## General format

```
🛑 BLOCKING ISSUE:
<emoji> <description of the blocking issue>
→ Source: <file> → <field> (<line>)
🛠️ GM intervention required: <necessary action>
```

---

## Concrete examples

### Hard line crossed

```
🛑 BLOCKING ISSUE:
🔒 Action refused — Berthe has a hard line "Do not kill innocents".
   → Source: npcs.json → Berthe → limites.lignes_rouges[0]
🛠️ GM intervention required: Explicitly override the hard line
   (with major narrative consequence) or propose an alternative to the player.
```

### NPC unreachable (dead/absent)

```
🛑 BLOCKING ISSUE:
💀 Impossible — Firmin is in "unconscious" state and cannot speak.
   → Source: npcs.json → Firmin → etat_actuel
🛠️ GM intervention required: Heal Firmin first, or decide on a
   healing time-skip, or accept that the information cannot be obtained now.
```

### Impossible timing

```
🛑 BLOCKING ISSUE:
🕒 Action impossible — it is pitch dark (midnight, Day 7) and Rubis has no
   light source to read the journal.
   → Source: world.json > rules.meteo.conditions_actuelles + Rubis inventory
🛠️ GM intervention required: Provide a light source (torch, campfire,
   full moon) or defer the reading to morning.
```

### Corrupted / inaccessible file

```
🛑 BLOCKING ISSUE:
📝 Data inaccessible — personnages/100000000000000001.json is corrupted
   or locked. Cannot verify inventory.
   → Source: personnages/100000000000000001.json — JSON parsing error
🛠️ GM intervention required: Restore the file from git, or rebuild
   the character sheet manually. The session cannot continue without it.
```

### Incoherent game state

```
🛑 BLOCKING ISSUE:
📝 Critical inconsistency — sessions/008.json has empty heure_fin, but sessions/009.json
   already exists with heure_debut populated. Two "active" sessions detected.
   → Source: sessions/008.json (no heure_fin), sessions/009.json (heure_debut populated)
🛠️ GM intervention required: Determine which session is the actual session.
   Manually close the other one.
```

---

## ERROR-specific rules

1. **Blocking issue = the game cannot continue without intervention** — no automatic workaround
2. **Always include a 🛠️ section** — the required GM action is explicit
3. **One ERROR at a time** — if multiple blocking issues, handle them sequentially
4. **No "soft" suggestions** — in ERROR, we don't suggest, we demand intervention
5. **Simple refusals (inventory, knowledge) are NOT ERROR** — they are handled in WARN. ERROR = the game is STOPPED
