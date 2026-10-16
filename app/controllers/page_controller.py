"""Controller หน้าเว็บ

GET /   หน้าแชท (views/templates/index.html)
"""

from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app.config import get_settings

router = APIRouter(tags=["page"])
templates = Jinja2Templates(directory=Path(__file__).resolve().parents[1] / "views" / "templates")


@router.get("/", response_class=HTMLResponse)
async def index(request: Request):
    s = get_settings()
    return templates.TemplateResponse(request, "index.html", {
        "max_chars": s.MAX_MESSAGE_CHARS, "max_image_mb": s.MAX_IMAGE_MB})
