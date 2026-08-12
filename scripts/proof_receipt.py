#!/usr/bin/env python3
"""Bind the fast audio proof to the exact EDL, source, proof audio, and STT."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path


SCHEMA = "reel-auto-cut.proof-pass"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(4 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def inputs(work: Path) -> dict:
    edl_path = work / "edl.json"
    proof_audio = work / "proof.wav"
    proof_stt = work / "proof_stt" / "transcript.json"
    for path in (edl_path, proof_audio, proof_stt):
        if not path.is_file():
            raise ValueError(f"缺 {path.relative_to(work)}")
    edl = json.loads(edl_path.read_text(encoding="utf-8"))
    source_values = list(edl.get("sources", {}).values())
    if len(source_values) != 1:
        raise ValueError("proof 暫時只支援 single-source EDL")
    source = Path(source_values[0]).expanduser().resolve()
    if not source.is_file():
        raise ValueError(f"source 不存在：{source}")
    return {
        "edl": {"path": "edl.json", "sha256": sha256(edl_path)},
        "source": {"path": str(source), "sha256": sha256(source)},
        "proof_audio": {"path": "proof.wav", "sha256": sha256(proof_audio)},
        "proof_stt": {"path": "proof_stt/transcript.json", "sha256": sha256(proof_stt)},
    }


def record(work: Path) -> Path:
    receipt_path = work / "proof_pass.json"
    receipt_path.write_text(json.dumps({
        "schema": SCHEMA,
        "version": 1,
        "status": "pass",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "inputs": inputs(work),
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return receipt_path


def check(work: Path) -> dict:
    receipt_path = work / "proof_pass.json"
    if not receipt_path.is_file():
        raise ValueError("缺 proof_pass.json；先跑 proof_check.sh")
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    if receipt.get("schema") != SCHEMA or receipt.get("version") != 1 or receipt.get("status") != "pass":
        raise ValueError("proof receipt 格式／狀態無效")
    actual = inputs(work)
    if receipt.get("inputs") != actual:
        raise ValueError("EDL／source／proof 已改；舊 proof 失效，請重跑 proof_check.sh")
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["record", "check"])
    parser.add_argument("work", type=Path)
    args = parser.parse_args()
    work = args.work.expanduser().resolve()
    try:
        result = record(work) if args.command == "record" else check(work)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"PROOF FAIL：{exc}")
        return 2
    print(result if isinstance(result, Path) else "PROOF RECEIPT PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
