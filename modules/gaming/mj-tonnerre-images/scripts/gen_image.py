#!/usr/bin/env python3
"""
gen_image.py — Image generation via OpenRouter for MJ Tonnerre.

Single, definitive script (stdlib only) that:
  1. builds the OpenRouter request with MANDATORY parameters
     (`modalities: ["image","text"]` + `image_config.aspect_ratio`);
  2. calls the API, with retries on transient errors (429 / 5xx / network);
  3. extracts the base64 image and writes it as PNG;
  4. writes (optional) the `.json` metadata file alongside the PNG.

The key is read from the environment (`OPENROUTER_API_KEY`) — NEVER as an argument,
NEVER from a .env file grepped by hand: in the Hermes container it is
already injected via EnvironmentFile (see ansible/roles/hermes_deploy/credentials.yml).

The prompt arrives via file (`--prompt-file`) or stdin (`--prompt-file -`), never
as an argument: it is large and contains the `description_complete`. The response
(base64 image, several MB) is read from the socket — never via jq/bash.

Usage:
  echo "<full prompt>" | python3 gen_image.py --out IMG.png --aspect 16:9
  python3 gen_image.py --prompt-file p.txt --out IMG.png --aspect 3:4 --crayon
  python3 gen_image.py --prompt-file - --out IMG.png --aspect 1:1 \
      --meta-json '{"type":"carte","campagne":"x"}' --json

Native Gemini ratios: 1:1 2:3 3:2 3:4 4:3 4:5 5:4 9:16 16:9 21:9
  scenes/session → 16:9 · portraits → 3:4 · maps → 1:1

Models:
  default         google/gemini-3.1-flash-image-preview
  --crayon        recraft/recraft-v4.1   (sketched explorer's notebook style)
  --model X       force a specific model

Exit codes:
  0  image generated (PNG written)
  1  generation failure (no image returned / safety refusal / HTTP / network)
  2  usage error (missing key, invalid arguments, empty prompt)
"""
import sys
import os
import json
import time
import base64
import argparse
import urllib.request
import urllib.error

API_URL = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_MODEL = "google/gemini-3.1-flash-image-preview"
CRAYON_MODEL = "recraft/recraft-v4.1"
VALID_RATIOS = {"1:1", "2:3", "3:2", "3:4", "4:3", "4:5", "5:4", "9:16", "16:9", "21:9"}
MIME_EXT = {"jpeg": "jpg", "jpg": "jpg", "png": "png", "webp": "webp"}

# Instruction automatically injected at the top of the prompt when reference portraits
# are provided. Guarantees visual consistency of the character without requiring a
# specific prompt from the GM.
_REF_INSTRUCTION_FR = (
    "RÉFÉRENCE VISUELLE CANONIQUE — à respecter absolument :\n"
    "{n_ref_label} {verb} l'apparence établie du ou des characters représentés dans cette scène.\n"
    "Tu DOIS conserver EXACTEMENT : visage, forme du visage, couleur et style des cheveux, "
    "teinte de peau, traits distinctifs (cicatrices, tatouages, couleur des yeux…). "
    "Seuls la pose, l'expression, l'éclairage et le cadrage peuvent changer.\n\n"
)

# For a map: the reference image is a composition LAYER, not a face.
# (Without this, the "portrait" instruction above pushes the model to interpret.)
_REF_INSTRUCTION_CALQUE = (
    "TECHNICAL REFERENCE — TREAT THE IMAGE BELOW AS A TRACING LAYER (calque), NOT a photo:\n"
    "It is a schematic map. You MUST keep EVERY element at its EXACT position, scale and "
    "road connection. Do NOT move, add, remove, merge, reflow or rearrange anything — the "
    "geometry is fixed. Redraw each marker, each coloured zone and each road line exactly "
    "where it sits in the reference. The numbered pins mark the locations described in the "
    "prompt; keep each number at its spot. Only the artistic rendering (textures, brushwork, "
    "palette, hand-drawn labels) may change — never the layout.\n\n"
)
_REF_INSTRUCTIONS = {"portrait": _REF_INSTRUCTION_FR, "calque": _REF_INSTRUCTION_CALQUE}


def die(msg, code):
    """Print an error to stderr and exit with the given code."""
    print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(code)


