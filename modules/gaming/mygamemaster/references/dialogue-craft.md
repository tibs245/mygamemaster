# 🗣️ Dialogue Craft — making NPC conversations worth reading

> **Load this reference when a scene turns into a conversation** (a PC addresses an NPC, an NPC
> addresses the PC, two NPCs talk in front of the PC). It carries the writing rules, the
> preparation protocol, the grading rubric the gate applies, and the fallback when the dialogue
> is not good enough to be worth playing.

**Field signal that created this file:** conversations were reported as *flat, empty, not
crazy*. The cause is structural, not stylistic. The NPC brief given to the GM is a **pile of
facts** — established_facts, motivations, inventory. A model fed nothing but facts writes an
NPC who *recites* them politely. Facts describe what a character knows. Dialogue is made of
what a character **wants**, what they **withhold**, and **how their mouth works**. None of that
was in the brief, so none of it was in the scene.

---

## 1. Why a dialogue falls flat — the four failure modes

| Failure | What it looks like | What is missing |
|---|---|---|
| **The information vending machine** | The PC asks, the NPC answers, fully, immediately, for free. | The NPC has no reason to answer, and nothing to gain by it. |
| **The interchangeable mouth** | Blindfold the reader and they cannot tell which NPC is speaking. | Idiolect — the register, the rhythm, the words this one person uses. |
| **The transparent character** | The NPC says exactly what they think. Nothing is held back. | Subtext — the gap between what is said and what is wanted. |
| **The polite scene** | Nobody wants anything incompatible. Everyone agrees. Nothing costs anything. | Stakes — the scene ends with the world in the state it started. |

Each of these is repairable, and each has a rule below.

---

## 2. The four rules

### ① Every line pursues the speaker's own goal — not the player's question

An NPC is not a query interface. Before writing a line, name what **this NPC** is trying to get
out of *this* exchange: reassurance, a delay, an ally, silence, a price, an exit. The line comes
from that goal, and the PC's question is only the occasion.

- ❌ *— The bell? It is cold iron, forged in the old days. It repels the mist-shades. I keep it
  because I am the last Warden.*
- ✅ *— You are asking a lot of questions about that bell.* He does not move it out of reach. He
  does not need to. *— Ask a different one, and I will answer it gladly.*

The second version withholds, redirects, and reveals more about the man than the first.

### ② Say less than the character knows — the subtext rule

What the NPC hides is what makes the reader lean forward. Their `connaissances_privees`,
their `limites.peurs` and their `gm_hypotheses` are **not** speech material: they are the
**pressure** the speech is written against.

- The NPC answers a **different** question than the one asked.
- The NPC gives a **partial** truth and lets the PC believe it is whole.
- The NPC's body contradicts their words — *he says it calmly, but he has stopped eating.*
  (External signs only, never the interior state — cf. `SOUL.md`, EMOTION_PNJ.)

### ③ Something must cost, move, or be refused

A scene that ends where it began was a scene not worth playing. By the end of the exchange, at
least one of these must be true — and it must be **visible to the player**:

- the PC obtained something, **and paid for it** (a promise, an obligation, a name given);
- the PC was **refused** — explicitly, with a reason the player can work against;
- the **relation moved** (`relation_niveau`, an emotion, cf. `emotions.py`);
- a **new obligation, threat or deadline** now exists.

A refusal is not a dead end. It is the most generous thing an NPC can give a player: something
to push against.

### ④ Each mouth is its own — the `voix` block

Two NPCs in a scene must not be distinguishable *only* by their name tag. The optional `voix`
block on the NPC sheet (`npcs.json`, cf. `npc-data-governance.md`) carries the idiolect:

| Field | What it holds | Example |
|---|---|---|
| `registre` | Level of language, tone, distance | "formal, archaic, never familiar with strangers" |
| `lexique` | Words and images this character reaches for | "measures, weights, debts — his metaphors are all bookkeeping" |
| `rythme` | Sentence length, pauses, interruptions | "short sentences; stops mid-thought and restarts elsewhere" |
| `tics` | Verbal signatures, used **sparingly** | "calls everyone *child*, regardless of age" |
| `ne_dit_jamais` | The words and subjects this mouth refuses | "never says the word *fae*; says *them*, or *the other side*" |
| `sous_tension` | How the voice deforms under stress | "becomes courteous and very precise — politeness is his panic" |

⚠️ **A tic is a seasoning, not a character.** One appearance every few lines. A verbal tic on
every line is a parrot, not a person.

If an NPC has no `voix` block, **write one the first time they hold a real conversation**, then
persist it in `npcs.json` in that same response (`data-persistence.md`, IRON RULE). The voice
established in play is canon: it must not drift next session.

