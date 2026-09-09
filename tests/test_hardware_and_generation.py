from app.services import generation as gen
from app.services import hardware, safety


def test_diagnostics_report():
    d = hardware.full_diagnostics(run_encoder_tests=False)
    md = hardware.render_markdown(d)
    for key in ("## OS", "## CPU", "## メモリ", "## GPU", "## Intel XPU", "## Intel Quick Sync Video", "## ACE-Step 1.5", "## 判定"):
        assert key in md
    assert hardware.usable_video_encoder(d) in ("libx264", "未確認", "h264_qsv", "h264_vaapi", "h264_videotoolbox")
    assert hardware.usable_video_encoder({"encoder_tests": [{"encoder": "h264_qsv", "ok": True}], "ffmpeg": {"encoders": {}}}) == "h264_qsv"


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
