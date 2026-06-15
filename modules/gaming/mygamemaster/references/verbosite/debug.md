# 💾 DEBUG Level — Persistence Operations

> ℹ️ **The `transform_llm_output` hook produces this block automatically** (labeled `💾 Persisted:` when `meta.verbosite=DEBUG`). Format reference below = safety net (hook disabled / bypass `⏸️`).

> **Usage:** Save verification, file write tracing.
> **What is reported:** The 7 Persistence Operations only (not Controls).

---

## General Format

```
💾 Persisted:
<emoji> <entity>: <value> — <detail>
<emoji> <entity>: <value> — <detail>
...
```

One line per persistence operation. No `[OPx]` prefix — we are at a higher level than TRACE.

---

## Concrete Examples

### Food Consumption

```
💾 Persisted:
🕒 +15min → early afternoon Day 7
🥦 sausage -1 (Rubis) — inventory updated
📝 sessions/009.json +1 action
```

### Object Discovery + Propagation

```
💾 Persisted:
⭐ summoning-statuette +1 (Rubis) — inventory updated
💬 Firmin: "statuette emits a blue glow" → established_facts[] — knowledge propagated
📝 sessions/009.json +1 action
```

### Travel

```
💾 Persisted:
🕒 +2h50 → late afternoon Day 7
🗺️ Rubis: Heart Valley → Berthe's Cabin (npcs.json updated)
🗺️ Firmin: Heart Valley → Berthe's Cabin (npcs.json updated)
📝 sessions/009.json +1 action
```

### Rest / Night

```
💾 Persisted:
🌙 Night passed — Berthe's Cabin
🕒 Day 7 → Day 8, morning
❤️ Rubis: HP restored (10/10)
🔋 Rubis: fatigue cleared
🥦 Rations -1d (Rubis) — remaining: 0d
📝 sessions/009.json +2 actions (rest + wake)
```

### Denied Transaction

```
💾 Persisted:
❌ DENIED — Firmin does not know the Temple of Markers
📝 sessions/009.json +1 action (DENIED documented)
```

---

## DEBUG-Specific Rules

1. **One line per operation** — no blocks, no sub-steps
2. **Concise format** — `<entity>: <value>` with arrow `→` for transitions
3. **Denials are logged** — always, even with no operation
4. **No file line numbers** — unlike TRACE, we do not cite `L:147`
