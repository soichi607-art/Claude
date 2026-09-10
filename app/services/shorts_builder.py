"""Duration-specific re-edits: Hook 25 s, Reward 65 s, Story 90 s, and Full.

Each version is a genuine re-edit, not a tail cut:
1. an *audio edit plan* picks source segments from the analysed song
   (hook → build-up → drop → change → ending) and stitches them with
   short cross-fades (``acrossfade``);
2. the stitched audio is re-analysed and rendered by ``mv_builder`` with
   version-specific intro/ending text, lyric style and platform safe-zones.
The 25 s Hook version ends with a 2 s tail that cross-fades into the same
bars it opened with, so it loops naturally.
Monetisation is never guaranteed — the UI states that explicitly.
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import Any, Callable

from sqlmodel import select

from ..config import settings
from ..db import session_scope
from ..models import Project
from . import audio_analysis
from . import ffmpeg as ff
from . import mv_builder

VERSIONS: dict[str, dict[str, Any]] = {
    "hook25": {"total": 25, "label": "Hook版 25秒", "blocks": [("hook", 0, 2), ("build_or_drop", 2, 18), ("showcase", 18, 23), ("loop_tail", 23, 25)]},
    "reward65": {"total": 65, "label": "Reward版 65秒（TikTok 1分以上要件を考慮）", "blocks": [("hook", 0, 2), ("intro", 2, 12), ("buildup", 12, 25), ("drop", 25, 45), ("change", 45, 58), ("ending", 58, 65)]},
    "story90": {"total": 90, "label": "Story版 90秒", "blocks": [("hook", 0, 3), ("story_intro", 3, 20), ("buildup", 20, 40), ("drop", 40, 65), ("final_drop", 65, 83), ("ending", 83, 90)]},
}

OUTPUTS = [
    ("youtube_short_25s.mp4", "hook25", "youtube"),
    ("youtube_short_65s.mp4", "reward65", "youtube"),
    ("youtube_short_90s.mp4", "story90", "youtube"),
    ("tiktok_hook_25s.mp4", "hook25", "tiktok"),
    ("tiktok_reward_65s.mp4", "reward65", "tiktok"),
    ("tiktok_story_90s.mp4", "story90", "tiktok"),
]


def _span(analysis: dict[str, Any], names: tuple[str, ...], fallback: tuple[float, float]) -> tuple[float, float]:
    sp = audio_analysis.section_span(analysis, names)
    return sp if sp else fallback


def _window(start: float, end: float, length: float, total: float, prefer_start: bool = True) -> tuple[float, float]:
    """Pick ``length`` seconds inside [start,end]; extend into neighbours if too short."""
    avail = end - start
    if avail >= length:
        return (start, start + length) if prefer_start else (end - length, end)
    s = max(0.0, start - (length - avail) / 2)
    e = min(total, s + length)
    s = max(0.0, e - length)
    return s, e


def edit_plan(version: str, analysis: dict[str, Any], total: float) -> list[dict[str, Any]]:
    """Return list of {role, src_start, src_end} totalling the version length."""
    v = VERSIONS[version]
    hook_t = audio_analysis.find_best_hook(analysis, 2.0)
    intro = _span(analysis, ("intro",), (0.0, min(12.0, total)))
    build = _span(analysis, ("buildup",), (max(0.0, hook_t - 16), hook_t))
    drop = _span(analysis, ("drop1", "full"), (hook_t, min(total, hook_t + 20)))
    brk = _span(analysis, ("break", "verse"), drop)
    final = _span(analysis, ("final_drop", "drop2", "drop1"), drop)
    outro = _span(analysis, ("outro",), (max(0.0, total - 8), total))
    plan: list[dict[str, Any]] = []
    for role, a, b in v["blocks"]:
        length = b - a
        if role == "hook":
            s, e = _window(hook_t, min(total, hook_t + length), length, total)
        elif role == "build_or_drop":
            s, e = _window(build[0], drop[1], length, total, prefer_start=False)
        elif role == "showcase":
            s, e = _window(final[0], final[1], length, total)
        elif role == "loop_tail":
            s, e = _window(hook_t, min(total, hook_t + length), length, total)  # same bars as the opening → loop
        elif role in ("intro", "story_intro"):
            s, e = _window(intro[0], intro[1], length, total)
        elif role == "buildup":
            s, e = _window(build[0], build[1], length, total, prefer_start=False)
        elif role == "drop":
            s, e = _window(drop[0], drop[1], length, total)
        elif role == "change":
            s, e = _window(brk[0], brk[1], length, total)
        elif role == "final_drop":
            s, e = _window(final[0], final[1], length, total)
        else:  # ending
            s, e = _window(outro[0], outro[1], length, total, prefer_start=False)
        s = max(0.0, min(s, max(0.0, total - length)))
        e = s + length
        plan.append({"role": role, "src_start": round(s, 3), "src_end": round(min(e, total), 3)})
    return plan


def stitch_audio(src: Path, plan: list[dict[str, Any]], out: Path, xfade: float = 0.35) -> Path:
    """Concatenate plan segments with acrossfade. Uses only numeric parameters."""
    g: list[str] = []
    labels: list[str] = []
    for i, seg in enumerate(plan):
        g.append(f"[0:a]atrim=start={seg['src_start']}:end={seg['src_end']},asetpts=PTS-STARTPTS,aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=stereo[s{i}]")
        labels.append(f"[s{i}]")
    cur = labels[0]
    for i in range(1, len(labels)):
        nxt = f"[x{i}]"
        g.append(f"{cur}{labels[i]}acrossfade=d={xfade}:c1=tri:c2=tri{nxt}")
        cur = nxt
    planned = sum(s['src_end'] - s['src_start'] for s in plan)
    g.append(f"{cur}apad,atrim=0:{planned:.3f},afade=t=out:st={planned - 0.6:.2f}:d=0.6,aresample=48000[aout]")
    out.parent.mkdir(parents=True, exist_ok=True)
    ff.run(["-i", str(src), "-filter_complex", ";".join(g), "-map", "[aout]", "-c:a", "pcm_s16le", str(out)], timeout=600)
    return out


def variant_texts(version: str, platform: str, story: dict[str, Any], artist: str) -> dict[str, str]:
    concept = story.get("concept_ja", "")
    if version == "hook25":
        intro = f"{concept}" if concept else ""
        ending = "🔁 ループ再生" if platform == "tiktok" else "フル版はチャンネルで"
    elif version == "reward65":
        intro = f"{artist} — {concept}"
        ending = "フォローで続きを" if platform == "tiktok" else "チャンネル登録で続きを"
    else:
        intro = f"{concept}\n{story.get('intro_style', '')}"
        ending = f"{story.get('ending_style', '')}\n{artist}"
    return {"intro_text": intro.strip(), "ending_text": ending.strip(), "platform": platform}


def render_version(project_id: int, out_name: str, version: str, platform: str, job_id: int | None = None, cancel: Callable[[], bool] | None = None,
                   fps: int | None = None) -> Path:
    from .generation import _update

    with session_scope() as s:
        project = s.get(Project, project_id)
        if not project:
            raise ff.FFmpegError("プロジェクトが見つかりません")
        audio = mv_builder.selected_audio(project, s)
        if not audio:
            raise ff.FFmpegError("採用済み音源がありません")
        story = project.story
        ch, _ = mv_builder.character_assets(s, project)
        artist = ch.name if ch else "AERA"
    analysis = mv_builder.load_or_analyze(project_id, audio)
    total = float(analysis.get("duration") or ff.probe(audio).duration)
    plan = edit_plan(version, analysis, total)
    pdir = mv_builder.project_dir(project_id)
    edited = stitch_audio(audio, plan, pdir / "audio" / f"edit_{version}.wav")
    (pdir / "audio" / f"edit_{version}.json").write_text(json.dumps(plan, ensure_ascii=False, indent=1), encoding="utf-8")
    edit_analysis = audio_analysis.analyze(edited, max_seconds=None)
    # keep the section names meaningful for the visual planner
    edit_analysis["sections"] = _plan_to_sections(plan)
    variant = variant_texts(version, platform, story, artist)
    spec = mv_builder.build_spec(project_id, out_name, 1080, 1920, audio=edited, variant=variant, fps=fps)
    spec.analysis = edit_analysis
    spec.seed = spec.seed + {"hook25": 1, "reward65": 2, "story90": 3}[version] * 17 + (5 if platform == "tiktok" else 0)
    spec.story = dict(story, lyric_style={"hook25": "kinetic zoom", "reward65": "center pulse", "story90": "lower-third typewriter"}[version])

    def prog(pct: int, msg: str) -> None:
        if job_id:
            _update(job_id, progress=pct, note=f"{out_name}: {msg}")

    out = mv_builder.render(spec, on_progress=prog, cancel=cancel)
    mv_builder.register_output(project_id, out_name, out, "video", spec.encoder)
    return out


def _plan_to_sections(plan: list[dict[str, Any]]) -> list[dict[str, Any]]:
    role_map = {"hook": ("drop1", True), "build_or_drop": ("buildup", False), "showcase": ("final_drop", True), "loop_tail": ("drop1", True),
                "intro": ("intro", False), "story_intro": ("intro", False), "buildup": ("buildup", False), "drop": ("drop1", True),
                "change": ("break", False), "final_drop": ("final_drop", True), "ending": ("outro", False)}
    t = 0.0
    out = []
    for seg in plan:
        d = seg["src_end"] - seg["src_start"]
        name, high = role_map.get(seg["role"], ("verse", False))
        out.append({"name": name, "start": round(t, 3), "end": round(t + d, 3), "high": high})
        t += d
    return out


def render_all(project_id: int, job_id: int | None = None, cancel: Callable[[], bool] | None = None, fps: int | None = None, include_full: bool = True) -> list[Path]:
    outs = []
    for name, version, platform in OUTPUTS:
        if cancel and cancel():
            raise ff.FFmpegError("cancelled")
        outs.append(render_version(project_id, name, version, platform, job_id=job_id, cancel=cancel, fps=fps))
    if include_full:
        outs += mv_builder.render_project_mv(project_id, job_id=job_id, cancel=cancel, fps=fps)
    with session_scope() as s:
        p = s.get(Project, project_id)
        if p:
            p.status = "ready"
            p.updated_at = dt.datetime.now()
            s.add(p)
            s.commit()
    return outs
