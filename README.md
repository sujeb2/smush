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

## cx_Freeze build
- Install Python 3.11.
- Run `build.bat` from Command Prompt on the target Windows machine.
- The distributable application is written to `dist\smush`.

## Windows 10 production run
- Open Windows PowerShell as the kiosk user.
- Run `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` once if local scripts are disabled.
- Run `.\run.ps1 -Build` for the first build and launch.
- Run `.\run.ps1` for later launches. It rebuilds automatically when `dist\smush\smush.exe` is missing.
- The runner requires an RTX 3050 and at least 8 GB of system memory, checks for a 24-inch panel when EDID data is available, and applies 1080x1920 FHD portrait mode to the primary display.
- Application options can be passed with `-ApplicationArguments`, for example `.\run.ps1 -ApplicationArguments "--demo","--skip-update"`.
