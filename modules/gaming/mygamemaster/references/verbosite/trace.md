# 🔍 TRACE Level — Every sub-step detailed

> ℹ️ **The `transform_llm_output` hook produces the "Persisted" block automatically** according to `meta.verbosite`. Reference format below = net (hook disabled / bypass `⏸️`).

> **Usage:** Complete audit, data debugging, post-bug verification.
> **What is reported:** The 3 Controls + the 7 Operations, with values read/written and file line numbers.

---

## General format

Each TRACE block follows the complete Steward sequence:

```
[CTRL1-SOURCE] <emoji> <entity> (<file>:<line>)
  → <value found> ✅/❌
[CTRL2-TRANSFER] <emoji> <check> ✅/❌
[CTRL3-COHERENCE] <emoji> <check> — <detail>
[OP1-DEDUCE] <emoji> <entity>: <old>→<new> (file updated L:<line>)
[OP2-ADD] <emoji> <entity>: +<value> (file updated L:<line>)
[OP3-PROPAGATE] 💬 <entity>: knowledge added to established_facts[] (npcs.json L:<line>)
[OP4-TIME] 🕒 heure_courante +<duration> (→ <new time>)
[OP5-STATE] <emoji> <entity>: <old state>→<new state>
[OP6-POSITION] 🗺️ <entity>: <old>→<new> (npcs.json L:<line>)
[OP7-LOG] 📝 sessions/<NNN>.json > actions[] +1 entry (L:<line>)
```

> **Note:** Only operations actually triggered are listed.
> A simple transaction (consumption) does not trigger OP2, OP3, OP5, OP6.

---

## Concrete examples

### Food consumption

```
[CTRL1-SOURCE] 🎒 inventory Rubis (characters/100000000000000001.json:142)
  → "saucisson" x2 found ✅
[CTRL2-TRANSFER] 🥦 Consumable — qty ≥ 1 ✅, time available ✅
[CTRL3-COHERENCE] 🗺️ Location: Chemin des Hêtres (outdoor), witnesses: Firmin — OK
[OP1-DEDUCE] 🥦 saucisson: Rubis qty 2→1 (file updated L:147)
[OP4-TIME] 🕒 heure_courante +15min (early afternoon → early afternoon+15)
[OP7-LOG] 📝 sessions/009.json > actions[] +1 entry (L:89)
```

### Object discovery + knowledge propagation

```
[CTRL1-SOURCE] ⭐ statuette-appelant — new object, no source to verify ✅
[CTRL2-TRANSFER] 🎒 Add to Rubis inventory — inventory accessible ✅
[CTRL3-COHERENCE] 💬 The statuette emits a glow — Firmin is present (witness) ✅
[OP2-ADD] ⭐ statuette-appelant → Rubis inventory (file updated L:152)
[OP3-PROPAGATE] 💬 Firmin: "statuette emits a bluish glow" → established_facts[] (npcs.json L:234)
[OP7-LOG] 📝 sessions/009.json > actions[] +1 entry (L:92)
```

### Transaction refused (missing knowledge)

```
[CTRL1-SOURCE] 💬 established_facts Firmin (npcs.json:89)
  → "temple des Marqueurs" NOT FOUND ❌
  → 17 entries scanned, no match
REFUSAL — ❌ Firmin cannot say "I know this temple".
  Source: npcs.json → Firmin → established_facts[0..16]
[OP7-LOG] 📝 sessions/009.json > actions[] +1 entry (REFUSAL documented)
```

---

## TRACE-specific rules

1. **Each modified file line is cited** — `L:147` after each OP
2. **Before/after values are explicit** — `qty 2→1`, not just `-1`
3. **Control failures are detailed** — number of entries scanned, precise reason
4. **REFUSAL replaces OP** — the refusal is logged (OP7) but OP1-OP6 are not applied
