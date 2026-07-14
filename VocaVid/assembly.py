from __future__ import annotations

import subprocess
import os
import shutil
import tempfile
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
    render_target_path: Path | None = None,
) -> Path:
    if not clips:
        raise ValueError("At least one clip is required")
    if not template_path.exists():
        raise FileNotFoundError(f"Kdenlive template not found: {template_path}")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    tree = ET.parse(template_path)
    root = tree.getroot()
    root.set("root", ".")

    sequence = _find_sequence_tractor(root)
    main_playlist = _require_playlist(root, "playlist10")
    overlay_playlist = _require_playlist(root, "playlist12")
    audio_playlist = _require_playlist(root, "playlist2")
    main_bin = _require_playlist(root, "main_bin")
    _clear_playlist_timeline(main_playlist)
    _clear_playlist_timeline(overlay_playlist)
    _clear_playlist_timeline(audio_playlist)
    _remove_generated_project_items(root)
    _prune_to_used_tracks(root)

    fps = _profile_fps(root)
    handle = max(0.0, float(transition_handle_seconds))
    timeline_clips = _clip_timings(clips, fps)
    transition_durations = _transition_durations(timeline_clips, handle, fps)
    total_duration = max(float(clip["timeline_end_sec"]) for clip in timeline_clips)
    total_frames = max(int(clip["timeline_end_frame"]) for clip in timeline_clips)

    audio_producer = _producer("audio0", audio_path, total_duration, playlist_id="main_bin", base_path=output_path.parent)
    root.insert(_producer_insert_index(root), audio_producer)
    ET.SubElement(audio_playlist, "entry", {"producer": "audio0", "in": _timecode(0), "out": _timecode(total_duration)})
    _add_bin_entry(main_bin, "audio0", total_duration)
    if render_target_path is not None:
        _set_render_target(main_bin, render_target_path, output_path.parent)

    for index, clip in enumerate(timeline_clips):
        visible_frames = max(1, int(clip["timeline_end_frame"]) - int(clip["timeline_start_frame"]))
        outgoing_handle_frames = transition_durations[index] if index < len(transition_durations) else 0
        entry_frames = visible_frames + outgoing_handle_frames
        producer_id = f"clip{index}"
        clip_path = Path(clip["path"])
        root.insert(
            _producer_insert_index(root),
            _producer(
                producer_id,
                clip_path,
                _frames_to_seconds(entry_frames, fps),
                playlist_id="main_bin",
                base_path=output_path.parent,
            ),
        )
        target_playlist = main_playlist if index % 2 == 0 else overlay_playlist
        _append_blank_until(target_playlist, _frames_to_seconds(int(clip["timeline_start_frame"]), fps))
        ET.SubElement(target_playlist, "entry", {"producer": producer_id, "in": _timecode(0), "out": _frame_timecode(entry_frames, fps)})
        _add_bin_entry(main_bin, producer_id, _frames_to_seconds(entry_frames, fps))

    for index, clip in enumerate(timeline_clips[:-1]):
        next_clip = timeline_clips[index + 1]
        transition_frames = transition_durations[index]
        start_frame = max(int(clip["timeline_end_frame"]), int(next_clip["timeline_start_frame"]))
        end_frame = min(
            int(clip["timeline_end_frame"]) + transition_frames,
            int(next_clip["timeline_start_frame"]) + transition_frames,
            total_frames,
        )
        from_playlist = "playlist10" if index % 2 == 0 else "playlist12"
        to_playlist = "playlist10" if (index + 1) % 2 == 0 else "playlist12"
        _add_transition(sequence, index, start_frame, end_frame, root, from_playlist, to_playlist, fps)

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


def render_kdenlive_project(
    project_path: Path,
    output_path: Path,
    runner: Runner = subprocess.run,
) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    render_project_path = _write_melt_render_project(project_path)
    try:
        command = render_kdenlive_project_command(render_project_path, output_path)
        result = runner(command, check=False, capture_output=True, text=True, cwd=project_path.parent)
        if result.returncode != 0:
            message = (result.stderr or result.stdout or "Kdenlive render failed").strip()
            raise RuntimeError(message)
    finally:
        render_project_path.unlink(missing_ok=True)
    return output_path


def render_kdenlive_project_command(project_path: Path, output_path: Path) -> list[str]:
    return [
        _melt_binary(),
        "-silent",
        str(project_path),
        "-consumer",
        f"avformat:{output_path}",
        "f=mp4",
        "vcodec=libx264",
        "acodec=aac",
        "pix_fmt=yuv420p",
        "crf=18",
        "preset=medium",
        "movflags=+faststart",
        "real_time=-1",
    ]


