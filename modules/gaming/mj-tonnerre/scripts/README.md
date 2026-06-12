# Deterministic Tooling — MJ Tonnerre

Standalone scripts (Python 3, **stdlib only**, zero network, zero pip dependencies)
that transform procedures "executed from memory" into verifiable commands.
Designed to run in the Hermes podman container.

All scripts:
- have a `--help` option;
- take the **campaign path** (or file path) as an argument;
- are compatible with **both campaigns** (`jusquau-bout-de-mon-monde`, UT mode;
  `la-naissance-dun-roi`, Narrative mode);
- return **clean exit codes** (`0` = OK) and often accept `--json`.

> Guiding principle: **the LLM keeps narration; the scripts handle
> mechanics and guards** (dice, validation, propagation, commit).

Path convention in examples (from project root):
```
CAMP=.hermes/mj-tonnerre/campaigns/la-naissance-dun-roi
SCRIPTS=/opt/modules/gaming/mj-tonnerre/scripts
```

---

## 1. `roll.py` — Real Dice Roller

Rolls **true** dice (cryptographic entropy via `secrets`, no network) and
applies **mechanical** natural die rules (`SOUL.md` §NATURAL DIE RULE):
`nat 1` = failure regardless (FUMBLE), `nat max` = success regardless
(CRITICAL), even against a threshold. The rule applies only to **single-die** rolls
(skill checks); multi-die rolls (damage) are simple summation.
Each roll is **logged** (JSON Lines) in an auditable log.

**Signature**
```
python3 roll.py "<formula>" [--dc N] [--stat NAME] [--seed N] [--json] [--log PATH] [--no-log]
```
- `formula`: `1d20+3`, `d6`, `2d8-1`, `1d100`… (the `1` before `d` is optional).
- `--dc N`: difficulty check threshold; success if `total ≥ N` (except natural die decides).
- `--stat NAME`: tested attribute (display + log).
- `--seed N`: makes the roll **reproducible** (tests / replaying a dispute ONLY — otherwise true entropy).
- `--json`: machine output. `--log`: log file (default `scripts/jets.log` or `$MJ_ROLL_LOG`). `--no-log`: do not log.

**Exit codes**: `0` roll completed (success OR failure) · `2` invalid formula.

**How the GM calls it** (instead of inventing a number)
```
python3 $SCRIPTS/roll.py "1d20+6" --dc 12 --stat Intuition --json
# → {"des":[14],"total":20,"dc":12,"nat":null,"resultat":"REUSSITE","ecart":8,...}
```
The GM then reformats this result into "Inviolable Output Format" and
**narrates only the consequence** (no numbers exposed to the player if immersion requires).
The JSON field (dice, rng, seed) can be copied into `sessions/NNN.json > actions[].details`.

---

## 2. `validator-distances.py` — Spatial Coherence (FIXED)

Validates travel governance rules from
`rules.temps.movements`:
- **R1**: an indirect route (source→X→dest) cannot be shorter than the direct route;
- **R3**: a round trip must not exceed 12h (game day);
- **R4**: flags suspicious identical durations (requires human review).

Fixes applied: (a) `Path` vs `dict` bug (crashed on both campaigns);
(b) duration parser that ignored minutes from `1h30`/`5h45`/`7h30` (read 60/300/420
instead of 90/345/450).

**Signature**
```
python3 validator-distances.py <path/world.json>
```
**Exit codes**: `0` coherent · `1` warnings (R3/R4 — human review needed) · `2` error/file not found.

**How the GM calls it** (after adding/modifying any route)
```
python3 $SCRIPTS/validator-distances.py $CAMP/world.json
```
Also automatically invoked by the pre-commit hook (see §4) on any modified `world.json`.

---

## 3. `validate_json.py` — Generic JSON Validator

Loads **all** `*.json` files from a campaign (`world.json`, `npcs.json`,
`evenements.json`, `characters/*`, `sessions/*`, etc.) and validates their syntax.
Ignores `.git`, `__pycache__`, `images`. Replaces scattered `python3 -c "import json; json.load(...)"` calls.

**Signature**
```
python3 validate_json.py <campaign|file.json> [<other>...] [--json]
```
**Exit codes**: `0` all valid · `1` at least one broken · `2` usage (path not found / no JSON).
For broken JSON, displays **file + line + column + message**.

