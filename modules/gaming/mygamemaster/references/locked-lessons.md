# Locked Lessons — consolidated GM conduct catalogue

Derived from 34 sessions of real play with a single demanding player (one campaign, S1→S34),
consolidated from ~95 distinct written statements spread over 55 lesson files and one
2 600-line intention log. Proper nouns removed; roles used instead (the PC, the companion,
the mystic NPC, the guide NPC).

## How to add a rule (read this before editing)

1. **One rule lives in exactly one place** — this file. Never restate it in a `SKILL.md`; link the ID.
2. **IDs are thematic and stable** (`AGENCY-03`, `TIME-02`). Never renumber, never use a session number or a global counter — the old `#1…#128` numbering collapsed (three different rules held `#75`).
3. **A new observation edits an existing rule** unless no rule covers it; only then append a new ID at the end of its family.
4. **Hard cap: 65 rules, one line each.** Reaching the cap means merge, not append — the worked example, the verbatim and the session story go to the campaign log, never here.
5. **Every rule declares two columns, and they are not the same claim.** `Enforced today` is falsifiable: it reads `code` only when a deterministic check in this repo *refuses the violating outcome*, and the row then names the artifact (file, plus function or check id) so a reader can go and break it. Everything else reads `prompt`, including code that only warns — opt-in, fail-open or advisory code is not enforcement, the corpus locked that lesson itself (TIME-04). `Target` is the intention: who *should* own the rule. When the two differ the target is written in **bold** and the row is open debt; when they match, nothing is emphasised. **One carve-out, stated here so the asymmetry is a rule and not an oversight:** a check that owns a discrete lifecycle step — today only `close_session.py` at wrap-up — reads `code` when it refuses *inside* that step, even though the step itself is prompt-invoked; the invocation gap is then logged once, as its own debt, in the fail-open inventory. A helper with no defined trigger point (`roll.py`, callable at any moment or never) does not qualify. Read every `code` in this file as "refuses at close, if close is run".
6. **Never promote a rule to `code` because code was merged nearby.** Promote it the day the check refuses. Written-only rules recidivate: the corpus shows 8 agency violations committed within one hour of writing the rule that forbade them — and a check that cannot say no is a written rule with a runtime cost.

Artifacts are named by file basename: scripts live in this module's `scripts/` directory, runtime
hooks in `hooks/`.

## Bug classes

| Code | Class |
|---|---|
| BC-AGENCY | GM acts, speaks or feels for the player character |
| BC-PACING | Turn granularity; time or space advanced without permission |
| BC-MENU | GM offers actions, options or questions to the player |
| BC-KNOW | A character knows what no played scene taught them |
| BC-TIME | Temporal drift; unanchored durations |
| BC-SPACE | Invented, contradicted or unpromoted geography |
| BC-FLAT | Passive NPCs, world that does not run |
| BC-INVENT | Canon built on vague or mistyped player input |
| BC-LOOP | Lexical repetition, flat prose, empty payoff |
| BC-DATA | Corrupted, unpersisted or unsynchronised canon |
| BC-CHANNEL | Meta pollution, silent turn, wrong thread |
| BC-RES | Untracked objects, food, inventory |
| BC-CLOSE | Closing discipline |

---

## TIER 0 — Violation destroys the session

The only two rejected sessions of the corpus (one cancelled outright, one replayed in full) have
the same root cause: the GM acted or spoke in place of the player character. Everything in this
tier is that same wound, plus the turn protocol the player wrote himself to contain it.

