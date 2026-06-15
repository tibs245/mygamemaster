# 🏷️ Relationship Levels — NPC & PC

## Definition

Each relationship between a PC and an NPC (or between two PCs) has a **level** that summarizes the quality of the bond.
This level can evolve through actions and dialogue.

---

## Full Scale

| Level | Meaning | Typical NPC Behavior | Possible Evolution |
|--------|------|-----------------------------|-------------------|
| **Unknown** | Never met, or encountered without exchange | Neutral. Knows nothing about you. | → Acquaintance after an interaction |
| **Acquaintance** | You've talked, cordial exchange | Polite, professional. No personal investment. | → Ally (service rendered) / Wary (conflict) |
| **Ally** | Common objective, basic trust | Cooperates, shares info. Trusts you on operational matters. | → Friend (personal bond) / Acquaintance (betrayal) |
| **Friend** | Personal bond, solid trust | Confides in you, defends you, makes efforts for you. | → Confidant (deep bond) / Hostile (serious betrayal) |
| **Confidant** | Confidant, strong bond | Would share their most intimate secrets. Protects you at risk of their own life. | — stable or → Hostile (ultimate betrayal) |
| **Wary** | Doubt, not yet trusting | Evasive, watches you, verifies your claims. | → Acquaintance (proof of good faith) / Hostile (provocation) |
| **Hostile** | Tense, declared antagonism | Seeks you out, provokes you, blocks you. Not yet open war. | → Enemy (escalation) / Wary (de-escalation) |
| **Enemy** | Active opposition, open conflict | Attacks you, betrays you, works against you actively. | — rarely reversible |

---

## Application in Files

### In the PC Character Sheet (PC's perception)
```json
"relations": {
  "Varek": {
    "niveau": "Connaissance",
    "description": "Steward of the Guild. Seems tired but honest."
  }
}
```
→ *How Oscar perceives Varek*

### In the NPC File (NPC's perception)
```json
{
  "nom": "Varek",
  "relation_niveau": "Allié",
  "attitude": "Tired but determined."
}
```
→ *How Varek perceives the group*

---

## Asymmetry

The two levels **can be different**. This is normal and intentional:

```
Oscar → Varek : Acquaintance
  ↕ (asymmetry)
Varek → group : Ally
```

Varek can already consider Oscar an Ally (he is counting on him to find the Khâl Squad) while Oscar still sees him as merely an Acquaintance. Both perspectives coexist.

---

## When the Level Changes

| Situation | Typical Change |
|-----------|-------------------|
| Service rendered to the NPC | ⬆ Acquaintance → Ally or Friend |
| Saving the NPC's life | ⬆ Friend → Confidant |
| Betrayal / Discovered Lie | ⬇ Ally → Hostile |
| Verbal Conflict / Provocation | ⬇ Acquaintance → Wary |
| Aid in Distress | ⬆ Wary → Acquaintance |
| Escalation of Hostilities | ⬇ Hostile → Enemy |

The GM rarely announces a level change explicitly — they play it through the NPC's behavior. Players can ask to see their level via `!fiche`.