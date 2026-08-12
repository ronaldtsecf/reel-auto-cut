import os
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import broll_index
import render_broll


class BrollSafetyTests(unittest.TestCase):
    def test_same_size_and_mtime_cannot_hide_changed_broll(self):
        with tempfile.TemporaryDirectory() as tmp:
            media = Path(tmp) / "clip.mp4"
            media.write_bytes(b"AAAA")
            original = media.stat()
            before = broll_index.sha256(media)
            media.write_bytes(b"BBBB")
            os.utime(media, ns=(original.st_atime_ns, original.st_mtime_ns))
            self.assertEqual(media.stat().st_size, 4)
            self.assertEqual(media.stat().st_mtime_ns, original.st_mtime_ns)
            self.assertNotEqual(before, broll_index.sha256(media))

    def test_broll_output_contract_rejects_wrong_colour_or_audio(self):
        main = {"width": 1080, "height": 1920, "fps": 60.0}
        good = {
            **main, "pix_fmt": "yuv420p", "color_space": "bt709",
            "color_transfer": "bt709", "color_primaries": "bt709",
            "audio_streams": 1,
        }
        self.assertEqual(render_broll.output_failures(good, main), [])
        broken = {**good, "color_transfer": "arib-std-b67", "audio_streams": 0}
        failures = render_broll.output_failures(broken, main)
        self.assertIn("color_transfer=arib-std-b67", failures)
        self.assertIn("audio_streams=0", failures)


if __name__ == "__main__":
    unittest.main()
