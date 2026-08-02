# Player Profile — template

A campaign that does not keep this file rediscovers its player's preferences by trial and error,
one rejected session at a time. Fill it from the first session; update it at every close.

## Rules for this file

1. **One entry = one line, dated, sourced to a session.** An unsourced preference is a guess.
2. **Status is explicit**: `locked` (the player stated it as a standing rule) · `observed` (inferred from repeated reactions) · `hypothesis` (to confirm). Only `locked` entries override a default.
3. **A preference born from a broken feature is not a preference** — record the outage, not the taste.
4. **Never delete, supersede.** Keep the old line with its replacement, like the repealed section of the rule catalogue.
5. **This file holds taste, not doctrine.** Universal GM rules belong in `locked-lessons.md`; only what is specific to *this* player lives here.

---

## 1. Identity and scope

| Field | Value |
|---|---|
| Player reference | `<handle or pseudonymous id>` |
| Campaign | `<name>` |
| Sessions covered | `<S1 → Sn>` |
| Player characters | `<PC, companions with dedicated sheets>` |
| Last updated | `<date, session>` |

## 2. Control signals

The vocabulary the player uses to steer pacing and mode. Fill even if empty — an undeclared
signal set means the GM is guessing when to advance.

| Signal | Meaning | Required GM response | Status |
|---|---|---|---|
| `<advance signal>` | | | |
| `<pause / meta signal>` | | | |
| `<resume signal>` | | | |
| `<bug-audit trigger>` | | | |
| `<session open / close triggers>` | | | |
| Silence at a STOP | | | |
| `<per-input rating tokens>` | | | |

## 3. Agency contract

The single most expensive axis. Answer explicitly, do not default.

| Question | Answer | Status |
|---|---|---|
| May the GM narrate a PC action the player did not declare? | | |
| May the GM write PC dialogue from substance the player gave? | | |
| Who decides purely narrative questions (timing, titles, branch names)? | | |
| May the GM voice the PC's feelings or draw a scene's moral? | | |
| How many PC actions per turn? | | |
| What happens on a violation (patch / rollback / replay)? | | |

## 4. Pacing and verbosity dials

| Dial | Setting | Status |
|---|---|---|
| Turn granularity (moments per narration) | | |
| Ellipse length tolerated without asking | | |
| Ellipse form expected | | |
| STOP format | | |
| Scene length / prose density | | |
| Number of NPCs speaking per input | | |

## 5. What the player likes

| # | Preference | Evidence (session, verbatim or reaction) | GM implication | Status |
|---|---|---|---|---|

## 6. What the player dislikes

| # | Rejection | Evidence | GM implication | Status |
|---|---|---|---|---|

## 7. Standing policies declared by the player

Permanent instructions that must be applied without asking again. Each one is also promoted into
the world rules file (see `DATA-03`).

| Policy | Declared at | Where it is persisted | Status |
|---|---|---|---|

## 8. Feedback protocol

| Field | Value |
|---|---|
| Evaluation format the player uses | |
| Granularity (per input / per session) | |
| Expected GM reaction to a negative rating | |
| Expected error-admission format | |
| Replay / rollback procedure he endorses | |

## 9. Validated positives — do not break

Things explicitly praised. A refactor that removes one of these is a regression even if every rule
still passes.

| Element | Session |
|---|---|

## 10. Change log

| Date | Session | Entry added / superseded | Trigger |
|---|---|---|---|

---

# Worked example — Player A, 34 sessions

Filled from a real corpus. Proper nouns removed; roles used instead.

## 1. Identity and scope

| Field | Value |
|---|---|
| Player reference | Player A (single-player table) |
| Campaign | low-fantasy, contemplative-domestic register |
| Sessions covered | S1 → S34 (81 in-game days) |
| Player characters | one PC; two companion NPCs given dedicated character sheets at the player's request |
| Last updated | S34 |

## 2. Control signals

