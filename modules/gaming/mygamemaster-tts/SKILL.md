---
name: mygamemaster-tts
description: Qualitative narrative voice for MJ Tonnerre — speech synthesis of ONLY the narration (no mechanics) via Minimax T2A v2 (speech-2.8-turbo, French_Female_Speech_New voice). Two modes: manual (!raconte, default) and auto (tts axis, in the transform_llm_output hook, OPT-IN). Two-stage pipeline that offloads from the GM model: a small model reformats the narration into a voice script (pauses, emotion, tics preserved, ambient), Minimax generates the audio, posted as MEDIA: in Discord.
category: gaming
triggers:
  - "!raconte"
  - "!audio"
  - "!voix"
  - "raconte la narration"
  - "voix off"
---

# 🔊 MJ Tonnerre — Narrative Voice (TTS)

## Objective

Give **qualitative voice** to the GM's **narration** — and **only the narration**.
Not a rushed TTS of all outputs: neither Steward blocks, nor mechanics, nor commands.
The voice focuses on **immersive storytelling** (French female voice, narrator).

**Two non-negotiable principles:**
1. **No load on the GM model.** The GM writes their narration **as usual**. All the voice work
   (reformatting + synthesis + ambient) is **offloaded** to a small dedicated model and the Minimax API.
   The **written message** delivered to the player is **never polluted** by TTS markup — it lives only
   in an **ephemeral** voice script.
2. **Fail-open everywhere.** No key, small model down, ffmpeg absent → the game continues, the text
   goes out normally, no error. Voice is a **bonus**, never a point of failure.

---

## Two trigger modes

### A. MANUAL — `!raconte` command (**the default path**)

Voices the **last narration** on demand (zero latency on normal turns), or a **provided passage**:
`!raconte <free text>`. Available as soon as the `tts` axis is ON (default) and
`MINIMAX_API_KEY` is set.

### B. AUTO — `meta.hooks.tts_auto` (in the `transform_llm_output` hook) — **OPT-IN**

**Off by default.** Enable it with **one** of:

```bash
MGM_TTS_AUTO=1                      # instance / deployment default
# ansible deployment: set `mgm_tts_auto: true` in group_vars — the playbook
# injects the variable into the container unit; exporting it in your own shell
# does NOT reach the hook subprocess inside the container.
```
```json
"meta": { "hooks": { "tts_auto": true } }   // world.json — campaign, wins over env
```

Once enabled, the hook voices **narrations** longer than `MGM_TTS_MIN_CHARS`
(default 280) and attaches the audio via `MEDIA:`. Latency: ~3-8 s on a long
narrative turn, inside a hook the runtime kills at 45 s.

**Why opt-in.** In 34 sessions of real play the automatic path produced **0 audio
file** while `!raconte` produced ~40, and it failed **without saying so** — three
sessions were burned before the player switched voice off for good
(`docs/10-field-report.md`). The path is repaired and, above all, now **audible when
it fails**; it ships disabled until a deployment has actually seen it work.
Nothing about `!raconte` depends on this toggle.

Every auto-voice decision — attached, skipped, or **failed** — is written to
`.banquier/tts-status.json` in the campaign, and echoed on stderr as `[mj-tts] …`.
Read it with the doctor (below), never by guessing.

---

## "Why is there no voice?" — one command

```bash
python3 /opt/modules/gaming/mygamemaster-tts/scripts/tts_doctor.py .          # in the campaign dir
python3 …/tts_doctor.py . --mock          # no key, no cost, no network
python3 …/tts_doctor.py . --json          # machine output
```

One run reports: the `tts` axis and the `tts_auto` opt-in **as the hook resolves
them**; `MINIMAX_API_KEY` in your shell **and** in the hook's own environment as the
hook last observed it (they differ — a hook does not inherit your interactive shell,
which is the most likely reason a voice that "works when I test it" never works in
play); the thresholds in effect; every outcome the hook recorded, failures kept apart
from configured silence; who produced the mp3 files sitting in `.banquier/tts/`; and a
real end-to-end render. Exit `0` = nothing would silence the game, `1` = it names the
defect.