def _load_ref_image(path):
    """Load a reference image → (data_url str, mime str). Raises OSError if not found."""
    ext = os.path.splitext(path)[1].lower().lstrip(".") or "png"
    mime = "jpeg" if ext in ("jpg", "jpeg") else ext
    with open(path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode()
    return f"data:image/{mime};base64,{b64}", mime


def build_payload(prompt, model, aspect, ref_images=None, ref_mode="portrait",
                  temperature=None):
    """ref_images: list (possibly empty) of paths to reference images.
    When provided, the content becomes multimodal (text + images) and an instruction
    is injected at the top of the prompt according to `ref_mode`:
      * "portrait" — character appearance consistency (default);
      * "calque"   — the image is a schematic to RETRACE (fixed positions): map.
    temperature: if provided, curbs model creativity (low = more faithful to the layer)."""
    if ref_images:
        n = len(ref_images)
        label = "L'image ci-dessous montre" if n == 1 else f"Les {n} images ci-dessous montrent"
        instr = _REF_INSTRUCTIONS.get(ref_mode, _REF_INSTRUCTION_FR)
        ref_note = instr.format(n_ref_label=label, verb="") if ref_mode == "portrait" else instr
        content = [{"type": "text", "text": ref_note + prompt}]
        for ref_path in ref_images:
            try:
                data_url, _ = _load_ref_image(ref_path)
                content.append({"type": "image_url", "image_url": {"url": data_url}})
            except OSError as e:
                print(f"  (warning: reference portrait ignored ({ref_path}): {e})",
                      file=sys.stderr)
    else:
        content = prompt
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": content}],
        "modalities": ["image", "text"],          # ← MANDATORY: otherwise text-only response
        "image_config": {"aspect_ratio": aspect},
    }
    if temperature is not None:
        payload["temperature"] = temperature
    return payload


def call_api(payload, api_key, retries, timeout):
    """Call OpenRouter. Retries on 429/5xx/network errors. Returns the JSON dict or raises RuntimeError."""
    body = json.dumps(payload).encode()
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    last_err = None
    for attempt in range(1, retries + 2):  # 1 attempt + `retries` retries
        try:
            req = urllib.request.Request(API_URL, data=body, headers=headers)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            detail = e.read().decode(errors="replace")[:500]
            last_err = f"HTTP {e.code}: {detail}"
            transient = e.code == 429 or 500 <= e.code < 600
            if not transient:
                raise RuntimeError(last_err)
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            last_err = f"network: {e}"
        if attempt <= retries:
            backoff = 2 ** (attempt - 1)  # 1s, 2s, 4s…
            print(f"  (attempt {attempt} failed: {last_err} — retrying in {backoff}s)",
                  file=sys.stderr)
            time.sleep(backoff)
    raise RuntimeError(last_err or "unknown failure")


def extract_image(data):
    """Return PNG bytes, or raise RuntimeError with an actionable diagnostic."""
    if isinstance(data, dict) and "error" in data:  # application-level error in HTTP 200
        raise RuntimeError(f"API: {json.dumps(data['error'])[:500]}")
    msg = (data.get("choices") or [{}])[0].get("message", {}) or {}
    images = msg.get("images") or []
    if not images:
        # No image: safety refusal, or `modalities` forgotten on the request side.
        txt = (msg.get("content") or "").strip()
        raise RuntimeError(
            "no image returned by the model. "
            f"Text response: {txt[:400] or '(empty)'}")
    url = images[0]["image_url"]["url"]
    # data:image/<mime>;base64,<...>  — the model may return JPEG, PNG or WebP.
    mime = "png"
    if url.startswith("data:") and "," in url:
        header = url[5:url.index(",")]
        if "/" in header:
            mime = header.split("/", 1)[1].split(";", 1)[0].lower() or "png"
    b64 = url.split(",", 1)[1] if "," in url else url
    return base64.b64decode(b64), mime


def generate(prompt, aspect, model, api_key, retries=2, timeout=120, ref_images=None,
             ref_mode="portrait", temperature=None):
    """Generate an image. Returns (bytes, ext) — ext ∈ {png,jpg,webp}.
    Raises RuntimeError on failure (no image / refusal / HTTP / network).
    ref_images: optional list of paths to reference images.
    ref_mode: "portrait" (character consistency) or "calque" (retrace a map).
    temperature: low → more faithful (less creativity).
    Reusable by the generate_reviewed.py wrapper (no duplicated API call)."""
    data = call_api(build_payload(prompt, model, aspect, ref_images, ref_mode, temperature),
                    api_key, retries, timeout)
    img, mime = extract_image(data)
    return img, MIME_EXT.get(mime, mime)


def write_metadata(meta_path, base_meta_json, model, prompt, aspect, fmt, ref_images=None):
    meta = {}
    if base_meta_json:
        try:
            meta = json.loads(base_meta_json)
        except json.JSONDecodeError as e:
            die(f"--meta-json invalid: {e}", 2)
    # Fields added/overwritten by the generator (technical source of truth).
    meta.update({
        "model": model,
        "prompt": prompt,
        "aspect_ratio": aspect,
        "format": fmt,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "generator": "openrouter",
    })
    if ref_images:
        meta["ref_images"] = ref_images
    with open(meta_path, "w") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)
    return meta_path


