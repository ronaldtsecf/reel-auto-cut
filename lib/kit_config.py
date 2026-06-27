"""jyut-cut user config loader — 讀 config.json + profiles/brand.json（runtime 沉澱）。

Self-locating（KIT_ROOT = 呢個檔上兩層），唔 hardcode 任何絕對路徑。
gen_briefing / reel_render_final import 呢度攞 brand color + emphasis words。
冇 config.json 就用 neutral DEFAULTS（zero-config 即跑）。
"""
import json
from pathlib import Path

KIT_ROOT = Path(__file__).resolve().parent.parent

DEFAULTS = {
    "brand": {
        "accent1": "#FFFFFF",          # neutral 白（唔自動標品牌色）
        "accent2": "#FFFFFF",
        "subtitle_font": None,         # None = 各平台中文 font 自動（Mac Hiragino / Win YaHei / Linux Noto）
        "emphasis_words": [],          # 空 = 唔自動標 keyword（避免亂標）
    },
    "glossary_terms": [],              # 專名串法表（STT 聽錯時 runtime 補）
    "glossary_fixes": [],              # [["錯","啱"], ...]
    "output_dir": None,                # None = 素材包出喺 WORK
}


def _merge(base: dict, override: dict) -> None:
    for k, v in override.items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            base[k].update(v)
        else:
            base[k] = v


def load() -> dict:
    cfg = json.loads(json.dumps(DEFAULTS))   # deep copy
    # config.json（用戶設定）→ profiles/brand.json（runtime 沉澱，後者贏）
    for src in (KIT_ROOT / "config.json", KIT_ROOT / "profiles" / "brand.json"):
        if src.exists():
            try:
                _merge(cfg, json.loads(src.read_text()))
            except Exception:
                pass
    return cfg


CONFIG = load()
