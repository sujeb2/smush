import os
import tempfile
import time
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from game.gameflow import MinigameFlowMixin
from game.displays import station_geometries
from game.selection_sync import read_selection
from game.AnimationFramework import MinigameAnimationMixin
from game.scenes import MinigameGameSceneMixin
from game.AssetWorker import IMAGE_PATHS


class EntryStation(MinigameFlowMixin):
    def __init__(self, session_dir, station):
        self.session_dir = session_dir
        self.station = station
        self.entry_round = 1
        self.entry_joined = False
        self._play_sfx = Mock()
        self._refresh_entry_joined = Mock()
        self._build_scene = Mock()


class SelectionStation(EntryStation):
    def __init__(self, session_dir, station, charts):
        super().__init__(session_dir, station)
        self.two_player = True
        self.scene = "select"
        self.game_mode = "4k"
        self.extra_stage_active = False
        self.song_groups = charts
        self.track_index = 0
        self.song_index = 0
        self.difficulty_index = 0
        self.selection_phase = "song"
        self.track = charts[0][0]
        self.rebuilt = 0
        self.wheel_turns = 0
        self.next_seen = False
        self.mode_confirmed = False
        self.loading_phase = None
        self.transition_phase = None

    def _build_scene(self):
        self.rebuilt += 1

    def _start_selection_wheel(self, direction):
        self.wheel_turns += direction

    def _schedule_select_preview(self, delay):
        pass

    def show_next(self):
        self.next_seen = True

    def _confirm_mode(self):
        self.mode_confirmed = True


class EntryAnimationHarness(MinigameAnimationMixin):
    two_player = True

    def __init__(self, joined, release_at=None, mode="duo"):
        self.joined = joined
        self.release_at = release_at
        self.mode = mode
        self.warning_started_at = None

    def _sync_entry_round(self):
        pass

    def _entry_decision(self):
        if self.release_at is None:
            return None
        return {"mode": self.mode, "at": self.release_at, "station": 1}

    def _refresh_entry_joined(self):
        return self.joined

    def _entry_release_at(self):
        return self.release_at

    def show_warning(self, started_at=None):
        self.warning_started_at = started_at