| ID | Rule | Class | Enforced today | Target | Evidence |
|---|---|---|---|---|---|
| **AGENCY-01** | Never write an action, gesture, posture, gaze, breath or movement of the PC — write only what the PC perceives. | BC-AGENCY | `prompt` — `llm_judge.py` rubric AGENTIVITE flags it, but the judge is opt-in (`meta.hooks.judge.actif`), fail-open and never blocks | **`code`** | S16 (cancelled), S23 (replayed), re-broken S26, S30 ×3 |
| **AGENCY-02** | Never put words in the PC's mouth: when the player gave substance without text, emit `[VERBATIM TO BE SUPPLIED BY THE PLAYER]`. | BC-AGENCY | `prompt` — same judge rubric covers imposed PC dialogue; nothing emits the placeholder | **`code`** | S21, S23 |
| **AGENCY-03** | Narrate at most one PC action per turn, and only the direct execution of an action the player has just declared — cite the declaration. | BC-AGENCY | `prompt` — nothing counts PC actions per turn | **`code`** | S14 (3 stacked), S16 (8 stacked), S23 (4 chained) |
| **AGENCY-04** | An announced intention is not an execution: narrate the moment, never the consequence chain it implies. | BC-AGENCY | `prompt` | `prompt` | S23 (whole bivouac narrated on an intention) |
| **AGENCY-05** | Anchor the PC's inner state through perception only, log a player's meta-thought as a director's note rather than voicing it, and never draw the moral of a scene. | BC-AGENCY | `prompt` | `prompt` | S24, S24–S27 |
| **AGENCY-06** | Callbacks and corrections belong to the player: never pre-empt a mirrored gesture or quoted echo, and when the player replays an action you invented, narrate it faithfully without meta-commenting. | BC-AGENCY | `prompt` | `prompt` | S23 |
| **AGENCY-07** | Purely narrative questions are yours to settle alone (timing, titles, branch names); PC decisions never are. | BC-MENU | `prompt` | `prompt` | S26 |
| **AGENCY-08** | Take the player's input literally and never extrapolate it ("I fall asleep" is not "you keep watch until dawn"). | BC-AGENCY | `prompt` | `prompt` | S24 |
| **TURN-01** | One non-ordinary moment = one STOP = one logged action: never cross two non-ordinary moments in a single narration, and stay at the same STOP through dialogue sub-stops until the player gives an explicit decision. | BC-PACING | `prompt` — nothing counts moments or STOPs | **`code`** | S23 (5 moments, 1 STOP), S25 |
| **TURN-02** | Advance in time or space only after an explicit fast-forward signal — a discussion, a question or an intention is not one — and ask "what do you do?" before any ellipse longer than about an hour of game time. | BC-PACING | `prompt` — no fast-forward signal is parsed anywhere | **`code`** | S17, S23 |
| **TURN-03** | End every turn on a STOP that states the world's condition — never a menu, a suggested action, a list, or a question to the player. | BC-MENU | `prompt` — no check reads the end of a narration; `SKILL.md` §6.6 is the only enforcer | **`code`** | S12, re-asserted S24, S25 |
| **TURN-04** | Treat the player's silence at a STOP as a valid decision to follow the default flow — neither permission to advance nor an invitation to decide for him. | BC-PACING | `prompt` | `prompt` | S23 |
| **TURN-05** | Distinguish a decision-STOP (wait for the player) from an event-STOP (narrate actively): NPCs act, refuse and negotiate on their own, and never need the player's validation. | BC-PACING | `prompt` | `prompt` | S23, S24 |
| **TURN-06** | When a fast-forward lands on a focal event, narrate that event in a few sentences and stop — no follow-on conversation, inventory or interiority. | BC-PACING | `prompt` | `prompt` | S34 |
| **TURN-07** | Run the pre-narration checklist before writing a single line of narration. | BC-AGENCY | `prompt` | `prompt` | S23 close, S25 |

### The checklist (TURN-07) — single canonical copy

| # | Question | Verdict |
|---|---|---|
| 1 | What is the player input? | action / decision / fast-forward / silence / question |
| 2 | How many actions in my narration? | target 1 — if "then" or "and so", cut |
| 3 | Am I making the PC act? | forbidden — perceptions only |
| 4 | Am I inventing PC dialogue? | forbidden — substance or placeholder |
| 5 | Am I concluding? | forbidden — no "and so", no "finally" |
| 6 | Am I chaining consequences? | forbidden — 1 input = 1 moment = 1 STOP |
| 7 | Is every NPC I make speak or comment physically present, and was he present at the event? | verify before writing |
| 8 | Final STOP | world state only — no option, no question |

Input → narration mapping: declared action → one narrated action → STOP · decision → one immediate
consequence → STOP · fast-forward → skip to the next non-ordinary scene → STOP · silence → default
flow → STOP · question → one answer → STOP.

---

## TIER 1 — Violation produces a coherence bug the player catches

