"""FFmpeg music-video builder.

Renders a full MV from: audio + analysis (beats/sections/energy), an optional
approved character image, optional imported AI scene clips, per-project story
(palette/camera/shots), and lyrics (as ASS subtitles).

Design rules
* Filter graphs contain only constants / numbers built here. User text goes to
  files (ASS subtitles, drawtext ``textfile``); colours are validated hex.
* Sections are rendered as separate clips then concatenated, so memory stays
  bounded and long songs work on a 16 GB laptop.
* Works with no AI clip at all (motion-graphics fallback), and swaps in AI
  clips per scene when they exist.
"""
from __future__ import annotations

import datetime as dt
import json
import math
import random
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from sqlmodel import select

from ..config import settings
from ..db import session_scope
from ..models import Candidate, Character, CharacterImage, Project, RenderOutput, SceneClip
from . import audio_analysis, covers
from . import ffmpeg as ff
from .fonts import japanese_font, latin_font

SCENES = ["hook", "intro", "verse", "buildup", "drop1", "break", "final_drop", "outro"]
SECTION_TO_SCENE = {"intro": "intro", "verse": "verse", "buildup": "buildup", "drop1": "drop1", "drop2": "drop1", "drop3": "final_drop",
                    "break": "break", "final_drop": "final_drop", "outro": "outro", "full": "drop1"}

_HEX = re.compile(r"^#?[0-9A-Fa-f]{6}$")


def hexcolor(c: str, default: str = "37E5FF") -> str:
    c = (c or "").strip()
    return c.lstrip("#") if _HEX.match(c) else default


@dataclass
class RenderSpec:
    audio_path: Path
    out_path: Path
    width: int = 1080
    height: int = 1920
    fps: int = 30
    title: str = ""
    artist: str = "AERA"
    accent: str = "#37E5FF"
    accent2: str = "#8A5CFF"
    character_image: Path | None = None
    scene_clips: dict[str, Path] = field(default_factory=dict)
    lyrics_en: str = ""
    story: dict[str, Any] = field(default_factory=dict)
    analysis: dict[str, Any] | None = None
    encoder: str = "libx264"
    quality: str = "standard"
    seed: int = 1
    intro_text: str = ""
    ending_text: str = ""
    platform: str = "youtube"
    show_lyrics: bool = True
    show_waveform: bool = True
    show_spectrum: bool = True
    work_dir: Path | None = None
    encoder_fallback_reason: str = ""


# ---------------------------------------------------------------- planning
def plan_sections(analysis: dict[str, Any], total: float) -> list[dict[str, Any]]:
    secs = [dict(s) for s in analysis.get("sections", []) if s["end"] > s["start"]]
    if not secs:
        secs = [{"name": "full", "start": 0, "end": int(math.ceil(total)), "high": True}]
    # clamp to actual duration and make continuous
    out = []
    cursor = 0.0
    for s in secs:
        start = max(cursor, float(s["start"]))
        end = min(float(s["end"]), total)
        if end - start < 0.5:
            continue
        out.append({"name": s["name"], "start": start, "end": end, "high": bool(s.get("high"))})
        cursor = end
    if out and out[-1]["end"] < total:
        out[-1]["end"] = total
    if not out:
        out = [{"name": "full", "start": 0.0, "end": total, "high": True}]
    return out


