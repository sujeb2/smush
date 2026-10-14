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
        self.ser = serial.Serial(port, baudrate, timeout=timeout, write_timeout=0.2)
        print(f"[{self.timestamp}] [SerialIO] Serial port init done: {port} at {baudrate} baudrate.")

    def open(self):
        if not self.ser.is_open:
            self.ser.open()

    def close(self):
        if self.ser.is_open:
            self.ser.close()

    def reopen(self):
        # Recover after the USB device dropped out and came back under the same port name.
        self.close()
        self.ser.open()

    def reset_board(self):
        # Pulse DTR: the Arduino's auto-reset circuit reboots the board, crashed or not.
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
        if self.ser.is_open and self.ser.in_waiting > 0:
            data = self.ser.read(self.ser.in_waiting)
            # Delimiters disambiguate Forwarded from Forwarded_2 immediately.
            message = data.decode('utf-8', errors='replace')
            self._consume_status(message)
            return message
        return None

    def _consume_status(self, message):
        self.status_buffer += message.lower()
        while True:
            matches = [(self.status_buffer.find(command), command)
                       for command in ("crushing_busy", "crushing_idle", "crushing_done",
                                       "obj_dropped1", "obj_dropped2", "resetting")
                       if command in self.status_buffer]
            if not matches:
                break
            position, command = min(matches)
            self.status_buffer = self.status_buffer[position + len(command):]
            if command.startswith("obj_dropped"):
                self.pending_sort = self.sorter_kinds.get(int(command[-1]))
                continue
            if command == "resetting":
                self.pending_sort = None
                continue
            if command == "crushing_done":
                self._run_sorter()
            busy = command == "crushing_busy"
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
        self.write_command(f"SORT:{kind}")

    @property
    def is_open(self):
        return self.ser.is_open

    @property
    def in_waiting(self):
        with self.read_lock:
            return sum(len(message) for message in self.pending_messages) + self.ser.in_waiting
