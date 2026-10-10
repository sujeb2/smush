import json
import subprocess
import sys

import cv2

CONTINUITY_MODEL_PREFIXES = ("iPhone", "iPad")


def _is_continuity(device):
    model_id = device.get("spcamera_model-id", "")
    return model_id.startswith(CONTINUITY_MODEL_PREFIXES) or "Desk View" in device.get("_name", "")


def _mac_cameras():
    output = subprocess.run(
        ["system_profiler", "SPCameraDataType", "-json"],
        capture_output=True, text=True, timeout=10, check=True,
    ).stdout
    devices = json.loads(output).get("SPCameraDataType", [])
    return sorted(devices, key=lambda device: device.get("spcamera_unique-id", ""))


def camera_index(preferred=-1):
    if preferred is not None and preferred >= 0:
        return preferred
    if sys.platform != "darwin":
        return 0
    try:
        devices = _mac_cameras()
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        print(f"[CameraSelect] could not list cameras ({error}); using index 0.")
        return 0
    for index, device in enumerate(devices):
        if not _is_continuity(device):
            print(f"[CameraSelect] using camera {index}: {device.get('_name', 'unknown')}")
            return index
    print("[CameraSelect] only Continuity cameras found; refusing to use them.")
    return None


def open_camera(preferred=-1):
    index = camera_index(preferred)
    if index is None:
        raise RuntimeError("No usable webcam found.\nIPhone Continuity Camera is disabled for SMUSH.")
    return cv2.VideoCapture(index)
