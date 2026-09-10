"""Hardware / toolchain diagnostics.

Every value is either measured on the machine that runs this code or reported
as ``未確認`` (unconfirmed). Nothing here guesses.
"""
from __future__ import annotations

import datetime as _dt
import os
import platform
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

UNKNOWN = "未確認"
# 実動作テストの対象と採用順（Intel QSV → NVIDIA NVENC → AMD AMF → macOS VideoToolbox → Linux VAAPI）。libx264 は常に最後の保険
HW_ENCODERS: tuple[str, ...] = ("h264_qsv", "h264_nvenc", "h264_amf", "h264_videotoolbox", "h264_vaapi")


def _run(cmd: list[str], timeout: int = 20) -> tuple[int, str]:
    """Run a command with shell=False. Returns (returncode, combined output)."""
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout, shell=False,
            errors="replace",
        )
        return proc.returncode, (proc.stdout or "") + (proc.stderr or "")
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return -1, ""


def _version_of(binary: str, args: list[str] | None = None) -> str:
    path = shutil.which(binary)
    if not path:
        return "未検出"
    code, out = _run([path] + (args or ["--version"]))
    first = out.strip().splitlines()[0] if out.strip() else ""
    return first or f"検出 ({path})"


# ---------------------------------------------------------------- OS / CPU
def detect_os() -> dict[str, str]:
    return {
        "system": platform.system() or UNKNOWN,
        "release": platform.release() or UNKNOWN,
        "version": platform.version() or UNKNOWN,
        "machine": platform.machine() or UNKNOWN,
    }


def detect_cpu() -> dict[str, Any]:
    name = UNKNOWN
    if platform.system() == "Linux":
        try:
            for line in Path("/proc/cpuinfo").read_text(errors="replace").splitlines():
                if line.lower().startswith("model name"):
                    name = line.split(":", 1)[1].strip()
                    break
        except OSError:
            pass
    elif platform.system() == "Windows":
        # platform.processor() は "AMD64 Family 25 Model 117" のような型番しか返さないので、CIM から製品名を取る
        code, out = _run(["powershell", "-NoProfile", "-Command", "(Get-CimInstance Win32_Processor).Name"], timeout=40)
        first = (out.strip().splitlines() or [""])[0].strip() if code == 0 else ""
        name = first or platform.processor() or UNKNOWN
    elif platform.system() == "Darwin":
        code, out = _run(["sysctl", "-n", "machdep.cpu.brand_string"])
        name = out.strip() or UNKNOWN
    logical = os.cpu_count()
    physical = None
    try:
        import psutil  # type: ignore

        physical = psutil.cpu_count(logical=False)
    except Exception:  # pragma: no cover - psutil optional
        pass
    return {"name": name, "logical_cores": logical, "physical_cores": physical}


def detect_memory() -> dict[str, Any]:
    try:
        import psutil  # type: ignore

        vm = psutil.virtual_memory()
        return {"total_gb": round(vm.total / 1e9, 1), "available_gb": round(vm.available / 1e9, 1)}
    except Exception:
        return {"total_gb": UNKNOWN, "available_gb": UNKNOWN}


def detect_disk(path: str | os.PathLike = ".") -> dict[str, Any]:
    try:
        usage = shutil.disk_usage(path)
        return {
            "total_gb": round(usage.total / 1e9, 1),
            "free_gb": round(usage.free / 1e9, 1),
            "path": str(Path(path).resolve()),
        }
    except OSError:
        return {"total_gb": UNKNOWN, "free_gb": UNKNOWN, "path": str(path)}


