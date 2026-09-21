"""Import a ZIP of AI-generated scene clips and map them to scenes (validated)."""
from __future__ import annotations

import re
import shutil
import zipfile
from pathlib import Path

from sqlmodel import select

from ..db import session_scope
from ..models import SceneClip
from . import ffmpeg as ff
from . import mv_builder

_ALLOWED = {".mp4", ".mov", ".webm", ".mkv"}
_SCENE_RE = re.compile(r"(hook|intro|verse|buildup|build[-_ ]?up|drop[-_ ]?1|drop1|break|final[-_ ]?drop|outro)", re.I)
MAX_MEMBER_BYTES = 500 * 1024 * 1024
MAX_MEMBERS = 40


def _scene_of(name: str) -> str | None:
    m = _SCENE_RE.search(Path(name).stem)
    if not m:
        return None
    key = m.group(1).lower().replace("-", "").replace("_", "").replace(" ", "")
    return {"buildup": "buildup", "drop1": "drop1", "finaldrop": "final_drop"}.get(key, key)


def import_zip(project_id: int, zip_path: Path) -> dict[str, list[str]]:
    dest = mv_builder.project_dir(project_id) / "ai_clips"
    dest.mkdir(parents=True, exist_ok=True)
    imported: list[str] = []
    skipped: list[str] = []
    with zipfile.ZipFile(zip_path) as z:
        members = [m for m in z.infolist() if not m.is_dir()]
        if len(members) > MAX_MEMBERS:
            raise ValueError(f"ZIP内のファイル数が多すぎます（上限 {MAX_MEMBERS}）")
        for m in members:
            name = Path(m.filename).name
            ext = Path(name).suffix.lower()
            if ext not in _ALLOWED:
                skipped.append(f"{name}: 拡張子非対応")
                continue
            if m.file_size > MAX_MEMBER_BYTES:
                skipped.append(f"{name}: サイズ超過")
                continue
            if ".." in m.filename or m.filename.startswith(("/", "\\")):
                skipped.append(f"{name}: 不正なパス")
                continue
            scene = _scene_of(name)
            if not scene or scene not in mv_builder.SCENES:
                skipped.append(f"{name}: シーン名が判別できません（hook/intro/verse/buildup/drop1/break/final_drop/outro を含めてください）")
                continue
            target = dest / f"{scene}{ext}"
            with z.open(m) as src, open(target, "wb") as dst:
                shutil.copyfileobj(src, dst, length=1024 * 1024)
            try:
                info = ff.probe(target)
                if not info.has_video or info.duration <= 0:
                    raise ff.FFmpegError("no video stream")
            except ff.FFmpegError:
                target.unlink(missing_ok=True)
                skipped.append(f"{name}: 動画として読み込めません")
                continue
            with session_scope() as s:
                row = s.exec(select(SceneClip).where(SceneClip.project_id == project_id, SceneClip.scene == scene)).first() or SceneClip(project_id=project_id, scene=scene)
                row.source = "ai"
                row.video_path = str(target)
                row.duration_s = info.duration
                s.add(row)
                s.commit()
            imported.append(f"{scene} ← {name} ({info.duration:.1f}s, {info.width}x{info.height})")
    return {"imported": imported, "skipped": skipped}


def clear_scene(project_id: int, scene: str) -> None:
    with session_scope() as s:
        row = s.exec(select(SceneClip).where(SceneClip.project_id == project_id, SceneClip.scene == scene)).first()
        if row:
            if row.video_path:
                Path(row.video_path).unlink(missing_ok=True)
            row.source = "motion"
            row.video_path = ""
            row.duration_s = None
            s.add(row)
            s.commit()
