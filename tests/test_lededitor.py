import os
import tempfile
import unittest


@unittest.skipUnless(os.environ.get("SMUSH_TEST_TK") == "1", "requires a desktop Tk session")
class LedEditorTests(unittest.TestCase):
    def test_edit_preview_scene_switch_and_save(self):
        import tkinter as tk
        from game.led import load
        from lededitor import LedEditor

        with tempfile.TemporaryDirectory() as directory:
            root = tk.Tk()
            try:
                path = os.path.join(directory, "led.json")
                editor = LedEditor(root, path)
                root.update()
                editor.tabs.select(editor.pixel_panel)
                root.update()
                self.assertTrue(editor.np_preview.winfo_viewable())
                self.assertTrue(editor.np_play_button.winfo_viewable())
                self.assertLess(editor.status.winfo_rooty(), root.winfo_rooty() + root.winfo_height())

                editor.np_enabled.set(True)
                editor.np_vars["brightness"].set("0.3")
                editor.np_vars["speed"].set("2")
                editor.toggle(0)
                self.assertEqual(editor.np_vars["speed"].get(), "2")
                editor.duration.set("700")
                editor.apply_neopixel()
                self.assertEqual(editor.duration.get(), "700")
                editor.play()
                self.assertTrue(editor.playing)
                editor.np_preview_health.set(True)
                editor.tick()
                self.assertTrue(editor.np_preview.find_all())
                editor.scene_var.set("title")
                editor.change_scene()
                self.assertEqual(editor.np_vars["mode"].get(), "rainbow")
                editor.np_vars["mode"].set("solid")
                self.assertTrue(editor.save())
                saved = load(path)
                self.assertTrue(saved["neopixel"]["enabled"])
                self.assertEqual(saved["scenes"]["game"]["neopixel"]["speed"], 2)
                self.assertEqual(saved["scenes"]["game"]["neopixel"]["brightness"], .3)
                self.assertEqual(saved["scenes"]["game"]["steps"][0]["ms"], 700)
                self.assertEqual(saved["scenes"]["title"]["neopixel"]["mode"], "solid")
            finally:
                root.destroy()
