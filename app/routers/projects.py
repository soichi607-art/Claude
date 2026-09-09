from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from starlette.datastructures import UploadFile
from sqlmodel import select

from ..config import settings
from ..db import session_scope
from ..models import AuditLog, Candidate, Project, ReferenceAudio
from ..security import ensure_inside, validate_upload
from ..services import audio_analysis, copywriter, lyrics, prompt_builder
from ..services.acestep_client import ACEStepError
from ..services import generation as gen
from ..services import ffmpeg as ff
from ..web import active_character, csrf_protect, form_of, redirect, render

router = APIRouter(prefix="/projects")

INPUT_FIELDS = ["theme", "free_text", "genre_modern", "genre_2010s", "brightness", "intensity", "emotion", "festival", "futuristic", "catchiness",
                "bpm", "duration_target", "vocal_type", "vocal_pitch", "vocal_tone", "ng_words", "ref_artists", "ref_songs", "ref_urls"]
FOCUS = [("A", "catchy", "キャッチー重視"), ("B", "drop", "ドロップ重視"), ("C", "vocal", "ボーカル重視")]


def _ctx_lists():
    return {"modern": prompt_builder.MODERN_GENRES, "edm2010": prompt_builder.EDM_2010S, "focus": FOCUS}


def _form_inputs(form) -> dict:
    d = {}
    for k in INPUT_FIELDS:
        v = form.get(k, "")
        d[k] = str(v).strip()[:2000]
    for k in ("brightness", "intensity", "emotion", "festival", "futuristic", "catchiness"):
        try:
            d[k] = max(0, min(100, int(d.get(k) or 50)))
        except ValueError:
            d[k] = 50
    return d


def _load(project_id: int, s) -> Project:
    p = s.get(Project, project_id)
    if not p:
        raise HTTPException(404, "プロジェクトが見つかりません")
    return p


@router.get("/new")
async def new_form(request: Request):
    return render(request, "project_new.html", {"inputs": {"brightness": 60, "intensity": 60, "emotion": 50, "festival": 60, "futuristic": 60, "catchiness": 70,
                                                          "vocal_type": "female", "vocal_pitch": "mid", "vocal_tone": "bright", "duration_target": 150},
                                                **_ctx_lists(), "project": None})


@router.post("/new", dependencies=[Depends(csrf_protect)])
async def create(request: Request):
    form = form_of(request)
    inputs = _form_inputs(form)
    title = (form.get("title") or inputs.get("theme") or "Untitled").strip()[:120]
    ch = active_character()
    with session_scope() as s:
        p = Project(title=title, inputs_json=json.dumps(inputs, ensure_ascii=False), mode=form.get("mode", "eco"), character_id=ch.id if ch else None)
        s.add(p)
        s.commit()
        s.refresh(p)
        p.story_json = json.dumps(copywriter.build_story(inputs, p.id * 97), ensure_ascii=False)
        s.add(p)
        s.commit()
        pid = p.id
    _rebuild_candidates(pid)
    return redirect(f"/projects/{pid}", "プロジェクトを作成しました。3案のプロンプトと歌詞を生成済みです。", "ok")


@router.get("/{project_id}")
async def detail(request: Request, project_id: int):
    with session_scope() as s:
        p = _load(project_id, s)
        cands = s.exec(select(Candidate).where(Candidate.project_id == project_id).order_by(Candidate.label)).all()
        refs = s.exec(select(ReferenceAudio).where(ReferenceAudio.project_id == project_id)).all()
        audits = s.exec(select(AuditLog).where(AuditLog.project_id == project_id).order_by(AuditLog.id.desc()).limit(10)).all()
        inputs, story = p.inputs, p.story
    tests = gen.tests_passed()
    eta = {}
    for secs in (30, 60, 150):
        e, note = gen.eta_for(secs)
        eta[secs] = (round(e / 60, 1) if e else None, note)
    return render(request, "project_detail.html", {"project": p, "inputs": inputs, "story": story, "cands": cands, "refs": refs, "audits": audits,
                                                   "tests": tests, "eta": eta, "modes": gen.MODE_CANDIDATE_SECONDS, **_ctx_lists()})


