---
name: mygamemaster-images
description: Manages image generation for MJ Tonnerre — scenes, portraits, maps — following the style → templates → instances pipeline. Delegates generation to OpenRouter (google/gemini-3.1-flash-image-preview by default, recraft/recraft-v4.1 as sketch-style fallback) or ComfyUI (local/cloud fallback).
category: gaming
triggers:
  - "!image"
  - "!portrait"
  - "!carte"
  - "!illustration"
  - "generate image"
  - "illustration"
  - "portrait of"
  - "map of"
---

# 🎨 MJ Tonnerre — Image Generation

## Objective

Generate illustrations for the RPG campaign (scenes, character portraits, location maps) with **absolute visual consistency** : everything starts from the `style_visuel` defined in `world.json`, passes through reusable templates, and produces instances.

---

## Visual Pipeline

```
┌──────────────────────────────────────────────────┐
│  1. VISUAL STYLE                                 │
│  world.json → meta.style_visuel                  │
│  • technique (illustration style, medium)        │
│  • palette (dominant colors, chromatic mood)     │
│  • ambiance (lighting, atmosphere)               │
│  • description_complete (canonical prompt)       │
└────────────────────┬─────────────────────────────┘
                     │
┌────────────────────▼─────────────────────────────┐
│  2. TEMPLATES                                    │
│  images/templates/                               │
│  • template_portrait.json  (base prompt)         │
│  • template_scene.json     (base prompt)         │
│  • template_carte.json     (base prompt)         │
│  Generated at onboarding, inherit the style      │
└────────────────────┬─────────────────────────────┘
                     │
┌────────────────────▼─────────────────────────────┐
│  3. INSTANCES                                    │
│  images/portraits/  — !portrait <character_name> │
│  images/scenes/     — !image <description>       │
│  images/cartes/     — !carte <location>          │
│  Each instance = template + specific context     │
└──────────────────────────────────────────────────┘
```

### Golden Rule

**Every prompt begins with `style_visuel.description_complete`.** This is non-negotiable — it's what guarantees the visual consistency of the campaign.

---

## File Architecture

```
~/.hermes/mygamemaster/campaigns/<campaign-name>/
├── world.json                              ← contains meta.style_visuel
├── images/
│   ├── templates/
│   │   ├── template_portrait.json          ← prompt template for portraits
│   │   ├── template_scene.json             ← prompt template for scenes
│   │   └── template_carte.json             ← prompt template for maps
│   ├── portraits/
│   │   ├── <character_name>.png            ← final portrait
│   │   └── <character_name>.json           ← metadata (prompt, date, seed)
│   ├── scenes/
│   │   ├── <slug>.png                      ← scene illustration
│   │   └── <slug>.json                     ← metadata
│   └── cartes/
│       ├── <location>.png                  ← location/region map
│       └── <location>.json                 ← metadata
```

---

## Structure of `world.json > meta.style_visuel`

```json
{
  "meta": {
    "style_visuel": {
      "technique": "dark fantasy oil painting, gritty textures, dramatic lighting",
      "palette": "muted earth tones, deep crimson accents, stormy grays",
      "ambiance": "twilight, misty, oppressive yet epic",
      "description_complete": "Dark fantasy oil painting style, gritty textures, dramatic chiaroscuro lighting. Color palette of muted earth tones with deep crimson accents and stormy grays. Twilight atmosphere, misty and oppressive yet epic in scale. High detail, 8K quality."
    }
  }
}
```

### Required Technical Tags in `description_complete`

The `description_complete` must include precise technical tags for quality generation:

| Element | Examples |
|---------|----------|
| **Artistic style** | `oil painting`, `digital art`, `ink drawing`, `watercolor`, `concept art` |
| **Quality** | `8K`, `highly detailed`, `masterpiece`, `sharp focus` |

> The **ratio** does NOT go in the prompt: it passes through `image_config.aspect_ratio` (mapping by type: see « Required Parameters »). **Negatives** integrate as text (« Avoid: … »), not as a flag `--no`.

---

## Templates

### Template Format (`templates/template_portrait.json`)

```json
{
  "type": "portrait",
  "prefix": "<style_visuel.description_complete>",
  "prompt_template": "Character portrait of {race} {classe}. {apparence}. {contexte}. Solo character, front-facing, detailed facial features, fantasy character design.",
  "negative_prompt": "text, watermark, signature, multiple characters, cropped, deformed, blurry",
  "ratio": "3:4",
  "steps": 30,
  "cfg": 7.5
}
```