def lyric_events(lyrics_en: str, sections: list[dict[str, Any]]) -> list[tuple[float, float, str]]:
    """Distribute lyric lines over sections by tag. Timing is approximate (not vocal-aligned)."""
    blocks: list[tuple[str, list[str]]] = []
    tag, lines = "verse", []
    for raw in lyrics_en.splitlines():
        raw = raw.strip()
        if not raw:
            continue
        m = re.match(r"^\[(.+?)\]$", raw)
        if m:
            if lines:
                blocks.append((tag, lines))
            tag, lines = m.group(1).lower(), []
            continue
        lines.append(raw)
    if lines:
        blocks.append((tag, lines))
    tag_to_names = {"chorus": ("drop1", "drop2", "final_drop", "drop3", "full"), "pre-chorus": ("buildup",), "bridge": ("break",),
                    "verse": ("verse", "intro"), "intro": ("intro",), "outro": ("outro",)}
    events: list[tuple[float, float, str]] = []
    used: set[int] = set()
    for tag, lns in blocks:
        names = tag_to_names.get(tag, ("verse",))
        target = next((i for i, s in enumerate(sections) if s["name"] in names and i not in used), None)
        if target is None:
            target = next((i for i, s in enumerate(sections) if i not in used), None)
        if target is None:
            break
        used.add(target)
        s = sections[target]
        span = s["end"] - s["start"]
        if span < 1 or not lns:
            continue
        per = span / len(lns)
        for i, ln in enumerate(lns):
            st = s["start"] + i * per
            events.append((st, min(st + per, s["end"]) - 0.05, ln))
    return events


