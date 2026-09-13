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

Four RGB NeoPixels can pulse with chart BPM, with colors and timing editable
in `python3 -m lededitor` → **NeoPixel / BPM groove**. Enable the output and
save to apply it to the game. See [wiring, firmware and editor instructions](hardware/arduino/test_io/README.md).

The title preset uses a scrolling rainbow at 100% brightness. In `rainbow`
mode, beats per rainbow step controls scrolling speed (2 is half speed);
four steps complete a cycle. The title uses Preview / menu BPM. Restart the
game and editor after code updates; demo mode only previews LEDs on screen.

Beat-mode LEDs use the selected song's BPM during music selection (including
difficulty selection and the next-song screen). Once the preview starts,
they follow its playback offset and timing-point BPM changes. Before playback
starts, they pulse at the tempo at the selected song's preview offset. The
editor/menu BPM is only a fallback for charts without timing data in these
scenes; title effects and other menu scenes retain their configured menu BPM.
