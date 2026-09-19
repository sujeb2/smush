import fnmatch
import os
import sys
import unicodedata

from PIL import ImageFont


FONT_EXTENSIONS = {".ttf", ".otf", ".ttc", ".otc"}


def installed_font_directories():
    home = os.path.expanduser("~")
    if sys.platform == "win32":
        return (
            os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts"),
            os.path.join(os.environ.get("LOCALAPPDATA", os.path.join(home, "AppData", "Local")),
                         "Microsoft", "Windows", "Fonts"),
        )
    if sys.platform == "darwin":
        return (os.path.join(home, "Library", "Fonts"), "/Library/Fonts", "/System/Library/Fonts")
    return (os.path.join(home, ".fonts"),
            os.path.join(os.environ.get("XDG_DATA_HOME", os.path.join(home, ".local", "share")), "fonts"),
            "/usr/local/share/fonts", "/usr/share/fonts")


def _normalized(value):
    return unicodedata.normalize("NFC", value).casefold()


def _family_key(value):
    return "".join(c for c in _normalized(value) if c.isalnum() or c in "*?[]")


def find_font(base, fallback, patterns, extra_directories=()):
    directories = (os.path.join(base, "files", "fonts"), *extra_directories,
                   *installed_font_directories())
    candidates = []
    seen = set()
    for directory in directories:
        directory = os.path.abspath(directory)
        if directory in seen:
            continue
        seen.add(directory)
        for root, dirs, files in os.walk(directory):
            dirs.sort()
            candidates.extend(os.path.join(root, name) for name in sorted(files)
                              if os.path.splitext(name)[1].lower() in FONT_EXTENSIONS)
    loaded = {}

    def load(path):
        if path not in loaded:
            try:
                loaded[path] = ImageFont.truetype(path, 16)
            except (OSError, ValueError):
                loaded[path] = None
        return loaded[path]

    for pattern in patterns:
        for path in candidates:
            if fnmatch.fnmatchcase(_normalized(os.path.basename(path)), _normalized(pattern)) and load(path):
                print(f"[FontManager] {patterns[0]} -> {path}")
                return path
    for pattern in patterns:
        family_pattern = _family_key(os.path.splitext(pattern)[0])
        for path in candidates:
            font = load(path)
            if font and fnmatch.fnmatchcase(_family_key(" ".join(font.getname())), family_pattern):
                print(f"[FontManager] {patterns[0]} -> {path} (family match)")
                return path
    print(f"[FontManager] {patterns[0]} not found; fallback -> {fallback}")
    return fallback