# ---------------------------------------------------------------- GPU
def detect_gpu() -> dict[str, Any]:
    """Best-effort GPU listing without any vendor SDK.

    Returns names found via lspci / wmic / system_profiler, plus VRAM when a
    tool reports it. Anything not reported is ``未確認``.
    """
    result: dict[str, Any] = {"devices": [], "vram": UNKNOWN, "source": "none"}
    system = platform.system()
    if system == "Linux":
        lspci = shutil.which("lspci")
        if lspci:
            code, out = _run([lspci])
            devs = [l.strip() for l in out.splitlines() if re.search(r"VGA|3D|Display", l)]
            if devs:
                result["devices"] = devs
                result["source"] = "lspci"
        if not result["devices"]:
            dri = Path("/dev/dri")
            if dri.exists():
                result["devices"] = [f"/dev/dri: {', '.join(sorted(p.name for p in dri.iterdir()))}"]
                result["source"] = "/dev/dri"
    elif system == "Windows":
        code, out = _run([
            "powershell", "-NoProfile", "-Command",
            "Get-CimInstance Win32_VideoController | Select-Object Name,AdapterRAM | ConvertTo-Json",
        ], timeout=40)
        if code == 0 and out.strip():
            import json

            try:
                data = json.loads(out)
                if isinstance(data, dict):
                    data = [data]
                for d in data:
                    result["devices"].append(str(d.get("Name")))
                    ram = d.get("AdapterRAM")
                    if isinstance(ram, (int, float)) and ram > 0:
                        # AdapterRAM is a 32-bit field on many systems; values >4GB are unreliable.
                        result["vram"] = f"{round(ram / 1e9, 1)} GB (AdapterRAM報告値、4GB超は不正確な場合あり)"
                result["source"] = "Win32_VideoController"
            except ValueError:
                pass
    elif system == "Darwin":
        code, out = _run(["system_profiler", "SPDisplaysDataType"], timeout=40)
        for line in out.splitlines():
            if "Chipset Model" in line:
                result["devices"].append(line.split(":", 1)[1].strip())
        if result["devices"]:
            result["source"] = "system_profiler"
    # nvidia-smi if present (dedicated NVIDIA only)
    smi = shutil.which("nvidia-smi")
    if smi:
        code, out = _run([smi, "--query-gpu=name,memory.total", "--format=csv,noheader"])
        if code == 0 and out.strip():
            result["nvidia"] = out.strip()
            m = re.search(r"(\d+)\s*MiB", out)
            if m:
                result["vram"] = f"{round(int(m.group(1)) / 1024, 1)} GB (nvidia-smi)"
    if not result["devices"]:
        result["devices"] = [UNKNOWN]
    return result


def detect_intel_xpu() -> dict[str, Any]:
    """Check torch.xpu availability without importing heavy deps if torch is absent."""
    info: dict[str, Any] = {"torch_installed": False, "xpu_available": UNKNOWN, "device_name": UNKNOWN}
    try:
        import importlib

        torch = importlib.import_module("torch")
        info["torch_installed"] = True
        info["torch_version"] = getattr(torch, "__version__", UNKNOWN)
        xpu = getattr(torch, "xpu", None)
        if xpu is not None and hasattr(xpu, "is_available"):
            avail = bool(xpu.is_available())
            info["xpu_available"] = avail
            if avail:
                try:
                    props = xpu.get_device_properties(0)
                    info["device_name"] = getattr(props, "name", UNKNOWN)
                    total = getattr(props, "total_memory", None)
                    if total:
                        info["vram_gb"] = round(total / 1e9, 1)
                except Exception:
                    pass
        else:
            info["xpu_available"] = False
            info["note"] = "このtorchビルドにはxpuバックエンドがありません"
    except ModuleNotFoundError:
        info["note"] = "torch未インストール（ACE-Stepのvenv内で再診断してください）"
    except Exception as exc:  # pragma: no cover
        info["note"] = f"検査エラー: {exc.__class__.__name__}"
    return info


# ---------------------------------------------------------------- Tooling
def detect_python() -> dict[str, str]:
    return {"version": sys.version.split()[0], "executable": sys.executable}


def _find(name: str) -> str | None:
    try:
        from .ffmpeg import find_binary

        return find_binary(name)
    except Exception:  # pragma: no cover
        return shutil.which(name)


