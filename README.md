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

- `F6`: led test renderer
- `F8`: toggle autoplay for 2K, 4K, and catch gameplay.
- `-`: open the original test-mode interface.

## 4K EXTRA charts

4K EXTRA is available through the earned EXTRA challenge only, with no health bar or early failure.
The challenge requires S or X ranks on the first two stages in demo mode, or all three stages in normal mode.
Place charts in `game/charts/extrastage`; they do not appear in normal mode selection.
Use osu!mania `CircleSize:6` for four center lanes plus two smaller side lanes.
From left to right, chart lanes map to BTN1, the four existing keys, and BTN2.
Keyboard controls are `A`, `D`, `F`, `J`, `K`, `L` in that order; the arrow keys still control the four center lanes.
Existing `CircleSize:4` EXTRA charts use the center lanes without adding side notes.
The NEXT screen displays the chart's osu `Creator` metadata below its level.
