"""Controller แชท — รับ request จากหน้าเว็บ ตรวจ input แล้วส่งต่อให้ chat_service

POST /api/v1/chat/stream   หน้าเว็บใช้ — ส่งสถานะทีละขั้นแบบ SSE (สัปดาห์ 6)
POST /api/v1/chat          สคริปต์ทดสอบใช้ — รอคำตอบเต็มแล้วคืน JSON
POST /api/v1/chat/reset    ปุ่ม "เริ่มบทสนทนาใหม่"
"""

import json

from fastapi import APIRouter, File, Form, HTTPException, Request, Response, UploadFile
from fastapi.responses import JSONResponse, StreamingResponse

from app.config import get_settings
from app.models import session_store
from app.services import chat_service
from app.services.vision_service import ALLOWED_TYPES

router = APIRouter(prefix="/api/v1/chat", tags=["chat"])


# ---------- ตัวช่วย: session / ตรวจ input / rate limit ----------

def get_sid(request: Request) -> str:
    sid = request.cookies.get(session_store.COOKIE_NAME)
    if not sid:
        sid = session_store.new_session_id()
        request.state.new_sid = sid
    return sid


def set_cookie(response: Response, request: Request, sid: str):
    if getattr(request.state, "new_sid", None):
        response.set_cookie(session_store.COOKIE_NAME, sid, httponly=True, samesite="lax", max_age=60 * 60 * 24)


async def validate(message: str, image: UploadFile | None) -> tuple[str, bytes | None, str]:
    """ตรวจ input ก่อนเข้า service (OWASP LLM06: จำกัดขนาด)"""
    s = get_settings()
    message = (message or "").strip()
    if len(message) > s.MAX_MESSAGE_CHARS:
        raise HTTPException(422, f"ข้อความยาวเกิน {s.MAX_MESSAGE_CHARS} ตัวอักษร")
    data, mime = None, ""
    if image is not None and image.filename:
        mime = (image.content_type or "").lower()
        if mime not in ALLOWED_TYPES:
            raise HTTPException(415, "รองรับเฉพาะไฟล์ .jpg .png .webp")
        data = await image.read()
        if len(data) > s.MAX_IMAGE_MB * 1024 * 1024:
            raise HTTPException(413, f"รูปภาพใหญ่เกิน {s.MAX_IMAGE_MB} MB")
    if not message and not data:
        raise HTTPException(422, "กรุณาพิมพ์ข้อความหรือแนบรูป")
    return message, data, mime


def check_rate(sid: str):
    if not session_store.allow_request(sid, get_settings().RATE_LIMIT_PER_MIN):
        raise HTTPException(429, "ส่งข้อความถี่เกินไป กรุณารอสักครู่แล้วลองใหม่")


# ---------- endpoints ----------

@router.post("/stream")
async def chat_stream(request: Request, message: str = Form(""), image: UploadFile | None = File(None)):
    sid = get_sid(request)
    check_rate(sid)
    text, data, mime = await validate(message, image)

    async def events():
        async for ev in chat_service.run(sid, text, data, mime):
            yield f"data: {json.dumps(ev, ensure_ascii=False)}\n\n"

    response = StreamingResponse(events(), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
    set_cookie(response, request, sid)
    return response


@router.post("")
async def chat_once(request: Request, message: str = Form(""), image: UploadFile | None = File(None),
                    session_id: str = Form("")):
    sid = session_id or get_sid(request)
    check_rate(sid)
    text, data, mime = await validate(message, image)
    result = {"answer": None}
    async for ev in chat_service.run(sid, text, data, mime):
        if ev["type"] == "answer":
            result.update({k: v for k, v in ev.items() if k != "type"})
            result["answer"] = ev["text"]
        elif ev["type"] == "vision":
            result["vision"] = ev
        elif ev["type"] == "done":
            result["timings"], result["total"] = ev["timings"], ev["total"]
        elif ev["type"] == "error":
            return JSONResponse(status_code=503, content={"error": ev["code"], "message": ev["message"]})
    response = JSONResponse(result)
    set_cookie(response, request, sid)
    return response


@router.post("/reset")
async def chat_reset(request: Request):
    sid = request.cookies.get(session_store.COOKIE_NAME)
    if sid:
        session_store.reset(sid)
    return {"ok": True}
