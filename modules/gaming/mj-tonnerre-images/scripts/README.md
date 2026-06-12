# Image tooling — MJ Tonnerre

Self-contained scripts (Python 3, **stdlib only**, zero pip dependencies) for
generating and reviewing illustrations. Designed to run in the Hermes Podman container,
where they are baked into `/opt/modules/gaming/mj-tonnerre-images/scripts/`.

> Difference from `mj-tonnerre/scripts/` tooling (dice, validation): these two
> scripts **make network calls** (OpenRouter API). This is the only exception to the
> "zero network" principle — image generation requires it by nature.

All scripts:
- have a `--help` option;
- read the `OPENROUTER_API_KEY` key **from the environment** (never as an argument,
  never from a grepped `.env`) — it is injected via `EnvironmentFile` in the
  container (see `ansible/roles/hermes_deploy/tasks/credentials.yml`);
- **never** pass base64 images as shell arguments (body posted via socket);
- retry on transient errors (429 / 5xx / network);
- return **clean exit codes** and accept `--json`.

Path convention in examples:
```
SCRIPTS=/opt/modules/gaming/mj-tonnerre-images/scripts
CAMP=/path/campaigns/<campaign>
```

---

## 0. `generate_reviewed.py` — generation WITH systematic review (standard path) ⭐

This is the **default skill command**. Deterministic pipeline, no steering LLM:
generates (`gen_image`) → reviews (`review_image`, Gemma 4 vision) → if score < threshold, reinjects
reviewer corrections into the prompt and **regenerates** (up to `--max-attempts`) → keeps
the **best** image. Makes review "MANDATORY" by the SKILL **inviolable by construction**,
independent of Hermes hooks (which cannot regenerate an image). Reuses the two
building blocks below (zero duplication).

**Signature**
```
python3 generate_reviewed.py --out IMG.png [--aspect 16:9] [--prompt-file -|FILE]
        [--criteria "..." | --criteria-file F] [--threshold 8] [--max-attempts 2]
        [--sketch | --model X] [--review-model google/gemma-4-31b-it]
        [--meta-json '{...}'] [--no-meta] [--retries N] [--timeout S] [--review-timeout S] [--json]
```
- `--criteria` : what the reviewer should check. **Default = the prompt** itself.
- `--threshold` : minimum score /10 accepted (default 8). `--max-attempts` : max number of generations (default 2).
- Fail-open: if review fails (network/HTTP), the generated image is kept (score unknown),
  no failure — a broken reviewer does not block a session.

**Sidecar `.json`** : fields from `gen_image` + `review` block (`model`, `score`, `threshold`,
`passed`, `attempts`, `corrections`, `verdict`).

**Exit codes** : `0` image produced (read `passed` : threshold met or not) ·
`1` total generation failure (no image) · `2` usage.

**Typical call**
```sh
echo "{full_description} {filled template} Avoid: text, watermark, signature." \
  | python3 $SCRIPTS/generate_reviewed.py \
      --out $CAMP/images/portraits/oscar.png --aspect 3:4 \
      --threshold 8 --max-attempts 2 \
      --meta-json '{"type":"portrait","campaign":"<name>"}' --json
```

---

## 1. `gen_image.py` — image generation (low-level building block)

Builds the OpenRouter request with **mandatory** parameters
(`modalities: ["image","text"]` + `image_config.aspect_ratio` — without them, the model
responds in text and **no image** is produced), calls the API, extracts the PNG,
and writes the metadata `.json` sidecar.

**Signature**
```
python3 gen_image.py --out IMG.png [--aspect 16:9] [--prompt-file -|FILE]
                     [--sketch | --model X] [--meta-json '{...}'] [--no-meta]
                     [--retries N] [--timeout S] [--json]
```
- Prompt: via **stdin** (default) or `--prompt-file FILE` — never as argument (too large).
- `--aspect` : native Gemini ratios `1:1 2:3 3:2 3:4 4:3 4:5 5:4 9:16 16:9 21:9`.
  Mapping: scenes/session → `16:9` · portraits → `3:4` · maps → `1:1`.
- `--sketch` : explorer's notebook style → `recraft/recraft-v4.1`.
- `--meta-json` : base metadata (type, campaign, style_snapshot…) merged
  into `<out>.json`; the script adds `model`, `prompt`, `aspect_ratio`, `format`, `generated_at`.

> **Variable format** : Nano Banana 2 returns PNG or JPEG (sometimes WebP).
> The script **honors the actual format** and adjusts the extension (`scene.png` → `scene.jpg`
> if needed). Always consume the returned path (field `image` in `--json`), never
> assume `.png`. The actual format is in the sidecar (`"format"`).

**Exit codes** : `0` image written · `1` generation failure (no image / security refusal
/ HTTP / network) · `2` usage (missing key, invalid ratio, empty prompt).

**Typical call**
```sh
echo "{full_description} {filled template} Avoid: text, watermark, signature." \
  | python3 $SCRIPTS/gen_image.py \
      --out $CAMP/images/scenes/the-bridge-on-fire.png \
      --aspect 16:9 \
      --meta-json '{"type":"scene","campaign":"<name>"}'
```

> **Negatives with Gemini** : no `negative_prompt` field in OpenRouter — integrates
> exclusions into the prompt text (« Avoid: … »). The `negative_prompt` from
> templates is only used for the ComfyUI fallback.

---

## 2. `review_image.py` — review by vision model (low-level building block)

Sends the image to a **vision** model (`google/gemma-4-31b-it` by default — avoid
Gemini for text/vision tasks, Gemma performs equally well at lower cost) with
a critique instruction (Style / Description / Quality / text artifacts + score /10),
and prints the verdict. Supports the "never post without review" workflow from
`SKILL.md` (≥ threshold → keep ; < threshold, default 8 → regenerate).

**Signature**
```
python3 review_image.py --image IMG.png (--criteria "..." | --criteria-file -|FILE)
                        [--model google/gemma-4-31b-it] [--retries N] [--timeout S] [--json]
```
**Exit codes** : `0` verdict obtained · `1` failure (HTTP / network / empty) · `2` usage.

**Typical call**
```sh
python3 $SCRIPTS/review_image.py \
  --image $CAMP/images/portraits/oscar.png \
  --criteria "Sketched portrait of Oscar (scout), hood, bow, twilight atmosphere" \
  --json
```

---

## Summary

| Script | Role | Network | Exit 0 | Exit 1 | Exit 2 |
|--------|------|--------|--------|--------|--------|
| `generate_reviewed.py` ⭐ | Generates **+ review + retry at threshold** (standard path) | OpenRouter | image produced (see `passed`) | total generation failure | usage |
| `gen_image.py` | Generates an image (+ metadata), no review | OpenRouter | image written | generation failure | usage |
| `review_image.py` | Vision review of an existing image | OpenRouter | verdict obtained | HTTP/network failure | usage |

**Execution constraints** : Python 3, stdlib only (`urllib`, `base64`, `argparse`…),
no pip dependencies (nothing to add to the image's `requirements.txt`). The API key
must be present in the environment.

**Quick test (no network)** — verifies compilation + guards:
```sh
python3 -m py_compile $SCRIPTS/gen_image.py $SCRIPTS/review_image.py
env -u OPENROUTER_API_KEY python3 $SCRIPTS/gen_image.py --out /tmp/x.png <<<"t"   # → exit 2
```
