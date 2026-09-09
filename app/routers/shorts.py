from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlmodel import select

from ..db import session_scope
from ..models import GenerationJob, Project, RenderOutput
from ..services import generation as gen
from ..services import mv_builder, shorts_builder
from ..web import csrf_protect, redirect, render

router = APIRouter(prefix="/projects/{project_id}")


@router.get("/shorts")
async def shorts_page(request: Request, project_id: int):
    with session_scope() as s:
        p = s.get(Project, project_id)
        if not p:
            raise HTTPException(404)
        audio = mv_builder.selected_audio(p, s)
        outputs = {o.name: o for o in s.exec(select(RenderOutput).where(RenderOutput.project_id == project_id)).all()}
        jobs = s.exec(select(GenerationJob).where(GenerationJob.project_id == project_id, GenerationJob.kind == "shorts", GenerationJob.status.in_(["queued", "running"]))).all()
    plans = {}
    if audio:
        analysis = mv_builder.load_or_analyze(project_id, audio)
        total = float(analysis.get("duration") or 0)
        for v in shorts_builder.VERSIONS:
            plans[v] = shorts_builder.edit_plan(v, analysis, total)
    return render(request, "shorts.html", {"project": p, "audio": audio, "outputs": outputs, "jobs": jobs, "plans": plans, "versions": shorts_builder.VERSIONS,
                                           "output_list": shorts_builder.OUTPUTS})


@router.post("/shorts/render", dependencies=[Depends(csrf_protect)])
async def render_shorts(request: Request, project_id: int):
    with session_scope() as s:
        p = s.get(Project, project_id)
        if not p or not mv_builder.selected_audio(p, s):
            return redirect(f"/projects/{project_id}/compare", "採用済み音源がありません。", "error")
    gen.enqueue("shorts", project_id, None, {"project_id": project_id}, note="25/65/90秒 ×(YouTube/TikTok) + フル版")
    return redirect("/jobs", "ショート版とフル版の一括描画をキューに入れました（PCによっては数十分かかります）。", "ok")