class TwoPlayerEntryTests(unittest.TestCase):
    def test_either_client_entering_entry_brings_the_other_client_into_same_round(self):
        for initiating_station in (1, 2):
            with self.subTest(station=initiating_station), tempfile.TemporaryDirectory() as session_dir:
                stations = [EntryStation(session_dir, station) for station in (1, 2)]
                for client in stations:
                    client.two_player = True
                    client.preload_complete = True
                    client.scene = "title"
                    client.root = Mock()
                    client._print = Mock()
                    client._play_entry_audio = Mock()
                initiator = stations[initiating_station - 1]
                follower = stations[2 - initiating_station]
                follower.loading_phase = "fading_out"
                follower.loading_action = Mock()
                initiator.show_entry()
                follower._follow_shared_entry()
                self.assertEqual((initiator.scene, follower.scene), ("entry", "entry"))
                self.assertEqual(initiator.entry_round, follower.entry_round)
                self.assertAlmostEqual(initiator.scene_started, follower.scene_started, delta=0.1)
                self.assertIsNone(follower.loading_phase)
                initiator._join_entry()
                initiator._follow_shared_entry()
                self.assertTrue(initiator.entry_joined)
                self.assertEqual(follower._joined_stations(), [initiating_station])

    def test_shared_entry_waits_for_other_client_to_finish_preloading(self):
        with tempfile.TemporaryDirectory() as session_dir:
            first = EntryStation(session_dir, 1)
            second = EntryStation(session_dir, 2)
            for client in (first, second):
                client.two_player = True
                client.root = Mock()
                client._print = Mock()
                client._play_entry_audio = Mock()
            first.scene = "title"
            first.preload_complete = True
            second.scene = "preload"
            second.preload_complete = False
            first.show_entry()
            second._follow_shared_entry()
            self.assertEqual(second.scene, "preload")
            second.scene = "title"
            second.preload_complete = True
            second._follow_shared_entry()
            self.assertEqual(second.scene, "entry")

    def test_waiting_asset_is_registered(self):
        self.assertEqual(IMAGE_PATHS["entry_waiting"], ("generic", "entry", "entry_waiting.png"))
        self.assertEqual(IMAGE_PATHS["rival_joined"], ("generic", "entry", "rival", "rival_joined.png"))

    def test_first_join_waits_without_timer_and_both_join_release_together(self):
        first_only = EntryAnimationHarness([1])
        first_only._animate_entry(1000.0)
        self.assertIsNone(first_only.warning_started_at)
        both = EntryAnimationHarness([1, 2], time.time() - 0.1)
        both._animate_entry(1000.0)
        self.assertIsNotNone(both.warning_started_at)

    def test_solo_decision_advances_both_clients_at_shared_release(self):
        release_at = time.time() - 0.1
        for station in (1, 2):
            client = EntryAnimationHarness([1], release_at, mode="solo")
            client.station = station
            client._animate_entry(1000.0)
            self.assertIsNotNone(client.warning_started_at)
            self.assertTrue(client.solo_active)

    def test_game_audio_waits_until_both_stations_are_ready(self):
        with tempfile.TemporaryDirectory() as session_dir:
            first = EntryStation(session_dir, 1)
            second = EntryStation(session_dir, 2)
            for station in (first, second):
                station.track = SimpleNamespace(path="/charts/shared.osu")
                station.track_index = 0
                station.extra_stage_active = False
                station.how_to_play_pre_roll = 2.0
            first._mark_game_ready()
            self.assertIsNone(first._game_release_at())
            second._mark_game_ready()
            self.assertEqual(first._game_release_at(), second._game_release_at())
            self.assertGreater(first._game_release_at(), time.time())

    def test_chart_audio_starts_only_after_shared_release(self):
        with tempfile.TemporaryDirectory() as session_dir:
            first = EntryStation(session_dir, 1)
            second = EntryStation(session_dir, 2)
            for station in (first, second):
                station.two_player = True
                station.running = True
                station.scene = "game"
                station.track = SimpleNamespace(path="/charts/shared.osu", audio_path="shared.mp3")
                station.track_index = 0
                station.extra_stage_active = False
                station.how_to_play_pre_roll = 2.0
                station.game_audio_offset = 0.0
                station.root = Mock()
                station.audio = Mock()
                station._print = Mock()
            first._mark_game_ready()
            first._start_chart_audio()
            first.audio.play.assert_not_called()
            first.root.after.assert_called_once_with(30, first._start_chart_audio)
            second._mark_game_ready()
            release_at = first._game_release_at()
            with patch("game.gameflow.time.time", return_value=release_at + 0.01):
                first._start_chart_audio()
                second._start_chart_audio()
            first.audio.play.assert_called_once_with("shared.mp3", start_seconds=0.0)
            second.audio.play.assert_called_once_with("shared.mp3", start_seconds=0.0)

    def test_either_player_can_change_song_and_first_confirmation_locks_it(self):
        charts = ((SimpleNamespace(path="song-a"),), (SimpleNamespace(path="song-b"),))
        with tempfile.TemporaryDirectory() as session_dir:
            first = SelectionStation(session_dir, 1, charts)
            second = SelectionStation(session_dir, 2, charts)
            second.song_index = 1
            second.track = charts[1][0]
            self.assertTrue(second._broadcast_selection("select"))
            first._poll_shared_selection()
            self.assertEqual(first.track.path, "song-b")
            first.song_index = 0
            first.track = charts[0][0]
            self.assertTrue(first._broadcast_selection("select"))
            second._poll_shared_selection()
            self.assertEqual(second.track.path, "song-a")
            self.assertTrue(second._broadcast_selection("next"))
            first.song_index = 1
            first.track = charts[1][0]
            self.assertFalse(first._broadcast_selection("select"))
            self.assertEqual(first.track.path, "song-a")
            self.assertTrue(first.next_seen)
            self.assertEqual(read_selection(first._selection_sync_path())["chart_path"], "song-a")

    def test_rival_single_step_turns_the_wheel_and_jumps_rebuild(self):
        charts = tuple((SimpleNamespace(path=f"song-{index}"),) for index in range(5))
        with tempfile.TemporaryDirectory() as session_dir:
            first = SelectionStation(session_dir, 1, charts)
            second = SelectionStation(session_dir, 2, charts)
            first.song_index, first.track = 1, charts[1][0]
            first._broadcast_selection("select")
            second._poll_shared_selection()
            self.assertEqual((second.wheel_turns, second._build_scene.call_count), (1, 0))
            first.song_index, first.track = 4, charts[4][0]
            first._broadcast_selection("select")
            second._poll_shared_selection()
            self.assertEqual((second.wheel_turns, second._build_scene.call_count), (1, 1))
            self.assertEqual(second.track.path, "song-4")

    def test_player_two_follows_mode_confirmation(self):
        charts = ((SimpleNamespace(path="song-a"),),)
        with tempfile.TemporaryDirectory() as session_dir:
            first = SelectionStation(session_dir, 1, charts)
            second = SelectionStation(session_dir, 2, charts)
            second.scene = "mode_select"
            first._broadcast_selection("mode")
            second._poll_shared_selection()
            self.assertTrue(second.mode_confirmed)

    def test_player_two_controls_shared_selection_when_starting_solo(self):
        charts = ((SimpleNamespace(path="song-a"),), (SimpleNamespace(path="song-b"),))
        with tempfile.TemporaryDirectory() as session_dir:
            first = SelectionStation(session_dir, 1, charts)
            second = SelectionStation(session_dir, 2, charts)
            first._write_entry_state({"round": 1, "mode": "solo", "station": 2, "at": time.time()})
            first.solo_active = second.solo_active = True
            first.scene = "mode_select"
            self.assertEqual(second._entry_controller_station(), 2)
            self.assertTrue(second._broadcast_selection("mode"))
            first._poll_shared_selection()
            self.assertTrue(first.mode_confirmed)
            first.scene = "select"
            second.song_index = 1
            second.track = charts[1][0]
            self.assertTrue(second._broadcast_selection("select"))
            first._poll_shared_selection()
            self.assertEqual(first.track.path, "song-b")

    def test_song_difficulty_and_confirmation_follow_player_one(self):
        charts = ((SimpleNamespace(path="song-a-easy"), SimpleNamespace(path="song-a-hard")),
                  (SimpleNamespace(path="song-b-easy"),))
        with tempfile.TemporaryDirectory() as session_dir:
            first = SelectionStation(session_dir, 1, charts)
            second = SelectionStation(session_dir, 2, charts)
            first.song_index = 1
            first.track = charts[1][0]
            first._broadcast_selection("select")
            second._poll_shared_selection()
            self.assertEqual((second.song_index, second.track.path), (1, "song-b-easy"))
            first.song_index = 0
            first.difficulty_index = 1
            first.selection_phase = "difficulty"
            first.track = charts[0][1]
            first._broadcast_selection("select")
            second._poll_shared_selection()
            self.assertEqual((second.song_index, second.difficulty_index, second.track.path),
                             (0, 1, "song-a-hard"))
            first._broadcast_selection("next")
            second._poll_shared_selection()
            self.assertTrue(second.next_seen)

    def test_demo_places_two_windows_on_one_monitor(self):
        self.assertEqual(
            station_geometries([(0, 0, 1920, 1080)], windowed=True),
            ["540x960+420+60", "540x960+960+60"],
        )

    def test_fullscreen_requires_two_monitors(self):
        with self.assertRaises(ValueError):
            station_geometries([(0, 0, 1920, 1080)])

    def test_join_markers_are_independent_and_visible_to_both_stations(self):
        with tempfile.TemporaryDirectory() as session_dir:
            first = EntryStation(session_dir, 1)
            second = EntryStation(session_dir, 2)
            first._write_entry_state({"round": 1})
            self.assertEqual(first._joined_stations(), [])
            first._join_entry()
            self.assertIsNone(first._entry_release_at())
            second._join_entry()
            self.assertEqual(first._joined_stations(), [1, 2])
            self.assertEqual(second._joined_stations(), [1, 2])
            self.assertEqual(first._entry_release_at(), second._entry_release_at())
            self.assertIsNotNone(first._entry_release_at())
            first._clear_join_marker()
            self.assertEqual(second._joined_stations(), [2])

    def test_joined_player_can_choose_solo_and_late_join_cannot_change_it(self):
        with tempfile.TemporaryDirectory() as session_dir:
            first = EntryStation(session_dir, 1)
            second = EntryStation(session_dir, 2)
            first._write_entry_state({"round": 1})
            first._join_entry()
            first._start_single_entry()
            self.assertEqual(first._entry_decision()["mode"], "solo")
            self.assertIsNotNone(first._entry_release_at())
            self.assertEqual(first._entry_release_at(), second._entry_release_at())
            second._join_entry()
            self.assertFalse(second.entry_joined)
            self.assertEqual(second._joined_stations(), [1])
            first._advance_entry_round()
            second._sync_entry_round()
            self.assertEqual(second.entry_round, 2)
            self.assertIsNone(second._entry_decision())

    def test_either_station_can_start_solo_with_bt1_after_joining(self):
        for station_number in (1, 2):
            with self.subTest(station=station_number), tempfile.TemporaryDirectory() as session_dir:
                station = EntryStation(session_dir, station_number)
                station._write_entry_state({"round": 1})
                station.two_player = True
                station.running = True
                station.scene = "entry"
                station.entry_choice = None
                station.transition_phase = None
                station.loading_phase = None
                station.entry_title_fade_started = None
                station.title_entry_morph_started = None
                station.mode_morph_in_started = None
                station.press_button(0)
                self.assertTrue(station.entry_joined)
                self.assertIsNone(station._entry_decision())
                station.press_button(0)
                self.assertEqual(station._entry_decision()["mode"], "solo")
                self.assertEqual(station._entry_decision()["station"], station_number)

    def test_old_round_cannot_release_new_entry(self):
        with tempfile.TemporaryDirectory() as session_dir:
            first = EntryStation(session_dir, 1)
            with open(first._join_marker(2), "w", encoding="ascii") as marker:
                marker.write(f"1 {time.time()}")
            first.entry_round = 2
            self.assertEqual(first._joined_stations(), [])
            self.assertIsNone(first._entry_release_at())


