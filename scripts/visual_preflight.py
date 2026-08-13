#!/usr/bin/env python3
"""Deterministic source-colour checks and one canonical HDR-to-SDR chain.

The renderer must understand the source pixels before it changes frame rate,
size, or style.  Explicit HLG/PQ sources are converted exactly once to
8-bit BT.709; ordinary SDR sources are left alone.  Risky, contradictory
metadata fails closed instead of silently producing a grey or washed-out reel.
"""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path


HLG_TRANSFERS = {"arib-std-b67", "hlg"}
PQ_TRANSFERS = {"smpte2084", "pq"}
SDR_TRANSFERS = {
    "bt709", "smpte170m", "gamma22", "gamma28", "iec61966-2-1",
    "bt470m", "bt470bg",
}
BT2020_MATRICES = {"bt2020nc", "bt2020_ncl", "bt2020c", "bt2020_cl"}
UNKNOWN_VALUES = {"", "unknown", "unspecified", "reserved", "none", "n/a"}


class VisualPreflightError(ValueError):
    """The source metadata is not safe enough for automatic colour routing."""


def _value(value) -> str:
    return str(value or "unknown").strip().casefold()


def probe_source_color(path: Path) -> dict:
    """Read the four video fields needed for deterministic colour routing."""
    result = subprocess.run(
        [
            "ffprobe", "-v", "error", "-select_streams", "v:0",
            "-show_entries",
            "stream=pix_fmt,color_space,color_transfer,color_primaries",
            "-of", "json", str(path),
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise VisualPreflightError(
            f"ffprobe 讀唔到 {path.name} 色彩 metadata：{result.stderr[-300:]}"
        )
    try:
        stream = (json.loads(result.stdout).get("streams") or [])[0]
    except (json.JSONDecodeError, IndexError, TypeError) as exc:
        raise VisualPreflightError(f"{path.name} 冇可用 video stream 色彩 metadata") from exc
    return {
        "pix_fmt": _value(stream.get("pix_fmt")),
        "color_space": _value(stream.get("color_space")),
        "color_transfer": _value(stream.get("color_transfer")),
        "color_primaries": _value(stream.get("color_primaries")),
    }


def pixel_depth(pix_fmt: str) -> int | None:
    value = _value(pix_fmt)
    for pattern in (r"p0?(10|12|16)", r"(?:yuv|gbr|gray)[a-z]*p(9|10|12|14|16)"):
        match = re.search(pattern, value)
        if match:
            return int(match.group(1))
    if value in UNKNOWN_VALUES:
        return None
    if any(token in value for token in ("yuv420p", "yuv422p", "yuv444p", "rgb24", "bgr24")):
        return 8
    return None


def classify_source_color(metadata: dict) -> dict:
    """Classify explicit SDR, HLG HDR, PQ HDR, or an unresolved source."""
    source = {
        "pix_fmt": _value(metadata.get("pix_fmt")),
        "color_space": _value(metadata.get("color_space")),
        "color_transfer": _value(metadata.get("color_transfer")),
        "color_primaries": _value(metadata.get("color_primaries")),
    }
    transfer = source["color_transfer"]
    matrix = source["color_space"]
    primaries = source["color_primaries"]
    depth = pixel_depth(source["pix_fmt"])
    source["component_depth"] = depth

    hdr_family = None
    if transfer in HLG_TRANSFERS:
        hdr_family = "hlg"
    elif transfer in PQ_TRANSFERS:
        hdr_family = "pq"

    if hdr_family:
        mismatches = []
        if primaries != "bt2020":
            mismatches.append(f"primaries={primaries}")
        if matrix not in BT2020_MATRICES:
            mismatches.append(f"matrix={matrix}")
        if depth is not None and depth < 10:
            mismatches.append(f"pix_fmt={source['pix_fmt']}")
        if mismatches:
            source.update({
                "classification": "unknown",
                "dynamic_range": "unknown",
                "confidence": "low",
                "fatal_reason": (
                    f"{hdr_family.upper()} transfer 同其餘 metadata 對唔上："
                    + ", ".join(mismatches)
                ),
            })
            return source
        source.update({
            "classification": f"hdr_{hdr_family}",
            "dynamic_range": "hdr",
            "confidence": "high",
        })
        return source

    if transfer in SDR_TRANSFERS:
        if primaries == "bt2020" or matrix in BT2020_MATRICES:
            source.update({
                "classification": "unknown",
                "dynamic_range": "unknown",
                "confidence": "low",
                "fatal_reason": "SDR transfer 配 BT.2020 gamut，未有安全自動轉色規則",
            })
            return source
        source.update({
            "classification": "sdr",
            "dynamic_range": "sdr",
            "confidence": "high" if primaries == "bt709" or matrix == "bt709" else "medium",
        })
        return source

    high_risk = primaries == "bt2020" or matrix in BT2020_MATRICES or (
        depth is not None and depth >= 10
    )
    source.update({
        "classification": "unknown",
        "dynamic_range": "unknown",
        "confidence": "low",
    })
    if high_risk:
        source["fatal_reason"] = "BT.2020／10-bit source 缺可靠 transfer metadata，唔可以估 HLG、PQ 定 SDR"
    else:
        source["warning"] = "source 色彩 metadata 不完整；保守地唔做 tone-map，請抽 frame 人眼確認"
    return source


def _filter_stage_names(filter_chain: str) -> list[str]:
    return [
        stage.strip().split("=", 1)[0].casefold()
        for stage in str(filter_chain or "").split(",")
        if stage.strip()
    ]


def tone_map_stage_count(filter_chain: str) -> int:
    return sum(
        name in {"tonemap", "tonemap_opencl", "tonemap_vaapi", "libplacebo"}
        for name in _filter_stage_names(filter_chain)
    )


def canonical_hdr_to_sdr_filter(classification: str) -> str:
    transfer = {"hdr_hlg": "arib-std-b67", "hdr_pq": "smpte2084"}.get(classification)
    if not transfer:
        raise VisualPreflightError(f"唔支援 HDR classification：{classification}")
    return (
        "setparams=colorspace=bt2020nc:color_primaries=bt2020:"
        f"color_trc={transfer}:range=tv,"
        f"zscale=tin={transfer}:pin=bt2020:min=bt2020nc:rin=tv:t=linear:npl=100,"
        "format=gbrpf32le,"
        "zscale=p=bt709,"
        "tonemap=tonemap=hable:desat=0,"
        "zscale=t=bt709:m=bt709:r=tv,"
        "format=yuv420p"
    )


def build_source_visual_preflight(metadata: dict) -> dict:
    source_color = classify_source_color(metadata)
    if source_color.get("fatal_reason"):
        raise VisualPreflightError(source_color["fatal_reason"])
    classification = source_color["classification"]
    filter_chain = (
        canonical_hdr_to_sdr_filter(classification)
        if classification in {"hdr_hlg", "hdr_pq"}
        else ""
    )
    count = tone_map_stage_count(filter_chain)
    expected = 1 if filter_chain else 0
    if count != expected:
        raise VisualPreflightError(f"tone-map stage 數量錯：預期 {expected}，實際 {count}")
    return {
        "source_color": source_color,
        "effective_color_filter": filter_chain,
        "tone_map_applied": bool(filter_chain),
        "tone_map_stage_count": count,
        "warnings": [source_color["warning"]] if source_color.get("warning") else [],
    }
