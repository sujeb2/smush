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
        self.mixer.Channel.side_effect = self.channels.__getitem__
        with patch.dict("sys.modules", {"pygame": SimpleNamespace(mixer=self.mixer)}):
            with patch.object(AudioPlayer, "_print"):
                self.player = AudioPlayer()
        self.hit = Mock()
        self.effect = Mock()
        self.player.sfx_cache = {"hitsound.wav": self.hit, "voice.wav": self.effect}
        self.player._print = Mock()

    def test_reserves_hit_channels_and_leaves_room_for_other_effects(self):
        self.assertTrue(self.player.available)
        self.mixer.set_num_channels.assert_called_once_with(48)
        self.mixer.set_reserved.assert_called_once_with(32)

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


if __name__ == "__main__":
    unittest.main()
