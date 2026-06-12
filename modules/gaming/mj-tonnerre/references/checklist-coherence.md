# Coherence Checklist — Full Detail

Detailed reference for the checklist in section 7 of SKILL.md.

## Verification by Category

### Agency
- **READ THE ENTIRE RESPONSE SENTENCE BY SENTENCE** before sending it
- A sentence that starts with `You [action verb]` → **STOP** — action not validated
- A sentence that starts with `You [perception verb]` → ✅ description allowed
- A sentence that starts with `You wonder / you think / you feel that` → ✅ internal state, does not force an action
- **No "and" magic:** ❌ `You inspect and find and slip your hand` → 3 unvalidated actions
- ✅ `You inspect. What do you do?` → 1 action requested, control returned to player

**Strict exceptions (traceable):** Critical failure, Fear 9-10, mental manipulation, activated trauma.

### Campaign and Coherence
- Verify which campaign is active (thread, player, memory)
- Verify world.json, npc.json, sessions/NNN.json
- A dead NPC does not reappear. A burned location stays burned.

### Data and Files
- If info is new → save it FIRST, THEN narrate
- JSON validation after each patch
- Commit: create/modify → validate → commit → continue

### Inventories
- Check each characters/<id>.json
- Say WHO carries what, not "the group has X"
- An object enters inventory only when the player says "I take it"

### Knowledge
- A PC knows only what their sheet says they know
- Do not make a PC react to info only another one knows

### NPC Position
- Check session logs: was the NPC present?
- If not established → ASK, do not invent
- After correction: verify the NPC is not an artifact from the canceled version

### Dice Rolls
- Risky action → roll mandatory
- Perception, persuasion, stealth → roll mandatory
- Do not describe the result before the roll

### Factions and Clock
- Check etat_global.factions: each interaction/clue/change recorded
- Check faction_actions_horloge: advance deadlines during narrative lulls
- If deadline reached → play the consequence

### Cross-check Clock vs Session
⚠️ Narrative verification — not just structural
- For EVERY active action, verify if ITS TRIGGER occurred in the played session
- If yes → was the consequence played? If NO → correct it, play the consequence
- Do NOT confuse "the file is coherent" with "the narration followed the consequences"

### Locations, Distances, Travel
- Every location from sessions in univers.regions[].lieux
- Travel durations in regles.temps.deplacements
- Pace chosen? Fatigue applied? Encounter roll made?
- At least one micro-choice during travel

### Allied NPCs
- Check relation_niveau in npc.json — is the request within their level?
- Check limites.lignes_rouges
- PC actions that affect the relation: note the facts

### Deduction Lock
- No "you're right", no "good deduction"
- Describe ONLY what the character perceives/deduces
- Let players test their hypotheses through action

### Player Turn
- If a player has not reacted → wait
- Do not advance the story without them

### Session Resumption (N+1)
At the start of a new session:
- Load situation_initiale as context only
- **Do NOT infer the PC's exact position** — the player decides where they are
- NEVER invent a "return to the cabin" or "next morning" not validated
- If in doubt: "We had left off with [X]. Where are you now?"

### Error After Technical Interruption
- Do not try to "catch up" on lost time
- Find the LAST decision point of the player
- Re-present it: "We had stopped when [context]. You were [action]. What do you do?"
- NEVER add discoveries, dialogue, or movement not requested