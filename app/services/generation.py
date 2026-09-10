"""Single-worker generation queue with PC protection, cancel/pause and measured ETA.

* One job runs at a time (thread).  * Every job re-checks safety before start.
* ETA is shown only from measured Benchmarks (never guessed).
* Modes: eco (30s x3 → adopt 1 → full), standard (60s x3 → full), overnight (full x3 sequential with rest).
"""
from __future__ import annotations

import datetime as dt
import json
import shutil
import threading
import time
from pathlib import Path
from typing import Any, Optional

from sqlmodel import select

from ..config import settings
from ..db import session_scope
from ..models import Benchmark, Candidate, GenerationJob, Project
from . import safety
from .acestep_client import ACEStepClient, ACEStepError

MODE_CANDIDATE_SECONDS = {"eco": 30, "standard": 60, "overnight": 150}
FULL_SECONDS_DEFAULT = 150  # 2.5 min; user may set 120-180


class Worker:
    def __init__(self) -> None:
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._cancel_ids: set[int] = set()
        self.paused = threading.Event()
        self.current_job_id: Optional[int] = None
        self.lock = threading.Lock()

    # ------------------------------------------------------------ control
    def start(self) -> None:
        if settings.testing:
            return
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="soa-worker", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def cancel(self, job_id: int) -> None:
        with self.lock:
            self._cancel_ids.add(job_id)
        with session_scope() as s:
            job = s.get(GenerationJob, job_id)
            if job and job.status == "queued":
                job.status = "cancelled"
                job.finished_at = dt.datetime.now()
                s.add(job)
                s.commit()

    def is_cancelled(self, job_id: int) -> bool:
        with self.lock:
            return job_id in self._cancel_ids or self._stop.is_set()

    def pause(self) -> None:
        self.paused.set()

    def resume(self) -> None:
        self.paused.clear()

    # ------------------------------------------------------------ loop
    def _loop(self) -> None:
        while not self._stop.is_set():
            if self.paused.is_set():
                time.sleep(2)
                continue
            job_id = self._next_job()
            if job_id is None:
                time.sleep(2)
                continue
            self.current_job_id = job_id
            try:
                run_job(job_id, self)
            except Exception as exc:  # pragma: no cover - defensive
                _fail(job_id, f"{exc.__class__.__name__}: {exc}")
            finally:
                self.current_job_id = None
                with self.lock:
                    self._cancel_ids.discard(job_id)

    def _next_job(self) -> Optional[int]:
        with session_scope() as s:
            job = s.exec(select(GenerationJob).where(GenerationJob.status == "queued").order_by(GenerationJob.id)).first()
            if not job:
                return None
            params = json.loads(job.params_json or "{}")
            not_before = params.get("not_before")
            if not_before and dt.datetime.fromisoformat(not_before) > dt.datetime.now():
                return None
            return job.id


worker = Worker()


# ---------------------------------------------------------------- helpers
def _fail(job_id: int, error: str) -> None:
    with session_scope() as s:
        job = s.get(GenerationJob, job_id)
        if job:
            job.status = "failed"
            job.error = error[:2000]
            job.finished_at = dt.datetime.now()
            if job.started_at:
                job.elapsed_s = (job.finished_at - job.started_at).total_seconds()
            s.add(job)
            if job.candidate_id:
                c = s.get(Candidate, job.candidate_id)
                if c:
                    c.status = "failed"
                    c.error = error[:500]
                    s.add(c)
            s.commit()


def _update(job_id: int, **fields: Any) -> None:
    with session_scope() as s:
        job = s.get(GenerationJob, job_id)
        if job:
            for k, v in fields.items():
                setattr(job, k, v)
            s.add(job)
            s.commit()


