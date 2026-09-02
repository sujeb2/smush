import serial
from datetime import datetime

class SerialIO:
    def __init__(self, port, baudrate, timeout):
        self.timestamp = datetime.now().strftime('%H:%M:%S')
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        print(f"[{self.timestamp}] [SerialIO] Initializing serial port: {port} at {baudrate} baudrate with timeout {timeout}.")
        self.ser = serial.Serial(port, baudrate, timeout=timeout)
        print(f"[{self.timestamp}] [SerialIO] Serial port init done: {port} at {baudrate} baudrate.")

    def open(self):
        if not self.ser.is_open:
            self.ser.open()

    def close(self):
        if self.ser.is_open:
            self.ser.close()

    def write(self, data):
        """
        serial data write, data shouldn't be null
        """
        if self.ser.is_open and data is not None:
            self.ser.write(data.encode('utf-8'))
            print(f'[{self.timestamp}] [SerialIO] write: {data}')

    def write_command(self, command):
        """Write one newline-delimited command to the Arduino."""
        command = str(command).strip()
        if not command or "\n" in command or "\r" in command:
            raise ValueError("serial command must be one non-empty line")
        self.write(f"{command}\n")

    def set_switch_led(self, switch_number, enabled):
        """Set one of the four illuminated switch LEDs on or off."""
        if isinstance(switch_number, bool) or switch_number not in range(1, 5):
            raise ValueError("switch_number must be an integer from 1 to 4")
        state = "ON" if enabled else "OFF"
        self.write_command(f"SW{switch_number}_{state}")

    def read(self):
        if self.ser.is_open and self.ser.in_waiting > 0:
            data = self.ser.read(self.ser.in_waiting)
            message = data.decode('utf-8', errors='replace').rstrip()
            print(f'[{self.timestamp}] [SerialIO] read: {message}')
            return message
        return None

    @property
    def is_open(self):
        return self.ser.is_open

    @property
    def in_waiting(self):
        return self.ser.in_waiting
