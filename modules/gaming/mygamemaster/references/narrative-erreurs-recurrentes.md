# 🔁 Recurring narrative errors — Session 6 (Birth of a King)

> Quick scannable reference before each narrative response.  
> Each entry documents an error MADE, its correction, and the underlying principle.

---

## 1. Duration "20 years" attached to the wrong verb

| Wrong version | Corrected version |
|---|---|
| *"Firmin slept for twenty years on the slab"* | *"Firmin spent twenty years maintaining the seals"* |
| *"the one beneath which Firmin slept for twenty years"* | *"the one where he sat after twenty years of vigil"* |

**Principle:** "20 years" is a real documented data point. The trap is attaching a false verb (sleep, solitude) instead of the true verb (maintain, keep vigil). **Always verify the verb before using the duration.**

---

## 2. Excessive possessive — assigning authority the PC does not have

| Wrong version | Corrected version |
|---|---|
| *"it's your cabin, your people, your March"* | *"Berthe looks at you — not because it belongs to you, but because you are the initiator"* |

**Principle:** Berthe owns the cabin. She is an ally, not a follower. Rousset has competing allegiance (to Corneille). The March belongs to no one. **A possessive implies a property/authority relationship that does not exist in the files.** Replace with descriptions of actual role.

---

## 3. NPC relationship crushed by PC spotlight

| Wrong version | Corrected version |
|---|---|
| *"it's you who knows Firmin"* | *"Berthe has known Firmin for years — you awoke him and received his confidences"* |

**Principle:** Giving importance to the PC must never come at the expense of documented NPC-to-NPC relationships. **Check `npcs.json > established_facts` for relationships before assigning primacy to the PC.**

---

## 4. Poorly calibrated temporality — distance between events

| Wrong version | Corrected version |
|---|---|
| *"for a few months, a stranger has been cleaning them"* | *"for a few days, a stranger has been cleaning them"* |

**Principle:** The timeline of Rubis in the March is **~6 game days**. Every time reference in NPC dialogue must be consistent with this timeline. **Read `world.json > global_state.chronologie` before writing a duration indication in dialogue.**

---

## 5. Incorrectly positioned object — inventory/location reversed

| Wrong version | Corrected version |
|---|---|
| *"Firmin sits by the window, **the journal open on his knees**"* | *"Firmin sits by the window, **hands empty** — the journal is beside you, on your pallet"* |

**Principle:** The journal was given by Firmin to Rubis the previous day ("I entrust it to you"). **Always verify object ownership in the PC or NPC inventory before describing it.** (See `characters/<id>.json > inventaire`)

---

## 6. Post-wrap-up — data not propagated

Systematic oversights observed after Session 6 wrap-up:

| Oversight | Correction |
|---|---|
| NPC positions not updated | Berthe (Stone House → Cabin), Drageon (same → En route), Firmin (Departed → Heart) |
| New NPCs not filed | Esterlin + Karel missing from `npcs.json` |
| New artifacts not listed | Heart-of-Shards missing from `artefacts_connus` |
| Rations not deducted | Shared with 8 people → deduct 2-3 days of rations |
| Timeline not enriched | Session 6 missing from `global_state.chronologie` |
| Locations not added | Beech Path missing from `universe.regions[].lieux` |
| Cabin activities not persisted | Turnips harvested, shed advanced — not in Berthe's file |

**Principle:** Files do not update themselves. Every RP data point (object used, NPC moved, location discovered, time elapsed) must be **written to the files in the same response** that reveals it. Not at session end. Not at wrap-up. Immediately.