def measured_rate(kind_prefix: str = "acestep") -> tuple[float | None, int]:
    """Seconds of wall-clock per second of audio, from successful benchmarks. (None, 0) if none."""
    with session_scope() as s:
        rows = s.exec(select(Benchmark).where(Benchmark.success == True, Benchmark.kind.startswith(kind_prefix))).all()  # noqa: E712
    rates = [b.elapsed_s / b.duration_s for b in rows if b.elapsed_s and b.duration_s]
    if not rates:
        return None, 0
    rates.sort()
    return rates[len(rates) // 2], len(rates)


def eta_for(duration_s: float) -> tuple[float | None, str]:
    rate, n = measured_rate()
    if rate is None:
        return None, "未計測（10秒テストを先に実行してください）"
    return duration_s * rate, f"実測 {n} 件の中央値から算出"


def record_benchmark(kind: str, duration_s: float, elapsed_s: float, success: bool, device: str = "", note: str = "") -> None:
    with session_scope() as s:
        s.add(Benchmark(kind=kind, duration_s=duration_s, elapsed_s=elapsed_s, success=success, device=device, note=note[:500]))
        s.commit()


def tests_passed() -> dict[str, bool]:
    with session_scope() as s:
        rows = s.exec(select(Benchmark).where(Benchmark.success == True)).all()  # noqa: E712
    kinds = {b.kind for b in rows}
    return {"test10": "acestep_10s" in kinds, "test30": "acestep_30s" in kinds}


def enqueue(kind: str, project_id: int | None = None, candidate_id: int | None = None, params: dict[str, Any] | None = None, note: str = "") -> int:
    with session_scope() as s:
        job = GenerationJob(kind=kind, project_id=project_id, candidate_id=candidate_id, params_json=json.dumps(params or {}, ensure_ascii=False), note=note)
        s.add(job)
        s.commit()
        s.refresh(job)
        if candidate_id:
            c = s.get(Candidate, candidate_id)
            if c:
                c.status = "queued"
                s.add(c)
                s.commit()
        return int(job.id)


# ---------------------------------------------------------------- job runner
def run_job(job_id: int, w: Worker) -> None:
    with session_scope() as s:
        job = s.get(GenerationJob, job_id)
        if not job or job.status != "queued":
            return
        params = json.loads(job.params_json or "{}")
        kind = job.kind
        job.status = "running"
        job.started_at = dt.datetime.now()
        s.add(job)
        s.commit()
    rep = safety.check()
    if not rep.ok:
        _fail(job_id, "安全停止: " + "; ".join(rep.reasons))
        return
    try:
        if kind in ("acestep_test10", "acestep_test30", "candidate", "full"):
            _run_acestep(job_id, kind, params, w)
        elif kind == "mv":
            from . import mv_builder

            mv_builder.render_project_mv(int(params["project_id"]), job_id=job_id, cancel=lambda: w.is_cancelled(job_id))
            _finish(job_id)
        elif kind == "shorts":
            from . import shorts_builder

            shorts_builder.render_all(int(params["project_id"]), job_id=job_id, cancel=lambda: w.is_cancelled(job_id))
            _finish(job_id)
        else:
            _fail(job_id, f"未知のジョブ種別: {kind}")
    except ACEStepError as exc:
        if str(exc) == "cancelled":
            _update(job_id, status="cancelled", finished_at=dt.datetime.now())
            if params.get("candidate_id"):
                with session_scope() as s:
                    c = s.get(Candidate, int(params["candidate_id"]))
                    if c:
                        c.status = "cancelled"
                        s.add(c)
                        s.commit()
        else:
            _fail(job_id, str(exc))
    except Exception as exc:
        _fail(job_id, f"{exc.__class__.__name__}: {exc}")
    finally:
        _cleanup_tmp()


def _finish(job_id: int, note: str = "") -> None:
    with session_scope() as s:
        job = s.get(GenerationJob, job_id)
        if job:
            job.status = "done"
            job.finished_at = dt.datetime.now()
            job.progress = 100
            if job.started_at:
                job.elapsed_s = (job.finished_at - job.started_at).total_seconds()
            if note:
                job.note = note
            s.add(job)
            s.commit()


def _cleanup_tmp() -> None:
    tmp = settings.tmp_dir
    try:
        for p in tmp.glob("*"):
            if p.is_file() and time.time() - p.stat().st_mtime > 3600:
                p.unlink(missing_ok=True)
            elif p.is_dir() and time.time() - p.stat().st_mtime > 3600:
                shutil.rmtree(p, ignore_errors=True)
    except OSError:
        pass


def _run_acestep(job_id: int, kind: str, params: dict[str, Any], w: Worker) -> None:
    client = ACEStepClient()
    ok, detail = client.health()
    if not ok:
        raise ACEStepError(f"ACE-Step API サーバーに接続できません ({detail})。docs/ACESTEP_SETUP.md を参照して起動してください。")
    duration = float(params.get("duration_s") or (10 if kind == "acestep_test10" else 30))
    eta, eta_note = eta_for(duration)
    _update(job_id, eta_s=eta, note=eta_note)
    dest_dir = settings.projects_dir / str(params.get("project_id") or "_tests") / "audio"
    dest_dir.mkdir(parents=True, exist_ok=True)
    stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    dest = dest_dir / f"{kind}_{params.get('label', '')}{stamp}.wav"
    t0 = time.monotonic()
    task_id = client.release_task(
        prompt=params.get("prompt") or "upbeat electronic dance music, english female vocal, catchy hook",
        lyrics=params.get("lyrics") or "[chorus]\nWe are the light tonight\n",
        duration_s=duration,
        bpm=params.get("bpm"),
        key_scale=params.get("key_scale", ""),
        seed=params.get("seed"),
        inference_steps=int(params.get("inference_steps", 8)),
        audio_format="wav",
        thinking=bool(params.get("thinking", False)),
        model=params.get("model"),
    )
    if params.get("candidate_id"):
        with session_scope() as s:
            c = s.get(Candidate, int(params["candidate_id"]))
            if c:
                c.acestep_task_id = task_id
                c.status = "running"
                s.add(c)
                s.commit()

    def on_tick(elapsed: float) -> None:
        prog = int(min(95, elapsed / eta * 100)) if eta else 0
        _update(job_id, progress=prog, elapsed_s=elapsed)

    result = client.wait_for(task_id, dest, should_cancel=lambda: w.is_cancelled(job_id), on_tick=on_tick)
    elapsed = time.monotonic() - t0
    device = params.get("device_label", "")
    bench_kind = {"acestep_test10": "acestep_10s", "acestep_test30": "acestep_30s"}.get(kind, "acestep_full" if kind == "full" else "acestep_candidate")
    record_benchmark(bench_kind, duration, elapsed, True, device=device, note=f"task {task_id}")
    seed_value = str(result.get("seed_value", ""))
    metas = result.get("metas") or {}
    if params.get("candidate_id"):
        with session_scope() as s:
            c = s.get(Candidate, int(params["candidate_id"]))
            if c:
                if kind == "full":
                    c.full_audio_path = str(dest)
                else:
                    c.audio_path = str(dest)
                c.status = "done"
                c.generation_seconds = elapsed
                c.source = "acestep"
                try:
                    c.seed = int(seed_value.split(",")[0]) if seed_value else c.seed
                except ValueError:
                    pass
                if metas.get("bpm"):
                    try:
                        c.bpm = int(metas["bpm"])
                    except (TypeError, ValueError):
                        pass
                c.key_scale = str(metas.get("keyscale") or c.key_scale)
                s.add(c)
                p = s.get(Project, c.project_id)
                if p and p.status in ("draft", "generating"):
                    p.status = "compare"
                    s.add(p)
                s.commit()
    _finish(job_id, note=f"実測 {elapsed:.1f} 秒で {duration:.0f} 秒生成（{elapsed / duration:.2f} 倍速）")
    _schedule_followups(params, kind)


def _schedule_followups(params: dict[str, Any], kind: str) -> None:
    """Overnight mode: chain next candidate with a rest period."""
    chain = params.get("chain") or []
    if not chain:
        return
    nxt = chain[0]
    rest = int(settings.rest_between_candidates_s)
    nxt = dict(nxt)
    nxt["not_before"] = (dt.datetime.now() + dt.timedelta(seconds=rest)).isoformat()
    nxt["chain"] = chain[1:]
    enqueue(nxt.pop("kind", "candidate"), project_id=nxt.get("project_id"), candidate_id=nxt.get("candidate_id"), params=nxt, note=f"{rest}秒休止後に開始")


# ---------------------------------------------------------------- project-level orchestration
def start_candidates(project_id: int, mode: str, thinking: bool = False) -> list[int]:
    """Queue A/B/C for the project according to mode. Returns job ids."""
    passed = tests_passed()
    if not (passed["test10"] and passed["test30"]):
        raise ACEStepError("10秒テストと30秒テストの両方が成功するまで、3案生成は有効化されません（設定画面で実行）。")
    secs = MODE_CANDIDATE_SECONDS.get(mode, 30)
    with session_scope() as s:
        project = s.get(Project, project_id)
        if not project:
            raise ACEStepError("プロジェクトが見つかりません")
        cands = s.exec(select(Candidate).where(Candidate.project_id == project_id).order_by(Candidate.label)).all()
        if not cands:
            raise ACEStepError("候補が未作成です")
        project.mode = mode
        project.status = "generating"
        s.add(project)
        for c in cands:
            c.target_duration_s = secs
            c.status = "pending"
            s.add(c)
        s.commit()
        cands = [c for c in cands]
        items = [
            {"kind": "candidate", "project_id": project_id, "candidate_id": c.id, "label": c.label + "_", "prompt": c.prompt, "lyrics": c.lyrics,
             "duration_s": secs, "seed": c.seed, "thinking": thinking, "bpm": c.bpm, "key_scale": c.key_scale}
            for c in cands
        ]
    if mode == "overnight":
        first = items[0]
        first["chain"] = items[1:]
        return [enqueue("candidate", project_id, first["candidate_id"], first, note="Overnight: 順次生成")]
    return [enqueue("candidate", project_id, it["candidate_id"], it, note=f"{mode}: {secs}秒") for it in items]


def start_full(project_id: int, candidate_id: int, full_seconds: int = FULL_SECONDS_DEFAULT, thinking: bool = False) -> int:
    with session_scope() as s:
        c = s.get(Candidate, candidate_id)
        if not c or c.project_id != project_id:
            raise ACEStepError("候補が見つかりません")
        params = {"project_id": project_id, "candidate_id": candidate_id, "label": c.label + "_full_", "prompt": c.prompt, "lyrics": c.lyrics,
                  "duration_s": int(full_seconds), "seed": c.seed, "thinking": thinking, "bpm": c.bpm, "key_scale": c.key_scale}
    return enqueue("full", project_id, candidate_id, params, note=f"採用案 {c.label} を {full_seconds} 秒化")
