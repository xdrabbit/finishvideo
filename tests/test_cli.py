from pathlib import Path
from contextlib import redirect_stderr, redirect_stdout
import io
import sys
import unittest
from argparse import Namespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

from finishvideo.audio import AudioInfo, extract_bpm_from_tags, parse_audio_probe_json
from finishvideo.cli import parse_args
from finishvideo.formatting import (
    ffmpeg_number,
    print_analyze,
    print_analyze_music,
    print_dry_run,
)
from finishvideo.plan import build_render_plan, resolve_bpm
from finishvideo.probe import ClipInfo, parse_fps, parse_probe_json
from finishvideo.render import apply_slowmo_filter, build_ffmpeg_command, build_xfade_filter
from finishvideo.timeline import (
    TransitionOffset,
    build_beat_grid,
    compute_output_duration,
    compute_transition_offsets,
    estimate_composed_duration,
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

    def test_build_beat_grid_with_offset(self) -> None:
        self.assertEqual(build_beat_grid(120, 4, 0.1), [0.1, 0.6, 1.1, 1.6])


class RenderBpmTests(unittest.TestCase):
    def test_numeric_bpm_still_parses(self) -> None:
        args = parse_args(["--beat-sync", "--bpm", "124", "clip1.mp4", "clip2.mp4", "out.mp4"])

        self.assertEqual(args.bpm, 124.0)

    def test_metadata_bpm_parses_case_insensitively(self) -> None:
        args = parse_args(
            [
                "--beat-sync",
                "--bpm",
                "Metadata",
                "--music",
                "song.mp3",
                "clip1.mp4",
                "clip2.mp4",
                "out.mp4",
            ]
        )

        self.assertEqual(args.bpm, "metadata")

    def test_metadata_bpm_requires_music(self) -> None:
        stderr = io.StringIO()

        with redirect_stderr(stderr), self.assertRaises(SystemExit) as error:
            parse_args(["--beat-sync", "--bpm", "metadata", "clip1.mp4", "clip2.mp4", "out.mp4"])

        self.assertNotEqual(error.exception.code, 0)
        self.assertIn("--bpm metadata requires --music", stderr.getvalue())

    def test_metadata_bpm_resolves_from_audio_info(self) -> None:
        resolution = resolve_bpm(
            Namespace(beat_sync=True, bpm="metadata", music=Path("song.mp3")),
            AudioInfo(
                path=Path("song.mp3"),
                duration=10.0,
                codec="mp3",
                sample_rate=44100,
                channels=2,
                bitrate=None,
                tags={"BPM": "124"},
                metadata_bpm=124.0,
            ),
        )

        self.assertEqual(resolution.bpm, 124.0)
        self.assertEqual(resolution.source, "metadata")

    def test_missing_metadata_bpm_errors_clearly(self) -> None:
        with self.assertRaises(SystemExit) as error:
            resolve_bpm(
                Namespace(beat_sync=True, bpm="metadata", music=Path("song.mp3")),
                AudioInfo(
                    path=Path("song.mp3"),
                    duration=10.0,
                    codec="mp3",
                    sample_rate=44100,
                    channels=2,
                    bitrate=None,
                    tags={},
                    metadata_bpm=None,
                ),
            )

        self.assertIn("usable metadata BPM", str(error.exception))
        self.assertIn("missing, invalid, or ambiguous", str(error.exception))

    def test_dry_run_includes_bpm_source_when_beat_sync_is_active(self) -> None:
        output = io.StringIO()

        with redirect_stdout(output):
            print_dry_run(
                [Path("clip1.mp4"), Path("clip2.mp4")],
                [2.0, 2.0],
                None,
                "fade",
                0.5,
                [TransitionOffset(index=1, before_beat_sync=1.5, after_beat_sync=1.5)],
                True,
                120.0,
                "metadata",
                0.0,
                1.0,
                1.0,
                60.0,
                3.5,
                ["ffmpeg", "-i", "clip1.mp4", "out.mp4"],
            )

        self.assertIn("bpm: 120", output.getvalue())
        self.assertIn("bpm source: metadata", output.getvalue())


class SlowmoParserTests(unittest.TestCase):
    def test_slowmo_options_parse(self) -> None:
        args = parse_args(
            [
                "--slowmo",
                "2",
                "--slowmo-fps",
                "60",
                "clip1.mp4",
                "clip2.mp4",
                "out.mp4",
            ]
        )

        self.assertEqual(args.slowmo, 2.0)
        self.assertEqual(args.slowmo_fps, 60.0)

    def test_slowmo_rejects_less_than_one(self) -> None:
        stderr = io.StringIO()

        with redirect_stderr(stderr), self.assertRaises(SystemExit) as error:
            parse_args(["--slowmo", "0.5", "clip1.mp4", "clip2.mp4", "out.mp4"])

        self.assertNotEqual(error.exception.code, 0)
        self.assertIn("--slowmo must be greater than or equal to 1.0", stderr.getvalue())

    def test_slowmo_fps_rejects_zero_or_negative(self) -> None:
        for fps in ("0", "-1"):
            with self.subTest(fps=fps):
                stderr = io.StringIO()

                with redirect_stderr(stderr), self.assertRaises(SystemExit) as error:
                    parse_args(
                        [
                            "--slowmo-fps",
                            fps,
                            "clip1.mp4",
                            "clip2.mp4",
                            "out.mp4",
                        ]
                    )

                self.assertNotEqual(error.exception.code, 0)
                self.assertIn("--slowmo-fps must be greater than 0", stderr.getvalue())


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


class AnalyzeMusicTests(unittest.TestCase):
    def test_extract_bpm_from_tags_reads_common_spellings(self) -> None:
        self.assertEqual(extract_bpm_from_tags({"BPM": "124"}), 124.0)
        self.assertEqual(extract_bpm_from_tags({"TBPM": "124.0"}), 124.0)
        self.assertEqual(extract_bpm_from_tags({"tempo": "124 BPM"}), 124.0)
        self.assertEqual(extract_bpm_from_tags({"initialbpm": "124"}), 124.0)
        self.assertEqual(extract_bpm_from_tags({"bpm": "124"}), 124.0)

    def test_extract_bpm_from_tags_rejects_invalid_or_ambiguous_values(self) -> None:
        self.assertIsNone(extract_bpm_from_tags({}))
        self.assertIsNone(extract_bpm_from_tags({"BPM": "0"}))
        self.assertIsNone(extract_bpm_from_tags({"BPM": "-124"}))
        self.assertIsNone(extract_bpm_from_tags({"BPM": "124-126"}))
        self.assertIsNone(extract_bpm_from_tags({"BPM": "124/125"}))
        self.assertIsNone(extract_bpm_from_tags({"BPM": "124", "TBPM": "125"}))

    def test_parse_audio_probe_json_reads_audio_metadata(self) -> None:
        audio = parse_audio_probe_json(
            Path("song.mp3"),
            {
                "format": {
                    "duration": "12.500000",
                    "bit_rate": "192000",
                    "tags": {"title": "Demo", "BPM": "124"},
                },
                "streams": [
                    {
                        "codec_type": "audio",
                        "codec_name": "mp3",
                        "sample_rate": "44100",
                        "channels": 2,
                        "tags": {"TBPM": "124", "initialkey": "8A"},
                    },
                ],
            },
        )

        self.assertEqual(audio.path, Path("song.mp3"))
        self.assertEqual(audio.duration, 12.5)
        self.assertEqual(audio.codec, "mp3")
        self.assertEqual(audio.sample_rate, 44100)
        self.assertEqual(audio.channels, 2)
        self.assertEqual(audio.bitrate, 192000)
        self.assertEqual(audio.tags["BPM"], "124")
        self.assertEqual(audio.tags["TBPM"], "124")
        self.assertEqual(audio.tags["initialkey"], "8A")
        self.assertEqual(audio.metadata_bpm, 124.0)

    def test_parse_audio_probe_json_uses_stream_duration_and_bitrate_first(self) -> None:
        audio = parse_audio_probe_json(
            Path("song.m4a"),
            {
                "format": {"duration": "12.500000", "bit_rate": "128000"},
                "streams": [
                    {
                        "codec_type": "audio",
                        "duration": "10.000000",
                        "bit_rate": "96000",
                    },
                ],
            },
        )

        self.assertEqual(audio.duration, 10.0)
        self.assertEqual(audio.bitrate, 96000)

    def test_parse_audio_probe_json_errors_without_audio_stream(self) -> None:
        with self.assertRaises(SystemExit) as error:
            parse_audio_probe_json(
                Path("clip.mp4"),
                {"format": {"duration": "2.0"}, "streams": [{"codec_type": "video"}]},
            )

        self.assertIn("no audio stream found", str(error.exception))

    def test_print_analyze_music_formats_metadata(self) -> None:
        output = io.StringIO()

        with redirect_stdout(output):
            print_analyze_music(
                AudioInfo(
                    path=Path("song.mp3"),
                    duration=12.5,
                    codec="mp3",
                    sample_rate=44100,
                    channels=2,
                    bitrate=192000,
                    tags={"BPM": "124", "initialkey": "8A"},
                )
            )

        text = output.getvalue()
        self.assertIn("path: song.mp3", text)
        self.assertIn("duration: 12.5s", text)
        self.assertIn("codec: mp3", text)
        self.assertIn("sample rate: 44100", text)
        self.assertIn("channels: 2", text)
        self.assertIn("bitrate: 192000", text)
        self.assertIn("metadata bpm: unknown", text)
        self.assertIn("BPM: 124", text)
        self.assertIn("initialkey: 8A", text)

    def test_print_analyze_music_formats_metadata_bpm_and_preview(self) -> None:
        output = io.StringIO()

        with redirect_stdout(output):
            print_analyze_music(
                AudioInfo(
                    path=Path("song.mp3"),
                    duration=12.5,
                    codec="mp3",
                    sample_rate=44100,
                    channels=2,
                    bitrate=None,
                    tags={"BPM": "120"},
                    metadata_bpm=120.0,
                ),
                build_beat_grid(120, 3, 0.1),
                120,
                0.1,
            )

        text = output.getvalue()
        self.assertIn("metadata bpm: 120", text)
        self.assertIn("Beat grid preview:", text)
        self.assertIn("beat interval: 0.5s", text)
        self.assertIn("beat count: 3", text)
        self.assertIn("beat offset: 0.1s", text)
        self.assertIn("1: 0.1s", text)
        self.assertIn("2: 0.6s", text)
        self.assertIn("3: 1.1s", text)


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

    def test_apply_slowmo_filter_appends_interpolation_stage(self) -> None:
        filter_complex, final_video = apply_slowmo_filter(
            "[0:v][1:v]xfade=transition=fade:duration=0.5:offset=9.5[v1]",
            "[v1]",
            2.0,
            60.0,
        )

        self.assertEqual(final_video, "[vslow]")
        self.assertIn("[v1]setpts=2*PTS", filter_complex)
        self.assertIn("minterpolate=fps=60", filter_complex)
        self.assertTrue(filter_complex.endswith("me_mode=bidir[vslow]"))

    def test_apply_slowmo_filter_leaves_normal_speed_unchanged(self) -> None:
        original = "[0:v][1:v]xfade=transition=fade:duration=0.5:offset=9.5[v1]"

        filter_complex, final_video = apply_slowmo_filter(original, "[v1]", 1.0, 60.0)

        self.assertEqual(filter_complex, original)
        self.assertEqual(final_video, "[v1]")

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


class RenderPlanTests(unittest.TestCase):
    def test_build_render_plan_collects_render_intent(self) -> None:
        args = Namespace(
            music=None,
            beat_sync=True,
            bpm=120.0,
            duration=0.5,
            transition="fade",
            beat_offset=0.0,
            video_codec="libx264",
            video_bitrate="8000k",
            music_volume=1.0,
            slowmo=1.0,
            slowmo_fps=60.0,
        )

        durations = {Path("clip1.mp4"): 2.0, Path("clip2.mp4"): 2.0}

        with patch("finishvideo.plan.probe_duration", side_effect=durations.__getitem__):
            plan = build_render_plan(
                args,
                [Path("clip1.mp4"), Path("clip2.mp4")],
                Path("out.mp4"),
            )

        self.assertEqual(plan.clips, [Path("clip1.mp4"), Path("clip2.mp4")])
        self.assertEqual(plan.output, Path("out.mp4"))
        self.assertEqual(plan.durations, [2.0, 2.0])
        self.assertEqual(plan.bpm, 120.0)
        self.assertEqual(plan.bpm_source, "manual")
        self.assertEqual(plan.output_duration, 3.5)
        self.assertEqual(plan.final_video, "[v1]")
        self.assertEqual(
            plan.filter_complex,
            "[0:v][1:v]xfade=transition=fade:duration=0.5:offset=1.5[v1]",
        )
        command_filter = plan.command[plan.command.index("-filter_complex") + 1]
        self.assertEqual(command_filter, plan.filter_complex)
        self.assertNotIn("minterpolate", command_filter)
        self.assertEqual(plan.command[plan.command.index("-map") + 1], "[v1]")
        self.assertEqual(plan.command[-1], "out.mp4")

    def test_build_render_plan_multiplies_duration_for_slowmo(self) -> None:
        args = Namespace(
            music=None,
            beat_sync=False,
            bpm=None,
            duration=0.5,
            transition="fade",
            beat_offset=0.0,
            video_codec="libx264",
            video_bitrate="8000k",
            music_volume=1.0,
            slowmo=2.0,
            slowmo_fps=60.0,
        )

        durations = {Path("clip1.mp4"): 2.0, Path("clip2.mp4"): 2.0}

        with patch("finishvideo.plan.probe_duration", side_effect=durations.__getitem__):
            plan = build_render_plan(
                args,
                [Path("clip1.mp4"), Path("clip2.mp4")],
                Path("out.mp4"),
            )

        self.assertEqual(plan.output_duration, 7.0)
        self.assertEqual(plan.final_video, "[vslow]")
        self.assertIn("setpts=2*PTS", plan.filter_complex)


if __name__ == "__main__":
    unittest.main()