def detect_ffmpeg() -> dict[str, Any]:
    ff = _find("ffmpeg")
    fp = _find("ffprobe")

    def _ver(path: str | None) -> str:
        if not path:
            return "未検出"
        code, out = _run([path, "-version"])
        first = out.strip().splitlines()[0] if out.strip() else ""
        return (first or "検出") + f"  [{path}]"

    info: dict[str, Any] = {
        "ffmpeg": _ver(ff),
        "ffprobe": _ver(fp),
        "ffmpeg_path": ff or "",
        "ffprobe_path": fp or "",
        "encoders": {},
        "qsv": UNKNOWN,
        "hw": UNKNOWN,
    }
    if ff:
        code, out = _run([ff, "-hide_banner", "-encoders"], timeout=30)
        wanted = ["libx264", "h264_qsv", "h264_vaapi", "h264_videotoolbox", "h264_nvenc", "h264_amf", "aac", "libx265", "hevc_qsv"]
        found = {}
        for name in wanted:
            found[name] = bool(re.search(rf"^\s*[VA][\.A-Z]{{5}}\s+{re.escape(name)}\s", out, re.M))
        info["encoders"] = found
        info["qsv"] = "エンコーダー有り (h264_qsv)。実動作は要テスト" if found.get("h264_qsv") else "h264_qsv 未検出"
        hw_present = [n for n in HW_ENCODERS if found.get(n)]
        info["hw"] = ("ffmpeg に含まれる HW エンコーダー: " + ", ".join(hw_present) + "（実動作は下のテスト結果で判定）") if hw_present else "HW エンコーダーなし（libx264 のみ）"
    return info


def test_encoder(encoder: str, workdir: str | os.PathLike | None = None) -> dict[str, Any]:
    """Actually try to encode 1 second of test video with the given encoder."""
    ff = _find("ffmpeg")
    if not ff:
        return {"encoder": encoder, "ok": False, "detail": "ffmpeg未検出"}
    out_dir = Path(workdir or ".")
    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / f"_enc_test_{encoder}.mp4"
    cmd = [ff, "-y", "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i",
           "testsrc=size=320x240:rate=30:duration=1", "-c:v", encoder]
    if encoder == "h264_vaapi":
        cmd = [ff, "-y", "-hide_banner", "-loglevel", "error", "-vaapi_device", "/dev/dri/renderD128",
               "-f", "lavfi", "-i", "testsrc=size=320x240:rate=30:duration=1",
               "-vf", "format=nv12,hwupload", "-c:v", encoder]
    cmd += [str(target)]
    code, out = _run(cmd, timeout=60)
    ok = code == 0 and target.exists() and target.stat().st_size > 0
    try:
        target.unlink(missing_ok=True)
    except OSError:
        pass
    return {"encoder": encoder, "ok": ok, "detail": (out.strip()[:300] or "OK")}


def detect_acestep(acestep_dir: str | None = None, api_url: str | None = None) -> dict[str, Any]:
    """Report whether an ACE-Step 1.5 checkout / API server is reachable.

    Only checks local directory presence and the official ``GET /health`` endpoint
    (docs/en/API.md of ace-step/ACE-Step-1.5). No inference is attempted here.
    """
    info: dict[str, Any] = {"dir": acestep_dir or "未設定", "dir_exists": False, "api_url": api_url or "未設定", "api_health": UNKNOWN}
    if acestep_dir:
        p = Path(acestep_dir)
        info["dir_exists"] = (p / "acestep" / "api_server.py").exists()
        for marker in ("venv_xpu", ".venv", "venv"):
            if (p / marker).exists():
                info["venv"] = marker
    if api_url:
        try:
            import httpx  # type: ignore

            r = httpx.get(api_url.rstrip("/") + "/health", timeout=3.0)
            info["api_health"] = f"HTTP {r.status_code}"
            if r.status_code == 200:
                info["api_health_body"] = r.text[:200]
        except Exception as exc:
            info["api_health"] = f"接続不可 ({exc.__class__.__name__})"
    return info


