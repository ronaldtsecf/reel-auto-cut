import os
import sys
import tempfile
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import transcribe


class TranscribeCacheIdentityTests(unittest.TestCase):
    def test_digest_is_content_based_not_path_based(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            first = root / "a.mov"
            second = root / "b.mov"
            first.write_bytes(b"same media bytes")
            second.write_bytes(b"same media bytes")
            self.assertEqual(transcribe.source_sha256(first), transcribe.source_sha256(second))

    def test_same_size_and_mtime_cannot_hide_changed_bytes(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "raw.mov"
            path.write_bytes(b"AAAA")
            original_stat = path.stat()
            before = transcribe.source_sha256(path)
            path.write_bytes(b"BBBB")
            os.utime(path, ns=(original_stat.st_atime_ns, original_stat.st_mtime_ns))
            self.assertEqual(path.stat().st_size, 4)
            self.assertEqual(path.stat().st_mtime_ns, original_stat.st_mtime_ns)
            self.assertNotEqual(before, transcribe.source_sha256(path))


if __name__ == "__main__":
    unittest.main()
