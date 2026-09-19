import os
from pathlib import Path
import shutil
import tempfile
import unicodedata
import unittest
from unittest.mock import patch

from font_discovery import find_font, installed_font_directories


FONT = Path(__file__).resolve().parents[1] / 'files/fonts/Novecentosanswide-DemiBold.otf'


class FontDiscoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.installed = self.root / 'installed'
        self.installed.mkdir()
        patcher = patch('font_discovery.installed_font_directories', return_value=(str(self.installed),))
        patcher.start()
        self.addCleanup(patcher.stop)

    def find(self, pattern):
        return find_font(str(self.root), 'fallback.ttf', (pattern,))

    def test_nested_installed_font_matches_case_insensitively(self):
        folder = self.installed / 'family'
        folder.mkdir()
        target = folder / 'novecentosanswide-demibold.OTF'
        shutil.copyfile(FONT, target)
        self.assertEqual(self.find('Novecentosanswide-DemiBold.otf'), str(target))

    def test_korean_unicode_normalization(self):
        target = self.installed / unicodedata.normalize('NFD', '에이투지체-4Regular.ttf')
        shutil.copyfile(FONT, target)
        self.assertEqual(self.find('*에이투지체*4Regular*'), str(target))

    def test_renamed_font_uses_family_metadata(self):
        target = self.installed / 'renamed.otf'
        shutil.copyfile(FONT, target)
        self.assertEqual(self.find('*Novecento*DemiBold*'), str(target))

    def test_invalid_font_is_skipped(self):
        (self.installed / 'broken.otf').write_text('invalid font')
        self.assertEqual(self.find('broken.otf'), 'fallback.ttf')

    def test_bundled_font_wins_same_pattern(self):
        bundled = self.root / 'files/fonts'
        bundled.mkdir(parents=True)
        for directory in (bundled, self.installed):
            shutil.copyfile(FONT, directory / FONT.name)
        self.assertEqual(self.find(FONT.name), str(bundled / FONT.name))

    def test_windows_system_and_per_user_directories(self):
        with patch('font_discovery.sys.platform', 'win32'), patch.dict(os.environ, {
            'WINDIR': '/windows', 'LOCALAPPDATA': '/local',
        }):
            directories = installed_font_directories()
        self.assertIn('/windows/Fonts', directories)
        self.assertIn('/local/Microsoft/Windows/Fonts', directories)
