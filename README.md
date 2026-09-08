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

## minigame debug controls

- Run `python -m lededitor` (or `python main.py --led-editor`) to edit button LED animations.
- Select any minigame scene, add timed steps, and click the four preview lamps to toggle their ON/OFF values. Use Play and the scrubber to preview the timeline; Save applies it to the game within one second.
- Files are stored in `files/led_animations.json`. Each scene restarts its assigned timeline on entry. Looping timelines repeat; non-looping timelines hold their final state. The bundled game/demonstration timeline is a four-button chase.
- Run `python main.py --minigame --demo --windowed` and press `F6` in any scene to toggle the LED preview. The preview stays visible across scene transitions. Demo mode previews without hardware output. Normal mode sends changes through the Arduino switch LED protocol (pins 6–9).

- `F8`: toggle autoplay for 2K, 4K, and catch gameplay.
- `-`: open the original test-mode interface.