### Scene Template (`templates/template_scene.json`)

```json
{
  "type": "scene",
  "prefix": "<style_visuel.description_complete>",
  "prompt_template": "Fantasy scene: {description}. Wide angle, environmental storytelling, atmospheric.",
  "negative_prompt": "text, watermark, signature, modern elements, UI, HUD",
  "ratio": "16:9",
  "steps": 30,
  "cfg": 7.5
}
```

### Map Template (`templates/template_carte.json`)

```json
{
  "type": "carte",
  "prefix": "<style_visuel.description_complete>",
  "prompt_template": "Fantasy map of {lieu}. Top-down cartography style, parchment texture, vintage map aesthetics, labeled regions: {elements}. Decorative compass rose, sea monsters in margins, aged paper borders.",
  "negative_prompt": "text, modern elements, satellite imagery, photorealistic, 3D render",
  "ratio": "1:1",
  "steps": 30,
  "cfg": 7.5
}
```

> This fantasy template serves only for **evocative sketch** (default) and **fallback** without `geo.json`. For a precise map, don't fill in `{elements}` manually: generate a **deterministic schema** from `geo.json` (`map_schema.py`) and pass it as `--ref-image` to the model, which only needs to embellish it. See the detailed `!carte` section below (levels A/B/C).

### Template Generation at Onboarding

When `mygamemaster-initiation` finishes creating a campaign, it must:

1. Generation is done via OpenRouter `google/gemini-3.1-flash-image-preview` (if `OPENROUTER_API_KEY` is defined; ComfyUI fallback archived, see Pipeline 2).
2. For each type (portrait, scene, map), create the template JSON file in `images/templates/`
3. Inject `description_complete` as `prefix` in each template
4. Save the templates

**Do not generate template images at onboarding** — these are prompt skeletons, not images. Instances will be generated on demand.

---

## Commands

The 4 commands (`!image`, `!portrait`, `!carte`, `!illustration session`) share **a single workflow**. Only the template, ratio, output folder, context source and messages vary — see the **specifics table** below.

> `!image` is the canonical name for the scene command (no `!create-image` variant).

### Generic Workflow (all commands)

0. **🚦 Feature flag guard — images.** If `world.json > meta.features.images` == `false` (or env `MGM_FEATURE_IMAGES=0`), briefly respond that illustrations are **disabled for this world** and **DO NOT generate an image** (stop here, do not execute subsequent steps). *Reminder: everything is ON by default — only act if the axis is explicitly `false`; if the info is not readable, consider the axis ON and generate normally (fail-open).* Wiring detail: `docs/living-world/10-features.md`.
1. **Determine active campaign** (check `world.json`). If absent → *« No active campaign. Run `!init` or `!campaign active <name>`. »*
2. **Load** `world.json` → `meta.style_visuel.description_complete`, then the **template** for the command (see table).
3. **Gather context** specific to the command (see « Context » column of table).
4. **Build final prompt** : `{description_complete}` + filled template. **Never one without the other** (see Golden Rule). Integrate exclusions as text (« Avoid: text, watermark, signature… »).
5. **Generate** via `generate_reviewed.py` (normal path: generate + review + retry, see « Effective Generation »). Ratio = `--aspect` from table. ComfyUI fallback only if OpenRouter unavailable.
6. **Check exit code** (see code table) before posting.
7. **Save** image at the **path actually returned** by the script (extension may differ from `.png`, see « Variable Output Format ») in the command folder, + its sidecar `.json`.
8. **Post to Discord** : `MEDIA:<actual path returned>` (never hardcode `{slug}.png`) + success message.

### Specifics Table

| Command | Template | `--aspect` | Folder / name | Context gathered (step 3) |
|----------|----------|-----------|---------------|------------------------------|
| `!image <description>` | `template_scene.json` | `16:9` | `images/scenes/{slug}.png` (slug = description lowercase, hyphens) | the description provided |
| `!portrait <character_name>` | `template_portrait.json` | `3:4` | `images/portraits/{character_name}.png` | character sheet (see below) |
| `!carte <location> [--precise]` | `template_carte.json` | `1:1` | `images/cartes/{location}.png` | **fidelity by source** (see `!carte` detail) : default = evocative sketch fed by `geo.json` ; `--precise`/cartographer = schema→embellishment pipeline (positions+routes guaranteed by `map_schema.py`) ; `--unreliable` = faked map (failure/trap). Fallback if no `geo.json` : regions/POI from `world.json > locations > {location}` |
| `!illustration session` | `template_scene.json` | `16:9` | `images/scenes/session_{N}_recap.png` | `resume` from `sessions/<derniere>.json` (3-5 sentences) ; prompt suffixed *« Key moment from a fantasy RPG session: {resume}. Cinematic composition, dramatic lighting, emotional impact. »* |

