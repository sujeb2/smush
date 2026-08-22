import sys

from cx_Freeze import Executable, setup


sys.setrecursionlimit(10000)

build_exe_options = {
    "include_files": [
        ("files/fonts", "files/fonts"),
        ("files/img", "files/img"),
        ("files/models", "files/models"),
        ("files/main_conf.ini", "files/main_conf.ini"),
        ("files/model_conf.ini", "files/model_conf.ini"),
        ("game/bgm", "game/bgm"),
        ("game/charts", "game/charts"),
        ("game/imgs", "game/imgs"),
        ("requirements.txt", "requirements.txt"),
    ],
    "includes": ["cv2", "model", "pygame"],
    "include_msvcr": True,
}

setup(
    name="smush",
    version="1.0.0",
    description="Plastic bottle and aluminum can recycling interface",
    options={"build_exe": build_exe_options},
    executables=[Executable("main.py", base="gui", target_name="smush")],
)
