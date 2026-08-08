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
- run `python main.py --demo` to test the portrait fullscreen layout without serial or camera hardware.
- set `SkipSerialCheck=False` and update `SerialPort` in `files/main_conf.ini` for the installed system. `python main.py` then reads `Forwarded`, saves the count, and starts the detector.
- use `python gui.py --port <serial-port>` when only the serial-driven UI is needed.
 
