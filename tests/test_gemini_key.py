import os
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "lib"))

from gemini_key import resolve_gemini_key


class GeminiKeyTests(unittest.TestCase):
    def test_google_api_key_has_documented_priority(self):
        value, name = resolve_gemini_key({
            "GOOGLE_API_KEY": "google",
            "GEMINI_API_KEY": "gemini",
            "GOOGLE_AI_API_KEY": "legacy",
        })
        self.assertEqual((value, name), ("google", "GOOGLE_API_KEY"))

    def test_gemini_api_key_is_supported(self):
        self.assertEqual(
            resolve_gemini_key({"GEMINI_API_KEY": "gemini"}),
            ("gemini", "GEMINI_API_KEY"),
        )

    def test_legacy_name_remains_compatible(self):
        self.assertEqual(
            resolve_gemini_key({"GOOGLE_AI_API_KEY": "legacy"}),
            ("legacy", "GOOGLE_AI_API_KEY"),
        )

    def test_missing_key_returns_none(self):
        self.assertEqual(resolve_gemini_key({}), (None, None))


if __name__ == "__main__":
    unittest.main()
