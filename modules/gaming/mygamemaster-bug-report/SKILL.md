---
name: mygamemaster-bug-report
description: Allows the player to report an issue — context, what happened, what was expected. Stored in a separate folder for deferred processing.
category: gaming
triggers:
  - "!bug"
  - "!report-bug"
  - "report a bug"
  - "player bug report"
  - "issue"
  - "player inconsistency"
---

# 🐛 MJ Tonnerre — Bug Report (Player)

> **Command** : `!bug`
> **Usage** : Report an issue, inconsistency, or unexpected behavior.
> The report is stored in a separate folder and processed later via `!analyse-bug`.

## 1. Why this skill?

`!analyse-bug` is a technical tool for the GM. `!bug` is for **the player**.
It allows the player to cleanly report what is wrong without interrupting
the game, and without the GM having to remember everything.

**Typical flow:**
```
1. During play, the player notices an inconsistency
2. They type !bug
3. The skill guides them to fill in: context + issue + expected
4. The report is stored in bug-reports/<id>.md
5. After the session, the GM (or analyst) processes the report
```

---

## 2. Command

### `!bug` — Start a report

The skill dialogues with the player to capture 3 pieces of information:

**Step 1 — Context**
> "Where / when did you notice the issue?"
> Ex: "During the walk to the cabin, S8", "When [NPC] spoke about [a location]"

**Step 2 — What happened**
> "Describe what happened (the inconsistency you saw)."
> Ex: "[NPC] said they had already passed [a location], but I thought they had never been there."

**Step 3 — What was expected**
> "What should have happened according to you?"
> Ex: "[NPC] should have said they had never been there, as established in the story."

### Short format (optional)

The player can also provide everything at once:
> `!bug Context: During dialogue at [a location]. Issue: [NPC] didn't react after my answer. Expected: They were supposed to uncross their arms, which was played afterward but not logged.`

The skill automatically parses the `Context:`, `Issue:`, `Expected:` markers.

---

## 3. Storage format

> ⚠️ **Path to confirm (outside `cwd` campaign):** bug-reports are stored **outside** the campaign directory (they persist across campaigns). The exact path depends on the runtime — use the configured bug-reports root (noted `<BUG_ROOT>` below), not a hardcoded `~/...` path.

Reports are stored in:
```
<BUG_ROOT>/<campaign>/<date>-<id>.md
```

### Example

```markdown
# 🐛 Bug Report — S8 — 2026-06-07

**Reported by:** [player] ([PC])
**Date:** 2026-06-07
**Session:** 8
**Status:** 🟡 Open

## Context
During the walk to the cabin (S8), [PC] asks [NPC] what they
think of [a location].

## Issue
[NPC] said: "I passed by once, years ago."
But in the story, [NPC] has never been to [a location].

## Expected
[NPC] should have said they had never been there but had
heard about it. This is consistent with their established_facts.

## Processing
<!-- Filled by GM / analyse-bug after the session -->
- [ ] Analyzed (date: )
- [ ] 🐛 BUG / 🎭 NOT A BUG / 🔍 Insufficient documentation
- [ ] Correction applied
- [ ] Report closed

## GM Note
<!-- Space for GM comments after analysis -->
```

---

## 4. Storage and organization

### Folder
```
<BUG_ROOT>/
├── <campaign-A>/
│   ├── 2026-06-07-001-<keyword>.md
│   └── ...
└── <campaign-B>/
    └── ...
```

### Naming
`<date>-<number>-<keyword>.md`
Ex: `YYYY-MM-DD-001-<subject>.md`

### Index file (optional)
`<BUG_ROOT>/index.json` (optional) — lists all reports
with their status and campaign for easy tracking.

```json
{
  "campaigns": {
    "<campaign>": [
      {
        "id": "2026-06-07-001",
        "file": "<campaign>/YYYY-MM-DD-001-<subject>.md",
        "status": "open",
        "summary": "[NPC] talks about [a location] when they've never been there"
      }
    ]
  },
  "last_id": 1
}
```

---

## 5. Report statuses

| Status | Meaning |
|--------|---------|
| 🟡 **Open** | Report created, awaiting analysis |
| 🔵 **In Progress** | Currently being analyzed by the GM |
| 🐛 **Confirmed** | Bug confirmed, awaiting correction |
| 🎭 **Rejected** | Not a bug — narrative consistency |
| 🔍 **Clarification Needed** | Need more information |
| ✅ **Resolved** | Fixed and closed |

---

## 6. Integration with !analyse-bug

After the session, the GM can process the reports:

```
!bug list           → Display all open reports
!bug show <id>      → Display a specific report
!bug close <id>     → Close a report (after processing)
!bug status <id> <status> → Change the status
```

When the GM processes a report, they can launch `!analyse-bug` on the reported
issue and link the analysis report to the bug report.

---

## 7. Rules

- **The player cannot modify their report after submission** — they can create a new one if needed
- **The player sees their own reports** with `!bug list` — not those of other players
- **The GM sees all reports** of the campaign
- **Reports never modify campaign data** — they are external documents
- **One report = one issue** — if the player has multiple issues, they create multiple reports

---

## 8. Safeguards

- **Zero self-correction** : the player reports, the GM processes. The player does not patch.
- **Zero data modification** : reports are in a separate folder.
- **Zero pressure** : the player reports when they want, the GM processes when they can.

---

## References

- `mygamemaster-analyst/SKILL.md` — Technical analysis after report
- `mygamemaster-session/SKILL.md` — Session wrap-up (ideal time to process bugs)