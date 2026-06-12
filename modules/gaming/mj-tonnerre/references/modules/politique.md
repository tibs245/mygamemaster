# Module — Politics: world layers, sovereignty and political entities

> **Conditional loading.** This module only applies if the campaign declares `monde.json > modules.politique.actif === true`. Relevant for political campaigns, kingdom-building campaigns, or territorial stakes. Unnecessary for a closed room, a dungeon, pure exploration.

---

## Part A — World layers and sovereignty

### Principle

A location is never isolated. It is traversed by political, economic, and cultural forces that come from above — and which it can influence in return. These forces are organized in **nested layers** (N+2, N+1, N, etc.).

**Layers are:**
- **Optional** — an N+1 entity can exist without N+2 (independent kingdom, city-state)
- **Variable in nature** — the names change depending on the world (Empire, Coalition, Union, Duchy, Republic — these are examples, not absolutes)
- **Flexible** — an N+2 layer can be a voluntary membership structure with withdrawal rights (coalition, trading union, alliance)
- **Descending in constraints** — decisions made in an upper layer impact lower layers

### The generic model

```
Layer N+2   ← large entity (ex: Empire, Coalition, Union, Holy Alliance, Council)
   ↓ downward impact
Layer N+1   ← local entity (ex: Kingdom, Duchy, Republic, City-State, Country)
   ↓ downward impact
Layer N     ← territory (ex: Region, Province, March, Canton)
   ↓ downward impact
Location
```

**Fundamental rule:** each layer transmits constraints to the layer below. But each layer can resist, deviate, or ignore them based on its situation — that is where stories are born.

### The 3 status levels of one layer over the next

| Status | Meaning | Example |
|--------|---------|---------|
| **🔗 Effective attachment** | The territory *truly* belongs to the entity. Laws, taxes, administration applied. | A province administered by its kingdom |
| **👁️ Claim** | The entity claims that the territory belongs to it — but lacks the means to enforce it | A crown claims a border march |
| **👀 Coveting** | The entity wants control — but has no formal right, openly or in secret | A criminal faction covets a passage point |

An entity without any of these three statuses in a zone = no political relationship = **ignorance** or **indifference**.

### Membership modes to an upper layer

An entity at layer N can belong to a layer N+1 in several ways:

| Mode | Description | Example |
|------|-------------|---------|
| **🤝 Free** | You join and leave voluntarily. Conditions negotiated. | Trading union — membership vote, unilateral withdrawal right |
| **⚔️ Constrained** | You are there by force, conquest, unequal treaty or necessity. Leaving = war. | Imposed protectorate, occupied territory, forced tribute |
| **👑 Inherited** | You were born into it. Membership is transmitted by blood, land, title. | Feudal monarchy — oath of vassalage, hereditary succession |
| **🔀 Mixed** | A historical constrained core + voluntary peripheral members. | Empire with conquered provinces and allies |

**Each political entity defines its membership mode in its `type` and `regles` fields.**

### The special case: free territory

A "free" territory is not a void or a bug — it is a **story engine**. Its freedom is temporary, contested, and fragile. This is exactly what makes it interesting for play.

### Generic data structure (political entity)

```json
{
  "univers": {
    "entites_politiques": [
      {
        "nom": "Name of the entity",
        "type": "Description of its nature (monarchy, coalition, union, republic, etc.)",
        "regles": "How it functions (membership, voting, inheritance, withdrawal right)",
        "membres": ["Entities from the lower layer that are members"],
        "impact_couche_inf": "What this entity imposes on members (taxes, laws, obligations)"
      }
    ]
  }
}
```

### Structure of `souverainete` for a region

```json
{
  "souverainete": {
    "rattachement_effectif": null,
    "revendications": ["List of entities that claim it"],
    "convoitises": [
      {"nom": "Entity or faction", "nature": "Type of coveting"}
    ],
    "note": "Narrative context of the political situation"
  }
}
```

### The question to ask at each location creation

> *What descends from the upper layers down to this location?*
> *What does this location send upward (resource, problem, information)?*

And conversely, when creating a policy in an upper layer:

> *How does this decision concretely manifest at a location?*

### Evolution of status in play

The transition from one status to another (free → claimed → attached) is a **narrative engine** to track via the faction clock (factions module):

```
🔗 Attached      → an administered region can revolt, change sides
👁️ Claimed      → a claimed region can be taken, defended, negotiated
👀 Coveted      → a coveted region can attract conflicts, alliances
```

