from __future__ import annotations

from fastapi import APIRouter, Request

from ..web import render

router = APIRouter()


@router.get("/help")
async def help_page(request: Request):
    return render(request, "help.html", {})
