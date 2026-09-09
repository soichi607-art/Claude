from __future__ import annotations

from fastapi import APIRouter, Request
from sqlmodel import select

from ..db import session_scope
from ..models import Candidate, GenerationJob, Project, RenderOutput
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
                "cands": len(s.exec(select(Candidate).where(Candidate.project_id == p.id, Candidate.status == "done")).all()),
                "outputs": len(s.exec(select(RenderOutput).where(RenderOutput.project_id == p.id, RenderOutput.kind == "video")).all()),
            }
    ace = ACEStepClient().health()
    return render(request, "dashboard.html", {"projects": projects, "jobs": jobs, "recent_fail": recent_fail, "counts": counts, "status_ja": STATUS_JA,
                                              "ace_ok": ace[0], "ace_detail": ace[1], "tests": tests_passed()})
