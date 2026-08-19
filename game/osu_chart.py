import csv
import math
import os
import re
from dataclasses import dataclass


class OsuChartError(ValueError):
    pass


class UnsupportedOsuChartError(OsuChartError):
    pass


@dataclass(frozen=True)
class ChartNote:
    time: float
    lane: int
    end_time: float = None
    x: float = 256.0


@dataclass(frozen=True)
class OsuManiaChart:
    path: str
    folder: str
    format_version: int
    title: str
    artist: str
    creator: str
    difficulty: str
    overall_difficulty: float
    hp_drain_rate: float
    audio_path: str
    audio_lead_in: int
    notes: tuple
    mode: int = 3
    circle_size: float = 2.0
    preview_time: int = -1
    background_path: str = None
    video_path: str = None
    video_start_time: int = 0

    @property
    def level(self):
        return max(1, round(self.overall_difficulty))

    @property
    def duration(self):
        if not self.notes:
            return 0.0
        return max(note.end_time or note.time for note in self.notes)


def _read_sections(path):
    with open(path, "r", encoding="utf-8-sig", errors="replace") as file:
        lines = file.read().splitlines()
    if not lines:
        raise OsuChartError("empty osu chart")
    match = re.fullmatch(r"osu file format v(\d+)", lines[0].strip(), re.IGNORECASE)
    if match is None:
        raise OsuChartError("invalid osu file format header")
    sections = {}
    supported_sections = {"General", "Metadata", "Difficulty", "Events", "TimingPoints", "HitObjects"}
    section = None
    for raw_line in lines[1:]:
        line = raw_line.strip()
        if not line or line.startswith("//"):
            continue
        if line.startswith("[") and line.endswith("]"):
            name = line[1:-1]
            section = name if name in supported_sections else None
            if section is not None:
                sections.setdefault(section, [])
            continue
        if section is not None:
            sections[section].append(line)
    return int(match.group(1)), sections


def _key_values(lines):
    values = {}
    for line in lines:
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        values[key.strip()] = value.strip()
    return values


def _chart_asset_path(folder, filename):
    filename = filename.strip().strip('"')
    if not filename:
        return None
    path = os.path.abspath(os.path.join(folder, filename))
    try:
        inside_folder = os.path.commonpath((folder, path)) == folder
    except ValueError:
        inside_folder = False
    return path if inside_folder and os.path.isfile(path) else None


def _chart_media(folder, event_lines):
    background_path = None
    video_path = None
    video_start_time = 0
    for line in event_lines:
        try:
            parts = next(csv.reader((line,), skipinitialspace=True))
        except csv.Error:
            continue
        if len(parts) < 3:
            continue
        event_type = parts[0].strip().casefold()
        if event_type in ("0", "background") and background_path is None:
            background_path = _chart_asset_path(folder, parts[2])
        elif event_type in ("1", "video") and video_path is None:
            video_path = _chart_asset_path(folder, parts[2])
            try:
                video_start_time = max(0, round(float(parts[1])))
            except ValueError:
                video_start_time = 0
    return background_path, video_path, video_start_time


def _slider_span_duration(note_time_ms, pixel_length, slider_multiplier, timing_lines):
    beat_length = 500.0
    slider_velocity = 1.0
    for line in timing_lines:
        parts = line.split(",")
        if len(parts) < 2:
            continue
        try:
            timing_time = float(parts[0])
            timing_beat_length = float(parts[1])
        except ValueError:
            continue
        if timing_time > note_time_ms:
            break
        if timing_beat_length > 0:
            beat_length = timing_beat_length
            slider_velocity = 1.0
        elif timing_beat_length < 0:
            slider_velocity = max(0.1, min(10.0, -100.0 / timing_beat_length))
    velocity = max(0.01, slider_multiplier * 100.0 * slider_velocity)
    return max(0.08, beat_length * pixel_length / velocity / 1000.0)