### Details by Command

**`!portrait` — character sheet lookup and enrichment:**
- Traverse `characters/*.json`, search for `meta.character_name` (fuzzy match). If not found → *« Character "{name}" not found in this campaign. Check the spelling. »*
- Inject `meta.race` → `{race}`, `meta.class_` → `{classe}`, `meta.apparence` → `{apparence}`, and a `{contexte}` (e.g. current location).
- If `apparence` missing, build it: `"{race} {classe}. Notable equipment: {equipment[0]}, {equipment[1]}. Key stats: {stats dominantes}."`
- If portrait already exists → offer existing file + *« To regenerate: `!portrait {name} --force` »*. `--force` overwrites existing and passes current portrait as `--ref-image` (see below).

**`!carte` — a map has a DIEGETIC SOURCE, which determines its precision, style AND reliability.**

A map is never « objective truth » : it's a fictional object *drawn by someone*, under given conditions. This source determines the fidelity level. We aim for just evocation for RPG, not an architect's blueprint — an image model can't place anything correctly on its own anyway. Three levels, from lightest to most exact:

**(A) Inhabitant Sketch — default.** For an ordinary `!carte` : evocative prompt, « sketch quickly drawn by a villager », approximate and assumed. Feed the prompt from `geo.json` to cite **the right places and their general relations** (neighborhoods, atmosphere, biomes), **without** seeking exact positions. Fast, reliable, consistent for RPG. The `prefix` `description_complete` (Golden Rule) and template style remain.

> To get context without ever manipulating coordinates (layer C, reserved for code) : `geo_query.py <campaign> who-is-at <location_id> --json` (sub-locations + occupants) and `neighbors <location_id> --json` (edges: `to`, `dir`, `distance_m`, `path`). The LLM cites, it doesn't calculate.

**(B) Cartographer's Map — precise, on demand or by fiction.** When the map is supposed to be the work of a cartographer (PC/NPC skilled), or on explicit demand (`!carte <location> --precise`) : **schema → embellishment pipeline**, where **code draws the layout, not the model** (validated: Gemini respects the layer). The schema is passed as a **layer** (`--ref-mode layer`) and creativity is constrained (`--temperature 0.2`).

```bash
SCHEMA=/opt/modules/gaming/mygamemaster/scripts/map_schema.py
GEN=/opt/modules/gaming/mygamemaster-images/scripts/generate_reviewed.py
CARTES=<campaign>/images/cartes
# 1) Deterministic schema + versioned + reproducible prompt, in one command.
#    Carries: REAL positions, winding routes that avoid obstacles,
#    biomes (grounded extent), town size (∝ connectivity), PIN markers.
python3 "$SCHEMA" <campaign_folder> --lieu <location_id> --labels pins \
    --emit-prompt --version --out "$CARTES/_schema_<location>.svg"
#    → writes, suffixed by world state HASH <h> : _schema_<location>.<h>.png (layer),
#      .prompt.txt (ready-to-use prompt), .legend.txt, .hash. Old version remains
#      (HISTORY). Hash changes ONLY if world changes.
# 2) PERSISTENCE / reuse: if <CARTES>/<location>.png exists AND <location>.hash == <h>,
#    DO NOT regenerate — reuse the image (consistency: the bar doesn't move). Otherwise:
# 3) Embellishment (default = Gemini 3.1 flash ; --precise → Gemini 3 Pro) :
python3 "$GEN" --prompt-file "$CARTES/_schema_<location>.<h>.prompt.txt" \
    --out "$CARTES/<location>.png" --aspect 1:1 \
    --ref-image "$CARTES/_schema_<location>.<h>.png" \
    --ref-mode layer --temperature 0.2 \
    --model google/gemini-3.1-flash-image-preview   # --precise → google/gemini-3-pro-image-preview
# then copy <h> into <CARTES>/<location>.hash (marks persisted version).
```

