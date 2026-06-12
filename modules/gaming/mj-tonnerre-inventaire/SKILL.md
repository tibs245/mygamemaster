---
name: mj-tonnerre-inventaire
description: Manages player inventory in MJ Tonnerre — display, add, use, discard, transfer between players. Evolving YAML item base.
category: gaming
triggers:
  - "!inv"
  - "inventaire"
  - "équipement"
  - "sac"
  - "objets"
---

# 🎒 MJ Tonnerre — Inventory Management

## Architecture

```txt
~/.hermes/mj-tonnerre/
├── base_items.yaml              ← Evolving item base (all campaigns)
├── campagnes/<nom>/
│   ├── personnages/<id>.json    ← PC character sheet → "inventaire" field (free strings)
│   ├── pnj.json                ← Allied NPCs → "inventaire" field (free strings)
│   │                               Key locations → "inventaire_<lieu>" field {description, contenu[]}
│   └── monde.json              ← Locations/resources → regles.ressources
```

### Who has an inventory?

- **PC** → `personnages/<discord_id>.json > inventaire` (objects carried)
- **Allied NPC** (2+ sessions or companion) → `pnj.json > inventaire` (what they carry)
- **Key inhabited location** (cabin, base, camp) → associated NPC's `pnj.json` > `inventaire_<lieu>` (e.g. `inventaire_cabane`) = `{description, contenu[]}`

> **The GM READS these inventories.** **Mutations** (add / use / transfer) are VERIFIED by the Steward (3 checks — see `mj-tonnerre-intendant`), and the actual persisted delta is reported **automatically by the `transform_llm_output` hook**. You do NOT need to produce the persistence report manually.

### Inventory format in character sheet

**CURRENT format (real): array of free strings.** The GM **reads** this array.

```json
{
  "inventaire": [
    "15 silver crowns",
    "Rations (~1 day)",
    "Leather notebook",
    "Utility knife"
  ]
}
```

> ⚠️ A migration to a **structured** format `{nom, qte, type}` is documented as **INACTIVE TARGET** in `specs/hooks-runtime.md §7`. **Do NOT write it** until it is activated. The `desc/poids/valeur/effet` fields below (commands, item base) describe this future target, not the current format.

---

## Commands

| Command | Effect | Visibility |
|----------|--------|------------|
| `!inv` | Display player inventory | DM or `\|\|spoiler\|\|` |
| `!inv ajoute <objet> [qte]` | Add one or more copies of an object | Public confirmation |
| `!inv utilise <objet>` | Use/consume 1 object. If qte=1 → removed | Narrative result |
| `!inv jette <objet> [qte]` | Discard the object (lost for good) | Public confirmation |
| `!inv donne <objet> <@joueur>` | Transfer object to another player | Confirmation to both |
| `!inv info <objet>` | Display details of an object (from base_items or inventory) | Public |
| `!inv or <montant>` | Display gold coins (reminder) | DM or `\|\|spoiler\|\|` |

### Command details

#### `!inv` — Display

**Required** output format:

```
🎒 INVENTORY OF {CHAR_NAME}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
💰 Gold: {amount} GP
⚖️ Weight: {current}/{max} kg

📦 OBJECTS
• {name} x{qty} — {desc}
  ↳ Weight: {weight} kg · Value: {value} GP · {effect}

📦 OBJECTS (continued)
...

━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{slots_available} free slots
```

If inventory is empty:

