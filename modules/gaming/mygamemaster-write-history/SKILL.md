---
name: mygamemaster-write-history
description: Generates a narrative session summary — novel/book style, no game mechanics at all. Read like a history chapter. No spoilers.
category: gaming
triggers:
  - "!write-history"
  - "session narrative"
  - "narrative summary"
  - "history"
  - "chapter"
---

# 📖 MJ Tonnerre — !write-history

> **Do not confuse:** `write-history` = novelized narrative ≠ `game-report` (raw facts, zero spoilers) ≠ the « Session Summary » header card (Discord wrap-up card).

> **Narrative session summary.** Written as a novel chapter.
> No stats, no dice, no mechanics. Just the story.
> Third person perspective. The PC is the main character.

## 1. Golden Rule — The Story Only

This narrative is **pure** — it contains no game mechanics at all:

| ✅ Allowed | ❌ Forbidden |
|---|---|
| « [the PC] descended into the blue room. » | « [the PC] made a Perception check DC 15. » |
| « [NPC] spoke in a low, weary voice. » | « [NPC] has 17 Wisdom and +5 Knowledge. » |
| « The air was heavy, charged with an ancient presence. » | « The blue room is located at coordinate X:Y. » |
| « — Where do we start? asked [NPC]. » | « The GM announces a new quest. » |

**The player must be able to read this text without ever being pulled out of the story.**

---

## 2. Writing Style

### Narrative Voice
- **Third person** (« [the PC] did… », « He felt… »)
- **Simple past** for actions (« He advanced », « The stone slab opened »)
- **Imperfect tense** for descriptions (« The path wound between the beeches »)
- **Tone**: that of the campaign (defined in `world.json > meta.tone`)

### Length
- 1 to 2 paragraphs per key scene
- 3 to 5 scenes per typical session
- Total of ~300-800 words

### Structure
```markdown
# {Chapter Title}

{Subtitle or hook — one sentence that sets the tone}

{Scene 1 — description + action + key dialogue}

{Scene 2 — transition + action + dialogue}

...

{Cliffhanger — end of chapter, often an open question or decision}
```

---

## 3. Output Format

The narrative is generated in `sessions/NNN-narrative.md`.

### Style Example (excerpt — Campaign X)

```markdown
# Chapter {N} — {Title}

*{One-sentence hook that sets the tone.}*

---

{Location} was calm that day. The men of {NPC} stood in a circle,
their gazes alternating between the unknown and the guide. {NPC}, weary yet
present, listened more than he spoke.

It was {NPC} who broke the silence first.
— {Striking question, in direct speech} ?

{PC} answered, and his answer carried further than words. {Brief description
of the effect on others: an uncrossed arm, a silence.}

---

Later, {PC} closed his eyes. When he opened them again, he knew where to go.
{Decision/direction played.}

---

On the path, as the sun declined, {NPC} slowed and asked:
— Where do we start?
```

> Keep ~300-800 words, 3-5 scenes. The excerpt above shows the tone (simple past, dialogue in direct speech, open cliffhanger) — adapt it to the actual facts of the session.

---

## 4. Generation Rules

### Sources

The narrative is built from:
- `sessions/NNN.json > actions[]` — the actions played
- `sessions/NNN.json > summary` — the session summary (if already written)
- `sessions/NNN.json > teaser` — the closing hook
- `world.json > meta.tone` — the campaign tone
- **GM knowledge** — what happened, the atmosphere, the dialogues

### Write It YOURSELF, From the Facts Played

Write the narrative **yourself**, grounded in the session logs.
Do not delegate, do not generate generic text: capture the **real tone**
of the campaign (`world.json > meta.tone`) and the **facts actually played**.

Start from the actions logged in the session, then enrich with:
- Atmosphere descriptions (weather, light, smells)
- NPC gestures (a look, a silence, a gesture)
- Key dialogues (verbatim, if you remember them)
- Scene transitions

**What you do NOT add:**
- ❌ Events that did not happen
- ❌ NPC thoughts the PC does not know
- ❌ Rule or mechanic explanations
- ❌ Future plot elements not revealed

---

## 5. Narrative Quality

### Checklist Before Publishing

- [ ] The narrative reads like a novel, not a report
- [ ] No game mechanics (stats, dice, DCs, levels)
- [ ] Third person, simple past/imperfect tense
- [ ] Dialogues are present if striking
- [ ] Atmosphere is described (weather, light, sensations)
- [ ] No spoilers — nothing the PC doesn't know
- [ ] The cliffhanger leaves a door open

### Common Pitfalls

| ❌ Avoid | ✅ Instead |
|---|---|
| « [the PC] succeeded on his Persuasion check against [NPC] » | « [the PC] spoke, and [NPC] listened. » |
| « The DC was 15 » | « It was not a sure thing. » |
| « The GM announces that winter arrives in 2 months » | « Autumn advanced, bringing with it the promise of frost. » |
| « [the PC] gains 0 XP » | (Nothing — XP does not exist in the story) |

---

## 6. Integration with !wrap-up

`!wrap-up` calls `!write-history` as the third step, after
`!analyse-bug` and `!game-report`.

The player can also launch `!write-history` at any time to get
a mid-session narrative.

---

## References

- `mygamemaster/SKILL.md` — GM Persona, narrative style
- `world.json > meta.tone` — Campaign tone (guides the style)
- `sessions/NNN.json` — Source of actions
- `mygamemaster-game-report/SKILL.md` — Factual report (complementary)