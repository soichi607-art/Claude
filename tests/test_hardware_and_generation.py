from app.services import generation as gen
from app.services import hardware, safety


def test_diagnostics_report():
    d = hardware.full_diagnostics(run_encoder_tests=False)
    md = hardware.render_markdown(d)
    for key in ("## OS", "## CPU", "## メモリ", "## GPU", "## Intel XPU", "## Intel Quick Sync Video", "## ACE-Step 1.5", "## 判定"):
        assert key in md
    assert hardware.usable_video_encoder(d) in ("libx264", "未確認", *hardware.HW_ENCODERS)
    assert hardware.usable_video_encoder({"encoder_tests": [{"encoder": "h264_qsv", "ok": True}], "ffmpeg": {"encoders": {}}}) == "h264_qsv"
    assert "## ハードウェアエンコーダー" in md


def test_hw_encoder_priority_and_args():
    """AMD (h264_amf) / NVIDIA (h264_nvenc) are real candidates; the priority is fixed and libx264 is the last resort."""
    from app.services import ffmpeg as ff

    assert hardware.HW_ENCODERS == ff.HW_ENCODER_PRIORITY == ("h264_qsv", "h264_nvenc", "h264_amf", "h264_videotoolbox", "h264_vaapi")
    only_amf = [{"encoder": "h264_amf", "ok": True}, {"encoder": "libx264", "ok": True}, {"encoder": "h264_qsv", "ok": False}]
    assert hardware.usable_video_encoder({"encoder_tests": only_amf, "ffmpeg": {"encoders": {"libx264": True}}}) == "h264_amf"
    assert ff.pick_encoder(only_amf) == "h264_amf"
    assert ff.pick_encoder([{"encoder": "h264_nvenc", "ok": True}, {"encoder": "h264_amf", "ok": True}]) == "h264_nvenc"
    assert ff.pick_encoder([]) == "libx264"
    for enc in (*hardware.HW_ENCODERS, "libx264"):
        args = ff.encoder_args(enc)
        assert args[:2] == ["-c:v", enc]
    assert ff.encoder_args("unknown_encoder")[1] == "libx264"


def test_safety_check_runs():
    rep = safety.check()
    assert isinstance(rep.ok, bool)


def _cleanup_benchmarks():
    from sqlmodel import select

    from app.db import session_scope
    from app.models import Benchmark

    with session_scope() as s:
        for b in s.exec(select(Benchmark)).all():
            s.delete(b)
        s.commit()


def test_eta_and_queue(client, csrf):
    from sqlmodel import select

    from app.db import session_scope
    from app.models import Candidate, GenerationJob, Project

    _cleanup_benchmarks()
    eta, note = gen.eta_for(30)
    assert eta is None and "未計測" in note
    try:
        gen.record_benchmark("acestep_10s", 10, 50, True, "cpu")
        gen.record_benchmark("acestep_30s", 30, 120, True, "cpu")
        eta, note = gen.eta_for(150)
        assert eta is not None and 600 <= eta <= 760 and "実測" in note
        assert gen.tests_passed() == {"test10": True, "test30": True}
        r = client.post("/projects/new", data={"csrf_token": csrf, "title": "Queue Test", "theme": "Queue", "vocal_type": "male", "mode": "eco"}, follow_redirects=False)
        pid = int(r.headers["location"].rsplit("/", 1)[1])
        jobs = gen.start_candidates(pid, "eco")
        assert len(jobs) == 3
        jobs = gen.start_candidates(pid, "overnight")
        assert len(jobs) == 1  # chained
        with session_scope() as s:
            job = s.get(GenerationJob, jobs[0])
            params = job.loads(job.params_json)
        assert len(params["chain"]) == 2 and params["duration_s"] == 150
        gen.worker.cancel(jobs[0])
        with session_scope() as s:
            assert s.get(GenerationJob, jobs[0]).status == "cancelled"
            for j in s.exec(select(GenerationJob).where(GenerationJob.project_id == pid)).all():
                s.delete(j)
            for c in s.exec(select(Candidate).where(Candidate.project_id == pid)).all():
                s.delete(c)
            s.delete(s.get(Project, pid))
            s.commit()
    finally:
        _cleanup_benchmarks()
    assert gen.tests_passed() == {"test10": False, "test30": False}


def test_dotenv_inline_comments_are_not_values(tmp_path):
    """`.env.example` is copied to `.env` by the start scripts; its trailing comments must not leak into values."""
    import os

    from app.config import _load_dotenv, parse_env_value

    assert parse_env_value("127.0.0.1          # LAN公開は 0.0.0.0") == "127.0.0.1"
    assert parse_env_value("                # 例 C:/ACE-Step-1.5") == ""
    assert parse_env_value("auto      # auto | h264_qsv") == "auto"
    assert parse_env_value('"quoted # not a comment"') == "quoted # not a comment"
    assert parse_env_value("'single'") == "single"
    assert parse_env_value("plain#hash") == "plain#hash"  # no whitespace before # → part of the value
    assert parse_env_value("") == ""
    env = tmp_path / ".env"
    env.write_text("# header\nSOA_TEST_ENV_A=127.0.0.1   # comment\nSOA_TEST_ENV_B=            # 空\nexport SOA_TEST_ENV_C=\"x y\"\n", encoding="utf-8")
    for k in ("SOA_TEST_ENV_A", "SOA_TEST_ENV_B", "SOA_TEST_ENV_C"):
        os.environ.pop(k, None)
    try:
        _load_dotenv(env)
        assert os.environ["SOA_TEST_ENV_A"] == "127.0.0.1"
        assert os.environ["SOA_TEST_ENV_B"] == ""
        assert os.environ["SOA_TEST_ENV_C"] == "x y"
    finally:
        for k in ("SOA_TEST_ENV_A", "SOA_TEST_ENV_B", "SOA_TEST_ENV_C"):
            os.environ.pop(k, None)