**Models** (tested) : **Gemini 3.1 flash** by default (≈ $0.04, very good) ; **Gemini 3 Pro** for main maps/`--precise` (≈ $0.10, most faithful). ⚠️ `--temperature` is only honored by Gemini — omit it for OpenAI models (they reject it).

**Temporal Consistency (central requirement).** Rendering is **deterministic** : same world state → **same layer, always**. A forest only grows/disappears **if the world changes** : its extent reads the `etendue` attribute of the location in `geo.json` (else type default) — deforestation/drought is an *event* that modifies `etendue`, never random. The **version hash** (`--version`) timestamps each state : regenerate only when it changes, **persist** layers + final images, and keep history.

**Extensible Semantics by Campaign (all universes).** The type→render table lives in `map_schema.py` (fantasy defaults), overridable by campaign via `<campaign>/carte_semantique.json` : `{"types": {"<type>": {color, shape (circle|square|triangle|diamond|star), family (city|biome|water|landmark|other), obstacle, etendue, visible, visual}}}`. **`visible: false` ⇒ type never appears** (abstract/secret location) — the indicator « what must / must not appear ». Generate a commented template: `python3 "$SCHEMA" <campaign> --dump-semantique`. An SF/post-apo game thus defines its own types without touching code.

> The **SVG** is the canonical layer (carries all info, inspectable). Data *exact* (locations, neighborhoods, routes, types) vs *synthesized* for conditioning (extent, town size, sinuosity) — all deterministic and grounded in `geo.json` + semantic table.

**What the map says — and does NOT say (essential nuance, take ownership).** We separate **logic** (code draws) from **data** (GM defines their world) : we don't predict any world, we provide tools.
- **Drawn routes = trade routes** : easiest paths **by the world's transport means** (set by GM via `carte.detours/routes`). They **avoid** `obstacle:true` — difficult terrain *for this transport*.
- An obstacle is **never a barrier**. Players can always **leave the roads** : climb the cliff, cross the river. The map shows the path *known and easy*, not the limit of possibility.
- **Off-road difficulty** (river current, scalability, weather) is **GM arbitration**, not map data. Tools to decide: `geo_query.py … distance --as-the-crow-flies`, `path`, `crossing` — *spatial truth* deterministic, distinct from *narrative*.
- So: **map = a view** (trade routes), **`geo_query` = tools** (measurements), **GM = rules** (what's crossable, at what cost, in THIS world). If a player invents an unexpected way, nothing in the system forbids it — GM adjudicates.

**(C) UNRELIABLE Map — failure, critical failure, trap. 🤫** When a character fails a cartography/navigation roll, or finds a trapped/deceptive map, the GM can generate a **deliberately false map** : `python3 "$SCHEMA" <campaign_folder> --lieu <location_id> --unreliable --seed <N>` scrambles positions, swaps labels, adds a phantom route and location — then embellish normally. **Nothing on the image signals it as false.**
- It's **known to the GM only** (trace intent in `GM-INTENTION-LOG.md`, never visible to player).
- If player cries bug: **NEVER confirm a bug** or the intent. Stay in fiction — *« the map you found may not have been drawn by a sure hand… »*. The map isn't broken: it's *unreliable*, and that's diegetic.

**Fallback (degraded mode).** If `temporality` is explicitly `false`, or no readable `geo.json` : simple decorative map (fantasy template, `{elements}` provided else regions/POI from `world.json > locations > {location}`). And if location undocumented: *« 📝 **{location}** is not yet documented. I'm generating a general map. Think about enriching `world.json` (or run `geo_query.py build` then `map_schema.py` for a faithful map) ! »*

**(D) Town/Village Map — micro detail (coming soon).** A regional map shouldn't try to show buildings of a village (unreadable). Dense detail (the tavern doesn't move, player orientates) will be **a separate map**, backed by a **`geo.json` specialized « town »** (micro scale: streets, buildings = containment sub-locations), generated as needed and **persisted** like regional maps. Same temporal consistency principle. *Not implemented — dedicated feature.*

---

## Visual Consistency by Base Portrait

### Principle