| ID | Rule | Class | Enforced today | Target | Evidence |
|---|---|---|---|---|---|
| **KNOW-01** | Before a character says or knows anything, trace SOURCE → PATH → DATE → REASON, and verify he was physically present at the event he comments on; without a source in a played scene, he does not know it. | BC-KNOW | `prompt` — `llm_judge.py` rule B2 is opt-in, fail-open and lenient by design ("doubt → VALID") | **`code`** | S16, S22, S32 |
| **KNOW-02** | GM knowledge is not character knowledge: faction sheets, secrets and off-screen outcomes are invisible to any character who did not live a scene that taught them. | BC-KNOW | `prompt` — `build_brief.py` builds NPC-agent briefs from an allow-list, so GM fields never reach an NPC agent; nothing guards the GM's own narration | **`code`** | S32 (faction outcome attributed to the PC) |
| **KNOW-03** | Never expose GM secrets and never use meta vocabulary in fiction — say "N days ago", not "day N" or "session". | BC-KNOW | `prompt` | `prompt` | S9 |
| **KNOW-04** | Document an NPC's supernatural powers, their limits and their origin in the NPC sheet before the first narrative use. | BC-KNOW | `prompt` | `prompt` | S16 (mystic NPC improvised perception) |
| **KNOW-05** | When the player's wording is vague, ambiguous or possibly a typo, ask — never build a mystery, a hook or a scheduled event on it. | BC-INVENT | `prompt` | `prompt` | S34 (four-session arc built on a typo) |
| **KNOW-06** | Persist a player's doubt as a doubt with an explicit epistemic status (fact / hypothesis / open contradiction); never promote it to established fact. | BC-INVENT | `prompt` | `prompt` | S23 |
| **KNOW-07** | When you settle an ambiguity you will not reveal, record the chosen reading in a dedicated commit field: a locked *interpretation* changes only on an in-game event, while a *factual error* is always correctable. | BC-KNOW | `prompt` | `prompt` | S27, S28, S33 |
| **TIME-01** | Anchor every temporal reference to an explicit game day plus its real date, reject any deadline expressed as a vague duration, and re-anchor an existing sheet to the session that created it — not to today. | BC-TIME | `prompt` — `check_session.py` sees vague deadlines (`echeance_non_parsable`) but files them as informational, never blocking | **`code`** | S17 (four cascading calendar patches) |
| **TIME-02** | Check every NPC line about season, weather or climatic urgency against the current fiction day; never use a generic seasonal formula. | BC-TIME | `prompt` | `prompt` | S16 |
| **TIME-03** | One writer owns game time: synchronise every temporal file after each ellipse and at close, before narrating anything further. | BC-TIME | `prompt` — `close_session.py` runs `clock.py` in dry-run at point P5 with `bloquant=False`: drift is reported, nothing is synchronised or refused | **`code`** | S17 (8-day drift over 10 sessions), S19, S29, S33 |
| **TIME-04** | Fail-open is not coherence — a script that does not crash may be hiding drift, so check the output, never the return code. | BC-TIME | `prompt` — the rule that names the failure mode is itself unenforced; see the fail-open inventory below | **`code`** | S17 |
| **SPACE-01** | Never invent a space (room, door, bed, annex) that was not built in play, and re-read your previous description of a place before re-describing it — any change requires an explicit narrative justification. | BC-SPACE | `prompt` — `scene_brief.py` supplies the place sheet fail-open; no check compares two descriptions of the same place | **`code`** | S17 (fire count), S22 (invented room) |
| **SPACE-02** | A teaser mentions only what lies ahead of the party and hooks rather than announces: recompute the position of recently seen NPCs before placing them in it. | BC-SPACE | `prompt` — `geo_query.py` can recompute positions on demand; nothing reads the teaser | **`code`** | S11, S18 |
| **AUDIT-01** | Read the files, never your memory: corroborate any assertion against at least three independent canonical sources, reproduce the canon's literal wording without widening its scope, and verify each item individually before any cascading change. | BC-DATA | `prompt` | `prompt` | S22, S28, S33 |
| **AUDIT-02** | A "FIXED" label or a "PATCHED" print is a claim, not a state — re-read the file after every write. | BC-DATA | `prompt` — `post_tool_call.py` does re-read and diff every campaign write, but the delta surfaces to the GM only at DEBUG/TRACE and the hook is fail-open by contract | **`code`** | S30, S32 |
| **AUDIT-03** | When the player submits a multi-bug audit, check every item against the files, patch only what is genuinely broken, and demonstrate false positives with evidence rather than patching them away. | BC-DATA | `prompt` | `prompt` | S23, S28 |
| **AUDIT-04** | Never report a modification you did not perform, and never defer: no "in progress", no "I'll do it after" — deliver in the same turn. | BC-DATA | `prompt` | `prompt` | S17 |
| **AUDIT-05** | After any correction to canon (group composition, status, name), run a full-text sweep across every data file before considering it done. | BC-DATA | `prompt` — no sweep exists | **`code`** | S22 (one error propagated into 4 files) |

