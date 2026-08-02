---
name: mygamemaster-help
description: Guide the player to use MJ Tonnerre — explains how it works, lists the skills, guides step-by-step, verifies that everything is ok.
category: gaming
triggers:
  - "!help"
  - "!aide"
  - "!guide"
  - "!tutoriel"
  - "!onboarding"
  - "comment faire"
  - "aide"
  - "guide"
---

# ⚡ MJ Tonnerre — !help

> **Welcome, adventurer.** You just arrived in a campaign run by
> **MJ Tonnerre**. This guide shows you how it works, what you can
> do, and how not to get lost in the woods (metaphorically speaking —
> for the real woods, ask an NPC).

## 1. `!help` — Overview

```
╔══════════════════════════════════════════╗
║  ⚡ MJ TONNERRE — HELP                   ║
╚══════════════════════════════════════════╝

MJ Tonnerre is a Game Master who speaks to you, plays with you,
and keeps everything up to date behind the scenes. You speak, they respond.
You take an action, they validate it. You report a problem, they store it.

📜 AVAILABLE COMMANDS
   !help                    → This guide
   !help <command>          → Details of a command
   !help etapes             → Steps for good play
   !help verifier           → Verify that everything is ok

🎮 GAME COMMANDS
   !fiche                   → Your character sheet
   !perso <stat> <value>    → Modify something on your sheet
   !inv                     → Your inventory
   !jet <formula>           → Roll dice (d20, 2d6+3...)
   !action <description>    → Resolve an action

📋 SESSION COMMANDS
   !cloture                 → End of session (summary + audit)
   !game-report             → Factual report (no spoilers)
   !write-history           → Narrative account (novel style)
   !image                   → Illustration of the session

🐛 QUALITY COMMANDS
   !bug                     → Report a problem
   !analyse-bug             → Technical diagnosis (GM)
   !audit-presession        → Full audit before resuming (admin/GM)

🖼️ VISUAL COMMANDS
   !image <description>     → Illustration of a scene
   !portrait <name>         → Character portrait
   !carte <place>           → Map of a location

💡 Tip: Use the commands! The GM recognizes them and that
   guarantees everything is properly tracked in the files.
```

---

## 2. `!help <command>` — Details of a command

### `!help fiche`

```
!fiche — Your character sheet
➤ Displays your stats, HP, equipment, skills
➤ In public channel: content is spoilered
➤ Switch to DM to see your sheet clearly

Tip: Check your sheet regularly to know where you stand.
     Before a risky action, check your HP and inventory.
```

### `!help jet`

```
!jet <formula> — Roll the dice
➤ !jet d20           → 1 d20 die
➤ !jet 2d6+3         → 2 d6 dice + 3
➤ !jet d20 avantage  → Roll 2 d20, keep the best
➤ !jet d20 desavantage → Roll 2 d20, keep the worst
➤ !jetq d20          → Quantum version (truly random)

Tip: For any risky action, use !action rather than !jet.
     !action automatically chooses the right formula and
     narrates the result.
```

### `!help action`

```
!action <description> — Resolves an action
➤ Describe what you want to do: « !action I force the door »
➤ The GM chooses the appropriate stat and rolls the die
➤ The result is narrated with context

Tip: This is the recommended command for ANY action.
     It guarantees that the Steward checks consistency
     (inventory, position, time).
```

### `!help bug`

```
!bug — Report a problem
➤ The GM guides you: context → problem → expected
➤ The report is stored for processing after the session
➤ You can also give it all at once:
   !bug Context: ... Problem: ... Expected: ...

Tip: Report EVERYTHING that seems odd to you. It helps the GM
     fix inconsistencies. And you get peace of mind
     for the rest of the game.
```

### `!help inventaire`

```
!inv — Your inventory
➤ Displays everything you carry
➤ !inv ajoute <object> [qty]   → Add an object
➤ !inv utilise <object>        → Use/consume
➤ !inv jette <object> [qty]    → Drop
➤ !inv donne <object> @player  → Give to someone

Tip: Use !inv to check what you have before acting.
     The Steward automatically verifies that you have
     the object you want to use.
```

### `!help cloture`

```
!cloture — End of session
➤ Triggers 4 automatic actions:
   1. 🐞 Data audit (Steward checks everything)
   2. 📋 Factual report (what happened)
   3. 📖 Narrative account (the story well written)
   4. 🎨 Illustration image

Tip: Run !cloture at the end of the game. The GM will present
     the results and ask you to validate the corrections.
```