def _ass_time(t: float) -> str:
    t = max(0.0, t)
    h = int(t // 3600)
    m = int((t % 3600) // 60)
    s = t % 60
    return f"{h}:{m:02d}:{s:05.2f}"


def _ass_escape(text: str) -> str:
    return re.sub(r"[{}\\]", "", text)[:120]


def write_ass(path: Path, events: list[tuple[float, float, str]], w: int, h: int, accent: str, style: str = "center pulse", platform: str = "youtube") -> Path:
    font = "DejaVu Sans"
    fp = latin_font()
    if fp:
        font = Path(fp).stem.replace("-Bold", "").replace("Bold", "")
    size = int(h * 0.036) if h > w else int(h * 0.055)
    a = hexcolor(accent)
    # ASS colours are &HBBGGRR&
    ass_accent = f"&H00{a[4:6]}{a[2:4]}{a[0:2]}&"
    align = 5 if style in ("center pulse", "kinetic zoom") else 2
    margin_v = int(h * 0.18) if platform == "tiktok" else int(h * 0.12)
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {w}
PlayResY: {h}
WrapStyle: 0

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Lyric,{font},{size},&H00FFFFFF&,{ass_accent},&H00000000&,&H80000000&,1,0,0,0,100,100,1,0,1,3,2,{align},60,60,{margin_v},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    lines = [header]
    for st, en, text in events:
        fx = ""
        if style == "center pulse":
            fx = r"{\fad(120,120)\fscx90\fscy90\t(0,200,\fscx100\fscy100)}"
        elif style == "kinetic zoom":
            fx = r"{\fad(80,80)\fscx70\fscy70\t(0,300,\fscx105\fscy105)}"
        elif style == "split glitch":
            fx = r"{\fad(40,40)\blur2\t(0,120,\blur0)}"
        else:
            fx = r"{\fad(150,150)}"
        lines.append(f"Dialogue: 0,{_ass_time(st)},{_ass_time(en)},Lyric,,0,0,0,,{fx}{_ass_escape(text)}\n")
    path.write_text("".join(lines), encoding="utf-8")
    return path


# ---------------------------------------------------------------- per-section rendering
def _beat_enable(beats: list[float], start: float, end: float, every: int, width_s: float) -> str:
    """Build an ``enable`` expression that is true for ``width_s`` after selected beats (relative to section)."""
    terms = []
    idx = 0
    for b in beats:
        if start <= b < end:
            if idx % every == 0:
                rel = b - start
                terms.append(f"between(t,{rel:.3f},{rel + width_s:.3f})")
            idx += 1
    if not terms:
        return "0"
    return "+".join(terms[:400])


def render_section(spec: RenderSpec, sec: dict[str, Any], idx: int, work: Path, beats: list[float], energy_mean: float) -> Path:
    w, h, fps = spec.width, spec.height, spec.fps
    dur = sec["end"] - sec["start"]
    frames = max(1, int(round(dur * fps)))
    rng = random.Random(spec.seed * 100 + idx)
    scene = SECTION_TO_SCENE.get(sec["name"], "verse")
    high = sec["high"]
    a1, a2 = hexcolor(spec.accent), hexcolor(spec.accent2, "8A5CFF")
    out = work / f"sec_{idx:02d}.mp4"
    inputs: list[str] = []
    graph: list[str] = []
    clip = spec.scene_clips.get(scene) or (spec.scene_clips.get("hook") if idx == 0 else None)
    speed = 1.0
    if high:
        speed = rng.choice([1.0, 1.15, 1.3])
    if clip and clip.exists():
        inputs += ["-stream_loop", "-1", "-i", str(clip)]
        # scale-to-cover + crop, speed change, subtle zoom on drops
        z = "min(zoom+0.0006,1.15)" if high else "min(zoom+0.0002,1.06)"
        graph.append(
            f"[0:v]setpts={1 / speed:.3f}*PTS,scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},fps={fps},"
            f"zoompan=z='{z}':d=1:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s={w}x{h}:fps={fps},format=yuv420p,trim=duration={dur:.3f},setpts=PTS-STARTPTS[base]"
        )
    else:
        gtype = rng.choice(["linear", "radial", "circular", "spiral"])
        gspeed = 0.03 if not high else 0.08
        inputs += ["-f", "lavfi", "-i", f"gradients=s={w}x{h}:c0=0x{a1}:c1=0x101018:c2=0x{a2}:c3=0x05050A:nb_colors=4:type={gtype}:speed={gspeed}:seed={rng.randint(1, 9999)}:duration={dur:.3f}:rate={fps}"]
        graph.append("[0:v]format=yuv420p[bg0]")
        if spec.character_image and spec.character_image.exists():
            inputs += ["-loop", "1", "-framerate", str(fps), "-t", f"{dur:.3f}", "-i", str(spec.character_image)]
            shot = spec.story.get("shot_order", ["wide", "medium", "close"])[idx % max(1, len(spec.story.get("shot_order", [1, 2, 3])))]
            zoom_max = {"wide": 1.08, "medium": 1.2, "close": 1.4, "detail": 1.6, "profile": 1.25, "full-body": 1.05}.get(shot, 1.15)
            zstep = (zoom_max - 1.0) / frames * (1.6 if high else 1.0)
            px = rng.choice(["iw/2-(iw/zoom/2)", "iw/2-(iw/zoom/2)+sin(on/60)*20", "(iw-iw/zoom)*on/{f}".format(f=frames)])
            py = rng.choice(["ih/2-(ih/zoom/2)", "ih/2-(ih/zoom/2)+cos(on/70)*15", "(ih-ih/zoom)*(1-on/{f})".format(f=frames)])
            # character layer: fit to ~85% height, Ken Burns, soft edge glow
            graph.append(
                f"[1:v]scale={w}:{int(h * 0.85)}:force_original_aspect_ratio=decrease:flags=lanczos,pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:color=black@0,format=rgba,"
                f"zoompan=z='min(zoom+{zstep:.5f},{zoom_max})':d=1:x='{px}':y='{py}':s={w}x{h}:fps={fps},format=rgba[ch]"
            )
            graph.append("[bg0][ch]overlay=0:0:format=auto[bg1]")
        else:
            graph.append("[bg0]null[bg1]")
        # particles / texture layer
        if high or energy_mean > 0.5:
            inputs += ["-f", "lavfi", "-i", f"life=s={max(16, w // 12)}x{max(16, h // 12)}:mold=10:r={fps}:ratio=0.12:death_color=0x{a2}:life_color=0x{a1}:seed={rng.randint(1, 9999)}"]
            gi = len([x for x in inputs if x == "-i"]) - 1
            graph.append(f"[{gi}:v]scale={w}:{h}:flags=neighbor,gblur=sigma={max(2, w // 200)},format=yuv420p,trim=duration={dur:.3f},setpts=PTS-STARTPTS[tex]")
            graph.append("[bg1][tex]blend=all_mode=screen:all_opacity=0.28[bg2]")
        else:
            inputs += ["-f", "lavfi", "-i", f"cellauto=s={max(16, w // 16)}x{max(16, h // 16)}:rule=110:r={fps}:seed={rng.randint(1, 9999)}"]
            gi = len([x for x in inputs if x == "-i"]) - 1
            graph.append(f"[{gi}:v]scale={w}:{h}:flags=neighbor,gblur=sigma={max(3, w // 120)},format=yuv420p,trim=duration={dur:.3f},setpts=PTS-STARTPTS[tex]")
            graph.append("[bg1][tex]blend=all_mode=screen:all_opacity=0.10[bg2]")
        graph.append("[bg2]null[base]")
    chain = "[base]"
    fx = []
    # beat flashes on downbeats during drops, softer on other high sections
    if beats:
        every = 4 if high else 8
        en = _beat_enable(beats, sec["start"], sec["end"], every, 0.07 if high else 0.05)
        if en != "0":
            fx.append(f"drawbox=x=0:y=0:w=iw:h=ih:color=white@{0.22 if high else 0.10}:t=fill:enable='{en}'")
        if high:
            en2 = _beat_enable(beats, sec["start"], sec["end"], 16, 0.12)
            if en2 != "0":
                fx.append(f"rgbashift=rh={max(2, w // 180)}:bh=-{max(2, w // 180)}:enable='{en2}'")
    if high:
        fx.append("eq=contrast=1.08:saturation=1.15")
    else:
        fx.append("eq=contrast=1.02:saturation=1.0:brightness=-0.02")
    fx.append("vignette=PI/4.5")
    fade = 0.4
    if idx == 0:
        fx.append(f"fade=t=in:st=0:d={fade}")
    fx.append(f"fade=t=out:st={max(0.0, dur - 0.25):.3f}:d=0.25")
    graph.append(chain + ",".join(fx) + f",fps={fps},format=yuv420p[vout]")
    args = inputs + ["-filter_complex", ";".join(graph), "-map", "[vout]", "-t", f"{dur:.3f}", "-an"]
    _run_with_fallback(spec, args + [*ff.encoder_args(spec.encoder, "standard"), "-r", str(fps), str(out)],
                       lambda enc: args + [*ff.encoder_args(enc, "standard"), "-r", str(fps), str(out)], timeout=3600)
    return out


def _run_with_fallback(spec: RenderSpec, args: list[str], rebuild: Callable[[str], list[str]], timeout: int) -> None:
    """Run ffmpeg; if a hardware encoder fails, retry once with libx264 and remember the choice."""
    try:
        ff.run(args, timeout=timeout)
    except ff.FFmpegError as exc:
        if spec.encoder == "libx264" or str(exc) == "cancelled":
            raise
        spec.encoder_fallback_reason = str(exc)[-300:]
        spec.encoder = "libx264"
        ff.run(rebuild("libx264"), timeout=timeout)


# ---------------------------------------------------------------- assembly
def render(spec: RenderSpec, on_progress: Callable[[int, str], None] | None = None, cancel: Callable[[], bool] | None = None) -> Path:
    info = ff.probe(spec.audio_path)
    total = info.duration
    if total <= 0:
        raise ff.FFmpegError("音源の長さを取得できません")
    analysis = spec.analysis or audio_analysis.analyze(spec.audio_path)
    sections = plan_sections(analysis, total)
    beats = analysis.get("beats", [])
    energy_mean = float(sum(analysis.get("energy", [0.5])) / max(1, len(analysis.get("energy", [1]))))
    work = spec.work_dir or (settings.tmp_dir / f"mv_{dt.datetime.now().strftime('%Y%m%d_%H%M%S_%f')}")
    work.mkdir(parents=True, exist_ok=True)
    parts: list[Path] = []
    for i, sec in enumerate(sections):
        if cancel and cancel():
            raise ff.FFmpegError("cancelled")
        if on_progress:
            on_progress(int(5 + 70 * i / max(1, len(sections))), f"セクション {i + 1}/{len(sections)} ({sec['name']}) を描画中")
        parts.append(render_section(spec, sec, i, work, beats, energy_mean))
    concat_list = work / "concat.txt"
    concat_list.write_text("".join(f"file '{p.as_posix()}'\n" for p in parts), encoding="utf-8")
    if on_progress:
        on_progress(80, "音声反応レイヤーと歌詞を合成中")
    w, h, fps = spec.width, spec.height, spec.fps
    a1 = hexcolor(spec.accent)
    inputs = ["-f", "concat", "-safe", "0", "-i", str(concat_list), "-i", str(spec.audio_path)]
    g: list[str] = ["[0:v]tpad=stop_mode=clone:stop_duration=2[vpad]"]
    cur = "[vpad]"
    if spec.show_waveform:
        wh = int(h * 0.12)
        g.append(f"[1:a]aformat=channel_layouts=mono,showwaves=s={w}x{wh}:mode=cline:rate={fps}:colors=0x{a1}D9:scale=sqrt,format=rgba[wv]")
        g.append(f"{cur}[wv]overlay=0:{h - wh - int(h * 0.02)}:format=auto:shortest=1[v1]")
        cur = "[v1]"
    if spec.show_spectrum:
        sh = int(h * 0.10)
        g.append(f"[1:a]aformat=channel_layouts=mono,showspectrum=s={w}x{sh}:mode=combined:color=intensity:scale=cbrt:slide=scroll:fps={fps},colorkey=black:0.35:0.15,format=rgba,colorchannelmixer=aa=0.5[sp]")
        g.append(f"{cur}[sp]overlay=0:{int(h * 0.02)}:format=auto:shortest=1[v2]")
        cur = "[v2]"
    # lyrics
    if spec.show_lyrics and spec.lyrics_en.strip():
        events = lyric_events(spec.lyrics_en, sections)
        if spec.title:
            events = [(max(st, 3.8), en, tx) for st, en, tx in events if en > 4.0]
        if events:
            ass = write_ass(work / "lyrics.ass", events, w, h, spec.accent, spec.story.get("lyric_style", "center pulse"), spec.platform)
            fontsdir = str(Path(latin_font()).parent) if latin_font() else None
            sub = f"subtitles='{ff.escape_filter_path(ass)}'" + (f":fontsdir='{ff.escape_filter_path(fontsdir)}'" if fontsdir else "")
            g.append(f"{cur}{sub}[v3]")
            cur = "[v3]"
    # title card + ending text (drawtext with textfile; never inline text)
    fp = latin_font()
    fpj = japanese_font()
    texts: list[tuple[str, str, float, float, str, int, str]] = []  # (textfile, fontfile, start, end, ypos, size, color)
    if spec.title:
        tf = ff.write_textfile(work, "title.txt", f"{spec.artist}\n{spec.title}"[:200])
        texts.append((str(tf), fp or "", 0.3, 3.5, "(h-text_h)/2", int(h * 0.05 if h > w else h * 0.08), "white"))
    if spec.intro_text:
        tf = ff.write_textfile(work, "intro.txt", spec.intro_text[:120])
        texts.append((str(tf), (fpj or fp) or "", 0.0, 2.2, f"h*0.28", int(h * 0.032 if h > w else h * 0.05), "white"))
    if spec.ending_text and total > 6:
        tf = ff.write_textfile(work, "ending.txt", spec.ending_text[:160])
        texts.append((str(tf), (fpj or fp) or "", max(0.0, total - 4.0), total, "h*0.62", int(h * 0.03 if h > w else h * 0.045), "white"))
    for i, (tf, fontfile, st, en, y, size, color) in enumerate(texts):
        if not fontfile:
            continue
        alpha = f"if(lt(t,{st + 0.4:.2f}),(t-{st:.2f})/0.4,if(lt(t,{en - 0.4:.2f}),1,({en:.2f}-t)/0.4))"
        g.append(
            f"{cur}drawtext=fontfile='{ff.escape_filter_path(fontfile)}':textfile='{ff.escape_filter_path(tf)}':fontsize={size}:fontcolor={color}:"
            f"borderw={max(1, size // 14)}:bordercolor=black@0.7:x=(w-text_w)/2:y={y}:line_spacing={size // 4}:enable='between(t,{st:.2f},{en:.2f})':alpha='{alpha}'[t{i}]"
        )
        cur = f"[t{i}]"
    # unified grade
    g.append(f"{cur}colorbalance=bs=0.04:bm=0.02:bh=-0.02,curves=preset=increase_contrast,format=yuv420p[vfinal]")
    base = inputs + ["-filter_complex", ";".join(g), "-map", "[vfinal]", "-map", "1:a"]
    tail = [*ff.audio_args(), "-movflags", "+faststart", "-shortest", "-r", str(fps), str(spec.out_path)]
    spec.out_path.parent.mkdir(parents=True, exist_ok=True)
    _run_with_fallback(spec, base + [*ff.encoder_args(spec.encoder, spec.quality)] + tail,
                       lambda enc: base + [*ff.encoder_args(enc, spec.quality)] + tail, timeout=7200)
    if on_progress:
        on_progress(98, "一時ファイルを削除中")
    shutil.rmtree(work, ignore_errors=True)
    return spec.out_path


# ---------------------------------------------------------------- project glue
def project_dir(project_id: int) -> Path:
    p = settings.projects_dir / str(project_id)
    p.mkdir(parents=True, exist_ok=True)
    return p


def selected_audio(project: Project, s) -> Path | None:
    if not project.selected_candidate_id:
        return None
    c = s.get(Candidate, project.selected_candidate_id)
    if not c:
        return None
    for p in (c.full_audio_path, c.audio_path):
        if p and Path(p).exists():
            return Path(p)
    return None


def load_or_analyze(project_id: int, audio: Path) -> dict[str, Any]:
    cache = project_dir(project_id) / "analysis" / (audio.stem + ".json")
    if cache.exists() and cache.stat().st_mtime >= audio.stat().st_mtime:
        try:
            return json.loads(cache.read_text(encoding="utf-8"))
        except ValueError:
            pass
    a = audio_analysis.analyze(audio, max_seconds=None)
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(a, ensure_ascii=False), encoding="utf-8")
    return a


def character_assets(s, project: Project) -> tuple[Character | None, Path | None]:
    ch = s.get(Character, project.character_id) if project.character_id else s.exec(select(Character).where(Character.is_active == True)).first()  # noqa: E712
    if not ch:
        return None, None
    img = None
    if ch.approved:
        for kind in ("transparent", "base", "front", "full_front"):
            row = s.exec(select(CharacterImage).where(CharacterImage.character_id == ch.id, CharacterImage.kind == kind)).first()
            if row and Path(row.path).exists():
                img = Path(row.path)
                break
    if img is None:
        img = covers.placeholder_character(settings.characters_dir / f"placeholder_{ch.id}.png", color=ch.theme_color, seed=ch.id or 1)
    return ch, img


def scene_clip_map(s, project_id: int) -> dict[str, Path]:
    rows = s.exec(select(SceneClip).where(SceneClip.project_id == project_id, SceneClip.source == "ai")).all()
    out: dict[str, Path] = {}
    for r in rows:
        if r.video_path and Path(r.video_path).exists():
            out[r.scene] = Path(r.video_path)
    return out


def scaled(width: int, height: int) -> tuple[int, int]:
    sc = max(0.05, min(1.0, settings.render_scale))
    w, h = int(width * sc) // 2 * 2, int(height * sc) // 2 * 2
    return max(64, w), max(64, h)


def build_spec(project_id: int, out_name: str, width: int, height: int, audio: Path | None = None, variant: dict[str, Any] | None = None,
               fps: int | None = None, quality: str = "standard") -> RenderSpec:
    variant = variant or {}
    width, height = scaled(width, height)
    fps = fps or settings.render_fps
    with session_scope() as s:
        project = s.get(Project, project_id)
        if not project:
            raise ff.FFmpegError("プロジェクトが見つかりません")
        audio = audio or selected_audio(project, s)
        if not audio:
            raise ff.FFmpegError("採用済み音源がありません（3案比較で採用するか、音源をアップロードしてください）")
        ch, img = character_assets(s, project)
        clips = scene_clip_map(s, project_id)
        story = project.story
        artist = ch.name if ch else "AERA"
        accent = story.get("accent_hex") or (ch.theme_color if ch else "#37E5FF")
        title = project.title or project.inputs.get("theme") or "Untitled"
        lyrics = project.lyrics_en
    analysis = load_or_analyze(project_id, audio)
    from .hardware import usable_video_encoder

    diag_path = settings.data_dir / "hardware_report.json"
    enc = settings.video_encoder
    if enc == "auto":
        try:
            enc = usable_video_encoder(json.loads(diag_path.read_text(encoding="utf-8"))) if diag_path.exists() else "libx264"
        except ValueError:
            enc = "libx264"
        if enc == "未確認":
            enc = "libx264"
    return RenderSpec(
        audio_path=audio, out_path=project_dir(project_id) / "output" / out_name, width=width, height=height, fps=fps,
        title=title, artist=artist, accent=accent, accent2="#8A5CFF", character_image=img, scene_clips=clips,
        lyrics_en=lyrics, story=story, analysis=analysis, encoder=enc, quality=quality, seed=project_id * 31 + 7,
        intro_text=variant.get("intro_text", ""), ending_text=variant.get("ending_text", ""), platform=variant.get("platform", "youtube"),
        show_lyrics=variant.get("show_lyrics", True),
    )


def register_output(project_id: int, name: str, path: Path, kind: str = "video", encoder: str = "") -> None:
    with session_scope() as s:
        for old in s.exec(select(RenderOutput).where(RenderOutput.project_id == project_id, RenderOutput.name == name)).all():
            s.delete(old)
        w = h = None
        dur = None
        if kind == "video" and path.exists():
            try:
                info = ff.probe(path)
                w, h, dur = info.width, info.height, info.duration
            except ff.FFmpegError:
                pass
        s.add(RenderOutput(project_id=project_id, name=name, kind=kind, path=str(path), width=w, height=h, duration_s=dur, encoder=encoder))
        s.commit()


def render_project_mv(project_id: int, job_id: int | None = None, cancel: Callable[[], bool] | None = None, fps: int | None = None) -> list[Path]:
    """Render full_mv_9x16.mp4 and full_mv_16x9.mp4."""
    from .generation import _update

    outs = []
    story_end = ""
    with session_scope() as s:
        p = s.get(Project, project_id)
        story_end = (p.story.get("ending_style", "") if p else "")
    for name, (w, h) in (("full_mv_9x16.mp4", (1080, 1920)), ("full_mv_16x9.mp4", (1920, 1080))):
        spec = build_spec(project_id, name, w, h, variant={"ending_text": f"{story_end}".strip(), "platform": "youtube"}, fps=fps)

        def prog(pct: int, msg: str, _name=name) -> None:
            if job_id:
                _update(job_id, progress=pct, note=f"{_name}: {msg}")

        out = render(spec, on_progress=prog, cancel=cancel)
        register_output(project_id, name, out, "video", spec.encoder)
        outs.append(out)
    with session_scope() as s:
        p = s.get(Project, project_id)
        if p and p.status in ("selected", "compare"):
            p.status = "mv"
            s.add(p)
            s.commit()
    return outs
