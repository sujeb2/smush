import model, os, serial
from datetime import datetime
import configparser as cfg

cfg = cfg.ConfigParser()
cfg.read('./files/main_conf.ini', encoding='utf-8')

class Main:
    def __init__(self):
        try:
            self.timestamp = datetime.now().strftime('%H:%M:%S')
            print(f"[{self.timestamp}] [main] smush starting, config loaded: {cfg.sections()}")
            self.model = model.Model(cfg['GENERIC']['ModelPath'], cfg['GENERIC']['LabelsPath'])
            self.serial = serial.Serial(port=cfg['SERIAL']['SerialPort'], baudrate=cfg['SERIAL']['SerialBaudrate'], timeout=1)
            self.serial.open()
            if(not self.serial.is_open):
                print(f"[{self.timestamp}] [main] Failed to find serial port thats avaliable from configuration. Is the device connected?")
                return
            print(f"[{self.timestamp}] [main] Init done, waiting for serial..")
            self.serial_read()
        except:
            print(f"[{self.timestamp}] [main] Failed to init, check if all external components are available.")

    def serial_read(self):
        while True:
            if self.serial.in_waiting > 0:
                line = self.serial.readline().decode('utf-8').rstrip()
                print(f"[{self.timestamp}] [main] read: {line}")

                if line != "1": # invalid signal
                    print(f"[{self.timestamp}] [main] read unknown signal.")
                    return
                
                result = self.model.capture()
                match result:
                    case "": #todo: add model name
                        pass

if __name__ == "__main__":
    main = Main()