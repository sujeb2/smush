import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from game.AudioManager import AudioPlayer


class HitsoundChannelTests(unittest.TestCase):
    def setUp(self):
        self.channels = [Mock() for _ in range(AudioPlayer.HITSOUND_CHANNEL_COUNT)]
        for channel in self.channels:
            channel.get_busy.return_value = False
            channel.play.side_effect = lambda sound, channel=channel: setattr(
                channel.get_busy, "return_value", True,
            )
        self.mixer = Mock()
        self.mixer.get_num_channels.return_value = 8
        self.layer_channels = [Mock() for _ in range(AudioPlayer.LAYER_CHANNEL_COUNT)]
        self.mixer.Channel.side_effect = (self.channels + self.layer_channels).__getitem__
        with patch.dict("sys.modules", {"pygame": SimpleNamespace(mixer=self.mixer)}):
            with patch.object(AudioPlayer, "_print"):
                self.player = AudioPlayer()
        self.hit = Mock()
        self.effect = Mock()
        self.player.sfx_cache = {"hitsound.wav": self.hit, "voice.wav": self.effect}
        self.player._print = Mock()

    def test_reserves_hit_channels_and_leaves_room_for_other_effects(self):
        self.assertTrue(self.player.available)
        self.mixer.set_num_channels.assert_called_once_with(52)
        self.mixer.set_reserved.assert_called_once_with(36)

    def test_rapid_hits_overlap_and_reuse_oldest_only_when_full(self):
        for expected in self.channels:
            self.assertIs(self.player.play_sfx("hitsound.wav", volume=0.45), expected)
        self.assertTrue(all(channel.play.call_count == 1 for channel in self.channels))
        for expected in self.channels[:4]:
            self.assertIs(self.player.play_sfx("hitsound.wav", volume=0.45), expected)
        self.assertEqual([c.play.call_count for c in self.channels], [2] * 4 + [1] * 28)
        self.hit.play.assert_not_called()
        for channel in self.channels:
            channel.set_volume.assert_called_with(0.45)
        self.mixer.music.play.assert_not_called()
        self.mixer.music.stop.assert_not_called()
        self.mixer.find_channel.assert_not_called()

    def test_reuses_finished_channel_before_interrupting_any_hit(self):
        for _ in self.channels:
            self.player.play_sfx("hitsound.wav")
        self.channels[9].get_busy.return_value = False
        self.assertIs(self.player.play_sfx("hitsound.wav"), self.channels[9])
        self.assertEqual(self.channels[0].play.call_count, 1)
        # Reusing a finished channel makes it the newest, not the next victim.
        self.assertIs(self.player.play_sfx("hitsound.wav"), self.channels[0])

    def test_other_effects_keep_automatic_channel_allocation(self):
        channel = self.player.play_sfx("voice.wav", volume=0.6)
        self.assertIs(channel, self.effect.play.return_value)
        channel.set_volume.assert_called_once_with(0.6)
        self.assertTrue(all(not item.play.called for item in self.channels))


    def test_layers_loop_in_sync_and_unmute_cumulatively(self):
        stems = [Mock(), Mock(), Mock()]
        self.player.sfx_cache.update(zip(("l0", "l1", "l2"), stems))
        with patch("os.path.isfile", return_value=True):
            self.player.play_layers(["l0", "l1", "l2"], level=0, fade_ms=320)
        for channel, stem in zip(self.layer_channels, stems):
            channel.play.assert_called_once_with(stem, loops=-1, fade_ms=320)
        self.assertEqual([c.set_volume.call_args.args[0] for c in self.layer_channels[:3]], [1.0, 0.0, 0.0])
        for channel in self.layer_channels:
            channel.get_volume.return_value = channel.set_volume.call_args.args[0] if channel.set_volume.called else 0.0
        with patch("threading.Thread") as thread:
            self.player.set_layer_level(1, fade_ms=0)
            thread.call_args.kwargs["target"]()
        self.assertEqual([c.set_volume.call_args.args[0] for c in self.layer_channels[:3]], [1.0, 1.0, 0.0])
        self.player.stop(250)
        for channel in self.layer_channels:
            channel.fadeout.assert_called_once_with(250)

    def test_missing_layer_falls_back_to_full_mix(self):
        self.player.play_layers(["missing_l0.wav"], fallback_path="entry.mp3")
        self.assertTrue(all(not channel.play.called for channel in self.layer_channels))


if __name__ == "__main__":
    unittest.main()
