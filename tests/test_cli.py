from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

from finishvideo.cli import (
    TransitionOffset,
    build_ffmpeg_command,
    build_xfade_filter,
    compute_transition_offsets,
    ffmpeg_number,
    rounded_to_beat,
)


class FormatTests(unittest.TestCase):
    def test_ffmpeg_number_trims_trailing_zeroes(self) -> None:
        self.assertEqual(ffmpeg_number(1.500000), "1.5")
        self.assertEqual(ffmpeg_number(2.0), "2")
        self.assertEqual(ffmpeg_number(0.333333333), "0.333333")


class BeatTests(unittest.TestCase):
    def test_rounded_to_beat(self) -> None:
        self.assertEqual(rounded_to_beat(1.01, 120), 1.0)
        self.assertEqual(rounded_to_beat(1.26, 120), 1.5)


class OffsetTests(unittest.TestCase):
    def test_compute_transition_offsets_without_beat_sync(self) -> None:
        offsets = compute_transition_offsets([10.0, 8.0, 6.0], 0.5, False, None)

        self.assertEqual(
            offsets,
            [
                TransitionOffset(index=1, before_beat_sync=9.5, after_beat_sync=9.5),
                TransitionOffset(index=2, before_beat_sync=17.0, after_beat_sync=17.0),
            ],
        )

    def test_compute_transition_offsets_with_beat_sync(self) -> None:
        offsets = compute_transition_offsets([10.0, 8.0, 6.0], 0.6, True, 120)

        self.assertEqual(offsets[0].before_beat_sync, 9.4)
        self.assertEqual(offsets[0].after_beat_sync, 9.5)
        self.assertEqual(offsets[1].before_beat_sync, 16.8)
        self.assertEqual(offsets[1].after_beat_sync, 17.0)


class FfmpegBuildTests(unittest.TestCase):
    def test_build_xfade_filter(self) -> None:
        filter_complex, final_video = build_xfade_filter(
            [
                TransitionOffset(index=1, before_beat_sync=9.5, after_beat_sync=9.5),
                TransitionOffset(index=2, before_beat_sync=17.0, after_beat_sync=17.0),
            ],
            "wipeleft",
            0.5,
        )

        self.assertEqual(final_video, "[v2]")
        self.assertEqual(
            filter_complex,
            "[0:v][1:v]xfade=transition=wipeleft:duration=0.5:offset=9.5[v1];"
            "[v1][2:v]xfade=transition=wipeleft:duration=0.5:offset=17[v2]",
        )

    def test_build_ffmpeg_command(self) -> None:
        command = build_ffmpeg_command(
            [Path("clip1.mp4"), Path("clip2.mp4")],
            Path("output.mp4"),
            "[0:v][1:v]xfade=transition=fade:duration=0.5:offset=9.5[v1]",
            "[v1]",
        )

        self.assertEqual(command[:6], ["ffmpeg", "-hide_banner", "-y", "-i", "clip1.mp4", "-i"])
        self.assertIn("-filter_complex", command)
        self.assertIn("hevc_videotoolbox", command)
        self.assertEqual(command[-1], "output.mp4")


if __name__ == "__main__":
    unittest.main()
