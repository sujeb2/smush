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
    supported_sections = {"General", "Metadata", "Difficulty", "HitObjects"}
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
        notes.append(ChartNote(note_time, lane, end_time))
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
    except ValueError as error:
        raise OsuChartError(f"invalid chart difficulty settings: {path}") from error
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
