import model, os, sys
from datetime import datetime
import configparser as cfg

def findCompiledDir():
    if "__compiled__" in globals():
        return os.path.dirname(os.path.abspath(sys.argv[0]))
    else:
        return os.path.dirname(os.path.abspath(__file__))

base = findCompiledDir()

cfg = cfg.ConfigParser()
cfg.read(os.path.join(base, 'files', 'main_conf.ini'), encoding='utf-8')

class Main:
    def __init__(self):
        try:
            self.timestamp = datetime.now().strftime('%H:%M:%S')
            print(f"[{self.timestamp}] [main] smush starting, config loaded: {cfg.sections()}")
            print(f"[{self.timestamp}] [main] model path: {cfg['GENERIC']['ModelPath']}")
            self.fileLimitChecker()
            self.model = model.Model(cfg['GENERIC']['ModelPath'])
            #self.serial = serial.Serial(port=cfg['SERIAL']['SerialPort'], baudrate=cfg['SERIAL']['SerialBaudrate'], timeout=1)
            #self.serial.open()
            #if(not self.serial.is_open):
            #    print(f"[{self.timestamp}] [main] Failed to find serial port thats avaliable from configuration. Is the device connected?")
            print(f"[{self.timestamp}] [main] Init done, waiting for serial..")
            self.model.liveFeedCapture()
            #self.checkForBottle()
        except Exception as e:
            print(f"[{self.timestamp}] [main] Error occurred while executing, check if all external components are available.")
            print(f"[{self.timestamp}] [main] Detailed log: {e}")

    def fileLimitChecker(self):
        try:
            capture_dir = os.path.join(base, "files", "captures")
            files = os.listdir(capture_dir)
            if len(files) > int(cfg['GENERIC']['MaxFileLimit']):
                a=input(f"[{self.timestamp}] [main] max file limit reached. remove all files? (y/n): ")
                if(a.lower() == "y"):
                    for file in files:
                        os.remove(os.path.join(capture_dir, file))
                    print(f"[{self.timestamp}] [main] All files deleted.")
        except OSError as e:
            print(f"[{self.timestamp}] [main] Error occurred while checking capture file limit. (OSError)")
            print(f"[{self.timestamp}] [main] Detailed log: {e}")

    def checkForBottle(self):
        while self.model.liveFeedCapture() == 1:
            print(f"[{self.timestamp}] [main] expected object not found, retrying..")
        print(f"[{self.timestamp}] [main] bottle found!")

if __name__ == "__main__":
    main = Main()