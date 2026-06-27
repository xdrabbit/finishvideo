#!/usr/bin/env python3
"""Render multiple MP4 clips into one video with ffmpeg xfade transitions."""

from __future__ import annotations

import argparse
import shlex
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class TransitionOffset:
    index: int
    before_beat_sync: float
    after_beat_sync: float


@dataclass(frozen=True)
class MusicTrack:
    path: Path
    duration: float


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="finishvideo",
        description="Join MP4 clips with ffmpeg xfade transitions.",
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
        type=float,
        help="Beats per minute used with --beat-sync.",
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
        "--music-audio",
        choices=("replace", "mix"),
        default="replace",
        help=(
            "How to combine --music with output audio. "
            "replace maps only the music track; mix combines music with clip audio. "
            "Default: replace"
        ),
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
    args = parser.parse_args()

    if len(args.paths) < 3:
        parser.error(
            "expected at least two input clips and one output file: "
            "clip1.mp4 clip2.mp4 output.mp4"
        )
    if args.duration <= 0:
        parser.error("--duration must be greater than 0")
    if args.beat_sync and args.bpm is None:
        parser.error("--beat-sync requires --bpm")
    if args.bpm is not None and args.bpm <= 0:
        parser.error("--bpm must be greater than 0")
    if args.beat_offset < 0:
        parser.error("--beat-offset must be greater than or equal to 0")
    if args.music_audio == "mix" and args.music is None:
        parser.error("--music-audio mix requires --music")

    return args


def require_tool(name: str) -> None:
    if shutil.which(name) is None:
        raise SystemExit(f"error: required tool not found on PATH: {name}")


def probe_duration(path: Path) -> float:
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    try:
        return float(result.stdout.strip())
    except ValueError as exc:
        raise SystemExit(f"error: could not read duration for {path}") from exc


def rounded_to_beat(offset: float, bpm: float, beat_offset: float = 0.0) -> float:
    beat = 60.0 / bpm
    return beat_offset + round((offset - beat_offset) / beat) * beat


def ffmpeg_number(value: float) -> str:
    return f"{value:.6f}".rstrip("0").rstrip(".")


def compute_transition_offsets(
    durations: list[float],
    transition_duration: float,
    beat_sync: bool,
    bpm: float | None,
    beat_offset: float = 0.0,
) -> list[TransitionOffset]:
    total_duration = durations[0]
    offsets: list[TransitionOffset] = []

    for index in range(1, len(durations)):
        before_beat_sync = total_duration - transition_duration * index
        after_beat_sync = before_beat_sync
        if beat_sync:
            assert bpm is not None
            after_beat_sync = rounded_to_beat(before_beat_sync, bpm, beat_offset)

        offsets.append(
            TransitionOffset(
                index=index,
                before_beat_sync=before_beat_sync,
                after_beat_sync=after_beat_sync,
            )
        )
        total_duration += durations[index]

    return offsets


def build_xfade_filter(
    transition_offsets: list[TransitionOffset],
    transition: str,
    transition_duration: float,
) -> tuple[str, str]:
    prev = "[0:v]"
    filter_parts: list[str] = []

    for item in transition_offsets:
        out = f"[v{item.index}]"
        filter_parts.append(
            f"{prev}[{item.index}:v]"
            f"xfade=transition={transition}:"
            f"duration={ffmpeg_number(transition_duration)}:"
            f"offset={ffmpeg_number(item.after_beat_sync)}"
            f"{out}"
        )
        prev = out

    return ";".join(filter_parts), prev


