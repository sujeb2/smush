import serial
import threading
import time
from collections import deque
from datetime import datetime

class SerialIO:
    def __init__(self, port, baudrate, timeout):
        self.timestamp = datetime.now().strftime('%H:%M:%S')
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        print(f"[{self.timestamp}] [SerialIO] Initializing serial port: {port} at {baudrate} baudrate with timeout {timeout}.")
        self.write_lock = threading.Lock()
        self.read_lock = threading.RLock()
        self.pending_messages = deque(maxlen=1024)
        self.status_buffer = ""
        self.crushing_busy = False
        self.crushing_generation = 0
        self.sorter = None
        self.sorter_kinds = {}
        self.pending_sort = None
        self.blocker = None
        self.blocker_side = None
        self.reply_buffer = ""
        self.log_buffer = ""
        self.last_command = None
        self.last_ack = None
        self.awaiting = None
        self.resend_on_ready = False
        self.failed_at = None
        self.ser = serial.Serial(port, baudrate, timeout=timeout, write_timeout=0.2)
        print(f"[{self.timestamp}] [SerialIO] Serial port init done: {port} at {baudrate} baudrate.")

    def open(self):
        if not self.ser.is_open:
            self.ser.open()

    def close(self):
        if self.ser.is_open:
            self.ser.close()

    def reopen(self):
        self.close()
        self.ser.open()

    def reset_board(self):
        with self.write_lock:
            self.ser.dtr = False
            time.sleep(0.1)
            self.ser.dtr = True
        print(f'[{self.timestamp}] [SerialIO] board reset: {self.port}')

    def write(self, data):
        if self.ser.is_open and data is not None:
            with self.write_lock:
                self.ser.write(data.encode('utf-8'))
            print(f'[{self.timestamp}] [SerialIO] write: {data}')

    def write_command(self, command):
        command = str(command).strip()
        if not command or "\n" in command or "\r" in command:
            raise ValueError("serial command must be one non-empty line")
        self.write(f"{command}\n")

    def read(self):
        with self.read_lock:
            if self.pending_messages:
                return self.pending_messages.popleft()
            return self._read_port()

    def _read_port(self):
        self._service_peripherals()
        if self.ser.is_open and self.ser.in_waiting > 0:
            data = self.ser.read(self.ser.in_waiting)
            message = data.decode('utf-8', errors='replace')
            self._consume_status(message)
            return message
        return None

    def _consume_status(self, message):
        self.status_buffer += message.lower()
        while True:
            matches = [(self.status_buffer.find(command), command)
                       for command in ("crushing_busy", "crushing_idle", "crushing_done",
                                       "obj_dropped1", "obj_dropped2", "resetting",
                                       "phase:convey", "phase:crush")
                       if command in self.status_buffer]
            if not matches:
                break
            position, command = min(matches)
            self.status_buffer = self.status_buffer[position + len(command):]
            if command.startswith("obj_dropped"):
                self.pending_sort = self.sorter_kinds.get(int(command[-1]))
                if not self.crushing_busy:
                    self.crushing_generation += 1
                self.crushing_busy = True
                continue
            if command == "resetting":
                self.pending_sort = None
                self.blocker_side = None
                continue
            if command == "phase:convey":
                self._run_blocker("RIGHT")
                continue
            if command == "phase:crush":
                self._run_blocker("LEFT")
                continue
            if command == "crushing_done":
                self._run_sorter()
            busy = command == "crushing_busy"
            if busy:
                self._run_blocker("LEFT")
            if busy != self.crushing_busy:
                self.crushing_generation += 1
            self.crushing_busy = busy
        self.status_buffer = self.status_buffer[-256:]

    def attach_sorter(self, sorter, kinds):
        # kinds maps the crusher's obj_dropped<index> to a sorter side, e.g. {1: "CAN", 2: "PLASTIC"}.
        self.sorter = sorter
        self.sorter_kinds = kinds

    def _run_sorter(self):
        # crushing_done arrives once the crusher has retracted, so the crushed item is ready to sort.
        kind, self.pending_sort = self.pending_sort, None
        if kind is None or self.sorter is None:
            return
        try:
            self.sorter.sort_object(kind)
        except Exception as error:
            print(f"[{self.timestamp}] [SerialIO] sorter write failed: {error}")

    def attach_blocker(self, blocker):
        blocker.resend_on_ready = True
        self.blocker = blocker
        self.blocker_side = None

    def _service_peripherals(self):
        for device in (self.sorter, self.blocker):
            if device is not None:
                device.service()

    def send_tracked(self, command, ack):
        self.last_command, self.last_ack = command, ack.lower()
        self.awaiting = (self.last_ack, time.monotonic(), 1)
        try:
            self.write_command(command)
        except serial.SerialException as error:
            print(f"[{self.timestamp}] [SerialIO] write failed on {self.port}: {error}")
            self.failed_at = time.monotonic()

    def service(self, retry_after=1.0, attempts=3):
        now = time.monotonic()
        try:
            if self.failed_at is not None:
                if now - self.failed_at < 2.0:
                    return
                self.failed_at = None
                self.reply_buffer = ""
                self.reopen()
                print(f"[{self.timestamp}] [SerialIO] reconnected: {self.port}")
                return
            if self.ser.is_open and self.ser.in_waiting > 0:
                data = self.ser.read(self.ser.in_waiting).decode('utf-8', errors='replace').lower()
                self.reply_buffer = (self.reply_buffer + data)[-256:]
                *lines, self.log_buffer = (self.log_buffer + data).split("\n")
                self.log_buffer = self.log_buffer[-256:]
                for line in lines:
                    if line.strip().startswith(("sort_arrived:", "sort_missed:")):
                        print(f"[{self.timestamp}] [SerialIO] {self.port}: {line.strip().upper()}")
            if "ready:" in self.reply_buffer:
                self.reply_buffer = ""
                if self.last_command and (self.awaiting or self.resend_on_ready):
                    self.awaiting = (self.last_ack, now, 1)
                    self.write_command(self.last_command)
                return
            if self.awaiting is None:
                return
            ack, sent_at, tries = self.awaiting
            if ack in self.reply_buffer:
                self.reply_buffer = self.reply_buffer[self.reply_buffer.find(ack) + len(ack):]
                self.awaiting = None
            elif now - sent_at >= retry_after:
                if tries >= attempts:
                    print(f"[{self.timestamp}] [SerialIO] no reply to {self.last_command} on {self.port}")
                    self.awaiting = None
                else:
                    self.awaiting = (ack, now, tries + 1)
                    self.write_command(self.last_command)
        except serial.SerialException as error:
            print(f"[{self.timestamp}] [SerialIO] connection lost on {self.port}: {error}")
            self.failed_at = now

    def _run_blocker(self, side):
        if self.blocker is None or side == self.blocker_side:
            return
        try:
            self.blocker.block_holes(side)
            self.blocker_side = side
        except Exception as error:
            print(f"[{self.timestamp}] [SerialIO] blocker write failed: {error}")

    def poll_machine_status(self):
        # Preserve data for the UI even when the recognition worker reads first.
        with self.read_lock:
            message = self._read_port()
            if message:
                self.pending_messages.append(message)
            return self.crushing_busy, self.crushing_generation

    def write_detection(self, data, generation):
        with self.read_lock:
            busy, current_generation = self.poll_machine_status()
            if busy or current_generation != generation:
                return False
            self.write(data)
            return True

    def set_led_frame(self, switches, pixels):
        if len(switches) != 4 or any(type(v) is not bool for v in switches):
            raise ValueError("four boolean switch states required")
        if len(pixels) != 4 or any(len(p) != 3 or any(type(v) is not int or not 0 <= v <= 255 for v in p) for p in pixels):
            raise ValueError("four pixels with byte values required")
        if not self.is_open:
            raise serial.SerialException("serial port is closed")
        # Keep frame shape compatible; the old button-lamp mask is always zero.
        self.write_command("LED0:" + "".join(f"{v:02X}" for p in pixels for v in p))

    def set_ticker(self, text, blink=False):
        if len(text) > 48 or any(not " " <= c <= "~" for c in text):
            raise ValueError("ticker text must be at most 48 printable ASCII characters")
        self.write_command(f"TICK:{'B' if blink else 'S'}:{text}")

    def sort_object(self, kind):
        # Sorter Nano gate (hardware/arduino/sorter); replies SORT_DONE:<side> when back at center.
        kind = str(kind).strip().upper()
        if kind not in ("CAN", "PLASTIC", "HOME"):
            raise ValueError("sorter target must be CAN, PLASTIC or HOME")
        self.send_tracked(f"SORT:{kind}", f"SORT_START:{kind}")

    def block_holes(self, side):
        side = str(side).strip().upper()
        if side not in ("LEFT", "RIGHT"):
            raise ValueError("blocker target must be LEFT or RIGHT")
        self.send_tracked(f"BLOCK:{side}", f"BLOCK_START:{side}")

    @property
    def is_open(self):
        return self.ser.is_open

    @property
    def in_waiting(self):
        with self.read_lock:
            return sum(len(message) for message in self.pending_messages) + self.ser.in_waiting
