"""Timeline calculations for finishvideo renders."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TransitionOffset:
    index: int
    before_beat_sync: float
    after_beat_sync: float


def rounded_to_beat(offset: float, bpm: float, beat_offset: float = 0.0) -> float:
    beat = 60.0 / bpm
    return beat_offset + round((offset - beat_offset) / beat) * beat


def build_beat_grid(bpm: float, count: int, offset: float = 0.0) -> list[float]:
    beat = 60.0 / bpm
    return [offset + beat * index for index in range(count)]


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


def compute_output_duration(
    durations: list[float],
    transition_offsets: list[TransitionOffset],
) -> float:
    if not transition_offsets:
        return durations[0]
    return transition_offsets[-1].after_beat_sync + durations[-1]


def estimate_composed_duration(
    durations: list[float],
    transition_duration: float,
) -> float:
    offsets = compute_transition_offsets(durations, transition_duration, False, None)
    return compute_output_duration(durations, offsets)