---

## TIER 2 — Violation flattens the world or pollutes the channel

| ID | Rule | Class | Enforced today | Target | Evidence |
|---|---|---|---|---|---|
| **WORLD-01** | Give every active NPC at least one logged scene or dated note per game day — including during ellipses — prioritising NPC↔NPC interaction over NPC↔PC. | BC-FLAT | `prompt` — `world_tick.py post` runs at close but is explicitly non-blocking and gated on `actors.json` | **`code`** | S13, S28, S33 (125 notes written retroactively) |
| **WORLD-02** | Give each NPC an explicit drive and play it unprompted; a drive that is never exercised is a failed drive. | BC-FLAT | `prompt` | `prompt` | S28 |
| **WORLD-03** | Promote every recurrence into canon: a place played in a session must exist in the world geography before close, an NPC, object or sign reaching three appearances gets a sheet, and any change to a place updates its record. | BC-SPACE | `code` — `check_session.py` `lieu_absent` / `pnj_sans_fiche` (blocking), gating `close_session.py` points P1/P2; the three-appearances threshold is not counted | `code` | S18–S23 (5 orphan places), S28 |
| **WORLD-04** | Faction clocks are alive, not statuses: an event whose date has passed cannot stay "scheduled" — narrate WHO / WHAT / WHY / CONSEQUENCE, or cancel it explicitly. | BC-FLAT | `code` — `check_session.py` `echeance_depassee` (blocking), plus `close_session.py` P3/P4 read directly from `world.json`; a free-text deadline stays informational (`echeance_non_parsable`) | `code` | S33 |
| **WORLD-05** | The world runs without the PC: a missed opportunity is a legitimate outcome, not a bug to repair. | BC-FLAT | `prompt` | `prompt` | S18 (validated by the player) |
| **WORLD-06** | Give any newly introduced NPC an entry score of at least two actions, and never let an NPC cross a scene without acting, being perceived and leaving a trace. | BC-FLAT | `prompt` | `prompt` | S14, S30, S31 |
| **WORLD-07** | Before narrating a scene, load in the same turn the place sheet, the sheet of every present NPC including their background actions, the calendar, the open threads and the GM secrets. | BC-FLAT | `prompt` — `scene_brief.py` is read-only and strictly fail-open, and `pre_llm_call.py` skips it entirely when the current location is unknown | **`code`** | S16 (place described from memory), S31 |
| **WORLD-08** | Structure every ellipse as: spare routine summary, landing on a meaningful event involving at least one active NPC, closing hook, STOP — and never chain two ellipses without player input. | BC-PACING | `prompt` | `prompt` | S33 |
| **WORLD-09** | Default to one line per NPC per input, extend into a full cascade (each NPC speaks once, closed by a one-line gesture and a STOP) when the player asks or the scene requires it, and let no NPC react to the PC without a prior gesture toward them. | BC-FLAT | `prompt` | `prompt` | S31, S33 (player override) |
| **WORLD-10** | Use a talkative NPC as an indirect channel toward a closed one, and keep delegation matter-of-fact: the NPC proposes in one sentence, the PC decides. | BC-FLAT | `prompt` | `prompt` | S18, S23 |
| **WORLD-11** | Play a social verb in three phases — formulation, reception, individual response from each NPC — and never collapse it into a unilateral outcome, nor over-socialise a unilateral verb. | BC-FLAT | `prompt` | `prompt` | S24, S25 |
| **META-01** | Treat any question addressed by name to an NPC present in the scene as in-character by default, absent an explicit meta signal; a formal register is not a meta signal. | BC-CHANNEL | `prompt` | `prompt` | S27, S28 |
| **META-02** | "We are not in game" is an immediate hard stop, and "decide" or "do what you want" keeps the meta channel open — neither of them starts narration. | BC-CHANNEL | `prompt` | `prompt` | S26, S28 |
| **META-03** | Answer a substantive meta question in the same turn, with a visible answer before any tool call; verification happens silently around the answer, never instead of it. | BC-CHANNEL | `prompt` — nothing observes the shape of a turn | **`code`** | S34, S35 (two empty turns) |
| **META-04** | After the narration's STOP send nothing else into the player channel — no recap, no internal audit, no "I'm waiting", no system block — and always reply in the exact thread the player wrote in. | BC-CHANNEL | `prompt` — `transform_llm_output.py` `_scrub_player_channel` strips code fences and tracebacks and keeps the Steward block internal outside DEBUG/TRACE; a prose recap passes untouched, and the thread is not checked | **`code`** | S32 (3 reminders in one session) |
| **META-05** | Admit an in-scene error in four columns — verify silently, admit, patch at the implicit signal, resume the scene without commenting the patch. | BC-CHANNEL | `prompt` | `prompt` | S24, S25 |