def battery_status() -> dict[str, Any]:
    try:
        import psutil  # type: ignore

        b = psutil.sensors_battery()
        if b is None:
            return {"present": False}
        return {"present": True, "percent": b.percent, "plugged": bool(b.power_plugged)}
    except Exception:
        return {"present": UNKNOWN}


def temperature_status() -> dict[str, Any]:
    try:
        import psutil  # type: ignore

        temps = psutil.sensors_temperatures()  # type: ignore[attr-defined]
        if not temps:
            return {"available": False}
        best = None
        for _name, entries in temps.items():
            for e in entries:
                if e.current is not None:
                    best = max(best or 0, e.current)
        return {"available": best is not None, "max_c": best}
    except Exception:
        return {"available": False}


# ---------------------------------------------------------------- Report
def full_diagnostics(acestep_dir: str | None = None, api_url: str | None = None, run_encoder_tests: bool = True,
                     workdir: str | os.PathLike | None = None) -> dict[str, Any]:
    ff = detect_ffmpeg()
    enc_tests = []
    if run_encoder_tests and ff["ffmpeg"] != "未検出":
        for enc in (*HW_ENCODERS, "libx264"):
            if ff["encoders"].get(enc):
                enc_tests.append(test_encoder(enc, workdir))
    return {
        "generated_at": _dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "os": detect_os(),
        "cpu": detect_cpu(),
        "memory": detect_memory(),
        "disk": detect_disk(workdir or "."),
        "gpu": detect_gpu(),
        "intel_xpu": detect_intel_xpu(),
        "python": detect_python(),
        "node": _version_of("node"),
        "git": _version_of("git"),
        "ffmpeg": ff,
        "encoder_tests": enc_tests,
        "acestep": detect_acestep(acestep_dir, api_url),
        "battery": battery_status(),
        "temperature": temperature_status(),
    }


def usable_video_encoder(diag: dict[str, Any]) -> str:
    """Pick the encoder to use: the first HW encoder (Intel QSV → NVIDIA NVENC → AMD AMF → VideoToolbox → VAAPI) that passed the real test, then libx264."""
    ok = {t["encoder"] for t in diag.get("encoder_tests", []) if t.get("ok")}
    for enc in (*HW_ENCODERS, "libx264"):
        if enc in ok:
            return enc
    return "libx264" if diag.get("ffmpeg", {}).get("encoders", {}).get("libx264") else "未確認"


