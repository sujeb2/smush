import json
import os

from game.rules import MAX_SCORE


def load_progress(path, track_count):
    if track_count <= 0:
        return 0
    try:
        with open(path, "r", encoding="utf-8") as file:
            value = int(json.load(file).get("track_index", 0))
        return value if 0 <= value < track_count else 0
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return 0


def load_event_results(path, track_count):
    scores = [0] * max(0, track_count)
    names = [""] * max(0, track_count)
    try:
        with open(path, "r", encoding="utf-8") as file:
            data = json.load(file)
        stored_scores = data.get("track_scores", [])
        stored_names = data.get("track_names", [])
        for index in range(min(track_count, len(stored_scores))):
            scores[index] = min(MAX_SCORE, max(0, int(stored_scores[index])))
        for index in range(min(track_count, len(stored_names))):
            names[index] = str(stored_names[index])
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        pass
    return scores, names


def load_event_ranks(path, track_count):
    ranks = [""] * max(0, track_count)
    try:
        with open(path, "r", encoding="utf-8") as file:
            stored = json.load(file).get("track_ranks", [])
        for index, rank in enumerate(stored[:track_count]):
            ranks[index] = rank if rank in ("X", "S", "A", "B", "C", "D") else ""
    except (OSError, ValueError, TypeError, AttributeError):
        pass
    return ranks


def load_seen_tutorials(path):
    try:
        with open(path, "r", encoding="utf-8") as file:
            seen = json.load(file).get("seen_tutorials", [])
        return {name for name in seen if name in ("4k", "catch", "extra")}
    except (OSError, ValueError, TypeError, AttributeError):
        return set()


def save_seen_tutorials(path, seen):
    directory = os.path.dirname(path)
    if directory:
        os.makedirs(directory, exist_ok=True)
    try:
        with open(path, "r", encoding="utf-8") as file:
            payload = json.load(file)
        if not isinstance(payload, dict):
            payload = {}
    except (OSError, ValueError, TypeError):
        payload = {}
    payload["seen_tutorials"] = sorted(seen)
    temporary_path = f"{path}.tmp"
    with open(temporary_path, "w", encoding="utf-8") as file:
        json.dump(payload, file)
    os.replace(temporary_path, path)


def save_progress(path, track_index, track_count, track_scores=None, track_names=None, track_ranks=None):
    if track_count <= 0:
        return
    directory = os.path.dirname(path)
    if directory:
        os.makedirs(directory, exist_ok=True)
    try:
        with open(path, "r", encoding="utf-8") as file:
            payload = json.load(file)
        if not isinstance(payload, dict):
            payload = {}
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        payload = {}
    payload["track_index"] = track_index % track_count
    if track_scores is not None:
        payload["track_scores"] = [min(MAX_SCORE, max(0, int(value))) for value in track_scores[:track_count]]
    if track_names is not None:
        payload["track_names"] = [str(value) for value in track_names[:track_count]]
    if track_ranks is not None:
        payload["track_ranks"] = list(track_ranks[:track_count])
    temporary_path = f"{path}.tmp"
    with open(temporary_path, "w", encoding="utf-8") as file:
        json.dump(payload, file)
    os.replace(temporary_path, path)
