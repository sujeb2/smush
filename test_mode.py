import configparser
import glob
import os
import queue
import re
import tempfile
from dataclasses import dataclass

from ui_framework import CanvasUIFramework, DESIGN_HEIGHT, DESIGN_WIDTH, find_compiled_dir


ROOT_GROUPS = (
    "GENERIC SETUP",
    "SERIAL SETUP",
    "MOTOR SETUP",
    "MODEL CONFIGURATION",
)

SERIAL_COMMANDS = ("reset", "test_up", "test_down", "test_back")


def split_serial_commands(buffer, message):
    data = (buffer + message.lower()).replace("\r", "").replace("\n", "")
    commands = []
    while data:
        matches = [(data.find(command), command) for command in SERIAL_COMMANDS if data.find(command) >= 0]
        if not matches:
            keep = max(len(command) for command in SERIAL_COMMANDS) - 1
            return data[-keep:], commands
        position, command = min(matches, key=lambda match: match[0])
        commands.append(command)
        data = data[position + len(command):]
    return "", commands


def setting_kind(value):
    if value.casefold() in ("true", "false"):
        return "boolean"
    if re.fullmatch(r"[+-]?\d+", value):
        return "integer"
    if re.fullmatch(r"[+-]?(?:\d+\.\d*|\d*\.\d+)", value):
        return "float"
    return "text"


def display_label(value):
    words = re.sub(r"(?<!^)(?=[A-Z])", " ", value).replace("_", " ")
    return " ".join(words.upper().split())


def update_config_value(path, section, option, value):
    with open(path, "r", encoding="utf-8") as file:
        lines = file.readlines()
    section_pattern = re.compile(rf"^\s*\[{re.escape(section)}\]\s*$", re.IGNORECASE)
    option_pattern = re.compile(rf"^(\s*{re.escape(option)}\s*=\s*).*$", re.IGNORECASE)
    active_section = False
    replaced = False
    for index, line in enumerate(lines):
        stripped = line.rstrip("\r\n")
        if stripped.lstrip().startswith("["):
            active_section = bool(section_pattern.match(stripped))
            continue
        if active_section:
            match = option_pattern.match(stripped)
            if match:
                newline = "\r\n" if line.endswith("\r\n") else "\n"
                lines[index] = f"{match.group(1)}{value}{newline}"
                replaced = True
                break
    if not replaced:
        raise KeyError(f"{section}.{option}")
    directory = os.path.dirname(path)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=directory, delete=False) as file:
        file.writelines(lines)
        temporary_path = file.name
    os.replace(temporary_path, path)


@dataclass
class ConfigSetting:
    path: str
    source: str
    section: str
    option: str
    value: str

    @property
    def kind(self):
        return setting_kind(self.value)

    @property
    def label(self):
        parts = [part for part in (self.source, self.section, display_label(self.option)) if part]
        return " / ".join(parts)

    @property
    def display_value(self):
        if self.kind == "boolean":
            return "ON" if self.value.casefold() == "true" else "OFF"
        return self.value


class ConfigRepository:
    def __init__(self, main_path, model_path):
        self.main_path = main_path
        self.model_path = model_path
        self.groups = {group: [] for group in ROOT_GROUPS}
        self._load()

    def _read(self, path):
        parser = configparser.ConfigParser()
        parser.optionxform = str
        parser.read(path, encoding="utf-8")
        return parser

    def _add_sections(self, group, path, parser, sections, source=""):
        for section in sections:
            if not parser.has_section(section):
                continue
            for option, value in parser.items(section):
                self.groups[group].append(ConfigSetting(path, source, section, option, value))

    def _load(self):
        main = self._read(self.main_path)
        model = self._read(self.model_path)
        self._add_sections("GENERIC SETUP", self.main_path, main, ("GENERIC", "UI", "UPDATE", "TEST_MODE"))
        self._add_sections("SERIAL SETUP", self.main_path, main, ("SERIAL",), "APP")
        self._add_sections("SERIAL SETUP", self.model_path, model, ("SERIAL",), "MODEL")
        self._add_sections("MOTOR SETUP", self.main_path, main, ("MOTOR",))
        self._add_sections("MODEL CONFIGURATION", self.model_path, model, ("GENERIC", "DETECTION"))

    def save(self, setting, value):
        update_config_value(setting.path, setting.section, setting.option, value)
        setting.value = value

    def choices(self, setting):
        option = setting.option.casefold()
        if setting.kind == "boolean":
            return ("False", "True")
        if "baud" in option:
            return ("9600", "19200", "38400", "57600", "115200")
        if option in ("serialport", "port", "motorserialport"):
            ports = [setting.value, *glob.glob("/dev/cu.*"), *(f"COM{index}" for index in range(1, 10))]
            return tuple(dict.fromkeys(ports))
        if option == "modelpath":
            models = glob.glob(os.path.join(os.path.dirname(self.main_path), "models", "*"))
            relative = [os.path.relpath(path, os.path.dirname(os.path.dirname(self.main_path))) for path in models]
            return tuple(dict.fromkeys((setting.value, *relative)))
        return ()


