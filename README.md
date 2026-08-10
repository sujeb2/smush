# smushed!
- smush your plastic bottles and aluminum cans.

## before building
- check if `main_conf.ini` file configuration is correct with arduino serial port.
- check if `model_conf.ini` file configuration is correct with model configuration.

## requirement for building
- USB Camera
- Arudino UNO (or any type that can do serial transmitting)
- 1920x1080 FHD 24inch screen
- Any step motor that can do 50kg/cm torque
- 2 mini type conveyor

## recycling ui
- set the display orientation to portrait at 1080 x 1920 before starting the application.
- run `python main.py --demo --windowed` for a local test. press Space or Enter to simulate `Forwarded`, press F to preview fireworks, and press Escape to exit.
- run `python main.py --test-mode --windowed` to open the configuration test mode. add `--demo` to use keyboard controls without opening an Arduino serial port.
- use Up and Down to select, Enter to open or save, Left to return or cancel, and Backspace while editing text. Arduino messages `test_up`, `test_down`, and `test_back` provide navigation at the same time.
- set `Enabled=True` in the `[TEST_MODE]` section of `files/main_conf.ini` to start in test mode without the command-line option. A serial `RESET` received in test mode restarts the program.
- dependencies from `requirements.txt` are upgraded at startup while the update progress screen is visible. use `--skip-update` only for offline troubleshooting.
- run `python main.py --demo` to test the portrait fullscreen layout without serial or camera hardware.
- run `python main.py --demo --windowed --simulate-error dependency` or replace `dependency` with `arduino`, `webcam`, or `runtime` to test each error overlay.
- set `SkipSerialCheck=False` and update `SerialPort` in `files/main_conf.ini` for the installed system. `python main.py` then reads `Forwarded`, saves the count, and starts the detector.
- use `python gui.py --port <serial-port>` when only the serial-driven UI is needed.
- place A2Z and Novecento Sans Wide font files in `files/fonts` to bundle them. the UI detects those filenames automatically and uses the existing Korean font when a requested font is unavailable.
 
