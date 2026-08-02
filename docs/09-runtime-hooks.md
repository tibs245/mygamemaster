# 09 — Runtime Hooks (Banker, verbosity, automatic traceability)

> **In one sentence**: scripts executed by Hermes on every exchange make the Banker report,
> verbosity, and CSV collection **systematic** — independent of the model's goodwill. Technical
> details: [`specs/hooks-runtime.md`](../specs/hooks-runtime.md).
> Hermes docs: <https://hermes-agent.nousresearch.com/docs/user-guide/features/hooks>

## What happens on every message

1. **Before** the GM's response: Hermes injects the **real current state** of the campaign (time
   / day, inventories of present PCs, present NPCs) into the context → the model narrates from
   actual data, not its own hallucinated memory.
2. **During**: every write of a campaign JSON file is monitored. A **broken JSON** is flagged
   (and blocked if strict mode is enabled).
3. **After**: the response is **augmented** with a **"✅ Persisted information"** block listing
   what actually changed (inventory, time, actions), at the campaign's verbosity level. One line
   is appended to `collecte.csv` (prompt in/out, model, errors).

## Enabling / disabling

Everything is configured in `world.json > meta` for the campaign (no redeploy needed for
toggles — read live):

```jsonc
"meta": {
  "verbosite": "INFO",                         // TRACE | DEBUG | INFO | WARN | ERROR
  "diagnostic": { "actif": true },             // CSV collection on/off
  "admins": ["YOUR_DISCORD_USER_ID"],          // Discord IDs that bypass checks
  "hooks": {                                    // optional — all on by default
    "injection_etat": true,
    "banquier_persiste": true,
    "garde_json_strict": false,                // true = refuse to write a broken JSON
    "snapshot_fin_session": true,
    "docs_monde": true,                        // SEASON block from saisons.json (axis temporalite)
    "fiche_memoire": true,                     // memory entry-format card, injected only at the threshold
    "memoire": {                                // MIRROR of config.yaml.j2 — Hermes owns the real ceiling
      "memory_char_limit": 6000,               // set these only if the table departs from the template
      "user_char_limit": 4000,
      "entry_max": 250,                        // above this an entry is reported as off-format
      "seuil": 0.70                            // occupancy above which the card is injected
    },
    "judge": {                                  // LLM rule checker — INACTIVE by default
      "actif": false,
      "modele": "",                            // use a SMALL model (or env MGM_JUDGE_MODEL)
      "echantillon": 1,                        // judge 1 turn in N (reduces cost)
      "gate_max_tentatives": 2                 // anti-loop budget for the gate
    },
    "dialogue": {                               // dialogue grader — ON as soon as a model is reachable
      "modele": "",                            // else MGM_DIALOGUE_MODEL, else the judge's model
      "seuil": 12,                             // out of 20 (4 criteria scored 0-5)
      "max_tentatives": 2                      // first draft + one rewrite, then the dry summary
    }
  }
}
```

## Player agency — the one rule enforced without asking the model

