import os
import queue
import tempfile
import threading
import time
import unittest
from dataclasses import replace
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
    derive_4k_chart,
    parse_osu_catch,
    parse_osu_mania_2k,
    parse_osu_mania_4k,
)
from game.rules import calculate_accuracy, rank_for_accuracy
from moderngl_framework import FrameRateCounter, ModernGLCanvas, ModernGLUIFramework


class ScoreTests(unittest.TestCase):
    def test_accuracy_and_rank_lookup(self):
        self.assertEqual(calculate_accuracy(["perfect", "good", "bad", "miss"], 4), 47.5)
        self.assertEqual(calculate_accuracy(["catch", "catch", "miss", "miss"], 4, catch_mode=True), 50.0)
        self.assertEqual(rank_for_accuracy(100), "X")
        self.assertEqual(rank_for_accuracy(95), "S")
        self.assertEqual(rank_for_accuracy(90), "A")
        self.assertEqual(rank_for_accuracy(80), "B")
        self.assertEqual(rank_for_accuracy(70), "C")
        self.assertEqual(rank_for_accuracy(69.99), "D")

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
        hitsounds = []
        game._play_sfx = lambda filename, volume=1.0: hitsounds.append((filename, volume))
        game._start_catch_burst = lambda x, y: bursts.append((x, y))
        game.track = SimpleNamespace(notes=tuple(ChartNote(float(index), 0) for index in range(6)))
        for index in range(5):
            game._resolve_catch(index, True)
        self.assertEqual((game.combo, game.score, game.counts["catch"]), (5, 7500, 5))
        self.assertEqual(len(bursts), 1)
        self.assertEqual(hitsounds, [("hitsound.wav", 0.45)] * 5)
        game._resolve_catch(5, False)
        self.assertEqual((game.combo, game.health, game.counts["miss"]), (0, 93.0, 1))
        self.assertEqual(hitsounds, [("hitsound.wav", 0.45)] * 5)

    def test_note_hits_and_hold_ticks_play_hitsound_but_misses_do_not(self):
        hitsounds = []
        game = MinigameUI.__new__(MinigameUI)
        game.resolved_notes = set()
        game.judgements = []
        game.counts = {"perfect": 0, "good": 0, "bad": 0, "miss": 0}
        game.health = 100.0
        game.combo = 0
        game.max_combo = 0
        game.combo_animation_started = None
        game.combo_frame_shown = -1
        game.combo_photo_cache = {}
        game.game_mode = "2k"
        game.combo_item = None
        game.catch_combo_item = None
        game.score_item = None
        game.judgement_item = None
        game.feedback_visible = False
        game.active_holds = {}
        game.track = SimpleNamespace(notes=(ChartNote(0.0, 0, 1.0), ChartNote(1.0, 0)))
        game._game_elapsed = lambda: 0.0
        game._start_health_animation = lambda previous, current: None
        game._play_sfx = lambda filename, volume=1.0: hitsounds.append((filename, volume))
        game._resolve_note(0, "perfect")
        game._update_hold_ticks(0.25)
        game._resolve_note(1, "miss")
        self.assertEqual(hitsounds, [("hitsound.wav", 0.45), ("hitsound.wav", 0.62)])

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


class FrameRateCounterTests(unittest.TestCase):
    def test_tracks_window_extremes_and_time_weighted_average(self):
        counter = FrameRateCounter(refresh_seconds=0.5)
        self.assertFalse(counter.update(0.0))
        for frame in range(1, 31):
            refreshed = counter.update(frame / 60)
        self.assertTrue(refreshed)
        self.assertAlmostEqual(counter.current, 60.0)
        self.assertAlmostEqual(counter.minimum, 60.0)
        self.assertAlmostEqual(counter.maximum, 60.0)
        for frame in range(1, 16):
            refreshed = counter.update(0.5 + frame / 30)
        self.assertTrue(refreshed)
        self.assertAlmostEqual(counter.current, 30.0)
        self.assertAlmostEqual(counter.minimum, 30.0)
        self.assertAlmostEqual(counter.maximum, 60.0)
        self.assertAlmostEqual(counter.average, 45.0)
        self.assertEqual(counter.text(), "FPS 30.0   MIN 30.0   MAX 60.0   AVG 45.0")


