import os
import queue
import tempfile
import threading
import time
import unittest
from types import SimpleNamespace

from PIL import Image

from game.AssetWorker import IMAGE_PATHS, load_minigame_assets
from game.minigame import (
    AudioPlayer,
    EVENT_TRACK_COUNT,
    MAX_SCORE,
    MinigameUI,
    calculate_catch_score,
    calculate_score,
    combo_after_judgement,
    event_result_destination,
    group_charts_by_song,
    is_clear,
    hold_tick_times,
    load_event_results,
    load_progress,
    save_progress,
)
from game.osu_chart import (
    ChartNote,
    UnsupportedOsuChartError,
    discover_osu_mania_2k,
    discover_osu_supported,
    parse_osu_catch,
    parse_osu_mania_2k,
)


class ScoreTests(unittest.TestCase):
    def test_all_perfect_score_is_exact_maximum(self):
        self.assertEqual(calculate_score(["perfect"] * 226, 226), MAX_SCORE)

    def test_score_uses_chart_note_count(self):
        judgements = ["perfect", "good", "bad", "miss"]
        self.assertEqual(calculate_score(judgements, 4), 4275)

    def test_catch_score_uses_chart_object_count(self):
        self.assertEqual(calculate_catch_score(113, 226), 4500)
        self.assertEqual(calculate_catch_score(226, 226), MAX_SCORE)

    def test_clear_requires_five_percent_health(self):
        self.assertFalse(is_clear(0))
        self.assertFalse(is_clear(4.99))
        self.assertTrue(is_clear(5))

    def test_combo_increments_for_hits_and_resets_for_miss(self):
        combo = 0
        for judgement in ("perfect", "good", "bad"):
            combo = combo_after_judgement(combo, judgement)
        self.assertEqual(combo, 3)
        self.assertEqual(combo_after_judgement(combo, "miss"), 0)

    def test_hold_ticks_follow_quarter_second_interval(self):
        self.assertEqual(hold_tick_times(1.0, 2.0), (1.25, 1.5, 1.75, 2.0))
        self.assertEqual(hold_tick_times(1.0, None), ())

    def test_catch_and_miss_update_combo_health_and_score(self):
        game = MinigameUI.__new__(MinigameUI)
        game.resolved_notes = set()
        game.judgements = []
        game.counts = {"catch": 0, "miss": 0}
        game.health = 100.0
        game.display_health = 100.0
        game.combo = 0
        game.max_combo = 0
        game.combo_animation_started = None
        game.combo_frame_shown = -1
        game.combo_photo_cache = {}
        game.game_mode = "catch"
        game.catch_combo_item = None
        game.combo_item = None
        game.catch_score_item = None
        game.score_item = None
        game.note_items = {}
        bursts = []
        game._start_catch_burst = lambda x, y: bursts.append((x, y))
        game.track = SimpleNamespace(notes=tuple(ChartNote(float(index), 0) for index in range(6)))
        for index in range(5):
            game._resolve_catch(index, True)
        self.assertEqual((game.combo, game.score, game.counts["catch"]), (5, 7500, 5))
        self.assertEqual(len(bursts), 1)
        game._resolve_catch(5, False)
        self.assertEqual((game.combo, game.health, game.counts["miss"]), (0, 93.0, 1))

    def test_catcher_uses_momentum_instead_of_fixed_steps(self):
        positions = []
        game = MinigameUI.__new__(MinigameUI)
        game.catcher_x = 540.0
        game.catcher_velocity = 0.0
        game.catcher_last_update = None
        game.catcher_item = 1
        game.canvas = SimpleNamespace(coords=lambda item, x, y: positions.append(x))
        game._x = lambda value: value
        game._y = lambda value: value
        game._move_catcher(1)
        started = game.catcher_last_update
        self.assertEqual(game.catcher_x, 540.0)
        self.assertEqual(game.catcher_velocity, 520.0)
        game._animate_catcher(started + 0.05)
        self.assertGreater(game.catcher_x, 540.0)
        self.assertGreater(game.catcher_velocity, 0.0)
        self.assertLess(game.catcher_velocity, 520.0)
        previous = game.catcher_x
        game._animate_catcher(started + 0.10)
        self.assertGreater(game.catcher_x, previous)
        self.assertTrue(positions)


