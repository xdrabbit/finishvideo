"""Output formatting helpers for finishvideo."""

from __future__ import annotations

import shlex
from pathlib import Path

from finishvideo.audio import AudioInfo
from finishvideo.probe import ClipInfo, MusicTrack
from finishvideo.timeline import TransitionOffset, estimate_composed_duration


def ffmpeg_number(value: float) -> str:
    return f"{value:.6f}".rstrip("0").rstrip(".")


def format_optional(value: str | None) -> str:
    return value if value is not None else "unknown"


def format_optional_int(value: int | None) -> str:
    return str(value) if value is not None else "unknown"


def print_dry_run(
    clips: list[Path],
    durations: list[float],
    music_track: MusicTrack | None,
    transition: str,
    transition_duration: float,
    transition_offsets: list[TransitionOffset],
    beat_sync: bool,
    bpm: float | None,
    bpm_source: str | None,
    beat_offset: float,
    music_volume: float,
    output_duration: float,
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
        print(f"  volume: {ffmpeg_number(music_volume)}")
        print("  output audio: music")

    print("\nTransition:")
    print(f"  type: {transition}")
    print(f"  duration: {ffmpeg_number(transition_duration)}s")
    print(f"  beat sync: {'on' if beat_sync else 'off'}")
    if bpm is not None:
        print(f"  bpm: {ffmpeg_number(bpm)}")
    if bpm_source is not None:
        print(f"  bpm source: {bpm_source}")
    print(f"  beat offset: {ffmpeg_number(beat_offset)}s")
    print(f"  output duration: {ffmpeg_number(output_duration)}s")

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


def print_analyze(
    clips: list[ClipInfo],
    transition_duration: float,
) -> None:
    print("Source clips:")
    for index, clip in enumerate(clips, start=1):
        print(f"  {index}. path: {clip.path}")
        print(f"     duration: {ffmpeg_number(clip.duration)}s")
        print(f"     resolution: {format_optional(clip.resolution)}")
        fps = "unknown" if clip.fps is None else f"{ffmpeg_number(clip.fps)} fps"
        print(f"     fps: {fps}")
        print(f"     audio: {'yes' if clip.has_audio else 'no'}")

    durations = [clip.duration for clip in clips]
    total_source_duration = sum(durations)
    composed_duration = estimate_composed_duration(durations, transition_duration)

    print("\nSummary:")
    print(f"  total source duration: {ffmpeg_number(total_source_duration)}s")
    print(f"  transition duration: {ffmpeg_number(transition_duration)}s")
    print(f"  estimated composed duration: {ffmpeg_number(composed_duration)}s")


def print_analyze_music(
    audio: AudioInfo,
    beat_grid: list[float] | None = None,
    preview_bpm: float | None = None,
    beat_offset: float = 0.0,
) -> None:
    print("Music:")
    print(f"  path: {audio.path}")
    print(f"  duration: {ffmpeg_number(audio.duration)}s")
    print(f"  codec: {format_optional(audio.codec)}")
    sample_rate = (
        "unknown" if audio.sample_rate is None else f"{audio.sample_rate} Hz"
    )
    print(f"  sample rate: {sample_rate}")
    print(f"  channels: {format_optional_int(audio.channels)}")
    if audio.bitrate is not None:
        print(f"  bitrate: {audio.bitrate} bps")
    metadata_bpm = (
        "unknown" if audio.metadata_bpm is None else ffmpeg_number(audio.metadata_bpm)
    )
    print(f"  metadata bpm: {metadata_bpm}")

    if beat_grid is not None:
        assert preview_bpm is not None
        print("\nBeat grid preview:")
        print(f"  bpm: {ffmpeg_number(preview_bpm)}")
        print(f"  beat interval: {ffmpeg_number(60.0 / preview_bpm)}s")
        print(f"  beat count: {len(beat_grid)}")
        print(f"  beat offset: {ffmpeg_number(beat_offset)}s")
        print("  beats:")
        for index, timestamp in enumerate(beat_grid, start=1):
            print(f"    {index}: {ffmpeg_number(timestamp)}s")

    print("\nMetadata:")
    if not audio.tags:
        print("  none")
        return

    for key in sorted(audio.tags, key=str.casefold):
        print(f"  {key}: {audio.tags[key]}")
