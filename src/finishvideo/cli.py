#!/usr/bin/env python3
"""Render multiple MP4 clips into one video with ffmpeg xfade transitions."""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

from finishvideo.formatting import print_analyze, print_analyze_music, print_dry_run
from finishvideo.audio import probe_audio
from finishvideo.plan import BPM_METADATA, build_render_plan
from finishvideo.probe import probe_media
from finishvideo.timeline import build_beat_grid


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    effective_argv = sys.argv[1:] if argv is None else argv
    if effective_argv and effective_argv[0] == "analyze":
        return parse_analyze_args(effective_argv[1:])
    if effective_argv and effective_argv[0] == "analyze-music":
        return parse_analyze_music_args(effective_argv[1:])

    parser = argparse.ArgumentParser(
        prog="finishvideo",
        description="Join MP4 clips with ffmpeg xfade transitions.",
        epilog=(
            "Use 'finishvideo analyze clip1.mp4 clip2.mp4' to inspect sources, "
            "or 'finishvideo analyze-music song.mp3' to inspect music metadata."
        ),
    )
    parser.add_argument(
        "--transition",
        default="fade",
        help="ffmpeg xfade transition name. Default: fade",
    )
    parser.add_argument(
        "--duration",
        type=float,
        default=0.5,
        help="Transition duration in seconds. Default: 0.5",
    )
    parser.add_argument(
        "--beat-sync",
        action="store_true",
        help="Round transition offsets to the nearest beat. Requires --bpm.",
    )
    parser.add_argument(
        "--bpm",
        help="Beats per minute used with --beat-sync, or 'metadata' with --music.",
    )
    parser.add_argument(
        "--beat-offset",
        type=float,
        default=0.0,
        help="Beat grid offset in seconds used with --beat-sync. Default: 0.",
    )
    parser.add_argument(
        "--music",
        type=Path,
        help="Music/audio file to use for the rendered output.",
    )
    parser.add_argument(
        "--music-volume",
        type=float,
        default=1.0,
        help="Music volume multiplier used with --music. Default: 1.0",
    )
    parser.add_argument(
        "--slowmo",
        type=float,
        default=1.0,
        help="Slow final composed video by this factor. Must be >= 1.0. Default: 1.0",
    )
    parser.add_argument(
        "--slowmo-fps",
        type=float,
        default=60.0,
        help="Interpolation frame rate used with --slowmo. Default: 60",
    )
    parser.add_argument(
        "--video-codec",
        default="libx264",
        help="ffmpeg video codec. Default: libx264",
    )
    parser.add_argument(
        "--video-bitrate",
        default="8000k",
        help="ffmpeg video bitrate. Default: 8000k",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print inputs, durations, offsets, and ffmpeg command without rendering.",
    )
    parser.add_argument(
        "paths",
        nargs="+",
        help="Input MP4 clips followed by the output MP4 filename.",
    )
    args = parser.parse_args(effective_argv)
    args.command = "render"

    if len(args.paths) < 3:
        parser.error(
            "expected at least two input clips and one output file: "
            "clip1.mp4 clip2.mp4 output.mp4"
        )
    if args.duration <= 0:
        parser.error("--duration must be greater than 0")
    if args.beat_sync and args.bpm is None:
        parser.error("--beat-sync requires --bpm")
    if args.bpm is not None:
        if args.bpm.casefold() == BPM_METADATA:
            args.bpm = BPM_METADATA
        else:
            try:
                args.bpm = float(args.bpm)
            except ValueError:
                parser.error("--bpm must be a positive number or metadata")
            if args.bpm <= 0:
                parser.error("--bpm must be greater than 0")
    if args.bpm == BPM_METADATA and args.music is None:
        parser.error("--bpm metadata requires --music")
    if args.beat_offset < 0:
        parser.error("--beat-offset must be greater than or equal to 0")
    if args.music_volume < 0:
        parser.error("--music-volume must be greater than or equal to 0")
    if args.slowmo < 1.0:
        parser.error("--slowmo must be greater than or equal to 1.0")
    if args.slowmo_fps <= 0:
        parser.error("--slowmo-fps must be greater than 0")

    return args