@router.post("/{project_id}/inputs", dependencies=[Depends(csrf_protect)])
async def update_inputs(request: Request, project_id: int):
    form = form_of(request)
    inputs = _form_inputs(form)
    with session_scope() as s:
        p = _load(project_id, s)
        p.title = (form.get("title") or p.title).strip()[:120]
        p.inputs_json = json.dumps(inputs, ensure_ascii=False)
        p.mode = form.get("mode", p.mode)
        p.updated_at = dt.datetime.now()
        s.add(p)
        s.commit()
    _rebuild_candidates(project_id, keep_done=True)
    return redirect(f"/projects/{project_id}", "入力を保存し、未生成の案のプロンプトを更新しました。", "ok")


def _rebuild_candidates(project_id: int, keep_done: bool = False) -> None:
    with session_scope() as s:
        p = _load(project_id, s)
        inputs = p.inputs
        ref = s.exec(select(ReferenceAudio).where(ReferenceAudio.project_id == project_id, ReferenceAudio.rights_confirmed == True)).first()  # noqa: E712
        ref_analysis = ref.loads(ref.analysis_json) if ref and ref.analysis_json else None
        neutral, audit = prompt_builder.neutralize_references(inputs, ref_analysis)
        s.add(AuditLog(project_id=project_id, kind="prompt_neutralization", before=json.dumps(audit["before"], ensure_ascii=False), after=json.dumps(audit["after"], ensure_ascii=False)))
        p.neutral_prompt = neutral
        existing = {c.label: c for c in s.exec(select(Candidate).where(Candidate.project_id == project_id)).all()}
        secs = gen.MODE_CANDIDATE_SECONDS.get(p.mode, 30)
        try:
            target = int(inputs.get("duration_target") or 150)
        except ValueError:
            target = 150
        full_en, full_ja = lyrics.generate(inputs, project_id * 13, max(120, min(180, target)), "catchy")
        p.lyrics_en, p.lyrics_ja = full_en, full_ja
        for label, focus, _ in FOCUS:
            c = existing.get(label) or Candidate(project_id=project_id, label=label, focus=focus)
            if keep_done and c.status in ("done", "uploaded", "running", "queued"):
                continue
            c.prompt = prompt_builder.build_caption(inputs, focus, neutral)
            en, _ja = lyrics.generate(inputs, project_id * 13 + ord(label), secs, focus)
            c.lyrics = en
            c.seed = prompt_builder.deterministic_seed(project_id, label, inputs.get("theme", ""))
            c.bpm = prompt_builder.default_bpm(inputs)
            c.target_duration_s = secs
            hits = prompt_builder.contains_ng(c.prompt + c.lyrics, inputs.get("ng_words", ""))
            c.error = ("NGワード検出: " + ", ".join(hits)) if hits else ""
            s.add(c)
        s.add(p)
        s.commit()


@router.post("/{project_id}/reference", dependencies=[Depends(csrf_protect)])
async def upload_reference(request: Request, project_id: int):
    form = form_of(request)
    up = form.get("audio")
    if not isinstance(up, UploadFile):
        raise HTTPException(400, "音源ファイルを選択してください")
    if form.get("rights") != "on":
        raise HTTPException(400, "解析権限（自分が権利を持つ、または解析許可を得た音源）の確認が必要です")
    data = await up.read()
    name = validate_upload(up.filename or "", data[:16], len(data), "audio")
    dest_dir = settings.projects_dir / str(project_id) / "reference"
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = ensure_inside(dest_dir, dest_dir / f"{dt.datetime.now().strftime('%Y%m%d%H%M%S')}_{name}")
    dest.write_bytes(data)
    try:
        ff.probe(dest)
        analysis = audio_analysis.analyze(dest)
    except Exception as exc:  # noqa: BLE001
        dest.unlink(missing_ok=True)
        raise HTTPException(400, f"音源を解析できません: {exc.__class__.__name__}")
    with session_scope() as s:
        _load(project_id, s)
        s.add(ReferenceAudio(project_id=project_id, filename=name, path=str(dest), rights_confirmed=True,
                             analysis_json=json.dumps({k: v for k, v in analysis.items() if k not in ("beats", "energy")}, ensure_ascii=False), analyzed_at=dt.datetime.now()))
        s.commit()
    _rebuild_candidates(project_id, keep_done=True)
    return redirect(f"/projects/{project_id}", "参考音源を解析し、中立化した特徴をプロンプトへ反映しました（音源は外部送信していません）。", "ok")


