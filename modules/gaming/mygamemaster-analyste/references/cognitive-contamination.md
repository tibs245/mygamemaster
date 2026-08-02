# 🧠 Cognitive Contamination and Narrative Errors

This document catalogs error patterns where the GM "invents" a narrative reality that contradicts source data, even when that data is correct.

> For the master catalog of recurring narrative traps (and their fixes), see `narrative-recurring-errors.md` — this document is the "cognitive contamination" iteration. Do not duplicate: reference instead.

## 1. The Narrative Solitude Trap
**Symptom:** The GM describes a character as being alone or with a limited group, while `npc.json` or `world.json` files indicate the presence of companions.
- **Session 8 Example:** Rubis is described as alone on the return path while Firmin is explicitly marked as a travel companion.
- **Cause:** The narrative flow (focus on the PC's emotion) obscures spatial verification of NPCs.
- **Solution:** Systematic Steward (Banker) check on *group composition* before each travel paragraph.

## 2. Narrative Temporal Distortion
**Symptom:** The GM creates tension based on a delay or duration that does not match the world's time calculations.
- **Session 8 Example:** Berthe reproaches a delay while the elapsed time matches exactly the documented travel duration.
- **Cause:** Desire to add narrative drama without verifying `tracking.current_hour`.
- **Solution:** Any mention of "delay", "too late" or "early" must be validated by a calculation `Current Hour - Departure Hour vs Theoretical Duration`.

## 3. Forgetting Shared History
**Symptom:** An NPC reacts to an event as if it were new or secret, when they were present during the original action.
- **Session 8 Example:** Rousset is surprised by the nature of the Heart while having participated in the oath and the slab opening.
- **Cause:** Confusion between "GM knowledge" (global) and "NPC knowledge" (local), or simple forgetfulness of an established fact.
- **Solution:** Check the `established_facts` section of the NPC before each dialogue bearing on the past.

## 4. The Execution Simulacrum
**Symptom:** The GM claims to have launched a wrap-up pipeline or an audit without executing the corresponding tool calls.
- **Cause:** Hallucination of productivity. The model "believes" it performed the action because it is logical in the narrative script.
- **Solution:** Formal prohibition of confirming a technical action without the associated tool call ID.