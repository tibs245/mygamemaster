# Narrative Trap — Unverified NPC Knowledge

## Problem

The GM improvises dialogue for an NPC and attributes knowledge of a location or artifact that contradicts the established facts in the files.

## Real Example (S7, "The Birth of a King")

I had **Firmin** say:
  > "I remember the first time I went down — it [the statuette] froze me in place, twenty years ago."

**Problem:** The files established that Firmin never visited the blue chamber before the PC opened the slab (S4).
He fell asleep ON the outer slab and woke up INSIDE.

## Pre-narration Checklist

Before having an NPC speak about a location/artifact from their past:

1. [ ] Has the NPC already visited this location?
   → Check `npcs.json > established_facts` + `sessions/NNN.json`
2. [ ] Did the artifact exist at that time?
   → Check `world.json > artefacts_connus`
3. [ ] Would the NPC have had a reason not to mention it before?
4. [ ] Does the attributed knowledge contradict an established fact or hypothesis?
5. [ ] Can it be rephrased to avoid the inconsistency?

## Rule

If an NPC claims to have visited a location or known an artifact before the PC discovers it, verify in the files that this knowledge is compatible with the established facts.

**In case of doubt:** keep a vague phrasing ("Perhaps. It seems to me.") rather than a precise one ("I went down").