**How the GM calls it** (before any commit, after any `patch`/edit)
```
python3 $SCRIPTS/validate_json.py $CAMP
```

---

## 4. Hook `pre-commit` + `install-hooks.sh`

Git guard-rail: **refuses the commit** if campaign JSON is syntactically
broken, and runs the distance validator (non-blocking) on any modified `world.json`.
Transforms the rule "never commit unvalidated JSON" into machine guarantee.

- `pre-commit.hook`: hook template (POSIX sh). Contains the placeholder
  `__MJ_SCRIPTS_DIR__` replaced at install with the absolute path of this folder.
- `install-hooks.sh`: installs the hook into the campaign's `.git/hooks`.

**Installation** (do once per campaign repository)
```
sh $SCRIPTS/install-hooks.sh <path/campaign> [--force]
# e.g.: sh $SCRIPTS/install-hooks.sh $CAMP
```
The installer finds the git repository versioning the campaign, copies the hook into
`<repo>/.git/hooks/pre-commit`, and injects the absolute path of the scripts.

**Behavior on commit**
- Valid JSON → commit allowed (`✅`).
- Broken JSON → commit **REFUSED** (`❌`, with line/column of problem).
- Emergency bypass: `MJ_SKIP_HOOK=1 git commit …`.
- Override script path: `MJ_TONNERRE_SCRIPTS=/path git commit …`.

> Note: scripts live in `skills/…` (separate repository from campaigns). That is
> why the absolute path is injected into the hook rather than deduced. If the
> scripts move, reinstall with `--force`.

---

## 5. `check_session.py` — Checklist Gap Detector (READ-ONLY)

Walks through the **latest** session (or `--session N`) and flags gaps WITHOUT
modifying anything. Compatible with both schemas (`npcs.json` can be
`{"pnj":[…]}` or a bare list). Matches locations/NPCs by **normalized name**
(tolerates accents, punctuation, spelling variants).

Gaps detected:
- location in `lieux_visites[]` missing from `universe.regions[].locations` → **blocking**;
- NPC in `pnj_rencontres[]` with no sheet in `npcs.json` → **blocking**;
- faction without `objectif_court_terme` OR `objectif_long_terme` → **blocking**;
- faction absent from `faction_actions_horloge` → **blocking**;
- clock deadline **overdue** (Day < current day) not marked RESOLVED → **blocking**;
- deadline unparseable (free text like "In 2-3 weeks") → **informational** (ℹ);
- session with content but empty `heure_fin` → **blocking**.

The "current day" is estimated deterministically: UT mode → last `t` from
`evenements.json`; otherwise → max "Day N" mentioned in timeline + sessions.

**Signature**
```
python3 check_session.py <campaign> [--session N] [--json]
```
**Exit codes**: `0` no blocking gaps (ℹ may remain) · `1` at least one blocking · `2` usage.

**How the GM calls it** (anytime "where am I?" and before wrap-up)
```
python3 $SCRIPTS/check_session.py $CAMP
```

---

## Summary of Calls (snippets to reference in SKILL.md)

```sh
CAMP=.hermes/mj-tonnerre/campaigns/<campaign>
SCRIPTS=/opt/modules/gaming/mj-tonnerre/scripts

# Roll a die (instead of inventing a number)
python3 $SCRIPTS/roll.py "1d20+6" --dc 12 --stat Intuition --json

# Check distance coherence (after adding a route)
python3 $SCRIPTS/validator-distances.py $CAMP/world.json

# Validate all JSON (before commit / after edit)
python3 $SCRIPTS/validate_json.py $CAMP

# Add an action to session log (instead of heredoc json.load/append/dump)
python3 $SCRIPTS/add_action.py $CAMP 9 <<'EOF'
{"timestamp":"Jour 7, soir","type":"dialogue","joueur":"Rubis","description":"…","resultat":"…"}
EOF

# Consult full NPC sheet (GM view, read-only)
python3 $SCRIPTS/voir_pnj.py $CAMP Firmin        # or --list / --json

# Detect gaps in latest session
python3 $SCRIPTS/check_session.py $CAMP

# Install git guard-rail (once per campaign repository)
sh $SCRIPTS/install-hooks.sh $CAMP
```