def build_ffmpeg_command(
    clips: list[Path],
    output: Path,
    filter_complex: str,
    final_video: str,
    video_codec: str = "libx264",
    video_bitrate: str = "8000k",
    music: Path | None = None,
    music_audio: str = "replace",
) -> list[str]:
    command = ["ffmpeg", "-hide_banner", "-y"]
    for clip in clips:
        command.extend(["-i", str(clip)])

    final_audio: str | None = None
    if music is not None:
        music_index = len(clips)
        command.extend(["-i", str(music)])
        if music_audio == "replace":
            final_audio = f"{music_index}:a:0"
        elif music_audio == "mix":
            clip_audio_inputs = "".join(f"[{index}:a]" for index in range(len(clips)))
            audio_filter = (
                f"{clip_audio_inputs}concat=n={len(clips)}:v=0:a=1[a_clips];"
                f"[a_clips][{music_index}:a]"
                "amix=inputs=2:duration=shortest:dropout_transition=0[aout]"
            )
            filter_complex = f"{filter_complex};{audio_filter}"
            final_audio = "[aout]"
        else:
            raise ValueError(f"unsupported music audio mode: {music_audio}")

    command.extend(
        [
            "-filter_complex",
            filter_complex,
            "-map",
            final_video,
            "-pix_fmt",
            "yuv420p",
            "-c:v",
            video_codec,
            "-b:v",
            video_bitrate,
        ]
    )
    if final_audio is None:
        command.append("-an")
    else:
        command.extend(["-map", final_audio, "-c:a", "aac", "-shortest"])

    command.append(str(output))
    return command


def print_dry_run(
    clips: list[Path],
    durations: list[float],
    music_track: MusicTrack | None,
    transition: str,
    transition_duration: float,
    transition_offsets: list[TransitionOffset],
    beat_sync: bool,
    bpm: float | None,
    beat_offset: float,
    music_audio: str,
    command: list[str],
) -> None:
    print("Input clips:")
    for index, clip in enumerate(clips, start=1):
        print(f"  {index}. {clip}")

    print("\nClip durations:")
    for clip, duration in zip(clips, durations):
        print(f"  {clip}: {ffmpeg_number(duration)}s")

    print("\nMusic:")
    if music_track is None:
        print("  path: none")
    else:
        print(f"  path: {music_track.path}")
        print(f"  duration: {ffmpeg_number(music_track.duration)}s")
        print(f"  audio mode: {music_audio}")

    print("\nTransition:")
    print(f"  type: {transition}")
    print(f"  duration: {ffmpeg_number(transition_duration)}s")
    print(f"  beat sync: {'on' if beat_sync else 'off'}")
    if bpm is not None:
        print(f"  bpm: {ffmpeg_number(bpm)}")
    print(f"  beat offset: {ffmpeg_number(beat_offset)}s")

    print("\nTransition offsets before beat sync:")
    for item in transition_offsets:
        print(
            f"  clip {item.index} -> clip {item.index + 1}: "
            f"{ffmpeg_number(item.before_beat_sync)}s"
        )

    if beat_sync:
        assert bpm is not None
        print(
            "\nTransition offsets after beat sync "
            f"({ffmpeg_number(bpm)} BPM, {ffmpeg_number(beat_offset)}s offset):"
        )
        for item in transition_offsets:
            print(
                f"  clip {item.index} -> clip {item.index + 1}: "
                f"{ffmpeg_number(item.after_beat_sync)}s"
            )

    print("\nffmpeg command:")
    print(f"  {shlex.join(command)}")


def run() -> int:
    args = parse_args()
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

    durations = [probe_duration(clip) for clip in clips]
    music_track = (
        MusicTrack(args.music, probe_duration(args.music)) if args.music is not None else None
    )
    transition_offsets = compute_transition_offsets(
        durations,
        args.duration,
        args.beat_sync,
        args.bpm,
        args.beat_offset,
    )
    filter_complex, final_video = build_xfade_filter(
        transition_offsets,
        args.transition,
        args.duration,
    )
    command = build_ffmpeg_command(
        clips,
        output,
        filter_complex,
        final_video,
        args.video_codec,
        args.video_bitrate,
        args.music,
        args.music_audio,
    )

    if args.dry_run:
        print_dry_run(
            clips,
            durations,
            music_track,
            args.transition,
            args.duration,
            transition_offsets,
            args.beat_sync,
            args.bpm,
            args.beat_offset,
            args.music_audio,
            command,
        )
        return 0

    subprocess.run(command, check=True)
    print(f"Created {output}")
    return 0


def main() -> None:
    try:
        raise SystemExit(run())
    except subprocess.CalledProcessError as exc:
        raise SystemExit(exc.returncode) from exc


if __name__ == "__main__":
    main()
