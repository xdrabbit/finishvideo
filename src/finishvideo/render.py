"""ffmpeg render command construction."""

from __future__ import annotations

from pathlib import Path

from finishvideo.formatting import ffmpeg_number
from finishvideo.timeline import TransitionOffset


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
    music_volume: float = 1.0,
    output_duration: float | None = None,
) -> list[str]:
    command = ["ffmpeg", "-hide_banner", "-y"]
    for clip in clips:
        command.extend(["-i", str(clip)])

    final_audio: str | None = None
    if music is not None:
        music_index = len(clips)
        command.extend(["-i", str(music)])
        final_audio = "[a_music]"
        filter_complex = (
            f"{filter_complex};"
            f"[{music_index}:a]volume={ffmpeg_number(music_volume)}{final_audio}"
        )

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
        command.extend(["-map", final_audio, "-c:a", "aac", "-b:a", "192k"])
        if output_duration is not None:
            command.extend(["-t", ffmpeg_number(output_duration)])

    command.append(str(output))
    return command
