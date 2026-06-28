"""Audio probing helpers for finishvideo."""

from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path


BPM_TAG_KEYS = {"bpm", "tbpm", "tempo", "initialbpm"}
BPM_TAG_PATTERN = re.compile(r"\s*(\d+(?:\.\d+)?)\s*(?:bpm)?\s*\Z", re.IGNORECASE)


@dataclass(frozen=True)
class AudioInfo:
    path: Path
    duration: float
    codec: str | None
    sample_rate: int | None
    channels: int | None
    bitrate: int | None
    tags: dict[str, str]
    metadata_bpm: float | None = None


def parse_optional_int(value: object) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(str(value))
    except ValueError:
        return None


def normalize_bpm_tag_value(value: str) -> float | None:
    match = BPM_TAG_PATTERN.fullmatch(value)
    if match is None:
        return None

    try:
        bpm = float(match.group(1))
    except ValueError:
        return None

    if bpm <= 0:
        return None
    return bpm


def extract_bpm_from_tags(tags: dict[str, str]) -> float | None:
    bpm_values = set()

    for key, value in tags.items():
        if key.casefold() not in BPM_TAG_KEYS:
            continue

        bpm = normalize_bpm_tag_value(value)
        if bpm is None:
            return None
        bpm_values.add(bpm)

    if len(bpm_values) != 1:
        return None
    return bpm_values.pop()


def parse_audio_probe_json(path: Path, payload: dict) -> AudioInfo:
    format_data = payload.get("format", {})
    streams = payload.get("streams", [])
    audio_stream = next(
        (stream for stream in streams if stream.get("codec_type") == "audio"),
        None,
    )

    if audio_stream is None:
        raise SystemExit(f"error: no audio stream found in {path}")

    duration_value = audio_stream.get("duration") or format_data.get("duration")
    try:
        duration = float(duration_value)
    except (TypeError, ValueError) as exc:
        raise SystemExit(f"error: could not read audio duration for {path}") from exc

    tags: dict[str, str] = {}
    for source in (format_data.get("tags", {}), audio_stream.get("tags", {})):
        if isinstance(source, dict):
            for key, value in source.items():
                tags[str(key)] = str(value)

    bitrate = parse_optional_int(audio_stream.get("bit_rate"))
    if bitrate is None:
        bitrate = parse_optional_int(format_data.get("bit_rate"))

    return AudioInfo(
        path=path,
        duration=duration,
        codec=audio_stream.get("codec_name"),
        sample_rate=parse_optional_int(audio_stream.get("sample_rate")),
        channels=parse_optional_int(audio_stream.get("channels")),
        bitrate=bitrate,
        tags=tags,
        metadata_bpm=extract_bpm_from_tags(tags),
    )


def probe_audio(path: Path) -> AudioInfo:
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

    return parse_audio_probe_json(path, payload)
