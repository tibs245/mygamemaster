---
name: mygamemaster-inventory
description: Manages player inventory in MJ Tonnerre — display, add, use, discard, transfer between players. Evolving YAML item base.
category: gaming
triggers:
  - "!inv"
  - "inventory"
  - "equipment"
  - "backpack"
  - "items"
---

# 🎒 MJ Tonnerre — Inventory Management

## Architecture

```txt
~/.hermes/mygamemaster/
├── base_items.yaml              ← Evolving item base (all campaigns)
├── campaigns/<name>/
│   ├── characters/<id>.json    ← PC character sheet → "inventory" field (free strings)
│   ├── npcs.json                ← Allied NPCs → "inventory" field (free strings)
│   │                               Key locations → "inventory_<lieu>" field {description, contenu[]}
│   └── world.json              ← Locations/resources → rules.ressources
```

### Who has an inventory?

- **PC** → `characters/<discord_id>.json > inventory` (objects carried)
- **Allied NPC** (2+ sessions or companion) → `npcs.json > inventory` (what they carry)
- **Key inhabited location** (cabin, base, camp) → associated NPC's `npcs.json` > `inventory_<lieu>` (e.g. `inventory_cabane`) = `{description, contenu[]}`

> **The GM READS these inventories.** **Mutations** (add / use / transfer) are VERIFIED by the Steward (3 checks — see `mygamemaster-steward`), and the actual persisted delta is reported **automatically by the `transform_llm_output` hook**. You do NOT need to produce the persistence report manually.

### Inventory format in character sheet

**CURRENT format (real): array of free strings.** The GM **reads** this array.

```json
{
  "inventory": [
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
| `!inv add <item> [qty]` | Add one or more copies of an item | Public confirmation |
| `!inv use <item>` | Use/consume 1 item. If qty=1 → removed | Narrative result |
| `!inv discard <item> [qty]` | Discard the item (lost for good) | Public confirmation |
| `!inv give <item> <@player>` | Transfer item to another player | Confirmation to both |
| `!inv info <item>` | Display details of an item (from base_items or inventory) | Public |
| `!inv gold <amount>` | Display gold coins (reminder) | DM or `\|\|spoiler\|\|` |

### Command details

#### `!inv` — Display

**Required** output format:

```
🎒 INVENTORY OF {CHAR_NAME}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
💰 Gold: {amount} GP
⚖️ Weight: {current}/{max} kg

📦 ITEMS
• {name} x{qty} — {desc}
  ↳ Weight: {weight} kg · Value: {value} GP · {effect}

📦 ITEMS (continued)
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

📦 ITEMS
(Empty — your backpack echoes 🦗)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

- Default capacity: **Max weight = 10 × STR** (or 50 kg if no STR stat)
- The `effect` field only displays if non-empty

#### `!inv add <item> [qty]`

1. Search for `<item>` in `base_items.yaml` (fuzzy match: exact name or keyword containing)
2. If found in base → copy complete fields (nom, desc, poids, valeur, effet)
3. If not found → create minimal entry: `{"name": "<item>", "qte": n, "desc": "", "poids": 0, "valeur": 0, "effet": ""}`
4. If item already exists in inventory → increment `qte`, do not duplicate
5. Check total weight — warn if exceeded
6. Update `characters/<discord_id>.json`
7. Confirm:

```
✅ {name} x{qty} added to inventory.
   ⚖️ Total weight: {current}/{max} kg
   ⚠️ Overloaded! Movement penalty.  ← if exceeded
```

#### `!inv use <item>`

1. Search for item in player inventory (fuzzy match)
2. Decrement `qte` by 1
3. If `qte` becomes 0 → **remove entry completely**
4. If `effet` non-empty → describe effect narratively
5. Update character sheet
6. Display confirmation:

```
🫧 {name} used.
   "{effect}"  ← if effect non-empty
   Remaining x{remaining_qty}.  ← if qty > 0
   The item disappears in a faint cloud of smoke. ✨  ← if qty = 0
```

#### `!inv discard <item> [qty]`

1. Search for item in inventory
2. Remove specified quantity (or 1 by default)
3. If qty discarded ≥ qty owned → remove entry
4. Confirm:

```
🗑️ {name} x{qty} discarded.
   Remaining x{remainder}.  ← if any remains
   Farewell, old {name}...  ← if nothing left
```

#### `!inv give <item> <@player>`

1. Search for `<item>` in giver's inventory
2. Extract `discord_id` of recipient from mention
3. Verify recipient has character sheet in same campaign
4. Remove item from giver's inventory (like `discard`)
5. Add item to recipient's inventory (like `add`)
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
# ~/.hermes/mygamemaster/base_items.yaml
armes:
  epee_longue:
    nom: "Long sword"
    description: "Well-balanced steel blade, effective and versatile"
    valeur_or: 15
    poids: 3
    effet: "1d8 slashing damage"
    rarete: common

