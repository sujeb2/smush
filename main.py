import model, os
from datetime import datetime
import configparser as cfg

cfg = cfg.ConfigParser()
cfg.read('./files/main_conf.ini', encoding='utf-8')

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
            #self.serial_read()
            self.model.capture()
        except Exception as e:
            print(f"[{self.timestamp}] [main] Error occurred while executing, check if all external components are available.")
            print(f"[{self.timestamp}] [main] Detailed log: \n{e}")

    def fileLimitChecker(self):
        try:
            capture_dir = "./files/captures"
            files = os.listdir(capture_dir)
            if len(files) > int(cfg['GENERIC']['MaxFileLimit']):
                a=input(f"[{self.timestamp}] [main] max file limit reached. remove all files? (y/n): ")
                if(a.lower() == "y"):
                    for file in files:
                        os.remove(os.path.join(capture_dir, file))
                    print(f"[{self.timestamp}] [main] All files deleted.")
        except OSError as e:
            print(f"[{self.timestamp}] [main] Error occurred while checking capture file limit. (OSError)")
            print(f"[{self.timestamp}] [main] Detailed log: \n{e}")

if __name__ == "__main__":
    main = Main()