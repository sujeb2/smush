"""IIDX-style 7-segment ticker text for the board IO display."""
import threading
import time

MAX_LENGTH = 48
RESEND_SECONDS = 5.0
SCENE_TEXT = {
    "title": "WELCOME TO SMUSH CiTRADE",
    "ci": "WELCOME TO SMUSH CiTRADE",
    "demonstration": "WELCOME TO SMUSH",
    "entry": "ENTRY",
    "warning": "ENTRY",
    "mode_select": "MODE SELECT",
    "title_select": "MUSIC SELECT",
    "total_result": "TOTAL RESULT",
    "game_ended": "CARD OUT",
    "ending": "THANK YOU FOR PLAYING",
}


def ticker_text(value):
    words = ("".join(c for c in word if " " <= c <= "_") for word in str(value or "").upper().split())
    return " ".join(word for word in words if word)[:MAX_LENGTH]


def song_label(track):
    title = ticker_text(getattr(track, "title_ascii", "")) or ticker_text(track.title)
    artist = ticker_text(getattr(track, "artist_ascii", "")) or ticker_text(track.artist)
    if not title:
        return "NOW PLAYING"
    return ticker_text(f"{title} / {artist}" if artist else title)


def ticker_message(app):
    """Return (text, blink) for the current scene."""
    scene = app.scene
    track = getattr(app, "track", None)
    if getattr(app, "unrecoverable_error", None):
        return "ERR", True
    if scene == "preload":
        return "LOAD", True
    if scene in ("title", "ci", "demonstration") and getattr(app, "coins_per_credit", 0) > 0 \
            and getattr(app, "credit_count", 0) == 0:
        return ticker_text(f"{SCENE_TEXT[scene]}  INSERT COIN"), False
    if scene in SCENE_TEXT:
        return SCENE_TEXT[scene], False
    if track is None:
        return "", False
    if scene == "select":
        return song_label(track), False
    if scene == "next":
        stage = "EXTRA STAGE" if getattr(app, "extra_stage_active", False) else f"STAGE {app.track_index + 1}"
        return ticker_text(f"{stage}  {song_label(track)}"), False
    if scene == "game":
        return song_label(track), False
    if scene == "result":
        return ticker_text(f"RANK {app.rank}  SCORE {app.score}"), False
    return "", False


class TickerOutput:
    def __init__(self, report):
        self.report = report
        self.condition = threading.Condition()
        self.pending = None
        self.closing = False
        self.thread = threading.Thread(target=self._run, daemon=True, name="smush-ticker-output")
        self.thread.start()

    def submit(self, serial, message):
        with self.condition:
            self.pending = serial, message
            self.condition.notify()

    def close(self):
        with self.condition:
            self.closing = True
            self.condition.notify()
        self.thread.join(timeout=0.2)

    def _run(self):
        previous, sent_at, failed = None, 0.0, None
        while True:
            with self.condition:
                self.condition.wait_for(lambda: self.pending is not None or self.closing)
                pending, self.pending = self.pending, None
                closing = self.closing
            if pending is not None:
                target, message = pending
                due = (target, message) != previous or time.monotonic() - sent_at >= RESEND_SECONDS
                if target is not None and target is not failed and due:
                    try:
                        target.set_ticker(*message)
                        previous, sent_at = (target, message), time.monotonic()
                    except Exception as error:
                        failed = target
                        self.report(f"ticker output unavailable: {error}")
            if closing:
                return


class TickerRuntimeMixin:
    def _initialize_ticker(self):
        self.ticker_output = None
        self.root.after(0, self._tick_ticker)

    def _tick_ticker(self):
        if not self.running:
            self._close_ticker()
            return
        if not self.demo_mode and self.serial is not None:
            if self.ticker_output is None:
                self.ticker_output = TickerOutput(self._print)
            self.ticker_output.submit(self.serial, ticker_message(self))
        if self.unrecoverable_error:
            self._close_ticker()  # err blink
            return
        self.root.after(100, self._tick_ticker)

    def _close_ticker(self):
        if getattr(self, "ticker_output", None) is not None:
            self.ticker_output.close()
            self.ticker_output = None
