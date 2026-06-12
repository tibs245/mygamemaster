# Ambiance sound beds — narrative voice

These files are **layered beneath the voice** (low volume, ~0.16) by `scripts/tts_render.py`
when the formatting step proposes an ambiance **and** the turn is a **key moment** or
a **long narrative** (see `--threshold-chars`). Mixing is done via **ffmpeg** (present
in the container image). If absent → the voice plays **alone** (fail-open, no error).

## Expected tags (one `.mp3` per tag)

The tag is selected by `tts_format.py` from this fixed set (`VALID_AMBIANCES`) :

| File | Ambiance |
|---|---|
| `foret.mp3`   | forest, nature, wind in leaves |
| `taverne.mp3` | tavern, hubbub, fireplace |
| `combat.mp3`  | tension, drums, distant sounds |
| `nuit.mp3`    | night, crickets, eerie silence |
| `ville.mp3`   | street, market, urban crowd |
| `donjon.mp3`  | cavern, water drops, echo |
| `mer.mp3`     | waves, seagulls, sea wind |

`aucune` → no file, no mixing (default case).

## File constraints

- **Format** : MP3 (mixed with `libmp3lame` 128 kbps). Mono or stereo.
- **Duration** : no matter — `tts_render.py` **loops** them (`-stream_loop -1`) and cuts to
  the voice duration. A clean loop of 20–60 s is sufficient and stays lightweight.
- **Level** : recorded at normal level; attenuation is applied during mixing
  (`MJ_TTS_AMBIANCE_VOLUME`, default `0.16`). Keep the voice in the **foreground**.
- **License** : use only **royalty-free sounds** (e.g. CC0 — freesound.org,
  pixabay). This folder is versioned: no files under restrictive license.

## Campaign override

`tts_render.py --ambiance-dir <folder>` lets you point to a campaign-specific sound bank
(e.g. `<campaign>/tts/ambiances/`) to match its sonic universe. Without override, this
base bank is used.

> The actual `.mp3` files are not shipped in the repository (heavy binaries / licenses). Place
> your chosen loops here, or point `--ambiance-dir` to an external bank. As long as a tag has no
> file, the corresponding turn outputs in **voice only** — without error.
