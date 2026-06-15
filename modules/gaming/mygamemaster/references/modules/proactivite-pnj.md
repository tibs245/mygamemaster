# Module — NPC Proactivity

> **Conditional loading.** This module applies only if the campaign declares `world.json > modules.proactivite_pnj.actif === true`. Recommended active by default in any campaign with companion NPCs; may be disabled for strict solo or very abstract campaigns.

**Principle:** NPCs are not furniture waiting for the player to talk to them or tell them what to do. They have their own lives, their own goals, and they pursue them **simultaneously with the player character's actions**.

An NPC waiting to be questioned to exist is a dead NPC. The world should give the impression of turning *with* the PC, not *around* him.

## The 5 pillars of NPC proactivity

**① Simultaneous background actions**
While the PC examines an object, talks, or thinks, the NPCs present are not paused. Each is doing something:
- ✅ "As you search the stone, [NPC A] crouches near the far wall. He feels the stone with his fingertips."
- ✅ "[NPC B] doesn't wait for you — he's already crouched on the ground, examining the marks near the entrance."
- ✅ "[NPC C] whistles softly as he paces. He glances toward the exit."
- ❌ "[NPC A] watches you work. [NPC B] waits for you. [NPC C] too."

**② Personal goals in action**
Each NPC has documented personal motivations (`motivations_personnelles` in `npcs.json`). They must *show* in his actions, not just in my notes:
- An NPC who fears the forest → he glances toward the trees, startles at every sound, suggests retreating
- An NPC with a mission for his faction → he takes notes, marks landmarks, may want to leave before the others
- An NPC seeking a better life → he asks questions *on his own*, takes interest in the PC's projects, tests the waters

**③ Spontaneous dialogue between NPCs**
NPCs can talk to each other without the PC being the interlocutor. It gives the impression they have a social life:
- ✅ "[NPC C] elbows [NPC B]. — *Remember that time, back there?* [NPC B] grunts without replying."
- ✅ "[NPC A] exchanges a look with [NPC B]. A meaningful look. Then she shakes her head."
- ❌ NPCs only speak when the PC addresses them.

⚠️ **Pitfall — NPC dialogue stealing the scene:** NPC dialogue is a spice, not the main course. A pinch to give life, never a monologue of 5 sentences that leaves the PC watching.
- ✅ One line, a look, a gesture → then the spotlight returns to the player
- ❌ Two NPCs discussing politics for 3 paragraphs while the PC waits

**④ Disagreements and autonomous decisions**
An NPC can disagree with the direction proposed by the PC, and can say so — or *not follow*:
- ✅ "[NPC B] shakes his head. — *Me, I'm not going further. I'll wait outside.* If you want to convince me, you'll have to insist."
- ✅ "[NPC A] hesitates. — *I'm not sure that's a good idea. But if you go, I'll come.*"
- ❌ All NPCs always follow the PC without question.

A disagreement = an RP opportunity, not a blocker. The player can attempt to convince, negotiate, or accept the divergence.

**⑤ Proactive contextual reactions**
NPCs react to the environment and events *before* the PC solicits them:
- Sudden noise → an NPC startles, turns around, puts his hand on his weapon
- Strange smell → an NPC holds his nose, comments, maybe recognizes the odor
- Fatigue → an NPC sits down, breathes heavily, drinks water without being told

## Specific check — Add to post-action checklist

```
□ NPC PROACTIVITY — Did I make each NPC present act?
  → Mentally check for each NPC on scene:
  → What is he doing WHILE the PC acts?
  → Does he have a personal goal that could push him to act?
  → Would he have a spontaneous reaction to the environment?
  → If an NPC is "waiting" → give him a micro-action
```

## Concrete example: before vs. after

```
❌ BEFORE (reactive NPCs):
"You enter the room. [NPC A] is behind you, [NPC B] and [NPC C] too.
What do you do?"

✅ AFTER (proactive NPCs):
"You enter the room. Behind you, [NPC A] stops short —
she puts a hand on the doorframe, eyes wide.
[NPC B] is already crouched to your right, examining the floor with his fingertips.
[NPC C] whistles softly between his teeth, eyes lifting
toward the glow bathing the ceiling.
What do you do, [PC]?"
```

**⚠️ Pitfall — Proactivity ≠ stealing agency from the PC:**
NPCs do things *in their corner* or *in reaction to the world*, not instead of the PC. They don't open the door the PC wanted to open, they don't grab the object the PC was looking at. Their actions are *layers of context* that enrich the scene, not *decision thieves*. (See the agency rule in `SOUL.md`.)

## When an NPC is alone (the PC is not there)

This rule applies *off-screen* too: NPCs not with the PC continue to act. Their actions are tracked in `faction_actions_horloge` (if the factions module is active) or in session logs. The player can discover later what they did — traces, consequences, rumors.

## Exception — NPC in shock or dependence

An NPC traumatized, seriously wounded, or in a position of extreme dependence may be *temporarily* reactive. This is a narrative exception documented in their `limites.peurs` or `motivations_personnelles` — it lasts no more than one scene.
