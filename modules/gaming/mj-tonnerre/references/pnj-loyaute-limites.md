# NPC Loyalty and Limits

## Principle

An allied NPC is not a robot. They have their own **limits**, **fears**, **values**, and **patience**. The relationship level determines what they are willing to do — but their individual limits can block even a request from a close friend.

## Loyalty Chart

The `relation_niveau` in the NPC sheet determines what they will accept doing without negotiation or rolls:

| Level | Services Provided | Risk Accepted | What is **Excluded** (unless massive favor in return) |
|--------|----------------|----------------|------------------------------------------------------|
| 🔘 **Stranger** | Nothing. You don't exist for them. | None | Anything that costs them time, money, or energy |
| 🔵 **Acquaintance** | Info, one night's lodging, loan of basic tool. Service given = service expected in return. | Low — doesn't risk life or possessions | Accompany into dangerous zones, get involved for you, lend valuable object |
| 🟢 **Ally** | Shared objective → accompanies, fights at your side, takes measured risks. | Moderate — up to getting wounded or losing gear | Betray their own, engage in open war without prep, kill innocent |
| 🔵 **Friend** | Beyond contract. Shares resources, takes risks for you, houses you without question. | High — risks life, deprives self for you | Betray fundamental values, abandon family/responsibilities, follow you on suicide mission |
| 🟣 **Close** | Almost anything. Would follow you to the ends of the world. Shares deepest secrets. Their loyalty is an extension of yours. | Very high — sacrifice possible | Go against their core nature (e.g., pacifist who kills, loyal one who breaks oath). These individual limits are sacred — even a Close one can say no. |

## Individual Limits for Each NPC

Each recurring NPC has **personal limits** — red lines they will not cross, no matter their attachment to the PC.

**Where to store them:** In `npcs.json` → `limites` field:

```json
"limites": {
  "lignes_rouges": [
    "Does not kill innocents — no matter the reason",
    "Does not steal from those who have sheltered them",
    "Does not abandon their cabin for more than 3 days"
  ],
  "peurs": [
    "Fears …"  // optional — what makes them hesitate
  ],
  "motivations_personnelles": [
    "Wants to find missing loved one alive",
    "Wants their region to stay free"
  ]
}
```

**How it works in play:**

- If the PC asks an allied NPC to **kill an unarmed prisoner** → their `ligne_rouge` "Does not kill innocents" blocks them. They refuse, end of story. No roll, no negotiation.
- If the PC asks an allied NPC to **accompany them into a risky zone** (but within their abilities) → the `relation_niveau` (Ally) allows it. They accept.
- If the PC asks an allied NPC to **abandon them and never return** → that exceeds Ally scope. Friend or Close level required.

## Building the Relationship

### Factors that increase loyalty:
- ✅ The PC **protects** the NPC (saves them from danger, takes a hit for them)
- ✅ The PC **respects** their limits and values
- ✅ The PC **shares** resources, discoveries, information
- ✅ The PC **keeps their promises**
- ✅ Time spent together and hardships endured

### Factors that decrease loyalty:
- ❌ The PC **puts the NPC in danger for nothing** (uses them as a shield, sends them scouting without prep)
- ❌ The PC **ignores their limits** (asks them to do what they won't, insists)
- ❌ The PC **lies** or **breaks a promise** made to the NPC
- ❌ The PC **takes without giving** (uses their resources with no return)
- ❌ The PC **acts against the NPC's values** (kills an innocent before them, allies with an enemy they hate)

### Level Changes

Relationship level can go up or down based on PC actions. No mechanical threshold — it's narrative:

- **A landmark action** (save NPC's life) → can move from Acquaintance to Ally
- **A betrayal** (lie, use, abandon) → can drop from Ally to Distrustful or Hostile
- **Accumulation of small actions** (keep promises, share, respect) → relationship rises gradually

**Record the change:** Update `relation_niveau` in `npcs.json` and add a `fait_etabli` to trace when the change happened.

## Generic Example — an Allied NPC

```json
"relation_niveau": "Ally — established trust, accompanies PC in explorations"
```

**What an Ally NPC will accept doing:**
- ✅ Accompany PC into risky zone
- ✅ Stand watch, share provisions
- ✅ Provide information about the region
- ✅ Lend a hand in combat

**What they would refuse (personal limits — to validate in play):**
- ❌ Kill an innocent
- ❌ Permanently abandon their home without guarantee of return
- ❌ Betray their loved ones or those they know
- ❌ Venture alone into territory they don't know at all

## Quick Test Before Each NPC Request

1. What is the current `relation_niveau`?
2. Is the request in the "Services Provided" column for that level? → ✅ accepted
3. Otherwise → request exceeds level → polite refusal or negotiation
4. Does the request touch an NPC `ligne_rouge`? → ❌ categorical refusal
5. If refusal → PC can attempt negotiation (Persuasion/Diplomacy roll, or service in exchange)