### `!help game-report`

```
!game-report — Factual session report
➤ Generates a factual summary: places, NPCs, decisions, inventory
➤ No spoilers — nothing you don't already know
➤ Useful to remember between sessions

Tip: If you want a quick memo of what happened,
     this is the command to use.
```

### `!help write-history`

```
!write-history — Narrative account of the session
➤ Generates novel/book-style text
➤ No stats, no mechanics — just the story
➤ Read like a chapter

Tip: Perfect for keeping a record of the adventure.
     You can even reread them later like a real book.
```

---

## 3. `!help etapes` — Steps for good play

```
╔══════════════════════════════════════════╗
║  📜 PLAYING WELL WITH MJ TONNERRE       ║
╚══════════════════════════════════════════╝

STEP 1 — DISCOVER YOUR CHARACTER
   !fiche         → Look at who you are
   !inv           → Look at what you have
   !perso notes   → Your personal notes

STEP 2 — ACT IN THE WORLD
   !action <description>  → Take a risky action
   !jet <formula>         → Roll the dice (if the GM asks)
   Direct dialogue        → Talk to NPCs (the GM responds)

STEP 3 — FOLLOW YOUR AFFAIRS
   !inv            → Check your inventory regularly
   !fiche          → Check your HP
   !game-report    → Factual summary mid-session
   !write-history  → Narrative account anytime

STEP 4 — REPORT PROBLEMS
   !bug            → If something seems odd to you
   The GM will handle it after the session

STEP 5 — END OF SESSION
   !cloture        → The GM orchestrates audit + report + narrative + image
   You validate the proposed corrections

💡 GOLDEN RULE: One action at a time.
   The GM describes the environment → You decide → The GM describes the result.
   Each action is a decision point.
```

---

## 4. `!help verifier` — Verify that everything is ok

```
╔══════════════════════════════════════════╗
║  ✅ VERIFICATION — IS EVERYTHING OK?    ║
╚══════════════════════════════════════════╝

Before you start playing, check these points:

□ !fiche → Are your stats correct?
□ !inv   → Is your inventory up to date?
□ Are you in the right campaign?
□ Do you know where your character is?
□ Do you have an idea of what you want to do?

During the game, remember to:

□ Use !action for risky actions
□ Check !inv before using an object
□ Report with !bug if something goes wrong
□ Run !game-report for a memo

At the end of the game:

□ Run !cloture (or ask the GM to do it)
□ Validate the proposed corrections
□ Read the narrative in sessions/NNN-recit.md

💡 If everything is checked, all is well. Good game!
```

---

## 5. Golden rules for the player

```
1. 🎭 ONE ACTION AT A TIME
   The GM describes → You decide → The GM describes the result.
   Don't chain 5 actions in the same message.

2. 🧮 USE THE COMMANDS
   !action rather than describing an action in free text.
   !bug rather than saying "something seems off".
   The commands guarantee that the Steward checks everything.

3. 📖 READ THE REPORTS
   !game-report gives you the facts.
   !write-history gives you the story.
   Together they let you follow the adventure.

4. 🐛 REPORT WITHOUT HESITATION
   If you see an inconsistency, !bug right away.
   This isn't nitpicking — it's rigor.
   The GM prefers 10 useless reports to one unreported bug.

5. 🔄 THE GM IS YOUR ALLY
   They are there to tell a good story with you, not against you.
   If you have a doubt, ask the question. The GM will answer.
```

---

## 6. Complete list of skills

| Skill | Role |
|-------|------|
| `mygamemaster` | The GM themselves — persona and rules |
| `mygamemaster-session` | Manages sessions (wrap-up, resumption) |
| `mygamemaster-analyst` | Technical data audit |
| `mygamemaster-bug-report` | Bug reporting by the player |
| `mygamemaster-game-report` | Factual session report |
| `mygamemaster-write-history` | Narrative session account |
| `mygamemaster-images` | Image generation |
| `mygamemaster-character` | Character sheets |
| `mygamemaster-inventory` | Inventory management |
| `mygamemaster-tools` | Dice rolls and actions |
| `mygamemaster-initiation` | Campaign creation |
| `mygamemaster-steward` | Steward (consistency verification) |

---

## References

- `mygamemaster/SKILL.md` — GM persona and rules
- Each skill listed above for command details