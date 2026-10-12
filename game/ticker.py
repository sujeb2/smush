import configparser
import os
import threading
import time

MAX_LENGTH = 48
RESEND_SECONDS = 2.0
WIDTH = 32
GLYPH_WIDTH = 5
GLYPH_PITCH = GLYPH_WIDTH + 1
STEP_MS = 100  # Keep in step with ticker.ino TICKER_STEP_MS / TICKER_BLINK_MS.
BLINK_MS = 500
# 5x7 columns (bit 0 = top row) for ASCII 0x20-0x5F, identical to ticker.ino TICKER_FONT.
FONT = (
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x5F, 0x00, 0x00, 0x00, 0x07, 0x00, 0x07, 0x00, 0x14, 0x7F, 0x14, 0x7F, 0x14,
    0x24, 0x2A, 0x7F, 0x2A, 0x12, 0x23, 0x13, 0x08, 0x64, 0x62, 0x36, 0x49, 0x55, 0x22, 0x50, 0x00, 0x05, 0x03, 0x00, 0x00,
    0x00, 0x1C, 0x22, 0x41, 0x00, 0x00, 0x41, 0x22, 0x1C, 0x00, 0x08, 0x2A, 0x1C, 0x2A, 0x08, 0x08, 0x08, 0x3E, 0x08, 0x08,
    0x00, 0x50, 0x30, 0x00, 0x00, 0x08, 0x08, 0x08, 0x08, 0x08, 0x00, 0x60, 0x60, 0x00, 0x00, 0x20, 0x10, 0x08, 0x04, 0x02,
    0x3E, 0x51, 0x49, 0x45, 0x3E, 0x00, 0x42, 0x7F, 0x40, 0x00, 0x42, 0x61, 0x51, 0x49, 0x46, 0x21, 0x41, 0x45, 0x4B, 0x31,
    0x18, 0x14, 0x12, 0x7F, 0x10, 0x27, 0x45, 0x45, 0x45, 0x39, 0x3C, 0x4A, 0x49, 0x49, 0x30, 0x01, 0x71, 0x09, 0x05, 0x03,
    0x36, 0x49, 0x49, 0x49, 0x36, 0x06, 0x49, 0x49, 0x29, 0x1E, 0x00, 0x36, 0x36, 0x00, 0x00, 0x00, 0x56, 0x36, 0x00, 0x00,
    0x08, 0x14, 0x22, 0x41, 0x00, 0x14, 0x14, 0x14, 0x14, 0x14, 0x00, 0x41, 0x22, 0x14, 0x08, 0x02, 0x01, 0x51, 0x09, 0x06,
    0x32, 0x49, 0x79, 0x41, 0x3E, 0x7E, 0x11, 0x11, 0x11, 0x7E, 0x7F, 0x49, 0x49, 0x49, 0x36, 0x3E, 0x41, 0x41, 0x41, 0x22,
    0x7F, 0x41, 0x41, 0x22, 0x1C, 0x7F, 0x49, 0x49, 0x49, 0x41, 0x7F, 0x09, 0x09, 0x01, 0x01, 0x3E, 0x41, 0x41, 0x51, 0x32,
    0x7F, 0x08, 0x08, 0x08, 0x7F, 0x00, 0x41, 0x7F, 0x41, 0x00, 0x20, 0x40, 0x41, 0x3F, 0x01, 0x7F, 0x08, 0x14, 0x22, 0x41,
    0x7F, 0x40, 0x40, 0x40, 0x40, 0x7F, 0x02, 0x04, 0x02, 0x7F, 0x7F, 0x04, 0x08, 0x10, 0x7F, 0x3E, 0x41, 0x41, 0x41, 0x3E,
    0x7F, 0x09, 0x09, 0x09, 0x06, 0x3E, 0x41, 0x51, 0x21, 0x5E, 0x7F, 0x09, 0x19, 0x29, 0x46, 0x46, 0x49, 0x49, 0x49, 0x31,
    0x01, 0x01, 0x7F, 0x01, 0x01, 0x3F, 0x40, 0x40, 0x40, 0x3F, 0x1F, 0x20, 0x40, 0x20, 0x1F, 0x7F, 0x20, 0x18, 0x20, 0x7F,
    0x63, 0x14, 0x08, 0x14, 0x63, 0x03, 0x04, 0x78, 0x04, 0x03, 0x61, 0x51, 0x49, 0x45, 0x43, 0x00, 0x7F, 0x41, 0x41, 0x00,
    0x02, 0x04, 0x08, 0x10, 0x20, 0x00, 0x41, 0x41, 0x7F, 0x00, 0x04, 0x02, 0x01, 0x02, 0x04, 0x40, 0x40, 0x40, 0x40, 0x40,
)
SCENE_TEXT = {
    "title": "CITRADE!!",
    "ci": "CITRADE!!",
    "demonstration": "DEMO PLAY",
    "entry": "ENTRY",
    "warning": "WARNING",
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


def text_column(text, x):
    if x < 0 or x >= len(text) * GLYPH_PITCH - 1 or x % GLYPH_PITCH == GLYPH_WIDTH:
        return 0
    code = ord(text[x // GLYPH_PITCH].upper())
    return FONT[(code - 0x20) * GLYPH_WIDTH + x % GLYPH_PITCH] if 0x20 <= code <= 0x5F else 0


def ticker_frame(text, blink, elapsed):
    width = len(text) * GLYPH_PITCH - 1
    elapsed_ms = round(elapsed * 1000)  # The firmware counts whole milliseconds.
    if width > WIDTH:
        offset = elapsed_ms // STEP_MS % (width + WIDTH)
        return tuple(text_column(text, x + offset - WIDTH) for x in range(WIDTH))
    if blink and elapsed_ms // BLINK_MS % 2:
        return (0,) * WIDTH
    start = (WIDTH - width) // 2
    return tuple(text_column(text, x - start) for x in range(WIDTH))


def render_preview(frame):
    from PIL import Image, ImageDraw

    lit, unlit = (255, 48, 32, 255), (40, 10, 8, 255)
    image = Image.new("RGBA", (480, 150), (8, 8, 8, 255))
    draw = ImageDraw.Draw(image)
    for x, column in enumerate(frame):
        left = 16 + x * 13 + x // 8 * 8
        for row in range(8):
            top = 14 + row * 13
            draw.ellipse((left, top, left + 10, top + 10), fill=lit if column >> row & 1 else unlit)
    draw.text((16, 128), "TICKER", fill="white")
    return image


def ticker_port(config_path):
    port = os.environ.get("SMUSH_TICKER_PORT")
    if port is None:
        parser = configparser.ConfigParser()
        parser.read(config_path, encoding="utf-8")
        port = parser.get("SERIAL", "TickerPort", fallback="")
    return port.strip()


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
    def _initialize_ticker(self, config_path):
        self.ticker_output = None
        self.ticker_serial = None
        self.ticker_message = None
        self.ticker_started = time.monotonic()
        self.ticker_preview_frame = None
        port = ticker_port(config_path)
        # One ticker per cabinet: in 2-player mode station 1 drives it.
        if port and not self.demo_mode and getattr(self, "station", 1) == 1:
            threading.Thread(target=self._connect_ticker, args=(config_path, port),
                             daemon=True, name="smush-ticker-serial").start()
        self.root.after(0, self._tick_ticker)

    def _connect_ticker(self, config_path, port):
        from serial_arduino import SerialIO

        parser = configparser.ConfigParser()
        parser.read(config_path, encoding="utf-8")
        try:
            self.ticker_serial = SerialIO(port, parser.getint("SERIAL", "SerialBaudrate", fallback=9600),
                                          parser.getint("SERIAL", "SerialTimeout", fallback=1))
        except Exception as error:
            self._print(f"ticker unavailable on {port}: {error}")

    def _tick_ticker(self):
        if not self.running:
            self._close_ticker()
            return
        message = ticker_message(self)
        now = time.monotonic()
        if message != self.ticker_message:  # Like the firmware, a resend keeps the scroll position.
            self.ticker_message, self.ticker_started = message, now
        if self.ticker_serial is not None:
            if self.ticker_output is None:
                self.ticker_output = TickerOutput(self._print)
            self.ticker_output.submit(self.ticker_serial, message)
        self._draw_ticker_preview(now)
        if self.unrecoverable_error:
            self._close_ticker()  # err blink
            return
        self.root.after(35, self._tick_ticker)

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
        if getattr(self, "ticker_serial", None) is not None and not self.running:
            self.ticker_serial.close()
            self.ticker_serial = None
