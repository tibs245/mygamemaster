# 10 — Unified feature flags (`meta.features`)

> A **single switch** per major axis of the game engine. Six axes, **all ON by default**, declared
> in one place (`monde.json > meta.features`), resolved by a **simple cascade** that is always
> **fail-open**. The goal: to lighten a campaign (or harden an instance default at deployment)
> **without touching code**, and to ensure an activated axis with missing data remains a **no-op**
> rather than an error.
>
> Source of truth for the resolver: `modules/gaming/mj-tonnerre/hooks/_lib.py` → `features()` /
> `hooks_cfg()`. This document describes the contract; the code is authoritative.

## 1. The six axes

| Axis | Enables… | Concrete effect | Required data |
|---|---|---|---|
| `tracabilite` | observability | CSV log `collecte.csv` + **auto-commit git** + **session snapshots** | none (always safe) |
| `verbosite` | rendered detail | **Persisted** block of the Steward + level `meta.verbosite` | none |
| `pnj_faction_vivants` | autonomous actors | modules `factions` / `proactivite_pnj` + actors that **think** (feeds `world_tick`) | `pnj.json` / `acteurs.json` (else inert) |
| `temporalite` | **living world** | `world_tick` engine **pre/post**, **scene brief** per turn, **causal propagation** | `geo.json` + `acteurs.json` (else no-op) |
| `images` | illustration | skill `mj-tonnerre-images` | none (API key at deployment) |
| `tts` | **narrative voice** | skill `mj-tonnerre-tts` (`!raconte`) + **auto-voice** of narration (Minimax `speech-2.8-turbo`, voice `French_Female_Speech_New`) attached as `MEDIA:` | none (key `MINIMAX_API_KEY` at deployment; else no-op) |

> Axis names are frozen in `_lib.FEATURES`:
> `("tracabilite", "verbosite", "pnj_faction_vivants", "temporalite", "images", "tts")`.

## 2. Resolution cascade

For **each** axis, the effective value is resolved from **most specific to most general**:

```
   meta.features.<axe>   >   env MJ_FEATURE_<AXE>   >   True
   (monde.json)              (instance default)        (universal default)
   the world has the         fixed at deployment       everything is ON as long
   final say                 (group_vars / quadlet)    as nothing says otherwise
```

- **`meta.features.<axe>`** in the campaign's `monde.json`: final authority, modifiable
  **hot** (no redeployment). Absent → step down one level.
- **`env MJ_FEATURE_<AXE>`** (ex. `MJ_FEATURE_IMAGES=0`): sets the **instance default**
  for the containerized environment. Allows an operator to enforce a default without editing data. Absent → step down one level.
- **`True`**: universal default. **No** configuration = **everything ON**.

Boolean coercion (`_lib.as_bool`) accepts standard env forms:
`1/true/yes/on/oui` → true, `0/false/no/off/non` → false; any unknown value **falls back to
the default** (never an error).