armures:
  bouclier_bois:
    nom: "Wooden shield"
    description: "Round shield made of oak reinforced with iron"
    valeur_or: 10
    poids: 4
    effet: "+2 Defense"
    rarete: common

potions:
  potion_soin:
    nom: "Healing potion"
    description: "Ruby-red vial that glimmers softly"
    valeur_or: 25
    poids: 0.5
    effet: "Restores 2d4+2 HP"
    rarete: common

# ...
```

### Required fields per item

| Field | Type | Description |
|-------|------|-------------|
| `name` | string | Display name |
| `description` | string | Descriptive text (1 sentence) |
| `valeur_or` | number | Price in gold pieces |
| `poids` | number | Weight in kg |
| `effet` | string | Mechanical or narrative effect (can be empty) |
| `rarete` | string | `common`, `uncommon`, `rare`, `epic`, `legendary` |

### Adding items to base

When the GM invents a new item in play:

1. Player uses `!inv add <item>` with details in description
2. If item does not exist in base → skill proposes to GM:
   ```
   📝 New item detected: "{name}"
   Do you want to add it to the item base? (yes/no)
   ```
3. If yes → add to appropriate category in `base_items.yaml` with fields filled
4. GM can also add manually with `!baseitem add <category> <name>`

---

## Compartmentalization Rules

> General compartmentalization rule: single source = header `mygamemaster/SKILL.md §2` (§9 = the GM keeps secrets). **Specific to inventory**:

- **A player's inventory is PRIVATE** → DM, or `||Discord spoilers||` in public channel. Suggest DM.
- Exception: `!inv add`, `!inv discard`, `!inv give` can have public confirmation (without complete inventory detail).
- Transfer (`!inv give`) is logged on both giver and recipient side.

---

## Weight and Overload

- **Max weight** = 10 × STR (character's Strength stat). If no STR stat → 50 kg by default.
- Total weight is sum of `weight × qty` for each entry.
- Overload (`current_weight > max_weight`):
  - Display `⚠️ OVERLOADED!` in `!inv` display
  - Narrative penalty: reduced movement, disadvantage on physical rolls (per system)

---

## Standard Workflow

### Adding existing item (nominal case)

```
Player: !inv add healing potion 2

1. Search for "healing potion" in base_items.yaml
2. Found → key "potions.potion_soin"
3. Current inventory: []
4. Add entry with complete fields, qty=2
5. Total weight: 1 kg (2 × 0.5)
6. Save character sheet
7. Reply: ✅ Healing potion x2 added. ⚖️ 1/50 kg
```

### Using item (qty > 1)

```
Player: !inv use healing potion

1. Search for "healing potion" in inventory
2. Found → qty=2
3. Decrement → qty=1
4. Effect: "Restores 2d4+2 HP"
5. Narrative result: "You drink the potion... +8 HP!"
6. Save
7. Reply: 🫧 Healing potion used. Remaining x1.
```

### Using item (qty = 1)

```
Player: !inv use healing potion

1. Search → found, qty=1
2. Remove entry completely
3. Reply: 🫧 Healing potion used. The item disappears in a faint cloud of smoke. ✨
```

### Transfer between players

```
Player A: !inv give long sword @PlayerB

1. Search for "long sword" in A's inventory → found, qty=1
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

To find an item, try in order:

1. **Exact match** — identical `name`
2. **Contains** — item whose `name` contains search string (ex: "heal" → "Healing potion", "Superior healing potion")
3. **Keyword** — search in `description` (ex: "red" → Healing potion)
4. If multiple matches → ask player to clarify
5. If none → create item on the fly (mode "unknown item")

---

## Anti-Patterns

| ❌ Avoid | ✅ Do |
|---------|------|
| Display complete player inventory in public channel | DM or `\|\|spoiler\|\|` |
| Duplicate entries instead of incrementing `qty` | Increment `qty` |
| Leave entry with `qty: 0` | Delete entry |
| Forget to check weight | Calculate total weight on each modification |
| Search only in base, not in existing inventory | Search inventory first for modifications |
| **Forget NPC and location inventories** — hold only PC inventory | Check EVERY entity: PC + companion NPC + location used. An item left in a cabin is not "lost" — it is in the location's inventory (`inventory_<lieu>.contenu`). |
| **Invent item** (PC, NPC or location) not listed | Rule "invented item": single source = header `mygamemaster/SKILL.md §8` (and §2 compartmentalization). Before any item mention, check entity's inventory; if absent, character does not have it. |

---

## Dependencies

- Parent skill: `mygamemaster` (loaded automatically in RPG session)
- Files: `~/.hermes/mygamemaster/campaigns/<name>/characters/<discord_id>.json`
- Files: `~/.hermes/mygamemaster/base_items.yaml`
- Tools: native JSON read/write (no external scripts needed)
- **Emoji convention:** `references/verbosity/README.md` (in `mygamemaster`) — use 🥦 for consumables, 🎒 for standard items, ⚔️ for weapons/combat equipment in all inventory change notifications.