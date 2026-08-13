import json
import sys
import tempfile
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import proof_receipt


class ProofReceiptTests(unittest.TestCase):
    def _work(self, root: Path) -> Path:
        work = root / "work"
        work.mkdir()
        source = work / "raw.mov"
        source.write_bytes(b"video")
        (work / "edl.json").write_text(json.dumps({
            "version": 1,
            "sources": {"main": str(source)},
            "ranges": [{"source": "main", "start": 0, "end": 1}],
        }))
        (work / "proof.wav").write_bytes(b"audio")
        (work / "proof_stt").mkdir()
        (work / "proof_stt" / "transcript.json").write_text("{}")
        return work

    def test_exact_inputs_pass(self):
        with tempfile.TemporaryDirectory() as tmp:
            work = self._work(Path(tmp))
            proof_receipt.record(work)
            self.assertEqual(proof_receipt.check(work)["status"], "pass")

    def test_edl_mutation_invalidates_receipt(self):
        with tempfile.TemporaryDirectory() as tmp:
            work = self._work(Path(tmp))
            proof_receipt.record(work)
            (work / "edl.json").write_text("{}")
            with self.assertRaises(ValueError):
                proof_receipt.check(work)


if __name__ == "__main__":
    unittest.main()
