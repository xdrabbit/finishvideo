"""Media probing helpers for finishvideo."""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class MusicTrack:
    path: Path
    duration: float


@dataclass(frozen=True)
class ClipInfo:
    path: Path
    duration: float
    resolution: str | None
    fps: float | None
    has_audio: bool


def parse_fps(value: str | None) -> float | None:
    if not value or value == "0/0":
        return None
    if "/" in value:
        numerator, denominator = value.split("/", 1)
        try:
            denominator_float = float(denominator)
            if denominator_float == 0:
                return None
            return float(numerator) / denominator_float
        except ValueError:
            return None
    try:
        return float(value)
    except ValueError:
        return None


def parse_probe_json(path: Path, payload: dict) -> ClipInfo:
    format_data = payload.get("format", {})
    streams = payload.get("streams", [])

    try:
        duration = float(format_data["duration"])
    except (KeyError, TypeError, ValueError) as exc:
        raise SystemExit(f"error: could not read duration for {path}") from exc

    video_stream = next(
        (stream for stream in streams if stream.get("codec_type") == "video"),
        None,
    )
    audio_stream = next(
        (stream for stream in streams if stream.get("codec_type") == "audio"),
        None,
    )

    resolution: str | None = None
    fps: float | None = None
    if video_stream is not None:
        width = video_stream.get("width")
        height = video_stream.get("height")
        if width and height:
            resolution = f"{width}x{height}"
        fps = parse_fps(video_stream.get("avg_frame_rate")) or parse_fps(
            video_stream.get("r_frame_rate")
        )

    return ClipInfo(
        path=path,
        duration=duration,
        resolution=resolution,
        fps=fps,
        has_audio=audio_stream is not None,
    )


def probe_media(path: Path) -> ClipInfo:
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_format",
            "-show_streams",
            "-of",
            "json",
            str(path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"error: could not parse ffprobe output for {path}") from exc

    return parse_probe_json(path, payload)


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
