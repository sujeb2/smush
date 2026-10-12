import os
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, call

from game.rules import group_charts_by_song, group_songs_into_folders
from test_selection_wheel import select_game


def chart(title, artist, level, difficulty="NORMAL"):
    return SimpleNamespace(
        title=title, artist=artist, difficulty=difficulty, level=level, path=f"{title}-{difficulty}.osu",
        video_path=None, background_path=None, preview_time=-1, audio_path=f"{title}.mp3",
        has_scroll_speed_changes=False,
    )


CHARTS = (
    chart("Zeta", "frums", 3), chart("Zeta", "frums", 9, "HARD"),
    chart("Alpha", "Camellia", 9),
    chart("Mid", "Frums", 3),
)


def folder_game():
    game = select_game()
    game.charts = CHARTS
    game.song_groups = group_charts_by_song(CHARTS)
    game.audio = Mock()
    game._play_sfx, game._print = Mock(), Mock()
    game.bgm_root = os.path.join("game", "bgm")
    for name in ("transition_phase", "loading_phase", "entry_title_fade_started",
                 "title_entry_morph_started", "mode_morph_in_started", "select_fade_in_started",
                 "select_morph_in_started"):
        setattr(game, name, None)
    game._reset_selection()
    game._build_scene()
    return game


def song_names(game, folder):
    return [game.song_groups[index][0].title for index in folder.songs]


class SongFolderTests(unittest.TestCase):
    def test_level_folders_ascend_then_artists_alphabetical_with_titles_sorted(self):
        game = folder_game()
        folders = group_songs_into_folders(game.song_groups)
        self.assertEqual([folder.name for folder in folders],
                         ["ALL SONGS", "LEVEL 3", "LEVEL 9", "Camellia", "frums"])
        self.assertEqual(song_names(game, folders[0]), ["Alpha", "Mid", "Zeta"])
        self.assertEqual(song_names(game, folders[1]), ["Mid", "Zeta"])
        self.assertEqual(song_names(game, folders[2]), ["Alpha", "Zeta"])
        # Artist names group case-insensitively.
        self.assertEqual(song_names(game, folders[4]), ["Mid", "Zeta"])

    def test_select_starts_on_closed_folders_with_every_bgm_layer(self):
        game = folder_game()
        game._start_select_audio()
        self.assertEqual(game.selection_phase, "folder")
        paths, = game.audio.play_layers.call_args.args
        self.assertEqual([os.path.basename(path)[:8] for path in paths], ["entry_l0", "entry_l1", "entry_l2"])
        self.assertEqual(game.audio.play_layers.call_args.kwargs["level"], 2)
        game._schedule_select_preview.assert_not_called()

    def test_btn1_cycles_folders_and_btn2_opens_with_card_sound(self):
        game = folder_game()
        for index in (1, 2):  # LEVEL 3, then LEVEL 9.
            game.press_button(0)
            self.assertEqual((game.selection_phase, game.folder_index), ("folder", index))
            game._finish_selection_wheel()
        game._play_sfx.reset_mock()
        game.press_button(1)
        self.assertEqual(game.selection_phase, "song")
        game._play_sfx.assert_called_once_with("card_show.wav")
        # LEVEL 9 opens on its first song, already on the level-9 chart.
        self.assertEqual((game.track.title, game.track.level), ("Alpha", 9))
        game._schedule_select_preview.assert_called_with(1.0)

    def test_song_from_a_level_folder_still_offers_every_difficulty(self):
        game = folder_game()
        for _ in range(2):  # LEVEL 9.
            game.press_button(0)
            game._finish_selection_wheel()
        game.press_button(1)
        game.press_button(0)
        game._finish_selection_wheel()
        self.assertEqual((game.track.title, game.track.level), ("Zeta", 9))
        game.press_button(1)
        self.assertEqual(game.selection_phase, "difficulty")
        self.assertEqual(game._selection_choices(), (("NORMAL", "HARD"), 0))
        self.assertEqual(game.track.level, 3)
        game.press_button(0)
        game._finish_selection_wheel()
        self.assertEqual((game.track.difficulty, game.track.level), ("HARD", 9))

    def test_btn1_on_the_open_folder_card_closes_it_with_card_sound(self):
        game = folder_game()
        game.press_button(1)
        for _ in range(3):  # ALL SONGS: Mid, Zeta, then its own card.
            game.press_button(0)
            game._finish_selection_wheel()
        self.assertEqual((game.folder_cursor, game._on_folder_card()), (0, True))
        game._play_sfx.reset_mock()
        game.audio.play_layers.reset_mock()
        game.press_button(0)
        self.assertEqual((game.selection_phase, game.folder_index), ("folder", 0))
        game._play_sfx.assert_called_once_with("card_show.wav")
        self.assertEqual(game.audio.play_layers.call_args.kwargs["level"], 2)

    def test_folder_list_never_starts_a_song_preview(self):
        game = folder_game()
        game._play_track_preview = Mock()
        game.select_preview_deadline = 0.0
        game._animate_select_preview(10.0)
        game._play_track_preview.assert_not_called()


if __name__ == "__main__":
    unittest.main()
