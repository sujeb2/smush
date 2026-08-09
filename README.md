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
- dependencies from `requirements.txt` are upgraded at startup while the update progress screen is visible. use `--skip-update` only for offline troubleshooting.
- run `python main.py --demo` to test the portrait fullscreen layout without serial or camera hardware.
- run `python main.py --demo --windowed --simulate-error dependency` or replace `dependency` with `arduino`, `webcam`, or `runtime` to test each error overlay.
- set `SkipSerialCheck=False` and update `SerialPort` in `files/main_conf.ini` for the installed system. `python main.py` then reads `Forwarded`, saves the count, and starts the detector.
- use `python gui.py --port <serial-port>` when only the serial-driven UI is needed.
- place A2Z and Novecento Sans Wide font files in `files/fonts` to bundle them. the UI detects those filenames automatically and uses the existing Korean font when a requested font is unavailable.
 
