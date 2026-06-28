# finishvideo

`finishvideo.py` joins multiple MP4 clips into one output video using `ffprobe`
for clip durations and `ffmpeg` `xfade` filters for transitions.

## Requirements

- Python 3.10 or newer
- `ffmpeg` and `ffprobe` on your `PATH`

## Install

Run directly from a source checkout:

```sh
./finishvideo.py clip1.mp4 clip2.mp4 output.mp4
```

Or install it as a local command:

```sh
python3 -m pip install .
finishvideo clip1.mp4 clip2.mp4 output.mp4
```

## Usage

Pass two or more input MP4 files followed by the output filename:

```sh
./finishvideo.py clip1.mp4 clip2.mp4 output.mp4
```

Use a different `xfade` transition:

```sh
./finishvideo.py --transition wipeleft clip1.mp4 clip2.mp4 clip3.mp4 output.mp4
```

Set the transition duration:

```sh
./finishvideo.py --duration 0.75 clip1.mp4 clip2.mp4 output.mp4
```

Use macOS hardware HEVC encoding when running on a Mac:

```sh
./finishvideo.py --video-codec hevc_videotoolbox --video-bitrate 8000k clip1.mp4 clip2.mp4 output.mp4
```

Round transition offsets to the nearest beat:

```sh
./finishvideo.py --beat-sync --bpm 124 clip1.mp4 clip2.mp4 clip3.mp4 output.mp4
```

Use a music file's metadata BPM tag for beat sync:

```sh
./finishvideo.py --beat-sync --bpm metadata --music song.mp3 clip1.mp4 clip2.mp4 clip3.mp4 output.mp4
```

Shift the beat grid before snapping transition offsets:

```sh
./finishvideo.py --beat-sync --bpm 124 --beat-offset 0.12 clip1.mp4 clip2.mp4 clip3.mp4 output.mp4
```

Use a music track as the final output audio:

```sh
./finishvideo.py --music song.mp3 clip1.mp4 clip2.mp4 clip3.mp4 output.mp4
```

Lower the music volume:

```sh
./finishvideo.py --music song.mp3 --music-volume 0.7 clip1.mp4 clip2.mp4 clip3.mp4 output.mp4
```

Render the final composed video in smooth slow motion:

```sh
./finishvideo.py --slowmo 2 --slowmo-fps 60 clip1.mp4 clip2.mp4 output_slow.mp4
```

Render beat-synced video with metadata BPM, music, and slow motion:

```sh
./finishvideo.py --music song.mp3 --beat-sync --bpm metadata --slowmo 2 --slowmo-fps 60 clip1.mp4 clip2.mp4 output_slow.mp4
```

Preview the computed durations, offsets, and ffmpeg command without rendering:

```sh
./finishvideo.py --dry-run clip1.mp4 clip2.mp4 clip3.mp4 output.mp4
```

Preview beat-synced offsets before rendering:

```sh
./finishvideo.py --dry-run --music song.mp3 --beat-sync --bpm 124 --beat-offset 0.12 clip1.mp4 clip2.mp4 clip3.mp4 output.mp4
```

Analyze clips before rendering:

```sh
./finishvideo.py analyze clip1.mp4 clip2.mp4 clip3.mp4
```

Analyze music metadata:

```sh
./finishvideo.py analyze-music song.mp3
```

Preview a beat grid from a known BPM without rendering:

```sh
./finishvideo.py analyze-music song.mp3 --bpm 124 --beats 16
```

Shift the preview beat grid:

```sh
./finishvideo.py analyze-music song.mp3 --bpm 124 --beats 16 --beat-offset 0.12
```

Options:

- `--transition`: ffmpeg `xfade` transition name. Defaults to `fade`.
- `--duration`: transition length in seconds. Defaults to `0.5`.
- `--beat-sync`: round each transition offset to the nearest beat.
- `--bpm`: beats per minute for `--beat-sync`, or `metadata` to use a usable
  BPM tag from `--music`.
- `--beat-offset`: beat grid offset in seconds for `--beat-sync`. Defaults to `0`.
- `--music`: music/audio file to use as the final output audio track.
- `--music-volume`: music volume multiplier used with `--music`. Defaults to `1.0`;
  use values such as `0.7` to lower the track.
- `--slowmo`: slow the final composed video by this factor after transitions.
  Defaults to `1.0`, which disables slow motion. Values must be `>= 1.0`.
- `--slowmo-fps`: interpolation frame rate for `--slowmo`. Defaults to `60`.
- `--video-codec`: ffmpeg video codec. Defaults to `libx264` for Linux and broad compatibility.
- `--video-bitrate`: ffmpeg video bitrate. Defaults to `8000k`.
- `--dry-run`: print input clips, durations, transition settings, computed
  offsets, music metadata, and the ffmpeg command without running ffmpeg.
- `analyze-music --bpm`: BPM used for beat-grid preview.
- `analyze-music --beats`: number of beat timestamps to preview.
- `analyze-music --beat-offset`: beat grid offset in seconds for preview.