def _write_melt_render_project(project_path: Path) -> Path:
    tree = ET.parse(project_path)
    root = tree.getroot()
    project_tractor = next(
        (
            tractor
            for tractor in root.findall("tractor")
            if _property_value(tractor, "kdenlive:projectTractor") == "1"
        ),
        None,
    )
    if project_tractor is None:
        project_tractor = root.find(".//tractor[@id='tractor7']") or _find_sequence_tractor(root)
    producer_id = project_tractor.attrib.get("id")
    if producer_id:
        root.set("producer", producer_id)
    handle = tempfile.NamedTemporaryFile(
        mode="wb",
        suffix=".kdenlive",
        prefix=f"{project_path.stem}.render-",
        dir=project_path.parent,
        delete=False,
    )
    render_path = Path(handle.name)
    with handle:
        tree.write(handle, encoding="utf-8", xml_declaration=True)
    return render_path


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
    audio_arg = _command_path_arg(audio_path)
    output_arg = _command_path_arg(output_path)
    command = [
        _ffmpeg_binary(),
        "-y",
        "-ss",
        f"{start_sec:.3f}",
        "-to",
        f"{end_sec:.3f}",
        "-i",
        audio_arg,
        "-vn",
        "-acodec",
        "pcm_s16le",
        output_arg,
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


def _prune_to_used_tracks(root: ET.Element) -> None:
    tractor_ids = {tractor.attrib.get("id", "") for tractor in root.findall("tractor")}
    if not {"tractor1", "tractor5", "tractor6"}.issubset(tractor_ids):
        return
    sequence = _find_sequence_tractor(root)
    used_playlist_ids = {"playlist2", "playlist3", "playlist10", "playlist11", "playlist12", "playlist13"}
    used_tractor_ids = {"tractor1", "tractor5", "tractor6"}
    for child in list(root):
        child_id = child.attrib.get("id", "")
        if child.tag == "playlist" and child_id.startswith("playlist") and child_id not in used_playlist_ids:
            root.remove(child)
        elif child.tag == "tractor" and child_id.startswith("tractor") and child_id not in used_tractor_ids and child_id != "tractor7":
            root.remove(child)

    wanted_tracks = ["producer0", "tractor1", "tractor5", "tractor6"]
    for child in list(sequence):
        if child.tag == "track" and child.attrib.get("producer") not in wanted_tracks:
            sequence.remove(child)
        elif child.tag == "transition" and not child.attrib.get("id", "").startswith("auto_transition"):
            sequence.remove(child)
    existing_tracks = {track.attrib.get("producer") for track in sequence.findall("track")}
    insert_at = 0
    for producer in wanted_tracks:
        if producer not in existing_tracks:
            sequence.insert(insert_at, ET.Element("track", {"producer": producer}))
        insert_at += 1
    _set_property(sequence, "kdenlive:sequenceproperties.tracksCount", "3")
    _set_property(sequence, "kdenlive:sequenceproperties.tracks", "3")
    _set_property(sequence, "kdenlive:sequenceproperties.audioTarget", "1")
    _set_property(sequence, "kdenlive:sequenceproperties.videoTarget", "2")
    _add_static_transition(sequence, "transition0", 0, 1, "mix")


def _add_static_transition(sequence: ET.Element, transition_id: str, a_track: int, b_track: int, service: str) -> None:
    transition = ET.SubElement(sequence, "transition", {"id": transition_id})
    _set_property(transition, "a_track", str(a_track))
    _set_property(transition, "b_track", str(b_track))
    _set_property(transition, "mlt_service", service)
    _set_property(transition, "kdenlive_id", service)
    _set_property(transition, "internal_added", "237")
    _set_property(transition, "always_active", "1")
    if service == "mix":
        _set_property(transition, "accepts_blanks", "1")
        _set_property(transition, "sum", "1")
    else:
        _set_property(transition, "compositing", "0")
        _set_property(transition, "distort", "0")
        _set_property(transition, "rotate_center", "0")


def _producer(producer_id: str, resource: Path, duration: float, playlist_id: str, base_path: Path) -> ET.Element:
    producer = ET.Element("producer", {"id": producer_id, "in": _timecode(0), "out": _timecode(duration)})
    _set_property(producer, "length", _timecode(duration))
    _set_property(producer, "eof", "pause")
    _set_property(producer, "resource", _relative_resource(resource, base_path))
    _set_property(producer, "mlt_service", "avformat")
    _set_property(producer, "kdenlive:playlistid", playlist_id)
    return producer


def _relative_resource(resource: Path, base_path: Path) -> str:
    return os.path.relpath(str(resource), str(base_path)).replace("\\", "/")


def _producer_insert_index(root: ET.Element) -> int:
    for index, child in enumerate(list(root)):
        if child.tag in {"playlist", "tractor"}:
            return index
    return len(root)


def _add_bin_entry(main_bin: ET.Element, producer_id: str, duration: float) -> None:
    ET.SubElement(main_bin, "entry", {"producer": producer_id, "in": _timecode(0), "out": _timecode(duration)})


def _set_render_target(main_bin: ET.Element, render_target_path: Path, base_path: Path) -> None:
    render_target = _relative_resource(render_target_path, base_path)
    _set_property(main_bin, "kdenlive:docproperties.renderurl", render_target)
    _set_property(main_bin, "kdenlive:docproperties.renderpath", render_target)


def _clip_timings(clips: Sequence[dict[str, Any]], fps: float) -> list[dict[str, Any]]:
    timed = []
    for clip in clips:
        start = float(clip["start_sec"])
        end = float(clip["end_sec"])
        if end < start:
            end = start
        start_frame = _seconds_to_frame(start, fps)
        end_frame = max(start_frame + 1, _seconds_to_frame(end, fps))
        updated = dict(clip)
        updated["source_start_sec"] = start
        updated["source_end_sec"] = end
        updated["timeline_start_frame"] = start_frame
        updated["timeline_end_frame"] = end_frame
        updated["timeline_start_sec"] = _frames_to_seconds(start_frame, fps)
        updated["timeline_end_sec"] = _frames_to_seconds(end_frame, fps)
        timed.append(updated)
    return timed


def _transition_durations(clips: Sequence[dict[str, Any]], handle: float, fps: float) -> list[int]:
    durations = []
    handle_frames = _duration_to_frames(handle, fps)
    for current, next_clip in zip(clips, clips[1:]):
        current_frames = max(1, int(current["timeline_end_frame"]) - int(current["timeline_start_frame"]))
        next_frames = max(1, int(next_clip["timeline_end_frame"]) - int(next_clip["timeline_start_frame"]))
        durations.append(max(0, min(handle_frames, current_frames // 2, next_frames // 2)))
    return durations


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
    start_frame: int,
    end_frame: int,
    root: ET.Element,
    from_playlist: str,
    to_playlist: str,
    fps: float,
) -> None:
    track_indices = {track.attrib.get("producer"): position for position, track in enumerate(sequence.findall("track"))}
    from_track = _sequence_track_producer_for_playlist(root, sequence, from_playlist)
    to_track = _sequence_track_producer_for_playlist(root, sequence, to_playlist)
    from_position = track_indices.get(from_track, 0)
    to_position = track_indices.get(to_track, 0)
    if end_frame - start_frame <= 1:
        return
    transition = ET.SubElement(
        sequence,
        "transition",
        {"id": f"auto_transition{index}", "in": _frame_timecode(start_frame, fps), "out": _frame_timecode(end_frame - 1, fps)},
    )
    _set_property(transition, "a_track", str(min(from_position, to_position)))
    _set_property(transition, "b_track", str(max(from_position, to_position)))
    _set_property(transition, "mlt_service", "luma")
    _set_property(transition, "kdenlive_id", "wipe")
    _set_property(transition, "reverse", "1" if from_position > to_position else "0")
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


def _property_value(parent: ET.Element, name: str) -> str:
    prop = next((child for child in parent.findall("property") if child.attrib.get("name") == name), None)
    return "" if prop is None or prop.text is None else prop.text


def _profile_fps(root: ET.Element) -> float:
    profile = root.find("profile")
    if profile is None:
        return 25.0
    numerator = float(profile.attrib.get("frame_rate_num", 25))
    denominator = float(profile.attrib.get("frame_rate_den", 1))
    return numerator / denominator if denominator else 25.0


def _seconds_to_frame(seconds: float, fps: float) -> int:
    frame_rate = fps if fps > 0 else 25.0
    return max(0, int(float(seconds) * frame_rate + 0.5))


def _duration_to_frames(seconds: float, fps: float) -> int:
    frame_rate = fps if fps > 0 else 25.0
    frames = int(float(seconds) * frame_rate + 1e-9)
    return max(1, frames) if seconds > 0 else 0


def _frames_to_seconds(frames: int, fps: float) -> float:
    frame_rate = fps if fps > 0 else 25.0
    return max(0, int(frames)) / frame_rate


def _frame_timecode(frames: int, fps: float) -> str:
    return _timecode(_frames_to_seconds(frames, fps))


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


def _command_path_arg(path: Path) -> str:
    return str(path.resolve(strict=False))


def _melt_binary() -> str:
    if os.environ.get("MELT_BINARY"):
        return os.environ["MELT_BINARY"]
    if shutil.which("melt"):
        return "melt"
    for candidate in (
        Path(r"C:\Program Files\Kdenlive\bin\melt.exe"),
        Path(r"C:\Program Files\kdenlive\bin\melt.exe"),
    ):
        if candidate.exists():
            return str(candidate)
    return "melt"