def parse_analyze_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="finishvideo analyze",
        description="Inspect source media and estimate composed duration.",
    )
    parser.add_argument(
        "--duration",
        type=float,
        default=0.5,
        help="Transition duration used for composed duration estimate. Default: 0.5",
    )
    parser.add_argument(
        "clips",
        nargs="+",
        help="Input media files to inspect.",
    )
    args = parser.parse_args(argv)
    args.command = "analyze"

    if args.duration <= 0:
        parser.error("--duration must be greater than 0")

    return args


def parse_analyze_music_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="finishvideo analyze-music",
        description="Inspect music/audio metadata for future beat-grid work.",
    )
    parser.add_argument(
        "music",
        type=Path,
        help="Music/audio file to inspect.",
    )
    parser.add_argument(
        "--bpm",
        type=float,
        help="Beats per minute used for beat-grid preview.",
    )
    parser.add_argument(
        "--beats",
        type=int,
        help="Number of beat timestamps to preview.",
    )
    parser.add_argument(
        "--beat-offset",
        type=float,
        default=0.0,
        help="Beat grid offset in seconds for preview. Default: 0.",
    )
    args = parser.parse_args(argv)
    args.command = "analyze-music"

    if args.bpm is not None and args.bpm <= 0:
        parser.error("--bpm must be greater than 0")
    if args.beats is not None and args.beats <= 0:
        parser.error("--beats must be greater than 0")
    if args.beat_offset < 0:
        parser.error("--beat-offset must be greater than or equal to 0")

    return args


def require_tool(name: str) -> None:
    if shutil.which(name) is None:
        raise SystemExit(f"error: required tool not found on PATH: {name}")


def run_analyze(args: argparse.Namespace) -> int:
    require_tool("ffprobe")
    clips = [Path(path) for path in args.clips]

    missing = [str(path) for path in clips if not path.exists()]
    if missing:
        raise SystemExit("error: input file not found: " + ", ".join(missing))

    print_analyze([probe_media(clip) for clip in clips], args.duration)
    return 0


def run_analyze_music(args: argparse.Namespace) -> int:
    require_tool("ffprobe")
    if not args.music.exists():
        raise SystemExit(f"error: input file not found: {args.music}")

    audio = probe_audio(args.music)
    preview_bpm = args.bpm
    beat_grid = None

    if args.beats is not None:
        if preview_bpm is None:
            preview_bpm = audio.metadata_bpm
        if preview_bpm is None:
            raise SystemExit("error: --beats requires --bpm or metadata BPM")
        beat_grid = build_beat_grid(preview_bpm, args.beats, args.beat_offset)

    print_analyze_music(audio, beat_grid, preview_bpm, args.beat_offset)
    return 0


def run() -> int:
    args = parse_args()
    if args.command == "analyze":
        return run_analyze(args)
    if args.command == "analyze-music":
        return run_analyze_music(args)

    require_tool("ffprobe")
    if not args.dry_run:
        require_tool("ffmpeg")

    output = Path(args.paths[-1])
    clips = [Path(path) for path in args.paths[:-1]]

    missing = [str(path) for path in clips if not path.exists()]
    if missing:
        raise SystemExit("error: input file not found: " + ", ".join(missing))
    if args.music is not None and not args.music.exists():
        raise SystemExit(f"error: music file not found: {args.music}")

    plan = build_render_plan(args, clips, output)

    if args.dry_run:
        print_dry_run(
            plan.clips,
            plan.durations,
            plan.music_track,
            plan.transition,
            plan.transition_duration,
            plan.transition_offsets,
            plan.beat_sync,
            plan.bpm,
            plan.bpm_source,
            plan.beat_offset,
            plan.music_volume,
            plan.slowmo_factor,
            plan.slowmo_fps,
            plan.output_duration,
            plan.command,
        )
        return 0

    subprocess.run(plan.command, check=True)
    print(f"Created {plan.output}")
    return 0


def main() -> None:
    try:
        raise SystemExit(run())
    except subprocess.CalledProcessError as exc:
        raise SystemExit(exc.returncode) from exc


if __name__ == "__main__":
    main()
