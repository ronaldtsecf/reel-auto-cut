import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
SPEC = importlib.util.spec_from_file_location("reel_preflight", ROOT / "scripts" / "preflight.py")
preflight = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(preflight)


class PreflightExitTests(unittest.TestCase):
    def test_warning_is_allowed_in_normal_mode(self):
        report = {"critical_failures": [], "warnings": ["gemini_key"]}
        self.assertFalse(preflight.should_fail(report, strict=False))

    def test_warning_fails_strict_mode(self):
        report = {"critical_failures": [], "warnings": ["gemini_key"]}
        self.assertTrue(preflight.should_fail(report, strict=True))

    def test_critical_failure_always_fails(self):
        report = {"critical_failures": ["ffmpeg"], "warnings": []}
        self.assertTrue(preflight.should_fail(report, strict=False))

    def test_required_ffmpeg_filters_are_critical(self):
        self.assertIn("ffmpeg_filters", preflight.CRITICAL_CHECKS)


if __name__ == "__main__":
    unittest.main()