---

## `!raconte` command flow

> The skill loads automatically on triggers (`!raconte`, `!audio`, `!voix`).
> It runs from the **cwd = campaign folder** (`/opt/data/mygamemaster/campaigns/<slug>`).

0. **🚦 Guard feature flag — tts.** If `world.json > meta.features.tts == false` (or
   `MGM_FEATURE_TTS=0`) → reply briefly *« 🔇 Narrative voice is disabled for this world
   (`!feature tts on` to reactivate). »* and **stop**. *Reminder: everything is ON by default —
   only act if the axis is explicitly `false`; unreadable info → assume ON (fail-open).*
1. **Retrieve text to voice:**
   - If the command has an **argument** (`!raconte <text>`) → use that text.
   - Otherwise → the **last narration** recorded by the hook:
     ```bash
     TXT=$(python3 /opt/modules/gaming/mygamemaster-tts/scripts/last_narration.py .)
     ```
     Exit code 1 (no narration found) → *« No recent narration to tell. Play a turn, then run
     `!raconte` again. »*
2. **Check `MINIMAX_API_KEY`** (present in env). Absent → *« 🔇 Voice unavailable:
   `MINIMAX_API_KEY` is not configured for this instance. »* (do not generate).
3. **Generate** via normal path (`tts_render.py`), text via **stdin**:
   ```bash
   SCRIPT=/opt/modules/gaming/mygamemaster-tts/scripts/tts_render.py
   OUT=.banquier/tts/raconte_$(date +%s).mp3
   printf '%s' "$TXT" | python3 "$SCRIPT" --out "$OUT" --json
   ```
   ⚠️ **Run this script. Never the runtime's built-in `tts_tool`.** It writes into the
   same directory under the same `raconte_*.mp3` name but synthesises with a different
   engine (Edge TTS): that substitution went unnoticed for a whole campaign and was
   reported by the player as "MiniMax sounds degraded, strange diction". Audio produced
   here always carries a `.json` sidecar with `generator` and `producer`; audio without
   a sidecar did **not** come from this module (`tts_doctor.py` counts them).
4. **Check exit code** (see table) before posting.
5. **Post to Discord**: `MEDIA:<real .mp3 path>` + a short message (*« 🔊 Narration. »*).
   Never hard-code the name: use the `audio` field from `--json` output (or the `OK:` line).

> `!raconte` is the canonical name; `!audio` / `!voix` are aliases.

---

## Quality pipeline (what `tts_render.py` does)

```
written narration ─► tts_format.py ─────────► tts_generate.py ──────► (ffmpeg) ─► voice.mp3
   (the GM)          small model              Minimax T2A v2          ambient
                     minimax/minimax-m3       speech-2.8-turbo        (key moments
                     weak reasoning           French_Female_Speech_New /long narrations)
```

1. **`tts_format.py`** transforms the narration into a **voice script**:
   - a **segment array** `[{text, emotion}, …]` (structured JSON output) — emotion can switch
     from segment to segment; each segment = one dedicated Minimax call (see segmentation);
   - **pauses** `<#x.x#>` and **interjection tags** live in the segment's `text` (true Minimax markup,
     sent to the API — unlike emotion, which is a call parameter);
   - valid **interjection tags** list (2.8 only): `(sighs)`, `(gasps)`, `(laughs)`…;
   - **dominant emotion** (`calm`="Neutral", `fearful`, `sad`, `surprised`, `fluent`… — **not**
     `whisper`: reserved for 2.6 models, rejected by `speech-2.8-turbo`): fallback if segmentation OFF;
   - **language tics and format PRESERVED** (explicit instruction: no paraphrasing);
   - **mechanics removed** (dice `1d20`, `[stats]`, `!commands`, technical labels);
   - an **ambient tag** (`forest`, `tavern`, `combat`, `dungeon`…) + a `key_moment` flag.

   Model: **`minimax/minimax-m3`** (same publisher as TTS → knows its own markup),
   **weak reasoning** (reformatting, not reasoning). Override: `MGM_TTS_FORMAT_MODEL`.
   **Fail-open**: call fails → cleaned narration + `emotion=calm`, `ambiance=none`.

