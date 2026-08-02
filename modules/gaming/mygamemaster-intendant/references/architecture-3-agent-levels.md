# 3-Level Architecture for NPC Agents (N0/N1/N2)

> Design validated in dry-run session on 2026-06-07.
> Answers the question: "How do we ensure NPCs always have their information,
> their knowledge, their view of the context, with coherent and
> interesting interactions, in an optimized way (AI cache so we don't repay tokens)?"

## Principle

An NPC does not need a complete Hermes profile to be coherent.
The architecture distinguishes **3 complexity levels**, from lightest to heaviest,
to cover all NPC use cases in a campaign.

```
N0 — GM only         Cost: 0 tokens
  ↓
N1 — Agent Brief    Cost: ~2K tokens/call
  ↓
N2 — Agent Profile  Cost: ~4K tokens/call
```

The choice of level depends on the importance of the NPC and the need for autonomy.

---

## Level 0 — GM only (zero tokens)

**How it works:**
- The GM reads the NPC sheet in `npcs.json` (already loaded in context)
- The GM improvises dialogue while respecting the NPC's `established_facts` (established facts)
- The **Steward** validates (Check 1 — SOURCE) that the GM is not inventing facts the NPC doesn't know

**Cost:** 0 tokens (the GM already has the files in context)

**For which NPCs:** Extras, passing NPCs, short responses (1-2 exchanges)

**Advantages:** Free, full GM control
**Disadvantages:** Mental load on the GM, risk of error (confirmed S7 — coherence bugs)

**Scripts used:** None

---

## Level 1 — Agent Brief (minimal cost)

**How it works:**
1. The GM calls `build_brief.py <campaign> <npc_name> --cache`
   - Extracts from `npcs.json`: identity, established_facts, limits, inventory, skills, stats
   - **Built-in cache**: checks MD5 checksum of `npcs.json` → if unchanged, uses stored cache
   - Cost: ~637 tokens for a typical NPC (Firmin)
2. The GM builds the scene context (1-2 sentences)
3. Direct call to a flash LLM (`deepseek/deepseek-v4-flash:free`) — **no Hermes profile**
4. The LLM returns the response in format `🎭 RP / 🎯 INTENTION / ❓ TO GM / 🔒 NOTES`
5. The **Steward** validates all 3 checks (SOURCE, TRANSFER, COHERENCE)
6. The GM relays the validated response on Discord

**Cost:** ~900 tokens prompt + ~600 tokens response = ~$0.005 per call

**For which NPCs:** Recurring NPCs (Firmin, Berthe, Rousset, Drageon)

**Cache:** The brief is stored in `~/.hermes/mygamemaster/cache-briefs/brief_<campaign>_<npc>.json`
- MD5 checksum of `npcs.json` → automatic HIT/MISS
- If `npcs.json` modified (new established fact) → MISS, regeneration
- If unchanged → HIT, cache use = zero re-read tokens

**Scripts:** `scripts/build_brief.py`, `scripts/call_npc.py`

---

## Level 2 — Agent Profile (moderate cost)

**How it works:**
1. A lightweight Hermes profile is created in `profiles/pnj-<slug>/`
2. The profile has:
   - `config.yaml` minimal (model, provider — **no copied skills**)
   - `SOUL.md` (personality, voice, limits)
   - `skills/` → symbolic link to `/opt/data/skills` (reference, not copy)
   - `sessions/` (for persistence)
3. The GM calls the profile via the same N1 mechanism (brief + context)
4. The profile uses its persistent memory for cross-session continuity
5. Same Steward validations

**Cost:** ~2.3K tokens total (brief 637 + profile overhead) = ~$0.008 per call

**Savings vs complete profile:** **-80% tokens** because we don't copy the 28 skills

**For which NPCs:** Major NPCs with continuity needs
(Esterlin, the Corneille, the Count — NPCs who travel and whom we encounter again)

**Typical minimal profile (467 bytes):**
```yaml
model:
  default: deepseek/deepseek-v4-flash
  provider: openrouter
  base_url: https://openrouter.ai/api/v1
toolsets: ["chat"]
skills: { required: [], optional: [], profiles: [] }
```

**Directory structure:**
```
profiles/pnj-firmin/
├── config.yaml      # minimal (467 bytes)
├── SOUL.md          # personality (~1.5K bytes)
├── skills → /opt/data/skills   # symbolic link, NOT copy
├── sessions/        # persistence
```

---

## Complete Flow (N1 — nominal case)

```
1. GM: "I need Firmin to respond to Rubis"
2. GM calls: python3 build_brief.py <campaign> Firmin --cache
   → Cache HIT (npcs.json unchanged) → brief in 0 tokens
   → Cache MISS (npcs.json modified) → regeneration, cache update
3. GM builds context: "You walk with Rubis... They ask you..."
4. LLM call: prompt = brief + context + rules
5. LLM returns: 🎭 RP / 🎯 INTENTION / ❓ TO GM / 🔒 NOTES
6. 🧮 STEWARD:
   - Check 1 (SOURCE): verify the RP doesn't invent facts
   - Check 2 (TRANSFER): is the action mechanically valid?
   - Check 3 (COHERENCE): is the result logical?
7. If ✅ VALIDATED → GM narrates on Discord + Steward applies operations
8. If ❌ REJECTED → GM corrects or replays
```

**Pitfall confirmed by simulation:** In N1, the LLM invented "I passed through there once, years ago" even though this fact is not in Firmin's `established_facts` (established facts).
→ **The Steward Check 1 blocked** this invention.
→ The Steward architecture is therefore **necessary** as complement to N1/N2.

---

## Cost Comparison

| Aspect | N0 — GM only | N1 — Agent Brief | N2 — Agent Profile |
|---|---|---|---|
| **Tokens per NPC response** | 0 | ~1.6K | ~2.3K |
| **Cost per response** | $0 | ~$0.005 | ~$0.008 |
| **GM load** | High | Low | Very low |
| **NPC coherence** | ✅ Steward | ✅✅ Brief + Steward | ✅✅✅ Memory + Steward |
| **Infrastructure** | None | `build_brief.py` + `call_npc.py` | Hermes profile + skills link |
| **Cache possible** | N/A | Brief snapshot (MD5 checksum) | Persistent session + snapshot |
| **For which NPCs** | Extras, short responses | Firmin, Berthe, Rousset | Esterlin, Corneille, Count |
| **Risk of invention** | Medium (GM may forget) | Moderate (LLM may invent) | Moderate (LLM may invent) |
| **Steward protection** | Check 1 (source) | Check 1 (source) | Check 1 (source) |

---

## Dependencies

- **Transactional Steward** : `mygamemaster-intendant` — validation of 3 checks (source, transfer, coherence)
- **Brief cache** : `scripts/build_brief.py` — MD5-cached extraction from npcs.json
- **N1 call** : `scripts/call_npc.py` — prompt construction + LLM call (dry-run/live)
- **N2 profile** : `profiles/pnj-<slug>/` — minimal structure with linked skills (not copied)

## Anti-patterns

| ❌ Avoid | ✅ Do |
|---|---|
| Copy the 28 skills into each agent profile | Create a symbolic link `skills → /opt/data/skills` |
| Let the N1/N2 LLM speak without Steward verification | Always pass through Check 1 (SOURCE) after LLM response |
| Use N2 for an NPC who speaks once | N0 is enough. Reserve N2 for NPCs with cross-session continuity |
| Call the LLM without the NPC's brief | The brief (established_facts) is the single source of truth for what the NPC knows |
| Store the NPC's brief in the GM's volatile memory | The MD5 cache is the source of truth — agent memory is not reliable |