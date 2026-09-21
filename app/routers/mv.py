from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from starlette.datastructures import UploadFile
from fastapi.responses import FileResponse
from sqlmodel import select

from ..config import settings
from ..db import session_scope
from ..models import Character, GenerationJob, Project, RenderOutput, SceneClip
from ..security import ensure_inside, validate_upload
from ..services import generation as gen
from ..services import mv_builder, notebook, packaging, video_import
from ..web import csrf_protect, form_of, redirect, render

router = APIRouter(prefix="/projects/{project_id}")


def _project(project_id: int, s) -> Project:
    p = s.get(Project, project_id)
    if not p:
        raise HTTPException(404, "プロジェクトが見つかりません")
    return p


@router.get("/mv")
async def mv_page(request: Request, project_id: int):
    with session_scope() as s:
        p = _project(project_id, s)
        audio = mv_builder.selected_audio(p, s)
        ch, _img = mv_builder.character_assets(s, p)
        scenes = s.exec(select(SceneClip).where(SceneClip.project_id == project_id).order_by(SceneClip.order)).all()
        if not scenes and ch:
            packaging.sync_scene_rows(project_id, packaging.scene_prompts(p, ch.name, p.story))
            scenes = s.exec(select(SceneClip).where(SceneClip.project_id == project_id).order_by(SceneClip.order)).all()
        outputs = {o.name: o for o in s.exec(select(RenderOutput).where(RenderOutput.project_id == project_id)).all()}
        jobs = s.exec(select(GenerationJob).where(GenerationJob.project_id == project_id, GenerationJob.kind.in_(["mv", "shorts"]), GenerationJob.status.in_(["queued", "running"]))).all()
        story = p.story
    analysis = mv_builder.load_or_analyze(project_id, audio) if audio else None
    return render(request, "mv.html", {"project": p, "audio": audio, "character": ch, "scenes": scenes, "outputs": outputs, "jobs": jobs, "story": story,
                                       "analysis": {k: v for k, v in (analysis or {}).items() if k in ("duration", "bpm", "key", "sections")},
                                       "scene_labels": packaging.SCENE_LABELS})


@router.post("/mv/render", dependencies=[Depends(csrf_protect)])
async def render_mv(request: Request, project_id: int):
    with session_scope() as s:
        p = _project(project_id, s)
        if not mv_builder.selected_audio(p, s):
            return redirect(f"/projects/{project_id}/compare", "採用済み音源がありません。先に案を採用してください。", "error")
    gen.enqueue("mv", project_id, None, {"project_id": project_id}, note="フルMV 9:16 / 16:9")
    return redirect("/jobs", "フルMVの描画をキューに入れました。", "ok")


@router.post("/mv/import", dependencies=[Depends(csrf_protect)])
async def import_clips(request: Request, project_id: int):
    form = form_of(request)
    up = form.get("zip")
    if not isinstance(up, UploadFile):
        raise HTTPException(400, "ZIPを選択してください")
    if form.get("license_ok") != "on":
        raise HTTPException(400, "生成に使ったモデル・サービスのライセンスと商用利用条件を確認した旨のチェックが必要です")
    data = await up.read()
    name = validate_upload(up.filename or "", data[:16], len(data), "zip")
    tmp = settings.tmp_dir / f"import_{project_id}_{name}"
    tmp.write_bytes(data)
    try:
        result = video_import.import_zip(project_id, tmp)
    except (ValueError, __import__("zipfile").BadZipFile) as exc:
        raise HTTPException(400, f"取り込みに失敗: {exc}")
    finally:
        tmp.unlink(missing_ok=True)
    msg = f"取り込み {len(result['imported'])} 件"
    if result["skipped"]:
        msg += f" / スキップ {len(result['skipped'])} 件: " + "; ".join(result["skipped"][:3])
    return redirect(f"/projects/{project_id}/mv", msg, "ok" if result["imported"] else "error")


@router.post("/mv/scene/{scene}/clear", dependencies=[Depends(csrf_protect)])
async def clear_scene(request: Request, project_id: int, scene: str):
    form = form_of(request)
    if form.get("confirm") != "yes":
        raise HTTPException(400, "削除の確認が必要です")
    video_import.clear_scene(project_id, scene)
    return redirect(f"/projects/{project_id}/mv", f"{scene} のAI動画を外し、モーショングラフィックスに戻しました。", "ok")


@router.post("/mv/pack", dependencies=[Depends(csrf_protect)])
async def build_pack(request: Request, project_id: int):
    try:
        packaging.build_video_generation_pack(project_id)
    except ValueError as exc:
        return redirect(f"/projects/{project_id}/mv", str(exc), "error")
    return redirect(f"/projects/{project_id}/mv", "video_generation_pack.zip を出力しました。", "ok")


@router.get("/mv/notebook")
async def download_notebook(project_id: int):
    out = notebook.build_notebook(mv_builder.project_dir(project_id) / "output" / "soa_free_gpu_video.ipynb")
    return FileResponse(out, filename="soa_free_gpu_video.ipynb", media_type="application/x-ipynb+json")


@router.get("/files/{name}")
async def project_file(project_id: int, name: str):
    """Serve a registered output file (path-guarded)."""
    with session_scope() as s:
        row = s.exec(select(RenderOutput).where(RenderOutput.project_id == project_id, RenderOutput.name == name)).first()
    if not row:
        raise HTTPException(404)
    path = ensure_inside(settings.projects_dir / str(project_id), Path(row.path))
    if not path.exists():
        raise HTTPException(404)
    media = "video/mp4" if name.endswith(".mp4") else ("image/png" if name.endswith(".png") else ("application/zip" if name.endswith(".zip") else "text/plain; charset=utf-8"))
    return FileResponse(path, media_type=media, filename=name)


@router.get("/audio/{cand_id}")
async def candidate_audio(project_id: int, cand_id: int, full: int = 0):
    from ..models import Candidate

    with session_scope() as s:
        c = s.get(Candidate, cand_id)
    if not c or c.project_id != project_id:
        raise HTTPException(404)
    p = c.full_audio_path if (full and c.full_audio_path) else c.audio_path
    if not p:
        raise HTTPException(404)
    path = ensure_inside(settings.projects_dir / str(project_id), Path(p))
    if not path.exists():
        raise HTTPException(404)
    return FileResponse(path, media_type="audio/wav" if path.suffix == ".wav" else "audio/mpeg")