| Script | Purpose | Exit 0 | Exit 1 | Exit 2 |
|--------|---------|--------|--------|--------|
| `roll.py` | Real dice + natural die + log | roll completed | — | invalid formula |
| `validator-distances.py` | Distance coherence | coherent | warnings | error/not found |
| `validate_json.py` | Campaign JSON syntax | all valid | one broken | usage |
| `check_session.py` | Checklist gaps (read-only) | no blocking | blocking gap | usage |
| `add_action.py` | Append action(s) to session log | added | invalid data | session not found |
| `voir_pnj.py` | Query NPC sheet (read-only) | found/--list | not found/ambiguous | npcs.json not found/usage |
| `install-hooks.sh` | Install hook | installed | hook already present | usage/no git |

**Execution constraints**: Python 3 (tested on 3.14), stdlib only, no network access
(`roll.py` uses `secrets`, not external service). No script modifies campaign data
except via git-triggered commits — `check_session.py` and `validator-distances.py`
are strictly read-only.

---

## 6. `clock.py` — Faction Clock Advancer

Reads `global_state.faction_actions_horloge`, calculates **current game time**
deterministically, and marks each action according to **pinned deadline format**:

- **UT** mode → current time = last `t` from `evenements.json` (in UT);
- **narrative** mode → current day = max "Day N" (timeline + sessions),
  same heuristic as `check_session.py`.

Deadline format consumed **identically** (object):
```json
"echeance": {
  "texte": "<original phrase>", "unite": "jour"|"ut",
  "min": <int|null>, "max": <int|null>, "ancre": <int>,
  "statut": "en_cours"|"echue"|"resolue"
}
```
For each deadline: `approche` if `current ≥ ancre+min`, `echue` if
`current ≥ ancre+max`. Deadlines still in **string format** (not migrated) are
**ignored and reported** (not machine-advanceable). `resolue` are never
overwritten (GM narrative decision).

**Signature**
```
python3 clock.py <campaign> [--dry-run|--apply] [--faction NAME] [--json] [--quiet]
```
- `--dry-run` (DEFAULT): report only, writes nothing.
- `--apply`: writes `echeance.statut` in `world.json` (`echue`/`en_cours`;
  `approche` is a report signal, not a persisted schema status).

**Exit codes**: `0` no overdue · `1` ≥ 1 overdue unresolved · `2` usage.

> ⚠️ Do NOT run `--apply` on real campaigns from this tooling (data migration
> is handled elsewhere). Test `--apply` on a `/tmp` copy.

```
python3 $SCRIPTS/clock.py $CAMP             # report
python3 $SCRIPTS/clock.py /tmp/copy --apply  # write, copy only
```

---

## 7. `close_session.py` — Wrap-Up Pipeline in 1 Command

Chains `validate_json.py` → `validator-distances.py` → `check_session.py` →
`clock.py --dry-run`, then a **~10-point pipeline check** (P1 locations propagated,
P2 NPCs sheeted, P3 factions with short+long term goals, P4 factions in clock, P5
clock up-to-date, P6 timeline, P7 `heure_fin`, P8 `resume`, P9 `etat_fin`, P10
UT timeline). **REFUSES wrap-up (exit ≠ 0)** if a blocking step is missing;
otherwise **proposes a commit message** — never commits itself.

**Signature**
```
python3 close_session.py <campaign> [--session N] [--titre "..."] [--teaser "..."] [--json] [--commit]
```
`--commit` is **documented but not executed** by this tooling (see `--help` warning):
the decision to commit belongs to the GM / Steward.

**Exit codes**: `0` pipeline green (wrap-up possible) · `1` blocking step
missing (wrap-up refused) · `2` usage.

```
python3 $SCRIPTS/close_session.py $CAMP --titre "Le Cœur" --teaser "..."
```

---

## 8. `validate_schema.py` + `schemas/` — Structural Validation

Validates a campaign against JSON Schemas in `scripts/schemas/` with a
**homegrown stdlib validator** (no external `jsonschema` lib). Supported
Draft 2020-12 subset: `type` (unions), `required`, `properties`,
`additionalProperties`, `patternProperties`, `items`, `enum`, `oneOf`/`anyOf`,
local `$ref`, `$defs`. Tolerant (`additionalProperties: true` everywhere): only
reports **actual gaps**.