def parse_osu_mania_2k(path):
    format_version, sections = _read_sections(path)
    general = _key_values(sections.get("General", ()))
    metadata = _key_values(sections.get("Metadata", ()))
    difficulty = _key_values(sections.get("Difficulty", ()))
    try:
        mode = int(general.get("Mode", "0"))
        key_count = float(difficulty.get("CircleSize", "0"))
    except ValueError as error:
        raise OsuChartError(f"invalid mode or circle size: {path}") from error
    if mode != 3:
        raise UnsupportedOsuChartError(f"not an osu!mania chart: {path}")
    if key_count != 2.0:
        raise UnsupportedOsuChartError(f"only 2K charts are supported: {path}")
    notes = []
    for line in sections.get("HitObjects", ()):
        parts = line.split(",")
        if len(parts) < 5:
            continue
        try:
            x = int(parts[0])
            note_time = int(parts[2]) / 1000.0
            note_type = int(parts[3])
        except ValueError as error:
            raise OsuChartError(f"invalid hit object: {line}") from error
        if not note_type & 1 and not note_type & 128:
            continue
        lane = max(0, min(1, math.floor(x * 2 / 512)))
        end_time = None
        if note_type & 128 and len(parts) > 5:
            try:
                end_time = int(parts[5].split(":", 1)[0]) / 1000.0
            except ValueError as error:
                raise OsuChartError(f"invalid hold note: {line}") from error
        notes.append(ChartNote(note_time, lane, end_time, x))
    if not notes:
        raise OsuChartError(f"chart has no playable notes: {path}")
    notes.sort(key=lambda note: (note.time, note.lane))
    folder = os.path.dirname(os.path.abspath(path))
    audio_filename = general.get("AudioFilename", "").strip()
    if not audio_filename:
        raise OsuChartError(f"chart has no AudioFilename: {path}")
    audio_path = os.path.abspath(os.path.join(folder, audio_filename))
    try:
        audio_inside_folder = os.path.commonpath((folder, audio_path)) == folder
    except ValueError:
        audio_inside_folder = False
    if not audio_inside_folder:
        raise OsuChartError(f"chart audio escapes its folder: {path}")
    if not os.path.isfile(audio_path):
        raise OsuChartError(f"chart audio does not exist: {audio_path}")
    try:
        overall_difficulty = float(difficulty.get("OverallDifficulty", "1"))
        hp_drain_rate = float(difficulty.get("HPDrainRate", "5"))
        audio_lead_in = int(general.get("AudioLeadIn", "0"))
        preview_time = int(general.get("PreviewTime", "-1"))
    except ValueError as error:
        raise OsuChartError(f"invalid chart difficulty settings: {path}") from error
    background_path, video_path, video_start_time = _chart_media(folder, sections.get("Events", ()))
    return OsuManiaChart(
        path=os.path.abspath(path),
        folder=folder,
        format_version=format_version,
        title=metadata.get("TitleUnicode") or metadata.get("Title") or os.path.basename(folder),
        artist=metadata.get("ArtistUnicode") or metadata.get("Artist") or "UNKNOWN ARTIST",
        creator=metadata.get("Creator", "UNKNOWN"),
        difficulty=metadata.get("Version", "2K"),
        overall_difficulty=overall_difficulty,
        hp_drain_rate=hp_drain_rate,
        audio_path=audio_path,
        audio_lead_in=max(0, audio_lead_in),
        notes=tuple(notes),
        preview_time=preview_time,
        background_path=background_path,
        video_path=video_path,
        video_start_time=video_start_time,
    )


