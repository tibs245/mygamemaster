# Scripts — narrative voice (mj-tonnerre-tts)

Three **pure stdlib** scripts (no pip dependencies), baked into the image. The pipeline
fully offloads the **GM model**: it continues to write its narration normally,
these scripts handle the voice downstream, without polluting the written message.

```
written narration ──► tts_format.py ──► tts_generate.py ──► (ffmpeg) ──► voice.mp3
                       (small model)     (Minimax T2A v2)   ambiance
```

| Script | Role | Network |
|---|---|---|
| **`tts_render.py`** | **Normal path**: orchestrates format → synthesis → ambiance, writes MP3 + sidecar | via the 2 following |
| `tts_format.py` | Narration → voice script (pauses `<#x.x#>`, tics preserved, mechanics removed) + emotion/ambiance/key-moment | OpenRouter (`minimax/minimax-m3`, weak reflection) |
| `tts_generate.py` | Voice script → MP3 (voice `French_Female_Speech_New`, model `speech-2.8-turbo`) | Minimax T2A v2 |

## Conventions (shared across project media scripts)

- **Keys in environment, never as arguments**: `MINIMAX_API_KEY` (synthesis),
  `OPENROUTER_API_KEY` (format). Injected into container via `EnvironmentFile`.
- **Text via stdin / `--text-file`**, never as arguments (markup `<#x#>`, accents).
- **Exit codes**: `0` ok · `1` synthesis failure (no audio) · `2` usage
  (missing key, empty text). Auto-TTS hook **fails open** on `≠ 0` (no `MEDIA:`).
- **Fail-open**: format failure → cleaned narration + `emotion=calm` ; ambiance/ffmpeg failure →
  voice only. Only total synthesis failure returns `1`.

## Examples

```bash
# Normal path (what the auto hook and !raconte command call)
echo "<narration>" | python3 tts_render.py --out voice.mp3 --json

# Without ambiance, voice only
echo "<narration>" | python3 tts_render.py --out voice.mp3 --no-ambiance

# Isolated building blocks
echo "<narration>" | python3 tts_format.py            # → JSON {script,emotion,ambiance,moment_cle}
echo "<script>"    | python3 tts_generate.py --out v.mp3 --emotion fearful
```

## Environment Variables

| Variable | Effect |
|---|---|
| `MINIMAX_API_KEY` | Minimax key (without it: no-op, exit 2) |
| `OPENROUTER_API_KEY` | key for format step (without it: fallback simple cleanup) |
| `MJ_TTS_FORMAT_MODEL` | model for format step (default `minimax/minimax-m3`) |
| `MJ_TTS_AMBIANCE_VOLUME` | volume of ambiance bed under voice (default `0.16`) |
| `MINIMAX_API_URL` | T2A endpoint (default `https://api.minimax.io/v1/t2a_v2`) |
| `MJ_TTS_MOCK=1` | mock synthesis offline (testing) |
| `MJ_TTS_FORMAT_MOCK=<json>` | format output injected offline (testing) |

For details per script: `python3 <script> --help`.
