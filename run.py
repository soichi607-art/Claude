"""Start SoA EDM Studio:  python run.py"""
from __future__ import annotations

import uvicorn

from app.config import settings

if __name__ == "__main__":
    if not settings.is_localhost and not (settings.auth_user and settings.auth_password):
        raise SystemExit("LAN公開 (SOA_HOST != 127.0.0.1) には SOA_AUTH_USER / SOA_AUTH_PASSWORD の設定が必須です。")
    uvicorn.run("app.main:app", host=settings.host, port=settings.port, reload=False, workers=1)
