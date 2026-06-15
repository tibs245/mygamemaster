#!/usr/bin/env python3
"""
generate_reviewed.py — Image generation WITH systematic review (and retry at threshold).

Deterministic pipeline, without a steering LLM: it makes the review **inviolable** (done at
every generation, independently of the model's discipline) — as the SKILL requires
("never post an image without a review"), without depending on Hermes hooks (which
cannot regenerate an image).

Loop:
  1. generates an image  (gen_image.generate — Nano Banana 2 by default)
  2. reviews it          (review_image.review — Gemma 4 vision)
  3. if score < threshold and attempts remain: appends the reviewer's CORRECTIONS to
     the prompt and regenerates
  4. keeps the **best** image (highest score), writes the image + the sidecar `.json`
     (with the `review` block: score, threshold, attempts, verdict)

Reuses gen_image.py and review_image.py (zero API-call duplication).
Key via environment (`OPENROUTER_API_KEY`). Prompt via stdin or `--prompt-file`.

Fail-open: if the review breaks (network/HTTP), we keep the generated image (unknown score),
we do not fail — a broken reviewer must not block a session.

Usage:
  echo "<prompt>" | python3 generate_reviewed.py --out IMG.png --aspect 16:9
  python3 generate_reviewed.py --prompt-file p.txt --out P.png --aspect 3:4 \
      --criteres "Portrait d'Oscar, rôdeur, capuche" --threshold 8 --max-attempts 3 --json

Feature flag guard "images": before any network call, we read
`meta.features.images` from the `world.json` of the current campaign (resolved by walking
up from `--out`). If the flag is explicitly `false` (or env `MGM_FEATURE_IMAGES` set to
0/false), we do NOT generate and exit with code 3. FAIL-OPEN: campaign / world.json
not found or unreadable → images considered ON (we never block on an error).

Exit codes:
  0  an image was produced (see `passed` in the --json output: threshold reached or not)
  1  total generation failure (no image, even on the 1st attempt)
  2  usage (missing key, invalid ratio, empty prompt)
  3  illustrations disabled for this world (meta.features.images=false) — nothing generated
"""
import sys
import os
import json
import time
import argparse

import gen_image
import review_image

# Exit code distinct from the "images disabled" guard (0=ok, 1=gen failure,
# 2=usage; 3 = world has cut illustrations — nothing generated, this is not an error).
IMAGES_OFF_EXIT = 3
_FALSE_ENV = ("0", "false", "no", "off", "non")  # same forms as worldlib.as_bool/feature_toggle


def die(msg, code):
    print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(code)


def _trouver_monde(out_path):
    """Walks up from `--out` (…/<campaign>/images/<type>/<file>) to find the
    world.json of the current campaign. Returns the Path to world.json or None.

    Same implicit resolution as the rest of the module: a campaign's directory tree
    places `world.json` at the root of the folder containing `images/`. We walk
    upward until we find a `world.json` (bound: filesystem root)."""
    d = os.path.dirname(os.path.abspath(out_path))
    prev = None
    while d and d != prev:
        cand = os.path.join(d, "world.json")
        if os.path.isfile(cand):
            return cand
        prev, d = d, os.path.dirname(d)
    return None


def _images_actives(out_path):
    """Deterministic guard, FAIL-OPEN, no external dependencies (stdlib only).

    Cascade aligned with the project resolver: meta.features.images > env
    MGM_FEATURE_IMAGES > True. Returns False only if the flag is EXPLICITLY
    disabled (readable world.json with images=false, or env set to 0/false). Any doubt
    (world not found / unreadable / key absent) → True (we generate). We NEVER block
    a session on a read error."""
    monde_path = _trouver_monde(out_path)
    val = None  # None = not specified in the world → we will check the env
    if monde_path:
        try:
            with open(monde_path, encoding="utf-8") as fh:
                monde = json.load(fh)
            feats = ((monde or {}).get("meta") or {}).get("features") or {}
            if isinstance(feats, dict) and isinstance(feats.get("images"), bool):
                val = feats["images"]
        except (OSError, ValueError):
            return True  # unreadable/corrupted → fail-open (images ON)
    if val is None:  # nothing in the world → instance default (env), then True
        env = os.environ.get("MGM_FEATURE_IMAGES")
        if env is not None and str(env).strip().lower() in _FALSE_ENV:
            return False
        return True
    return bool(val)


