# 🔍 Persistence Audit — Dry-Run Methodology

> From the session of 2026-05-30 — dry-run audit of the campaign
> `la-naissance-dun-roi` (7 sessions, player Rubis/Alex).
> Use as a checklist when a player or the GM asks "are the data really
> being stored properly?"

## Audit Structure

A persistence audit verifies that what EXISTS (the files) corresponds
to what SHOULD EXIST (the formats documented in the skills). It is
**proactive** — unlike `!analyse-bug` which reacts to a reported inconsistency,
the audit seeks gaps before they cause a bug.

## Step by Step

### 0. Path Discovery

> Before any audit, locate the actual path to the campaign.
> `~/.hermes/` is the documented value, but not always the reality
> (e.g., `/opt/data/.hermes/` in a container).

```bash
find / -name "campagnes" -type d 2>/dev/null | grep "mygamemaster/campaigns$"
# → Resolve to: <path_found>/<campaign-name>/
```

### 1. File Inventory

```
Campaign: <path>
├── world.json           # Size, lines?
├── npcs.json             # Size, lines?
├── events.json      # DOES IT EXIST? (frequently missing)
├── MJ-INTENTION-LOG.md  # Ideally present
├── analyse-bug-rapport.md # If applicable
├── characters/
│   └── <id>.json        # One per player
├── sessions/
│   ├── 001.json → NNN.json  # All present?
│   └── NNN+1.json       # Created (next wrap-up)?
├── outils/
│   └── gestion_temps.py # If applicable
├── images/              # If applicable
└── .git/                # Local repository?
```

### 2. Git Status

```bash
cd <campaign_path>
git log --oneline -5     # View recent activity
git status                # Working tree clean?
                          # → `??` (untracked) = campaign not committed
                          #   → git add . && git commit -m "Campaign init"
                          # → `M` (modified) = pending modifications
                          #   → git add . && git commit -m "Pre-resume audit"
cd ~/.hermes/
git status                # Campaign tracked in parent?
```

**Trap S7:** The campaign's local repository was clean (15 commits),
but the parent repository (`~/.hermes/`) listed the campaign as "new commits"
unresolved — no commit in the parent tree since creation.

**Trap S8:** A campaign can be entirely untracked (`??`) in
the parent repository. This is not a resume blocker — just the
first time we commit this campaign. Do it in pre-resume.

### 3. Most Recent Session

Read `sessions/NNN.json` (the highest one with `heure_fin` filled):

| Field | Verification |
|-------|-------------|
| `heure_fin` | Filled (not empty) |
| `resume` | Complete narrative |
| `actions[]` | ≥ 1 action (not empty) |
| `pnj_rencontres[]` | Each NPC listed |
| `lieux_visites[]` | Each location listed |
| `etat_fin` | Active quest, location, leads, key NPCs |
| `teaser` | Present |

### 4. Synchronization `global_state` vs `etat_fin`

Compare `world.json > global_state` with `sessions/NNN.json > etat_fin`.

**Typical divergence points (documented S7):**

| Field | world.json (obsolete) | etat_fin S7 (truth) |
|-------|----------------------|----------------------|
| `quete_active` | "Build a camp" (template) | "Expedition to the Temple of Markers" |
| `phase_construction` | "None — not yet arrived" | Camp established, lean-to in progress |
| `population` | 1 | 4+ (Rubis group) |

**Remedy:** Update `world.json > global_state` from the information
in the last session BEFORE starting narration.

### 5. Time Tracking (`regles.temps.suivi`)

`world.json > regles.temps.suivi` must contain:
- `date_jeu_actuelle` (e.g., "Day 6")
- `heure_jeu_actuelle` (e.g., "early afternoon")
- `t_actuel` (if UT mode) or `null`
- `contrainte_mission.ecoule/restant` (if applicable)
- `rations_consommees_depuis_derniere` (number of days since last resupply)
- Progress of time mechanics specific to the campaign

**If absent:** Extract from `sessions/NNN.json > heure_fin` and
`global_state.chronologie`. Create the section without inventing dates.

**Trap S7:** Absent from the campaign despite 7 sessions. Impossible to
answer "what day are we on?" without digging through the narrative timeline.

### 6. Character Sheet Format

Check `characters/<id>.json` for the new format fields:

| Field | New format | S7 (old) |
|-------|---------------|-------------|
| `historique[]` | Array of persistent facts | ❌ Absent |
| `connaissances_privees[]` | Knowledge not revealed | ❌ Absent |
| `notes_privees[]` | Inner thoughts | ❌ Absent |
| `session_id` | Persistent agent session | ❌ Absent |

**Migration:** Add missing fields without breaking existing ones.
`historique[]` can be pre-filled from `global_state.chronologie`.
Do NOT rewrite the sheet entirely.

### 7. Factions and Clocks

Check in `world.json > global_state.faction_actions_horloge`:

- Each faction has ≥ 1 CT action + ≥ 1 LT action
- Resolved actions are marked ✅
- Objectives are INDEPENDENT of PCs
- The deadline corresponds to elapsed game time (not number of sessions)

**Common trap:** Faction objectives are not renewed after
resolution. If an action is marked ✅ and the CT objective is reached
→ replace it with a new objective consistent with the LT.

### 8. Narrative Integrity (Final Cross-Check)

Before closing the audit: read the `actions[]` from the last session and
mentally verify that each significant action has a trace in the
files (location created, NPC recorded, artifact documented, character
modification applied, route recorded).

**Rule:** You must be able to trace each action from the session to a
concrete modification in the files. If a major action left
no trace → 🐛 PERSISTENCE BUG.

## Audit Report Format

```markdown
# 🔍 Persistence Audit — <Date>

**Campaign:** <name>
**Last session:** S<NNN>
**Git:** <recent commits, status>

## Files
| File | Status | Notes |
|---------|--------|-------|
| world.json | ✅/⚠️/❌ | Size, gaps found |
| npcs.json | ✅/⚠️/❌ | Number of NPCs |
| events.json | ✅/⚠️/❌ | Present/absent |
| sessions/NNN.json | ✅/⚠️/❌ | Verified complete |
| characters/<id>.json | ✅/⚠️/❌ | Format, stats |

## Gaps Found
1. **Critical** — <description>
2. **Minor** — <description>

## Recommendations
- <priority action>
```

## Anti-patterns

| ❌ DO NOT | ✅ DO |
|-------------------|----------|
| Block resume for non-blocking gaps | Fix BEFORE opening narration, but do not prevent play |
| Invent missing game dates/times | Extract from sessions or ask the GM |
| Rewrite everything in new format at once | Soft migration: add fields, don't break existing ones |
| Report without fixing | The audit is meant to fix, not just observe |
| Commit to the wrong repository | The campaign has its own `.git` → commit locally. The parent can be committed separately |