def parse_osu_catch(path):
    format_version, sections = _read_sections(path)
    general = _key_values(sections.get("General", ()))
    metadata = _key_values(sections.get("Metadata", ()))
    difficulty = _key_values(sections.get("Difficulty", ()))
    try:
        mode = int(general.get("Mode", "0"))
        circle_size = float(difficulty.get("CircleSize", "5"))
        slider_multiplier = float(difficulty.get("SliderMultiplier", "1.4"))
    except ValueError as error:
        raise OsuChartError(f"invalid mode or circle size: {path}") from error
    if mode != 2:
        raise UnsupportedOsuChartError(f"not an osu!catch chart: {path}")
    notes = []
    for line in sections.get("HitObjects", ()):
        parts = line.split(",")
        if len(parts) < 5:
            continue
        try:
            x = max(0, min(512, int(parts[0])))
            note_time = int(parts[2]) / 1000.0
            note_type = int(parts[3])
        except ValueError as error:
            raise OsuChartError(f"invalid hit object: {line}") from error
        if note_type & 1:
            notes.append(ChartNote(note_time, 0, None, x))
        elif note_type & 2:
            notes.append(ChartNote(note_time, 0, None, x))
            if len(parts) > 7:
                try:
                    repeat_count = max(1, int(parts[6]))
                    pixel_length = max(0.0, float(parts[7]))
                except ValueError as error:
                    raise OsuChartError(f"invalid slider: {line}") from error
                control_points = parts[5].split("|")
                endpoint_x = x
                if len(control_points) > 1 and ":" in control_points[-1]:
                    try:
                        endpoint_x = max(0, min(512, int(control_points[-1].split(":", 1)[0])))
                    except ValueError as error:
                        raise OsuChartError(f"invalid slider endpoint: {line}") from error
                duration = _slider_span_duration(
                    note_time * 1000.0, pixel_length, slider_multiplier, sections.get("TimingPoints", ()),
                )
                for repeat in range(1, repeat_count + 1):
                    repeat_x = endpoint_x if repeat % 2 else x
                    notes.append(ChartNote(note_time + duration * repeat, 0, None, repeat_x))
        elif note_type & 8:
            continue
    if not notes:
        raise OsuChartError(f"chart has no playable catch objects: {path}")
    notes.sort(key=lambda note: (note.time, note.x))
    folder = os.path.dirname(os.path.abspath(path))
    audio_filename = general.get("AudioFilename", "").strip()
    if not audio_filename:
        raise OsuChartError(f"chart has no AudioFilename: {path}")
    audio_path = os.path.abspath(os.path.join(folder, audio_filename))
    try:
        audio_inside_folder = os.path.commonpath((folder, audio_path)) == folder
    except ValueError:
        audio_inside_folder = False
    if not audio_inside_folder:
        raise OsuChartError(f"chart audio escapes its folder: {path}")
    if not os.path.isfile(audio_path):
        raise OsuChartError(f"chart audio does not exist: {audio_path}")
    try:
        overall_difficulty = float(difficulty.get("OverallDifficulty", "1"))
        hp_drain_rate = float(difficulty.get("HPDrainRate", "5"))
        audio_lead_in = int(general.get("AudioLeadIn", "0"))
        preview_time = int(general.get("PreviewTime", "-1"))
    except ValueError as error:
        raise OsuChartError(f"invalid chart difficulty settings: {path}") from error
    background_path, video_path, video_start_time = _chart_media(folder, sections.get("Events", ()))
    return OsuManiaChart(
        path=os.path.abspath(path),
        folder=folder,
        format_version=format_version,
        title=metadata.get("TitleUnicode") or metadata.get("Title") or os.path.basename(folder),
        artist=metadata.get("ArtistUnicode") or metadata.get("Artist") or "UNKNOWN ARTIST",
        creator=metadata.get("Creator", "UNKNOWN"),
        difficulty=metadata.get("Version", "CATCH"),
        overall_difficulty=overall_difficulty,
        hp_drain_rate=hp_drain_rate,
        audio_path=audio_path,
        audio_lead_in=max(0, audio_lead_in),
        notes=tuple(notes),
        mode=2,
        circle_size=circle_size,
        preview_time=preview_time,
        background_path=background_path,
        video_path=video_path,
        video_start_time=video_start_time,
    )


def discover_osu_mania_2k(charts_root, folder_names=()):
    charts_root = os.path.abspath(charts_root)
    allowed = {name.casefold() for name in folder_names if name}
    charts = []
    rejected = []
    if not os.path.isdir(charts_root):
        return (), ()
    for directory, directories, files in os.walk(charts_root):
        directories.sort()
        files.sort()
        relative = os.path.relpath(directory, charts_root)
        top_folder = relative.split(os.sep, 1)[0] if relative != "." else ""
        if allowed and top_folder and top_folder.casefold() not in allowed:
            directories[:] = []
            continue
        for filename in files:
            if not filename.casefold().endswith(".osu"):
                continue
            path = os.path.join(directory, filename)
            try:
                charts.append(parse_osu_mania_2k(path))
            except OsuChartError as error:
                rejected.append((path, str(error)))
    charts.sort(key=lambda chart: (os.path.relpath(chart.folder, charts_root).casefold(), chart.difficulty.casefold()))
    return tuple(charts), tuple(rejected)


def discover_osu_supported(charts_root, folder_names=()):
    charts_root = os.path.abspath(charts_root)
    allowed = {name.casefold() for name in folder_names if name}
    charts = {"2k": [], "catch": []}
    rejected = []
    if not os.path.isdir(charts_root):
        return {key: () for key in charts}, ()
    for directory, directories, files in os.walk(charts_root):
        directories.sort()
        files.sort()
        relative = os.path.relpath(directory, charts_root)
        top_folder = relative.split(os.sep, 1)[0] if relative != "." else ""
        if allowed and top_folder and top_folder.casefold() not in allowed:
            directories[:] = []
            continue
        for filename in files:
            if not filename.casefold().endswith(".osu"):
                continue
            path = os.path.join(directory, filename)
            try:
                _, sections = _read_sections(path)
                general = _key_values(sections.get("General", ()))
                mode = int(general.get("Mode", "0"))
                if mode == 2:
                    charts["catch"].append(parse_osu_catch(path))
                elif mode == 3:
                    charts["2k"].append(parse_osu_mania_2k(path))
            except OsuChartError as error:
                rejected.append((path, str(error)))
            except ValueError:
                rejected.append((path, f"invalid game mode: {path}"))
    for mode_charts in charts.values():
        mode_charts.sort(
            key=lambda chart: (os.path.relpath(chart.folder, charts_root).casefold(), chart.difficulty.casefold())
        )
    return {key: tuple(value) for key, value in charts.items()}, tuple(rejected)
