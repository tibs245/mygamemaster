# 📋 Template — Problem / Solution / Consequence

> Structured format to document post-session fixes.
> Each problem = one entry in a dedicated `.md` file.
> To be reviewed at the end of the session for collective validation.

## Structure

```markdown
## 🚨 Problem <num> — <short title>
*[Description of the problem — inconsistency, oversight, narrative error, file discrepancy, etc.]*

**💡 Proposed solution:** *[The exact correction or solution applied.]*

**⚖️ Consequence:** *[Impact on the game, characters, world — what changes concretely.]*

---
```

## Usage rules

1. **One file per session** — named `probleme-session<N>.md`, placed at the root of the campaign or in `audits/`
2. **One problem per entry** — even if problems are linked, separate them. Each has its own solution and consequence.
3. **Consequence is mandatory** — without an identifiable consequence, it is not a problem. Rephrase or remove.
4. **Review at end of session** — the file serves as the basis for collective discussion. Do not close without reviewing it.

## Example (from the Birth of a King campaign, S7)

```markdown
## 🚨 Problem 1 — Missing time tracking in world.json
`world.json` did not have a `regles.temps.suivi` section to track the
current day/hour, making temporal consistency difficult.

**💡 Proposed solution:** Addition of `regles.temps.suivi` with
`jour_courant`, `heure_courante`, `derniere_ellipse`, and `jalons_temporels`.

**⚖️ Consequence:** The GM can verify the exact moment of narration
at a glance. Milestones serve as reference points to avoid unintended
temporal jumps.
```