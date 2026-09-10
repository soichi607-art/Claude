"""Application configuration loaded from environment / .env (never logged)."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def parse_env_value(raw: str) -> str:
    """Return the value part of a .env line without quotes or an inline comment.

    ``.env.example`` documents each key with a trailing ``# comment``; the comment must
    never become part of the value (otherwise SOA_HOST becomes "127.0.0.1   # ..." and the
    app wrongly switches to LAN mode).
    """
    v = raw.strip()
    if not v or v.startswith("#"):
        return ""
    if v[0] in ("'", '"'):
        end = v.find(v[0], 1)
        return v[1:end] if end > 0 else v[1:]
    for i, ch in enumerate(v):
        if ch == "#" and (i == 0 or v[i - 1] in " \t"):
            return v[:i].strip()
    return v


def _load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k = k.strip()
        if k.lower().startswith("export "):
            k = k[7:].strip()
        os.environ.setdefault(k, parse_env_value(v))


_load_dotenv(ROOT / ".env")


def _bool(v: str | None, default: bool) -> bool:
    if v is None or v == "":
        return default
    return v.strip().lower() in {"1", "true", "yes", "on"}


def _int(v: str | None, default: int) -> int:
    try:
        return int(v) if v not in (None, "") else default
    except ValueError:
        return default


@dataclass
class Settings:
    host: str = os.environ.get("SOA_HOST", "127.0.0.1")
    port: int = _int(os.environ.get("SOA_PORT"), 8000)
    secret_key: str = os.environ.get("SOA_SECRET_KEY", "")
    # Authentication is mandatory whenever the app is exposed beyond localhost.
    auth_user: str = os.environ.get("SOA_AUTH_USER", "")
    auth_password: str = os.environ.get("SOA_AUTH_PASSWORD", "")
    data_dir: Path = Path(os.environ.get("SOA_DATA_DIR", str(ROOT / "data")))
    max_upload_mb: int = _int(os.environ.get("SOA_MAX_UPLOAD_MB"), 200)
    acestep_dir: str = os.environ.get("ACESTEP_DIR", "")
    acestep_api_url: str = os.environ.get("ACESTEP_API_URL", "http://127.0.0.1:8001")
    acestep_api_key: str = os.environ.get("ACESTEP_API_KEY", "")
    cpu_threads: int = _int(os.environ.get("SOA_CPU_THREADS"), 0)  # 0 = auto (half of logical cores)
    min_free_disk_gb: float = float(os.environ.get("SOA_MIN_FREE_DISK_GB", "5"))
    min_free_mem_gb: float = float(os.environ.get("SOA_MIN_FREE_MEM_GB", "2"))
    max_temp_c: float = float(os.environ.get("SOA_MAX_TEMP_C", "90"))
    stop_on_battery: bool = _bool(os.environ.get("SOA_STOP_ON_BATTERY"), True)
    rest_between_candidates_s: int = _int(os.environ.get("SOA_REST_BETWEEN_CANDIDATES_S"), 60)
    font_path: str = os.environ.get("SOA_FONT_PATH", "")
    font_path_ja: str = os.environ.get("SOA_FONT_PATH_JA", "")
    ffmpeg_bin: str = os.environ.get("SOA_FFMPEG", "ffmpeg")
    ffprobe_bin: str = os.environ.get("SOA_FFPROBE", "ffprobe")
    video_encoder: str = os.environ.get("SOA_VIDEO_ENCODER", "auto")
    testing: bool = _bool(os.environ.get("SOA_TESTING"), False)
    render_scale: float = float(os.environ.get("SOA_RENDER_SCALE", "1.0"))  # <1.0 for quick previews / tests
    render_fps: int = _int(os.environ.get("SOA_RENDER_FPS"), 30)
    allowed_audio_ext: tuple[str, ...] = field(default=(".wav", ".mp3", ".flac", ".m4a", ".aac", ".ogg", ".opus"))
    allowed_image_ext: tuple[str, ...] = field(default=(".png", ".jpg", ".jpeg", ".webp"))
    allowed_video_ext: tuple[str, ...] = field(default=(".mp4", ".mov", ".webm", ".mkv"))

    @property
    def db_path(self) -> Path:
        return self.data_dir / "soa_edm.db"

    @property
    def projects_dir(self) -> Path:
        return self.data_dir / "projects"

    @property
    def characters_dir(self) -> Path:
        return self.data_dir / "characters"

    @property
    def tmp_dir(self) -> Path:
        return self.data_dir / "tmp"

    @property
    def audit_dir(self) -> Path:
        return self.data_dir / "audit"

    @property
    def is_localhost(self) -> bool:
        return self.host in {"127.0.0.1", "localhost", "::1"}

    def ensure_dirs(self) -> None:
        for p in (self.data_dir, self.projects_dir, self.characters_dir, self.tmp_dir, self.audit_dir, self.data_dir / "uploads"):
            p.mkdir(parents=True, exist_ok=True)


settings = Settings()
