# Narrative Rhythm — Concrete Examples

> Examples from the 2026-05-25 session (campaign "Birth of a King", player Alex/Rubis).
> Use as reference for protocol §6.6 "Open narrative rhythm: one action per narrative moment".

## ✅ What works (before the regression)

```
GM: "The fire crackles. The cabin smokes softly in the autumn. Before you, Rousset has already left to cut wood. You hear the murmur of the Douce. What do you do?"
→ Rubis: "I go to the traps, I pull in the fish."
→ GM describes the traps → decision point on the fish → etc.
```

Each step = 1 player decision.

## ❌ What doesn't work (the regression, same session)

```
❌ "You pull the first trap — it's heavy. Full of silvery perch.
   You move to the snares next — a hare hangs there, stiff.
   You bring it all back to the cabin. Berthe has already prepared the smoker.
   Rousset returns with more perch.
   Evening falls. Firmin hasn't come back."
```

→ 6 unvalidated actions. The player only chose "go to the traps".

## ✅ Post-correction — same scene, same intent

```
GM: "The Douce flows before you, the traps are further down on the left bank.
    The smoker is ready. Berthe is working on the turnips. What do you do?"
→ Rubis: "I go to the traps."
→ GM: "You pull the first one. It's full of silvery perch.
       The second one too, a bit less. What do you do with all this?"
→ Rubis: ...
```

## Derived Rules

- **One scene per response** — the landscape and what stands in it (the perceptible state of the world)
- **Zero unvalidated action verbs** — the test "did the player tell me to do that?"
- **No unvalidated time skips** — "You move next to the snares" assumes the player finishes at the traps and continues. They may decide to stop after the traps.
- **Describe what IS, not what HAPPENS** — "the traps are in the river" vs "you pull the traps". The first is a state of the world. The second is an assigned action.
- **Never a menu of actions** — describe the state, then stop. ✅ "🛑 Rousset looks at you. He waits." ❌ "You can: a) go to the traps b) help Berthe c) wait". The GM never lists the player's possible actions and never says "the options are visible".
- **An NPC offer is dialogue, not a menu** — "Rousset suggests going to cut wood" ✅ (a character speaks, inside the fiction). "Rousset leaves to cut wood" ❌ (assumes the group agrees, or cuts Rubis off from acting without their decision).

## No invented objects

If an NPC needs to carry something but doesn't have the object in their sheet:
- ✅ The NPC uses what they have: their blanket spread on the ground serves as a gathering mat
- ❌ The NPC pulls out an "empty canvas sack" that doesn't exist in their inventory
- ✅ Check in `npcs.json > inventory` and `inventory_<lieu>.contenu` before each interaction