"""ACE-Step 1.5 REST client.

Implements exactly the endpoints documented in the official repository
``docs/en/API.md`` (ace-step/ACE-Step-1.5, checked 2026-09-09):

* ``GET  /health``
* ``GET  /v1/models``
* ``GET  /v1/stats``
* ``POST /release_task``   -> ``{"data": {"task_id": ...}}``
* ``POST /query_result``   -> ``{"data": [{"task_id", "status", "result"}]}``  (status 0 queued/running, 1 succeeded, 2 failed)
* ``GET  /v1/audio?path=`` -> audio bytes

No other endpoints are assumed. Authentication (optional on the server) uses
``Authorization: Bearer <key>`` as documented.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

import httpx

from ..config import settings


class ACEStepError(RuntimeError):
    pass


@dataclass
class ACEStepStatus:
    reachable: bool
    detail: str
    models: list[str]
    default_model: str | None
    avg_job_seconds: float | None


class ACEStepClient:
    def __init__(self, base_url: str | None = None, api_key: str | None = None, timeout: float = 15.0):
        self.base_url = (base_url or settings.acestep_api_url).rstrip("/")
        self.api_key = api_key if api_key is not None else settings.acestep_api_key
        self.timeout = timeout

    # ------------------------------------------------------------ helpers
    def _headers(self) -> dict[str, str]:
        h = {"Content-Type": "application/json"}
        if self.api_key:
            h["Authorization"] = f"Bearer {self.api_key}"
        return h

    def _unwrap(self, r: httpx.Response) -> Any:
        if r.status_code == 401:
            raise ACEStepError("ACE-Step API: 認証エラー（ACESTEP_API_KEY を確認）")
        if r.status_code == 429:
            raise ACEStepError("ACE-Step API: キューが満杯です (429)")
        if r.status_code >= 400:
            raise ACEStepError(f"ACE-Step API: HTTP {r.status_code} {r.text[:200]}")
        try:
            body = r.json()
        except ValueError as exc:
            raise ACEStepError("ACE-Step API: JSONでない応答") from exc
        if isinstance(body, dict) and "data" in body:
            if body.get("code") not in (None, 200):
                raise ACEStepError(f"ACE-Step API: code={body.get('code')} error={body.get('error')}")
            return body["data"]
        return body

    # ------------------------------------------------------------ status
    def health(self) -> tuple[bool, str]:
        try:
            r = httpx.get(f"{self.base_url}/health", timeout=self.timeout)
            if r.status_code == 200:
                return True, r.text[:200]
            return False, f"HTTP {r.status_code}"
        except httpx.HTTPError as exc:
            return False, f"接続不可: {exc.__class__.__name__}"

    def status(self) -> ACEStepStatus:
        ok, detail = self.health()
        if not ok:
            return ACEStepStatus(False, detail, [], None, None)
        models: list[str] = []
        default = None
        avg = None
        try:
            data = self._unwrap(httpx.get(f"{self.base_url}/v1/models", timeout=self.timeout, headers=self._headers()))
            models = [m.get("name", "") for m in data.get("models", [])]
            default = data.get("default_model")
        except (ACEStepError, httpx.HTTPError):
            pass
        try:
            data = self._unwrap(httpx.get(f"{self.base_url}/v1/stats", timeout=self.timeout, headers=self._headers()))
            avg = data.get("avg_job_seconds")
        except (ACEStepError, httpx.HTTPError):
            pass
        return ACEStepStatus(True, detail, models, default, avg)

    # ------------------------------------------------------------ jobs
    def release_task(self, *, prompt: str, lyrics: str, duration_s: float, bpm: int | None = None, key_scale: str = "",
                     seed: int | None = None, inference_steps: int = 8, vocal_language: str = "en",
                     audio_format: str = "wav", thinking: bool = False, model: str | None = None, batch_size: int = 1,
                     time_signature: str = "4") -> str:
        payload: dict[str, Any] = {
            "prompt": prompt,
            "lyrics": lyrics,
            "audio_duration": float(duration_s),
            "inference_steps": inference_steps,
            "vocal_language": vocal_language,
            "audio_format": audio_format,
            "thinking": thinking,
            "batch_size": batch_size,
            "time_signature": time_signature,
            "use_cot_caption": False,
            "use_cot_language": False,
        }
        if bpm:
            payload["bpm"] = int(bpm)
        if key_scale:
            payload["key_scale"] = key_scale
        if seed is not None:
            payload["use_random_seed"] = False
            payload["seed"] = int(seed)
        if model:
            payload["model"] = model
        try:
            r = httpx.post(f"{self.base_url}/release_task", content=json.dumps(payload), headers=self._headers(), timeout=self.timeout)
        except httpx.HTTPError as exc:
            raise ACEStepError(f"ACE-Step API に接続できません: {exc.__class__.__name__}") from exc
        data = self._unwrap(r)
        task_id = data.get("task_id")
        if not task_id:
            raise ACEStepError("task_id が返されませんでした")
        return str(task_id)

    def query_result(self, task_ids: list[str]) -> list[dict[str, Any]]:
        try:
            r = httpx.post(f"{self.base_url}/query_result", content=json.dumps({"task_id_list": task_ids}), headers=self._headers(), timeout=self.timeout)
        except httpx.HTTPError as exc:
            raise ACEStepError(f"ACE-Step API に接続できません: {exc.__class__.__name__}") from exc
        data = self._unwrap(r)
        return data if isinstance(data, list) else []

    def download_audio(self, file_url: str, dest: Path) -> Path:
        """``file_url`` is the ``file`` field from the result, e.g. ``/v1/audio?path=...``."""
        url = file_url if file_url.startswith("http") else f"{self.base_url}{file_url if file_url.startswith('/') else '/' + file_url}"
        headers = {k: v for k, v in self._headers().items() if k != "Content-Type"}
        dest.parent.mkdir(parents=True, exist_ok=True)
        try:
            with httpx.stream("GET", url, headers=headers, timeout=120.0) as r:
                if r.status_code >= 400:
                    raise ACEStepError(f"音源ダウンロード失敗: HTTP {r.status_code}")
                with open(dest, "wb") as fh:
                    for chunk in r.iter_bytes():
                        fh.write(chunk)
        except httpx.HTTPError as exc:
            raise ACEStepError(f"音源ダウンロード失敗: {exc.__class__.__name__}") from exc
        return dest

    def wait_for(self, task_id: str, dest: Path, poll_s: float = 3.0, max_wait_s: float = 4 * 3600,
                 should_cancel: Callable[[], bool] | None = None, on_tick: Callable[[float], None] | None = None) -> dict[str, Any]:
        """Poll until succeeded/failed; download first audio to ``dest``. Returns parsed result dict."""
        start = time.monotonic()
        while True:
            if should_cancel and should_cancel():
                raise ACEStepError("cancelled")
            elapsed = time.monotonic() - start
            if elapsed > max_wait_s:
                raise ACEStepError(f"タイムアウト（{int(max_wait_s)}秒）")
            if on_tick:
                on_tick(elapsed)
            rows = self.query_result([task_id])
            row = next((x for x in rows if str(x.get("task_id")) == task_id), None)
            if row is None:
                time.sleep(poll_s)
                continue
            st = row.get("status")
            if st == 1:
                result = row.get("result")
                if isinstance(result, str):
                    try:
                        result = json.loads(result)
                    except ValueError:
                        result = []
                items = result if isinstance(result, list) else [result]
                if not items or not isinstance(items[0], dict) or not items[0].get("file"):
                    raise ACEStepError("結果に音声ファイルが含まれていません")
                first = items[0]
                self.download_audio(first["file"], dest)
                first["_elapsed_s"] = time.monotonic() - start
                return first
            if st == 2:
                raise ACEStepError(f"生成失敗: {str(row.get('result'))[:300]}")
            time.sleep(poll_s)
