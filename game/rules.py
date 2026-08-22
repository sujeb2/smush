MAX_SCORE = 9000
EVENT_TRACK_COUNT = 3
TEXT_SCALE = 1.18
PERFECT_WINDOW = 0.09
GOOD_WINDOW = 0.18
BAD_WINDOW = 0.30
HIT_WINDOW = 0.34
HOLD_TICK_INTERVAL = 0.25
CI_WARNING_SECONDS = 2.0
CI_NOTICE_SECONDS = 2.0
CI_CREDITS_SECONDS = 4.0
JUDGEMENT_WEIGHT = {
    "perfect": 1.0,
    "good": 0.65,
    "bad": 0.25,
    "miss": 0.0,
}
HEALTH_CHANGE = {
    "perfect": 0.45,
    "good": 0.15,
    "bad": -3.0,
    "miss": -7.0,
}

def calculate_score(judgements, note_count):
    if note_count <= 0:
        return 0
    weighted = sum(JUDGEMENT_WEIGHT.get(judgement, 0.0) for judgement in judgements)
    return min(MAX_SCORE, max(0, round(MAX_SCORE * weighted / note_count)))

def calculate_catch_score(catches, note_count):
    if note_count <= 0:
        return 0
    return min(MAX_SCORE, max(0, round(MAX_SCORE * catches / note_count)))

def is_clear(health):
    return health > 0 and health >= 5.0

def smooth_progress(value):
    progress = min(1.0, max(0.0, value))
    return progress * progress * (3 - 2 * progress)

def combo_after_judgement(combo, judgement):
    return 0 if judgement == "miss" else combo + 1

def hold_tick_times(note_time, end_time, interval=HOLD_TICK_INTERVAL):
    if end_time is None or end_time <= note_time or interval <= 0:
        return ()
    ticks = []
    tick = note_time + interval
    while tick <= end_time + 0.000001:
        ticks.append(round(tick, 6))
        tick += interval
    return tuple(ticks)

def group_charts_by_song(charts):
    grouped = {}
    order = []
    for chart in charts:
        key = chart.artist.casefold(), chart.title.casefold()
        if key not in grouped:
            grouped[key] = []
            order.append(key)
        grouped[key].append(chart)
    return tuple(
        tuple(sorted(grouped[key], key=lambda chart: (chart.level, chart.difficulty.casefold(), chart.path.casefold())))
        for key in order
    )

def event_result_destination(track_index, cleared):
    if cleared and track_index < EVENT_TRACK_COUNT - 1:
        return "select", track_index + 1
    if cleared:
        return "total_result", 0
    return "ending", 0