def render_markdown(diag: dict[str, Any]) -> str:
    g = diag
    xpu = g["intel_xpu"]
    ff = g["ffmpeg"]
    lines = [
        "# ハードウェア診断レポート",
        "",
        f"- 生成日時: {g['generated_at']}",
        "- 注意: このレポートは **このスクリプトを実行したマシン** の実測値です。別のPCで使う場合は `python scripts/diagnose.py` を再実行してください。",
        "",
        "## OS",
        f"- System: {g['os']['system']} {g['os']['release']}",
        f"- Version: {g['os']['version']}",
        f"- Arch: {g['os']['machine']}",
        "",
        "## CPU",
        f"- 名称: {g['cpu']['name']}",
        f"- 論理コア: {g['cpu']['logical_cores']} / 物理コア: {g['cpu']['physical_cores'] if g['cpu']['physical_cores'] is not None else UNKNOWN}",
        "",
        "## メモリ",
        f"- 合計: {g['memory']['total_gb']} GB / 利用可能: {g['memory']['available_gb']} GB",
        "",
        "## ストレージ",
        f"- パス: {g['disk']['path']}",
        f"- 合計: {g['disk']['total_gb']} GB / 空き: {g['disk']['free_gb']} GB",
        "",
        "## GPU",
        f"- 検出元: {g['gpu']['source']}",
    ]
    for d in g["gpu"]["devices"]:
        lines.append(f"- デバイス: {d}")
    lines += [f"- VRAM: {g['gpu']['vram']}"]
    if g["gpu"].get("nvidia"):
        lines.append(f"- nvidia-smi: {g['gpu']['nvidia']}")
    lines += [
        "",
        "## Intel XPU (torch.xpu)",
        f"- torch インストール: {'あり (' + str(xpu.get('torch_version')) + ')' if xpu['torch_installed'] else 'なし'}",
        f"- torch.xpu.is_available(): {xpu['xpu_available']}",
        f"- デバイス名: {xpu['device_name']}",
    ]
    if xpu.get("vram_gb"):
        lines.append(f"- XPU メモリ: {xpu['vram_gb']} GB")
    if xpu.get("note"):
        lines.append(f"- 備考: {xpu['note']}")
    lines += [
        "",
        "## ツールチェーン",
        f"- Python: {g['python']['version']} ({g['python']['executable']})",
        f"- Node.js: {g['node']}",
        f"- Git: {g['git']}",
        f"- FFmpeg: {ff['ffmpeg']}",
        f"- ffprobe: {ff['ffprobe']}",
        "",
        "## Intel Quick Sync Video",
        f"- {ff['qsv']}",
        "",
        "## ハードウェアエンコーダー（Intel QSV / NVIDIA NVENC / AMD AMF など）",
        f"- {ff.get('hw', UNKNOWN)}",
        "",
        "## 動画エンコーダー（ffmpeg -encoders）",
    ]
    for name, present in ff.get("encoders", {}).items():
        lines.append(f"- {name}: {'あり' if present else 'なし'}")
    lines += ["", "## エンコーダー実動作テスト（1秒のテスト映像を実際にエンコード）"]
    if g["encoder_tests"]:
        for t in g["encoder_tests"]:
            lines.append(f"- {t['encoder']}: {'成功' if t['ok'] else '失敗'} — {t['detail'][:160]}")
    else:
        lines.append("- 実施なし")
    lines += [
        f"- **採用エンコーダー: {usable_video_encoder(g)}**",
        "",
        "## ACE-Step 1.5",
        f"- ディレクトリ: {g['acestep']['dir']} (存在: {g['acestep']['dir_exists']})",
        f"- venv: {g['acestep'].get('venv', UNKNOWN)}",
        f"- API URL: {g['acestep']['api_url']}",
        f"- /health: {g['acestep']['api_health']}",
        "",
        "## 電源・温度",
        f"- バッテリー: {g['battery']}",
        f"- 温度センサー: {g['temperature']}",
        "",
        "## 判定",
    ]
    mem = g["memory"]["total_gb"]
    verdicts = []
    if isinstance(mem, (int, float)) and mem < 12:
        verdicts.append("- メモリ12GB未満: ACE-Step CPU実行は失敗する可能性が高い → 手動アップロード運用を推奨")
    if xpu["xpu_available"] is True:
        verdicts.append("- Intel XPU 利用可: ACE-Step を XPU で試験可能（要 10秒→30秒 実測）")
    elif xpu["torch_installed"]:
        verdicts.append("- Intel XPU 未検出: ACE-Step は CPU 実行のみ（非常に遅い、公式INSTALL.md「CPU-Only Mode」参照）")
    else:
        verdicts.append("- Intel XPU: 未確認（ACE-Step の venv で `python scripts/diagnose.py` を再実行）")
    gpu_names = " / ".join(str(d) for d in g["gpu"]["devices"] if d and d != UNKNOWN)
    if xpu["xpu_available"] is not True and gpu_names and "intel" not in gpu_names.lower():
        verdicts.append(f"- GPU は Intel 以外（{gpu_names}）: torch.xpu（Intel XPU）の対象外。ACE-Step の対応デバイスは公式に CUDA / MPS / ROCm / Intel XPU / CPU（PLAN.md、2026-09-09 確認）。このアプリ側は CPU 実行または手動アップロードで全工程を完成できる")
    verdicts.append(f"- 動画エンコード: {usable_video_encoder(g)} を使用")
    lines += verdicts or ["- 判定なし"]
    return "\n".join(lines) + "\n"
