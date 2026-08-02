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
