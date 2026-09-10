"""PC protection checks used before / during generation and rendering."""
from __future__ import annotations

import os
import shutil
from dataclasses import dataclass, field

from ..config import settings


@dataclass
class SafetyReport:
    ok: bool
    reasons: list[str] = field(default_factory=list)
    free_mem_gb: float | None = None
    free_disk_gb: float | None = None
    on_battery: bool | None = None
    temp_c: float | None = None


def check(path: str | os.PathLike | None = None) -> SafetyReport:
    rep = SafetyReport(ok=True)
    try:
        import psutil

        vm = psutil.virtual_memory()
        rep.free_mem_gb = round(vm.available / 1e9, 2)
        if rep.free_mem_gb < settings.min_free_mem_gb:
            rep.ok = False
            rep.reasons.append(f"空きメモリ不足 ({rep.free_mem_gb} GB < {settings.min_free_mem_gb} GB)")
        try:
            b = psutil.sensors_battery()
            if b is not None:
                rep.on_battery = not b.power_plugged
                if settings.stop_on_battery and rep.on_battery:
                    rep.ok = False
                    rep.reasons.append("バッテリー駆動中（AC接続で再開）")
        except Exception:
            rep.on_battery = None
        try:
            temps = psutil.sensors_temperatures()  # type: ignore[attr-defined]
            mx = None
            for entries in (temps or {}).values():
                for e in entries:
                    if e.current is not None:
                        mx = max(mx or 0, e.current)
            rep.temp_c = mx
            if mx is not None and mx > settings.max_temp_c:
                rep.ok = False
                rep.reasons.append(f"温度が高すぎます ({mx:.0f}°C > {settings.max_temp_c:.0f}°C)")
        except Exception:
            rep.temp_c = None
    except ImportError:
        rep.reasons.append("psutil 未導入のためメモリ/電源/温度は未確認")
    try:
        du = shutil.disk_usage(path or settings.data_dir)
        rep.free_disk_gb = round(du.free / 1e9, 2)
        if rep.free_disk_gb < settings.min_free_disk_gb:
            rep.ok = False
            rep.reasons.append(f"空き容量不足 ({rep.free_disk_gb} GB < {settings.min_free_disk_gb} GB)")
    except OSError:
        rep.reasons.append("空き容量を取得できません")
    return rep


def cpu_threads() -> int:
    return settings.cpu_threads or max(1, (os.cpu_count() or 2) // 2)
