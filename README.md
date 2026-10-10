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
- `F8`: toggle autoplay for 4K and catch gameplay.
- `-`: open the original test-mode interface.

## sensor IO software reset

- Flash `hardware/arduino/sensor_io/sensor_io.ino` to a classic AVR Arduino, such as an Uno R3.
- Send `reset_soft` followed by a newline at 9600 baud (Serial Monitor: **Newline** or **Both NL & CR**), or call `sensor_io.write_command("reset_soft")` on the corresponding `SerialIO` instance.
- The board stops the crusher and conveyor, replies `resetting`, and reboots through the watchdog. Startup then runs the crusher backward for `MOTOR_RESET_TIME` (3000 ms) before accepting detection commands. This is a timed return, without position feedback.

Detection commands (`obj1_detect` or `obj2_detect`, followed by a newline) run the conveyor for `CONV_FORWARD_FOR` (6500 ms). Once the conveyor stops, the crusher runs forward for `MOTOR_RUNNING_FOR`, pauses for `MOTOR_BRAKE_FOR`, and returns backward for `MOTOR_RUNNING_FOR`. Further detections are rejected until the cycle and stop interval finish; `reset_soft` remains available throughout.

## Conveyor stepper wiring

The sensor IO firmware controls **one four-wire bipolar stepper using both bridges of one L298N**, replacing the previous two-DC-motor `L298NX2` control. Both object commands run this same motor. Keep `ConveyorStepper.h` beside `sensor_io.ino` when opening or copying the sketch. The TM1637 display library is still required; L298N library installation is no longer required for this sketch.

With the 12 V supply and Arduino USB disconnected, wire:

| Arduino / motor | L298N |
| --- | --- |
| D8 | IN1 |
| D9 | IN2 |
| D10 | IN3 |
| D11 | IN4 |
| D12 | ENA, with the ENA jumper removed |
| D13 | ENB, with the ENB jumper removed |
| One complete motor coil pair | OUT1 and OUT2 |
| Other complete motor coil pair | OUT3 and OUT4 |
| Arduino GND and DC supply negative | GND |
| DC supply positive | Motor supply terminal marked 12V |

ENA/ENB jumpers are separate from the module's 5V regulator jumper. Follow your specific module's instructions for the regulator and 5V logic supply; do not connect 12 V to a 5V terminal. Identify coil pairs with resistance measurements, not wire colors.

The controller generates nonblocking half steps by default (`CONV_HALF_STEP = true`) to reduce the size of each movement. `CONV_STEPS_PER_SECOND` remains a **full-step-equivalent rate** (currently 300): half-step mode emits twice as many steps for the same nominal shaft speed. For a 200-full-step/revolution motor, 300 means approximately 90 RPM. This is a step rate, not PWM or a current setting. A startup ramp shortens the step interval from `CONV_START_STEPS_PER_SECOND` (50 full steps/s) toward the target over `CONV_RAMP_MS` (1000 ms). It is not constant acceleration. Set `CONV_HALF_STEP` to `false` for two-phase full steps, or `CONV_RAMP_MS` to zero to disable the ramp. Half-stepping alternates one and two energized coils without current compensation, so torque can vary; it cannot guarantee smooth running or fix incorrect wiring/current. The ramp helps startup, not resonance during steady running.

Set `CONV_REVERSE` to `true` if the conveyor turns the wrong way. The controller releases both coils at boot, on timed stop, and before software reset. Serial reset remains responsive; delayed loop updates do not generate a burst of catch-up steps. The 6500 ms conveyor duration includes the ramp, so a run travels slightly less than starting instantly at the target rate.