| Signal | Meaning | Required GM response | Status |
|---|---|---|---|
| `⏩` | Ellipsis up to the next non-ordinary moment — **not** "narrate the next chunk", **not** "conclude the scene" | Summarise the routine, land on one meaningful event with an active NPC, hook, STOP | locked (S23, re-locked S24) |
| `⏸️` | Immediate meta stop — a violation is in progress | Leave fiction at once, answer in the meta register, do not narrate | locked (S23) |
| `!analyse-bug` | Targeted audit request | Verdict + patch in the same turn, false positives proven with evidence | locked |
| `!reprendre` / `!cloture` | Session open / close | Close is state-driven, refused while a violation is open | locked |
| Silence at a STOP | **A decision**: follow the default flow | Continue the default flow at the same granularity; never read it as permission to advance | locked (S23) |
| `+1` / `-1` | Per-input evaluation, aggregated at close | A `-1` requires an admission and a patch, not a defence | locked (S14 → S34) |

## 3. Agency contract

| Question | Answer | Status |
|---|---|---|
| May the GM narrate an undeclared PC action? | No — including "obvious" ones (getting up, sitting down, smiling), including after being woken, including during sleep or trance | locked (S16, S26, S30) |
| May the GM write PC dialogue from substance? | No — emit a verbatim placeholder | locked (S23) |
| Who decides purely narrative questions? | The GM, alone, without a menu — "you decide the narrative questions", "choose, titles don't interest me" | locked (S26) |
| May the GM voice the PC's feelings? | No — perception only; the player draws his own morals and plays his own vulnerability | locked (S18, S24) |
| PC actions per turn | One, and only the execution of what was just declared | locked |
| Response to violation | Rollback and full replay of the session, framed as `[Session-v2]` | locked (used twice: S16, S23) |

## 4. Pacing and verbosity dials

| Dial | Setting | Status |
|---|---|---|
| Turn granularity | One non-ordinary moment per narration; sub-stops inside a dialogue stay at the same STOP | locked |
| Ellipse without asking | Up to roughly one hour of game time; beyond that, ask | locked (S17) |
| Ellipse form | Routine summary (2–5 sentences) → landing on a meaningful event with ≥1 active NPC → hook → STOP; never two ellipses in a row | locked (S33) |
| STOP format | World state only — no options, no suggestions, no question, then silence | locked (S24, S25) |
| Scene length | Sober; short gestures; farewells in one gesture and one word | observed (S15, S18) |
| NPCs speaking per input | One by default, full cascade on request | locked (S31, overridden upward S33) |

## 5. What the player likes

| # | Preference | Evidence | GM implication | Status |
|---|---|---|---|---|
| 1 | **Choosing** — including gestures he would have made anyway | S16: "I'd probably have done the same, but you have to let me choose" | Never pre-empt, however predictable | locked |
| 2 | **Visible travel rolls** — mechanics beat invisible narration | S25: "it's better with the travel rolls" | Roll per leg against a fixed difficulty ladder; narrative result, numbers on request | locked, no exception |
| 3 | **Conflict between NPCs**, with no winner and no capitulation | S34: "don't hesitate to create conflict" | Resolve with a real roll, never a pre-decided outcome | locked |
| 4 | **Sobriety** — one gesture and one word rather than a speech | S15; "sober farewells are stronger than long speeches" | Cut the flourish, keep the concrete | observed |
| 5 | **Contemplative-domestic register** — hearth, wood, preserves, walls, first stone | S29, S33 | Give ordinary labour real texture | observed |
| 6 | **Legitimate consequences of his own inaction** | S18: an NPC left before he could speak to him — "I should have talked to him earlier" | Let the world run without the PC; do not repair missed opportunities | locked |
| 7 | **Structured feedback** — strong points / weak points, `+1`/`-1` per input | constant S14 → S34 | Provide the frame at close; keep the "PC actions without validation" section empty | locked |
| 8 | **The replay method** as a repair tool | "I found it was a good method" | Keep a reusable rollback-and-replay procedure, not an ad-hoc one | locked |
| 9 | **Sober error admission** — acknowledge, patch immediately, no minimising | recurring across the log | Four-column admission, then resume without commenting the patch | locked |
| 10 | **Precise inventory on demand**, with honest gaps | S29 | Answer from the ledger; admit holes rather than improvising | observed |
| 11 | **The GM settling narrative questions himself** | S26 | Decide, do not submit an A/B/C menu | locked |

## 6. What the player dislikes

