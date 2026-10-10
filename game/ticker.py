"""IIDX-style 7-segment ticker text for the board IO display."""
import threading
import time

MAX_LENGTH = 48
RESEND_SECONDS = 5.0
DIGITS = 4
STEP_SECONDS = 0.28  # Keep in step with boardio.ino TICKER_STEP_MS / TICKER_BLINK_MS.
BLINK_SECONDS = 0.5
# Segments (bit 0 = A ... bit 6 = G) for ASCII 0x20-0x5F, identical to boardio.ino TICKER_FONT.
FONT = (
    0x00, 0x0A, 0x22, 0x00, 0x6D, 0x00, 0x00, 0x02, 0x39, 0x0F, 0x63, 0x40, 0x04, 0x40, 0x08, 0x52,
    0x3F, 0x06, 0x5B, 0x4F, 0x66, 0x6D, 0x7D, 0x07, 0x7F, 0x6F, 0x09, 0x00, 0x58, 0x48, 0x4C, 0x53,
    0x7B, 0x77, 0x7C, 0x39, 0x5E, 0x79, 0x71, 0x3D, 0x76, 0x30, 0x1E, 0x75, 0x38, 0x37, 0x54, 0x3F,
    0x73, 0x67, 0x50, 0x6D, 0x78, 0x3E, 0x1C, 0x2A, 0x76, 0x6E, 0x5B, 0x39, 0x64, 0x0F, 0x23, 0x08,
)
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


def glyph(character):
    code = ord(character.upper()) if len(character) == 1 else 0
    return FONT[code - 0x20] if 0x20 <= code <= 0x5F else 0


def ticker_frame(text, blink, elapsed):
    """Segment bytes the board shows `elapsed` seconds after receiving the text."""
    frame = [0] * DIGITS
    if len(text) > DIGITS:
        offset = int(elapsed / STEP_SECONDS) % (len(text) + DIGITS)
        for digit in range(DIGITS):
            index = offset + digit - DIGITS
            if 0 <= index < len(text):
                frame[digit] = glyph(text[index])
    elif not blink or int(elapsed / BLINK_SECONDS) % 2 == 0:
        start = (DIGITS - len(text)) // 2
        for index, character in enumerate(text):
            frame[start + index] = glyph(character)
    return tuple(frame)


def render_preview(frame):
    from PIL import Image, ImageDraw

    lit, unlit = (255, 48, 32, 255), (52, 12, 10, 255)
    image = Image.new("RGBA", (480, 170), (8, 8, 8, 255))
    draw = ImageDraw.Draw(image)
    width, height, thick = 72, 120, 12
    half = thick / 2

    def horizontal(x, y):
        return ((x + half, y), (x + thick, y - half), (x + width - thick, y - half),
                (x + width - half, y), (x + width - thick, y + half), (x + thick, y + half))

    def vertical(x, y):
        return ((x, y + half), (x + half, y + thick), (x + half, y + height / 2 - thick),
                (x, y + height / 2 - half), (x - half, y + height / 2 - thick), (x - half, y + thick))

    for digit, segments in enumerate(frame):
        x, y = 48 + digit * 108, 14
        shapes = (horizontal(x, y), vertical(x + width, y), vertical(x + width, y + height / 2),
                  horizontal(x, y + height), vertical(x, y + height / 2), vertical(x, y),
                  horizontal(x, y + height / 2))
        for bit, shape in enumerate(shapes):
            draw.polygon(shape, fill=lit if segments >> bit & 1 else unlit)
    draw.text((12, 150), "TICKER", fill="white")
    return image


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
        self.ticker_message = None
        self.ticker_started = time.monotonic()
        self.ticker_preview_frame = None
        self.root.after(0, self._tick_ticker)

    def _tick_ticker(self):
        if not self.running:
            self._close_ticker()
            return
        message = ticker_message(self)
        now = time.monotonic()
        if message != self.ticker_message:  # Like the firmware, a resend keeps the scroll position.
            self.ticker_message, self.ticker_started = message, now
        if not self.demo_mode and self.serial is not None:
            if self.ticker_output is None:
                self.ticker_output = TickerOutput(self._print)
            self.ticker_output.submit(self.serial, message)
        self._draw_ticker_preview(now)
        if self.unrecoverable_error:
            self._close_ticker()  # err blink
            return
        self.root.after(40, self._tick_ticker)

    def _draw_ticker_preview(self, now):
        # Shares the F6 toggle with the demo-mode LED preview.
        if not (self.demo_mode and self.led_preview_visible):
            self.canvas.delete("ticker_preview")
            self.ticker_preview_frame = None
            return
        frame = ticker_frame(*self.ticker_message, now - self.ticker_started)
        if frame != self.ticker_preview_frame or not self.canvas.coords("ticker_preview"):
            self.canvas.delete("ticker_preview")
            self.ticker_preview_photo = render_preview(frame)
            self.canvas.create_image(self._x(540), self._y(570), image=self.ticker_preview_photo,
                                     anchor="center", tags=("ticker_preview",))
            self.ticker_preview_frame = frame
        self.canvas.tag_raise("ticker_preview")

    def _close_ticker(self):
        if getattr(self, "ticker_output", None) is not None:
            self.ticker_output.close()
            self.ticker_output = None
