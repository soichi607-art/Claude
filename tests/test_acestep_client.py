"""Protocol test against a fake server implementing the documented ACE-Step 1.5 endpoints."""
import json
import socket
import threading
import time

import pytest
import uvicorn
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import Response

from app.services.acestep_client import ACEStepClient, ACEStepError


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def fake_acestep(api_key: str = "secret") -> FastAPI:
    app = FastAPI()
    tasks: dict[str, dict] = {}

    def wrap(data):
        return {"data": data, "code": 200, "error": None, "timestamp": int(time.time() * 1000), "extra": None}

    def auth(authorization: str | None):
        if api_key and authorization != f"Bearer {api_key}":
            raise HTTPException(401, "Unauthorized")

    @app.get("/health")
    def health():
        return wrap({"status": "ok", "service": "ACE-Step API", "version": "1.0"})

    @app.get("/v1/models")
    def models(authorization: str | None = Header(default=None)):
        auth(authorization)
        return wrap({"models": [{"name": "acestep-v15-turbo", "is_default": True}], "default_model": "acestep-v15-turbo"})

    @app.get("/v1/stats")
    def stats(authorization: str | None = Header(default=None)):
        auth(authorization)
        return wrap({"jobs": {"total": 1}, "avg_job_seconds": 8.5})

    @app.post("/release_task")
    async def release(request: Request, authorization: str | None = Header(default=None)):
        auth(authorization)
        body = await request.json()
        assert body["audio_duration"] == 10.0 and body["lyrics"] and body["prompt"]
        tid = f"task-{len(tasks) + 1}"
        tasks[tid] = {"polls": 0, "body": body}
        return wrap({"task_id": tid, "status": "queued", "queue_position": 1})

    @app.post("/query_result")
    async def query(request: Request, authorization: str | None = Header(default=None)):
        auth(authorization)
        body = await request.json()
        out = []
        for tid in body["task_id_list"]:
            t = tasks[tid]
            t["polls"] += 1
            if t["polls"] < 2:
                out.append({"task_id": tid, "status": 0, "result": ""})
            else:
                res = [{"file": "/v1/audio?path=%2Ftmp%2Fx.wav", "status": 1, "metas": {"bpm": 128, "keyscale": "A Minor", "duration": 10},
                        "seed_value": "12345", "dit_model": "acestep-v15-turbo", "lm_model": ""}]
                out.append({"task_id": tid, "status": 1, "result": json.dumps(res)})
        return wrap(out)

    @app.get("/v1/audio")
    def audio(path: str, authorization: str | None = Header(default=None)):
        auth(authorization)
        return Response(b"RIFF" + b"\x00" * 40, media_type="audio/wav")

    return app


@pytest.fixture(scope="module")
def fake_server():
    port = _free_port()
    config = uvicorn.Config(fake_acestep(), host="127.0.0.1", port=port, log_level="error")
    server = uvicorn.Server(config)
    th = threading.Thread(target=server.run, daemon=True)
    th.start()
    for _ in range(50):
        try:
            socket.create_connection(("127.0.0.1", port), timeout=0.2).close()
            break
        except OSError:
            time.sleep(0.1)
    yield f"http://127.0.0.1:{port}"
    server.should_exit = True


def test_full_protocol(fake_server, tmp_path):
    c = ACEStepClient(fake_server, api_key="secret")
    st = c.status()
    assert st.reachable and st.models == ["acestep-v15-turbo"] and st.avg_job_seconds == 8.5
    tid = c.release_task(prompt="edm", lyrics="[chorus]\nhi", duration_s=10, bpm=128, seed=42)
    assert tid == "task-1"
    res = c.wait_for(tid, tmp_path / "out.wav", poll_s=0.05)
    assert (tmp_path / "out.wav").exists() and res["seed_value"] == "12345" and res["metas"]["bpm"] == 128


def test_auth_failure(fake_server):
    c = ACEStepClient(fake_server, api_key="wrong")
    with pytest.raises(ACEStepError):
        c.release_task(prompt="x", lyrics="y", duration_s=10)


def test_unreachable_reports_cleanly():
    c = ACEStepClient("http://127.0.0.1:1", api_key="")
    ok, detail = c.health()
    assert ok is False and "接続不可" in detail