@router.post("/{project_id}/reference/{ref_id}/delete", dependencies=[Depends(csrf_protect)])
async def delete_reference(request: Request, project_id: int, ref_id: int):
    form = form_of(request)
    if form.get("confirm") != "yes":
        raise HTTPException(400, "削除の確認が必要です")
    with session_scope() as s:
        r = s.get(ReferenceAudio, ref_id)
        if r and r.project_id == project_id:
            Path(r.path).unlink(missing_ok=True)
            s.delete(r)
            s.add(AuditLog(project_id=project_id, kind="delete", before=r.filename, after=""))
            s.commit()
    return redirect(f"/projects/{project_id}", "参考音源を削除しました。", "ok")


@router.post("/{project_id}/candidates/{cand_id}/edit", dependencies=[Depends(csrf_protect)])
async def edit_candidate(request: Request, project_id: int, cand_id: int):
    form = form_of(request)
    with session_scope() as s:
        c = s.get(Candidate, cand_id)
        if not c or c.project_id != project_id:
            raise HTTPException(404)
        c.prompt = str(form.get("prompt", c.prompt))[:4000]
        c.lyrics = str(form.get("lyrics", c.lyrics))[:6000]
        try:
            c.bpm = int(form.get("bpm") or c.bpm or 128)
        except ValueError:
            pass
        c.key_scale = str(form.get("key_scale", ""))[:20]
        s.add(c)
        s.commit()
    return redirect(f"/projects/{project_id}", f"案 {c.label} を更新しました。", "ok")


@router.post("/{project_id}/lyrics", dependencies=[Depends(csrf_protect)])
async def edit_lyrics(request: Request, project_id: int):
    form = form_of(request)
    with session_scope() as s:
        p = _load(project_id, s)
        p.lyrics_en = str(form.get("lyrics_en", ""))[:8000]
        p.lyrics_ja = str(form.get("lyrics_ja", ""))[:8000]
        s.add(p)
        s.commit()
    return redirect(f"/projects/{project_id}", "歌詞を保存しました。", "ok")


@router.post("/{project_id}/generate", dependencies=[Depends(csrf_protect)])
async def generate(request: Request, project_id: int):
    form = form_of(request)
    mode = form.get("mode", "eco")
    if mode not in gen.MODE_CANDIDATE_SECONDS:
        mode = "eco"
    try:
        gen.start_candidates(project_id, mode, thinking=form.get("thinking") == "on")
    except ACEStepError as exc:
        return redirect(f"/projects/{project_id}", str(exc), "error")
    return redirect("/jobs", f"{mode.capitalize()} モードで3案の生成をキューに入れました。", "ok")


