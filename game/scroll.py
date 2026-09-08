"""Continuous scroll coordinates, normalized to the chart's initial tempo."""

from bisect import bisect_right
import math


def parse_tempo_points(lines):
    points = {}
    for line in lines:
        fields = line.split(",")
        try:
            offset, beat_ms = float(fields[0]) / 1000, float(fields[1])
            uninherited = len(fields) < 7 or int(fields[6]) == 1
        except (ValueError, IndexError):
            continue
        if uninherited and math.isfinite(offset) and math.isfinite(beat_ms) and beat_ms > 0:
            points[offset] = beat_ms
    return tuple(sorted(points.items()))


def parse_scroll_points(lines):
    """Combine red BPM points and green SV points into effective beat lengths."""
    events = []
    for line in lines:
        fields = line.split(",")
        try:
            offset, value = float(fields[0]) / 1000, float(fields[1])
            red = len(fields) < 7 or int(fields[6]) == 1
        except (ValueError, IndexError):
            continue
        if math.isfinite(offset) and math.isfinite(value) and ((red and value > 0) or (not red and value < 0)):
            events.append((offset, red, value))
    # Process BPM before SV at a shared timestamp, preserving order within each type.
    events.sort(key=lambda event: (event[0], not event[1]))
    beat_ms = next((value for _, red, value in events if red), 500.0)
    points = {}
    for offset, red, value in events:
        if red:
            beat_ms = value
            multiplier = 1.0
        else:
            multiplier = min(10.0, max(0.1, -100.0 / value))
        points[offset] = beat_ms / multiplier
    return tuple(points.items())


class ScrollTimeline:
    def __init__(self, points, base_beat_ms=None):
        points = points or ((0.0, 500.0),)
        self.times = tuple(point[0] for point in points)
        base_beat_ms = points[0][1] if base_beat_ms is None else base_beat_ms
        self.rates = tuple(base_beat_ms / point[1] for point in points)
        self.positions = [self.times[0]]
        for index in range(1, len(points)):
            self.positions.append(self.positions[-1] +
                                  (self.times[index] - self.times[index - 1]) * self.rates[index - 1])

    def position(self, seconds):
        if seconds < self.times[0]:
            return seconds
        index = max(0, bisect_right(self.times, seconds) - 1)
        return self.positions[index] + (seconds - self.times[index]) * self.rates[index]
