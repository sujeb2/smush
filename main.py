import model, os, serial
import configparser as cfg

cfg = cfg.ConfigParser()
cfg.read('./files/main_conf.ini', encoding='utf-8')

class Main:
    def __init__(self):
        try:
            print(f"smush starting, config loaded: {cfg.sections()}")
            self.model = model.Model(cfg['GENERIC']['ModelPath'], cfg['GENERIC']['LabelsPath'])
            self.serial = serial.Serial(port=cfg['SERIAL']['SerialPort'], baudrate=cfg['SERIAL']['SerialBaudrate'], timeout=1)
            self.serial.open()
            if(not self.serial.is_open):
                print("Failed to find serial port thats avaliable from configuration. Is the device connected?")
                return
            print("Init done, waiting for serial.")
            self.serial_read()
        except:
            print("Failed to init, check if all external components are available.")

    def serial_read(self):
        #todo: add serial connection.
        pass

if __name__ == "__main__":
    main = Main()