class FlowStation(MinigameFlowMixin, MinigameGameSceneMixin):

    def __init__(self, session_dir, station, cleared=True, scene="result"):
        self.two_player = True
        self.session_dir = session_dir
        self.station = station
        self.entry_round = 1
        self.scene = scene
        self.scene_started = time.monotonic() - 10.0
        self.loading_phase = None
        self.track_index = 0
        self.extra_stage_active = False
        self.health = 100.0 if cleared else 0.0
        self.result_unlock_at = 0.0
        self.track_scores = [0] * 3
        self.track_names = [""] * 3
        self.track_ranks = [""] * 3
        self.progress_path = os.path.join(session_dir, f"progress_{station}.json")
        self.extra_charts_by_mode = {"4k": (object(),), "catch": ()}
        self.extra_challenge_prompt = False
        self.extra_challenge_started = None
        self.total_result_count_channel = None
        self.game_ended_exit_started = None
        self.audio = Mock()
        self._play_sfx = Mock()
        self._stop_result_rank_audio = Mock()
        self._print = Mock()
        self.loading_targets = []

    def _start_loading(self, target, action):
        self.loading_targets.append(target)
        self.loading_phase = "fading_out"


class TwoPlayerFlowTests(unittest.TestCase):
    def publish_results(self, *stations, extra=False):
        for station in stations:
            station._publish_station_result(extra)

    def test_result_to_music_select_follows_rival_even_when_one_player_failed(self):
        for initiating_station in (1, 2):
            with self.subTest(station=initiating_station), tempfile.TemporaryDirectory() as session_dir:
                stations = (FlowStation(session_dir, 1, cleared=True), FlowStation(session_dir, 2, cleared=False))
                self.publish_results(*stations)
                initiator = stations[initiating_station - 1]
                follower = stations[2 - initiating_station]
                initiator.start_result_transition()
                self.assertEqual(follower.loading_targets, [])
                follower._poll_flow()
                for station in stations:
                    self.assertEqual(station.loading_targets, ["select"])
                    self.assertEqual(station.track_index, 1)

    def test_both_failed_players_end_together(self):
        with tempfile.TemporaryDirectory() as session_dir:
            stations = (FlowStation(session_dir, 1, cleared=False), FlowStation(session_dir, 2, cleared=False))
            self.publish_results(*stations)
            stations[0].start_result_transition()
            stations[1]._poll_flow()
            self.assertEqual([station.loading_targets for station in stations], [["game_ended"], ["game_ended"]])

    def test_first_decision_wins_when_both_players_press_at_once(self):
        with tempfile.TemporaryDirectory() as session_dir:
            first, second = FlowStation(session_dir, 1), FlowStation(session_dir, 2)
            first.track_index = second.track_index = 2
            self.publish_results(first, second, extra=True)
            first.extra_challenge_prompt = True
            first.extra_challenge_started = 0.0
            first._accept_extra_challenge()
            second.start_result_transition()
            self.assertEqual(first.loading_targets, ["select"])
            self.assertEqual(second.loading_targets, ["select"])
            self.assertEqual((first.track_index, second.track_index), (0, 0))
            first._poll_flow()
            self.assertEqual(first.loading_targets, ["select"])

    def test_total_result_and_game_ended_exits_are_shared(self):
        with tempfile.TemporaryDirectory() as session_dir:
            first = FlowStation(session_dir, 1, scene="total_result")
            second = FlowStation(session_dir, 2, scene="total_result")
            second.start_total_result_transition()
            first._poll_flow()
            self.assertEqual((first.loading_targets, second.loading_targets), (["game_ended"], ["game_ended"]))
            for station in (first, second):
                station.scene, station.loading_phase = "game_ended", None
            first.start_game_ended_transition()
            second._poll_flow()
            self.assertIsNotNone(second.game_ended_exit_started)

    def test_decision_from_an_earlier_stage_is_ignored(self):
        with tempfile.TemporaryDirectory() as session_dir:
            first, second = FlowStation(session_dir, 1), FlowStation(session_dir, 2)
            self.publish_results(first, second)
            first.start_result_transition()
            second.track_index = 1
            second._poll_flow()
            self.assertEqual(second.loading_targets, [])

    def test_rival_rank_compares_live_scores_and_ignores_previous_song(self):
        with tempfile.TemporaryDirectory() as session_dir:
            first = FlowStation(session_dir, 1, scene="game")
            second = FlowStation(session_dir, 2, scene="game")
            for station in (first, second):
                station.canvas = Mock()
                station._asset_photo = lambda name: name
                station.rival_rank_item = 1
                station.rival_rank_shown = "rival_1st_watermark"
            second.track_index = 1
            second.score = 90000
            second._update_rival_rank()
            first.score = 500
            first._update_rival_rank()
            self.assertEqual(first.rival_rank_shown, "rival_1st_watermark")
            second.track_index = 0
            second.score = 1000
            second._update_rival_rank()
            first._update_rival_rank()
            self.assertEqual(first.rival_rank_shown, "rival_2nd_watermark")
            self.assertEqual(second.rival_rank_shown, "rival_1st_watermark")

    def test_rival_rank_updates_while_the_game_scene_is_running(self):
        game = SimpleNamespace(
            running=True, unrecoverable_error=False, two_player=True, solo_active=False, scene="game",
            loading_phase=None, transition_phase=None, how_to_play_mode=None, root=Mock(),
            _poll_events=Mock(), _follow_shared_entry=Mock(), _poll_flow=Mock(), _update_rival_rank=Mock(),
            _animate_game_media=Mock(), _update_game_frame=Mock(), _animate=Mock(),
        )
        MinigameAnimationMixin._animate(game)
        game._update_rival_rank.assert_called_once()


if __name__ == "__main__":
    unittest.main()
