import argparse
import copy
import os
import time
import tkinter as tk
from tkinter import colorchooser, messagebox, ttk

from PIL import ImageTk

from game.led import SCENES, load, render_preview, sample, save
from game import neopixel


class LedEditor:
    def __init__(self, root, path):
        self.root, self.path = root, path
        self.data = load(path)
        self.scene = "game"
        self.index = 0
        self.dirty = False
        self.playing = False
        self.cursor = 0.0
        self.last_tick = time.monotonic()
        self.updating = False
        root.title("SMUSH · LED Animation Editor")
        root.geometry("900x820")
        root.minsize(860, 780)
        root.protocol("WM_DELETE_WINDOW", self.close)
        panel = ttk.Frame(root, padding=20)
        panel.pack(fill="both", expand=True)
        ttk.Label(panel, text="LED ANIMATION", font=("Helvetica", 20, "bold")).pack(anchor="w")
        toolbar = ttk.Frame(panel)
        toolbar.pack(fill="x")
        self.scene_var = tk.StringVar(value=self.scene)
        selector = ttk.Combobox(toolbar, textvariable=self.scene_var, values=SCENES, state="readonly", width=20)
        selector.pack(side="left")
        selector.bind("<<ComboboxSelected>>", self.change_scene)
        self.loop_var = tk.BooleanVar()
        ttk.Button(toolbar, text="Copy to all scenes", command=self.copy_all).pack(side="right")
        container = panel
        self.tabs = ttk.Notebook(container)
        self.tabs.pack(fill="both", expand=True, pady=10)
        panel = ttk.Frame(self.tabs, padding=10)
        pixel_panel = ttk.Frame(self.tabs, padding=10)
        self.tabs.add(panel, text="Button LEDs")
        self.tabs.add(pixel_panel, text="NeoPixel / BPM groove")
        self.pixel_panel = pixel_panel
        self.build_neopixel_controls(pixel_panel)
        self.preview = tk.Canvas(panel, width=480, height=140, bg="#101520", highlightthickness=0)
        self.preview.pack(pady=16)
        self.preview.bind("<Button-1>", lambda event: self.toggle(min(3, max(0, event.x // 120))))
        controls = ttk.Frame(panel)
        controls.pack(fill="x")
        ttk.Checkbutton(controls, text="Loop", variable=self.loop_var, command=self.change_loop).pack(side="left", padx=8)
        self.play_button = ttk.Button(controls, text="Play", command=self.play)
        self.play_button.pack(side="left")
        ttk.Button(controls, text="Rewind", command=self.rewind).pack(side="left", padx=8)
        self.time_label = ttk.Label(controls)
        self.time_label.pack(side="right")
        self.scrub = ttk.Scale(panel, from_=0, to=1, command=self.seek)
        self.scrub.pack(fill="x", pady=8)
        self.steps = ttk.Treeview(panel, columns=("duration", "states"), show="headings", height=7, selectmode="browse")
        self.steps.heading("duration", text="Step / duration")
        self.steps.heading("states", text="SW1   SW2   SW3   SW4")
        self.steps.pack(fill="both", expand=True)
        self.steps.bind("<<TreeviewSelect>>", self.select_step)
        edits = ttk.Frame(panel)
        edits.pack(fill="x", pady=12)
        ttk.Label(edits, text="Duration (ms)").pack(side="left")
        self.duration = tk.StringVar()
        ttk.Spinbox(edits, from_=100, to=60000, increment=100, textvariable=self.duration, width=8).pack(side="left", padx=8)
        ttk.Button(edits, text="Apply duration", command=self.apply_duration).pack(side="left")
        ttk.Button(edits, text="Add step", command=self.add).pack(side="left", padx=8)
        ttk.Button(edits, text="Delete step", command=self.delete).pack(side="left")
        ttk.Button(edits, text="Chase preset", command=self.chase).pack(side="right")
        footer = ttk.Frame(container)
        footer.pack(fill="x")
        self.status = ttk.Label(footer, text="Save to apply in the running game (reloads within one second).")
        self.status.pack(side="left")
        ttk.Button(footer, text="Save animations", command=self.save).pack(side="right")
        root.bind("<Control-s>", lambda event: self.save())
        root.bind("<Command-s>", lambda event: self.save())
        self.refresh_neopixel()
        self.refresh()
        self.tick()

    def build_neopixel_controls(self, panel):
        self.np_enabled = tk.BooleanVar()
        ttk.Checkbutton(panel, text="Enable four-pixel NeoPixel output (all scenes)", variable=self.np_enabled,
                        command=self.apply_neopixel).pack(anchor="w")
        self.np_preview = tk.Canvas(panel, width=480, height=110, bg="#101520", highlightthickness=0)
        self.np_preview.pack(pady=12)
        form = ttk.Frame(panel)
        form.pack(fill="x")
        self.np_vars = {key: tk.StringVar() for key in ("mode", "speed", "brightness", "pulse_fraction", "offset_ms", "preview_bpm")}
        fields = (("mode", "Scene effect", ("off", "solid", "beat", "rainbow")),
                  ("speed", "Beats per pulse / rainbow step (2 = half speed)", (.25, 8, .25)),
                  ("brightness", "Brightness (0–1)", (0, 1, .05)),
                  ("pulse_fraction", "Fade length / pulse (0.05–1)", (.05, 1, .05)),
                  ("offset_ms", "Delay in ms (+ delays the light)", (-2000, 2000, 10)),
                  ("preview_bpm", "Editor / menu BPM (song beat uses chart)", (20, 400, 1)))
        for row, (key, label, values) in enumerate(fields):
            ttk.Label(form, text=label).grid(row=row, column=0, sticky="w", pady=3)
            if key == "mode":
                widget = ttk.Combobox(form, textvariable=self.np_vars[key], values=values, state="readonly", width=14)
            else:
                widget = ttk.Spinbox(form, textvariable=self.np_vars[key], from_=values[0], to=values[1], increment=values[2], width=14)
            widget.grid(row=row, column=1, sticky="w", padx=16)
        self.np_high_health = tk.BooleanVar()
        ttk.Checkbutton(panel, text="Above 85% HP: alternate colors on right pixels NP3 / NP4",
                        variable=self.np_high_health, command=self.apply_neopixel).pack(anchor="w", pady=8)
        self.np_color_buttons = []
        for key, label, count in (("colors", "Normal colors", 4), ("right_colors", "High-HP right colors", 2)):
            row = ttk.Frame(panel)
            row.pack(fill="x", pady=3)
            ttk.Label(row, text=label, width=24).pack(side="left")
            for index in range(count):
                button = tk.Button(row, width=9, command=lambda k=key, i=index: self.choose_color(k, i))
                button.pack(side="left", padx=4)
                self.np_color_buttons.append((key, index, button))
        row = ttk.Frame(panel)
        row.pack(fill="x", pady=12)
        self.np_play_button = ttk.Button(row, text="Play", command=self.play)
        self.np_play_button.pack(side="left")
        ttk.Button(row, text="Rewind", command=self.rewind).pack(side="left", padx=8)
        ttk.Button(row, text="Apply settings", command=self.apply_neopixel).pack(side="left")
        self.np_preview_health = tk.BooleanVar(value=False)
        ttk.Checkbutton(row, text="Preview HP > 85%", variable=self.np_preview_health).pack(side="left", padx=12)
        ttk.Label(panel, text="Save applies to the running game. Preview sends no hardware commands.\n"
                  "Beat follows song BPM from music select; beat / rainbow follow chart timing in gameplay.\n"
                  "Rainbow cycles hues; color pickers apply to solid / beat.").pack(anchor="w")

    def refresh_neopixel(self):
        settings = self.animation["neopixel"]
        self.np_enabled.set(self.data["neopixel"]["enabled"])
        self.np_high_health.set(settings["high_health"])
        for key, variable in self.np_vars.items():
            variable.set(str(self.data["neopixel"][key] if key == "preview_bpm" else settings[key]))
        for key, index, button in self.np_color_buttons:
            color = settings[key][index]
            button.configure(text=color, background=color, foreground="black" if sum(int(color[i:i+2], 16) for i in (1, 3, 5)) > 380 else "white")

    def commit_neopixel(self):
        settings = copy.deepcopy(self.animation["neopixel"])
        try:
            for key in ("speed", "brightness", "pulse_fraction", "offset_ms"):
                settings[key] = float(self.np_vars[key].get())
            settings["mode"] = self.np_vars["mode"].get()
            settings["high_health"] = self.np_high_health.get()
            bpm = float(self.np_vars["preview_bpm"].get())
            neopixel.validate(settings)
            if not neopixel.number(bpm, 20, 400):
                raise ValueError("invalid bpm range error")
        except ValueError as error:
            messagebox.showerror("invalid configuration error", str(error), parent=self.root)
            return False
        global_settings = {"enabled": self.np_enabled.get(), "preview_bpm": bpm}
        if settings != self.animation["neopixel"] or global_settings != self.data["neopixel"]:
            self.dirty = True
        self.animation["neopixel"] = settings
        self.data["neopixel"] = global_settings
        return True

    def apply_neopixel(self):
        if self.commit_neopixel():
            self.status.configure(text="Unsaved changes")
            self.refresh_neopixel()

    def choose_color(self, key, index):
        if not self.commit_neopixel():
            return
        color = colorchooser.askcolor(self.animation["neopixel"][key][index], parent=self.root)[1]
        if color:
            self.animation["neopixel"][key][index] = color.upper()
            self.dirty = True
            self.status.configure(text="Unsaved changes")
            self.refresh_neopixel()

    @property
    def animation(self):
        return self.data["scenes"][self.scene]

    def refresh(self):
        self.updating = True
        self.steps.delete(*self.steps.get_children())
        for index, step in enumerate(self.animation["steps"]):
            self.steps.insert("", "end", iid=str(index), values=(f"{index + 1} · {step['ms']} ms", "    ".join("ON" if v else "OFF" for v in step["leds"])))
        self.steps.selection_set(str(self.index))
        self.steps.see(str(self.index))
        self.duration.set(str(self.animation["steps"][self.index]["ms"]))
        self.loop_var.set(self.animation["loop"])
        self.scrub.configure(to=sum(s["ms"] for s in self.animation["steps"]) / 1000)
        self.updating = False

    def changed(self):
        self.dirty = True
        self.status.configure(text="Unsaved changes")
        self.refresh()

    def commit_duration(self):
        try:
            value = int(self.duration.get())
            if not 100 <= value <= 60000:
                raise ValueError()
        except ValueError:
            messagebox.showerror("Invalid duration", "Use an integer from 100 to 60000 ms.", parent=self.root)
            return False
        step = self.animation["steps"][self.index]
        if step["ms"] != value:
            step["ms"] = value
            self.dirty = True
        return True

    def apply_duration(self):
        if self.commit_duration():
            self.changed()

    def change_scene(self, event=None):
        if not self.commit_duration() or not self.commit_neopixel():
            self.scene_var.set(self.scene)
            return
        self.scene = self.scene_var.get()
        self.index = 0
        self.rewind()
        self.refresh_neopixel()
        self.refresh()

    def change_loop(self):
        self.animation["loop"] = self.loop_var.get()
        self.changed()

    def select_step(self, event=None):
        if self.updating or not self.steps.selection():
            return
        index = int(self.steps.selection()[0])
        if index == self.index:
            return
        if not self.commit_duration():
            self.steps.selection_set(str(self.index))
            return
        self.index = index
        self.playing = False
        self.cursor = sum(s["ms"] for s in self.animation["steps"][:index]) / 1000
        self.duration.set(str(self.animation["steps"][index]["ms"]))

    def toggle(self, index):
        if not self.commit_duration():
            return
        self.playing = False
        step = self.animation["steps"][self.index]
        step["leds"][index] = not step["leds"][index]
        self.cursor = sum(s["ms"] for s in self.animation["steps"][:self.index]) / 1000
        self.changed()

    def add(self):
        if not self.commit_duration() or len(self.animation["steps"]) >= 1000:
            return
        self.animation["steps"].insert(self.index + 1, copy.deepcopy(self.animation["steps"][self.index]))
        self.index += 1
        self.playing = False
        self.cursor = sum(s["ms"] for s in self.animation["steps"][:self.index]) / 1000
        self.changed()

    def delete(self):
        if len(self.animation["steps"]) > 1:
            self.animation["steps"].pop(self.index)
            self.index = min(self.index, len(self.animation["steps"]) - 1)
            self.playing = False
            self.cursor = sum(s["ms"] for s in self.animation["steps"][:self.index]) / 1000
            self.changed()

    def chase(self):
        self.animation["steps"] = [{"ms": 200, "leds": [i == n for i in range(4)]} for n in range(4)]
        self.animation["loop"] = True
        self.index = 0
        self.rewind()
        self.changed()

    def copy_all(self):
        if self.commit_duration() and self.commit_neopixel() and messagebox.askyesno("Copy animation", "Replace every scene's button timeline and NeoPixel settings with this animation?", parent=self.root):
            animation = copy.deepcopy(self.animation)
            self.data["scenes"] = {scene: copy.deepcopy(animation) for scene in SCENES}
            self.changed()

    def play(self):
        if self.commit_duration() and self.commit_neopixel():
            self.refresh()
            self.playing = not self.playing
            self.last_tick = time.monotonic()

    def rewind(self):
        self.playing = False
        self.cursor = 0.0

    def seek(self, value):
        if not self.updating:
            self.cursor = float(value)

    def tick(self):
        now = time.monotonic()
        duration = sum(s["ms"] for s in self.animation["steps"]) / 1000
        pixel_tab = self.tabs.select() == str(self.pixel_panel)
        if pixel_tab:
            duration = 8 * 60 / self.data["neopixel"]["preview_bpm"] * self.animation["neopixel"]["speed"]
        if self.playing:
            self.cursor += now - self.last_tick
            if self.cursor >= duration:
                if pixel_tab or self.animation["loop"]:
                    self.cursor %= duration
                else:
                    self.cursor = duration
                    self.playing = False
        self.last_tick = now
        self.play_button.configure(text="Pause" if self.playing else "Play")
        self.np_play_button.configure(text="Pause" if self.playing else "Play")
        pixels = neopixel.sample(self.animation["neopixel"], self.cursor,
                                 health=100 if self.np_preview_health.get() else 50,
                                 fallback_bpm=self.data["neopixel"]["preview_bpm"]) if self.data["neopixel"]["enabled"] else neopixel.BLACK
        self.np_photo = ImageTk.PhotoImage(neopixel.render_preview(pixels))
        self.np_preview.delete("all")
        self.np_preview.create_image(0, 0, image=self.np_photo, anchor="nw")
        states = sample(self.animation, self.cursor)
        self.photo = ImageTk.PhotoImage(render_preview(states))
        self.preview.delete("all")
        self.preview.create_image(0, 0, image=self.photo, anchor="nw")
        self.time_label.configure(text=f"{self.cursor:.2f} / {duration:.2f} s")
        self.updating = True
        self.scrub.set(self.cursor)
        self.updating = False
        self.root.after(33, self.tick)

    def save(self):
        if not self.commit_duration() or not self.commit_neopixel():
            return False
        try:
            save(self.path, self.data)
            self.dirty = False
            self.status.configure(text="Saved — running game reloads automatically.")
            return True
        except (OSError, ValueError) as error:
            messagebox.showerror("Cannot save", str(error), parent=self.root)
            return False

    def close(self):
        if not self.commit_duration() or not self.commit_neopixel():
            return
        if self.dirty:
            answer = messagebox.askyesnocancel("Unsaved animations", "Save changes before closing?", parent=self.root)
            if answer is None or (answer and not self.save()):
                return
        self.root.destroy()


def run(path=None):
    from ui_framework import find_compiled_dir

    root = tk.Tk()
    try:
        LedEditor(root, path or os.path.join(find_compiled_dir(), "files", "led_animations.json"))
    except (OSError, ValueError) as error:
        messagebox.showerror("Cannot open animations", str(error), parent=root)
        root.destroy()
        return
    root.mainloop()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--file", help="LED animation JSON file")
    run(parser.parse_args().file)