To guarantee that **a character's face remains identical** across images (portrait, scene, session illustration), the `generate_reviewed.py` script accepts `--ref-image <path>` (repeatable up to 3 times). The reference image is sent to the model as multimodal input : Gemini receives the existing portrait alongside the prompt and preserves the face, hair color, skin tone and distinctive features. Only pose, expression, lighting and framing vary.

### Application Rules

**`!portrait <name>` — first portrait (no reference available)**
- Generate normally (without `--ref-image`).
- The produced portrait becomes the **canonical reference** for the character: it is saved in `images/portraits/<name>.<ext>`.

**`!portrait <name> --force` — regenerate existing portrait**
- Pass the current portrait as reference: `--ref-image images/portraits/<name>.<ext>`.
- The new portrait will preserve the face from before while possibly changing pose or lighting.

**`!image <description>` — scene with named characters**
- If the description mentions one or more characters whose portrait already exists in `images/portraits/`, pass these portraits as `--ref-image` (max 3).
- Detection: search in the description for `meta.character_name` values from `characters/*.json` sheets (fuzzy match, case-insensitive).
- If a mentioned character has no portrait yet → generate the scene without reference for that character; note *« ⚠️ No reference portrait for **{name}**. Run `!portrait {name}` first to freeze their appearance. »*

**`!illustration session`** — apply same logic: detect characters in session summary and pass their portraits as `--ref-image`.

### Typical Call (scene with two referenced characters)

```bash
SCRIPT=/opt/modules/gaming/mygamemaster-images/scripts/generate_reviewed.py
echo "{description_complete} {filled scene template} Avoid: text, watermark." \
  | python3 "$SCRIPT" \
      --out /path/campaign/images/scenes/{slug}.png \
      --aspect 16:9 \
      --threshold 8 --max-attempts 2 \
      --ref-image /path/campaign/images/portraits/oscar.png \
      --ref-image /path/campaign/images/portraits/cendre.png \
      --meta-json '{"type":"scene","campagne":"<name>"}'
```

### Sidecar `.json` — reference traceability

The `ref_images` field is added to sidecar when references are used:

```json
{
  "type": "scene",
  "prompt": "...",
  "ref_images": [
    "/path/campaign/images/portraits/oscar.png",
    "/path/campaign/images/portraits/cendre.png"
  ],
  "review": { ... }
}
```

### Limits and Graceful Degradation

- **Portrait not found** (`--ref-image` points to missing file) : script emits warning to stderr and generates without this reference (no blocking failure).
- **Recraft (`--crayon`)** : Recraft model doesn't support multimodal input — `--ref-image` are silently ignored ; warning is emitted.
- **Max 3 references** : beyond that, payload becomes too heavy and model may refuse. Cap is applied automatically (excess references ignored).
- **OpenRouter Compatibility** : feature depends on multimodal support of Gemini 3.1 Flash Image via OpenRouter. If API refuses (security refusal or unsupported format), script exits with code 1 and diagnosis — restart without `--ref-image` as fallback.

### Messages by Command

| Command | Start | Success |
|----------|-------|--------|
| `!image` | *« 🎨 Generating scene... (style: {technique}) »* | image + *« 🖼️ Illustration generated. »* |
| `!portrait` | *« 🎨 Generating portrait of **{character_name}**... ({race}, {classe}) »* | image + name |
| `!carte` | *« 🗺️ Mapping **{location}**... »* | map + *« 🗺️ Map of **{location}** generated. »* |
| `!illustration` | *« 🎬 Illustration of session {N} recap... »* | image + formatted recap |

Generation error (code ≠ 0) : *« ⚠️ Generation failed. Check that `OPENROUTER_API_KEY` is defined or ComfyUI is running. »*

---

## Effective Generation

This skill supports **two generation pipelines**, tried in order :

### Pipeline 1 : OpenRouter (recommended — zero setup)

If an OpenRouter token is available (variable `OPENROUTER_API_KEY`), use the following models:

| Model | Usage | Cost | Quality |
|--------|-------|------|---------|
| **`google/gemini-3.1-flash-image-preview`** (**Nano Banana 2**) | **Default** — portraits, scenes, everyday maps | preview | Latest Gemini image generation ; more details, better precision, better prompt adherence |
| **`recraft/recraft-v4.1`** | **On explicit demand only** (« sketch version explorer's notebook » or `!image --crayon`) | ~$0.04/image | Excellent sketch/sketchy style, perfect for explorer's notebook |

**Rule** : Always use `google/gemini-3.1-flash-image-preview` (Nano Banana 2) by default. Switch to Recraft only if user explicitly requests sketch/sketchy style.

> **Note on « avoid Gemini » preference** : image generation is the **only exception**. Nano Banana 2 **is** a Gemini model (Gemini 3.1 Flash Image) — but Gemma (nor any equivalent non-Gemini model) can *generate* images, so we keep it here. Everywhere else (review/vision, judge, delegation), use **Gemma** (`google/gemma-4-31b-it` for vision) — best quality/price ratio.

**⚠️ REQUIRED Parameters (otherwise no image returned) :**

For a Gemini model to return an **image** (and not just text), the request body **must** contain:

| Field | Value | Why |
|-------|--------|----------|
| `modalities` | `["image", "text"]` | **Without this field, model responds in text only** — this is the #1 cause of « no image ». Non-negotiable. |
| `image_config.aspect_ratio` | `"16:9"`, `"3:4"`, `"1:1"`… | Native ratio control. Midjourney-style `--ar` flags in the prompt **don't work** here. |

Native ratios supported by Gemini : `1:1`, `2:3`, `3:2`, `3:4`, `4:3`, `4:5`, `5:4`, `9:16`, `16:9`, `21:9`. Mapping by type :

| Type | `aspect_ratio` |
|------|----------------|
| Scene / session illustration | `16:9` |
| Portrait | `3:4` |
| Map | `1:1` |

> **Negatives with Gemini** : there is **no** `negative_prompt` field on OpenRouter/Gemini (that's a Stable Diffusion/ComfyUI concept). To exclude elements, **integrate them in the prompt text** : `« … Avoid: text, watermark, signature, deformed hands. »`. The `negative_prompt` field from templates serves only the ComfyUI fallback.

**Permanent Scripts (shipped with module) — NEVER rewrite on the fly or recreate `/tmp/gen_image.py` :**

```
/opt/modules/gaming/mygamemaster-images/scripts/
├── generate_reviewed.py   ← DEFAULT COMMAND : generate + review + retry at threshold
├── gen_image.py           ← low-level brick : generate an image (no review)
└── review_image.py        ← low-level brick : review existing image
```

All: key read from environment (never as argument), retries on transient errors, prompt via **stdin**/`--prompt-file` (never as argument), base64 response read from socket. Detail: `scripts/README.md` or `--help`.

**➡️ Normal Path : `generate_reviewed.py`** — it chains generation → **systematic review** (vision model) → if score < threshold, reinjects reviewer corrections and **regenerates** (up to `--max-attempts`), then keeps best image. This makes review **tamper-proof** (see « Review & Regeneration » section — no need to run manually). It writes sidecar `.json` with `review` block (score, threshold, verdict).

**Typical Call (scene) :**

```bash
SCRIPT=/opt/modules/gaming/mygamemaster-images/scripts/generate_reviewed.py
echo "{description_complete} {filled template} Avoid: text, watermark, signature." \
  | python3 "$SCRIPT" \
      --out /path/campaign/images/scenes/{slug}.png \
      --aspect 16:9 \
      --threshold 8 --max-attempts 2 \
      --meta-json '{"type":"scene","campagne":"<name>","style_snapshot":{...}}'
```

Options : `--aspect` (16:9 scenes · 3:4 portraits · 1:1 maps), `--threshold N` (min score /10, default 8), `--max-attempts N` (default 2), `--criteres "…"` (review criteria ; default = prompt), `--crayon` (Recraft), `--model`/`--review-model`, `--prompt-file`, `--json`, `--no-meta`. For generation **without** review (rare cases), use directly `gen_image.py` (same options minus `--threshold`/`--max-attempts`).

**Exit codes — check systematically before posting :**

| Code | Meaning | Action |
|------|---------|--------|
| `0` | image produced (`OK: …`) | read `passed`/`score` : if `passed` true → post ; if false (threshold not met after retries) → GM decision: post as-is or retry with higher `--max-attempts` |
| `1` | total generation failure (no image, even on 1st try) | relay diagnosis ; rephrase or switch to ComfyUI |
| `2` | usage (missing key, invalid ratio, empty prompt) | fix the call |

Never post image if code ≠ 0.

> **⚠️ Variable Output Format** : script adjusts extension to actual format (PNG/JPEG/WebP — Nano Banana 2 varies). **Always post the path actually returned** (field `image` from `--json`, or line `OK: …`) ; never hardcode `{slug}.png`. Detail: `scripts/README.md` §1 (« Variable »).

**Cost:** see OpenRouter model page (Nano Banana 2 is in *preview* — price may change ; Recraft v4.1 ~$0.04/image).

**Flag `!image --crayon` / `!portrait --crayon` / `!carte --crayon` :** passes `--crayon` to script → `recraft/recraft-v4.1`, sketch-style explorer's notebook rendering.

### Pipeline 2 : ComfyUI (historic fallback — unavailable by default)

> ⚠️ **Historic fallback, NOT available by default** : the `comfyui` skill is **archived** (no longer in `modules/`). Normal pipeline is OpenRouter (above). Don't count on ComfyUI without reinstalling that skill.
>
> If `comfyui` is ever reactivated : it generates locally via Stable Diffusion/Flux, the templates' `negative_prompt` serves it then (ratio passes through `width`/`height` : 16:9 → 1344×768, 3:4 → 768×1024, 1:1 → 1024×1024), and the generated image is moved to command folder then given its sidecar `.json`.

---

## Metadata Files

Each generated image comes with a `.json` file of the same name:

```json
{
  "type": "portrait|scene|carte|session_recap",
  "campagne": "<campaign-name>",
  "date": "2026-05-14T16:30:00Z",
  "personnage": "<character_name> (portraits only)",
  "session": 3,
  "prompt": "<complete prompt used>",
  "negative_prompt": "<negative prompt>",
  "seed": 84729301,
  "ratio": "3:4",
  "workflow": "sdxl_txt2img.json",
  "style_snapshot": {
    "technique": "...",
    "palette": "...",
    "ambiance": "..."
  }
}
```

Useful for :
- **Regeneration** : reproduce exact same image (same seed + prompt)
- **Variation** : same prompt, different seed
- **Traceability** : know what style was active at generation time

---

## 🔍 Review & Regeneration (REQUIRED)

**Every generated image must be reviewed and regenerated if necessary.** Never post an image without prior review. The current generation model (Nano Banana 2 / Gemini 3.1 Flash Image) produces uneven results — anatomy, style, details can vary greatly from one generation to another.

### Review is Applied Automatically

This obligation is **realized by construction** whenever we generate via **`generate_reviewed.py`** (normal path, above) : it reviews each image with a vision model (`google/gemma-4-31b-it`), and if the score is below `--threshold` (default 8/10), it reinjects reviewer corrections into the prompt and **regenerates** up to `--max-attempts`, then keeps best. Score, threshold and verdict are written in the `review` block of the sidecar `.json`.

Decision based on `passed`/`score` of output :
- **`passed` true** (score ≥ threshold) → post.
- **`passed` false** after retries → GM decision : post as-is, or retry with higher `--max-attempts` / revised prompt. Never silently post image below threshold without noting it.

### Manual Re-review (occasional case)

To review an **already existing image** (without regenerating), use the `review_image.py` brick :

```bash
REVIEW=/opt/modules/gaming/mygamemaster-images/scripts/review_image.py
python3 "$REVIEW" \
  --image /path/campaign/images/portraits/oscar.png \
  --criteres "Portrait of Oscar (human, ranger), hood, bow on back, twilight atmosphere" \
  --json
```

It prints verdict + a parsable overall score (`OVERALL_SCORE: N/10`) and a line `CORRECTIONS:`. Evaluated criteria : **Style** (respect of visual style), **Description** (requested elements present), **Quality** (anatomy, artifacts, composition), **Parasite Text** (watermark/signature).

### Trap : payload sizes

Base64 images weigh 2-3 MB. Scripts `gen_image.py` / `review_image.py` handle this internally (request body posted via socket, never as argument). If you must exceptionally hand-craft a `curl`, **never** pass image as `-d` inline argument (`Argument list too long`) — use `-d @file`.

---

## Visual Consistency — Checklist & Traps

Before each generation :

- [ ] `description_complete` loaded from `world.json` (never generate without — it's the visual glue)
- [ ] Correct template loaded ; full prompt = `description_complete` + filled template (**never one without the other**, never improvise)
- [ ] Required OpenRouter parameters present : `modalities` + `image_config.aspect_ratio` (see « Required Parameters » table — their absence = #1 cause of « no image » ; Midjourney `--ar` flags don't work)
- [ ] Negatives integrated in prompt text (« Avoid: … ») ; `negative_prompt` field reserved for ComfyUI fallback
- [ ] `!portrait` : character sheet read (race, class, appearance)
- [ ] Base64 image never passed inline as shell argument (`-d @file` ; payload >2 MB)

After generation :

- [ ] **Systematic review** applied (done by `generate_reviewed.py` ; never post without review — regenerate if < threshold, default 8)
- [ ] **Exit code verified** before posting (see code table ; ≠ 0 → don't post, diagnose)
- [ ] Image posted to **path actually returned** (not hardcoded `{slug}.png`) + its sidecar `.json` (with review score)
- [ ] `/tmp` cleaned after move

---

## Error Handling

| Error | Diagnosis | Solution |
|--------|-----------|----------|
| **No image returned (text only response)** | Script prints `no image returned` ; `images` absent from response | **Check that `modalities: ["image", "text"]` is in payload** — #1 cause. Most frequent failure reason. |
| Model security refusal | Text response like « I can't generate… » | Rephrase prompt (remove explicit violence/sensitive content), or switch to ComfyUI |
| `OPENROUTER_API_KEY not set` | Script stops immediately | Load key in environment before call (`export OPENROUTER_API_KEY=…`) |
| Invalid ratio | API error on `aspect_ratio` | Use supported ratio : `1:1`, `3:4`, `4:3`, `16:9`, `9:16`… |
| ComfyUI not running | `curl http://127.0.0.1:8188/system_stats` fails | Run `comfy launch --background` |
| Model missing | `check_deps.py` reports missing checkpoint | `comfy model download --url ...` |
| Prompt too long | Tokenization error | Truncate `description_complete` to 300 tokens max, keep essentials |
| Character not found | No sheet with matching `meta.character_name` | List available characters |
| No active campaign | `world.json` not found | *« No active campaign. Run `!init` or `!campaign active <name>`. »* |
| Visual style missing | `world.json` without `meta.style_visuel` | *« ⚠️ Visual style not defined. Use `!style visual ...` to configure it. »* |

---

## Dependencies

| Dependency | Role |
|-----------|------|
| `mygamemaster` (parent skill) | Campaign context, GM persona |
| `mygamemaster-character` | Character sheet reading for `!portrait` |
| `scripts/` (OpenRouter) | Actual image generation (`generate_reviewed.py` & co.) |
| `comfyui` (creative skill, **archived**) | Historic fallback unavailable by default |
| `world.json` | Visual style + world data |
| `characters/*.json` | Character details for portraits |

---

## Integration with Parent Skill

This skill is a sub-skill of `mygamemaster`. It is loaded automatically when triggers `!image`, `!portrait`, `!carte`, `!illustration` are detected.

**Before each action :**
1. Load `mygamemaster` for persona and global conventions
2. Determine active campaign
3. Check `world.json > meta.style_visuel`
4. Generate via OpenRouter `scripts/` (see « Effective Generation »)

**Always respect parent skill principles :**
- Consistency — everything starts from defined visual style
- Systematic logging — each generated image is logged with metadata
- Appropriate channel — images are posted to campaign channel
- MJ Tonnerre format — status messages with emojis and narrative style

---

## Style Management Commands

### `!style visual` — Display Current Style

Displays the campaign's current `style_visuel` in readable form :

```
🎨 VISUAL STYLE — {campaign_name}
━━━━━━━━━━━━━━━━━━━━━━━━━━
🖌️ Technique : {technique}
🎨 Palette : {palette}
🌅 Atmosphere : {ambiance}
📝 Canonical prompt : {description_complete}
```

### `!style visual <attribute> <value>` — Modify Style

Allows evolving visual style during campaign :

- `!style visual technique "watercolor ink, soft gradients"`
- `!style visual palette "pastels, soft golds, twilight blues"`
- `!style visual ambiance "dreamlike, ethereal, melancholic yet serene"`

After modification, automatically rebuild `description_complete` by concatenating the three fields.

**Message :**
```
✅ Visual style updated.
   🖌️ {attribute} → "{new_value}"
   📝 New canonical prompt : {description_complete}
   ⚠️ Next images will use this new style.
```

> Anti-patterns (missing prefix, uniform ratio, `--ar` in prompt, post without review/exit code, inline base64…) are covered by **Checklist & Traps** and **Error Handling** above.