2. **`tts_generate.py`** synthesizes voice (Minimax T2A v2, hex → MP3), one emotion per call.

3. **MULTI-EMOTION voice (segmentation)**: the API applies **only one emotion per generation**
   (also Minimax's official recommendation: split then reassemble). `tts_render` takes the
   **segment array**, **synthesizes one clip per segment** (own emotion) and **concatenates them
   with ffmpeg**. Safeguards: merge adjacent segments of same emotion, ceiling (`max_segments`,
   fallback to mono if exceeded). **Fail-open**: `MGM_TTS_SEGMENT=0`, ffmpeg absent, or segment
   fails → fallback to **mono-call** on dominant emotion (text cleaned of tags). Cost: **N API calls**
   per segmented narration (latency + price ∝ number of segments).

4. **Ambient (ffmpeg, optional)**: if **key-moment** or **long narration**, and a soundbed matches
   the tag, it is **layered under the voice** (low volume). Otherwise: voice alone.
   Bank: `modules/gaming/mygamemaster-tts/ambiances/` (see its README). ffmpeg absent → voice alone
   (fail-open).

---

## Exit codes (`tts_render.py` / `tts_generate.py`)

| Code | Meaning | Action |
|------|---------|--------|
| `0` | audio produced (voice alone or voice+ambient) | post `MEDIA:` + message |
| `1` | synthesis failure (no audio: HTTP/network/empty response) | do not post; *« ⚠️ Voice failed. »* + relay stderr diagnostic |
| `2` | usage (missing key, empty text) | fix (key / text) |

Never post `MEDIA:` if code ≠ 0.

---

## Voice selection — per-language defaults

MiniMax voice and `language_boost` are selected automatically based on the campaign
language. The lookup table lives in `scripts/tts_generate.py` (`LANGUAGE_DEFAULTS`).

### Default table

| Language | voice_id | language_boost |
|---|---|---|
| `fr` (French) | `French_Female_Speech_New` | `French` |
| `en` (English) | `Serene_Female` | `English` |
| _(unknown / fallback)_ | `French_Female_Speech_New` | `French` |

Adding a new language is one line in `LANGUAGE_DEFAULTS` — no other code changes needed.

### Resolution order (highest wins)

1. **Explicit CLI flags** `--voice` / `--language-boost` (direct `tts_generate.py` / `tts_render.py` calls).
2. **Campaign override** in `world.json > meta.audio` — fields `voice` and `language_boost`.
3. **Language auto-select** via `world.json > meta.langue` (or env `MGM_LANGUAGE` / `MGM_LANGUE`).
4. **Built-in fallback** — `French_Female_Speech_New` / `French` (existing default, unchanged).

**Fail-open**: an unknown language code, a missing `world.json`, or any read error falls
through to the built-in default — nothing breaks.

### Guided setup flow (for GM / admin at campaign creation)

1. **Check available voices** (no key required):
   ```bash
   python3 /opt/modules/gaming/mygamemaster-tts/scripts/tts_generate.py --list-voices
   ```
2. **Set the campaign language** in `world.json > meta.langue` (e.g. `"en"` or `"fr"`).
   The matching voice is then selected automatically.
3. **Optionally override** for this campaign (e.g. to use a different English voice):
   ```json
   "meta": {
     "langue": "en",
     "audio": {
       "voice": "Serene_Female",
       "language_boost": "English"
     }
   }
   ```
4. **Test the voice** in mock mode (no key, no cost):
   ```bash
   MGM_TTS_MOCK=1 printf 'The mist thickens.' | \
     python3 /opt/modules/gaming/mygamemaster-tts/scripts/tts_render.py \
     --out /tmp/test.mp3 --json --campaign-dir .
   # Check "voice" and "language_boost" in the JSON output.
   ```
5. **Live test** (key required): same command without `MGM_TTS_MOCK=1`.

To add a new language, open `scripts/tts_generate.py` and add one entry to
`LANGUAGE_DEFAULTS` following the existing `fr`/`en` pattern.

---

## Configuration

| Lever | Where | Effect |
|---|---|---|
| `tts` axis | `world.json > meta.features.tts` / `MGM_FEATURE_TTS` / `!feature tts on\|off` | activate/cut **all** voice (auto **and** `!raconte`) — live |
| `meta.hooks.tts_auto` | `world.json` | **auto-voice opt-in** — default `false` (see § B), governed by the `tts` axis; `!raconte` is unaffected either way |
| `MGM_TTS_AUTO` | env | instance-level auto-voice opt-in (default `0`; `world.json` wins). Ansible: `mgm_tts_auto` in `group_vars` — the unit file has no `MGM_TTS_AUTO` line unless that var is defined |
| `meta.langue` | `world.json` | campaign language code (e.g. `"fr"`, `"en"`) — selects the default voice/boost |
| `meta.audio.voice` | `world.json` | campaign voice override (takes priority over `meta.langue`) |
| `meta.audio.language_boost` | `world.json` | campaign language_boost override |
| `MGM_LANGUAGE` / `MGM_LANGUE` | env | instance-level language code (same effect as `meta.langue`, lower priority) |
| `MINIMAX_API_KEY` | env (vault) | Minimax key — absent = no audio, recorded as `failed:key_missing` (not as a silence by choice) |
| `MGM_TTS_MIN_CHARS` | env | auto-voice length threshold (default 280) |
| `MGM_TTS_FORMAT_MODEL` | env | format step model (default `minimax/minimax-m3`) |
| `MGM_TTS_SEGMENT` | env | multi-emotion voice by segments (default ON; `0`/`off` = mono-call) |
| `MGM_TTS_TIMEOUT` | env | auto-voice **wall-clock** budget in the hook (default 40 s; keep it under the runtime's 45 s hook timeout, otherwise the whole hook is killed and the turn loses its CSV line too). The `--timeout` the hook passes on to the renderer is a **per-call** budget and segmented synthesis applies it once per segment, so only this kill deadline actually bounds the total — an overrun is recorded as `failed:timeout` |
| `MGM_TTS_PRODUCER` | env | caller tag stamped in the sidecar (`manual`, `hook-auto`, `doctor`) |
| `MGM_TTS_AMBIANCE_VOLUME` | env | ambient bed volume under voice (default 0.16) |

---

## Dependencies

| Dependency | Role |
|---|---|
| `mygamemaster` (umbrella skill) | persona, conventions, `transform_llm_output` hook (auto-voice + `last_narration` snapshot + `.banquier/tts-status.json` journal) |
| `scripts/` (Minimax + OpenRouter) | actual generation (`tts_render.py` & modules) |
| `ffmpeg` (container image) | ambient mixing (fail-open if absent) |
| `MINIMAX_API_KEY` / `OPENROUTER_API_KEY` | synthesis / format step |
| `world.json` | `tts` axis, `meta.hooks.tts_auto` toggles |

---

## Integration with umbrella skill

- **Guard feature-flag first** (step 0) — like `mygamemaster-images`.
- **Appropriate channel**: voice is posted in the campaign channel, as `MEDIA:`.
- **Transparency**: never expose TTS markup (`<#x#>`, emotions) in the written message.
- **MJ Tonnerre format**: short, immersive status message (emoji 🔊).

> Anti-patterns: voice a Steward block or mechanics (narration only); post without checking exit code;
> hard-code the `.mp3` name (always use the returned path); pass text as a shell argument (always
> via **stdin**); **use the runtime's built-in `tts_tool`** instead of `tts_render.py` (different
> engine, no sidecar, silently degrades the voice — see the `!raconte` flow); answer "the voice
> doesn't work" from intuition instead of running `tts_doctor.py`.
