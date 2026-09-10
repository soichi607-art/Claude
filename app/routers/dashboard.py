from __future__ import annotations

from fastapi import APIRouter, Request
from sqlmodel import select

import shutil

from ..config import settings
from ..db import session_scope
from ..models import Candidate, Character, GenerationJob, Project, RenderOutput
from ..services.acestep_client import ACEStepClient
from ..services.generation import tests_passed
from ..web import render

router = APIRouter()

STATUS_JA = {"draft": "下書き", "generating": "生成中", "compare": "3案比較", "selected": "採用済み", "mv": "MV作成済み", "ready": "投稿準備完了", "posted": "投稿済み"}


@router.get("/")
async def dashboard(request: Request):
    with session_scope() as s:
        projects = s.exec(select(Project).order_by(Project.updated_at.desc()).limit(20)).all()
        jobs = s.exec(select(GenerationJob).where(GenerationJob.status.in_(["queued", "running"])).order_by(GenerationJob.id)).all()
        recent_fail = s.exec(select(GenerationJob).where(GenerationJob.status == "failed").order_by(GenerationJob.id.desc()).limit(3)).all()
        counts = {}
        for p in projects:
            counts[p.id] = {
                "cands": len(s.exec(select(Candidate).where(Candidate.project_id == p.id, Candidate.status.in_(["done", "uploaded"]))).all()),
                "outputs": len(s.exec(select(RenderOutput).where(RenderOutput.project_id == p.id, RenderOutput.kind == "video")).all()),
            }
        ch = s.exec(select(Character).where(Character.is_active == True)).first()  # noqa: E712
        any_audio = bool(s.exec(select(Candidate).where(Candidate.status.in_(["done", "uploaded"]))).first())
        any_selected = bool(s.exec(select(Project).where(Project.selected_candidate_id.is_not(None))).first())
        any_video = bool(s.exec(select(RenderOutput).where(RenderOutput.kind == "video")).first())
    ace = ACEStepClient().health()
    tests = tests_passed()
    from ..services.ffmpeg import available as ffmpeg_available

    ffmpeg_ok = ffmpeg_available()
    diag_done = (settings.data_dir / "hardware_report.json").exists()
    checklist = [
        {"label": "FFmpeg / ffprobe が使える", "ok": ffmpeg_ok, "href": "/help", "hint": "無いと動画が作れません（ガイド参照）"},
        {"label": "ハードウェア診断を実行した", "ok": diag_done, "href": "/settings", "hint": "設定 → 診断を実行"},
        {"label": "ACE-Step API に接続（任意）", "ok": ace[0], "href": "/settings", "hint": "未接続でも手動アップロードで進めます"},
        {"label": "10秒・30秒テストに成功（ACE-Step 利用時）", "ok": tests["test10"] and tests["test30"], "href": "/settings", "hint": "成功すると3案生成が有効化"},
        {"label": "プロジェクトを作成した", "ok": bool(projects), "href": "/projects/new", "hint": "＋新規"},
        {"label": "音源のある案がある", "ok": any_audio, "href": (f"/projects/{projects[0].id}" if projects else "/projects/new"), "hint": "生成または手動アップロード"},
        {"label": "1案を採用した", "ok": any_selected, "href": (f"/projects/{projects[0].id}/compare" if projects else "/projects/new"), "hint": "3案比較"},
        {"label": "動画を出力した", "ok": any_video, "href": (f"/projects/{projects[0].id}/shorts" if projects else "/projects/new"), "hint": "ショート編集 → 一括描画"},
        {"label": "代表者がキャラクター基準画像を確定（AI動画を使う場合）", "ok": bool(ch and ch.approved), "href": "/characters", "hint": "AERA 画面"},
    ]
    next_step = next((c for c in checklist if not c["ok"]), None)
    return render(request, "dashboard.html", {"projects": projects, "jobs": jobs, "recent_fail": recent_fail, "counts": counts, "status_ja": STATUS_JA,
                                              "ace_ok": ace[0], "ace_detail": ace[1], "tests": tests, "checklist": checklist, "next_step": next_step})
