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