def main():
    p = argparse.ArgumentParser(
        description="Generates an image with systematic review and retry at threshold.",
        formatter_class=argparse.RawDescriptionHelpFormatter, epilog=__doc__)
    p.add_argument("--out", required=True, help="Output image path (extension adjusted to actual format).")
    p.add_argument("--aspect", default="1:1", help="Ratio (16:9 scenes · 3:4 portraits · 1:1 maps).")
    p.add_argument("--prompt-file", default="-", help="Prompt file, or '-' for stdin.")
    p.add_argument("--criteres", default=None, help="Review criteria (default: the prompt itself).")
    p.add_argument("--criteres-file", default=None, help="Review criteria file.")
    p.add_argument("--ref-image", action="append", dest="ref_images", metavar="REF",
                   help="Reference image (portrait OR map layer). Repeatable, max 3.")
    p.add_argument("--ref-mode", choices=["portrait", "calque"], default="portrait",
                   help="portrait=character consistency (default) · calque=retrace a map (fixed positions).")
    p.add_argument("--temperature", type=float, default=None,
                   help="Temperature (low → more faithful to the layer; ignore for OpenAI models).")
    p.add_argument("--model", default=None, help="Generation model (default Nano Banana 2).")
    p.add_argument("--crayon", action="store_true", help="Sketch style (Recraft).")
    p.add_argument("--review-model", default=review_image.DEFAULT_VISION_MODEL,
                   help=f"Vision model for review (default {review_image.DEFAULT_VISION_MODEL}).")
    p.add_argument("--threshold", type=float, default=8.0, help="Minimum score /10 accepted (default 8).")
    p.add_argument("--max-attempts", type=int, default=2, help="Max number of generations (default 2).")
    p.add_argument("--meta-json", default=None, help="Base metadata merged into <out>.json.")
    p.add_argument("--no-meta", action="store_true", help="Do not write the <out>.json sidecar.")
    p.add_argument("--retries", type=int, default=2, help="Transient retries per call (default 2).")
    p.add_argument("--timeout", type=int, default=120, help="Generation timeout (default 120 s).")
    p.add_argument("--review-timeout", type=int, default=90, help="Review timeout (default 90 s).")
    p.add_argument("--json", action="store_true", dest="as_json", help="Machine output.")
    args = p.parse_args()

    # 🚦 Feature flag guard "images" — BEFORE any network call (and even before the
    # key check): if the world has explicitly disabled illustrations, we generate
    # nothing and exit cleanly with code 3. FAIL-OPEN (see _images_actives).
    if not _images_actives(args.out):
        msg = "illustrations disabled for this world (meta.features.images=false)"
        if args.as_json:
            print(json.dumps({"ok": False, "images_disabled": True, "image": None,
                              "reason": msg}, ensure_ascii=False))
        else:
            print(f"⚪ {msg} — no image generated.")
        sys.exit(IMAGES_OFF_EXIT)

    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        die("OPENROUTER_API_KEY not set in the environment.", 2)
    if args.aspect not in gen_image.VALID_RATIOS:
        die(f"ratio '{args.aspect}' not supported. Valid: {' '.join(sorted(gen_image.VALID_RATIOS))}", 2)
    if args.max_attempts < 1:
        die("--max-attempts must be ≥ 1.", 2)

    # Prompt
    if args.prompt_file == "-":
        base_prompt = sys.stdin.read().strip()
    else:
        try:
            with open(args.prompt_file) as f:
                base_prompt = f.read().strip()
        except OSError as e:
            die(f"reading prompt: {e}", 2)
    if not base_prompt:
        die("empty prompt.", 2)

    # Review criteria
    if args.criteres_file:
        try:
            with open(args.criteres_file) as f:
                criteres = f.read().strip()
        except OSError as e:
            die(f"reading criteria: {e}", 2)
    else:
        criteres = (args.criteres or base_prompt).strip()

    model = args.model or (gen_image.CRAYON_MODEL if args.crayon else gen_image.DEFAULT_MODEL)
    ref_images = (args.ref_images or [])[:3]  # cap at 3 to avoid exploding the payload
    # Recraft does not support multimodal input — ignore references.
    if ref_images and model == gen_image.CRAYON_MODEL:
        print("  (warning: --ref-image ignored with Recraft model — no multimodal support)",
              file=sys.stderr)
        ref_images = []

    best = None  # dict: img, ext, score, verdict, corrections, prompt, attempt
    prompt = base_prompt
    attempts = 0

    for attempt in range(1, args.max_attempts + 1):
        attempts = attempt
        # 1. Generation (failure on 1st attempt = fatal; otherwise we keep the best already obtained)
        try:
            img, ext = gen_image.generate(prompt, args.aspect, model, api_key,
                                          args.retries, args.timeout,
                                          ref_images=ref_images or None,
                                          ref_mode=args.ref_mode,
                                          temperature=args.temperature)
        except RuntimeError as e:
            if best is None:
                die(f"generation (attempt {attempt}): {e}", 1)
            print(f"  (attempt {attempt}: generation failed: {e} — keeping previous best)",
                  file=sys.stderr)
            break

        # 2. Review (fail-open: if it breaks, we keep the image without a score)
        score, verdict, corrections = None, "", ""
        tmp = f"{os.path.splitext(args.out)[0]}.__review_tmp__.{ext}"
        try:
            os.makedirs(os.path.dirname(os.path.abspath(tmp)), exist_ok=True)
            with open(tmp, "wb") as f:
                f.write(img)
            verdict = review_image.review(tmp, criteres, api_key,
                                          args.review_model, args.retries, args.review_timeout)
            score = review_image.parse_score(verdict)
            corrections = review_image.parse_corrections(verdict)
        except (RuntimeError, OSError) as e:
            print(f"  (attempt {attempt}: review unavailable: {e} — image kept without score)",
                  file=sys.stderr)
        finally:
            if os.path.exists(tmp):
                os.remove(tmp)

        cand = {"img": img, "ext": ext, "score": score, "verdict": verdict,
                "corrections": corrections, "prompt": prompt, "attempt": attempt}
        sc = score if score is not None else -1.0
        best_sc = best["score"] if (best and best["score"] is not None) else -1.0
        if best is None or sc > best_sc:
            best = cand

        note = f"{score}/10" if score is not None else "unknown score"
        print(f"  attempt {attempt}/{args.max_attempts}: {note}", file=sys.stderr)

        if score is not None and score >= args.threshold:
            break
        # Prepare regeneration with the reviewer's corrections
        if attempt < args.max_attempts:
            corr = corrections or "améliore qualité, anatomie et fidélité au brief"
            prompt = f"{base_prompt}\nCorrections impératives par rapport à la version précédente : {corr}"

    passed = best["score"] is not None and best["score"] >= args.threshold

    # 3. Write the best image (extension = actual format)
    base = os.path.splitext(args.out)[0]
    out_path = f"{base}.{best['ext']}"
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    with open(out_path, "wb") as f:
        f.write(best["img"])

    # 4. Metadata sidecar (with review block)
    meta_path = None
    if not args.no_meta:
        meta = {}
        if args.meta_json:
            try:
                meta = json.loads(args.meta_json)
            except json.JSONDecodeError as e:
                die(f"--meta-json invalid: {e}", 2)
        meta.update({
            "model": model,
            "prompt": best["prompt"],
            "aspect_ratio": args.aspect,
            "format": best["ext"],
            "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "generator": "openrouter",
            "review": {
                "model": args.review_model,
                "score": best["score"],
                "threshold": args.threshold,
                "passed": passed,
                "attempts": attempts,
                "corrections": best["corrections"],
                "verdict": best["verdict"],
            },
        })
        if ref_images:
            meta["ref_images"] = ref_images
        meta_path = base + ".json"
        with open(meta_path, "w") as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)

    # 5. Report
    if not passed:
        print(f"  ⚠️ threshold {args.threshold}/10 not reached after {attempts} attempt(s) "
              f"(best score: {best['score']}). Image kept — decision left to MJ Tonnerre.",
              file=sys.stderr)
    if args.as_json:
        print(json.dumps({"ok": True, "image": out_path, "meta": meta_path,
                          "model": model, "aspect_ratio": args.aspect, "format": best["ext"],
                          "score": best["score"], "threshold": args.threshold,
                          "passed": passed, "attempts": attempts, "bytes": len(best["img"])},
                         ensure_ascii=False))
    else:
        flag = "✅" if passed else "⚠️ below threshold"
        print(f"OK: {out_path} — score {best['score']}/10 {flag} ({attempts} attempt(s), {model})")
        if meta_path:
            print(f"    metadata: {meta_path}")
    sys.exit(0)


if __name__ == "__main__":
    main()
