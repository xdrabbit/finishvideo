from pathlib import Path
from contextlib import redirect_stdout
import io
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

from finishvideo.cli import (
    ClipInfo,
    TransitionOffset,
    build_ffmpeg_command,
    build_xfade_filter,
    compute_output_duration,
    compute_transition_offsets,
    estimate_composed_duration,
    ffmpeg_number,
    parse_fps,
    parse_probe_json,
    print_analyze,
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

    def test_rounded_to_beat_with_offset(self) -> None:
        self.assertEqual(rounded_to_beat(1.01, 120, 0.25), 1.25)
        self.assertEqual(rounded_to_beat(1.49, 120, 0.25), 1.25)


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

    def test_compute_transition_offsets_with_beat_offset(self) -> None:
        offsets = compute_transition_offsets([10.0, 8.0], 0.5, True, 120, 0.25)

        self.assertEqual(offsets[0].before_beat_sync, 9.5)
        self.assertEqual(offsets[0].after_beat_sync, 9.25)

    def test_compute_output_duration_uses_final_offset(self) -> None:
        offsets = compute_transition_offsets([10.0, 8.0, 6.0], 0.5, False, None)

        self.assertEqual(compute_output_duration([10.0, 8.0, 6.0], offsets), 23.0)

    def test_estimate_composed_duration_subtracts_transition_overlap(self) -> None:
        self.assertEqual(estimate_composed_duration([2.0, 2.0, 2.0], 0.5), 5.0)


class AnalyzeTests(unittest.TestCase):
    def test_parse_fps_fraction(self) -> None:
        self.assertAlmostEqual(parse_fps("30000/1001"), 29.97002997002997)
        self.assertIsNone(parse_fps("0/0"))
        self.assertIsNone(parse_fps("not-a-rate"))

    def test_parse_probe_json_reads_video_and_audio_metadata(self) -> None:
        clip = parse_probe_json(
            Path("clip.mp4"),
            {
                "format": {"duration": "2.500000"},
                "streams": [
                    {
                        "codec_type": "video",
                        "width": 1920,
                        "height": 1080,
                        "avg_frame_rate": "30000/1001",
                    },
                    {"codec_type": "audio"},
                ],
            },
        )

        self.assertEqual(clip.path, Path("clip.mp4"))
        self.assertEqual(clip.duration, 2.5)
        self.assertEqual(clip.resolution, "1920x1080")
        self.assertAlmostEqual(clip.fps, 29.97002997002997)
        self.assertTrue(clip.has_audio)

    def test_print_analyze_formats_summary(self) -> None:
        output = io.StringIO()

        with redirect_stdout(output):
            print_analyze(
                [
                    ClipInfo(Path("clip1.mp4"), 2.0, "320x240", 30.0, True),
                    ClipInfo(Path("clip2.mp4"), 2.0, None, None, False),
                ],
                0.5,
            )

        text = output.getvalue()
        self.assertIn("path: clip1.mp4", text)
        self.assertIn("resolution: 320x240", text)
        self.assertIn("fps: 30 fps", text)
        self.assertIn("audio: no", text)
        self.assertIn("total source duration: 4s", text)
        self.assertIn("estimated composed duration: 3.5s", text)


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
        self.assertIn("libx264", command)
        self.assertIn("8000k", command)
        self.assertEqual(command[-1], "output.mp4")

    def test_build_ffmpeg_command_accepts_custom_encoder(self) -> None:
        command = build_ffmpeg_command(
            [Path("clip1.mp4"), Path("clip2.mp4")],
            Path("output.mp4"),
            "[0:v][1:v]xfade=transition=fade:duration=0.5:offset=9.5[v1]",
            "[v1]",
            "hevc_videotoolbox",
            "12000k",
        )

        self.assertIn("hevc_videotoolbox", command)
        self.assertIn("12000k", command)

    def test_build_ffmpeg_command_with_music_replace(self) -> None:
        command = build_ffmpeg_command(
            [Path("clip1.mp4"), Path("clip2.mp4")],
            Path("output.mp4"),
            "[0:v][1:v]xfade=transition=fade:duration=0.5:offset=9.5[v1]",
            "[v1]",
            music=Path("song.mp3"),
            music_volume=0.7,
            output_duration=17.5,
        )
        filter_complex = command[command.index("-filter_complex") + 1]

        self.assertIn("song.mp3", command)
        self.assertIn("-map", command)
        self.assertIn("[a_music]", command)
        self.assertIn("[2:a]volume=0.7[a_music]", filter_complex)
        self.assertIn("-c:a", command)
        self.assertIn("aac", command)
        self.assertIn("-b:a", command)
        self.assertIn("192k", command)
        self.assertIn("-t", command)
        self.assertIn("17.5", command)
        self.assertNotIn("-shortest", command)
        self.assertNotIn("-an", command)

    def test_build_ffmpeg_command_without_music_keeps_video_only_output(self) -> None:
        command = build_ffmpeg_command(
            [Path("clip1.mp4"), Path("clip2.mp4")],
            Path("output.mp4"),
            "[0:v][1:v]xfade=transition=fade:duration=0.5:offset=9.5[v1]",
            "[v1]",
        )

        self.assertIn("-an", command)
        self.assertNotIn("-c:a", command)


if __name__ == "__main__":
    unittest.main()
