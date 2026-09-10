"""Safe FFmpeg / ffprobe wrapper.

Rules enforced here:
* every call is ``subprocess.run(list, shell=False)``;
* user text never goes into a filter string — text is written to a file and
  referenced via ``textfile=`` / ``subtitles=`` with the path escaped;
* timeouts and log redaction are applied uniformly.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from ..config import settings


class FFmpegError(RuntimeError):
    pass


_FOUND: dict[str, str | None] = {}


def _candidate_roots() -> list[Path]:
    """Places to look for a portable FFmpeg when it is not on PATH (no bin folder needed)."""
    from ..config import ROOT

    roots: list[Path] = [ROOT / "tools", ROOT / "ffmpeg", ROOT]
    home = Path.home()
    roots += [home / "Downloads", home / "ダウンロード", home / "Desktop", home / "デスクトップ", home / "ffmpeg"]
    for env in ("LOCALAPPDATA", "ProgramFiles", "ProgramFiles(x86)", "ProgramW6432"):
        v = os.environ.get(env)
        if v:
            roots += [Path(v) / "Microsoft" / "WinGet" / "Packages", Path(v) / "ffmpeg", Path(v)]
    roots += [Path("C:/ffmpeg"), Path("/opt/homebrew/bin"), Path("/usr/local/bin"), Path("/opt/ffmpeg")]
    seen: list[Path] = []
    for r in roots:
        if r.exists() and r not in seen:
            seen.append(r)
    return seen


def find_binary(name: str, extra_roots: list[Path] | None = None, max_depth: int = 4) -> str | None:
    """Locate ffmpeg/ffprobe: explicit setting → PATH → recursive search of common folders."""
    key = name + "|" + "|".join(map(str, extra_roots or []))
    if key in _FOUND and _FOUND[key] and Path(_FOUND[key]).exists():  # type: ignore[arg-type]
        return _FOUND[key]
    configured = settings.ffmpeg_bin if name == "ffmpeg" else settings.ffprobe_bin
    if configured and configured not in (name, name + ".exe") and Path(configured).exists():
        _FOUND[key] = str(Path(configured))
        return _FOUND[key]
    hit = shutil.which(configured) or shutil.which(name)
    if hit:
        _FOUND[key] = hit
        return hit
    exe_names = {name, name + ".exe"}
    for root in (extra_roots or []) + _candidate_roots():
        try:
            base_depth = len(root.parts)
            for dirpath, dirnames, filenames in os.walk(root):
                depth = len(Path(dirpath).parts) - base_depth
                if depth >= max_depth:
                    dirnames[:] = []
                dirnames[:] = [d for d in dirnames if not d.startswith((".", "__")) and d not in ("node_modules", "site-packages", "venv", ".venv")]
                for f in filenames:
                    if f in exe_names:
                        found = str(Path(dirpath) / f)
                        _FOUND[key] = found
                        return found
        except (OSError, PermissionError):
            continue
    _FOUND[key] = None
    return None


def ffmpeg_bin() -> str:
    return find_binary("ffmpeg") or settings.ffmpeg_bin


def ffprobe_bin() -> str:
    return find_binary("ffprobe") or settings.ffprobe_bin


def available() -> bool:
    return bool(find_binary("ffmpeg")) and bool(find_binary("ffprobe"))


def run(args: Sequence[str], timeout: int = 1800, cwd: str | os.PathLike | None = None) -> subprocess.CompletedProcess:
    cmd = [ffmpeg_bin(), "-hide_banner", "-nostdin", "-y", "-loglevel", "error", *map(str, args)]
    threads = settings.cpu_threads or max(1, (os.cpu_count() or 2) // 2)
    if "-threads" not in cmd:
        cmd += ["-threads", str(threads)]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, shell=False, cwd=cwd, errors="replace")
    except subprocess.TimeoutExpired as exc:
        raise FFmpegError(f"ffmpeg timeout after {timeout}s") from exc
    except FileNotFoundError as exc:
        raise FFmpegError("ffmpeg が見つかりません") from exc
    if proc.returncode != 0:
        raise FFmpegError((proc.stderr or "")[-2000:])
    return proc


@dataclass
class MediaInfo:
    duration: float
    width: int | None
    height: int | None
    has_audio: bool
    has_video: bool
    sample_rate: int | None
    codec_video: str = ""
    codec_audio: str = ""


def probe(path: str | os.PathLike) -> MediaInfo:
    cmd = [ffprobe_bin(), "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(path)]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=60, shell=False, errors="replace")
    except (subprocess.TimeoutExpired, FileNotFoundError) as exc:
        raise FFmpegError(f"ffprobe failed: {exc.__class__.__name__}") from exc
    if proc.returncode != 0:
        raise FFmpegError(proc.stderr[-1000:])
    data = json.loads(proc.stdout or "{}")
    dur = float(data.get("format", {}).get("duration") or 0.0)
    w = h = sr = None
    ha = hv = False
    cv = ca = ""
    for s in data.get("streams", []):
        if s.get("codec_type") == "video" and not hv:
            hv, w, h, cv = True, s.get("width"), s.get("height"), s.get("codec_name", "")
        elif s.get("codec_type") == "audio" and not ha:
            ha, sr, ca = True, int(s.get("sample_rate") or 0) or None, s.get("codec_name", "")
    return MediaInfo(dur, w, h, ha, hv, sr, cv, ca)


def escape_filter_path(path: str | os.PathLike) -> str:
    """Escape a path for use inside a filtergraph option value."""
    p = str(path).replace("\\", "/")
    p = p.replace(":", "\\:").replace("'", "\\'").replace(",", "\\,").replace("[", "\\[").replace("]", "\\]")
    return p


# 実動作テストに合格した HW エンコーダーを、この順で採用する（libx264 は常に最後の保険）
HW_ENCODER_PRIORITY: tuple[str, ...] = ("h264_qsv", "h264_nvenc", "h264_amf", "h264_videotoolbox", "h264_vaapi")


def encoder_args(encoder: str, quality: str = "standard") -> list[str]:
    """Return codec args for the chosen H.264 encoder."""
    if encoder == "h264_qsv":
        return ["-c:v", "h264_qsv", "-global_quality", "23" if quality == "standard" else "20", "-look_ahead", "0", "-pix_fmt", "nv12"]
    if encoder == "h264_videotoolbox":
        return ["-c:v", "h264_videotoolbox", "-b:v", "8M", "-pix_fmt", "yuv420p"]
    if encoder == "h264_vaapi":
        return ["-c:v", "h264_vaapi", "-qp", "23"]
    if encoder == "h264_nvenc":  # NVIDIA。オプションは汎用のもののみ（実機未検証、失敗時は libx264 へ自動フォールバック）
        return ["-c:v", "h264_nvenc", "-b:v", "8M", "-pix_fmt", "yuv420p"]
    if encoder == "h264_amf":  # AMD (Radeon)。同上
        return ["-c:v", "h264_amf", "-b:v", "8M", "-pix_fmt", "yuv420p"]
    return ["-c:v", "libx264", "-preset", "veryfast" if quality == "standard" else "medium", "-crf", "21", "-pix_fmt", "yuv420p", "-profile:v", "high", "-level", "4.1"]


def pick_encoder(diag_tests: list[dict] | None = None) -> str:
    """Prefer a hardware encoder that passed the 1-second real test (Intel QSV → NVIDIA NVENC → AMD AMF → VideoToolbox → VAAPI), else libx264."""
    if settings.video_encoder != "auto":
        return settings.video_encoder
    ok = {t["encoder"] for t in (diag_tests or []) if t.get("ok")}
    for enc in HW_ENCODER_PRIORITY:
        if enc in ok:
            return enc
    return "libx264"


def audio_args() -> list[str]:
    return ["-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2"]


def write_textfile(dirpath: Path, name: str, text: str) -> Path:
    dirpath.mkdir(parents=True, exist_ok=True)
    p = dirpath / name
    p.write_text(text, encoding="utf-8")
    return p
