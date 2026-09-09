from __future__ import annotations

import datetime as dt
import json

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlmodel import select

from ..db import session_scope
from ..models import AuditLog, Character, PostRecord, Project, RenderOutput
from ..services import copywriter, packaging
from ..web import csrf_protect, form_of, redirect, render

router = APIRouter(prefix="/projects/{project_id}")
PLATFORM_OUTPUTS = {"youtube": ["youtube_short_25s.mp4", "youtube_short_65s.mp4", "youtube_short_90s.mp4", "full_mv_9x16.mp4", "full_mv_16x9.mp4"],
                    "tiktok": ["tiktok_hook_25s.mp4", "tiktok_reward_65s.mp4", "tiktok_story_90s.mp4", "full_mv_9x16.mp4"]}


@router.get("/publish")
async def publish_page(request: Request, project_id: int):
    with session_scope() as s:
        p = s.get(Project, project_id)
        if not p:
            raise HTTPException(404)
        outputs = {o.name: o for o in s.exec(select(RenderOutput).where(RenderOutput.project_id == project_id)).all()}
        posts = s.exec(select(PostRecord).where(PostRecord.project_id == project_id).order_by(PostRecord.id.desc())).all()
        ch = s.get(Character, p.character_id) if p.character_id else None
        artist = ch.name if ch else "AERA"
        copy = copywriter.build_copy(p.title or p.inputs.get("theme", ""), p.inputs, artist, (p.id or 1) * 131, p.story)
    videos = [n for n in packaging.expected_outputs() if n.endswith(".mp4") and n in outputs]
    missing = [n for n in packaging.expected_outputs() if n not in outputs]
    return render(request, "publish.html", {"project": p, "outputs": outputs, "posts": posts, "copy": copy, "videos": videos, "missing": missing,
                                            "platform_outputs": PLATFORM_OUTPUTS, "checklist": copywriter.disclosure_checklist().splitlines()[1:]})


@router.post("/publish/package", dependencies=[Depends(csrf_protect)])
async def make_package(request: Request, project_id: int):
    packaging.build_post_package(project_id)
    return redirect(f"/projects/{project_id}/publish", "投稿パッケージ（テキスト・カバー・ZIP）を出力しました。", "ok")


@router.post("/publish/post", dependencies=[Depends(csrf_protect)])
async def create_post(request: Request, project_id: int):
    form = form_of(request)
    platform = str(form.get("platform", "youtube"))
    output_name = str(form.get("output_name", ""))
    if platform not in PLATFORM_OUTPUTS or output_name not in PLATFORM_OUTPUTS[platform]:
        raise HTTPException(400, "プラットフォームまたは動画の指定が不正です")
    checks = {k: form.get(k) == "on" for k in ("chk_ai", "chk_commercial", "chk_no_imitation", "chk_no_refnames", "chk_ng", "chk_no_logo", "chk_no_guarantee", "chk_rep")}
    if not all(checks.values()):
        raise HTTPException(400, "公開前チェックをすべて確認してください")
    with session_scope() as s:
        if not s.get(Project, project_id):
            raise HTTPException(404)
        post = PostRecord(project_id=project_id, platform=platform, output_name=output_name, title=str(form.get("title", ""))[:100],
                          caption=str(form.get("caption", ""))[:5000], hashtags=str(form.get("hashtags", ""))[:500], ai_disclosure=checks["chk_ai"],
                          commercial_disclosure=checks["chk_commercial"], precheck_json=json.dumps(checks), approved_by_rep=checks["chk_rep"], status="ready")
        s.add(post)
        s.commit()
        s.refresh(post)
        s.add(AuditLog(project_id=project_id, kind="share", before="", after=f"post {post.id} ready {platform} {output_name}"))
        s.commit()
        pid = post.id
    return redirect(f"/projects/{project_id}/share/{pid}", "投稿準備が完了しました。iPhoneの共有シートへ渡します。", "ok")


@router.get("/share/{post_id}")
async def share_page(request: Request, project_id: int, post_id: int):
    with session_scope() as s:
        post = s.get(PostRecord, post_id)
        p = s.get(Project, project_id)
        if not post or not p or post.project_id != project_id:
            raise HTTPException(404)
        out = s.exec(select(RenderOutput).where(RenderOutput.project_id == project_id, RenderOutput.name == post.output_name)).first()
    return render(request, "share.html", {"project": p, "post": post, "output": out})


@router.post("/share/{post_id}/mark", dependencies=[Depends(csrf_protect)])
async def mark(request: Request, project_id: int, post_id: int):
    form = form_of(request)
    status = str(form.get("status", "shared"))
    if status not in ("shared", "posted", "draft"):
        raise HTTPException(400)
    with session_scope() as s:
        post = s.get(PostRecord, post_id)
        if not post or post.project_id != project_id:
            raise HTTPException(404)
        post.status = status
        post.url = str(form.get("url", ""))[:500]
        if status == "posted":
            post.posted_at = dt.datetime.now()
            p = s.get(Project, project_id)
            if p:
                p.status = "posted"
                s.add(p)
        s.add(post)
        s.commit()
    return redirect("/analytics" if status == "posted" else f"/projects/{project_id}/share/{post_id}", "記録しました。", "ok")
