# Data Persistence Discipline

> ℹ️ The report of what was actually persisted is now automatically emitted by the `transform_llm_output` hook (block "Persisted"). This document details the **procedures** (git, JSON validation, `._*` artifacts, movement governance) that the GM applies; the hook only observes the diff.

## Golden Rule

**Every piece of information created or modified during a session must be immediately saved in the campaign files.** Never wait until the end of the session.

## Post-Action Checklist

After each significant narrative action (NPC dialogue, discovery, combat, event), verify:

- [ ] `pnj.json` — every new NPC named, described, with their role, attitude, location
- [ ] `monde.json` — every new location visited or mentioned added to `regions` or `lieux`
- [ ] **`monde.json > regles.temps.suivi`** — game time elapsed? rations consumed? mission constraint advanced?
- [ ] `personnages/<id>.json` — equipment updated, `notes_perso.relations` enriched, `notes_perso.secrets` if new personal info, **rations deducted if the day changed**
- [ ] `sessions/NNN.json` — action logged in `actions[]`, NPC in `pnj_rencontres[]`, location in `lieux_visites[]`

## Common Pitfalls

| ❌ Pitfall | ✅ Fix |
|----------|--------|
| Create an NPC in narration without saving it to `pnj.json` | Save immediately after first mention |
| Give equipment without updating the character sheet | Patch `equipement[]` right away |
| Establish a relationship between PC/NPC without writing it in `notes_perso.relations` | Add to the relations in the relevant character sheets |
| Narrate a flashback/background without adding it to `notes_perso.secrets` | Log in the character's secrets |
| Forget to log an action in `sessions/NNN.json > actions[]` | Log immediately after resolution |

## Why This Matters

Without this discipline, the GM loses long-term coherence:
- An NPC mentioned then forgotten cannot reappear naturally
- A location visited will not be recognized if the players return
- Character relationships will not hold up over time
- The wrap-up session will be incomplete
- **Game time becomes unclear** — impossible to know what day it is, how many rations remain, if the mission constraint has expired, or what NPCs were doing while the PCs were away

**MJ Tonnerre, what do the notes say?** — this ritual question only makes sense if the notes are up to date.

---

## Memory vs Files Governance

**Never store game data in agent memory.** Memory serves exclusively for:
- User preferences (tone, style, communication habits)
- Current operation state (session number, active participants, channel)
- Conduct reminders (agency rules, formats to respect)

Game rules, NPCs, characters, session logs, chronology, and GM secrets go **only** in the campaign files.

---

## Versioning (Git)

Campaign files are versioned to enable rollback and history.

> ℹ️ **At runtime, commits are AUTOMATIC** (hook `post_tool_call`, `meta.hooks.auto_commit` on
> by default): every **valid** campaign file write is committed alone, with a message
> derived from actual deltas. The model does **not** need to run `git`; it should only write the data
> and **validate JSON** (the hook does not commit broken JSON). The manual workflow below remains the
> reference for operations outside runtime (init, maintenance, rollback).

### Workflow (manual reference / outside runtime)

```bash
# One-time initialization (if not already done)
cd ~/.hermes/mj-tonnerre/
git init
echo -e "*.log\n.env\n__pycache__/\n*.pyc\n.DS_Store" > .gitignore
git add .gitignore campagnes/
git commit -m "Initialize MJ Tonnerre — campaign <name>"

# After each session
cd ~/.hermes/mj-tonnerre/
git add campagnes/<campaign-name>/
git commit -m "🎲 <Campaign Name> — Session <N> wrapped: <episode title>"

# Verification
git status  # should display "nothing to commit, working tree clean"
```

### What Gets Committed

- `monde.json` — world, rules, chronology, secrets
- `pnj.json` — all NPCs
- `personnages/<id>.json` — player character sheets
- `sessions/NNN.json` — session logs
- `images/` — generated illustrations (portraits, maps, scenes)

### What Gets Ignored

- `.env` — API keys
- `*.log` — execution logs
- `__pycache__/`, `*.pyc` — Python caches
- `.DS_Store` — system files

---

## JSON Validation (before commit)

Every campaign file is JSON. One extra comma, one missing brace, and the file becomes unreadable → session blocked. **Validate after every write, always before committing.**

```bash
# 1. Well-formed JSON (syntax) — all .json files in the campaign
python3 /opt/modules/gaming/mj-tonnerre/scripts/validate_json.py <path/campaign>

# 2. Schema compliance (required fields, types, enums)
python3 /opt/modules/gaming/mj-tonnerre/scripts/validate_schema.py <path/campaign>
#   → a specific file:
python3 /opt/modules/gaming/mj-tonnerre/scripts/validate_schema.py <file.json> --schema monde
```

Exit codes: `0` = OK, `1` = deviation detected, `2` = usage error. **NEVER commit a file that fails `validate_json` (syntax).** A schema deviation (`validate_schema` = 1) is non-blocking but should be corrected as soon as possible.

---

## Apple Double Artifacts (`._*`)

On macOS, copying/moving a file into a non-native folder creates a **ghost file** `._<name>` (e.g., `._monde.json`) that stores metadata. These files:

- **pollute git** (committed by mistake, they create noise),
- **break scripts** that iterate over `*.json` (`._monde.json` is NOT valid JSON → false positive validation).

### Rules

1. They are already ignored via `.gitignore` (`.DS_Store` + add `._*` below).
2. Before committing, clean up: `dot_clean <path/campaign>` (removes redundant `._*`), or `find <path/campaign> -name '._*' -delete`.
3. Validation scripts **ignore** files starting with `.` — do not work around this by renaming them.

Recommended addition to `.gitignore` (see Versioning section):

```
._*
.AppleDouble
```

---

## Movement Governance — `deplacements.gouvernance`

The `regles.temps.deplacements.gouvernance` block is **injected at campaign creation** (do NOT copy it by hand). It encodes the **4 spatial coherence rules** that `validator-distances.py` verifies after each route is added:

1. **Fixed durations** — once set, the duration of a journey does not change without explicit narrative reason.
2. **Indirect ≥ direct** — a journey passing through an intermediate point takes at least as long as the direct route between the same two endpoints.
3. **Round trips / max 12-hour day** — round trip + work must fit in a playable day (≤ 12 h).
4. **Distant point ≥ close point** — no inverted hierarchy: a more distant location cannot be faster to reach than a closer location on the same axis.

### Template (reference — already injected at creation)

```json
"deplacements": {
  "gouvernance": {
    "regles": [
      "durees_fixes: une durée figée ne change pas sans justification narrative",
      "indirect_superieur_ou_egal_direct",
      "allers_simples: aller-retour + travail <= 12h (journée jouable)",
      "point_lointain_superieur_ou_egal_point_proche"
    ],
    "validation": "python3 /opt/modules/gaming/mj-tonnerre/scripts/validator-distances.py <campaign>/monde.json"
  },
  "depuis_<base_location>_vers": {
    "<destination>": "<duration> — <path description>"
  },
  "entre": {
    "<location_a>__<location_b>": "<duration> — <description>"
  }
}
```

### Verification

```bash
python3 /opt/modules/gaming/mj-tonnerre/scripts/validator-distances.py <path/campaign>/monde.json
# → 0 OK, 1 warning (inconsistent route), 2 error
```

Run **after every route addition** in `regles.temps.deplacements`. If a route breaks one of the 4 rules, correct the duration or document the narrative reason before committing.
