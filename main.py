import model, os, sys
from datetime import datetime
from serial_arduino import SerialIO
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
            self.serial = None
            print(f"[{self.timestamp}] [main] smush starting, config loaded: {cfg.sections()}")
            print(f"[{self.timestamp}] [main] model path: {cfg['GENERIC']['ModelPath']}")
            self.fileLimitChecker()
            if(cfg['GENERIC']['SkipSerialCheck'] == 'False'):
                self.serial = SerialIO(cfg['SERIAL']['SerialPort'], cfg['SERIAL']['SerialBaudrate'], timeout=cfg['SERIAL'].getint('SerialTimeout'))
                if(not self.serial.is_open):
                    print(f"[{self.timestamp}] [main] Failed to communicate with serial, please check if serial port configuration is correct.")
                    exit(1)
            self.model = model.Model(cfg['GENERIC']['ModelPath'], serial=self.serial)
            print(f"[{self.timestamp}] [main] Init done, waiting for serial..")
            self.model.liveFeedCapture()
            #if(cfg['GENERIC']['SkipToLiveFeed'] == 'True'):
            #    self.model.liveFeedCapture()
            #else: self.checkForBottle()
        except Exception as e:
            print(f"[{self.timestamp}] [main] Error occurred while executing, check if all external components are available.")
            print(f"[{self.timestamp}] [main] Detailed log: {e.with_traceback(e.__traceback__)}")

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