def main():
    p = argparse.ArgumentParser(
        description="Generate an image via OpenRouter (modalities + aspect_ratio handled).",
        formatter_class=argparse.RawDescriptionHelpFormatter, epilog=__doc__)
    p.add_argument("--out", required=True, help="Output PNG path.")
    p.add_argument("--aspect", default="1:1",
                   help=f"Native ratio. Valid: {' '.join(sorted(VALID_RATIOS))} (default 1:1).")
    p.add_argument("--prompt-file", default="-",
                   help="Prompt file, or '-' for stdin (default: stdin).")
    p.add_argument("--model", default=None, help="Force a specific OpenRouter model.")
    p.add_argument("--crayon", action="store_true",
                   help=f"Sketched style: uses {CRAYON_MODEL}.")
    p.add_argument("--ref-image", action="append", dest="ref_images", metavar="PORTRAIT",
                   help="Reference portrait for visual consistency (repeatable, max 3).")
    p.add_argument("--meta-json", default=None,
                   help="Base metadata JSON (merged into <out>.json).")
    p.add_argument("--no-meta", action="store_true",
                   help="Do not write the <out>.json sidecar.")
    p.add_argument("--retries", type=int, default=2,
                   help="Retries on transient 429/5xx/network error (default 2).")
    p.add_argument("--timeout", type=int, default=120, help="HTTP timeout in s (default 120).")
    p.add_argument("--ref-mode", choices=["portrait", "calque"], default="portrait",
                   help="portrait=character consistency (default) · calque=retrace a map (fixed positions).")
    p.add_argument("--temperature", type=float, default=None,
                   help="Model temperature (low → more faithful to the layer, less creative).")
    p.add_argument("--json", action="store_true", dest="as_json",
                   help="Machine output on stdout (paths + status).")
    args = p.parse_args()

    # 1. Key (environment only)
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        die("OPENROUTER_API_KEY not set in the environment.", 2)

    # 2. Ratio
    if args.aspect not in VALID_RATIOS:
        die(f"ratio '{args.aspect}' not supported. Valid: {' '.join(sorted(VALID_RATIOS))}", 2)

    # 3. Prompt
    if args.prompt_file == "-":
        prompt = sys.stdin.read().strip()
    else:
        try:
            with open(args.prompt_file) as f:
                prompt = f.read().strip()
        except OSError as e:
            die(f"reading prompt: {e}", 2)
    if not prompt:
        die("empty prompt.", 2)

    # 4. Model
    model = args.model or (CRAYON_MODEL if args.crayon else DEFAULT_MODEL)

    # 5. Call + extraction (generation failure = exit 1)
    ref_images = (args.ref_images or [])[:3]  # cap at 3 to avoid blowing up the payload
    # Recraft does not support multimodal input — silently ignore references.
    if ref_images and model == CRAYON_MODEL:
        print("  (warning: --ref-image ignored with the Recraft model — no multimodal support)",
              file=sys.stderr)
        ref_images = []
    try:
        img, ext = generate(prompt, args.aspect, model, api_key, args.retries, args.timeout,
                            ref_images=ref_images or None, ref_mode=args.ref_mode,
                            temperature=args.temperature)
    except RuntimeError as e:
        die(str(e), 1)

    # 6. Honor the actually returned format (the model may return JPEG/WebP):
    #    adjust the extension so the file does not lie about its contents.
    base, req_ext = os.path.splitext(args.out)
    if req_ext.lstrip(".").lower() != ext:
        out_path = f"{base}.{ext}"
        print(f"  (note: model returned {ext.upper()}; writing as .{ext} "
              f"instead of '{req_ext or '(none)'}')", file=sys.stderr)
    else:
        out_path = args.out

    # 7. Write image (+ metadata, sidecar .json alongside)
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    with open(out_path, "wb") as f:
        f.write(img)

    meta_path = None
    if not args.no_meta:
        meta_path = write_metadata(base + ".json",
                                   args.meta_json, model, prompt, args.aspect, ext,
                                   ref_images=ref_images or None)

    # 8. Report — use the ACTUAL path (out_path) downstream, not args.out
    if args.as_json:
        print(json.dumps({"ok": True, "image": out_path, "meta": meta_path,
                          "model": model, "aspect_ratio": args.aspect,
                          "format": ext, "bytes": len(img)}))
    else:
        print(f"OK: {out_path} ({len(img)} bytes, {ext.upper()}, {model}, {args.aspect})")
        if meta_path:
            print(f"    metadata: {meta_path}")
    sys.exit(0)


if __name__ == "__main__":
    main()