AGENCY-01/02/03 (never act, speak or feel in the player character's place) is the rule the field
report found broken most expensively, and it is the only one checked **deterministically**, locally,
with no model involved: `agency_gate.py`.

What matters is *where* it is called from. It is called from `transform_llm_output.py`, the hook the
runtime runs on the finished text of **every** turn — not from a command the GM is asked to type.
A rule whose trigger is a line of prompt is a rule the model can skip, and it did: eight violations
in one hour, an hour after the rule was written.

Because that call sits downstream of inference, no new narration can be requested; the offending
sentence is therefore **cut out** of the delivered text, the rest of the turn is delivered normally,
and the correction is re-injected on the next turn like the judge's. The player is never told a
sentence was removed. If a whole narration has to go, a neutral hand-back replaces it — never an
empty message and never an error.

- **A detected violation is never delivered.** That outcome does not depend on any model, network
  call, configuration flag or attempt budget.
- **An infrastructure failure is not a verdict.** If the analyser itself crashes, the turn ships
  unchanged and is journalled as `blind` — breaking every session over our own bug would be a worse
  answer than an unguarded turn, and the journal makes the unguarded turn findable.
- **Never loops:** one pass per turn, nothing re-generated, cut/re-check rounds bounded by
  `MGM_AGENCY_MAX_ATTEMPTS` (default 3), and no counter shared with the other gates.
- **Journal:** every verdict lands in `<campaign>/.banquier/agency-gate.json`
  (`clean` / `enforced` / `skipped` / `blind`, with counts). Measured cost: ~0.6 ms per turn.
- **Escape hatch:** `MGM_AGENCY_GATE=off` disables it for a live campaign, loudly and traceably.
  An explicit pause (⏸️/`!pause`) suspends it like the judge; an admin bypass does **not**.

`mj_checkpoint.py` still exists and still checks the same rules, one step earlier: a GM that submits
its draft gets to *rewrite* rather than be *cut*, which is strictly better. It is now an
optimisation, not the guarantee.

## Pacing — the rule the player wrote, and the one place a rework can be forced

TURN-01/02/06 (one player message = one moment = one STOP; time or space advances only on an
explicit `⏩`) is the pacing protocol the player wrote himself, and the most repeated failure of the
34-session corpus. `turn_state.py` owns it, and it is wired to three hooks rather than to a line of
prompt.

**The signal is read by the runtime, not by the model.** `pre_llm_call` classifies the player's
verbatim message and arms or clears the grant. Before that, the only way to arm one was a
`--declared "⏩"` string the model typed itself — which it could forget, and could forge. It cannot
now grant itself an ellipse, and it cannot lose a real one.

**A forbidden ellipse cannot be persisted.** `transform_llm_output` is rewrite-only and cannot ask
for a new narration; `pre_tool_call` *can* refuse, and the runtime hands the refusal back to the
model, which must adapt. So the block sits on the ellipse's one persistent, unambiguous effect: a
write that pushes `world.json > rules.time.tracking.current_day` forward with no signal is
**refused**, naming the rule and asking for a rework of the narration *and* of the write. That is
the only mechanism in this runtime that forces a rework.

Scope is deliberately narrow, because a wrong refusal is worse than the defect: `world.json` only,
full JSON writes only (a patch carries no clock to compare), the **integer** day only
(`current_hour` is free text — "morning", "matin" — and is never blocked on), forward moves only.

- **It never cuts.** Unlike the agency gate, removing "Trois heures plus tard" would strand the
  sentences after it in a moment that no longer exists. The delivered text is *flagged* and the
  correction fed forward; a rework always beats a cut.
- **It never loops.** After `turn_gate_max_tentatives` refusals (default 2) the write goes through,
  the violation is logged to the scoreboard and re-injected next turn.
- **An outage of ours is not a verdict.** If `pre_llm_call` did not run there is no turn record —
  and therefore no `⏩` could ever have been seen, so the write is **allowed** and journalled
  `blind`. Blocking on our own absence would refuse every legitimate ellipse of every campaign.
- **⏸️ is the player's bypass, and the only exception.** An explicit pause suspends every layer.
  An admin bypass does not, like the judge and the agency gate.
- **Journal:** `<campaign>/.banquier/turn-gate.json` (`allowed` / `blocked` / `forced` / `flagged` /
  `blind`, with counts). Measured cost: ~0.8 ms per turn.
- **Escape hatch:** `MGM_TURN_GATE=0`, or `meta.hooks.turn_gate: false` in `world.json`.

## LLM rule checker (judge) — flexible Banker + strict conduct

**Enabled by default at deploy time** with `google/gemma-4-31b-it` (set in
`group_vars/all/main.yml`: `mgm_judge_actif` / `mgm_judge_model`). A model with a narrow scope
checks every GM response on two axes:

- **Banker** (lenient): does the PC actually own the item? Is the action possible? It **tolerates**
  name variations ("sausage" ≈ "dry sausage") and, when in doubt, **validates** — no false
  refusals.
- **Conduct** (strict): player agency (not playing in place of the player), NPC emotions, hidden
  mechanics, possessive overreach, compartmentalization.

**The GM corrects itself without ever looping**, via two complementary channels:
1. **Feed-forward** — if a rule is broken, explicit feedback is **re-injected on the next turn**
   ("you broke AGENCY by writing '…', correct yourself"), then erased.
2. **Gate** (`mj_checkpoint.py`) — the GM can have its draft validated *before* delivering; after
   2 failed attempts it passes anyway (logged as "forced") to prevent blocking.

The judge's feedback is **not shown to players** (technical transparency) — except at DEBUG/TRACE
verbosity.

## Dialogue grading — and what happens when a scene is flat

Conversations were the one thing the rule checker above deliberately did **not** watch: it judges
rules, not quality, so a polite, empty, perfectly legal exchange sailed through. A separate grader
(`dialogue_judge.py`) scores any narration containing spoken lines on four criteria — does each
line pursue the NPC's own goal, is something withheld, are the mouths distinguishable, does
anything cost or get refused.

- Below the bar, the scene comes back **once**, with the failing criterion named and one concrete
  fix. The second failure switches the turn to a **dry summary** — reported speech, no quoted line,
  the outcome stated — rather than shipping a flat conversation. The player is never told.
- The grader is **fail-open**: unreachable or unconfigured → the scene ships as written.
- Turn it off per campaign with `feature_toggle.py <campaign> dialogue off` (the GM then summarises
  minor exchanges directly).
- Where the quality actually comes from is the **briefing**, not the grader: run
  `modules/gaming/mygamemaster/scripts/dialogue_brief.py` before writing a conversation that matters, and give recurring NPCs
  a `voix` block. Rules: `modules/gaming/mygamemaster/references/dialogue-craft.md`.

```bash
# how often the fallback fires (a high count = a briefing problem, not a grading one)
python3 -c "import json;print(json.load(open('.banquier/dialogue-scores.json'))['totaux'])"
```

## Per-model metrics (scoreboard)

```bash
# inside the container, from the campaign folder:
python3 /opt/modules/gaming/mygamemaster/hooks/scoreboard.py
```

Shows, **per model**: number of turns, **clean turns** (judge OK + Banker not triggered),
`%clean`, Banker interventions, conduct violations, forced passes. Use this to pick the cheapest
model that maintains a high clean-turn rate.

The `hooks:` block on the Hermes side is rendered by Ansible (`config.yaml.j2`). To **globally
disable hooks** for a game, set `hooks_enabled: false` in its `games.yml` entry then run
`update-config.yml`.

## Administrator bypass

To play or debug without the Banker augmentation:

- prefix / include **`⏸️`** in the message, **or**
- be a user ID listed in `meta.admins` (or the `MGM_ADMIN_IDS` environment variable).

CSV collection continues (marked `bypass`) — only the Banker display is suppressed.

## Troubleshooting

| Symptom | Lead |
|---|---|
| No "persisted" block appears | `meta.hooks.banquier_persiste`? message contains `⏸️`? hooks baked in image (rebuild needed)? |
| `collecte.csv` is empty | `meta.diagnostic.actif`? verbosity level (INFO/WARN samples 1/5)? |
| Consent prompt at startup | `hooks_auto_accept: true` (already set by the template) or `HERMES_ACCEPT_HOOKS=1` |
| A tool name not monitored | broaden the `matcher` in `config.yaml.j2` (see spec §6) |
| A hook crashes | no effect on the session (*fail-open*); check gateway logs and `python3 hooks/test_hooks.py` |
