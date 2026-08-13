import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import visual_preflight


class VisualPreflightTests(unittest.TestCase):
    def test_hlg_gets_exactly_one_tone_map(self):
        report = visual_preflight.build_source_visual_preflight({
            "pix_fmt": "yuv420p10le",
            "color_space": "bt2020nc",
            "color_transfer": "arib-std-b67",
            "color_primaries": "bt2020",
        })
        self.assertEqual(report["source_color"]["classification"], "hdr_hlg")
        self.assertTrue(report["tone_map_applied"])
        self.assertEqual(report["tone_map_stage_count"], 1)
        self.assertEqual(
            visual_preflight.tone_map_stage_count(report["effective_color_filter"]), 1,
        )

    def test_pq_gets_exactly_one_tone_map(self):
        report = visual_preflight.build_source_visual_preflight({
            "pix_fmt": "yuv420p10le",
            "color_space": "bt2020nc",
            "color_transfer": "smpte2084",
            "color_primaries": "bt2020",
        })
        self.assertEqual(report["source_color"]["classification"], "hdr_pq")
        self.assertEqual(report["tone_map_stage_count"], 1)

    def test_sdr_is_not_tone_mapped(self):
        report = visual_preflight.build_source_visual_preflight({
            "pix_fmt": "yuv420p",
            "color_space": "bt709",
            "color_transfer": "bt709",
            "color_primaries": "bt709",
        })
        self.assertEqual(report["source_color"]["classification"], "sdr")
        self.assertFalse(report["tone_map_applied"])
        self.assertEqual(report["effective_color_filter"], "")

    def test_contradictory_hlg_metadata_fails_closed(self):
        with self.assertRaises(visual_preflight.VisualPreflightError):
            visual_preflight.build_source_visual_preflight({
                "pix_fmt": "yuv420p",
                "color_space": "bt709",
                "color_transfer": "arib-std-b67",
                "color_primaries": "bt709",
            })


if __name__ == "__main__":
    unittest.main()
