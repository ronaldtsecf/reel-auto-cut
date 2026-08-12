import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import reel_render_final
import render_edl


class RenderContractTests(unittest.TestCase):
    def test_display_size_respects_rotation_metadata(self):
        payload = '{"streams":[{"width":1920,"height":1080,"side_data_list":[{"rotation":-90}]}]}'
        with mock.patch.object(
            render_edl, "run", return_value=SimpleNamespace(returncode=0, stdout=payload, stderr=""),
        ):
            self.assertEqual(render_edl.ffprobe_size("portrait.mov"), (1080, 1920))

    def test_segment_filter_puts_tone_map_before_fps_and_tags_bt709(self):
        calls = []

        def fake_run(command):
            calls.append(command)
            return SimpleNamespace(returncode=0, stderr="", stdout="")

        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(render_edl, "run", fake_run):
            render_edl.extract(
                "raw.mov", 1.0, 2.0, Path(tmp) / "seg.mov",
                ["-c:v", "libx264"], vf_prefix="tonemap=tonemap=hable",
            )
        command = calls[0]
        vf = command[command.index("-vf") + 1]
        self.assertTrue(vf.startswith("tonemap=tonemap=hable,fps=60"))
        self.assertIn("afade=t=in", command[command.index("-af") + 1])
        self.assertIn("-color_trc", command)
        self.assertEqual(command[command.index("-color_trc") + 1], "bt709")

    def test_final_contract_rejects_wrong_dimensions_or_colour(self):
        good = {
            "width": 1080, "height": 1920, "fps": 60.0,
            "pix_fmt": "yuv420p", "color_space": "bt709",
            "color_transfer": "bt709", "color_primaries": "bt709",
            "audio_streams": 1,
        }
        self.assertEqual(reel_render_final.validate_final(good), [])
        broken = {**good, "width": 1920, "color_transfer": "arib-std-b67"}
        failures = reel_render_final.validate_final(broken)
        self.assertTrue(any(item.startswith("size=") for item in failures))
        self.assertIn("color_transfer=arib-std-b67", failures)


if __name__ == "__main__":
    unittest.main()
