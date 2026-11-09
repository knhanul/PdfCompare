import os
import unittest
from pathlib import Path

from PIL import Image

from app.common.resources import get_icon_path

ROOT = Path(__file__).resolve().parents[1]
MSIX = ROOT / 'assets' / 'posid' / 'msix'


class TestBrandIcons(unittest.TestCase):
    def test_runtime_icon_found_for_target(self):
        p = get_icon_path()
        self.assertIsNotNone(p)
        self.assertTrue(p.endswith('.ico'))

    def test_ico_multi_resolution_and_alpha(self):
        im = Image.open(ROOT / 'assets' / 'posid' / 'posid_icon.ico')
        sizes = im.ico.sizes()
        for s in (16, 32, 48, 256):
            self.assertIn((s, s), sizes)
        a = im.convert('RGBA').getchannel('A')
        self.assertEqual(a.getpixel((0, 0)), 0)

    def test_msix_unplated_assets_transparent(self):
        files = sorted(MSIX.glob('*altform-unplated.png'))
        self.assertGreaterEqual(len(files), 5)
        for f in files:
            im = Image.open(f)
            self.assertEqual(im.mode, 'RGBA', f.name)
            a = im.getchannel('A')
            w, h = im.size
            self.assertEqual(a.getpixel((0, 0)), 0, f.name)
            self.assertEqual(a.getpixel((w - 1, h - 1)), 0, f.name)
            self.assertEqual(a.getextrema()[1], 255, f.name)


if __name__ == '__main__':
    unittest.main()
