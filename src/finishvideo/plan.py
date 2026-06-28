"""Validated render plan construction."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

from finishvideo.audio import AudioInfo, probe_audio
from finishvideo.probe import MusicTrack, probe_duration
from finishvideo.render import build_ffmpeg_command, build_xfade_filter
from finishvideo.timeline import (
    TransitionOffset,
    compute_output_duration,
    compute_transition_offsets,
)

BPM_METADATA = "metadata"


@dataclass(frozen=True)
class BpmResolution:
    bpm: float | None
    source: str | None


@dataclass(frozen=True)
class RenderPlan:
    clips: list[Path]
    output: Path
    durations: list[float]
    music_track: MusicTrack | None
    transition: str
    transition_duration: float
    transition_offsets: list[TransitionOffset]
    beat_sync: bool
    bpm: float | None
    bpm_source: str | None
    beat_offset: float
    music_volume: float
    video_codec: str
    video_bitrate: str
    output_duration: float
    filter_complex: str
    final_video: str
    command: list[str]


def resolve_bpm(
    args: argparse.Namespace,
    music_audio_info: AudioInfo | None = None,
) -> BpmResolution:
    if not args.beat_sync:
        return BpmResolution(None, None)

    if args.bpm == BPM_METADATA:
        if args.music is None:
            raise SystemExit("error: --bpm metadata requires --music")
        if music_audio_info is None:
            raise SystemExit("error: --bpm metadata requires music metadata")
        if music_audio_info.metadata_bpm is None:
            raise SystemExit(
                "error: --bpm metadata requires a usable metadata BPM tag "
                "on the music file (missing, invalid, or ambiguous)"
            )
        return BpmResolution(music_audio_info.metadata_bpm, BPM_METADATA)

    return BpmResolution(args.bpm, "manual")


def build_render_plan(
    args: argparse.Namespace,
    clips: list[Path],
    output: Path,
) -> RenderPlan:
    durations = [probe_duration(clip) for clip in clips]
    music_audio_info = None
    if args.music is not None and args.beat_sync and args.bpm == BPM_METADATA:
        music_audio_info = probe_audio(args.music)
        music_track = MusicTrack(args.music, music_audio_info.duration)
    else:
        music_track = (
            MusicTrack(args.music, probe_duration(args.music))
            if args.music is not None
            else None
        )

    bpm_resolution = resolve_bpm(args, music_audio_info)
    transition_offsets = compute_transition_offsets(
        durations,
        args.duration,
        args.beat_sync,
        bpm_resolution.bpm,
        args.beat_offset,
    )
    filter_complex, final_video = build_xfade_filter(
        transition_offsets,
        args.transition,
        args.duration,
    )
    output_duration = compute_output_duration(durations, transition_offsets)
    command = build_ffmpeg_command(
        clips,
        output,
        filter_complex,
        final_video,
        args.video_codec,
        args.video_bitrate,
        args.music,
        args.music_volume,
        output_duration,
    )

    return RenderPlan(
        clips=clips,
        output=output,
        durations=durations,
        music_track=music_track,
        transition=args.transition,
        transition_duration=args.duration,
        transition_offsets=transition_offsets,
        beat_sync=args.beat_sync,
        bpm=bpm_resolution.bpm,
        bpm_source=bpm_resolution.source,
        beat_offset=args.beat_offset,
        music_volume=args.music_volume,
        video_codec=args.video_codec,
        video_bitrate=args.video_bitrate,
        output_duration=output_duration,
        filter_complex=filter_complex,
        final_video=final_video,
        command=command,
    )
