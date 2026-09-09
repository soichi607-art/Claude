import os
import sys
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

_TMP = Path(os.environ.get("SOA_TEST_TMP", str(ROOT / "data" / "_pytest")))
os.environ.setdefault("SOA_DATA_DIR", str(_TMP / "data"))
os.environ.setdefault("SOA_TESTING", "1")
os.environ.setdefault("SOA_RENDER_SCALE", "0.125")
os.environ.setdefault("SOA_RENDER_FPS", "10")
os.environ.setdefault("ACESTEP_API_URL", "http://127.0.0.1:1")  # unreachable by default


def make_test_audio(path: Path, seconds: int = 20, bpm: int = 128, sr: int = 22050) -> Path:
    t = np.linspace(0, seconds, sr * seconds, endpoint=False)
    beat = 60 / bpm
    y = np.zeros_like(t)
    for k in np.arange(0, seconds, beat):
        idx = (t >= k) & (t < k + 0.08)
        y[idx] += np.sin(2 * np.pi * 60 * (t[idx] - k)) * np.exp(-30 * (t[idx] - k))
    loud = ((t > seconds * 0.3) & (t < seconds * 0.6)) | (t > seconds * 0.75)
    y += 0.3 * np.sin(2 * np.pi * 220 * t) * loud + 0.05 * np.sin(2 * np.pi * 440 * t)
    path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(path, y / np.abs(y).max(), sr)
    return path


@pytest.fixture(scope="session")
def test_audio(tmp_path_factory) -> Path:
    return make_test_audio(tmp_path_factory.mktemp("audio") / "test20.wav", 20)


@pytest.fixture(scope="session")
def test_audio_40(tmp_path_factory) -> Path:
    return make_test_audio(tmp_path_factory.mktemp("audio") / "test40.wav", 40)


@pytest.fixture(scope="session")
def client():
    import shutil

    shutil.rmtree(_TMP, ignore_errors=True)
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as c:
        c.get("/")
        yield c


@pytest.fixture
def csrf(client) -> str:
    return client.cookies.get("soa_csrf")