| # | Rejection | Evidence | GM implication | Status |
|---|---|---|---|---|
| 1 | Acting, speaking or feeling for his PC | S16 cancelled, S23 fully replayed — the two rejected sessions of the corpus | Hard gate before delivery | locked |
| 2 | **Option menus** and suggested actions | S12, restated S24: "I don't like you proposing actions to me" | STOP describes the world, nothing else | locked |
| 3 | Advancing time without his permission | S23: "still no permission to switch to fast-forward — go back to midday" | Explicit signal only | locked |
| 4 | **Raw dice numbers** outside narration | S13: "narrative rolls only, never numbers" | Result as narration; numbers on request | locked |
| 5 | An **empty place** while the sheets are rich | S16 v2: "the ford wasn't alive enough" | Pre-load sheets and background actions before narrating | locked |
| 6 | An NPC knowing what he should not know | three separate bug analyses | Trace source, path, date, reason | locked |
| 7 | **Invented spaces** — "what would have been logical" is not "what was played" | S22 | Check the built-spaces record | locked |
| 8 | **Lexical repetition** | S21 (five tics counted), S34 (`-1` on one word repeated five times in a turn) | Max two occurrences per response | locked |
| 9 | Overshooting the **focal point** he chose | S34, `-1` | Narrate the focal event and stop | locked |
| 10 | **Meta vocabulary** in fiction ("day 15", "session") | S9 | Say "N days ago" | locked |
| 11 | **Spoilers in the teaser** | S11 | A teaser hooks, it does not announce | locked |
| 12 | Inventing a mystery on one of his clumsy phrasings | S34, a four-session arc built on a typo | Ask instead of canonising | locked |
| 13 | Being answered with silence while tools run | S34/S35, two empty turns, the question had to be repeated | Substantive answer in the same turn, before any tool call | locked |

## 7. Standing policies declared by the player

| Policy | Declared at | Where it is persisted | Status |
|---|---|---|---|
| Animal companion answers when there is no danger; "he is not yours, he is passing through" | S18 | NPC sheet | locked |
| Guide NPC stays master of his own actions and decisions; the delegation is the player's decision and revocable at any time | S23 | NPC role record | locked |
| Ration convention: stocks expressed in person-days, divided by group size | S23 | world rules — the player verified it had been written | locked |
| Name ethics: no nickname or role assigned to his PC; group nicknames stay internal to that group | S18 | NPC sheets | locked |
| NPCs interact with someone every day, including during ellipses | S33 | NPC journals | locked |
| Text-to-speech off | S13 | deployment config | **outage, not preference** — the renderer was blocked and the fallback voice degraded; revisit if repaired |

## 8. Feedback protocol

| Field | Value |
|---|---|
| Evaluation format | strong points / weak points, plus `+1` / `-1` per input, aggregated into a session evaluation |
| Granularity | per input, then per session |
| Reaction to a negative rating | acknowledge sobrely, patch in the same turn, log the lesson, no defence and no minimising |
| Error-admission format | four columns: what I wrote / what the canon says / why it is a bug / the patch — then resume the scene without commenting |
| Replay procedure | full session rollback framed as `[Session-v2]`, lessons re-locked at the opening of each subsequent session, "PC actions without validation" section must stay empty |

## 9. Validated positives — do not break

| Element | Session |
|---|---|
| Visible travel rolls | S25 |
| Three-NPC triangle where a talkative NPC opens up a closed one | S18 |
| Non-human companion with a declared policy | S18 |
| Name ethics — an imposed nickname refused | S18 |
| A concrete, chore-anchored NPC as the model for all NPCs | S13 |
| The world running without the PC, even when the frustration is his | S18 |
| Scene sobriety and short gestures | S19, S34 |
| Sober bug admission with no self-defence | recurring |

## 10. Change log

| Date | Session | Entry added / superseded | Trigger |
|---|---|---|---|
| — | S16 | Agency contract locked | session cancelled |
| — | S23 | Control signals, pacing dials, ration convention locked | session replayed in full |
| — | S24 | "No option menus" restated; supersedes the earlier "offer 3–4 options at the STOP" | explicit rejection |
| — | S25 | Travel rolls locked | explicit praise |
| — | S33 | "One NPC line per input" downgraded from ceiling to default | player override |
| — | S34 | Lexical-loop ceiling and focal-point discipline locked | two `-1` ratings |
