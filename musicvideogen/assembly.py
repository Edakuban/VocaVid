from __future__ import annotations

import subprocess
import os
import shutil
import wave
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Callable, Sequence


Runner = Callable[..., subprocess.CompletedProcess[str]]


def assemble_video(
    clip_paths: Sequence[Path],
    audio_path: Path,
    output_path: Path,
    runner: Runner = subprocess.run,
) -> Path:
    if not clip_paths:
        raise ValueError("At least one clip is required")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    concat_path = output_path.with_suffix(".concat.txt")
    concat_path.write_text("".join(f"file '{clip.as_posix()}'\n" for clip in clip_paths), encoding="utf-8")

    command = [
        _ffmpeg_binary(),
        "-y",
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        str(concat_path),
        "-i",
        str(audio_path),
        "-c:v",
        "copy",
        "-c:a",
        "aac",
        "-shortest",
        str(output_path),
    ]
    runner(command, check=True, capture_output=True, text=True)
    return output_path


def assemble_kdenlive_project(
    clips: Sequence[dict[str, Any]],
    audio_path: Path,
    output_path: Path,
    template_path: Path,
    transition_handle_seconds: float,
) -> Path:
    if not clips:
        raise ValueError("At least one clip is required")
    if not template_path.exists():
        raise FileNotFoundError(f"Kdenlive template not found: {template_path}")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    tree = ET.parse(template_path)
    root = tree.getroot()
    root.set("root", str(output_path.parent).replace("\\", "/"))

    sequence = _find_sequence_tractor(root)
    main_playlist = _require_playlist(root, "playlist10")
    overlay_playlist = _require_playlist(root, "playlist12")
    audio_playlist = _require_playlist(root, "playlist2")
    main_bin = _require_playlist(root, "main_bin")
    _clear_playlist_timeline(main_playlist)
    _clear_playlist_timeline(overlay_playlist)
    _clear_playlist_timeline(audio_playlist)
    _remove_generated_project_items(root)

    fps = _profile_fps(root)
    handle = max(0.0, float(transition_handle_seconds))
    total_duration = max(float(clip["end_sec"]) for clip in clips)

    audio_producer = _producer("audio0", audio_path, total_duration, playlist_id="main_bin")
    root.insert(_producer_insert_index(root), audio_producer)
    ET.SubElement(audio_playlist, "entry", {"producer": "audio0", "in": _timecode(0), "out": _timecode(total_duration)})
    _add_bin_entry(main_bin, "audio0", total_duration)

    for index, clip in enumerate(clips):
        visible_duration = max(0.0, float(clip["end_sec"]) - float(clip["start_sec"]))
        entry_duration = visible_duration + handle if index < len(clips) - 1 else visible_duration
        producer_id = f"clip{index}"
        clip_path = Path(clip["path"])
        root.insert(_producer_insert_index(root), _producer(producer_id, clip_path, entry_duration, playlist_id="main_bin"))
        target_playlist = main_playlist if index % 2 == 0 else overlay_playlist
        _append_blank_until(target_playlist, float(clip["start_sec"]))
        ET.SubElement(target_playlist, "entry", {"producer": producer_id, "in": _timecode(0), "out": _timecode(entry_duration)})
        _add_bin_entry(main_bin, producer_id, entry_duration)

    for index, clip in enumerate(clips[:-1]):
        start = float(clip["end_sec"])
        from_playlist = "playlist10" if index % 2 == 0 else "playlist12"
        to_playlist = "playlist10" if (index + 1) % 2 == 0 else "playlist12"
        _add_transition(sequence, index, start, min(start + handle, total_duration), root, from_playlist, to_playlist)

    sequence.set("out", _timecode(total_duration))
    _set_property(sequence, "kdenlive:duration", _timecode(total_duration))
    project_tractor = root.find(".//tractor[@id='tractor7']")
    if project_tractor is not None:
        project_tractor.set("out", _timecode(total_duration))
        for track in project_tractor.findall("track"):
            track.set("out", _timecode(total_duration))

    ET.indent(tree, space=" ")
    tree.write(output_path, encoding="utf-8", xml_declaration=True)
    return output_path


