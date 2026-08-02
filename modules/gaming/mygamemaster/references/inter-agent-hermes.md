> ⚠️ **« profiles » mechanism OBSOLETE — agent CONCEPT remains valid.** NPC/Faction agents (level 2) are **approved** (activatable/deactivatable per campaign): the conceptual plan below (GM hub, memory/perception isolation, auditable brief, 🎭/🎯/❓/🔒 format) remains relevant. ONLY **provisioning via `hermes profile create`** is dead: the « profiles » functionality in Hermes does not work, replaced by **one container per agent** (see `README.md`, `docs/06-isolation-model.md`, `specs/profiles-to-containers.md`). Read the commands `hermes -p <slug>` / `hermes profile create` below as INTENT (one isolated agent per NPC) — the implementation target is a container, not a profile. Do NOT run `hermes profile create`.

# 🔄 Inter-agent Hermes Communication — Physical Mechanism

> Reference document. Describes how **MJ Tonnerre** physically communicates
> with its **NPC agents** and **Faction agents** via the Hermes infrastructure.
> Derived from the design validated in dry-run session (2026-05-25).

---

## 1. The Exchange Channel

**There is no real-time dialogue bus between agents.** Hermes does not expose
a conversational channel between two live sessions. The GM is the **hub**, and
the physical channel is **process invocation**:

```bash
REPONSE_PNJ=$(hermes -p pnj-<slug> chat -Q -q "<brief + contexte>" -c)
```

| Flag | Role |
|------|------|
| `-p pnj-<slug>` | Isolated NPC profile (memory, skills, separate sessions) |
| `-Q` (quiet) | Suppresses banner/info → stdout = pure response (🎭/🎯/❓/🔒), capturable |
| `-q "<...>"` | The only input for the turn — identity brief + scene context |
| `-c` (continue) | Resumes existing session → NPC remembers previous turns |

**All other exchanges go through the GM:**
- **NPC ↔ NPC**: never directly. The GM relays — they take NPC-A's output,
  decide what NPC-B perceives, and inject it into NPC-B's turn `-q`.
- **NPC ↔ Steward**: indirect. The GM takes the NPC's 🎯 INTENTION + its brief,
  and launches `delegate_task` to the Steward (disposable) which returns VALID/INVALID/TO_ARBITRATE.
- **NPC profile without `messaging` toolset** → physically unable to reach Discord.
  One voice to players = the GM.

---

## 2. Profile Isolation

Each NPC/faction has its **own Hermes profile**, cloned from `default`:

```bash
hermes profile create pnj-<slug> --clone-from default
```

The folder `profiles/pnj-<slug>/` contains:
- `SOUL.md` — NPC personality (fears, ambitions)
- `sessions/` — conversational history of THIS NPC only
- `memories/` — durable facts extracted automatically
- `config.yaml` — config overrides (memory, skills)

### Session Continuity

| Need | Command |
|--------|----------|
| Normal case (1 thread per NPC) | `hermes -p pnj-<slug> chat -c -q "..."` |
| Named stable thread (long campaign) | `hermes sessions rename <id> "<slug>-partie"` then `... chat -c "<slug>-partie" -q "..."` |
| Resume by exact ID (pinned in npcs.json) | `hermes -p pnj-<slug> chat --resume <id> -q "..."` |
| First turn (empty sessions/) | `hermes -p pnj-<slug> chat -q "..."` (creates thread; following turns = `-c`) |

---

## 3. How the NPC Perceives / Remembers / Interprets

### (a) What It SEES This Turn (perception)

Only the `-q` sent by the GM, assembled by `build_brief.py`:

```
build_brief.py <campaign> <npc>   → identity + established_facts + private_knowledge
                                   + limits + abilities + inventory
```
+
```
Scene context written by the GM
```

**Mechanically excluded:** `gm_hypotheses`, `gm_notes`, `gm_secrets`, data from
OTHER NPCs. This is the « no more, no less » — auditable with `--audit`.

### (b) What It REMEMBERS (conversational memory)

The history of its session (`profiles/pnj-<slug>/sessions/`). Resumed via `-c`:
past exchanges stay in context → the NPC naturally remembers what was said,
its decisions, the evolution of its relationship with the PCs.

**This is the profile's native continuity** — what `delegate_task` never gives.

### (c) Its LONG-TERM Memory (cross-session)

`profiles/pnj-<slug>/memories/`. The `memory` toolset writes durable facts there:

| Parameter | NPC Value | Global Value (default) |
|-----------|-----------|------------------------|
| `memory_enabled` | `true` | `true` |
| `nudge_interval` | 10 turns | 10 |
| `flush_min_turns` | 6 | 6 |
| `memory_char_limit` | **8000** | 2200 |

**Why 8000 for NPCs:** modern models have windows ≥200k tokens.
2200 is legacy from the 8k-32k era. A recurring NPC over a long campaign
needs more space for its durable memories.

### (d) How It INTERPRETS

The profile's LLM, guided by:
- Its `SOUL.md` (personality: fears, ambitions)
- The `mygamemaster-pnj` skill (protocol: golden rule, 🎭/🎯/❓/🔒 format, guardrails)

It reads its brief through its motivations and red lines → credible
and fallible reaction.

### ⚠️ Memory Trap

