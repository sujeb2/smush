import serial_io, enum, os, sys
import configparser as cfg
from datetime import datetime

def findCompiledDir():
    if "__compiled__" in globals():
        return os.path.dirname(os.path.abspath(sys.argv[0]))
    else:
        return os.path.dirname(os.path.abspath(__file__))

base = findCompiledDir()

cfg = cfg.ConfigParser()
cfg.read(os.path.join(base, 'files', 'main_conf.ini'), encoding='utf-8')

class Direction(enum.Enum):
    FORWARD = 1
    BACKWARD = 2
    LEFT = 3
    RIGHT = 4

class Motor:
    def __init__(self, port):
        self.timestamp = datetime.now().strftime('%H:%M:%S')
        self.port = port
        self.ser = serial_io.Serial(port, 9600, timeout=1)
        self.currentDirection = None
        self.currentForce = 0

    def movement(self, direction: Direction, force: int):
        # excluding
        if(force <= 0 or force > int(cfg['MOTOR']['MaximumForceAvailable'])):
            print(f"[{self.timestamp}] [motor] invalid force value. expected between 1 and {cfg['MOTOR']['MaximumForceAvailable']}.")
            return
        if(direction not in Direction):
            print(f"[{self.timestamp}] [motor] invalid direction value. expected one of {list(Direction)}.")
            return

    def getCurrentDirection(self):
        return self.currentDirection

    def getCurrentForce(self):
        return self.currentForce