Provided schemas:
- `monde.schema.json` — incl. `modules` block, `global_state.factions` with
  required `objectif_court_terme`+`objectif_long_terme`, `faction_actions_horloge`
  with new `echeance` object (legacy string format tolerated via `oneOf`);
- `pnj.schema.json` — canonical format (required `established_facts`/`hypotheses_mj`;
  tolerates bare list or `{"pnj":[...]}`);
- `personnage.schema.json` — `meta.nom_perso`, `stats`, `inventaire`, `sante`;
- `session.schema.json` — session log fields.

**Signature**
```
python3 validate_schema.py <campaign>                 # entire campaign
python3 validate_schema.py <file.json> --schema monde   # specific file
```
**Exit codes**: `0` compliant · `1` ≥ 1 gap · `2` usage.

> First run = list of **technical debt** (expected real gaps). E.g.:
> in C1 the 3 NPCs lack `established_facts`/`hypotheses_mj` → 6 gaps reported
> (audit gap §2.9, to migrate on data side, not by this tooling).

```
python3 $SCRIPTS/validate_schema.py $CAMP
```

---

## 10. `add_action.py` — Append Action(s) to Session Log

Eliminates recurring GM boilerplate (`python3 << EOF … json.load →
actions.append → json.dump … EOF` followed by revalidation `json.load`). The
template provides only **the action data**; the script loads the session,
appends, writes **atomically** (via `worldlib.sauver_json_atomique`:
`ensure_ascii=False`, `indent=2`, final `\n`, `mkstemp`+`fsync`+`replace`) then
rereads to confirm coherence. The `post_tool_call` hook (auto-commit) then freezes
the session — nothing else to run.

**Target**: campaign + session number (`9` → `009.json`), or direct path
to `sessions/NNN.json`.
**Data**: stdin (default), `--action '<json>'`, or `--fichier f.json`. Single object
**or** array of objects. `description` is required; `timestamp`, `type`,
`joueur`, `resultat` are only **recommended** (warning, not blocking).

**Signature**
```
python3 add_action.py <campaign> <session> [--action JSON | --fichier F] [--dry-run] [--json]
python3 add_action.py <sessions/NNN.json> [--action JSON | --fichier F]
```
**Exit codes**: `0` added/dry-run · `1` invalid data (broken JSON,
not an object, missing `description`) · `2` usage (session not found, non-session file).

```
python3 $SCRIPTS/add_action.py $CAMP 9 <<'EOF'
{"timestamp":"Jour 7, soir","type":"dialogue","joueur":"Rubis","description":"…","resultat":"…"}
EOF
```

---

## 11. `voir_pnj.py` — Query NPC Sheet (READ-ONLY)

Eliminates the heredoc `for pnj in p: if pnj['nom']==… : print …` that the GM
recopies to reread a sheet. Searches by name (case-insensitive equality, then
unique substring), displays **all** fields from `npcs.json`, including
**GM secret fields** (`hypotheses_mj`, `notes_privees`, `derniere_interaction`).

Distinct from `build_brief.py`: the latter produces a *brief for NPC agents*
and deliberately **omits** secret fields (not to expose them). `voir_pnj.py` is the
**complete GM view**. Never writes (read-only).

**Signature**
```
python3 voir_pnj.py <campaign> <name> [--json] [--max N]
python3 voir_pnj.py <campaign> --list
python3 voir_pnj.py <npcs.json> <name>
```
**Exit codes**: `0` found / `--list` · `1` not found or name ambiguous
(≥ 2 substrings) · `2` usage (`npcs.json` not found, name missing).

```
python3 $SCRIPTS/voir_pnj.py $CAMP Firmin
python3 $SCRIPTS/voir_pnj.py $CAMP --list
```

---

## Summary of New Exit Codes

| Script | Exit 0 | Exit 1 | Exit 2 |
|--------|--------|--------|--------|
| `clock.py` | no overdue deadline | ≥ 1 overdue unresolved | usage |
| `close_session.py` | pipeline green | blocking step missing | usage |
| `validate_schema.py` | compliant with schemas | ≥ 1 schema gap | usage |
| `add_action.py` | action(s) added | invalid data | session not found/usage |
| `voir_pnj.py` | NPC found / `--list` | not found or ambiguous | npcs.json not found/usage |
