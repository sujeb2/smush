import argparse
import configparser
import os
import sys
import threading
from datetime import datetime

from gui import RecyclingUI
from serial_arduino import SerialIO


def find_compiled_dir():
    if "__compiled__" in globals():
        return os.path.dirname(os.path.abspath(sys.argv[0]))
    return os.path.dirname(os.path.abspath(__file__))


base = find_compiled_dir()
config = configparser.ConfigParser()
config.read(os.path.join(base, "files", "main_conf.ini"), encoding="utf-8")


def load_count(path, fallback):
    try:
        with open(path, "r", encoding="utf-8") as file:
            return int(file.read().strip())
    except (OSError, ValueError):
        return fallback


class Main:
    def __init__(self, args):
        self.timestamp = datetime.now().strftime("%H:%M:%S")
        self.serial = None
        self.args = args
        try:
            print(f"[{self.timestamp}] [main] smush starting, config loaded: {config.sections()}")
            print(f"[{self.timestamp}] [main] model path: {config['GENERIC']['ModelPath']}")
            self.file_limit_checker()
            if not args.demo and not config["GENERIC"].getboolean("SkipSerialCheck"):
                self.serial = SerialIO(
                    config["SERIAL"]["SerialPort"],
                    config["SERIAL"]["SerialBaudrate"],
                    timeout=config["SERIAL"].getint("SerialTimeout"),
                )
                if not self.serial.is_open:
                    print(f"[{self.timestamp}] [main] Failed to communicate with serial, please check if serial port configuration is correct.")
                    raise SystemExit(1)
            if self._ui_enabled():
                self._run_ui()
            else:
                self._run_model()
        except SystemExit:
            raise
        except Exception as error:
            print(f"[{self.timestamp}] [main] Error occurred while executing, check if all external components are available.")
            print(f"[{self.timestamp}] [main] Detailed log: {error.with_traceback(error.__traceback__)}")

    def _ui_enabled(self):
        return not self.args.headless and config["UI"].getboolean("Enabled", fallback=True)

    def _run_ui(self):
        ui_config = config["UI"]
        count_file = os.path.join(base, ui_config.get("CountFile", fallback="files/recycle_count.txt"))
        initial_count = self.args.count
        if initial_count is None:
            initial_count = ui_config.getint("InitialCount", fallback=0)
        if not self.args.demo:
            initial_count = load_count(count_file, initial_count)
        fullscreen = ui_config.getboolean("Fullscreen", fallback=True) and not self.args.windowed
        self.ui = RecyclingUI(
            serial_io=self.serial,
            initial_count=initial_count,
            fullscreen=fullscreen,
            serial_message=ui_config.get("SerialMessage", fallback="Forwarded"),
            count_file=count_file if self.serial is not None else None,
        )
        if self.serial is not None:
            detector_thread = threading.Thread(target=self._run_model, daemon=True, name="smush-detector")
            detector_thread.start()
        else:
            print(f"[{self.timestamp}] [main] demo mode started")
        print(f"[{self.timestamp}] [main] ui started, waiting for serial message: {ui_config.get('SerialMessage', fallback='Forwarded')}")
        self.ui.run()

    def _run_model(self):
        import model

        self.model = model.Model(config["GENERIC"]["ModelPath"], serial=self.serial)
        self.model.liveFeedCapture()

    def file_limit_checker(self):
        try:
            capture_dir = os.path.join(base, "files", "captures")
            os.makedirs(capture_dir, exist_ok=True)
            files = os.listdir(capture_dir)
            if len(files) > int(config["GENERIC"]["MaxFileLimit"]):
                answer = input(f"[{self.timestamp}] [main] max file limit reached. remove all files? (y/n): ")
                if answer.lower() == "y":
                    for file in files:
                        os.remove(os.path.join(capture_dir, file))
                    print(f"[{self.timestamp}] [main] All files deleted.")
        except OSError as error:
            print(f"[{self.timestamp}] [main] Error occurred while checking capture file limit. (OSError)")
            print(f"[{self.timestamp}] [main] Detailed log: {error}")


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--windowed", action="store_true")
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--count", type=int)
    return parser.parse_args()


if __name__ == "__main__":
    Main(parse_args())
