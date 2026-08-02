# ✅ INFO Level — PC-Focused Summary (DEFAULT)

> ℹ️ **The `transform_llm_output` hook generates this block automatically** (labeled `✅ Persisted Information:` when `meta.verbosite=INFO`). Format reference below = fallback (hook disabled / bypass `⏸️`).

> **Usage:** Normal play. The Steward reports what directly concerns the player.
> **Reported:** PC-related transactions + persisted data (inventory, stats, weather, time). **Not reported:** Internal checks, purely technical operations.

---

## General Format

```
✅ Persisted Information:
<emoji> <natural language sentence mentioning WHO and WHAT>
...
```

One line per modified data type. Always name the affected character. Emojis per the `README.md` table.

**Example (night's rest):**
```
✅ Persisted Information:
🌙 Night spent at Berthe's Cottage
🕒 Next morning, Day 8
❤️ Ruby is rested (HP restored: 10/10)
🔋 Fatigue dissipated
🥦 Rations consumed: 1 day — 0 remaining
```

---

## INFO-Specific Rules

1. **Always mention WHO** — each line names the affected PC
2. **One line per data type** — do not group food and HP on a single line
3. **Natural language sentences** — no codes, no JSON, no raw stats
4. **Refusals are NOT reported in INFO** — that is the job of WARN/ERROR levels
5. **Pure successes (a successful roll with no data change) are NOT reported** — only what changes the persistent state is logged