@router.post("/{project_id}/candidates/{cand_id}/upload", dependencies=[Depends(csrf_protect)])
async def upload_candidate_audio(request: Request, project_id: int, cand_id: int):
    """Manual audio upload path (when ACE-Step is unavailable)."""
    form = form_of(request)
    up = form.get("audio")
    if not isinstance(up, UploadFile):
        raise HTTPException(400, "音源ファイルを選択してください")
    if form.get("original") != "on":
        raise HTTPException(400, "自作・権利確認済みの音源であることの確認が必要です")
    data = await up.read()
    name = validate_upload(up.filename or "", data[:16], len(data), "audio")
    dest_dir = settings.projects_dir / str(project_id) / "audio"
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = ensure_inside(dest_dir, dest_dir / f"upload_{cand_id}_{name}")
    dest.write_bytes(data)
    try:
        info = ff.probe(dest)
    except ff.FFmpegError:
        dest.unlink(missing_ok=True)
        raise HTTPException(400, "音声として読み込めません")
    with session_scope() as s:
        c = s.get(Candidate, cand_id)
        if not c or c.project_id != project_id:
            raise HTTPException(404)
        if info.duration >= 100:
            c.full_audio_path = str(dest)
        c.audio_path = str(dest)
        c.status = "uploaded"
        c.source = "upload"
        c.generation_seconds = None
        s.add(c)
        p = _load(project_id, s)
        if p.status in ("draft", "generating"):
            p.status = "compare"
        s.add(p)
        s.commit()
    return redirect(f"/projects/{project_id}/compare", f"案 {c.label} に音源を登録しました（{info.duration:.0f}秒）。", "ok")


@router.get("/{project_id}/compare")
async def compare(request: Request, project_id: int):
    with session_scope() as s:
        p = _load(project_id, s)
        cands = s.exec(select(Candidate).where(Candidate.project_id == project_id).order_by(Candidate.label)).all()
    e, note = gen.eta_for(150)
    return render(request, "compare.html", {"project": p, "cands": cands, "focus": FOCUS, "eta_full": (round(e / 60, 1) if e else None, note)})


@router.post("/{project_id}/select/{cand_id}", dependencies=[Depends(csrf_protect)])
async def select_candidate(request: Request, project_id: int, cand_id: int):
    form = form_of(request)
    with session_scope() as s:
        p = _load(project_id, s)
        cands = s.exec(select(Candidate).where(Candidate.project_id == project_id)).all()
        target = None
        for c in cands:
            c.is_selected = c.id == cand_id
            if c.is_selected:
                target = c
            s.add(c)
        if not target or not (target.audio_path and Path(target.audio_path).exists()):
            raise HTTPException(400, "音源のある案のみ採用できます")
        p.selected_candidate_id = cand_id
        p.status = "selected"
        s.add(p)
        s.add(AuditLog(project_id=project_id, kind="approval", before="", after=f"candidate {target.label} selected"))
        s.commit()
        label = target.label
        has_full = bool(target.full_audio_path and Path(target.full_audio_path).exists())
    if form.get("make_full") == "on" and not has_full:
        try:
            secs = int(form.get("full_seconds") or gen.FULL_SECONDS_DEFAULT)
            secs = max(120, min(180, secs))
            gen.start_full(project_id, cand_id, secs)
            return redirect("/jobs", f"案 {label} を採用し、{secs}秒のフル生成をキューに入れました。", "ok")
        except ACEStepError as exc:
            return redirect(f"/projects/{project_id}/compare", f"採用しましたがフル生成を開始できません: {exc}", "error")
    return redirect(f"/projects/{project_id}/mv", f"案 {label} を採用しました。", "ok")


@router.post("/{project_id}/delete", dependencies=[Depends(csrf_protect)])
async def delete_project(request: Request, project_id: int):
    form = form_of(request)
    if form.get("confirm") != "yes":
        raise HTTPException(400, "削除の確認が必要です")
    import shutil

    with session_scope() as s:
        p = _load(project_id, s)
        title = p.title
        s.delete(p)
        for c in s.exec(select(Candidate).where(Candidate.project_id == project_id)).all():
            s.delete(c)
        s.add(AuditLog(project_id=None, kind="delete", before=f"project {project_id} {title}", after=""))
        s.commit()
    shutil.rmtree(settings.projects_dir / str(project_id), ignore_errors=True)
    return redirect("/", f"プロジェクト「{title}」を削除しました。", "ok")