```
🎒 INVENTORY OF {CHAR_NAME}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
💰 Gold: {amount} GP
⚖️ Weight: {current}/{max} kg

📦 OBJECTS
(Empty — your backpack echoes 🦗)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

- Default capacity: **Max weight = 10 × STR** (or 50 kg if no STR stat)
- The `effect` field only displays if non-empty

#### `!inv ajoute <objet> [qte]`

1. Search for `<objet>` in `base_items.yaml` (fuzzy match: exact name or keyword containing)
2. If found in base → copy complete fields (nom, desc, poids, valeur, effet)
3. If not found → create minimal entry: `{"nom": "<objet>", "qte": n, "desc": "", "poids": 0, "valeur": 0, "effet": ""}`
4. If object already exists in inventory → increment `qte`, do not duplicate
5. Check total weight — warn if exceeded
6. Update `personnages/<discord_id>.json`
7. Confirm:

```
✅ {name} x{qty} added to inventory.
   ⚖️ Total weight: {current}/{max} kg
   ⚠️ Overloaded! Movement penalty.  ← if exceeded
```

#### `!inv utilise <objet>`

1. Search for object in player inventory (fuzzy match)
2. Decrement `qte` by 1
3. If `qte` becomes 0 → **remove entry completely**
4. If `effet` non-empty → describe effect narratively
5. Update character sheet
6. Display confirmation:

```
🫧 {name} used.
   "{effect}"  ← if effect non-empty
   Remaining x{remaining_qty}.  ← if qty > 0
   The object disappears in a faint cloud of smoke. ✨  ← if qty = 0
```

#### `!inv jette <objet> [qte]`

1. Search for object in inventory
2. Remove specified quantity (or 1 by default)
3. If qty discarded ≥ qty owned → remove entry
4. Confirm:

```
🗑️ {name} x{qty} discarded.
   Remaining x{remainder}.  ← if any remains
   Farewell, old {name}...  ← if nothing left
```

#### `!inv donne <objet> <@joueur>`

1. Search for `<objet>` in giver's inventory
2. Extract `discord_id` of recipient from mention
3. Verify recipient has character sheet in same campaign
4. Remove object from giver's inventory (like `jette`)
5. Add object to recipient's inventory (like `ajoute`)
6. Log transfer
7. Confirm:

```
🤝 {name} given to @{recipient}.
   {giver} → {recipient} : {name} x{qty}
```

---

## Item Base (`base_items.yaml`)

File shared across all campaigns. Flat YAML format, organized by categories.

### Structure

```yaml
# ~/.hermes/mj-tonnerre/base_items.yaml
armes:
  epee_longue:
    nom: "Long sword"
    description: "Well-balanced steel blade, effective and versatile"
    valeur_or: 15
    poids: 3
    effet: "1d8 slashing damage"
    rarete: commun

armures:
  bouclier_bois:
    nom: "Wooden shield"
    description: "Round shield made of oak reinforced with iron"
    valeur_or: 10
    poids: 4
    effet: "+2 Defense"
    rarete: commun

potions:
  potion_soin:
    nom: "Healing potion"
    description: "Ruby-red vial that glimmers softly"
    valeur_or: 25
    poids: 0.5
    effet: "Restores 2d4+2 HP"
    rarete: commun

# ...
```

### Required fields per item

| Field | Type | Description |
|-------|------|-------------|
| `nom` | string | Display name |
| `description` | string | Descriptive text (1 sentence) |
| `valeur_or` | number | Price in gold pieces |
| `poids` | number | Weight in kg |
| `effet` | string | Mechanical or narrative effect (can be empty) |
| `rarete` | string | `commun`, `peu_commun`, `rare`, `épique`, `légendaire` |

### Adding items to base

When the GM invents a new object in play:

1. Player uses `!inv ajoute <objet>` with details in description
2. If object does not exist in base → skill proposes to GM:
   ```
   📝 New object detected: "{name}"
   Do you want to add it to the item base? (yes/no)
   ```
3. If yes → add to appropriate category in `base_items.yaml` with fields filled
4. GM can also add manually with `!baseitem ajoute <catégorie> <nom>`

---

## Compartmentalization Rules

> General compartmentalization rule: single source = header `mj-tonnerre/SKILL.md §2` (§9 = the GM keeps secrets). **Specific to inventory**:

- **A player's inventory is PRIVATE** → DM, or `||Discord spoilers||` in public channel. Suggest DM.
- Exception: `!inv ajoute`, `!inv jette`, `!inv donne` can have public confirmation (without complete inventory detail).
- Transfer (`!inv donne`) is logged on both giver and recipient side.

---

## Weight and Overload

- **Max weight** = 10 × STR (character's Strength stat). If no STR stat → 50 kg by default.
- Total weight is sum of `weight × qty` for each entry.
- Overload (`current_weight > max_weight`):
  - Display `⚠️ OVERLOADED!` in `!inv` display
  - Narrative penalty: reduced movement, disadvantage on physical rolls (per system)

---

## Standard Workflow

### Adding existing object (nominal case)

```
Player: !inv ajoute potion de soin 2

