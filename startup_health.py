import configparser
import glob
import json
import os
import shutil
import tempfile
import xml.etree.ElementTree as ElementTree
from datetime import datetime

from PIL import Image


ERROR_MARKER_NAME = ".last_unrecoverable_error.json"
MINIMUM_FREE_DISK_BYTES = 256 * 1024 * 1024


class StartupHealthError(RuntimeError):
    pass


def error_marker_path(base):
    return os.path.join(base, "files", ERROR_MARKER_NAME)


def mark_unrecoverable_error(base, code, detail):
    path = error_marker_path(base)
    directory = os.path.dirname(path)
    os.makedirs(directory, exist_ok=True)
    payload = {
        "code": str(code),
        "detail": str(detail)[-4000:],
        "occurred_at": datetime.now().astimezone().isoformat(timespec="seconds"),
    }
    temporary_path = f"{path}.tmp"
    try:
        with open(temporary_path, "w", encoding="utf-8") as file:
            json.dump(payload, file, ensure_ascii=False, indent=2)
            file.flush()
            os.fsync(file.fileno())
        os.replace(temporary_path, path)
    finally:
        if os.path.exists(temporary_path):
            os.remove(temporary_path)


def previous_error_details(base):
    path = error_marker_path(base)
    if not os.path.isfile(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as file:
            payload = json.load(file)
        return payload if isinstance(payload, dict) else {"code": "UNKNOWN_PREVIOUS_ERROR"}
    except (OSError, ValueError):
        return {"code": "DAMAGED_ERROR_MARKER"}


def clear_previous_error(base):
    try:
        os.remove(error_marker_path(base))
    except FileNotFoundError:
        pass
    except OSError as error:
        raise StartupHealthError(f"cannot clear the previous-error marker: {error}") from error


def check_disk(base, minimum_free_bytes=MINIMUM_FREE_DISK_BYTES):
    try:
        usage = shutil.disk_usage(base)
    except OSError as error:
        raise StartupHealthError(f"cannot read disk information: {error}") from error
    if usage.free < minimum_free_bytes:
        available_mb = usage.free // (1024 * 1024)
        required_mb = minimum_free_bytes // (1024 * 1024)
        raise StartupHealthError(
            f"insufficient disk space: {available_mb} MB available; {required_mb} MB required",
        )
    probe_directory = os.path.join(base, "files")
    if not os.path.isdir(probe_directory):
        raise StartupHealthError(f"startup data directory is missing: {probe_directory}")
    probe_path = None
    try:
        descriptor, probe_path = tempfile.mkstemp(prefix=".smush-disk-check-", dir=probe_directory)
        with os.fdopen(descriptor, "wb") as file:
            file.write(b"SMUSH_DISK_CHECK")
            file.flush()
            os.fsync(file.fileno())
        with open(probe_path, "rb") as file:
            if file.read() != b"SMUSH_DISK_CHECK":
                raise StartupHealthError("disk read-back verification failed")
    except OSError as error:
        raise StartupHealthError(f"disk write/read check failed: {error}") from error
    finally:
        if probe_path is not None:
            try:
                os.remove(probe_path)
            except FileNotFoundError:
                pass
            except OSError as error:
                raise StartupHealthError(f"cannot remove disk-check file: {error}") from error
    return usage


def _require_nonempty_files(base, relative_paths):
    resolved = []
    for relative_path in relative_paths:
        path = os.path.join(base, relative_path)
        if not os.path.isfile(path):
            raise StartupHealthError(f"required file is missing: {relative_path}")
        if os.path.getsize(path) <= 0:
            raise StartupHealthError(f"required file is empty: {relative_path}")
        resolved.append(path)
    return resolved


def _validate_configs(base):
    main_path = os.path.join(base, "files", "main_conf.ini")
    model_path = os.path.join(base, "files", "model_conf.ini")
    parser = configparser.ConfigParser()
    try:
        with open(main_path, "r", encoding="utf-8") as file:
            parser.read_file(file)
        if not parser.has_section("GENERIC") or not parser.has_section("UI"):
            raise StartupHealthError("files/main_conf.ini is missing required sections")
        model_relative_path = parser.get("GENERIC", "ModelPath", fallback="").strip()
        if model_relative_path:
            _require_nonempty_files(base, (model_relative_path,))
        model_parser = configparser.ConfigParser()
        with open(model_path, "r", encoding="utf-8") as file:
            model_parser.read_file(file)
        if not model_parser.sections():
            raise StartupHealthError("files/model_conf.ini contains no configuration sections")
    except (OSError, configparser.Error) as error:
        raise StartupHealthError(f"configuration file validation failed: {error}") from error


def _validate_images(base, image_paths):
    for relative_path in image_paths:
        path = os.path.join(base, relative_path)
        try:
            with Image.open(path) as image:
                image.verify()
        except (OSError, SyntaxError) as error:
            raise StartupHealthError(f"image file is damaged: {relative_path}: {error}") from error


def _validate_application_sources(base):
    source_paths = sorted(glob.glob(os.path.join(base, "*.py")))
    source_paths.extend(sorted(glob.glob(os.path.join(base, "game", "*.py"))))
    for path in source_paths:
        try:
            with open(path, "r", encoding="utf-8") as file:
                source = file.read()
            compile(source, path, "exec")
        except (OSError, SyntaxError, UnicodeError) as error:
            relative_path = os.path.relpath(path, base)
            raise StartupHealthError(f"application file is damaged: {relative_path}: {error}") from error


def _validate_data_files(base):
    progress_path = os.path.join(base, "game", "minigame_progress.json")
    if os.path.isfile(progress_path):
        try:
            with open(progress_path, "r", encoding="utf-8") as file:
                json.load(file)
        except (OSError, ValueError) as error:
            raise StartupHealthError(f"game/minigame_progress.json is damaged: {error}") from error
    svg_path = os.path.join(base, "files", "img", "unrecoverable_system_error.svg")
    try:
        ElementTree.parse(svg_path)
    except (OSError, ElementTree.ParseError) as error:
        raise StartupHealthError(f"unrecoverable-system-error artwork is damaged: {error}") from error
    for chart_path in glob.glob(os.path.join(base, "game", "charts", "**", "*.osu"), recursive=True):
        try:
            with open(chart_path, "r", encoding="utf-8-sig") as file:
                header = file.readline().strip()
            if not header.lower().startswith("osu file format"):
                raise StartupHealthError(
                    f"chart file has an invalid header: {os.path.relpath(chart_path, base)}",
                )
        except (OSError, UnicodeError) as error:
            raise StartupHealthError(
                f"chart file is damaged: {os.path.relpath(chart_path, base)}: {error}",
            ) from error


def check_runtime_files(base, required_paths=None, image_paths=None):
    if required_paths is None:
        required_paths = (
            "requirements.txt",
            "files/main_conf.ini",
            "files/model_conf.ini",
            "files/fonts/KERISKEDU_B.ttf",
            "files/fonts/Novecentosanswide-DemiBold.otf",
            "files/img/unrecoverable_system_error.svg",
            "game/imgs/generic/fail_io.png",
        )
    _require_nonempty_files(base, required_paths)
    if image_paths is None:
        from game.AssetWorker import IMAGE_PATHS

        image_paths = tuple(os.path.join("game", "imgs", *parts) for parts in IMAGE_PATHS.values())
        image_paths += tuple(
            os.path.join("files", "img", filename)
            for filename in (
                "can.png", "cans.png", "ground_layer.png", "plastic_bottle.png",
                "trash_can.png", "update_layer.png",
            )
        )
    _validate_configs(base)
    _validate_images(base, image_paths)
    _validate_data_files(base)
    _validate_application_sources(base)
    return True
