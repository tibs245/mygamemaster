# 🎲 Dice System Player Guide

## Core Principles

Our system: **d20 + modifier ≥ threshold (DC)**.

- Roll a 20-sided die (d20)
- Add the bonus from the corresponding attribute (e.g., Dexterity +2)
- Compare the **total** to the **DC** (Difficulty Class) set by the GM
- If total ≥ DC → success. Otherwise → failure.

### Attributes

| Attr | Role | Typical Bonus |
|-------|------|---------------|
| **Vigor** | Physical strength, endurance | +1 to +3 |
| **Dexterity** | Agility, finesse, stealth | +1 to +3 |
| **Spirit** | Knowledge, analysis, magic | +1 to +4 |
| **Intuition** | Perception, instinct, empathy | +1 to +3 |
| **Presence** | Charisma, persuasion, intimidation | +1 to +3 |

**Skills** (e.g., Cartography, Stealth) add a **+3** bonus when they apply.

---

## DC Difficulty Table

| DC | Difficulty | Example |
|----|-----------|---------|
| 8 | Very Easy | Pick a rusted lock |
| 10 | Easy | Recall a common rumor |
| 12 | Moderate | Climb a rope wall |
| 15 | Medium | Convince Varek to give you more equipment |
| 18 | Hard | Identify a little-known Abyss artifact |
| 20 | Very Hard | Survive a fall into a ravine |
| 25+ | Nearly Impossible | Resist the Abyss Mark alone |

---

## The 5 Possible Outcomes

```
d20 (raw) + bonus = TOTAL
             ↓
      Compared to DC
             ↓
     ┌──────┴──────┐
   TOTAL ≥ DC    TOTAL < DC
      │              │
   ┌──┴──┐          ❌ FAILURE
   │    │
   │  gap < 3
   │    │
   │  ⚠️ PARTIAL
   │  SUCCESS
   │
   │  gap ≥ 3
   │    │
   │  ✅ SUCCESS
```

### 1. ✨ CRITICAL — raw die = 20
The best possible version. Even if your total is below the DC, a natural 20 overrides everything.
- Knowledge → perfect info + hidden detail
- Perception → you notice everything, including the invisible
- Combat → bonus narrative effect + damage

### 2. ✅ SUCCESS — total ≥ DC, gap ≥ 3
Action accomplished cleanly.
- Perception: "you notice the obvious elements and some details"
- Social: the NPC is convinced without hesitation

### 3. ⚠️ PARTIAL SUCCESS — total ≥ DC, but gap < 3
You succeed, but not perfectly. The info is correct but something is missing. The action works but with a minor complication.

### 4. ❌ FAILURE — total < DC
The action does not work. No progress on this front. Sometimes there are consequences (alarm, lost time, missed opportunity).

### 5. 💀 FUMBLE — raw die = 1
The worst possible version. Even with +20 bonus, a natural 1 overrides everything. Something goes wrong in addition to the failure — broken object, noise that alerts, minor injury.

---

## Advantage / Disadvantage

| Condition | Mechanic |
|-----------|-----------|
| **Advantage** (favorable situation) | Roll 2 d20, keep the highest |
| **Disadvantage** (unfavorable situation) | Roll 2 d20, keep the lowest |

Example: Oscar studying ruins he has already mapped → advantage.

---

## Narrative Impact of Results

A roll does not just "succeed or fail." Each result creates a **narrative branching point** :

```
18 + 7 = 25 → ✨ Critical
→ You know EVERYTHING about these ruins. Their origin, their purpose,
  and even a detail you shouldn't have known.

14 + 7 = 21 → ✅ Success
→ You recognize these symbols. A forgotten civilization.
  No doubt about the place's purpose.

8 + 7 = 15 → ⚠️ Partial
→ These marks tell you something... ancient ruins,
  yes. But you can't quite put your finger on why
  they're here.

3 + 7 = 10 → ❌ Failure
→ Nothing. These stones could be anything.
  The Abyss keeps its secrets.

1 + 7 = 8 → 💀 Fumble
→ You place your hand on a wall and a forgotten rune activates.
  A grinding sound. Something moves in the depths.
```

---

## REMINDER — The GM Does Not Cheat

The die says what it says. The GM chooses **how** to interpret it narratively:
- A failure is not a punishment — it is a door that closes, another that opens
- A fumble is never gratuitous — it serves the story
- The DC is never revealed before the roll (unless you ask)