class AudioTests(unittest.TestCase):
    def test_song_preview_starts_from_chart_preview_time(self):
        calls = []
        music = SimpleNamespace(
            load=lambda path: calls.append(("load", path)),
            play=lambda *args: calls.append(("play", args)),
            stop=lambda: None,
            fadeout=lambda milliseconds: None,
        )
        player = AudioPlayer.__new__(AudioPlayer)
        player.available = True
        player.current_path = None
        player.pygame = SimpleNamespace(mixer=SimpleNamespace(music=music))
        player._print = lambda message: None
        with tempfile.NamedTemporaryFile() as audio:
            player.play(audio.name, fade_ms=260, start_seconds=40.16)
        self.assertEqual(calls[-1], ("play", (0, 40.16, 260)))

    def test_gameplay_uses_actual_mixer_position(self):
        game = MinigameUI.__new__(MinigameUI)
        game.game_audio_started = True
        game.game_started = 0.0
        game.audio = SimpleNamespace(position_seconds=lambda: 12.345)
        self.assertEqual(game._game_elapsed(), 12.345)

    def test_sfx_preload_populates_audio_cache_once(self):
        loaded = []
        player = AudioPlayer.__new__(AudioPlayer)
        player.available = True
        player.sfx_cache = {}
        player.pygame = SimpleNamespace(mixer=SimpleNamespace(Sound=lambda path: loaded.append(path) or path))
        player._print = lambda message: None
        with tempfile.NamedTemporaryFile(suffix=".wav") as audio:
            player.preload_sfx((audio.name, audio.name))
        self.assertEqual(loaded, [audio.name])


class OsuChartTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.audio_path = os.path.join(self.directory.name, "audio.mp3")
        with open(self.audio_path, "wb") as file:
            file.write(b"audio")
        for filename in ("background.jpg", "video.mp4"):
            with open(os.path.join(self.directory.name, filename), "wb") as file:
                file.write(b"media")

    def tearDown(self):
        self.directory.cleanup()

    def _write_chart(self, circle_size="2"):
        path = os.path.join(self.directory.name, "test.osu")
        with open(path, "w", encoding="utf-8") as file:
            file.write(
                "osu file format v126\n"
                "[General]\nAudioFilename: audio.mp3\nAudioLeadIn: 0\nPreviewTime: 1250\nMode: 3\n"
                "[Metadata]\nTitle:Test Song\nArtist:Test Artist\nCreator:Mapper\nVersion:Test 2K\n"
                f"[Difficulty]\nHPDrainRate:5\nCircleSize:{circle_size}\nOverallDifficulty:8\n"
                "[Events]\n0,0,\"background.jpg\",0,0\nVideo,500,\"video.mp4\"\n"
                "Sprite,Foreground,Centre,storyboard.png,320,240\n"
                "256,192,999,1,0,0:0:0:0:\n"
                "[HitObjects]\n64,192,1000,1,0,0:0:0:0:\n"
                "448,192,1500,128,0,2000:0:0:0:0:\n"
            )
        return path

    def test_v126_mania_chart_uses_only_hit_objects(self):
        chart = parse_osu_mania_2k(self._write_chart())
        self.assertEqual(chart.format_version, 126)
        self.assertEqual(chart.title, "Test Song")
        self.assertEqual([(note.time, note.lane) for note in chart.notes], [(1.0, 0), (1.5, 1)])
        self.assertEqual(chart.notes[1].end_time, 2.0)
        self.assertEqual(chart.preview_time, 1250)
        self.assertEqual(chart.background_path, os.path.join(self.directory.name, "background.jpg"))
        self.assertEqual(chart.video_path, os.path.join(self.directory.name, "video.mp4"))
        self.assertEqual(chart.video_start_time, 500)

    def test_non_2k_chart_is_rejected(self):
        with self.assertRaises(UnsupportedOsuChartError):
            parse_osu_mania_2k(self._write_chart(circle_size="6"))

    def test_sample_folder_discovers_only_2k_difficulty(self):
        charts, rejected = discover_osu_mania_2k(os.path.join("game", "charts", "sample-chart"))
        self.assertEqual(len(charts), 1)
        self.assertEqual(len(rejected), 1)
        self.assertEqual(charts[0].difficulty, "Learn 2 Alternate!")

    def test_v126_catch_chart_uses_horizontal_hit_object_position(self):
        path = os.path.join(self.directory.name, "catch.osu")
        with open(path, "w", encoding="utf-8") as file:
            file.write(
                "osu file format v126\n"
                "[General]\nAudioFilename: audio.mp3\nAudioLeadIn: 0\nMode: 2\n"
                "[Metadata]\nTitle:Catch Song\nArtist:Test Artist\nCreator:Mapper\nVersion:Catch\n"
                "[Difficulty]\nHPDrainRate:5\nCircleSize:5\nOverallDifficulty:7\nSliderMultiplier:1.4\n"
                "[TimingPoints]\n0,500,4,2,1,60,1,0\n"
                "[Events]\nSprite,Foreground,Centre,storyboard.png,320,240\n"
                "[HitObjects]\n64,192,1000,1,0,0:0:0:0:\n"
                "448,192,1500,1,0,0:0:0:0:\n"
            )
        chart = parse_osu_catch(path)
        self.assertEqual(chart.mode, 2)
        self.assertEqual([(note.time, note.x) for note in chart.notes], [(1.0, 64), (1.5, 448)])

    def test_supported_discovery_separates_2k_and_catch(self):
        catch_path = os.path.join(self.directory.name, "catch.osu")
        with open(catch_path, "w", encoding="utf-8") as file:
            file.write(
                "osu file format v126\n"
                "[General]\nAudioFilename: audio.mp3\nMode: 2\n"
                "[Metadata]\nTitle:Catch\nVersion:Catch\n"
                "[Difficulty]\nCircleSize:5\nOverallDifficulty:5\n"
                "[HitObjects]\n256,192,1000,1,0,0:0:0:0:\n"
            )
        self._write_chart()
        charts, rejected = discover_osu_supported(self.directory.name)
        self.assertEqual(len(charts["2k"]), 1)
        self.assertEqual(len(charts["catch"]), 1)
        self.assertEqual(rejected, ())


class ProgressTests(unittest.TestCase):
    def test_progress_defaults_and_wraps_to_available_chart_count(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "progress.json")
            self.assertEqual(load_progress(path, 3), 0)
            save_progress(path, 1, 3)
            self.assertEqual(load_progress(path, 3), 1)
            save_progress(path, 3, 3)
            self.assertEqual(load_progress(path, 3), 0)
            with open(path, "w", encoding="utf-8") as file:
                file.write('{"track_index": 4}')
            self.assertEqual(load_progress(path, 3), 0)

    def test_event_progression_has_three_tracks(self):
        self.assertEqual(EVENT_TRACK_COUNT, 3)
        self.assertEqual(event_result_destination(0, True), ("select", 1))
        self.assertEqual(event_result_destination(1, True), ("select", 2))
        self.assertEqual(event_result_destination(2, True), ("total_result", 0))
        self.assertEqual(event_result_destination(1, False), ("ending", 0))

    def test_track_results_are_saved_for_total_result(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "progress.json")
            scores = [9000, 7200, 8100]
            names = ["First", "Second", "Final"]
            save_progress(path, 2, 3, scores, names)
            self.assertEqual(load_event_results(path, 3), (scores, names))