class TestModeUI(CanvasUIFramework):
    def __init__(self, main_config_path, model_config_path, fullscreen=True, restart_callback=None):
        self.repository = ConfigRepository(main_config_path, model_config_path)
        self.settings = self._load_ui_settings(main_config_path)
        super().__init__(self.settings["title"], fullscreen=fullscreen)
        self.restart_callback = restart_callback
        self.event_queue = queue.Queue()
        self.serial_buffer = ""
        self.serial_status = "KEYBOARD READY"
        self.level = "root"
        self.group_index = 0
        self.setting_index = 0
        self.edit_setting = None
        self.edit_value = ""
        self.edit_choices = ()
        self.edit_choice_index = 0
        self.replace_edit_value = False
        self.scene_photos = []
        self.root.bind("<KeyPress>", self._handle_key)
        self.root.after(0, self._build_scene)
        self.root.after(50, self._poll_serial)
        self.root.after(50, self._poll_events)

    def _load_ui_settings(self, path):
        parser = configparser.ConfigParser()
        parser.read(path, encoding="utf-8")
        section = parser["TEST_MODE"] if parser.has_section("TEST_MODE") else {}
        return {
            "title": section.get("Title", "TEST MODE"),
            "background": section.get("BackgroundColor", "#080808"),
            "text": section.get("TextColor", "#FFFFFF"),
            "selected": section.get("SelectedColor", "#00ECFF"),
            "disabled": section.get("DisabledColor", "#545454"),
            "title_y": int(section.get("TitleY", 120)),
            "menu_y": int(section.get("MenuStartY", 780)),
            "spacing": int(section.get("MenuSpacing", 74)),
            "footer_root": section.get("FooterRoot", "UP / DOWN : MENU SELECT, ENTER : OPEN, SW1+SW2 (10S) : RESET"),
            "footer_menu": section.get("FooterMenu", "UP / DOWN : MENU SELECT, ENTER : EDIT, SW1+SW2 : BACK"),
        }

    def post_serial(self, serial_io):
        self.event_queue.put(("serial", serial_io))

    def post_status(self, status):
        self.event_queue.put(("status", status))

    def _handle_key(self, event):
        if event.keysym == "Up":
            self.move_selection(-1)
        elif event.keysym == "Down":
            self.move_selection(1)
        elif event.keysym in ("Return", "KP_Enter"):
            self.activate_selection()
        elif event.keysym == "Left":
            self.go_back()
        elif event.keysym == "BackSpace":
            if self.level == "edit" and self.edit_setting.kind == "text" and not self.edit_choices:
                self.edit_value = self.edit_value[:-1]
                self.replace_edit_value = False
                self._build_scene()
            else:
                self.go_back()
        elif self.level == "edit" and self.edit_setting.kind == "text" and not self.edit_choices and event.char and event.char.isprintable():
            if self.replace_edit_value:
                self.edit_value = ""
                self.replace_edit_value = False
            self.edit_value += event.char
            self._build_scene()

    def move_selection(self, direction):
        if self.level == "root":
            self.group_index = (self.group_index + direction) % len(ROOT_GROUPS)
        elif self.level == "group":
            settings = self.repository.groups[ROOT_GROUPS[self.group_index]]
            if settings:
                self.setting_index = (self.setting_index + direction) % len(settings)
        elif self.edit_choices:
            self.edit_choice_index = (self.edit_choice_index + direction) % len(self.edit_choices)
            self.edit_value = self.edit_choices[self.edit_choice_index]
        elif self.edit_setting.kind == "integer":
            self.edit_value = str(int(self.edit_value) + direction)
        elif self.edit_setting.kind == "float":
            self.edit_value = f"{float(self.edit_value) + direction * 0.1:.2f}".rstrip("0").rstrip(".")
        self._build_scene()

    def activate_selection(self):
        if self.level == "root":
            self.level = "group"
            self.setting_index = 0
        elif self.level == "group":
            settings = self.repository.groups[ROOT_GROUPS[self.group_index]]
            if not settings:
                return
            self.edit_setting = settings[self.setting_index]
            self.edit_choices = self.repository.choices(self.edit_setting)
            self.edit_value = self.edit_setting.value
            if self.edit_choices:
                matches = [
                    index for index, choice in enumerate(self.edit_choices)
                    if choice.casefold() == self.edit_value.casefold()
                ]
                self.edit_choice_index = matches[0] if matches else 0
                self.edit_value = self.edit_choices[self.edit_choice_index]
            self.replace_edit_value = self.edit_setting.kind == "text" and not self.edit_choices
            self.level = "edit"
        else:
            self.repository.save(self.edit_setting, self.edit_value)
            self.serial_status = f"SAVED {self.edit_setting.label}"
            self.level = "group"
            self.edit_setting = None
            self.edit_choices = ()
        self._build_scene()

    def go_back(self):
        if self.level == "edit":
            self.level = "group"
            self.edit_setting = None
            self.edit_choices = ()
        elif self.level == "group":
            self.level = "root"
        self._build_scene()

    def _build_scene(self):
        if not self.running:
            return
        self._prepare_scene()
        self.scene_photos = []
        self.canvas.create_rectangle(
            self._x(0),
            self._y(0),
            self._x(DESIGN_WIDTH),
            self._y(DESIGN_HEIGHT),
            fill=self.settings["background"],
            outline="",
        )
        if self.level == "root":
            self._build_root_menu()
        elif self.level == "group":
            self._build_group_menu()
        else:
            self._build_edit_menu()

    def _place_text(self, text, x, y, size=34, color=None, anchor="center", align="center"):
        photo = self._text_photo(
            text,
            size,
            color=color or self.settings["text"],
            font_path=self.novecento_demibold_font_path,
            align=align,
        )
        self.scene_photos.append(photo)
        self.canvas.create_image(self._x(x), self._y(y), image=photo, anchor=anchor)

    def _build_header(self, title):
        self._place_text(title, 540, self.settings["title_y"], 40)
        self._place_text(self.serial_status, 540, 205, 20, self.settings["disabled"])

    def _build_root_menu(self):
        self._build_header(self.settings["title"])
        start_y = self.settings["menu_y"]
        spacing = self.settings["spacing"]
        for index, group in enumerate(ROOT_GROUPS):
            color = self.settings["selected"] if index == self.group_index else self.settings["text"]
            self._place_text(group, 540, start_y + index * spacing, 32, color)
        self._place_text(self.settings["footer_root"], 540, 1815, 19)

    def _visible_settings(self):
        settings = self.repository.groups[ROOT_GROUPS[self.group_index]]
        page_size = 12
        start = self.setting_index // page_size * page_size
        return start, settings[start:start + page_size]

    def _build_group_menu(self):
        group = ROOT_GROUPS[self.group_index]
        self._build_header(group)
        start, settings = self._visible_settings()
        total = len(self.repository.groups[group])
        page = start // 12 + 1
        pages = max(1, (total + 11) // 12)
        self._place_text(f"{page} / {pages}", 540, 290, 18, self.settings["disabled"])
        start_y = 450
        spacing = 92
        for row, setting in enumerate(settings):
            selected = start + row == self.setting_index
            color = self.settings["selected"] if selected else self.settings["text"]
            value_color = color if setting.display_value else self.settings["disabled"]
            value = setting.display_value
            if len(value) > 32:
                value = f"...{value[-29:]}"
            self._place_text(setting.label, 110, start_y + row * spacing, 23, color, anchor="w", align="left")
            self._place_text(value, 970, start_y + row * spacing, 23, value_color, anchor="e", align="right")
        self._place_text(self.settings["footer_menu"], 540, 1815, 19)

    def _build_edit_menu(self):
        self._build_header(self.edit_setting.label)
        value = self.edit_value
        if self.edit_setting.kind == "boolean":
            value = "ON" if value.casefold() == "true" else "OFF"
        if len(value) > 42:
            value = f"...{value[-39:]}"
        self._place_text(value, 540, 850, 38, self.settings["selected"])
        if self.edit_choices:
            instruction = "UP / DOWN : CHANGE, ENTER : SAVE, LEFT : CANCEL"
        elif self.edit_setting.kind in ("integer", "float"):
            instruction = "UP / DOWN : ADJUST, ENTER : SAVE, LEFT : CANCEL"
        else:
            instruction = "TYPE VALUE, BACKSPACE : DELETE, ENTER : SAVE, LEFT : CANCEL"
        self._place_text(instruction, 540, 1815, 19)

    def _poll_events(self):
        if not self.running:
            return
        try:
            while True:
                event = self.event_queue.get_nowait()
                if event[0] == "serial":
                    self.attach_serial(event[1])
                    self.serial_status = "ARDUINO CONNECTED"
                elif event[0] == "status":
                    self.serial_status = event[1]
                self._build_scene()
        except queue.Empty:
            pass
        self.root.after(50, self._poll_events)

    def _poll_serial(self):
        if not self.running:
            return
        if self.serial is not None:
            try:
                while self.serial.in_waiting > 0:
                    message = self.serial.read()
                    if message is not None:
                        self._consume_serial(message)
            except Exception as error:
                failed_serial = self.serial
                self.serial = None
                try:
                    failed_serial.close()
                except Exception:
                    pass
                self.serial_status = f"ARDUINO DISCONNECTED: {error}"
                self._build_scene()
        self.root.after(50, self._poll_serial)

    def _consume_serial(self, message):
        self.serial_buffer, commands = split_serial_commands(self.serial_buffer, message)
        for command in commands:
            if command == "reset":
                if self.restart_callback is not None:
                    self.restart_callback()
                return
            if command == "test_up":
                self.move_selection(-1)
            elif command == "test_down":
                self.move_selection(1)
            elif command == "test_back":
                self.go_back()


def default_config_paths():
    base = find_compiled_dir()
    return os.path.join(base, "files", "main_conf.ini"), os.path.join(base, "files", "model_conf.ini")
