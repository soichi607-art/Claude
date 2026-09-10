"""Shared web helpers: templates, CSRF dependency, flash messages."""
from __future__ import annotations

import json
import urllib.parse
from pathlib import Path
from typing import Any

from fastapi import Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlmodel import select

from .config import ROOT, settings
from .db import session_scope
from .models import AppSetting, Character
from .security import CSRF_COOKIE, issue_csrf, verify_csrf

templates = Jinja2Templates(directory=str(ROOT / "app" / "templates"))
templates.env.autoescape = True


def get_setting(key: str, default: str = "") -> str:
    with session_scope() as s:
        row = s.get(AppSetting, key)
        return row.value if row else default


def set_setting(key: str, value: str) -> None:
    with session_scope() as s:
        row = s.get(AppSetting, key) or AppSetting(key=key)
        row.value = value
        s.add(row)
        s.commit()


def active_character() -> Character | None:
    with session_scope() as s:
        return s.exec(select(Character).where(Character.is_active == True).order_by(Character.id)).first()  # noqa: E712


def render(request: Request, name: str, ctx: dict[str, Any] | None = None, status_code: int = 200):
    ctx = dict(ctx or {})
    token = issue_csrf(request)
    ch = active_character()
    ctx.update({
        "request": request,
        "csrf_token": token,
        "artist_name": ch.name if ch else "AERA",
        "flash": _pop_flash(request),
        "app_host": settings.host,
        "app_port": settings.port,
        "is_localhost": settings.is_localhost,
    })
    resp = templates.TemplateResponse(request, name, ctx, status_code=status_code)
    if getattr(request.state, "new_csrf", None):
        resp.set_cookie(CSRF_COOKIE, token, httponly=True, samesite="strict", secure=False)
    return resp


def redirect(url: str, flash: str | None = None, kind: str = "info") -> RedirectResponse:
    resp = RedirectResponse(url, status_code=303)
    if flash:
        resp.set_cookie("soa_flash", urllib.parse.quote(json.dumps({"m": flash[:400], "k": kind})), max_age=30, samesite="lax", httponly=True)
    return resp


def _pop_flash(request: Request) -> dict[str, str] | None:
    raw = request.cookies.get("soa_flash")
    if not raw:
        return None
    try:
        data = json.loads(urllib.parse.unquote(raw))
        request.state.clear_flash = True
        return {"message": data.get("m", ""), "kind": data.get("k", "info")}
    except ValueError:
        return None


async def csrf_protect(request: Request) -> None:
    if request.method in ("POST", "PUT", "DELETE", "PATCH"):
        form = await request.form()
        verify_csrf(request, form.get("csrf_token"))
        request.state.form = form


def form_of(request: Request):
    return getattr(request.state, "form", None)


def project_output_dir(project_id: int) -> Path:
    return settings.projects_dir / str(project_id) / "output"