def split_audio_segment(
    audio_path: Path,
    start_sec: float,
    end_sec: float,
    output_path: Path,
    runner: Runner = subprocess.run,
) -> Path:
    if end_sec <= start_sec:
        raise ValueError("Audio segment end must be after start")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    command = [
        _ffmpeg_binary(),
        "-y",
        "-ss",
        f"{start_sec:.3f}",
        "-to",
        f"{end_sec:.3f}",
        "-i",
        str(audio_path),
        "-vn",
        "-acodec",
        "pcm_s16le",
        str(output_path),
    ]
    try:
        runner(command, check=True, capture_output=True, text=True)
    except FileNotFoundError:
        _split_wav_segment(audio_path, start_sec, end_sec, output_path)
    return output_path


def _split_wav_segment(audio_path: Path, start_sec: float, end_sec: float, output_path: Path) -> None:
    with wave.open(str(audio_path), "rb") as source:
        frame_rate = source.getframerate()
        start_frame = max(0, int(round(float(start_sec) * frame_rate)))
        end_frame = max(start_frame, int(round(float(end_sec) * frame_rate)))
        source.setpos(min(start_frame, source.getnframes()))
        frames = source.readframes(max(0, min(end_frame, source.getnframes()) - start_frame))
        with wave.open(str(output_path), "wb") as target:
            target.setnchannels(source.getnchannels())
            target.setsampwidth(source.getsampwidth())
            target.setframerate(frame_rate)
            target.writeframes(frames)


def _find_sequence_tractor(root: ET.Element) -> ET.Element:
    for tractor in root.findall("tractor"):
        track_producers = [track.attrib.get("producer") for track in tractor.findall("track")]
        if "playlist10" in track_producers and "playlist12" in track_producers:
            return tractor
    main_track = _playlist_track_producer(root, "playlist10")
    overlay_track = _playlist_track_producer(root, "playlist12")
    if main_track and overlay_track:
        for tractor in root.findall("tractor"):
            track_producers = [track.attrib.get("producer") for track in tractor.findall("track")]
            if main_track in track_producers and overlay_track in track_producers:
                return tractor
    for tractor in root.findall("tractor"):
        if tractor.attrib.get("id") != "tractor7":
            return tractor
    raise ValueError("Kdenlive template has no sequence tractor")


def _require_playlist(root: ET.Element, playlist_id: str) -> ET.Element:
    playlist = root.find(f".//playlist[@id='{playlist_id}']")
    if playlist is None:
        raise ValueError(f"Kdenlive template is missing playlist {playlist_id}")
    return playlist


def _clear_playlist_timeline(playlist: ET.Element) -> None:
    for child in list(playlist):
        if child.tag in {"entry", "blank"}:
            playlist.remove(child)


def _remove_generated_project_items(root: ET.Element) -> None:
    for child in list(root):
        if child.tag == "producer" and (child.attrib.get("id", "").startswith("clip") or child.attrib.get("id") == "audio0"):
            root.remove(child)
    for tractor in root.findall("tractor"):
        for child in list(tractor):
            if child.tag == "transition" and child.attrib.get("id", "").startswith("auto_transition"):
                tractor.remove(child)


def _producer(producer_id: str, resource: Path, duration: float, playlist_id: str) -> ET.Element:
    producer = ET.Element("producer", {"id": producer_id, "in": _timecode(0), "out": _timecode(duration)})
    _set_property(producer, "length", _timecode(duration))
    _set_property(producer, "eof", "pause")
    _set_property(producer, "resource", str(resource))
    _set_property(producer, "mlt_service", "avformat")
    _set_property(producer, "kdenlive:playlistid", playlist_id)
    return producer


def _producer_insert_index(root: ET.Element) -> int:
    for index, child in enumerate(list(root)):
        if child.tag in {"playlist", "tractor"}:
            return index
    return len(root)


