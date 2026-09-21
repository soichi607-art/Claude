from pathlib import Path

from app.services import audio_analysis, ffmpeg as ff, mv_builder, shorts_builder, covers


def test_analysis_finds_bpm_and_sections(test_audio: Path):
    a = audio_analysis.analyze(test_audio)
    assert 120 <= a["bpm"] <= 136 or 60 <= a["bpm"] <= 68  # librosa may halve
    assert a["duration"] == 20.0
    assert len(a["beats"]) > 20
    assert len(a["energy"]) == 20
    names = [s["name"] for s in a["sections"]]
    assert any(s["high"] for s in a["sections"]) and "intro" in names
    hook = audio_analysis.find_best_hook(a)
    assert 0 <= hook < 20


def test_edit_plans_have_correct_totals(test_audio_40: Path):
    a = audio_analysis.analyze(test_audio_40)
    for v, meta in shorts_builder.VERSIONS.items():
        plan = shorts_builder.edit_plan(v, a, 40.0)
        total = sum(p["src_end"] - p["src_start"] for p in plan)
        assert abs(total - meta["total"]) < 0.01, (v, total)
        assert all(0 <= p["src_start"] < p["src_end"] <= 40.0 for p in plan)
    hook = shorts_builder.edit_plan("hook25", a, 40.0)
    assert hook[0]["src_start"] == hook[-1]["src_start"]  # loop tail == opening bars


def test_stitch_audio_duration(test_audio_40: Path, tmp_path: Path):
    a = audio_analysis.analyze(test_audio_40)
    plan = shorts_builder.edit_plan("hook25", a, 40.0)
    out = shorts_builder.stitch_audio(test_audio_40, plan, tmp_path / "e.wav")
    assert abs(ff.probe(out).duration - 25.0) < 0.1


def test_render_mv_small(test_audio: Path, tmp_path: Path):
    ph = covers.placeholder_character(tmp_path / "ph.png", 256, 256)
    spec = mv_builder.RenderSpec(audio_path=test_audio, out_path=tmp_path / "mv.mp4", width=144, height=256, fps=10, title="T", artist="AERA",
                                 character_image=ph, lyrics_en="[verse]\nLine one\nLine two\n[chorus]\nHook line\n", story={"lyric_style": "kinetic zoom"},
                                 analysis=audio_analysis.analyze(test_audio), intro_text="導入", ending_text="結末", work_dir=tmp_path / "w")
    out = mv_builder.render(spec)
    info = ff.probe(out)
    assert info.has_video and info.has_audio and info.width == 144 and info.height == 256
    assert abs(info.duration - 20.0) < 0.5
    assert not (tmp_path / "w").exists()  # temp cleaned


def test_lyric_events_and_ass(tmp_path: Path):
    sections = [{"name": "intro", "start": 0, "end": 5, "high": False}, {"name": "drop1", "start": 5, "end": 15, "high": True}]
    ev = mv_builder.lyric_events("[verse]\nA\nB\n[chorus]\nC {bad}\n", sections)
    assert len(ev) == 3 and ev[2][0] == 5.0
    p = mv_builder.write_ass(tmp_path / "l.ass", ev, 1080, 1920, "#37E5FF")
    text = p.read_text(encoding="utf-8")
    assert "Dialogue:" in text and "{bad}" not in text and "&H00FFE537&" in text


def test_hexcolor_validation():
    assert mv_builder.hexcolor("#ff00aa") == "ff00aa"
    assert mv_builder.hexcolor("red; rm -rf /") == "37E5FF"


def test_covers(tmp_path: Path):
    res = covers.make_all_covers(tmp_path, "Title", "AERA", "#37E5FF", None, 1, "サブ")
    assert all(p.exists() for p in res.values())


def test_encoder_fallback_to_libx264(test_audio: Path, tmp_path: Path):
    """A hardware encoder that fails on this machine must not break the render."""
    spec = mv_builder.RenderSpec(audio_path=test_audio, out_path=tmp_path / "fb.mp4", width=144, height=256, fps=10, title="",
                                 lyrics_en="", analysis=audio_analysis.analyze(test_audio), encoder="h264_qsv", show_spectrum=False,
                                 work_dir=tmp_path / "w")
    out = mv_builder.render(spec)
    assert out.exists() and ff.probe(out).has_video
    # either QSV really worked (real Intel GPU) or we fell back — both are valid, but the choice must be recorded
    assert spec.encoder in ("h264_qsv", "libx264")
    if spec.encoder == "libx264":
        assert spec.encoder_fallback_reason
