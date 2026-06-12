# Module — Artefacts: tracking important world objects

> **Conditional loading.** This module applies only if the campaign declares `monde.json > modules.artefacts.actif === true`.

**Principle:** Objects that are narratively important (artefacts, relics, mysterious objects, physical signs) deserve their own structured tracking, just like NPCs or factions. Do not leave them floating orphaned in the narration.

**Standard structure in `monde.json > etat_global.artefacts_connus`:** each documented artefact must have:
- `nom` — unique, descriptive identifier
- `type` — nature of the object (Ritual Figurine, Ancient Artefact, Weapon, Sign, Document, etc.)
- `description` — what we know about it physically
- `source` — where and when it was discovered (with session reference)
- `localisation_actuelle` — where it is now (on whom, in which location)
- `liens_hypotheses` — array of possible connections to other elements, ALL marked UNCONFIRMED HYPOTHESIS as long as they haven't been played out
- `statut_connaissance` — what the PC knows about it (Seen, Examined, Collected, Not examined, etc.)

**Rules:**
1. ✅ Create an `artefacts_connus` entry **on first narrative mention** of an important object, not at wrap-up. A minimal placeholder is enough — refine it later.
2. ✅ The `liens_hypotheses` must be explicitly marked as hypotheses, not facts. Use the prefix `UNCONFIRMED HYPOTHESIS — `.
3. ✅ Update `localisation_actuelle` with each movement or change of hands.
4. ❌ Do not leave an object narrated but unfiled — it is an object that exists only in the GM's memory, lost at the next session.
5. ✅ See also the distinction `faits_etablis` vs `hypotheses_mj` (section §4.1 and `references/pnj-data-governance.md`) — the same principle applies to artefacts.

**Generic example:**
```json
{
  "nom": "[Ancient ritual object]",
  "type": "Ritual Figurine",
  "description": "Dark wood statuette, base burned by design...",
  "source": "[Place of discovery] ([session ref])",
  "localisation_actuelle": "Still in place — not collected",
  "liens_hypotheses": [
    "UNCONFIRMED HYPOTHESIS — could be linked to [another element seen in play]"
  ],
  "statut_connaissance": "Seen and examined by [the PC], not collected"
}
```
