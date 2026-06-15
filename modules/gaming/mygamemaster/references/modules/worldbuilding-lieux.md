# Module — Location Creation: 10-Point Framework

> **Conditional loading.** This module applies only if the campaign declares `world.json > modules.worldbuilding_locations.active === true`. Recommended active by default, except for minimalist or single-location campaigns.
>
> **Note:** Points 5 (clock) and 7 (sovereignty) rely respectively on the `factions` module and `politics` module if active. If they are not, handle these points in a lightweight way (purely narrative clock, sovereignty = simple note).

**Absolute rule:** Each significant location (village, camp, hamlet, town, city) must be created with this complete framework. Pass-through hamlets or purely functional locations can fit in `world.json` with a lightweight version (points 1, 2, 5, 6, 7, 9).

## The 10 Points

**1. ✨ The Spark** — Strong concept that sums up the location in one sentence + immediate central conflict
- A striking image: "A village at the summit of a world-tree whose roots plunge into an underground lake."
- The central conflict: what **tears apart** or **threatens** the location upon arrival

**2. ⚙️ Vital Questions** — The immediate answers that give the location substance:
- Who governs here? (a council, a chief, no one, an entity?)
- Why does this location exist? (resource, refuge, passage, cult?)
- What is its critical need? (what is missing or what does it desperately protect)
- What is its shameful secret? (something the inhabitants hide)

**3. 🎭 3 Key NPCs** — Exactly three, no more at creation:
- **The Face** — the one you see first (welcome, first impression)
- **The Problem** — the one who has a need, a fear, a plan (quest driver)
- **The Shadow** — the one you don't see right away, but who pulls the strings
- Each has: a **desire**, a **weakness**, and a **distinctive appearance**

**4. 👃 Atmosphere** — Three strong sensations permeate the location every time you describe it:
- A smell, a persistent sound, a dominant tactile or visual sensation
- Example: *"smell of hops and sweat, constant sound of hammers, sky veiled by smoke"*
- No more than three — the rest is improvised

**5. ⏰ Seed of Conflict / Clock** — What WILL happen if the PCs do nothing:
- A precise deadline (in 3 days, the guard discovers the body)
- The consequence if the clock triggers (bridge closes, trial, massacre)
- The levers the PCs can pull to slow down/speed up

**6. 🕸️ Ties to the World** — How the location breathes with what surrounds it:
- **Routes/Access** — where goods come from, how long to reach the nearest neighbor
- **Dependencies** — who the location needs to survive (water, food, protection, knowledge)
- **Frictions** — which neighbor it is in silent or declared conflict with
- **Rumors from Elsewhere** — what arrives from outside and disturbs the balance

**7. 🏛️ Sovereignty** — What comes down from the higher layers to this location (politics module if active):
- **Effective Attachment** — what entity does this location really belong to?
- **Claims** — what entities claim it without controlling it?
- **Coveting** — what factions or powers covet it?
- **Active Constraints** — what the higher layers already impose on the location (laws, taxes, military presence)?

**8. 📈 Dynamics** — The location is a secondary character: it has its own objectives and evolves even without the PCs:
- **Own Objective** — what does the location seek? (to expand, survive, trade, hide)
- **Means** — what resources does it have to achieve it?
- **Documented Progress** — numerical or narrative sliders on ongoing projects (bridge repaired 35%, negotiation 10%)
- Evolution: success → prosperity, decline → abandonment/death, transformation → change of nature
- At each narrative transition or session start: advance the sliders and play out the consequences

**9. ⚖️ Laws and Morality** — The invisible framework that sets the location's temperature:
- **Cardinal Laws** — 3 to 5 written or customary rules that really matter (not the complete criminal code)
- **Justice** — how it is rendered (judge, crowd, duel, oracle) and what the penalties are
- **Taboos** — what is not done, what is not said
- **Tolerances** — what strangers would find shocking but locals accept
- **Latent Moral Tension** — part of the population is starting to reject the old rules

**10. 🕳️ The Sacred Void** — What remains blank and will be filled by improvisation or player actions:
- Unnamed secondary characters, undescribed streets, secrets you haven't invented yet
- Why: the best idea will come **during play**, not in front of your screen

## JSON Template for a Significant Location

```json
{
  "nom": "Location-Name",
  "essence": "Strong concept — 1 sentence that sums it all up",
  "conflit_central": "What tears apart or threatens the location",
  "questions_vitales": {
    "gouvernance": "...",
    "raison_existence": "...",
    "besoin_critique": "...",
    "secret_honteux": "..."
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
  "liens_monde": {
    "routes": [],
    "dependances": [],
    "frictions": [],
    "rumeurs": []
  },
  "souverainete": {
    "rattachement_effectif": null,
    "revendications": [],
    "convoitises": []
  },
  "contraintes_actives": [],
  "dynamique": {
    "objectif": "",
    "moyens": [],
    "progres": {},
    "evolution": ""
  },
  "lois_et_morale": {
    "lois_cardinales": [],
    "justice": "",
    "tabous": [],
    "tolerances": [],
    "tension_morale": ""
  },
  "vide_sacre": ""
}
```

## Lightweight Version (Pass-Through Hamlets, Functional Locations)

In `world.json > universe.regions[].lieux`:

```json
{
  "nom": "[Name of functional location]",
  "type": "[type, e.g.: fortified bridge]",
  "description": "[short description]",
  "conflit": "[the conflict or tension of the location]",
  "souverainete": "[attachment entity, if the politics module is active]",
  "lois": "[local law in one sentence]"
}
```

## Verification at Creation

For each new significant location, run through this mini-checklist before declaring it ready:
1. □ Does the location have an immediate central conflict?
2. □ Does it have exactly 3 key NPCs with desire + weakness?
3. □ Does it have a clock (what happens if the PCs do nothing)?
4. □ Is it connected to the world (routes, dependencies, frictions)?
5. □ Does it have clear sovereignty (via `souverainte` — politics module)?
6. □ Does it have active constraints (`contraintes_actives[]`) from higher layers?
7. □ Does it have its own dynamics (objectives + progress)?
8. □ Does it have laws and morality (even informal)?
9. □ Is there a sacred void left for improvisation?

Points 1, 3, 4, 5 are mandatory **from first appearance**. The others can be refined during play.

The impact of political entities (N+2/N+1) on each location is documented via `contraintes_actives`. See the `politique` module for sovereignty and political entities.
