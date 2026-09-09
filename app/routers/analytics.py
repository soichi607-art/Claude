from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlmodel import select

from ..db import session_scope
from ..models import Candidate, Metric, PostRecord, Project
from ..services.copywriter import genre_label
from ..web import csrf_protect, form_of, redirect, render

router = APIRouter()
WEEKDAYS = ["月", "火", "水", "木", "金", "土", "日"]
DURATIONS = {"25s": 25, "65s": 65, "90s": 90, "9x16": "full", "16x9": "full"}


def _dur(name: str):
    for k, v in DURATIONS.items():
        if k in name:
            return v
    return "?"


@router.get("/analytics")
async def analytics(request: Request):
    rows = []
    with session_scope() as s:
        posts = s.exec(select(PostRecord).order_by(PostRecord.id.desc())).all()
        for post in posts:
            p = s.get(Project, post.project_id)
            latest = s.exec(select(Metric).where(Metric.post_id == post.id).order_by(Metric.recorded_at.desc())).first()
            cand = s.get(Candidate, p.selected_candidate_id) if p and p.selected_candidate_id else None
            rows.append({
                "post": post, "project": p, "metric": latest, "genre": genre_label(p.inputs) if p else "?",
                "vocal": (p.inputs.get("vocal_type") if p else "?"), "duration": _dur(post.output_name),
                "weekday": WEEKDAYS[post.posted_at.weekday()] if post.posted_at else "未投稿", "hour": post.posted_at.strftime("%H:%M") if post.posted_at else "—",
                "focus": cand.focus if cand else "?",
            })
    return render(request, "analytics.html", {"rows": rows})


@router.post("/analytics/{post_id}/metric", dependencies=[Depends(csrf_protect)])
async def add_metric(request: Request, post_id: int):
    form = form_of(request)

    def num(key, cast=int):
        v = str(form.get(key, "")).strip()
        if v == "":
            return None  # 未取得
        try:
            return cast(v)
        except ValueError:
            raise HTTPException(400, f"{key} は数値で入力してください")

    with session_scope() as s:
        post = s.get(PostRecord, post_id)
        if not post:
            raise HTTPException(404)
        m = Metric(post_id=post_id, views=num("views"), avg_watch_s=num("avg_watch_s", float), completion_rate=num("completion_rate", float),
                   likes=num("likes"), comments=num("comments"), shares=num("shares"), follows_gained=num("follows_gained"), note=str(form.get("note", ""))[:300])
        posted_at = str(form.get("posted_at", "")).strip()
        if posted_at:
            try:
                post.posted_at = dt.datetime.fromisoformat(posted_at)
                post.status = "posted"
                s.add(post)
            except ValueError:
                raise HTTPException(400, "投稿日時の形式が不正です")
        s.add(m)
        s.commit()
    return redirect("/analytics", "成績を記録しました（空欄は未取得として保存）。", "ok")