1. Search for "potion de soin" in base_items.yaml
2. Found → key "potions.potion_soin"
3. Current inventory: []
4. Add entry with complete fields, qty=2
5. Total weight: 1 kg (2 × 0.5)
6. Save character sheet
7. Reply: ✅ Healing potion x2 added. ⚖️ 1/50 kg
```

### Using object (qty > 1)

```
Player: !inv utilise potion de soin

1. Search for "potion de soin" in inventory
2. Found → qty=2
3. Decrement → qty=1
4. Effect: "Restores 2d4+2 HP"
5. Narrative result: "You drink the potion... +8 HP!"
6. Save
7. Reply: 🫧 Healing potion used. Remaining x1.
```

### Using object (qty = 1)

```
Player: !inv utilise potion de soin

1. Search → found, qty=1
2. Remove entry completely
3. Reply: 🫧 Healing potion used. The object disappears in a faint cloud of smoke. ✨
```

### Transfer between players

```
Player A: !inv donne épée longue @PlayerB

1. Search for "épée longue" in A's inventory → found, qty=1
2. Extract discord_id from @PlayerB
3. Verify B's character sheet in same campaign
4. Remove from A's inventory
5. Add to B's inventory
6. Save both sheets
7. Log transfer
8. Reply: 🤝 Long sword given to @PlayerB.
```

---

## Fuzzy Match

To find an object, try in order:

1. **Exact match** — identical `nom`
2. **Contains** — object whose `nom` contains search string (ex: "soin" → "Healing potion", "Superior healing potion")
3. **Keyword** — search in `description` (ex: "red" → Healing potion)
4. If multiple matches → ask player to clarify
5. If none → create object on the fly (mode "unknown object")

---

## Anti-Patterns

| ❌ Avoid | ✅ Do |
|---------|------|
| Display complete player inventory in public channel | DM or `\|\|spoiler\|\|` |
| Duplicate entries instead of incrementing `qty` | Increment `qty` |
| Leave entry with `qty: 0` | Delete entry |
| Forget to check weight | Calculate total weight on each modification |
| Search only in base, not in existing inventory | Search inventory first for modifications |
| **Forget NPC and location inventories** — hold only PC inventory | Check EVERY entity: PC + companion NPC + location used. An object left in a cabin is not "lost" — it is in the location's inventory (`inventaire_<lieu>.contenu`). |
| **Invent object** (PC, NPC or location) not listed | Rule "invented object": single source = header `mj-tonnerre/SKILL.md §8` (and §2 compartmentalization). Before any object mention, check entity's inventory; if absent, character does not have it. |

---

## Dependencies

- Parent skill: `mj-tonnerre` (loaded automatically in RPG session)
- Files: `~/.hermes/mj-tonnerre/campagnes/<nom>/personnages/<discord_id>.json`
- Files: `~/.hermes/mj-tonnerre/base_items.yaml`
- Tools: native JSON read/write (no external scripts needed)
- **Emoji convention:** `references/verbosite/README.md` (in `mj-tonnerre`) — use 🥦 for consumables, 🎒 for standard objects, ⚔️ for weapons/combat equipment in all inventory change notifications.