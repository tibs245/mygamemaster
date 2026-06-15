# Wrap-Up Audit — Steward Post-Session Checklist

> Apply BEFORE committing a session wrap-up (`!cloture`).
> The Steward verifies that ALL transactions from the session have been correctly recorded.

## 1. Verify the 3 Steward Controls Across the Entire Session

For EACH action in `sessions/NNN.json > actions[]` :

| # | Control | Verification | Action if Failed |
|---|---|---|---|
| **1** | **SOURCE** | Do the objects, knowledge, HP, positions used in the action EXIST in the files at the time of the action? | ❌ BLOCKED — invented object, knowledge without source. Fix the file. |
| **2** | **TRANSFER** | Were the routes, durations, recipients, required time AVAILABLE and DOCUMENTED? | ❌ BLOCKED — undocumented route, insufficient time. Add the route or fix the timing. |
| **3** | **COHERENCE** | Is the action result LOGICAL (presence of witnesses, respect for limits, timing)? | ❌ BLOCKED — NPC who knows what they cannot know, action violating a hard limit. Fix the narration or the files. |

## 2. Verify the 7 Accounting Operations

For each validated action, verify that the following operations HAVE BEEN APPLIED:

| Operation | Verification |
|---|---|
| 1. Deduct source inventory | Was the object removed from the donor/consumer's inventory? |
| 2. Add target inventory | Was the object added to the recipient's inventory? |
| 3. Propagate knowledge | Did the present NPCs receive the knowledge they heard? |
| 4. Deduct time | Were `heure_courante` and/or `jour_courant` advanced correctly? |
| 5. Apply state changes | HP, fatigue, wounds, states — everything is up to date? |
| 6. Update positions | Are the `localisation_actuelle` of PCs and NPCs correct? |
| 7. Log | Is each action in `sessions/NNN.json > actions[]` with sufficient detail? |

## 3. Structural Verification (scripts)

Run the pipeline scripts to confirm everything is green:

```bash
SCRIPTS=/opt/modules/gaming/mygamemaster/scripts
CAMP=.hermes/mygamemaster/campaigns/<campagne>
python3 $SCRIPTS/validate_json.py $CAMP/        # STOP if JSON broken
python3 $SCRIPTS/check_session.py $CAMP --session NNN   # STOP if blocking discrepancy
python3 $SCRIPTS/validator-distances.py $CAMP/world.json # WARN if inconsistency
python3 $SCRIPTS/clock.py $CAMP --dry-run                 # WARN if faction clock behind
```

If all pass → commit. If STOP → fix before committing.

## 4. Narrative Verification (GM only)

These points are not automatable — the GM verifies them manually:

- [ ] Have the promised faction clock consequences been played out?
- [ ] Are the faction short-term/long-term objectives still valid?
- [ ] Do encountered NPCs have a record in `npcs.json` with `established_facts`?
- [ ] Do visited locations have an entry in `universe.regions[].lieux`?
- [ ] Are the weather and season consistent with elapsed time?
- [ ] Have rations been consumed correctly?

## 5. Commit

```bash
cd .hermes/mygamemaster/campaigns/<campagne>
git add . && git commit -m "Session NNN — Steward wrap-up: <summary of changes>"
```
