import subprocess
import tempfile
import unittest
import xml.etree.ElementTree as ET
import wave
from unittest.mock import patch
from pathlib import Path

from VocaVid.assembly import assemble_kdenlive_project, assemble_video, render_kdenlive_project, render_kdenlive_project_command, split_audio_segment


class AssemblyTests(unittest.TestCase):
    def test_assemble_video_writes_concat_list_and_invokes_ffmpeg(self):
        with tempfile.TemporaryDirectory() as directory:
            tmp_path = Path(directory)
            clip_a = tmp_path / "a.mp4"
            clip_b = tmp_path / "b.mp4"
            audio = tmp_path / "song.wav"
            output = tmp_path / "final.mp4"
            clip_a.write_text("a", encoding="utf-8")
            clip_b.write_text("b", encoding="utf-8")
            audio.write_text("wav", encoding="utf-8")
            calls = []

            def fake_run(command, check, capture_output, text):
                calls.append(command)
                output.write_text("video", encoding="utf-8")
                return subprocess.CompletedProcess(command, 0, "", "")

            result = assemble_video([clip_a, clip_b], audio, output, runner=fake_run)

            concat_file = tmp_path / "final.concat.txt"
            self.assertEqual(result, output)
            self.assertEqual(
                concat_file.read_text(encoding="utf-8"),
                f"file '{clip_a.resolve().as_posix()}'\nfile '{clip_b.resolve().as_posix()}'\n",
            )
            self.assertTrue(calls[0][0].endswith("ffmpeg.exe") or calls[0][0] == "ffmpeg")
            self.assertEqual(calls[0][1:4], ["-y", "-f", "concat"])
            self.assertIn(str(audio), calls[0])
            self.assertIn(str(output), calls[0])

    def test_split_audio_segment_invokes_ffmpeg_with_segment_bounds(self):
        with tempfile.TemporaryDirectory() as directory:
            tmp_path = Path(directory)
            audio = tmp_path / "song.wav"
            output = tmp_path / "segment.wav"
            audio.write_text("wav", encoding="utf-8")
            calls = []

            def fake_run(command, check, capture_output, text):
                calls.append(command)
                output.write_text("clip", encoding="utf-8")
                return subprocess.CompletedProcess(command, 0, "", "")

            result = split_audio_segment(audio, start_sec=35.0, end_sec=42.5, output_path=output, runner=fake_run)

            self.assertEqual(result, output)
            self.assertTrue(calls[0][0].endswith("ffmpeg.exe") or calls[0][0] == "ffmpeg")
            self.assertEqual(calls[0][1:6], ["-y", "-ss", "35.000", "-to", "42.500"])
            self.assertIn(str(audio), calls[0])
            self.assertIn(str(output), calls[0])

    def test_render_kdenlive_project_invokes_melt_with_mp4_consumer(self):
        with tempfile.TemporaryDirectory() as directory:
            tmp_path = Path(directory)
            project = tmp_path / "final.kdenlive"
            output = tmp_path / "finished.mp4"
            project.write_text(
                '<mlt producer="main_bin"><tractor id="tractor7"><property name="kdenlive:projectTractor">1</property></tractor></mlt>',
                encoding="utf-8",
            )
            calls = []
            render_producers = []

            def fake_run(command, check, capture_output, text, cwd=None):
                render_producers.append(ET.parse(command[2]).getroot().attrib.get("producer"))
                calls.append((command, check, capture_output, text, cwd))
                output.write_bytes(b"mp4")
                return subprocess.CompletedProcess(command, 0, "", "")

            with patch.dict("os.environ", {"MELT_BINARY": "C:/tools/melt.exe"}):
                result = render_kdenlive_project(project, output, runner=fake_run)

            self.assertEqual(result, output)
            command, check, capture_output, text, cwd = calls[0]
            self.assertEqual(command[0], "C:/tools/melt.exe")
            self.assertEqual(command[1], "-silent")
            self.assertNotEqual(command[2], str(project))
            self.assertEqual(Path(command[2]).parent, project.parent)
            self.assertEqual(command[3], "-consumer")
            self.assertEqual(command[4], f"avformat:{output.resolve()}")
            self.assertIn("vcodec=libx264", command)
            self.assertIn("acodec=aac", command)
            self.assertFalse(check)
            self.assertTrue(capture_output)
            self.assertTrue(text)
            self.assertEqual(cwd, project.parent)
            self.assertEqual(render_producers, ["tractor7"])
            self.assertFalse(Path(command[2]).exists())

    def test_render_kdenlive_project_command_uses_detected_melt_binary(self):
        with patch.dict("os.environ", {"MELT_BINARY": "C:/tools/melt.exe"}):
            command = render_kdenlive_project_command(Path("final.kdenlive"), Path("finished.mp4"))

        self.assertEqual(command[0], "C:/tools/melt.exe")
        self.assertEqual(command[1], "-silent")
        self.assertEqual(command[3], "-consumer")
        self.assertEqual(command[4], f"avformat:{Path('finished.mp4').resolve()}")

    def test_render_kdenlive_project_rejects_unsafe_melt_binary_override(self):
        with patch.dict("os.environ", {"MELT_BINARY": "-consumer"}):
            with self.assertRaises(ValueError):
                render_kdenlive_project_command(Path("final.kdenlive"), Path("finished.mp4"))

    def test_split_audio_segment_uses_ffmpeg_binary_env_override(self):
        with tempfile.TemporaryDirectory() as directory:
            tmp_path = Path(directory)
            audio = tmp_path / "song.wav"
            output = tmp_path / "segment.wav"
            audio.write_text("wav", encoding="utf-8")
            calls = []

            def fake_run(command, check, capture_output, text):
                calls.append(command)
                output.write_text("clip", encoding="utf-8")
                return subprocess.CompletedProcess(command, 0, "", "")

            with patch.dict("os.environ", {"FFMPEG_BINARY": "C:/tools/ffmpeg.exe"}):
                split_audio_segment(audio, start_sec=0, end_sec=1, output_path=output, runner=fake_run)

            self.assertEqual(calls[0][0], "C:/tools/ffmpeg.exe")

    def test_split_audio_segment_rejects_unsafe_ffmpeg_binary_override(self):
        with tempfile.TemporaryDirectory() as directory:
            tmp_path = Path(directory)
            audio = tmp_path / "song.wav"
            output = tmp_path / "segment.wav"
            audio.write_text("wav", encoding="utf-8")

            with patch.dict("os.environ", {"FFMPEG_BINARY": "-i"}):
                with self.assertRaises(ValueError):
                    split_audio_segment(audio, start_sec=0, end_sec=1, output_path=output)

    def test_split_audio_segment_rejects_source_outside_allowed_root(self):
        with tempfile.TemporaryDirectory() as source_directory, tempfile.TemporaryDirectory() as other_directory:
            source_root = Path(source_directory)
            other_root = Path(other_directory)
            audio = other_root / "song.wav"
            output = source_root / "segment.wav"
            audio.write_text("wav", encoding="utf-8")

            with self.assertRaises(ValueError):
                split_audio_segment(
                    audio,
                    start_sec=0,
                    end_sec=1,
                    output_path=output,
                    source_root=source_root,
                    output_root=source_root,
                )

    def test_split_audio_segment_rejects_output_outside_allowed_root(self):
        with tempfile.TemporaryDirectory() as source_directory, tempfile.TemporaryDirectory() as other_directory:
            source_root = Path(source_directory)
            other_root = Path(other_directory)
            audio = source_root / "song.wav"
            output = other_root / "segment.wav"
            audio.write_text("wav", encoding="utf-8")

            with self.assertRaises(ValueError):
                split_audio_segment(
                    audio,
                    start_sec=0,
                    end_sec=1,
                    output_path=output,
                    source_root=source_root,
                    output_root=source_root,
                )

    def test_split_audio_segment_falls_back_to_python_wav_when_ffmpeg_is_missing(self):
        with tempfile.TemporaryDirectory() as directory:
            tmp_path = Path(directory)
            audio = tmp_path / "song.wav"
            output = tmp_path / "segment.wav"
            _write_wav(audio, duration_sec=2.0)

            def missing_ffmpeg(command, check, capture_output, text):
                raise FileNotFoundError(command[0])

            result = split_audio_segment(audio, start_sec=0.5, end_sec=1.5, output_path=output, runner=missing_ffmpeg)

            self.assertEqual(result, output)
            with wave.open(str(output), "rb") as handle:
                self.assertEqual(handle.getnchannels(), 1)
                self.assertEqual(handle.getframerate(), 1000)
                self.assertEqual(handle.getnframes(), 1000)

    def test_assemble_kdenlive_project_places_clip_handles_as_overlapping_transitions(self):
        with tempfile.TemporaryDirectory() as directory:
            tmp_path = Path(directory)
            clip_a = tmp_path / "a.mp4"
            clip_b = tmp_path / "b.mp4"
            audio = tmp_path / "song.wav"
            template = tmp_path / "template.kdenlive"
            output = tmp_path / "final.kdenlive"
            clip_a.write_text("a", encoding="utf-8")
            clip_b.write_text("b", encoding="utf-8")
            audio.write_text("wav", encoding="utf-8")
            template.write_text(
                """<?xml version='1.0' encoding='utf-8'?>
<mlt producer="main_bin">
 <profile frame_rate_num="25" frame_rate_den="1" width="1920" height="1080"/>
 <producer id="producer0"><property name="resource">black</property></producer>
 <playlist id="playlist2"/>
 <playlist id="playlist10"/>
 <playlist id="playlist12"/>
 <tractor id="{sequence}">
  <track producer="producer0"/>
  <track producer="playlist2"/>
  <track producer="playlist10"/>
  <track producer="playlist12"/>
 </tractor>
 <playlist id="main_bin"/>
 <tractor id="tractor7"><track producer="{sequence}"/></tractor>
</mlt>
""",
                encoding="utf-8",
            )

            result = assemble_kdenlive_project(
                [
                    {"path": clip_a, "start_sec": 0.0, "end_sec": 4.0},
                    {"path": clip_b, "start_sec": 4.0, "end_sec": 7.0},
                ],
                audio,
                output,
                template,
                transition_handle_seconds=0.5,
            )

            self.assertEqual(result, output)
            root = ET.parse(output).getroot()
            resources = [
                prop.text
                for producer in root.findall("producer")
                for prop in producer.findall("property")
                if prop.attrib.get("name") == "resource"
            ]
            self.assertIn("a.mp4", resources)
            self.assertIn("b.mp4", resources)
            self.assertIn("song.wav", resources)

            main_entries = root.find(".//playlist[@id='playlist10']").findall("entry")
            overlay_entries = list(root.find(".//playlist[@id='playlist12']"))
            audio_entries = root.find(".//playlist[@id='playlist2']").findall("entry")
            self.assertEqual(audio_entries[0].attrib["out"], "00:00:07.000")
            self.assertEqual(main_entries[0].attrib["producer"], "clip0")
            self.assertEqual(main_entries[0].attrib["in"], "00:00:00.000")
            self.assertEqual(main_entries[0].attrib["out"], "00:00:04.480")
            self.assertEqual(len(main_entries), 1)
            self.assertEqual(overlay_entries[0].tag, "blank")
            self.assertEqual(overlay_entries[0].attrib["length"], "00:00:04.000")
            self.assertEqual(overlay_entries[1].attrib["producer"], "clip1")
            self.assertEqual(overlay_entries[1].attrib["in"], "00:00:00.000")
            self.assertEqual(overlay_entries[1].attrib["out"], "00:00:03.000")
            sequence = root.find(".//tractor[@id='{sequence}']")
            self.assertEqual(sequence.attrib["out"], "00:00:07.000")

            transitions = [
                transition
                for transition in root.findall(".//transition")
                if any(prop.text == "luma" for prop in transition.findall("property") if prop.attrib.get("name") == "mlt_service")
            ]
            self.assertEqual(len(transitions), 1)
            self.assertEqual(transitions[0].attrib["in"], "00:00:04.000")
            self.assertEqual(transitions[0].attrib["out"], "00:00:04.440")
            static_video_transitions = [
                transition
                for transition in root.findall(".//transition")
                if any(prop.text == "qtblend" for prop in transition.findall("property") if prop.attrib.get("name") == "mlt_service")
            ]
            self.assertEqual(static_video_transitions, [])

    def test_assemble_kdenlive_project_preserves_tiny_timing_gaps_and_shortens_transition(self):
        with tempfile.TemporaryDirectory() as directory:
            tmp_path = Path(directory)
            clip_a = tmp_path / "a.mp4"
            clip_b = tmp_path / "b.mp4"
            audio = tmp_path / "song.wav"
            template = tmp_path / "template.kdenlive"
            output = tmp_path / "final.kdenlive"
            clip_a.write_text("a", encoding="utf-8")
            clip_b.write_text("b", encoding="utf-8")
            audio.write_text("wav", encoding="utf-8")
            template.write_text(
                """<?xml version='1.0' encoding='utf-8'?>
<mlt producer="main_bin">
 <profile frame_rate_num="25" frame_rate_den="1" width="1920" height="1080"/>
 <producer id="producer0"><property name="resource">black</property></producer>
 <playlist id="playlist2"/>
 <playlist id="playlist10"/>
 <playlist id="playlist12"/>
 <tractor id="{sequence}">
  <track producer="producer0"/>
  <track producer="playlist2"/>
  <track producer="playlist10"/>
  <track producer="playlist12"/>
 </tractor>
 <playlist id="main_bin"/>
 <tractor id="tractor7"><track producer="{sequence}"/></tractor>
</mlt>
""",
                encoding="utf-8",
            )

            assemble_kdenlive_project(
                [
                    {"path": clip_a, "start_sec": 0.0, "end_sec": 4.0},
                    {"path": clip_b, "start_sec": 4.012, "end_sec": 7.012},
                ],
                audio,
                output,
                template,
                transition_handle_seconds=0.5,
            )

            root = ET.parse(output).getroot()
            overlay_items = list(root.find(".//playlist[@id='playlist12']"))
            self.assertEqual(overlay_items[0].tag, "blank")
            self.assertEqual(overlay_items[0].attrib["length"], "00:00:04.000")
            transition = next(
                transition
                for transition in root.findall(".//transition")
                if any(prop.text == "luma" for prop in transition.findall("property") if prop.attrib.get("name") == "mlt_service")
            )
            self.assertEqual(transition.attrib["in"], "00:00:04.000")
            self.assertEqual(transition.attrib["out"], "00:00:04.440")

    def test_assemble_kdenlive_project_adds_transitions_to_nested_video_tracks(self):
        with tempfile.TemporaryDirectory() as directory:
            tmp_path = Path(directory)
            clip_a = tmp_path / "a.mp4"
            clip_b = tmp_path / "b.mp4"
            audio = tmp_path / "song.wav"
            template = tmp_path / "template.kdenlive"
            output = tmp_path / "final.kdenlive"
            clip_a.write_text("a", encoding="utf-8")
            clip_b.write_text("b", encoding="utf-8")
            audio.write_text("wav", encoding="utf-8")
            template.write_text(
                """<?xml version='1.0' encoding='utf-8'?>
<mlt producer="main_bin">
 <profile frame_rate_num="25" frame_rate_den="1" width="1920" height="1080"/>
 <producer id="producer0"><property name="resource">black</property></producer>
 <playlist id="playlist2"/>
 <playlist id="playlist10"/>
 <playlist id="playlist12"/>
 <tractor id="tractor5"><track producer="playlist10"/></tractor>
 <tractor id="tractor6"><track producer="playlist12"/></tractor>
 <tractor id="{sequence}">
  <track producer="producer0"/>
  <track producer="playlist2"/>
  <track producer="tractor5"/>
  <track producer="tractor6"/>
 </tractor>
 <playlist id="main_bin"/>
 <tractor id="tractor7"><track producer="{sequence}"/></tractor>
</mlt>
""",
                encoding="utf-8",
            )

            assemble_kdenlive_project(
                [
                    {"path": clip_a, "start_sec": 0.0, "end_sec": 4.0},
                    {"path": clip_b, "start_sec": 4.0, "end_sec": 7.0},
                ],
                audio,
                output,
                template,
                transition_handle_seconds=0.5,
            )

            root = ET.parse(output).getroot()
            sequence = root.find(".//tractor[@id='{sequence}']")
            transitions = [
                transition
                for transition in sequence.findall("transition")
                if any(prop.text == "luma" for prop in transition.findall("property") if prop.attrib.get("name") == "mlt_service")
            ]

            self.assertEqual(len(transitions), 1)
            properties = {
                prop.attrib.get("name"): prop.text
                for prop in transitions[0].findall("property")
            }
            self.assertEqual(properties["a_track"], "2")
            self.assertEqual(properties["b_track"], "3")

    def test_assemble_kdenlive_project_reverses_only_upper_to_lower_transitions(self):
        with tempfile.TemporaryDirectory() as directory:
            tmp_path = Path(directory)
            clips_dir = tmp_path / "media" / "clips"
            output_dir = tmp_path / "exports" / "demo"
            clips_dir.mkdir(parents=True)
            clip_a = clips_dir / "a.mp4"
            clip_b = clips_dir / "b.mp4"
            clip_c = clips_dir / "c.mp4"
            audio = tmp_path / "media" / "song.wav"
            template = tmp_path / "template.kdenlive"
            output = output_dir / "final.kdenlive"
            for path in (clip_a, clip_b, clip_c, audio):
                path.write_text(path.name, encoding="utf-8")
            template.write_text(
                """<?xml version='1.0' encoding='utf-8'?>
<mlt producer="main_bin">
 <profile frame_rate_num="25" frame_rate_den="1" width="1920" height="1080"/>
 <producer id="producer0"><property name="resource">black</property></producer>
 <playlist id="playlist2"/>
 <playlist id="playlist10"/>
 <playlist id="playlist12"/>
 <tractor id="tractor5"><track producer="playlist10"/></tractor>
 <tractor id="tractor6"><track producer="playlist12"/></tractor>
 <tractor id="{sequence}">
  <track producer="producer0"/>
  <track producer="playlist2"/>
  <track producer="tractor5"/>
  <track producer="tractor6"/>
 </tractor>
 <playlist id="main_bin"/>
 <tractor id="tractor7"><track producer="{sequence}"/></tractor>
</mlt>
""",
                encoding="utf-8",
            )

            assemble_kdenlive_project(
                [
                    {"path": clip_a, "start_sec": 0.0, "end_sec": 4.0},
                    {"path": clip_b, "start_sec": 4.0, "end_sec": 7.0},
                    {"path": clip_c, "start_sec": 7.0, "end_sec": 10.0},
                ],
                audio,
                output,
                template,
                transition_handle_seconds=0.5,
            )

            sequence = ET.parse(output).getroot().find(".//tractor[@id='{sequence}']")
            transitions = [
                transition
                for transition in sequence.findall("transition")
                if any(prop.text == "luma" for prop in transition.findall("property") if prop.attrib.get("name") == "mlt_service")
            ]

            transition_properties = [
                {prop.attrib.get("name"): prop.text for prop in transition.findall("property")}
                for transition in transitions
            ]
            self.assertEqual(len(transition_properties), 2)
            self.assertEqual(transition_properties[0]["a_track"], "2")
            self.assertEqual(transition_properties[0]["b_track"], "3")
            self.assertEqual(transition_properties[0]["reverse"], "0")
            self.assertEqual(transition_properties[1]["a_track"], "2")
            self.assertEqual(transition_properties[1]["b_track"], "3")
            self.assertEqual(transition_properties[1]["reverse"], "1")

    def test_assemble_kdenlive_project_writes_relative_resource_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            tmp_path = Path(directory)
            media_dir = tmp_path / "media"
            output_dir = tmp_path / "outputs" / "demo"
            media_dir.mkdir()
            clip = media_dir / "a.mp4"
            audio = media_dir / "song.wav"
            template = tmp_path / "template.kdenlive"
            output = output_dir / "final.kdenlive"
            clip.write_text("a", encoding="utf-8")
            audio.write_text("wav", encoding="utf-8")
            template.write_text(
                """<?xml version='1.0' encoding='utf-8'?>
<mlt producer="main_bin" root="/absolute/template/path">
 <profile frame_rate_num="25" frame_rate_den="1" width="1920" height="1080"/>
 <producer id="producer0"><property name="resource">black</property></producer>
 <playlist id="playlist2"/>
 <playlist id="playlist10"/>
 <playlist id="playlist12"/>
 <tractor id="{sequence}">
  <track producer="producer0"/>
  <track producer="playlist2"/>
  <track producer="playlist10"/>
  <track producer="playlist12"/>
 </tractor>
 <playlist id="main_bin"/>
 <tractor id="tractor7"><track producer="{sequence}"/></tractor>
</mlt>
""",
                encoding="utf-8",
            )

            assemble_kdenlive_project(
                [{"path": clip, "start_sec": 0.0, "end_sec": 4.0}],
                audio,
                output,
                template,
                transition_handle_seconds=0.5,
            )

            root = ET.parse(output).getroot()
            resources = [
                prop.text
                for producer in root.findall("producer")
                for prop in producer.findall("property")
                if prop.attrib.get("name") == "resource" and prop.text != "black"
            ]
            self.assertEqual(root.attrib["root"], ".")
            self.assertEqual(resources, ["../../media/song.wav", "../../media/a.mp4"])

    def test_assemble_kdenlive_project_stores_relative_render_target(self):
        with tempfile.TemporaryDirectory() as directory:
            tmp_path = Path(directory)
            media_dir = tmp_path / "media"
            output_dir = tmp_path / "outputs" / "demo"
            media_dir.mkdir()
            clip = media_dir / "a.mp4"
            audio = media_dir / "song.wav"
            template = tmp_path / "template.kdenlive"
            output = output_dir / "final.kdenlive"
            render_target = output_dir / "finished.mp4"
            clip.write_text("a", encoding="utf-8")
            audio.write_text("wav", encoding="utf-8")
            template.write_text(
                """<?xml version='1.0' encoding='utf-8'?>
<mlt producer="main_bin">
 <profile frame_rate_num="25" frame_rate_den="1" width="1920" height="1080"/>
 <producer id="producer0"><property name="resource">black</property></producer>
 <playlist id="playlist2"/>
 <playlist id="playlist10"/>
 <playlist id="playlist12"/>
 <tractor id="{sequence}">
  <track producer="producer0"/>
  <track producer="playlist2"/>
  <track producer="playlist10"/>
  <track producer="playlist12"/>
 </tractor>
 <playlist id="main_bin"/>
 <tractor id="tractor7"><track producer="{sequence}"/></tractor>
</mlt>
""",
                encoding="utf-8",
            )

            assemble_kdenlive_project(
                [{"path": clip, "start_sec": 0.0, "end_sec": 4.0}],
                audio,
                output,
                template,
                transition_handle_seconds=0.5,
                render_target_path=render_target,
            )

            main_bin = ET.parse(output).getroot().find(".//playlist[@id='main_bin']")
            properties = {prop.attrib.get("name"): prop.text for prop in main_bin.findall("property")}
            self.assertEqual(properties["kdenlive:docproperties.renderurl"], "finished.mp4")
            self.assertEqual(properties["kdenlive:docproperties.renderpath"], "finished.mp4")


def _write_wav(path: Path, duration_sec: float) -> None:
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(1000)
        handle.writeframes(b"\x00\x00" * int(1000 * duration_sec))
