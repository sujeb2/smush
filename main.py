import model, serial
from datetime import datetime
import configparser as cfg

cfg = cfg.ConfigParser()
cfg.read('./files/main_conf.ini', encoding='utf-8')

class Main:
    def __init__(self):
        try:
            self.timestamp = datetime.now().strftime('%H:%M:%S')
            print(f"[{self.timestamp}] [main] smush starting, config loaded: {cfg.sections()}")
            print(f"[{self.timestamp}] [main] model path: {cfg['GENERIC']['ModelPath']}, labels path: {cfg['GENERIC']['LabelsPath']}")
            self.model = model.Model(cfg['GENERIC']['ModelPath'], cfg['GENERIC']['LabelsPath'])
            #self.serial = serial.Serial(port=cfg['SERIAL']['SerialPort'], baudrate=cfg['SERIAL']['SerialBaudrate'], timeout=1)
            #self.serial.open()
            #if(not self.serial.is_open):
            #    print(f"[{self.timestamp}] [main] Failed to find serial port thats avaliable from configuration. Is the device connected?")
            print(f"[{self.timestamp}] [main] Init done, waiting for serial..")
            #self.serial_read()
            self.model.camera_capture()
        except Exception as e:
            print(f"[{self.timestamp}] [main] Error occurred while executing, check if all external components are available.")
            print(f"[{self.timestamp}] [main] Detailed log: \n{e}")

    def serial_read(self):
        while True:
            if self.serial.in_waiting > 0:
                line = self.serial.readline().decode('utf-8').rstrip()
                print(f"[{self.timestamp}] [main] read: {line}")

                if line != "1": # invalid signal
                    print(f"[{self.timestamp}] [main] read unknown signal.")
                    return
                
                result = self.model.capture()
                match result: #sample return
                    case "can":
                        print(f"[{self.timestamp}] [main] model detected: can")
                        break
                    case "plastic":
                        print(f"[{self.timestamp}] [main] model detected: plastic")
                        break
                    case _:
                        break

if __name__ == "__main__":
    main = Main()