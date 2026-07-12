import subprocess
import tempfile
import unittest
import xml.etree.ElementTree as ET
import wave
from unittest.mock import patch
from pathlib import Path

from VocaVid.assembly import assemble_kdenlive_project, assemble_video, split_audio_segment


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
                f"file '{clip_a.as_posix()}'\nfile '{clip_b.as_posix()}'\n",
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
            self.assertEqual(main_entries[0].attrib["out"], "00:00:04.500")
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
            self.assertEqual(transitions[0].attrib["out"], "00:00:04.500")

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

    def test_assemble_kdenlive_project_reverts_only_visually_descending_transitions(self):
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
            self.assertEqual(transition_properties[0]["reverse"], "1")
            self.assertEqual(transition_properties[1]["a_track"], "2")
            self.assertEqual(transition_properties[1]["b_track"], "3")
            self.assertEqual(transition_properties[1]["reverse"], "0")

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


def _write_wav(path: Path, duration_sec: float) -> None:
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(1000)
        handle.writeframes(b"\x00\x00" * int(1000 * duration_sec))
