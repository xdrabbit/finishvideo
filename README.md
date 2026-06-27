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

Preview the computed durations, offsets, and ffmpeg command without rendering:

```sh
./finishvideo.py --dry-run clip1.mp4 clip2.mp4 clip3.mp4 output.mp4
```

Preview beat-synced offsets before rendering:

```sh
./finishvideo.py --dry-run --beat-sync --bpm 124 clip1.mp4 clip2.mp4 clip3.mp4 output.mp4
```

Options:

- `--transition`: ffmpeg `xfade` transition name. Defaults to `fade`.
- `--duration`: transition length in seconds. Defaults to `0.5`.
- `--beat-sync`: round each transition offset to the nearest beat.
- `--bpm`: beats per minute for `--beat-sync`.
- `--video-codec`: ffmpeg video codec. Defaults to `libx264` for Linux and broad compatibility.
- `--video-bitrate`: ffmpeg video bitrate. Defaults to `8000k`.
- `--dry-run`: print input clips, durations, transition settings, computed
  offsets, and the ffmpeg command without running ffmpeg.

The legacy Bash version is preserved at `legacy/finishvideo.sh`. The original
`~/bin/finishvideo` file has not been deleted.


## Development

Run the unit tests without installing extra dependencies:

```sh
PYTHONPATH=src python3 -m unittest discover -s tests
```

Check Python syntax:

```sh
python3 -m py_compile finishvideo.py src/finishvideo/cli.py tests/test_cli.py
```