Each status change is a **playable consequence** for the PCs.

---

## Part B — Political entities (complete framework)

### Principle

The same principles that make a location or faction alive apply to political entities (kingdoms, empires, coalitions, republics, city-states, etc.). They are **characters at territorial scale** — with their own objectives, dynamics, clocks, tensions, and secrets.

### Commonalities with the location framework

| Location point | Applied to political entity |
|---|---|
| **✨ 1. Spark + conflict** | Concept that sums up the entity + the conflict tearing it apart |
| **⚙️ 2. Vital questions** | Who governs? Why does it exist? Its critical need? Its shameful secret? |
| **🎭 3. Key NPCs** | Figures of power: sovereign, advisor, opponent, secret agent |
| **👃 4. Atmosphere** | Three sensations that permeate its court, halls, streets |
| **⏰ 5. Clock** | What happens if nothing is done — succession, invasion, famine, civil war |
| **🕸️ 6. Links** | Alliances, rivalries, dependencies, rumors with other entities |
| **📈 8. Dynamics** | Objectives, means, progress — advances independently of PCs |
| **⚖️ 9. Laws and morality** | Written laws, justice, taboos, internal tensions |
| **🕳️ 10. Sacred void** | What remains to improvise — unknown plots, hidden heirs, future betrayals |

### Commonalities with the faction framework

| Faction point | Applied |
|---|---|
| **Attitude** | Toward PCs — evolves with actions |
| **ST / LT objectives** | Independent of PCs, self-renewing |
| **Inter-faction relations** | Alliances, rivalries, hostilities |
| **Action clock** | Deadlines, consequences, modifying factors |
| **Observed clues** | Traces that PCs can discover |

### What is unique to political entities

| Field | Description |
|---|---|
| `mode_adhesion` | How you enter and leave: 🤝 Free / ⚔️ Constrained / 👑 Inherited / 🔀 Mixed |
| `membres` | Entities from layer N-1 that are members |
| `impact_couche_inf` | What the entity imposes on lower layers (taxes, laws, military obligations) |
| `souverainete` | Which territories it controls, claims, or covets |
| `stabilite_interne` | Is the entity united, fragile, on the verge of implosion? |

### Complete template

```json
{
  "nom": "Name of the entity",
  "type": "Nature + membership mode (ex: Feudal monarchy — hereditary and constrained)",
  "regles": "How it functions (voting, inheritance, membership, withdrawal right)",
  "etincelle": "Strong concept in one sentence",
  "conflit_central": "What tears it apart or threatens it",
  "questions_vitales": {
    "gouvernance": "Who decides and how",
    "raison_existence": "Why this entity exists",
    "besoin_critique": "What it lacks or what it protects",
    "secret_honteux": "What it hides"
  },
  "pnjs_cles": {
    "visage": {"nom": "", "desir": "", "faiblesse": ""},
    "probleme": {"nom": "", "desir": "", "faiblesse": ""},
    "ombre": {"nom": "", "desir": "", "faiblesse": ""}
  },
  "ambiance": ["sensation1", "sensation2", "sensation3"],
  "horloge": {
    "evenement": "",
    "echeance": "",
    "consequence": "",
    "leviers_pj": []
  },
  "liens": {
    "alliances": [],
    "rivalites": [],
    "dependances": [],
    "rumeurs": []
  },
  "membres": ["Entities N-1 that are members"],
  "souverainete": {
    "territoires_controles": [],
    "revendications": [],
    "convoitises": []
  },
  "impact_couche_inf": "What it imposes on lower layers",
  "stabilite_interne": "United / Fragile / On the verge of implosion",
  "dynamique": {
    "objectif_court_terme": "",
    "objectif_long_terme": "",
    "moyens": [],
    "progres": {}
  },
  "lois_et_morale": {
    "lois_cardinales": [],
    "justice": "",
    "tabous": [],
    "tolerances": [],
    "tension_morale": ""
  },
  "relations": {},
  "attitude_pj": "",
  "indices_observes": [],
  "vide_sacre": ""
}
```

### Lightweight version (distant or minimally detailed entities)

```json
{
  "nom": "Name",
  "type": "Nature + membership mode",
  "etincelle": "Short concept",
  "conflit_central": "",
  "membres": [],
  "stabilite_interne": "",
  "horloge": {}
}
```