If the GM accidentally sent info outside the brief, the NPC's session would memorize it
(permanent spoiler). **Strict rule: everything that goes in must pass through `build_brief.py`.**
The source of truth remains files (`private_notes`, written via `faction_slice.py add-note`),
not volatile memory.

---

## 4. Automatic Context Compaction

Hermes has a native compaction engine: `context.engine: compressor` (config.yaml).

### Three Memory Nets — Nothing Is Lost

| Mechanism | What | Scope |
|-----------|------|--------|
| **Compaction** (compressor) | Summarizes session transcript | Short-term, within session |
| **Memory** (memories/) | Extracts durable facts outside transcript | Long-term, cross-session |
| **Files** (private_notes) | Versioned inner thoughts + brief reconstruction | Permanent, auditable |

When an old detail leaves the transcript via compaction, if it is important it has
normally already migrated to `memories/` (or `private_notes`). **Three nets →
nothing essential is lost over a long campaign.**

---

## 5. Concrete Trace of 2 Turns for the Same NPC

```bash
# Turn 5 — the GM wakes up blacksmith NPC pnj-barda (session already in progress)
brief=$(python3 build_brief.py jusquau-bout-de-mon-monde barda)
msg="$brief

[SCENE] The PCs enter your forge, covered in mud, and ask to repair a chipped blade."
rep=$(hermes -p pnj-barda chat -Q -q "$msg" -c)
# -c resumes ITS thread → they remember turn 3
# rep = 🎭 « Here you are again… » / 🎯 suggests a price / ❓ … / 🔒 « they're hiding something »

# → GM validates via Steward (delegate_task), weaves VALID, then:
python3 faction_slice.py add-note jusquau-bout-de-mon-monde --pnj barda "Suspects the PCs" --apply

# Turn 12 (7 turns later) — compressor summarized turns 1-6
# barda keeps the thread (who they are, their suspicion) without being reminded.
rep=$(hermes -p pnj-barda chat -Q -q "$brief
[SCENE] A PC returns alone, at night, to knock on your door." -c)
```

---

## 6. Glue Scripts

| Script | Role |
|--------|------|
| `ensure_agent.sh <slug> --mode pnj\|faction` | Provisions an NPC/Faction profile (clone default, memory 8000, verify skill) |
| `run_turn.sh <slug> --mode pnj\|faction --campagne <path> "<context>"` | Executes a complete turn: brief → hermes -Q -q -c → response |

Both scripts live in `/opt/modules/gaming/mygamemaster/scripts/`.

---

## 7. E2E Validation (2026-05-25, Hermes v0.13.0)

Full pipeline successfully tested on 2 NPCs (Kreevix/Zulka), model `deepseek/deepseek-v4-flash` (OpenRouter), 4 turns played:

| NPC | Turn | Command | Result |
|-----|------|----------|----------|
| Kreevix | T1 | `chat -Q -q` (creation) | ✅ Format 🎭/🎯/❓/🔒, coherent RP |
| Zulka | T1 | `chat -Q -q` (creation) | ✅ Format respected, distrustful |
| Kreevix | T2 | `chat -Q -q -c` (resume) | ✅ Session resumed, T1 memory |
| Zulka | T2 | `chat -Q -q -c` (resume) | ✅ Session resumed, T1 memory |

**Validated points:**
- Format 🎭/🎯/❓/🔒 respected 100% by both NPCs
- Isolated sessions — each has their own memory, no NPC-to-NPC spoil
- `-c` works — perfect continuity between turns (NPC remembers)
- `-Q` works — clean stdout, no banner
- `memory_char_limit: 8000` (vs 2200 global) — suited for modern models ≥200k tokens
- Skill `mygamemaster-pnj` loaded via `-s` and applied correctly
- Per-profile model — deepseek-v4-flash (free), swappable

**Confirmed trap:** First turn requires `chat -Q -q` WITHOUT `-c` (no existing session).
Second and subsequent turns use `-c`. The `run_turn.sh` glue documents this case.

## 8. Architecture Diagram

```
                    ┌─────────────────┐
                    │   MJ TONNERRE   │ ← main agent
                    │  (orchestrator)  │   toolsets: file, terminal, messaging
                    └────────┬────────┘
                             │
            ┌────────────────┼────────────────┐
            ▼                ▼                ▼
    ┌────────────┐   ┌────────────┐   ┌────────────┐
    │ Pnj-Kreevix│   │ Pnj-Zulka  │   │ Faction-X  │
    │ (profile)  │   │ (profile)  │   │ (profile)  │
    │ memory A   │   │ memory B   │   │ memory C   │
    │ limited    │   │ limited    │   │ limited    │
    │ view       │   │ view       │   │ view       │
    │ toolsets:  │   │ toolsets:  │   │ toolsets:  │
    │  skills    │   │  skills    │   │  skills    │
    │  memory    │   │  memory    │   │  memory    │
    │  (no       │   │  (no       │   │  (no       │
    │  messaging)│   │  messaging)│   │  messaging)│
    └────────────┘   └────────────┘   └────────────┘
```

**Golden Rule:** Each NPC profile loads the `mygamemaster-pnj` skill.
No profile has access to `messaging`, `file`, or `terminal` —
they can only propose, not act.
