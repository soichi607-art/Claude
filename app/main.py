"""SoA EDM Studio — FastAPI application entry point."""
from __future__ import annotations

import datetime as dt
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from sqlmodel import select

from .config import ROOT, settings
from .db import init_db, session_scope
from .models import Character
from .routers import analytics, characters, dashboard, generation, mv, projects, publish, settings_page, shorts
from .security import check_basic_auth, static_root
from .services import covers
from .services.generation import worker
from .web import render

DEFAULT_PROMPT = (
    "Original fictional virtual EDM artist named AERA, an androgynous adult in their early twenties, calm and powerful presence, "
    "distinctive natural facial structure, short asymmetrical hair fading from metallic silver to pale cyan, luminous soft-cyan eyes, "
    "small triangular light pattern beside the left eye, translucent futuristic ear device, elegant black and silver performance outfit "
    "with subtle cyan light lines, modest premium futuristic fashion, emotionally expressive face, cinematic realism, realistic skin, "
    "clean silhouette, high-end music artist photography, consistent identity and proportions, completely original character, "
    "no resemblance to any real person, no logo, no text"
)
DEFAULT_NEGATIVE = (
    "child, teenager, underage, celebrity, real artist, copyrighted character, logo, watermark, text, signature, sexualized pose, "
    "excessive skin exposure, distorted face, face morphing, asymmetrical eyes, duplicate person, extra limbs, extra fingers, malformed hands, "
    "blurry face, plastic skin, inconsistent hair, different costume, bad anatomy"
)
DEFAULT_SHEET = (
    "Create a professional character reference sheet of the exact same AERA identity and outfit in every panel: front portrait, left profile, "
    "right profile, three-quarter view, full-body front, full-body back, neutral expression, confident expression, emotional expression, "
    "light-gray studio background, even lighting, accurate proportions, no text, no logo, no other characters."
)
DEFAULT_PROFILE = (
    "完全オリジナルのバーチャルEDMアーティスト。成人・ジェンダーニュートラル。シルバーから淡いシアンへ変化する短い左右非対称の髪、淡いシアンの瞳、"
    "左目付近の小さな三角形の発光模様、半透明の未来的イヤーデバイス。黒・シルバー・シアンの上品な衣装。近未来的だが人間的。過度な露出なし、ロゴなし、政治・宗教的シンボルなし。"
)


def ensure_default_character() -> None:
    with session_scope() as s:
        if s.exec(select(Character)).first():
            return
        s.add(Character(name="AERA", profile=DEFAULT_PROFILE, prompt=DEFAULT_PROMPT, negative_prompt=DEFAULT_NEGATIVE, sheet_prompt=DEFAULT_SHEET, seed=20260909))
        s.commit()


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings.ensure_dirs()
    init_db()
    ensure_default_character()
    try:
        covers.pwa_icons(static_root())
    except Exception:
        pass
    worker.start()
    yield
    worker.stop()


app = FastAPI(title="SoA EDM Studio", lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
app.mount("/static", StaticFiles(directory=str(static_root())), name="static")


@app.middleware("http")
async def security_headers(request: Request, call_next):
    try:
        check_basic_auth(request)
    except HTTPException as exc:
        return Response(status_code=exc.status_code, headers=exc.headers or {}, content=exc.detail or "")
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "same-origin"
    response.headers["Content-Security-Policy"] = "default-src 'self'; img-src 'self' data: blob:; media-src 'self' blob:; style-src 'self' 'unsafe-inline'; script-src 'self'; connect-src 'self'"
    if getattr(request.state, "clear_flash", False):
        response.delete_cookie("soa_flash")
    return response


@app.exception_handler(HTTPException)
async def http_exc(request: Request, exc: HTTPException):
    if exc.status_code == 401:
        return Response(status_code=401, headers=exc.headers or {})
    if "text/html" in request.headers.get("accept", "") or request.method == "GET":
        return render(request, "error.html", {"status": exc.status_code, "detail": exc.detail}, status_code=exc.status_code)
    return JSONResponse({"detail": exc.detail}, status_code=exc.status_code)


for r in (dashboard, projects, generation, characters, mv, shorts, publish, analytics, settings_page):
    app.include_router(r.router)


@app.get("/manifest.webmanifest")
async def manifest():
    return JSONResponse({
        "name": "SoA EDM Studio", "short_name": "EDM Studio", "start_url": "/", "display": "standalone", "background_color": "#0b0d12",
        "theme_color": "#0b0d12", "lang": "ja", "icons": [{"src": "/static/icon-192.png", "sizes": "192x192", "type": "image/png"},
                                                            {"src": "/static/icon-512.png", "sizes": "512x512", "type": "image/png"}],
    }, media_type="application/manifest+json")


@app.get("/sw.js")
async def service_worker():
    return Response((static_root() / "sw.js").read_text(encoding="utf-8"), media_type="application/javascript", headers={"Service-Worker-Allowed": "/"})


@app.get("/healthz")
async def healthz():
    return {"ok": True, "time": dt.datetime.now().isoformat(timespec="seconds")}