---

## TIER 3 — Violation costs one patch, never a session

| ID | Rule | Class | Enforced today | Target | Evidence |
|---|---|---|---|---|---|
| **STYLE-01** | Count your verbal tics: at most two occurrences of the same lemma or formula per response and one signature phrase per session — switch to a synonym or to silence at the second temptation. | BC-LOOP | `prompt` — no lemma counter exists | **`code`** | S21, S28, S29, S30, S34 (explicit penalty) |
| **STYLE-02** | Keep a voice sheet per active NPC (qualities, flaws, signature phrase and gesture, behaviour under solemnity / tension / tenderness / refusal, what he leaves unsaid, what he does alone) and consult it before every line he speaks. | BC-LOOP | `prompt` | `prompt` | S21 |
| **STYLE-03** | Never place a strongly charged word adjacent to an NPC's name in a status table; every column must read correctly on its own. | BC-CHANNEL | `prompt` | `prompt` | S27 |
| **STYLE-04** | Play fatigue, pain and physical state during the effort rather than afterwards, and never let a bodily cue drown inside a technical exchange. | BC-LOOP | `prompt` | `prompt` | S11, S14 |
| **STYLE-05** | Calibrate a payoff to the player's cumulative investment — a proportional payoff carries all three of a tangible object or change, a new piece of knowledge, and a felt answer; restraint is not emptiness. | BC-LOOP | `prompt` | `prompt` | S27, S28 |
| **MECH-01** | Roll before narrating any uncertain outcome, give the result as narration without the raw number, never dress a failure as a success, and resolve conflict with a real roll instead of a pre-decided outcome. | BC-RES | `prompt` — `roll.py` rolls real dice and applies the natural-die rule mechanically, but nothing requires the GM to call it | **`code`** | S12, S13, S25, S28–S34 |
| **MECH-02** | Offer visible travel rolls for each leg (descent, march, orientation, watchfulness, crossing) against a fixed difficulty ladder, with numbers disclosed only on request. | BC-RES | `prompt` | `prompt` | S25 (strongest positive signal of the corpus) |
| **MECH-03** | Express every ration stock in person-days and divide by group size, and route every object transfer through a ledger write rather than through prose. | BC-RES | `prompt` — no ledger write path exists for object transfers | **`code`** | S15, S23 |
| **DATA-01** | Write canon only through the API scripts with schema validation as a post-condition, using a unique anchor per patch; never hand-edit structured data and never use a blind replace-all. | BC-DATA | `prompt` — `validate_json.py` and `validate_schema.py` refuse malformed or schema-deviant canon at close, never a hand-edit or a blind replace-all that yields valid JSON; the write-time post-condition `garde_json_strict` is off by default, and `pre-commit.hook` is an opt-in template with an `MGM_SKIP_HOOK=1` bypass | **`code`** | S23 (two JSON corruptions) |
| **DATA-02** | Keep one canonical channel: any play that happened outside the instrumented channel must be re-integrated as a structured report, in the same format as a logged session, before close. | BC-DATA | `prompt` — nothing detects play that happened off-channel | **`code`** | S20, S21 (sessions played, files empty) |
| **DATA-03** | When the player states a rule of play, apply it in the data, trace it in the log, and promote it into the world rules file — the log alone does not make it discoverable. | BC-DATA | `prompt` | `prompt` | S23, S24 |
| **CLOSE-01** | Trigger close from state and never from intention, refuse to close while any violation flag is open, generate the teaser only after the temporal sync, and pair every significant patch with a snapshot, a replayable audit script and a log entry. | BC-CLOSE | `code` — `close_session.py` refuses (exit 1) as soon as one blocking point fails; the teaser ordering and the snapshot/audit/log triplet are not checked | `code` | S22, S23, S21→S22 teaser desync |