class SelectionTests(unittest.TestCase):
    def test_charts_are_grouped_by_song_and_sorted_by_difficulty(self):
        charts = (
            SimpleNamespace(artist="Artist", title="Song", level=8, difficulty="Hard", path="hard.osu"),
            SimpleNamespace(artist="Artist", title="Song", level=3, difficulty="Easy", path="easy.osu"),
            SimpleNamespace(artist="Other", title="Second", level=5, difficulty="2K", path="second.osu"),
        )
        groups = group_charts_by_song(charts)
        self.assertEqual(len(groups), 2)
        self.assertEqual([chart.difficulty for chart in groups[0]], ["Easy", "Hard"])


class RefactorTests(unittest.TestCase):
    def test_state_initialization_groups_default_runtime_state(self):
        track = SimpleNamespace(title="Song")
        game = MinigameUI.__new__(MinigameUI)
        game.song_groups = ((track,),)
        game._initialize_state()
        self.assertEqual(game.scene, "preload")
        self.assertIs(game.track, track)
        self.assertEqual(game.counts, {"perfect": 0, "good": 0, "bad": 0, "miss": 0})
        self.assertEqual((game.health, game.combo, game.score), (100.0, 0, 0))

    def test_asset_worker_builds_all_derived_sources(self):
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        sources, bgm_root, sfx_root = load_minigame_assets(base)
        required = set(IMAGE_PATHS) | {
            "catch_line", "top_gradient", "next_arrow_left", "select_sweep", "catch_particle", "catch_scroll",
        }
        self.assertTrue(required <= set(sources))
        self.assertEqual(sources["top_gradient"].size, (1080, 520))
        self.assertEqual(sources["select_sweep"].size, (150, sources["select_bg"].height))
        self.assertEqual(sfx_root, os.path.join(bgm_root, "sfx"))

    def test_game_media_is_sized_and_dimmed_for_playfield(self):
        game = MinigameUI.__new__(MinigameUI)
        source = game._game_media_source(Image.new("RGB", (320, 180), "white"))
        self.assertEqual(source.size, (1000, 1430))
        self.assertTrue(130 <= source.getpixel((500, 715))[0] <= 134)

    def test_ci_waits_for_preload_completion(self):
        actions = []
        game = MinigameUI.__new__(MinigameUI)
        game.preload_complete = False
        game.show_preload = lambda action: actions.append(action)
        game.show_ci(fade_in=True)
        self.assertEqual(len(actions), 1)

    def test_preload_diagnostic_advances_checking_stages(self):
        game = MinigameUI.__new__(MinigameUI)
        game.preload_status_lines = []
        game.preload_stage_states = {}
        game.preload_active_stage = None
        game.scene = "test"
        game._print = lambda message: None
        game._set_preload_stage("GRAPHIC ASSETS", "CHECKING")
        self.assertEqual(game.preload_stage_states["GRAPHIC ASSETS"], "CHECKING")
        game._set_preload_stage("GRAPHIC ASSETS", "OK")
        game._set_preload_stage("ANIMATION CACHE", "CHECKING")
        self.assertEqual(game.preload_stage_states["GRAPHIC ASSETS"], "OK")
        self.assertEqual(game.preload_stage_states["ANIMATION CACHE"], "CHECKING")
        game._update_preload_status("Initialization complete.")
        self.assertTrue(all(status == "OK" for status in game.preload_stage_states.values()))

    def test_preload_worker_runs_independent_groups_on_multiple_threads(self):
        game = MinigameUI.__new__(MinigameUI)
        game.event_queue = queue.Queue()
        game._load_assets = lambda: None
        thread_ids = set()
        lock = threading.Lock()

        def work():
            with lock:
                thread_ids.add(threading.get_ident())
            time.sleep(0.025)

        for name in (
            "_preload_entry_animation_sources",
            "_preload_warning_animation_sources",
            "_preload_result_animation_sources",
            "_preload_gameplay_animation_sources",
            "_preload_chart_media",
            "_warm_preload_audio_files",
        ):
            setattr(game, name, work)
        game._run_preload()
        events = []
        while not game.event_queue.empty():
            events.append(game.event_queue.get_nowait()[0])
        self.assertGreater(len(thread_ids), 1)
        self.assertIn("preload_ready", events)


if __name__ == "__main__":
    unittest.main()