> **Why does the world override env?** Env describes *the instance* ("on this deployment, no
> images by default"); `monde.json` describes *the campaign's intent* ("but THIS
> campaign, yes"). A campaign thus remains portable across instances: it carries its
> explicit choices with it.

## 3. Hot vs. cold activation

The cascade from §2 has **two temporal stages**: depending on where you place the value, the
change is either immediate (at the next turn) or frozen until the next deployment.

| Where | Scope | When effect takes place |
|---|---|---|
| `monde.json > meta.features.<axe>` | **one** campaign | **hot** — at the **next turn**, no redeployment |
| `MJ_FEATURE_<AXE>` (container env) | **entire instance** | **cold** — at the **next container start** |

- **`monde.json` = hot.** The `monde.json` is **reloaded at each turn** (each hook and each
  script is a fresh process that reloads it): any modification to `meta.features` is thus
  applied **starting the next turn, without redeployment** or restart. This is the standard
  adjustment lever.
- **`MJ_FEATURE_*` = cold.** Environment variables are read **at startup** of the
  container and **frozen** for its entire lifetime. Changing them requires **redeployment**
  (regenerate the quadlet via Ansible then restart). They only serve to set the **instance default** (cf. §5.3); `monde.json` retains the **final say** (§2) and can therefore turn back on hot, for a
  campaign, what the instance shuts off by default.

### The `!feature` command — toggle hot without editing JSON

Rather than opening `monde.json` manually, an **admin** toggles an axis via the Discord
command `!feature <axe> on|off` (skill header `mj-tonnerre`). It relies on the deterministic script
`modules/gaming/mj-tonnerre/scripts/feature_toggle.py`, which rewrites `meta.features.<axe>`
atomically. Since this is a write to `monde.json`, the effect is **hot**: next
turn, no redeployment. Without arguments, `!features` / `!feature` **displays** the effective state
of the 6 axes (read, open to all); the `on|off` toggle is **reserved for admins**
(`meta.admins` / `MJ_ADMIN_IDS`).

```bash
# Check the effective state of the 6 axes
python3 modules/gaming/mj-tonnerre/scripts/feature_toggle.py <campaign> --list
# Toggle an axis hot (admin) — effect at next turn
python3 modules/gaming/mj-tonnerre/scripts/feature_toggle.py <campaign> images off
```

### "Soft" axes vs. "structural" axes

All axes toggle **technically** hot, but they don't have the same impact on a
**game in progress** — hence two families (the toggle signals this):

| Family | Axes | Toggle mid-session |
|---|---|---|
| **soft** | `images`, `verbosite`, `tracabilite`, `tts` | **safe anytime** — no effect on game state (rendering / internal logs only) |
| **structural** | `temporalite`, `pnj_faction_vivants` | **possible hot, but prefer at session boundaries**: these axes affect simulation (living world, autonomous actors); cutting mid-session can leave scheduled events or plans in limbo |

For a **structural** axis, `feature_toggle.py` emits a **warning** reminding of the preference for session boundaries; the `!feature` command **relays** it as-is. For a **soft** axis,
no warning: toggle peacefully, even mid-turn.

## 4. Safety principle: **ON by default + fail-open**

Two combined guarantees make "everything ON" **safe**:

1. **ON by default.** A campaign with **no** `meta.features` block behaves as if
   the six axes were `true`. You never forget to enable a feature; you optionally choose to **disable** it.
2. **Systematic fail-open.** An ON axis with **missing data** breaks nothing: it
   becomes a **silent no-op**. Examples:
   - `temporalite=true` but **no** `geo.json` / `acteurs.json` → `world_tick` and the scene
     brief **self-deactivate** (skip), the turn proceeds as today.
   - `pnj_faction_vivants=true` without actor sheets → the "thinking" hooks have nothing to
     animate, empty output.
   - `images=true` without API key → generation fails gracefully, narration continues.
   - `tts=true` without `MINIMAX_API_KEY` → no voice generated, written message goes out normally.

Consequence: you can **leave everything ON everywhere**. Campaigns that don't yet have their
spatial graph pay no price; those that do (`geo.json` + `acteurs.json` present)
automatically benefit from the living world.

### Articulation with `meta.hooks` (fine toggles)

Feature flags are the **main switches**; `meta.hooks` remains for **fine tuning**.
The composition rule (implemented in `_lib.hooks_cfg`) is: **an OFF axis forces OFF
all fine toggles it oversees**. Otherwise, the fine toggle decides (default ON).

| `meta.features` axis | Oversees `meta.hooks` toggles |
|---|---|
| `tracabilite` | `auto_commit`, `snapshot_fin_session` |
| `verbosite` | `banquier_persiste` |
| `temporalite` | `tick_pre`, `tick_post`, `brief_scene` |
| `pnj_faction_vivants` | exposed to `world_tick` (actors that think) |
| `tts` | `tts_auto` (auto-voice in `transform_llm_output`) |

> So `tts=false` cuts **everything** (auto-voice **and** `!raconte`). To keep the
> manual `!raconte` command but **cut auto-voice** (zero latency on turns), leave
> `tts=true` and set `meta.hooks.tts_auto=false` (surgical cut).

> So `temporalite=false` is enough to neutralize `tick_pre/tick_post/brief_scene` even if they are
> `true` further down — no need to set them to `false` one by one. Conversely, for a
> **surgical cut** (e.g. keep the scene brief but cut the closure reconciliation), leave `temporalite=true` and set `meta.hooks.tick_post=false`.

## 5. Configuration examples

### 5.1 "Light world" — no images, no temporality

For a pure narrative campaign, without spatial graph or illustration (the other three axes
remain ON):

```json
{
  "meta": {
    "features": {
      "tracabilite": true,
      "verbosite": true,
      "pnj_faction_vivants": true,
      "temporalite": false,
      "images": false
    }
  }
}
```

Effect: you keep the CSV log, auto-commit, Steward detail, and proactive factions/NPCs; you cut the `world_tick` engine + scene brief **and** the images skill. (Note:
with `temporalite=false`, even if `geo.json`/`acteurs.json` exist, the living world remains
dormant.)

### 5.2 "Complete world" — everything ON (default)

The case of `la-naissance-dun-roi`, which has `geo.json` + `acteurs.json`: "everything ON" actually
activates the living world.

```json
{
  "meta": {
    "features": {
      "tracabilite": true,
      "verbosite": true,
      "pnj_faction_vivants": true,
      "temporalite": true,
      "images": true
    }
  }
}
```

> **Strictly equivalent** to writing **nothing** (the six defaults are `true`). You can therefore
> omit the block entirely and get the same behavior. Writing it explicitly mainly serves as
> **in-situ documentation** (the `_schema` recalls the mapping) and an anchor point
> to modify an axis later.

### 5.3 Force an instance default at deployment (env)

To have a containerized instance start **by default without images** (without editing each
campaign's `monde.json`), define the corresponding Ansible variable — it injects
`MJ_FEATURE_IMAGES=0` into the container (see `ansible/templates/hermes-campagne.container.j2` and
`group_vars/all/main.yml`):

```yaml
# ansible/inventory/host_vars/<host>.yml  (or group_vars)
mj_feature_images: false        # → Environment=MJ_FEATURE_IMAGES=0 in the quadlet
```

Result: on this instance, any campaign **without** explicit `meta.features.images` key
starts with images **OFF**. A campaign that sets `"images": true` in its `monde.json` **turns back on**
images for itself alone (the world overrides env — §2).

> **Naming convention:** the Ansible variable `mj_feature_<axe>` (lowercase) controls the env
> `MJ_FEATURE_<AXE>` (uppercase). The variable is injected **only if it is defined**;
> undefined = no `Environment=` = runtime falls back to its default `True`.

## 6. Verify effective resolution

To inspect what the runtime actually calculates for a given campaign (accounting for
the current env):

```bash
python3 - <<'PY'
import sys, json
sys.path.insert(0, "modules/gaming/mj-tonnerre/hooks")
import _lib as L
monde = L.load_json("data/mj-tonnerre/campagnes/la-naissance-dun-roi/monde.json") or {}
print("features   :", json.dumps(L.features(monde), ensure_ascii=False))
print("hooks_cfg  :", json.dumps(L.hooks_cfg(monde), ensure_ascii=False))
PY
```

`features()` shows the six resolved axes; `hooks_cfg()` shows the fine toggles **after**
applying the oversight rule (a toggle overseen by an OFF axis comes back as `false`).

## 7. Key takeaways

- **Six axes, one place** (`meta.features`), **all ON by default**.
- **Cascade**: `meta.features.<axe>` (world, hot) **>** `MJ_FEATURE_<AXE>` (instance, at
  deployment) **>** `True` (universal).
- **Hot vs. cold** (§3): `monde.json` is reloaded each turn → changes **hot** (next
  turn, no redeployment); `MJ_FEATURE_*` is **cold** (instance default, redeployment
  required). The admin command `!feature <axe> on|off` toggles hot without editing JSON. **Soft** axes
  (`images`, `verbosite`, `tracabilite`, `tts`): safe to toggle anytime; **structural**
  (`temporalite`, `pnj_faction_vivants`): prefer session boundaries (the toggle warns).
- **Safety**: ON by default **+** fail-open → leaving everything ON is risk-free; axes with
  missing data are simple no-ops.
- **`meta.hooks`** remains for **fine** tuning: an OFF axis **forces OFF** the toggles it
  oversees; otherwise the toggle decides.
- **Deployment**: `mj_feature_<axe>` (Ansible) → `MJ_FEATURE_<AXE>` (env), injected **only
  if defined**.