---

## Repealed, superseded or withdrawn

Kept visible so they are not rediscovered. Never reinstate without a new player decision.

| Former statement | Status | Replaced by |
|---|---|---|
| "Offer 3–4 options at the STOP" (original pre-narration checklist, item 7) | **Repealed.** Confirmed product decision: the GM describes the world's state and stops; he never lists actions. | TURN-03 |
| "STOP format = `You can: — option 1 — option 2 — fast-forward — something else. What do you do?`" (locked and un-locked the same day in two different lesson files) | **Repealed** — purge the block wherever it survives; an agent loading only that file reproduces the bug. | TURN-03 |
| Product prompt still teaching an option menu ("the scenery is before you, options are visible — what do you do?" / "NPCs can propose options") | **Removed from the shipped prompt** (PR #18). `SKILL.md` §6.6 now opens on "NO OPTIONS MENU — absolute rule"; the old wording survives there only as a ❌ counter-example, and an NPC offer inside the fiction is explicitly not a menu. | TURN-03, AGENCY-07 |
| "One NPC dialogue per player input" | **Overridden by the player** in S33 ("don't hesitate to make them participate"); survives only as the *default*, not as a ceiling. | WORLD-09 |
| Global lesson numbering `#1…#128` | **Abandoned.** Three unrelated rules held `#75`; the multi-NPC override held two numbers; the preference series and the lesson series collided at 21–26. | Thematic IDs in this file |
| "The GM may narrate a PC action when it is traceable or justifiable" | **Superseded** — the exception is now bounded and must cite the player's declaration. | AGENCY-03 |
| "TTS on" in the original player profile | **Not a preference.** The player locked TTS off after a runtime failure (renderer blocked, degraded fallback voice); record it as a broken feature, not as taste. | — |
| "The player over-interpreted" as a repair option in a bug analysis | **Withdrawn** — the player formally recorded the point as a defect; never offer this as a fix. | AUDIT-03 |
| Under-documentation complaint about an NPC quoting troop numbers | **Closed by the player** ("his question is legitimate"). | — |
| Chronology bug reported in S19 | **Withdrawn** — player false memory; the passage does not exist in the canonical log. | — |
| Self-assigned session scores aggregated into a quality trend | **Not evidence.** Only player-issued evaluations count. | — |
| "27 rules are applied by `code`" (former single "Applied by" column) | **Withdrawn** — three were, and only at close. The column stated an intention as a state, in the very file that diagnoses that failure mode; it is now split into `Enforced today` and `Target`. | This file's preamble, rule 5 |

---

## Campaign-specific — keep in campaign data, never in the product

These carry the values a rule consumes; the rule itself is above. One line each is enough.

| Item | Parent rule | Home |
|---|---|---|
| Calendar anchors: day 1 real date, solstice day, frost counter, dawn offset constant | TIME-01 | world state, in-game calendar |
| Cabin floor plan and built-spaces record (single room + lean-to, one door, who sleeps where) | SPACE-01 | place record + NPC sheet |
| Travel party composition and who stayed behind | AUDIT-05 | world quest record |
| Mystic NPC's powers, limits ("the signs, not the origins") and their origin | KNOW-04 | NPC sheet |
| NPC voice sheets and their signature phrases and gestures | STYLE-02 | NPC sheet |
| Animal companion policy ("answers when there is no danger", "he is not yours") | DATA-03 | NPC sheet |
| Guide NPC's delegation: principal guide and decider, revocable at any time, mutual | WORLD-10 | NPC role record |
| Unresolved NPC/temple ambiguity, deliberately kept open | KNOW-06 | NPC hypotheses field |
| Six canonical mystic sign types and their vocabulary | KNOW-07 | world canon |
| Ration convention text (person-day) | MECH-03 | world rules |
| Canonical camp layout (three equidistant fires on the bank) | SPACE-01 | place record |
| GM-only mystery attached to a companion NPC, disclosure forbidden | KNOW-02 | NPC sheet + coherence test |
| Watched tic-word list for this campaign | STYLE-01 | world style meta |
| Discord channel and thread identifiers | META-04 | deployment config |

---

## Enforcement summary

| Tier | Rules | `code` today | `prompt` today | Target `code` | Open debt |
|---|---|---|---|---|---|
| 0 — session-destroying | 15 | 0 | 15 | 6 | 6 |
| 1 — canon integrity | 18 | 0 | 18 | 9 | 9 |
| 2 — living world & channel | 16 | 2 | 14 | 6 | 4 |
| 3 — style, mechanics, data | 12 | 1 | 11 | 6 | 5 |
| **Total** | **61** | **3** | **58** | **27** | **24** |

The three rules a deterministic check actually refuses today — all three at close, and only once
`close_session.py` is actually invoked, which `SKILL.md` §4 (data governance) asks the GM to do but
nothing forces: **WORLD-03** (`check_session.py` `lieu_absent` / `pnj_sans_fiche`, gating `close_session.py`
P1/P2), **WORLD-04** (`check_session.py` `echeance_depassee`, plus P3/P4 read directly in
`close_session.py`) and **CLOSE-01** (`close_session.py` exit 1). Every one of them guards *canon at
rest*; not one guards a narration in flight, and not one runs unless the GM asks for it.

The five highest-recidivism rules — agency (8 reported violations), temporal drift (7
rediscoveries), lexical loops (8 rediscoveries), verification discipline (6), empty meta turns (4)
— all target `code`, and none of them is enforced by code today. They were written down repeatedly
and still recurred; text is not an enforcement mechanism, and neither is a check that cannot refuse.

### Code that exists but does not enforce

Named so the debt is worked, not rediscovered. None of these refuses the violating outcome on its
own — either because it cannot say no, or because nothing guarantees it is ever asked.

| Artifact | Rule it was written for | Why it does not count |
|---|---|---|
| `close_session.py` itself, the host of every `code` row above | CLOSE-01, WORLD-03, WORLD-04 | it refuses correctly once it runs, but no hook, no CI step and no automation invokes it — `SKILL.md` §4 asks the GM to run it at close ("Run this script at close"), and a GM who declares the session closed from intention never triggers a single check |
| `validate_json.py` and `validate_schema.py` at close | DATA-01 | they refuse malformed or schema-deviant canon, not a hand-edit or a blind replace-all that yields valid JSON — `validate_schema.py` is tolerant by design (`additionalProperties: true` everywhere) |
| `pre-commit.hook`, installed by `install-hooks.sh` | DATA-01 | a template, live only once copied into `.git/hooks/`; checks JSON *syntax* only and honours an `MGM_SKIP_HOOK=1` bypass |
| `llm_judge.py` (rubric AGENTIVITE, B2) and the `mj_checkpoint.py` gate | AGENCY-01/02, KNOW-01/02 | opt-in (`meta.hooks.judge.actif`, off by default), fail-open on any error, and the gate forces the turn through after `gate_max_tentatives` attempts |
| `clock.py` at close, via `close_session.py` point P5 | TIME-01, TIME-03 | run in dry-run, and P5 carries `bloquant=False`: drift is printed, never synchronised, never refused |
| `world_tick.py post` at close | WORLD-01 | documented non-blocking; gated on `actors.json` and on the `temporality` feature axis |
| `scene_brief.py`, injected by `pre_llm_call.py` | WORLD-07, SPACE-01 | strictly fail-open (minimal brief, exit 0) and skipped entirely when the current location is unknown — the turn then narrates from memory |
| `post_tool_call.py` | AUDIT-02 | re-reads and diffs every campaign write, but the delta reaches the GM only at DEBUG/TRACE, and the hook is fail-open by contract |
| `_scrub_player_channel` in `transform_llm_output.py` | META-04 | strips code fences and tracebacks; a prose recap after the STOP passes untouched |
| `garde_json_strict` in `pre_tool_call.py` | DATA-01 | the only write-time validation post-condition, and it is off by default — corruption is caught later, at close, and only if it broke the syntax or the schema |
| `roll.py` | MECH-01 | rolls real dice and applies the natural-die rule, but nothing requires the GM to call it |

## The prompt core

If only five sentences reach the shipped prompt, these, in this order:

1. You never make the player's character act, speak or feel. You describe what he perceives. *(AGENCY-01/02/03)*
2. One player input = one moment = one STOP. You stop and you wait. The fast-forward signal is the only permission to advance. *(TURN-01/02)*
3. At the STOP you describe the state of the world. You propose nothing and you ask nothing. *(TURN-03)*
4. A character knows only what a played scene taught him. What you know is not what he knows. *(KNOW-01/02)*
5. You read the sheets before narrating, never your memory. *(WORLD-07, AUDIT-01)*
