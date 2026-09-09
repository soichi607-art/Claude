from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, Depends, HTTPException, Request
from starlette.datastructures import UploadFile
from fastapi.responses import FileResponse
from sqlmodel import select

from ..config import settings
from ..db import session_scope
from ..models import AuditLog, Character, CharacterImage
from ..security import ensure_inside, validate_upload
from ..web import csrf_protect, form_of, redirect, render

router = APIRouter(prefix="/characters")
IMAGE_KINDS = [("base", "基準画像（正面・確定用）"), ("front", "正面"), ("profile_left", "横顔（左）"), ("profile_right", "横顔（右）"), ("three_quarter", "斜め"),
               ("full_front", "全身（前）"), ("full_back", "全身（背面）"), ("expressions", "表情シート"), ("transparent", "透過PNG")]


@router.get("")
async def index(request: Request):
    with session_scope() as s:
        chars = s.exec(select(Character).order_by(Character.id)).all()
        images = {c.id: s.exec(select(CharacterImage).where(CharacterImage.character_id == c.id)).all() for c in chars}
    return render(request, "characters.html", {"chars": chars, "images": images, "kinds": IMAGE_KINDS})


@router.post("/{char_id}/update", dependencies=[Depends(csrf_protect)])
async def update(request: Request, char_id: int):
    form = form_of(request)
    with session_scope() as s:
        c = s.get(Character, char_id)
        if not c:
            raise HTTPException(404)
        c.name = str(form.get("name") or c.name).strip()[:40]
        c.profile = str(form.get("profile", c.profile))[:2000]
        c.theme_color = str(form.get("theme_color", c.theme_color))[:9]
        c.prompt = str(form.get("prompt", c.prompt))[:4000]
        c.negative_prompt = str(form.get("negative_prompt", c.negative_prompt))[:4000]
        c.sheet_prompt = str(form.get("sheet_prompt", c.sheet_prompt))[:4000]
        try:
            c.seed = int(form.get("seed")) if form.get("seed") else c.seed
        except ValueError:
            pass
        if c.approved and form.get("keep_approval") != "on":
            c.approved = False  # any identity change requires re-approval
        s.add(c)
        s.commit()
    return redirect("/characters", "キャラクター設定を保存しました。", "ok")


@router.post("/{char_id}/image", dependencies=[Depends(csrf_protect)])
async def upload_image(request: Request, char_id: int):
    form = form_of(request)
    kind = str(form.get("kind", "base"))
    if kind not in dict(IMAGE_KINDS):
        raise HTTPException(400, "種別が不正です")
    up = form.get("image")
    if not isinstance(up, UploadFile):
        raise HTTPException(400, "画像を選択してください")
    if form.get("original") != "on":
        raise HTTPException(400, "実在人物に似ていない完全オリジナル画像であることの確認が必要です")
    data = await up.read()
    name = validate_upload(up.filename or "", data[:16], len(data), "image")
    if kind == "transparent" and not name.lower().endswith(".png"):
        raise HTTPException(400, "透過PNGは .png のみ")
    from PIL import Image
    import io

    try:
        with Image.open(io.BytesIO(data)) as im:
            im.verify()
    except Exception:
        raise HTTPException(400, "画像として読み込めません")
    dest_dir = settings.characters_dir / str(char_id)
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = ensure_inside(dest_dir, dest_dir / f"{kind}_{dt.datetime.now().strftime('%Y%m%d%H%M%S')}_{name}")
    dest.write_bytes(data)
    with session_scope() as s:
        c = s.get(Character, char_id)
        if not c:
            raise HTTPException(404)
        for old in s.exec(select(CharacterImage).where(CharacterImage.character_id == char_id, CharacterImage.kind == kind)).all():
            s.delete(old)
        s.add(CharacterImage(character_id=char_id, kind=kind, path=str(dest), note=str(form.get("note", ""))[:200]))
        if kind == "base":
            c.approved = False
            s.add(c)
        s.commit()
    return redirect("/characters", f"{dict(IMAGE_KINDS)[kind]} を登録しました。", "ok")


@router.post("/{char_id}/approve", dependencies=[Depends(csrf_protect)])
async def approve(request: Request, char_id: int):
    form = form_of(request)
    who = str(form.get("approver", "")).strip()[:60]
    if form.get("confirm") != "on" or not who:
        raise HTTPException(400, "代表者名の入力と確認チェックが必要です")
    with session_scope() as s:
        c = s.get(Character, char_id)
        if not c:
            raise HTTPException(404)
        base = s.exec(select(CharacterImage).where(CharacterImage.character_id == char_id, CharacterImage.kind == "base")).first()
        if not base:
            raise HTTPException(400, "基準画像が未登録です")
        c.approved = True
        c.approved_at = dt.datetime.now()
        c.approved_by = who
        s.add(c)
        s.add(AuditLog(kind="approval", before="", after=f"character {c.name} base image approved by {who}", actor=who))
        s.commit()
    return redirect("/characters", "代表者が基準画像を確定しました。AI動画生成パックの出力が可能になります。", "ok")


@router.post("/{char_id}/unapprove", dependencies=[Depends(csrf_protect)])
async def unapprove(request: Request, char_id: int):
    with session_scope() as s:
        c = s.get(Character, char_id)
        if c:
            c.approved = False
            s.add(c)
            s.commit()
    return redirect("/characters", "承認を取り消しました。", "ok")


@router.get("/{char_id}/image/{kind}")
async def image(char_id: int, kind: str):
    with session_scope() as s:
        row = s.exec(select(CharacterImage).where(CharacterImage.character_id == char_id, CharacterImage.kind == kind)).first()
    if not row:
        raise HTTPException(404)
    path = ensure_inside(settings.characters_dir, __import__("pathlib").Path(row.path))
    return FileResponse(path)