class AudioTests(unittest.TestCase):
    def test_song_preview_starts_from_chart_preview_time(self):
        calls = []
        music = SimpleNamespace(
            load=lambda path: calls.append(("load", path)),
            play=lambda *args: calls.append(("play", args)),
            set_volume=lambda volume: calls.append(("volume", volume)),
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

    def test_next_screen_mixes_preview_and_next_audio(self):
        calls = []
        channel = SimpleNamespace()
        track = SimpleNamespace(audio_path="song.mp3", preview_time=40160)
        game = MinigameUI.__new__(MinigameUI)
        game.running = True
        game.scene = "next"
        game.transition_phase = None
        game.track = track
        game.bgm_root = "/bgm"
        game.audio = SimpleNamespace(
            current_path=track.audio_path,
            is_playing=lambda: True,
            set_music_volume=lambda volume: calls.append(("music", volume)),
            play_sfx=lambda path, volume=1.0: calls.append((path, volume)) or channel,
        )
        game._play_next_audio()
        self.assertEqual(calls, [("music", 0.58), (os.path.join("/bgm", "next.mp3"), 0.34)])
        self.assertIs(game.next_audio_channel, channel)

    def test_rank_voice_uses_result_rank_audio(self):
        calls = []
        game = MinigameUI.__new__(MinigameUI)
        game.rank = "S"
        game.voice_root = "/voice"
        game.audio = SimpleNamespace(play_sfx=lambda path, volume=1.0: calls.append((path, volume)))
        game._play_rank_voice()
        self.assertEqual(calls, [(os.path.join("/voice", "rank_s.mp3"), 0.9)])

    def test_ending_voice_uses_see_you_audio(self):
        calls = []
        game = MinigameUI.__new__(MinigameUI)
        game.voice_root = "/voice"
        game.audio = SimpleNamespace(play_sfx=lambda path, volume=1.0: calls.append((path, volume)))
        game._play_ending_voice()
        self.assertEqual(calls, [(os.path.join("/voice", "see_you.mp3"), 0.9)])

    def test_result_animation_plays_rank_voice_once(self):
        calls = []
        game = MinigameUI.__new__(MinigameUI)
        game.scene_started = 0.0
        game.result_rank_voice_played = False
        game._play_sfx = lambda filename, volume=1.0: calls.append((filename, volume))
        game._play_rank_voice = lambda: calls.append(("rank", 0.9))
        game.result_rank_sfx_channel = None
        game.result_rank_voice_channel = None
        game.result_rank_item = None
        game.result_card_offset = 560.0
        game.result_banner_item = None
        game.result_final_counts = {}
        game.score = 0
        game.result_values_shown = {"score": 0}
        game.result_value_items = {}
        game.scale = 1.0
        game.canvas = SimpleNamespace(move=lambda *args: None)
        game._animate_result(0.8)
        game._animate_result(1.0)
        self.assertEqual(calls, [("rank_show.mp3", 0.68), ("rank", 0.9)])

    def test_ending_animation_plays_see_you_voice_once(self):
        calls = []
        game = MinigameUI.__new__(MinigameUI)
        game.scene_started = 0.0
        game.ending_voice_played = False
        game.ending_voice_channel = None
        game._play_ending_voice = lambda: calls.append("see_you")
        game._set_motion_item = lambda *args: None
        game.ending_logo_item = None
        game.ending_thanks_item = None
        game.ending_motion_state = {}
        game.scale = 1.0
        game.offset_x = 0.0
        game.offset_y = 0.0
        game.canvas = SimpleNamespace(coords=lambda *args: None)
        game.ending_audio_started = False
        game.ending_audio_deadline = 20.0
        game.loading_phase = "active"
        game._animate_ending(0.9)
        game._animate_ending(1.1)
        self.assertEqual(calls, ["see_you"])

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

    def test_4k_chart_maps_all_four_lanes(self):
        path = self._write_chart(circle_size="4")
        chart = parse_osu_mania_4k(path)
        self.assertEqual(chart.circle_size, 4.0)
        self.assertEqual([note.lane for note in chart.notes], [0, 3])
        with self.assertRaises(UnsupportedOsuChartError):
            parse_osu_mania_2k(path)

    def test_2k_chart_gets_playable_4k_fallback(self):
        chart = parse_osu_mania_2k(self._write_chart())
        repeated = tuple(
            replace(note, time=note.time + repeat * 2.0)
            for repeat in range(2)
            for note in chart.notes
        )
        converted = derive_4k_chart(replace(chart, notes=repeated))
        self.assertEqual([note.lane for note in converted.notes], [0, 2, 1, 3])
        self.assertEqual(converted.circle_size, 4.0)

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
    def test_attract_title_routes_to_demonstration(self):
        transitions = []
        game = MinigameUI.__new__(MinigameUI)
        game.loading_phase = None
        game.title_entry_morph_started = None
        game.title_fade_started = None
        game.title_audio_started = True
        game.title_audio_deadline = 0.0
        game.audio = SimpleNamespace(available=True, is_playing=lambda: False)
        game._animate_title_fade = lambda now: None
        game.show_demonstration = lambda: None
        game._start_loading = lambda target, action: transitions.append((target, action))
        game._animate_title(1.0)
        self.assertEqual(transitions, [("demonstration", game.show_demonstration)])

    def test_demonstration_uses_gameplay_header(self):
        labels = []
        game = MinigameUI.__new__(MinigameUI)
        game.scene = "demonstration"
        game.settings = {"mode": "EVENT"}
        game.coins_per_credit = 0
        game.credit_count = 0
        game.coin_count = 0
        game._track_key = lambda: "1"
        game._track_position = lambda: 1
        game._image = lambda *args, **kwargs: None
        game._text_image = lambda text, *args, **kwargs: labels.append(text) or len(labels)
        game._build_header()
        self.assertEqual(labels[:2], ["TRACK 1", "GAME"])

    def test_demonstration_excludes_test_and_sample_charts(self):
        game = MinigameUI.__new__(MinigameUI)
        game.charts_by_mode = {
            "2k": (
                SimpleNamespace(folder="/charts/testchart"),
                SimpleNamespace(folder="/charts/sample-chart"),
                SimpleNamespace(folder="/charts/music"),
            ),
        }
        self.assertEqual(
            [chart.folder for chart in game._demonstration_candidates()],
            ["/charts/music"],
        )

    def test_lane_help_and_demonstration_use_translucent_animation_frames(self):
        game = MinigameUI.__new__(MinigameUI)
        game.sources = {
            "lane_help_2k_0": Image.new("RGBA", (20, 60), "white"),
            "demonstration_able": Image.new("RGBA", (80, 20), "white"),
        }
        game.lane_help_source_frames = {}
        game.demonstration_source_frames = {}
        lane_frames = game._lane_help_animation_sources("lane_help_2k_0")
        demonstration_frames = game._demonstration_overlay_sources("demonstration_able")
        self.assertEqual((len(lane_frames), len(demonstration_frames)), (18, 30))
        self.assertIsNone(lane_frames[0].getbbox())
        self.assertIsNotNone(lane_frames[4].getbbox())
        self.assertLess(max(demonstration_frames[0].getchannel("A").getextrema()), 255)

    def test_gameplay_scroll_speed_shortens_note_lead_time(self):
        game = MinigameUI.__new__(MinigameUI)
        game.settings = {"scroll_speed": 1.30}
        self.assertAlmostEqual(game._scroll_lead_time(2.0), 2.0 / 1.30)
        self.assertAlmostEqual(game._scroll_lead_time(1.65), 1.65 / 1.30)

    def test_moderngl_uses_one_design_space_transform(self):
        canvas = ModernGLCanvas.__new__(ModernGLCanvas)
        canvas.width = 540
        canvas.height = 960
        canvas._update_layout()
        self.assertEqual(canvas.layout_scale, 0.5)
        self.assertEqual((canvas.layout_offset_x, canvas.layout_offset_y), (0.0, 0.0))

        deleted = []
        framework = ModernGLUIFramework.__new__(ModernGLUIFramework)
        framework.canvas = SimpleNamespace(delete=deleted.append)
        framework.resize_job = "pending"
        framework._prepare_scene()
        source = Image.new("RGBA", (603, 233))
        self.assertEqual(framework._x(540), 540)
        self.assertEqual(framework._y(960), 960)
        self.assertIs(framework._scaled_photo(source), source)
        self.assertEqual(deleted, ["all"])

    def test_moderngl_center_anchor_centers_both_axes(self):
        self.assertEqual(
            ModernGLCanvas._image_origin(540, 270, 603, 174, "center"),
            (238.5, 183.0),
        )
        self.assertEqual(
            ModernGLCanvas._image_origin(63, 112, 954, 296, "nw"),
            (63, 112),
        )

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
            "catch_line", "line_4k", "health_4k", "health_bg_4k", "mode_4k", "top_gradient", "next_arrow_left",
            "select_sweep", "catch_particle", "catch_scroll",
        }
        self.assertTrue(required <= set(sources))
        self.assertEqual(sources["top_gradient"].size, (1080, 520))
        self.assertEqual(sources["select_sweep"].size, (150, sources["select_bg"].height))
        self.assertEqual(sources["health_4k"].size, sources["health_bg_4k"].size)
        self.assertTrue(all(sources[name].size == (600, 250) for name in ("mode_2k", "mode_4k", "mode_catch")))
        mode_bounds = {
            name: sources[name].getchannel("A").point(lambda value: 255 if value > 4 else 0).getbbox()
            for name in ("mode_2k", "mode_4k", "mode_catch")
        }
        self.assertTrue(all(bounds[2] - bounds[0] <= 560 for bounds in mode_bounds.values()))
        self.assertTrue(all(bounds[3] - bounds[1] <= 230 for bounds in mode_bounds.values()))
        self.assertGreater(mode_bounds["mode_2k"][2] - mode_bounds["mode_2k"][0], 500)
        self.assertTrue(all(sources[f"rank_{rank}"].width <= 190 for rank in "xsabcd"))
        self.assertTrue(all(sources[f"rank_{rank}"].height <= 220 for rank in "xsabcd"))
        game = MinigameUI.__new__(MinigameUI)
        game.sources = sources
        game.rank_reveal_source_frames = {}
        rank_frames = game._rank_reveal_sources("rank_s")
        self.assertEqual(len(rank_frames), 28)
        self.assertIsNone(rank_frames[0].getbbox())
        self.assertIsNotNone(rank_frames[-1].getbbox())
        for name in ("select_bg", "previous"):
            panel = sources[name]
            fill = panel.getpixel((panel.width // 2, panel.height // 2))
            self.assertEqual(panel.getpixel((panel.width // 2, 0)), fill)
            self.assertEqual(panel.getpixel((panel.width - 1, panel.height // 2)), fill)
        self.assertEqual(sfx_root, os.path.join(bgm_root, "sfx"))

    def test_credit_status_and_four_button_serial_input(self):
        game = MinigameUI.__new__(MinigameUI)
        game.coins_per_credit = 0
        game.coin_count = 0
        game.credit_count = 0
        self.assertEqual(game._credit_status_text(), "FREEPLAY")
        game.coins_per_credit = 3
        game.coin_count = 2
        game.credit_count = 4
        self.assertEqual(game._credit_status_text(), "2/3 CREDIT 4")

        pressed = []
        coins = []
        game.settings = {
            "button_1": "sw1", "button_2": "sw2", "button_3": "sw3", "button_4": "sw4",
            "coin_message": "coin",
        }
        game.press_button = pressed.append
        game._insert_coin = lambda: coins.append(True)
        game.serial_buffer = "sw1sw2sw3sw4coin"
        game._drain_serial_buffer(force=True)
        self.assertEqual(pressed, [0, 1, 2, 3])
        self.assertEqual(coins, [True])

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