def _add_bin_entry(main_bin: ET.Element, producer_id: str, duration: float) -> None:
    ET.SubElement(main_bin, "entry", {"producer": producer_id, "in": _timecode(0), "out": _timecode(duration)})


def _append_blank_until(playlist: ET.Element, target_start: float) -> None:
    current = _playlist_duration(playlist)
    gap = target_start - current
    if gap > 0.0005:
        ET.SubElement(playlist, "blank", {"length": _timecode(gap)})


def _playlist_duration(playlist: ET.Element) -> float:
    duration = 0.0
    for child in playlist:
        if child.tag == "blank":
            duration += _parse_timecode(child.attrib.get("length", "0"))
        elif child.tag == "entry":
            duration += _parse_timecode(child.attrib.get("out", "0")) - _parse_timecode(child.attrib.get("in", "0"))
    return duration


def _add_transition(
    sequence: ET.Element,
    index: int,
    start: float,
    end: float,
    root: ET.Element,
    from_playlist: str,
    to_playlist: str,
) -> None:
    track_indices = {track.attrib.get("producer"): position for position, track in enumerate(sequence.findall("track"))}
    from_track = _sequence_track_producer_for_playlist(root, sequence, from_playlist)
    to_track = _sequence_track_producer_for_playlist(root, sequence, to_playlist)
    transition = ET.SubElement(sequence, "transition", {"id": f"auto_transition{index}", "in": _timecode(start), "out": _timecode(end)})
    _set_property(transition, "a_track", str(track_indices.get(from_track, 0)))
    _set_property(transition, "b_track", str(track_indices.get(to_track, 0)))
    _set_property(transition, "mlt_service", "luma")
    _set_property(transition, "kdenlive_id", "wipe")
    _set_property(transition, "reverse", "1")
    _set_property(transition, "softness", "0")
    _set_property(transition, "progressive", "1")
    _set_property(transition, "always_active", "0")


def _sequence_track_producer_for_playlist(root: ET.Element, sequence: ET.Element, playlist_id: str) -> str:
    track_producers = {track.attrib.get("producer") for track in sequence.findall("track")}
    if playlist_id in track_producers:
        return playlist_id
    nested_track = _playlist_track_producer(root, playlist_id)
    if nested_track in track_producers:
        return nested_track
    return playlist_id


def _playlist_track_producer(root: ET.Element, playlist_id: str) -> str | None:
    for tractor in root.findall("tractor"):
        if any(track.attrib.get("producer") == playlist_id for track in tractor.findall("track")):
            return tractor.attrib.get("id")
    return None


def _set_property(parent: ET.Element, name: str, value: object) -> None:
    prop = None
    for child in parent.findall("property"):
        if child.attrib.get("name") == name:
            prop = child
            break
    if prop is None:
        prop = ET.SubElement(parent, "property", {"name": name})
    prop.text = str(value)


def _profile_fps(root: ET.Element) -> float:
    profile = root.find("profile")
    if profile is None:
        return 25.0
    numerator = float(profile.attrib.get("frame_rate_num", 25))
    denominator = float(profile.attrib.get("frame_rate_den", 1))
    return numerator / denominator if denominator else 25.0


def _timecode(seconds: float) -> str:
    milliseconds = max(0, int(round(float(seconds) * 1000)))
    hours, remainder = divmod(milliseconds, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    secs, millis = divmod(remainder, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}.{millis:03d}"


def _parse_timecode(value: str) -> float:
    raw = str(value or "0")
    if ":" not in raw:
        return float(raw)
    hours, minutes, seconds = raw.split(":")
    return (int(hours) * 3600) + (int(minutes) * 60) + float(seconds)


def _ffmpeg_binary() -> str:
    if os.environ.get("FFMPEG_BINARY"):
        return os.environ["FFMPEG_BINARY"]
    if shutil.which("ffmpeg"):
        return "ffmpeg"
    bundled = Path(r"C:\tmp\Dione\apps\Applio\applio\ffmpeg.exe")
    if bundled.exists():
        return str(bundled)
    return "ffmpeg"
