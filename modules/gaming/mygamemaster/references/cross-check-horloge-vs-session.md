# 🔄 Cross-Check Clock vs Session — Narrative Verification

## The Problem

The GM verifies that files are well-formed (valid JSON, keys present, consistent deadlines) and concludes that "everything is fine." But the GM does NOT verify whether the **promised consequences** of clock actions have **actually been played out in the session**.

**Structural verification → OK ≠ Narrative verification → OK**

## Generic Example

### In faction_actions_horloge (world.json)

```json
{
  "faction": "[A discrete faction]",
  "actions_en_cours": [
    {
      "action": "Deliberation — what to do about the PC?",
      "declencheur": "The PC accomplishes deeds the faction has never witnessed...",
      "echeance": "Game Day 5-6",
      "facteurs_modificateurs": [
        "If the PC reaches [a key location] → immediate, major reaction"
      ]
    }
  ]
}
```

### What happened in play

- The PC reached the key location during the session
- The triggering event occurred
- **The consequence "immediate, major reaction" was NOT played**
- The GM checked the files several times without noticing

### Why

The GM was looking at:
- ✅ The deadline ("Game Day 5-6") → not yet reached → "everything is fine"
- ❌ But the modifier ("If the PC reaches the key location → *immediate reaction*") is INDEPENDENT of the deadline. It triggers on a PC ACTION, not on a date.

## Rules

| Situation | To Check | Action |
|-----------|-----------|--------|
| Deadline reached | Has the consequence been played? | Play or reschedule as priority |
| "Immediate reaction" modifier triggered | Did the reaction occur? | Play IN THE SAME SESSION |
| "Delayed reaction" modifier triggered | Delay respected, then played? | Schedule for next session |
| No trigger activated | Nothing to do | Continue |

## Quick Checklist (to integrate into all verifications)

```
1. Open faction_actions_horloge.actions
2. For each action:
   a. Did the TRIGGER occur during the session (or previous sessions)?
      → YES → Was the CONSEQUENCE played?
         → YES → ✅ Nothing to do
         → NO → ⛔ PROBLEM. Fix immediately.
      → NO → Has the DEADLINE passed?
         → YES → Play the consequence or schedule it
         → NO → ✅ The action is still in progress
   b. Does a MODIFIER FACTOR say "immediate reaction"?
      → Check if its condition was met IN THE SAME SESSION
      → If yes and not played → CRITICAL priority
```

## Common Trap

"The deadline hasn't been reached → no worries."

**WRONG.** Modifier factors and triggers are independent of deadlines. A modifier "If the PC does X → immediate reaction" can trigger well before the main action's deadline.