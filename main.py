import argparse
import configparser
import os
import sys
import threading
import time
from datetime import datetime

from dependency_updater import DependencyUpdateError, load_requirements, requirement_name, update_dependencies
from gui import RecyclingUI
from game.minigame import MinigameUI
from serial_arduino import SerialIO
from test_mode import TestModeUI

def find_compiled_dir():
    if "__compiled__" in globals() or getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
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
        self.model = None
        self.args = args
        print(f"[{self.timestamp}] [main] smush starting, config loaded: {config.sections()}")
        print(f"[{self.timestamp}] [main] model path: {config['GENERIC']['ModelPath']}")
        if self._minigame_enabled():
            self._run_minigame()
        elif self._test_mode_enabled():
            self._run_test_mode()
        elif self._ui_enabled():
            self._run_ui()
        else:
            self._run_headless()

    def _test_mode_enabled(self):
        return not self.args.headless and (
            self.args.test_mode or config.getboolean("TEST_MODE", "Enabled", fallback=False)
        )

    def _minigame_enabled(self):
        return not self.args.headless and (
            self.args.minigame or config.getboolean("MINIGAME", "Enabled", fallback=False)
        )

    def _run_minigame(self):
        fullscreen = config["UI"].getboolean("Fullscreen", fallback=True) and not self.args.windowed
        progress_file = config.get("MINIGAME", "ProgressFile", fallback="game/minigame_progress.json")
        self.ui = MinigameUI(
            os.path.join(base, "files", "main_conf.ini"),
            fullscreen=fullscreen,
            progress_path=os.path.join(base, progress_file),
        )
        self.ui.root.after(100, self._start_minigame_serial)
        print(f"[{self.timestamp}] [main] minigame visible")
        self.ui.run()

    def _start_minigame_serial(self):
        if self.args.demo:
            self.ui.post_status("demo mode: keyboard input ready")
            return
        if config["GENERIC"].getboolean("SkipSerialCheck"):
            self.ui.post_status("Arduino check skipped: keyboard input ready")
            return
        connector = threading.Thread(target=self._connect_minigame_serial, daemon=True, name="smush-minigame-serial")
        connector.start()

    def _connect_minigame_serial(self):
        try:
            self.serial = SerialIO(
                config["SERIAL"]["SerialPort"],
                config["SERIAL"]["SerialBaudrate"],
                timeout=config["SERIAL"].getint("SerialTimeout"),
            )
        except Exception as error:
            self.ui.post_status(f"Arduino unavailable: {error}")
            return
        self.ui.post_serial(self.serial)

    def _ui_enabled(self):
        return not self.args.headless and config["UI"].getboolean("Enabled", fallback=True)

    def _run_test_mode(self):
        fullscreen = config["UI"].getboolean("Fullscreen", fallback=True) and not self.args.windowed
        self.ui = TestModeUI(
            os.path.join(base, "files", "main_conf.ini"),
            os.path.join(base, "files", "model_conf.ini"),
            fullscreen=fullscreen,
            restart_callback=self._restart_program,
        )
        self.ui.root.after(100, self._start_test_mode_serial)
        print(f"[{self.timestamp}] [main] test mode visible")
        self.ui.run()

    def _start_test_mode_serial(self):
        if self.args.demo:
            self.ui.post_status("DEMO MODE: KEYBOARD READY")
            return
        if config["GENERIC"].getboolean("SkipSerialCheck"):
            self.ui.post_status("ARDUINO CHECK SKIPPED: KEYBOARD READY")
            return
        connector = threading.Thread(target=self._connect_test_mode_serial, daemon=True, name="smush-test-serial")
        connector.start()

    def _connect_test_mode_serial(self):
        try:
            self.serial = SerialIO(
                config["SERIAL"]["SerialPort"],
                config["SERIAL"]["SerialBaudrate"],
                timeout=config["SERIAL"].getint("SerialTimeout"),
            )
        except Exception as error:
            self.ui.post_status(f"ARDUINO UNAVAILABLE: {error}")
            return
        self.ui.post_serial(self.serial)

    def _restart_program(self):
        timestamp = datetime.now().strftime("%H:%M:%S")
        print(f"[{timestamp}] [main] RESET received, restarting smush")
        if self.ui.serial is not None:
            self.ui.serial.close()
        arguments = [sys.executable, *sys.argv]
        if "__compiled__" in globals() or getattr(sys, "frozen", False):
            arguments = [sys.executable, *sys.argv[1:]]
        os.execv(sys.executable, arguments)

    def _enter_test_mode(self):
        timestamp = datetime.now().strftime("%H:%M:%S")
        print(f"[{timestamp}] [main] test input received, opening test mode")
        if self.ui.serial is not None:
            self.ui.serial.close()
        arguments = [sys.executable, *sys.argv]
        if "__compiled__" in globals() or getattr(sys, "frozen", False):
            arguments = [sys.executable, *sys.argv[1:]]
        if "--test-mode" not in arguments:
            arguments.append("--test-mode")
        os.execv(sys.executable, arguments)

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
            initial_count=initial_count,
            fullscreen=fullscreen,
            serial_message=ui_config.get("SerialMessage", fallback="Forwarded"),
            count_file=None if self.args.demo else count_file,
            test_mode_callback=self._enter_test_mode,
        )
        self.ui.root.after(100, self._start_initialization)
        print(f"[{self.timestamp}] [main] ui dependency update screen visible")
        self.ui.run()

    def _start_initialization(self):
        initializer = threading.Thread(target=self._startup_sequence, daemon=True, name="smush-initializer")
        initializer.start()

    def _startup_sequence(self):
        try:
            update_config = config["UPDATE"]
            update_enabled = (
                update_config.getboolean("Enabled", fallback=True)
                and not self.args.skip_update
                and not getattr(sys, "frozen", False)
            )
            if not update_enabled:
                self.ui.post_update(100, "UPDATE SKIPPED")
                time.sleep(0.4)
            elif self.args.demo:
                requirements = load_requirements(os.path.join(base, "requirements.txt"))
                total = max(1, len(requirements))
                self.ui.post_update(0, "CHECKING DEPENDENCIES")
                for index, requirement in enumerate(requirements):
                    if self.args.simulate_error == "dependency" and index == max(1, total // 2):
                        raise DependencyUpdateError(f"{requirement_name(requirement)} update failed")
                    self.ui.post_update(round(index / total * 100), f"UPDATING {requirement_name(requirement).upper()}")
                    time.sleep(0.1)
                    self.ui.post_update(round((index + 1) / total * 100), f"{requirement_name(requirement).upper()} UPDATED")
                self.ui.post_update(100, "UPDATE COMPLETE")
                time.sleep(0.4)
            else:
                update_dependencies(
                    os.path.join(base, "requirements.txt"),
                    self._dependency_progress,
                    timeout=update_config.getint("Timeout", fallback=900),
                )
                time.sleep(0.4)
        except Exception as error:
            self.ui.post_error(
                "DEPENDENCY_UPDATE_FAILED",
                f"CANNOT UPDATE REQUIRED DEPENDENCIES.\nCHECK NETWORK CONNECTION AND PYTHON PERMISSIONS.\n{error}",
            )
            return
        self._initialize_components()

    def _dependency_progress(self, progress, status):
        timestamp = datetime.now().strftime("%H:%M:%S")
        print(f"[{timestamp}] [updater] {progress}% {status}")
        self.ui.post_update(progress, status)

    def _initialize_components(self):
        started = time.monotonic()
        startup_lines = []

        def status(message):
            startup_lines.append(message)
            self.ui.post_startup("\n".join(startup_lines))
            timestamp = datetime.now().strftime("%H:%M:%S")
            print(f"[{timestamp}] [main] {message}")

        try:
            status("start smush interface...")
            os.makedirs(os.path.join(base, "files", "captures"), exist_ok=True)
            if self.args.demo:
                status("Demo mode enabled.")
                self._wait_for_startup(started)
                if self.args.simulate_error == "arduino":
                    self.ui.post_error("ARDUINO_CONNECTION_LOST", f"CANNOT COMMUNICATE WITH ARDUINO.\nCHECK USB CABLE AND RESTART THE PROGRAM.")
                elif self.args.simulate_error == "webcam":
                    self.ui.post_error("WEBCAM_NOT_FOUND", f"CANNOT FIND COMPATIBLE WEBCAM.\nCHECK CONNECTION AND RESTART THE PROGRAM.")
                elif self.args.simulate_error == "runtime":
                    self.ui.post_error("RUNTIME_FAILURE", f"AN UNEXPECTED ERROR HAS OCCURRED.\nMORE INFORMATION IS PROVIDED IN THE CONSOLE, PLEASE RESTART THE MACHINE.")
                else:
                    status("Initialization complete.")
                    self.ui.post_ready()
                return
            if config["GENERIC"].getboolean("SkipSerialCheck"):
                status("Arduino check skipped by configuration.")
            else:
                status("Checking Arduino connection...")
                try:
                    self.serial = SerialIO(
                        config["SERIAL"]["SerialPort"],
                        config["SERIAL"]["SerialBaudrate"],
                        timeout=config["SERIAL"].getint("SerialTimeout"),
                    )
                except Exception as error:
                    self.ui.post_error(
                        "ARDUINO_NOT_FOUND",
                        f"CANNOT OPEN PORT IN {config['SERIAL']['SerialPort']}.\n{error}",
                    )
                    return
                self.ui.post_serial(self.serial)
                status("Arduino connected.")
            status("Checking webcam connection...")
            webcam_error = self._check_webcam()
            if webcam_error is not None:
                self.ui.post_error("WEBCAM_NOT_FOUND", webcam_error)
                return
            status("Webcam connected.")
            if self.serial is None:
                self._wait_for_startup(started)
                status("Initialization complete without Arduino.")
                self.ui.post_ready()
                return
            status("Loading recognition model...")
            try:
                import model

                self.model = model.Model(config["GENERIC"]["ModelPath"], serial=self.serial)
                if not hasattr(self.model, "vc") or not self.model.vc.isOpened():
                    raise RuntimeError("webcam initialization failed in recognition model")
            except BaseException as error:
                self.ui.post_error("MODEL_INITIALIZATION_FAILED", str(error).upper())
                return
            self._wait_for_startup(started)
            status("Initialization complete.")
            self.ui.post_ready()
            result = self.model.liveFeedCapture()
            if result == 1 and self.ui.running:
                self.ui.post_error("WEBCAM_STREAM_LOST", "The webcam stopped providing frames.\nCheck the camera connection and restart SMUSH.".upper())
        except BaseException as error:
            if self.ui.running:
                self.ui.post_error("RUNTIME_FAILURE", str(error))

    def _check_webcam(self):
        camera = None
        try:
            import cv2

            camera = cv2.VideoCapture(0)
            if not camera.isOpened():
                return "Webcam could not be opened.\nCheck the connection and camera permission.".upper()
            available, frame = camera.read()
            if not available or frame is None:
                return "Webcam opened but no image was received.\nCheck whether another application is using it.".upper()
            return None
        except Exception as error:
            return str(error)
        finally:
            if camera is not None:
                camera.release()

    def _wait_for_startup(self, started):
        remaining = 1.2 - (time.monotonic() - started)
        if remaining > 0:
            time.sleep(remaining)

    def _run_headless(self):
        try:
            self.file_limit_checker()
            if not self.args.demo and not config["GENERIC"].getboolean("SkipSerialCheck"):
                self.serial = SerialIO(
                    config["SERIAL"]["SerialPort"],
                    config["SERIAL"]["SerialBaudrate"],
                    timeout=config["SERIAL"].getint("SerialTimeout"),
                )
            import model

            self.model = model.Model(config["GENERIC"]["ModelPath"], serial=self.serial)
            self.model.liveFeedCapture()
        except BaseException as error:
            print(f"[{self.timestamp}] [main] Error occurred while executing, check if all external components are available.")
            print(f"[{self.timestamp}] [main] Detailed log: {error}")

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
    parser.add_argument("--simulate-error", choices=("dependency", "arduino", "webcam", "runtime"))
    parser.add_argument("--skip-update", action="store_true")
    parser.add_argument("--test-mode", action="store_true")
    parser.add_argument("--minigame", action="store_true")
    return parser.parse_args()

if __name__ == "__main__":
    Main(parse_args())
