from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlmodel import select

from ..db import session_scope
from ..models import Benchmark, GenerationJob, Project
from ..services import generation as gen
from ..services import safety
from ..web import csrf_protect, redirect, render

router = APIRouter()
KIND_JA = {"acestep_test10": "ACE-Step 10秒テスト", "acestep_test30": "ACE-Step 30秒テスト", "candidate": "楽曲案の生成", "full": "採用案のフル生成",
           "mv": "フルMV描画", "shorts": "ショート/フル版の一括描画"}
STATUS_JA = {"queued": "待機中", "running": "実行中", "done": "完了", "failed": "失敗", "cancelled": "キャンセル", "paused": "一時停止"}


def _jobs_ctx():
    with session_scope() as s:
        jobs = s.exec(select(GenerationJob).order_by(GenerationJob.id.desc()).limit(40)).all()
        titles = {p.id: p.title for p in s.exec(select(Project)).all()}
        bench = s.exec(select(Benchmark).order_by(Benchmark.id.desc()).limit(10)).all()
    return {"jobs": jobs, "titles": titles, "bench": bench, "kind_ja": KIND_JA, "status_ja": STATUS_JA, "paused": gen.worker.paused.is_set(),
            "safety": safety.check(), "current": gen.worker.current_job_id}


@router.get("/jobs")
async def jobs(request: Request):
    return render(request, "jobs.html", _jobs_ctx())


@router.get("/jobs/partial")
async def jobs_partial(request: Request):
    return render(request, "_jobs_partial.html", _jobs_ctx())


@router.post("/jobs/{job_id}/cancel", dependencies=[Depends(csrf_protect)])
async def cancel(request: Request, job_id: int):
    gen.worker.cancel(job_id)
    return redirect("/jobs", "キャンセルを要求しました。", "ok")


@router.post("/jobs/pause", dependencies=[Depends(csrf_protect)])
async def pause(request: Request):
    gen.worker.pause()
    return redirect("/jobs", "キューを一時停止しました（実行中のジョブは完了まで続きます）。", "ok")


@router.post("/jobs/resume", dependencies=[Depends(csrf_protect)])
async def resume(request: Request):
    gen.worker.resume()
    return redirect("/jobs", "キューを再開しました。", "ok")


@router.post("/jobs/{job_id}/retry", dependencies=[Depends(csrf_protect)])
async def retry(request: Request, job_id: int):
    with session_scope() as s:
        job = s.get(GenerationJob, job_id)
        if job and job.status in ("failed", "cancelled"):
            params = job.loads(job.params_json)
            params.pop("not_before", None)
            gen.enqueue(job.kind, job.project_id, job.candidate_id, params, note="再実行")
    return redirect("/jobs", "再実行をキューに入れました。", "ok")
