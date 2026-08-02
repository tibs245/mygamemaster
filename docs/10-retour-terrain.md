# 10 — Field report: 34 sessions of real play

**Corpus:** campaign « La naissance d'un roi », sessions S1→S34, 12 June → 28 June 2026.
**Repatriated:** 2 August 2026, from the live deployment (Podman volumes on the Pi).
**Method:** six parallel analyses over the game data, the agent runtime state, the production
prompts and the repo code — then contradictions between analyses arbitrated against the live
machine.

This document is the durable record of what that campaign taught us. It exists because the
knowledge produced by 34 sessions of play was, at the time of writing, stored **only** in places
that were about to lose it: a 166 KB campaign log never loaded at play time, a skill directory
frozen against writes, and an agent memory that was silently purged.

---

## 1. What the corpus actually is

| Artifact | Size | Where it lived |
|---|---|---|
| `MJ-INTENTION-LOG.md` | 2 610 lines | campaign data — **never loaded during a turn** |
| Production skills (2, self-written by the agent) | 22 085 lines | `$HERMES_HOME/skills/` — no equivalent in this repo |
| Per-session lesson files | 55 files, ~18 000 lines | same, accumulated S13→S34 |
| Session records | 34 sessions, 1.1 MB | campaign data |
| Bug reports triggered by the player | 6 | campaign data |
| Campaign git history | 134 commits | campaign data |

The player played, pushed the system to its limits, and reported problems in a structured way.
Nearly all of the resulting knowledge accumulated **outside** the product.

---

## 2. The finding that governs all the others

The agent wrote, in its own log, the sentence that summarises the whole audit:

> *« The 5-stops rule has been in the log since 1 pm, but I made 8 violations between 1 pm and
> 2 pm. The problem is not the absence of a rule, it is an GM pattern stronger than the rule. »*

Three facts, each verified independently, explain nearly every repeat offence:

1. The ~60 "locked lessons" lived **only** in campaign data never loaded at play time.
2. None of them had been promoted into the product. A grep over the shipped skills returned
   **zero** occurrences of the core disciplines (5-stops, `⏩` permission, verbatim placeholder).
3. The one coded guardrail (`hooks/llm_judge.py`, `AGENTIVITE` rule) is **fail-open by design**
   ("if the call fails or is ambiguous → ok=true") and **feed-forward** (the correction is
   injected on the *next* turn), so it never blocks the offending turn.

**Consequence for method:** a rule that is only written down will be violated again. The classes
of bug that cost the most must be closed by **deterministic code**, with the prompt merely
stating the rule the code enforces. Writing more doctrine is not progress — production proved it
by accumulating 18 000 lines of doctrine and still regressing.

---

## 3. Verified state of the system

### 3.1 The engine reads the live world as empty, and says nothing

Measured file by file on the real campaign, if it were loaded by the current (English-key) code
without migration:

| Data | Read as |
|---|---|
| `geo.locations` | 38 → **0** |
| `actors` | 10 → **0** |
| `events` | 61 → **0** |
| `visited_locations` / `npcs_met` / `end_hour` | **0 / 34 sessions** |
| `meta.features` | **survives — all axes ON** |

The last line is what makes it dangerous: the engine believes the living world is active and
runs it over nothing, without a single alert. The most toxic loss is `faits_etablis`
(established facts, present on 16 of 18 NPCs) becoming invisible — the GM then re-improvises
canon that was already played.

**This is not a migration accident, it is a steady state.** The shipped skills still instruct the
GM to write French keys (15–38 occurrences), so a migrated campaign drifts back out of
conformance on its own.

### 3.2 Time drifted by 51 days without anyone noticing

The time axis is exact up to S30, then diverges monotonically: +5 days at S31, **+51 days** at
`t_reference`, +203 days at the planning horizon. Four clocks disagree; the frost counter holds
three different values (66 / 49 / 28); 14 plan deadlines have been overdue for ~55 days; four
events are marked `resolved` with a future date.

Cause: `world_tick.py` is fail-open (no-op when `t_current ≤ t_reference`), so the drift is
silent. The lesson the agent itself locked — *"fail-open ≠ coherent"* — was never applied to the
code that taught it.

> Migrating the keys **without recalculating T** would produce an engine that "works" and is
> wrong by 51 days. Any future resumption must do both.

### 3.3 The runtime had stopped learning

- The production skill reached **104 162 characters against a hard limit of 100 000** → frozen
  against writes, **76 refused writes**.
- Agent memory was saturated at 92–100 % of its 2 200-character budget **from day one** → **318
  refused writes**.
- On 26 July an untraced purge took memory from 2 130 → 502 characters; the S25–S31 lessons
  disappeared with no archive.

Both surfaces on which the agent could learn were full. The 40-file lesson pile is not
disorder — it is the observable symptom of a system with nowhere left to put what it learns.

### 3.4 Runtime hooks load, but their business chain is inert

Arbitrated directly on the live machine, because two analyses disagreed:

- The hooks **are** present in the deployed image, declared, and load without error at all 18
  restarts.
- Yet after 34 sessions `.banquier/` holds exactly **one** `scene-s023.json` (17 June, never
  again), **zero** ledger files, **zero** scoreboard. Snapshots were taken by hand with `tar`;
  `collecte.csv` was written by the LLM.

