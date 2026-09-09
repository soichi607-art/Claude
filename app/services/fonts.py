"""Font discovery for FFmpeg drawtext / Pillow. Reports 未設定 when nothing is found."""
from __future__ import annotations

import platform
from pathlib import Path

from ..config import settings

_LATIN = [
    "C:/Windows/Fonts/arialbd.ttf", "C:/Windows/Fonts/arial.ttf", "C:/Windows/Fonts/segoeuib.ttf",
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf", "/System/Library/Fonts/Helvetica.ttc",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
]
_JA = [
    "C:/Windows/Fonts/meiryob.ttc", "C:/Windows/Fonts/meiryo.ttc", "C:/Windows/Fonts/YuGothB.ttc", "C:/Windows/Fonts/YuGothM.ttc",
    "C:/Windows/Fonts/msgothic.ttc",
    "/System/Library/Fonts/ヒラギノ角ゴシック W6.ttc", "/System/Library/Fonts/Hiragino Sans GB.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc", "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/opentype/ipafont-gothic/ipag.ttf", "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
    "/etc/alternatives/fonts-japanese-gothic.ttf",
]


def _first(paths: list[str]) -> str | None:
    for p in paths:
        if Path(p).exists():
            return str(Path(p))
    return None


def latin_font() -> str | None:
    if settings.font_path and Path(settings.font_path).exists():
        return settings.font_path
    return _first(_LATIN)


def japanese_font() -> str | None:
    if settings.font_path_ja and Path(settings.font_path_ja).exists():
        return settings.font_path_ja
    return _first(_JA) or latin_font_if_cjk_unknown()


def latin_font_if_cjk_unknown() -> None:
    return None


def font_report() -> dict[str, str]:
    return {
        "latin": latin_font() or "未設定",
        "japanese": japanese_font() or "未設定（日本語テロップは省略されます。SOA_FONT_PATH_JA を設定してください）",
        "platform": platform.system(),
    }
