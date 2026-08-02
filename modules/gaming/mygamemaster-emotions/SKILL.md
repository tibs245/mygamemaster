---
name: mygamemaster-emotions
description: Character emotion tracking with logical, event-driven evolution. A compact per-character model (6 emotions 0..1 + temperament baseline + explainable history) persisted in npcs.json, updated by deterministic rules and decayed toward temperament, so the GM portrays NPCs consistently across a campaign — shown through behavior, never told as stats.
category: gaming
triggers:
  - "emotions"
  - "emotional state"
  - "npc mood"
  - "humeur pnj"
  - "etat emotionnel"
---

# 🎭 Character Emotions

> ✅ **Approved — fail-open, opt-in per character.** A character without an `emotions` object behaves exactly as before (no behavior change). Tooling: `mygamemaster/scripts/emotions.py`. Injection: `pre_llm_call` (axis `living_npcs_factions`).

A recurring NPC who was betrayed in session 2 should still be guarded in session 5 — and the player should FEEL it in how the NPC talks, not be told "his trust is 0.1". This skill tracks each character's emotional state, makes it **evolve logically** in response to events, and surfaces a one-line brief to the GM so portrayal stays consistent. Primarily for NPCs; PCs only ever opt in (see "Sacred agency" below).

## The model (compact, legible — no over-engineering)

Per character, one `emotions` object in their sheet (`npcs.json` for NPCs; `characters/<id>.json` for opt-in PCs). Keys follow the sibling sheet keys (`established_facts`, `gm_hypotheses`…); `etat` and `temperament` are the exact names read by `emotions.py`:

```json
"emotions": {
  "etat":        { "joy": 0.2, "trust": 0.15, "fear": 0.55,
                   "anger": 0.1, "sadness": 0.45, "surprise": 0.0 },
  "temperament": { "joy": 0.2, "trust": 0.25, "fear": 0.35,
                   "anger": 0.1, "sadness": 0.4, "surprise": 0.0 },
  "history": [
    { "event": "bad_news", "deltas": { "fear": 0.15, "sadness": 0.2 },
      "reason": "The Veil took two more villagers", "session": 1 }
  ]
}
```

- **6 core emotions, intensities 0..1** — `joy`, `trust`, `fear`, `anger`, `sadness`, `surprise`. Plutchik-inspired: `trust` is in the palette because trust drives ally/wary/hostile dynamics at the table; `surprise` captures shocks but is transient (it decays much faster).
- **`temperament`** — the baseline: who the character is when nothing is happening (a fae lady stays near-flat; an innkeeper who lost her father to the mist has a high `fear` baseline). The current state always drifts back toward it.
- **`history`** — capped journal (last 20 shifts) with event, effective deltas, in-fiction reason and session number. **Every change is explainable**; an emotional state with no journal trail is suspect, like a `established_facts` with no session reference (cf. `references/npc-data-governance.md`).

## Evolution rules (deterministic — never arbitrary)

1. **Named events** (`apply --event …`): a fixed lexicon maps event → deltas, e.g. `betrayal` → trust down hard, anger/fear/surprise up; `kindness` → trust and joy up a little; `rescue` → fear down, trust up. `emotions.py list-events` prints the full table. Scale with `--intensity` (0.5 = a minor slight, 1.0 = the real thing). All values clamp to [0, 1].
2. **Free-form shifts** (`adjust emo=±delta`): for situations outside the lexicon — the `--reason` is **mandatory** (it is what makes the journal explainable).
3. **Decay** (`decay [--rate 0.5]`): each emotion closes a fraction of the gap to temperament — run it at session close or on a big time skip. One default step ≈ one session of off-screen life. `surprise` decays at ≥ 0.8 regardless (shock does not linger for weeks).
4. **Auto-init**: `apply`/`adjust` on a character without emotions data first initializes a neutral temperament; prefer an explicit `init` with a temperament that matches the sheet (`attitude`, `peurs`, `motivations_personnelles`).

## Commands (GM/coordinator side)

```bash
SCRIPTS=/opt/modules/gaming/mygamemaster/scripts

python3 $SCRIPTS/emotions.py init   <campaign> "Petra" fear=0.3 sadness=0.3
python3 $SCRIPTS/emotions.py apply  <campaign> "Petra" --event promise_kept \
        --reason "The players swore on cold iron" --session 1
python3 $SCRIPTS/emotions.py adjust <campaign> "Mosswick" fear=+0.2 \
        --reason "Realized he may be the third soul" --session 2
python3 $SCRIPTS/emotions.py decay  <campaign>            # all NPCs, at wrap-up
python3 $SCRIPTS/emotions.py get    <campaign> "Petra"    # full state + history
python3 $SCRIPTS/emotions.py summary <campaign>           # the injected block
python3 $SCRIPTS/emotions.py list-events                  # the rule table
```

**When to update**: right after a charged beat lands in play (a betrayal revealed, a gift, a threat) — at the same moment you would add a `established_facts` line. Decay at session close (`mygamemaster-session` wrap-up) or when the clock jumps days.

## How the GM uses it — show, don't tell

`pre_llm_call` injects a compact block for NPCs that carry emotions data (one line each, capped — no context bloat), e.g.:

```
🎭 NPC EMOTIONS — play these through behavior, tone and word choice;
NEVER state feelings or numbers to players:
• Elder Mosswick — fearful (fear .55▲, trust .35▲) ; last shift: caught off guard by the players' questions (S1)
```

- **Behavior, not labels**: a `fear .55` Mosswick checks the window latch twice and answers a beat too late — the narration never says "he is afraid", and *never* shows an emotion name or a number to players (cf. the show-don't-tell rule in the `mygamemaster` umbrella and `SOUL.md`).
- **Consistency beats drama**: the injected state is **authoritative**, like inventory or HP. If the sheet says trust is low, the NPC does not warmly volunteer help this turn, whatever the conversational flow suggests.
- **Emotions color, they do not decide**: an NPC's `limites` (red lines, fears, motivations) still rule their choices; emotions set the tone and the friction.
- **Sacred agency (PCs)**: the GM **never assigns or narrates a PC's feelings** (cf. `SOUL.md`). A PC sheet may carry an `emotions` object only if the player asks for it as a roleplay aid; it is never injected into GM context.

## Wiring & fail-open

- Injection lives in `mygamemaster/hooks/pre_llm_call.py` → `build_emotions_brief()` (subprocess to `emotions.py summary`), gated by the `living_npcs_factions` feature axis. Any failure (no `npcs.json`, no emotions data, missing script, timeout) → no block, the turn proceeds untouched.
- `emotions.py summary` ALWAYS exits 0 — the fail-open contract of the hooks (`specs/hooks-runtime.md`) extends to this module.
- Schema: optional `emotions` property in `scripts/schemas/npcs.schema.json` (validated by `validate_schema.py`).

## Dependencies

- **Parent skill**: `mygamemaster` (umbrella — state injection precedence, show-don't-tell).
- **Data governance**: `mygamemaster/references/npc-data-governance.md` (traceable facts ↔ traceable emotional shifts).
- **Siblings**: `mygamemaster-pnj` (an NPC agent's brief gains consistent affect), `mygamemaster-session` (decay at wrap-up), `mygamemaster-intendant` (the Steward can check a declared NPC reaction against its persisted state).
- **Tools**: `mygamemaster/scripts/emotions.py` (stdlib only, tested in `scripts/tests/test_emotions.py`).