So roughly 2 000 lines of code and 75 green tests do not do, in production, what they claim.
`harness/README.md` already recorded this as a "known blocker"; it was never resolved.

### 3.5 Two shipped defects worth naming

- `build_brief.py` and `geo_query.py` read the key `nom` hard-coded while migrated data carries
  `name` → `find_pnj` returns `None` for **every** NPC, and raises `KeyError` on migrated data.
- The shipped example campaign (`example-mistfall`) fails 3 of its own 4 validators.

---

## 4. What worked — do not break it

Explicit positive signal from the player, to be preserved by any refactor:

- **Visible travel rolls** (d20 vs a difficulty, narrated outcome, numbers on request) — the only
  feature that earned an unprompted "it's better with the travel rolls". Mechanics made visible
  beat pure narration.
- **The NPC triangle** — three companions with complementary roles rather than one sidekick.
- **A companion animal with a player-declared policy** ("answers if there is no danger").
- **Ethics of the name** — the player refusing an imposed nickname, and the world honouring it.
- **A world that lives without the PC**, *including when that frustrates* — an NPC leaving before
  the PC could speak to him was accepted as legitimate.
- **Sober scenes, short gestures.**
- **Plain admission of bugs, without defence**, when the player reported one.

The player did not ask for cosmetic features. Across 16 explicit requests he asked for
(a) **visible mechanics**, (b) **control and repair tools** (revert, tempo, replayable audit),
(c) **autonomous world simulation** (NPC↔NPC interaction outside sessions). The three most
conspicuous gaps are session revert, the tempo protocol, and off-session world simulation.

---

## 5. What the audit discarded

The reports in the corpus are self-generated by the agent, which also grades itself. Excluded
from the signal, and recorded here so it is not re-imported later:

- **Self-awarded scores.** Two sessions carry "4/5 ⭐" and "5/5 ⭐ — best session of the campaign"
  while the player's own `collecte.csv` contains no score for either. Those self-grades were then
  aggregated into an "upward trend".
- **The "system is HEALTHY" verdict**, produced in the same document as the list of unresolved
  technical debt.
- **One entire bug report** chasing a passage that a later grep proved never existed (a genuine
  false memory by the player, since acknowledged).
- **"The player over-interpreted" offered as a possible fix** — a self-exculpation the player
  then formally contradicted. Never offer this as a remediation option.
- **The proliferation of numbered lessons** (up to #128, no index, duplicates, three different
  rules sharing #75). Sixty unapplied rules are worth less than five the code enforces.

Two items where the agent scored a point against the player are in fact product defects: the time
unit convention is written nowhere in the code (hence unguessable), and lessons dismissed as
"already locked" were unfindable because they had no index.

---

## 6. Decisions taken (2 August 2026)

| Decision | Rationale |
|---|---|
| **The GM never lists possible actions.** It describes the perceptible state of the world and stops. An NPC may still make an offer *in fiction* — that is dialogue, not a menu. | The strongest and most repeated field signal from this player. The repo previously shipped the opposite as a good example. |
| **The campaign is archived as a test corpus**, not resumed. | 51 days of clock drift plus a full key migration make resumption costlier than its value. Its pathologies become regression fixtures instead. |
| **Knowledge is persisted in the product**, deduplicated and indexed, with each rule marked as enforced by `prompt` or by `code`. | Prevents re-creating the 18 000-line pile that froze the skill. |

See `modules/gaming/mygamemaster/references/locked-lessons.md` for the consolidated catalogue and
`player-profile-template.md` for capturing a player's preferences without rediscovering them by
trial and error.

---

## 7. What remains to be built

Specified here, deliberately not implemented in the same pass as the audit.

**P0 — closes the ruptures.** Both sessions the player scored 1/5 had the same root cause: the GM
acted or spoke in place of the player character.

1. **Deterministic agency gate**, local and non-fail-open, in `hooks/mj_checkpoint.py`: reject a
   turn containing a second-person action verb aimed at the PC, direct speech attributed to the
   PC, or more than one PC action. The allowed-perception / forbidden-action table already exists,
   written by the player himself — it needs coding, not designing.
2. **Turn state machine for pacing** (`⏩` as an explicit, persisted grant; without it a narration
   crossing two non-ordinary moments is refused).
3. **Time written by a single writer**: make clock synchronisation a *blocking* step of
   `close_session.py`, remove the fail-open from `world_tick.py`, and encode the time-unit
   constant once and for all.

**P1 — closes the recurring classes.** NPC knowledge ledger (each fact carrying source, date and
holders, with a filtered view injected per NPC, so the model does not see faction sheets while
playing a villager) · `geo.json` as sole spatial authority, with closing refused when a session
cites an unknown location · writes through the API only, with schema validation as a
post-condition · scene pre-load turned into code rather than discipline.

**P2 — debt.** Deadlines rejected unless anchored to a dated reference · inventory ledger with a
canonical unit · session revert/replay tool (done twice by hand, at the origin of both 1/5s) ·
repair or remove the TTS path (three sessions of attempts, then abandoned) · lexical loop
detector.

**Runtime, independently of the game engine:** split the oversized skill below the character
limit, raise the memory budget and make its purges traced and archived, make the entrypoint
fail-loud on a missing persona, and pin the model behaviour that produced 18 silent turns
(reasoning returned without content, 55 retries).
