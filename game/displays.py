"""Discover monitor bounds in desktop coordinates without an extra dependency on macOS."""

import ctypes
import sys
from ctypes.util import find_library


class _Point(ctypes.Structure):
    _fields_ = (("x", ctypes.c_double), ("y", ctypes.c_double))


class _Size(ctypes.Structure):
    _fields_ = (("width", ctypes.c_double), ("height", ctypes.c_double))


class _Rect(ctypes.Structure):
    _fields_ = (("origin", _Point), ("size", _Size))


def connected_monitors():
    """Return (x, y, width, height) for each connected monitor."""
    if sys.platform == "darwin":
        framework = find_library("CoreGraphics")
        if framework:
            graphics = ctypes.CDLL(framework)
            graphics.CGGetActiveDisplayList.argtypes = (
                ctypes.c_uint32, ctypes.POINTER(ctypes.c_uint32), ctypes.POINTER(ctypes.c_uint32),
            )
            graphics.CGGetActiveDisplayList.restype = ctypes.c_int32
            graphics.CGDisplayBounds.argtypes = (ctypes.c_uint32,)
            graphics.CGDisplayBounds.restype = _Rect
            display_ids = (ctypes.c_uint32 * 32)()
            count = ctypes.c_uint32()
            if graphics.CGGetActiveDisplayList(32, display_ids, ctypes.byref(count)) == 0 and count.value:
                return [
                    (round(bounds.origin.x), round(bounds.origin.y),
                     round(bounds.size.width), round(bounds.size.height))
                    for bounds in (graphics.CGDisplayBounds(display_ids[index]) for index in range(count.value))
                ]
    try:
        from screeninfo import get_monitors
    except ImportError:
        return []
    return [(monitor.x, monitor.y, monitor.width, monitor.height) for monitor in get_monitors()]


def station_geometries(monitors, windowed=False):
    """Place two portrait stations on separate monitors or beside each other."""
    monitors = sorted(monitors, key=lambda monitor: (monitor[0], monitor[1]))
    if not monitors:
        raise ValueError("No connected monitor was found.")
    if not windowed and len(monitors) < 2:
        raise ValueError("Two-player fullscreen mode requires two connected monitors.")
    if not windowed:
        return [f"{width}x{height}{x:+d}{y:+d}" for x, y, width, height in monitors[:2]]
    if len(monitors) >= 2:
        positions = []
        for x, y, width, height in monitors[:2]:
            scale = min(0.5, (width - 60) / 1080, (height - 60) / 1920)
            station_width, station_height = round(1080 * scale), round(1920 * scale)
            positions.append((x + (width - station_width) // 2, y + (height - station_height) // 2,
                              station_width, station_height))
    else:
        x, y, width, height = monitors[0]
        scale = min(0.5, (width - 60) / 2160, (height - 60) / 1920)
        station_width, station_height = round(1080 * scale), round(1920 * scale)
        left = x + (width - 2 * station_width) // 2
        top = y + (height - station_height) // 2
        positions = [(left, top, station_width, station_height),
                     (left + station_width, top, station_width, station_height)]
    return [f"{width}x{height}{x:+d}{y:+d}" for x, y, width, height in positions]
