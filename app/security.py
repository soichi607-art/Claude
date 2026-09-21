"""Security helpers: CSRF, optional auth for LAN exposure, upload validation, path guards."""
from __future__ import annotations

import base64
import hmac
import os
import re
import secrets
import unicodedata
from pathlib import Path

from fastapi import HTTPException, Request
from itsdangerous import BadSignature, URLSafeSerializer

from .config import ROOT, settings

_SECRET_FILE = settings.data_dir / ".secret_key"


def get_secret() -> str:
    if settings.secret_key:
        return settings.secret_key
    settings.ensure_dirs()
    if _SECRET_FILE.exists():
        return _SECRET_FILE.read_text(encoding="utf-8").strip()
    key = secrets.token_urlsafe(48)
    _SECRET_FILE.write_text(key, encoding="utf-8")
    try:
        os.chmod(_SECRET_FILE, 0o600)
    except OSError:
        pass
    return key


_serializer: URLSafeSerializer | None = None


def serializer() -> URLSafeSerializer:
    global _serializer
    if _serializer is None:
        _serializer = URLSafeSerializer(get_secret(), salt="soa-csrf")
    return _serializer


CSRF_COOKIE = "soa_csrf"


def issue_csrf(request: Request) -> str:
    """Return the CSRF token for this browser (double-submit cookie pattern)."""
    tok = request.cookies.get(CSRF_COOKIE)
    if tok:
        try:
            serializer().loads(tok)
            return tok
        except BadSignature:
            pass
    tok = serializer().dumps(secrets.token_hex(16))
    request.state.new_csrf = tok
    return tok


def verify_csrf(request: Request, form_token: str | None) -> None:
    cookie = request.cookies.get(CSRF_COOKIE)
    if not cookie or not form_token or not hmac.compare_digest(cookie, form_token):
        raise HTTPException(status_code=403, detail="CSRF検証に失敗しました。ページを再読み込みしてください。")
    try:
        serializer().loads(cookie)
    except BadSignature:
        raise HTTPException(status_code=403, detail="CSRFトークンが無効です。")


def check_basic_auth(request: Request) -> None:
    """Mandatory HTTP Basic auth when the app is bound to a non-localhost address."""
    if settings.is_localhost:
        return
    if not settings.auth_user or not settings.auth_password:
        raise HTTPException(status_code=503, detail="LAN公開時は SOA_AUTH_USER / SOA_AUTH_PASSWORD の設定が必須です。")
    header = request.headers.get("authorization", "")
    if not header.startswith("Basic "):
        raise HTTPException(status_code=401, headers={"WWW-Authenticate": 'Basic realm="SoA EDM Studio"'})
    try:
        raw = base64.b64decode(header[6:]).decode("utf-8")
        user, _, pw = raw.partition(":")
    except Exception:
        raise HTTPException(status_code=401, headers={"WWW-Authenticate": 'Basic realm="SoA EDM Studio"'})
    if not (hmac.compare_digest(user, settings.auth_user) and hmac.compare_digest(pw, settings.auth_password)):
        raise HTTPException(status_code=401, headers={"WWW-Authenticate": 'Basic realm="SoA EDM Studio"'})


# ------------------------------------------------------------- files
_SAFE_NAME = re.compile(r"[^A-Za-z0-9._-]+")


def safe_filename(name: str, default: str = "file") -> str:
    name = unicodedata.normalize("NFKC", name or "")
    name = os.path.basename(name.replace("\\", "/"))
    name = _SAFE_NAME.sub("_", name).strip("._")
    return name[:120] or default


def ensure_inside(base: Path, candidate: Path) -> Path:
    """Raise if ``candidate`` escapes ``base`` (path traversal guard)."""
    base_r = base.resolve()
    cand_r = candidate.resolve()
    try:
        cand_r.relative_to(base_r)
    except ValueError:
        raise HTTPException(status_code=400, detail="不正なパスです。")
    return cand_r


MAGIC = {
    "png": b"\x89PNG\r\n\x1a\n",
    "jpg": b"\xff\xd8\xff",
    "riff": b"RIFF",  # wav / webp
    "flac": b"fLaC",
    "ogg": b"OggS",
    "id3": b"ID3",
    "zip": b"PK\x03\x04",
}


def sniff_kind(head: bytes) -> str:
    if head.startswith(MAGIC["png"]) or head.startswith(MAGIC["jpg"]):
        return "image"
    if head.startswith(b"RIFF") and head[8:12] == b"WEBP":
        return "image"
    if head.startswith(b"RIFF") and head[8:12] == b"WAVE":
        return "audio"
    if head.startswith(MAGIC["flac"]) or head.startswith(MAGIC["ogg"]) or head.startswith(MAGIC["id3"]):
        return "audio"
    if len(head) > 1 and head[0] == 0xFF and (head[1] & 0xE0) == 0xE0:
        return "audio"  # MPEG frame sync
    if head[4:8] in (b"ftyp",):
        return "mp4"  # m4a / mp4 / mov share ftyp
    if head.startswith(MAGIC["zip"]):
        return "zip"
    if head[:4] == b"\x1a\x45\xdf\xa3":
        return "video"  # webm/mkv
    return "unknown"


def validate_upload(filename: str, head: bytes, size: int, expected: str) -> str:
    """Validate extension + magic + size. Returns safe filename. expected: audio|image|video|zip."""
    if size <= 0:
        raise HTTPException(status_code=400, detail="空のファイルです。")
    if size > settings.max_upload_mb * 1024 * 1024:
        raise HTTPException(status_code=413, detail=f"ファイルが大きすぎます（上限 {settings.max_upload_mb}MB）。")
    name = safe_filename(filename)
    ext = Path(name).suffix.lower()
    kind = sniff_kind(head)
    table = {
        "audio": (settings.allowed_audio_ext, {"audio", "mp4"}),
        "image": (settings.allowed_image_ext, {"image"}),
        "video": (settings.allowed_video_ext, {"mp4", "video"}),
        "zip": ((".zip",), {"zip"}),
    }
    exts, kinds = table[expected]
    if ext not in exts:
        raise HTTPException(status_code=400, detail=f"拡張子 {ext or '(なし)'} は許可されていません。許可: {', '.join(exts)}")
    if kind not in kinds:
        raise HTTPException(status_code=400, detail="ファイル内容が拡張子と一致しません。")
    return name


def redact(text: str) -> str:
    """Remove anything that looks like an API key before logging."""
    text = re.sub(r"(?i)(api[_-]?key|token|authorization)[\"':=\s]+(bearer\s+)?[A-Za-z0-9._\-]{8,}", r"\1=[REDACTED]", text)
    text = re.sub(r"(?i)bearer\s+[A-Za-z0-9._\-]{8,}", "Bearer [REDACTED]", text)
    if settings.acestep_api_key:
        text = text.replace(settings.acestep_api_key, "[REDACTED]")
    return text


def static_root() -> Path:
    return ROOT / "app" / "static"