Notes:

- Beat sync currently snaps transition offsets to a manual BPM grid starting at
  time zero, plus optional `--beat-offset`; it does not perform automatic audio
  beat detection yet.
- `--beat-sync --bpm metadata --music song.mp3` uses only simple music metadata
  tags. It does not infer BPM from the waveform or detect onsets.
- `analyze-music` reads audio stream and container metadata, including tags such
  as `BPM`, `TBPM`, `tempo`, and `initialkey` when present. It also reports a
  conservative metadata BPM from simple numeric `BPM`, `TBPM`, `tempo`, or
  `initialbpm` tag values when present.
- Metadata BPM is useful as a known reference when the tag came from a trusted
  source. If automatic BPM detection is added later, this gives a debuggable
  ground truth to compare against when detection disagrees.
- `analyze-music --beats` previews a lightweight beat grid from `--bpm`, or from
  metadata BPM when `--bpm` is omitted. This is only a timing preview. It is NOT
  automatic beat detection from waveform/audio.
- When `--music` is provided, the music replaces clip audio in the output. The
  render ends at the composed video duration, not at the music duration.
- Slow motion uses FFmpeg optical-flow interpolation via `minterpolate`, not
  AI/RIFE. It is dependency-light and CPU-compatible, but can create artifacts
  on fast motion.

The legacy Bash version is preserved at `legacy/finishvideo.sh`. The original
`~/bin/finishvideo` file has not been deleted.

## Quick smoke test

Create tiny local fixtures:

```sh
scripts/make_smoke_fixtures.sh /tmp/finishvideo-smoke
```

Inspect the generated clips:

```sh
./finishvideo.py analyze /tmp/finishvideo-smoke/clip1.mp4 /tmp/finishvideo-smoke/clip2.mp4 /tmp/finishvideo-smoke/clip3.mp4
```

Inspect the generated music metadata:

```sh
./finishvideo.py analyze-music /tmp/finishvideo-smoke/music.m4a
```

Inspect the tagged music metadata:

```sh
ffprobe -v error -show_entries format_tags=BPM -of default=nw=1 /tmp/finishvideo-smoke/music_bpm120.m4a
./finishvideo.py analyze-music /tmp/finishvideo-smoke/music_bpm120.m4a
```

Preview a generated beat grid:

```sh
./finishvideo.py analyze-music /tmp/finishvideo-smoke/music.m4a --bpm 120 --beats 8 --beat-offset 0.1
```

Preview the render command with music:

```sh
./finishvideo.py --dry-run --music /tmp/finishvideo-smoke/music.m4a /tmp/finishvideo-smoke/clip1.mp4 /tmp/finishvideo-smoke/clip2.mp4 /tmp/finishvideo-smoke/clip3.mp4 /tmp/finishvideo-smoke/output.mp4
```

Preview the metadata BPM render command:

```sh
./finishvideo.py --dry-run --music /tmp/finishvideo-smoke/music_bpm120.m4a --beat-sync --bpm metadata --beat-offset 0.1 /tmp/finishvideo-smoke/clip1.mp4 /tmp/finishvideo-smoke/clip2.mp4 /tmp/finishvideo-smoke/clip3.mp4 /tmp/finishvideo-smoke/output_metadata.mp4
```

Preview a slow-motion render command:

```sh
./finishvideo.py --dry-run --slowmo 2 --slowmo-fps 60 /tmp/finishvideo-smoke/clip1.mp4 /tmp/finishvideo-smoke/clip2.mp4 /tmp/finishvideo-smoke/output_slow.mp4
```

Render a tiny output:

```sh
./finishvideo.py --music /tmp/finishvideo-smoke/music.m4a /tmp/finishvideo-smoke/clip1.mp4 /tmp/finishvideo-smoke/clip2.mp4 /tmp/finishvideo-smoke/clip3.mp4 /tmp/finishvideo-smoke/output.mp4
```

Render a tiny metadata BPM output:

```sh
./finishvideo.py --music /tmp/finishvideo-smoke/music_bpm120.m4a --beat-sync --bpm metadata --beat-offset 0.1 /tmp/finishvideo-smoke/clip1.mp4 /tmp/finishvideo-smoke/clip2.mp4 /tmp/finishvideo-smoke/clip3.mp4 /tmp/finishvideo-smoke/output_metadata.mp4
```

Render a tiny slow-motion output:

```sh
./finishvideo.py --slowmo 2 --slowmo-fps 60 /tmp/finishvideo-smoke/clip1.mp4 /tmp/finishvideo-smoke/clip2.mp4 /tmp/finishvideo-smoke/output_slow.mp4
```

Run unit tests:

```sh
PYTHONPATH=src python3 -m unittest discover -s tests
```


## Development

Run the unit tests without installing extra dependencies:

```sh
PYTHONPATH=src python3 -m unittest discover -s tests
```

Check Python syntax:

```sh
python3 -m py_compile finishvideo.py src/finishvideo/*.py tests/test_cli.py
```
