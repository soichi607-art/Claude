from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, Depends, Request
from sqlmodel import select

from ..config import ROOT, settings
from ..db import session_scope
from ..models import Benchmark, Character
from ..services import generation as gen
from ..services import hardware, safety
from ..services.acestep_client import ACEStepClient
from ..services.fonts import font_report
from ..web import csrf_protect, form_of, get_setting, redirect, render, set_setting

router = APIRouter(prefix="/settings")


def _diag():
    p = settings.data_dir / "hardware_report.json"
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except ValueError:
            return None
    return None


@router.get("")
async def page(request: Request):
    ace = ACEStepClient().status()
    diag = _diag()
    with session_scope() as s:
        bench = s.exec(select(Benchmark).order_by(Benchmark.id.desc()).limit(20)).all()
        ch = s.exec(select(Character).where(Character.is_active == True)).first()  # noqa: E712
    report_md = (ROOT / "docs" / "HARDWARE_REPORT.md")
    return render(request, "settings.html", {
        "ace": ace, "diag": diag, "bench": bench, "tests": gen.tests_passed(), "safety": safety.check(), "fonts": font_report(),
        "encoder": hardware.usable_video_encoder(diag) if diag else "未診断", "settings": settings, "character": ch,
        "report_exists": report_md.exists(), "default_mode": get_setting("default_mode", "eco"), "threads": safety.cpu_threads(),
        "acestep_key_set": bool(settings.acestep_api_key),
    })


@router.post("/diagnose", dependencies=[Depends(csrf_protect)])
async def diagnose(request: Request):
    diag = hardware.full_diagnostics(settings.acestep_dir or None, settings.acestep_api_url or None, run_encoder_tests=True, workdir=settings.tmp_dir)
    (ROOT / "docs" / "HARDWARE_REPORT.md").write_text(hardware.render_markdown(diag), encoding="utf-8")
    (settings.data_dir / "hardware_report.json").write_text(json.dumps(diag, ensure_ascii=False, indent=2), encoding="utf-8")
    return redirect("/settings", "ハードウェア診断を実行し docs/HARDWARE_REPORT.md を更新しました。", "ok")


@router.post("/acestep/test", dependencies=[Depends(csrf_protect)])
async def acestep_test(request: Request):
    form = form_of(request)
    secs = 10 if form.get("secs") == "10" else 30
    if secs == 30 and not gen.tests_passed()["test10"]:
        return redirect("/settings", "先に10秒テストを成功させてください。", "error")
    ok, detail = ACEStepClient().health()
    if not ok:
        return redirect("/settings", f"ACE-Step API に接続できません（{detail}）。docs/ACESTEP_SETUP.md を参照。", "error")
    device = str(form.get("device_label", ""))[:40]
    gen.enqueue(f"acestep_test{secs}", None, None, {"duration_s": secs, "device_label": device, "seed": 42}, note=f"{secs}秒 実測テスト")
    return redirect("/jobs", f"{secs}秒テストをキューに入れました。実測時間が完了予定の算出に使われます。", "ok")


@router.post("/general", dependencies=[Depends(csrf_protect)])
async def general(request: Request):
    form = form_of(request)
    mode = str(form.get("default_mode", "eco"))
    if mode in gen.MODE_CANDIDATE_SECONDS:
        set_setting("default_mode", mode)
    return redirect("/settings", "設定を保存しました。", "ok")