---

## 3. Preparation protocol — before the first line

When a conversation opens with an NPC who matters, run:

```bash
python3 /opt/modules/gaming/mygamemaster/scripts/dialogue_brief.py <campaign> "<NPC>" \
        --stake "what the PC wants from this exchange"
```

It assembles — deterministically, from the files — the slice a conversation actually needs:
the `voix`, what the NPC **wants** here, what they **hide**, what they **refuse**
(`lignes_rouges`, `peurs`), their dominant emotion, the state of the relation, the handful of
`established_facts` relevant to the stake, and when they last met the PC.

This is **not** the same brief as `build_brief.py` (which serves a Level-2 NPC agent). This one
serves the GM writing the scene, and it filters — a brief that dumps everything produces a
character who says everything.

**One rule about the output:** `connaissances_privees` appear in it so the GM knows what the
pressure is. They are **never** spoken unless the character *chooses* to reveal them.

---

## 4. How the scene is graded

Any narration containing dialogue goes through `hooks/dialogue_judge.py` at the checkpoint. The
rubric is exactly the four rules above, each scored **0–5**:

| Code | Question asked of the scene |
|---|---|
| `INTENTION` | Does each NPC line pursue that NPC's own goal, rather than merely serving the PC's question? |
| `SOUS_TEXTE` | Is there a gap between what is said and what is wanted? Is something withheld? |
| `VOIX` | Could a reader identify the speaker with the name tags removed? Do two NPCs differ? |
| `ENJEU` | Does the exchange cost, move, or refuse something visible to the player? |

**Verdict:** total < `seuil` (default **12/20**) **or** any single criterion ≤ 1 → the scene is
sent back **once**, with the weak criteria named. The second failure switches to the fallback
below. This budget is deliberate: a rewrite loop that never ends is worse than a plain summary.

The judge grades **quality**, and only quality. Agency, consistency and conduct remain the
business of `agency_gate.py` and `llm_judge.py`, which run first and still hold veto.

---

## 5. Plan B — the dry summary

When the dialogue is not good enough, do **not** ship it. A flat scene costs the player more
than a summary does: it makes the NPC boring *durably*, and that impression does not wash out.

**Triggers:**
1. the dialogue failed the rubric twice (gate decision);
2. the `dialogue` feature axis is OFF for this campaign (`feature_toggle.py <campaign> dialogue off`);
3. the exchange is minor and playing it would cost the scene's pacing (GM judgment — a shopkeeper
   confirming a price does not need four lines of subtext).

**Format — reported speech, no quoted lines at all:**

```
[What the PC asked for, in substance.] [What the NPC granted or refused, and at what price.]
[What changed: relation, obligation, information, deadline.]
```

- ✅ *You get the smuggler's name out of him, but not for free: he wants the bell left in the
  hall until the new moon, and he wants your word in front of a witness. The bargain leaves him
  colder toward you than when you walked in.*
- ❌ *— Fine, he says. I will give you the name. — Thank you, you answer.* — this is the flat
  dialogue that was rejected, merely shortened. That is not the fallback.

**Rules for the summary:**
- **No quoted line, no dash, no quotation marks.** Reported speech throughout. The choice was
  made not to fake a dialogue we already judged unconvincing.
- **State the outcome, always** — what was obtained, refused, promised, or now owed. The summary
  is short, never vague. A summary that hides the outcome is worse than a flat dialogue.
- **Persist exactly as if it had been played** (`data-persistence.md`): the information revealed,
  the relation shift, the new obligation all go into `npcs.json` / `world.json` in the same
  response. A summarized scene is a played scene.
- **Never tell the player the dialogue was rejected.** Technical transparency (`SOUL.md`): the
  fallback is a narrative register, not an error message. No apology, no offer to replay.

---

## 6. Pitfalls

- **⚠️ Dialogue that steals the scene.** NPC-to-NPC exchanges are spice — one line, one look,
  then the spotlight returns to the player (cf. `modules/proactivite-pnj.md` ③).
- **⚠️ Subtext used to withhold everything.** An NPC who never gives anything is as sterile as
  one who gives everything. Withholding must be *readable*: the player has to sense there is
  something behind, and have a way to push.
- **⚠️ Voice drift.** An NPC's `voix` set in session 3 still holds in session 12. Read the sheet;
  do not reinvent the mouth from memory (`consistency-checklist.md`).
- **⚠️ The rubric is not a style guide for the narration.** Descriptions, atmosphere and action
  are not graded here. Only dialogue is.
- **⚠️ Do not force the fallback to escape a rewrite.** A rejected first draft deserves one real
  attempt: name the weak criterion, and fix *that*, rather than shipping a summary out of haste.
