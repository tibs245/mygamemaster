# 📜 Timeline Governance — events.json Protocol

## Principle

`evenements.json` is the **temporal canon** of the campaign. Every event in it is an established, immutable fact. Nothing is speculative — we log only what has **actually occurred** in play.

## Trap #1: Extrapolation

**Never assume a time jump between two sessions.** Real example that caused an error:

```
Session 1 (closed) → Session 2 (resumed)
Error: I assumed a night had passed between them
       → timeline invented a Day 2 that didn't exist
Reality: both sessions occurred on the same game day
         → all at t=0..57, no jump to t=144
```

**Rule:** Game time is what was explicitly played. A session wrap-up does not advance the clock. A session resumption picks up at the same instant in-game unless the GM says "X time has passed between them". **When in doubt: the clock does not advance.**

## Trap #2: Narrative Invention

When you construct or expand the timeline:

- Every event must be traceable to a source: `session_001`, `session_002`, `campaign_lore`, etc.
- If data is not in session logs → do not invent it
- Events of type `meta` mark session starts/ends — these are acceptable
- Events of type `character` / `npc` / `town_location` must be based on actions actually played

## Architecture

```
campaigns/<name>/
├── evenements.json        ← The temporal canon — single file
├── tools/
│   ├── time_management.py   ← Python functions + CLI
│   └── README.md            ← Tool documentation
└── world.json             ← meta.time contains configuration (time_unit_minutes,
                              units_per_day, days_per_year, t_offset, regime)
```

### evenements.json

```json
{
  "meta": {
    "version": "1.0",
    "regime": "UT",
    "time_unit_minutes": 10,
    "units_per_day": 144,
    "units_per_year": 52560,
    "epoch": 0,
    "last_t_recorded": 57
  },
  "events": [
    {
      "t": -26280000,       // negative = pre-campaign, 0 = campaign start
      "type": "global",     // global | town_location | character | npc | faction | artifact | quest | meta
      "id": "...",          // optional — for get_entity_history() queries
      "label": "Short title",
      "desc": "Detailed description — must be understandable by an agent without context",
      "location": "Location (optional)",
      "participants": ["pc:character_a", "pc:character_b"],
      "source": "session_001",
      "duration_ut": 6,
      "roll": {"stat": "Intuition", "skill": "Survival", "die": 14, "total": 20, "threshold": 12, "result": "success"},
      "session_end": true    // session wrap-up marker
    }
  ]
}
```

## Systematic Rules (checklist)

### After EVERY time-consuming action

1. **Calculate** the next t: `calculate_next_t(events, duration=<UT>)` or `python3 tools/time_management.py add --t ...`
2. **Add** the event to evenements.json
3. **Validate**: `python3 tools/time_management.py validate` → must return ✅
4. **Update** `world.json > rules.time.tracking.t_current`

### Before EVERY narrative response

If unsure about a past event:
- `get_events(t_min, t_max, ...)` — time slice
- `get_entity_history("pc:character_b")` — history of a character/NPC
- `get_relation_history("pc:character_b", "pc:character_a")` — interactions between two entities

## Configuration (world.json > meta.time)

```json
{
  "time_unit_minutes": 10,      // duration of 1 UT
  "units_per_day": 144,         // UT per day (24h)
  "days_per_year": 365,
  "t_offset": 48,               // UT at campaign start (48 = 8am)
  "regime": "UT"                // "UT" or "narrative"
}
```

Python tools read this config automatically. After modifying world.json, call `reload_config()`.

## Quick CLI Commands

```bash
# Stats
python3 tools/time_management.py stats

# Add
python3 tools/time_management.py add --t 58 --type character \
  --id "pc:character_a" --label "..." --desc "..." --source "session_003"

# Query
python3 tools/time_management.py query --day 1
python3 tools/time_management.py query --t-min 30 --t-max 60

# Verification
python3 tools/time_management.py entity pc:character_b
python3 tools/time_management.py relation pc:character_b pc:character_a
python3 tools/time_management.py validate
python3 tools/time_management.py slice 57
```

## Python Functions Accessible from RP

```python
from tools.time_management import *

# Configuration
config_time_unit_minutes()     # → 10
config_units_per_day()         # → 144
config_t_offset()              # → 48
reload_config()                # clears cache

# Math
t_to_human_day(57)             # → "Day 1"
t_to_game_time(57)             # → "17:30"
t_to_window(57)                # → "evening"
duration_text(57)              # → "9.5 h"
calculate_next_t(data, duration=6)  # → int

# Queries
get_events(t_min=0, t_max=144, type="character")
get_entity_history("npc:npc_a")
get_relation_history("pc:character_b", "pc:character_a")
get_world_state(57)            # snapshot of world at t=57
validate_timeline()            # → list[str] (empty if all OK)
format_events_for_agent(list)  # → readable str
```
