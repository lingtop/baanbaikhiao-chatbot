"""เรียก LLM ผ่าน API มาตรฐาน OpenAI-compatible (/chat/completions) — สัปดาห์ 7

ใช้ได้กับทุกผู้ให้บริการที่รองรับรูปแบบนี้ (Google AI Studio, Groq, OpenRouter, LM Studio)
แค่เปลี่ยน LLM_BASE_URL / LLM_API_KEY / LLM_MODEL ใน .env
"""

import logging
import re

import httpx

from app.config import get_settings
from app.services.http_client import get_client

log = logging.getLogger("uvicorn.error")
THOUGHT_RE = re.compile(r"<(thought|think)>.*?</\1>", re.DOTALL)

# แปลงรหัส error ของผู้ให้บริการเป็นข้อความภาษาไทยที่ผู้ใช้เข้าใจ (สัปดาห์ 7)
ERROR_MESSAGES = {
    400: "คำขอไม่ถูกต้อง (เช่น รูปภาพเสียหรือไม่รองรับ)",
    401: "API key ไม่ถูกต้อง",
    403: "ไม่มีสิทธิ์ใช้งานโมเดลนี้",
    404: "ไม่พบโมเดลที่ตั้งค่าไว้",
    429: "ใช้งานเกินโควต้าชั่วคราว กรุณารอสักครู่แล้วลองใหม่",
    500: "ผู้ให้บริการ AI ขัดข้องชั่วคราว",
    503: "ผู้ให้บริการ AI ไม่ว่างชั่วคราว",
}


class LLMError(Exception):
    def __init__(self, status: int, detail: str = ""):
        self.status = status
        self.detail = detail
        super().__init__(ERROR_MESSAGES.get(status, f"เรียก AI ไม่สำเร็จ (รหัส {status})"))


def build_messages(system_prompt: str, history: list[dict], user_content) -> list[dict]:
    """ประกอบ messages: system → ประวัติแชท → ข้อความล่าสุด"""
    return [{"role": "system", "content": system_prompt}, *history, {"role": "user", "content": user_content}]


async def _post(base_url: str, api_key: str, body: dict, timeout: float | None = None) -> str:
    if body["model"].startswith("openai/gpt-oss"):
        body = {**body, "reasoning_effort": "low"}  # reasoning model: คิดสั้น ๆ เพื่อให้ตอบเร็ว
    try:
        r = await get_client().post(f"{base_url.rstrip('/')}/chat/completions", json=body,
                                    headers={"Authorization": f"Bearer {api_key}"},
                                    timeout=timeout or httpx.USE_CLIENT_DEFAULT)
    except httpx.TimeoutException as e:
        raise LLMError(504, "timeout") from e
    except httpx.HTTPError as e:
        raise LLMError(503, str(e)) from e
    if r.status_code != 200:
        raise LLMError(r.status_code, r.text[:300])
    content = r.json()["choices"][0]["message"].get("content") or ""
    return THOUGHT_RE.sub("", content).strip()


async def chat(messages: list[dict], *, model: str | None = None, temperature: float | None = None,
               json_mode: bool = False, max_tokens: int = 1024, allow_fallback: bool = True) -> str:
    """เรียก LLM หลัก ถ้าผู้ให้บริการไม่ว่าง (429/503/504) สลับไปตัวสำรองอัตโนมัติ

    ตัวสำรองรับเฉพาะข้อความ — คำขอที่มีรูป (vision) ต้องส่ง allow_fallback=False
    """
    s = get_settings()
    body = {
        "model": model or s.LLM_MODEL,
        "messages": messages,
        "temperature": s.LLM_TEMPERATURE if temperature is None else temperature,
        "max_tokens": max_tokens,
    }
    if json_mode:
        body["response_format"] = {"type": "json_object"}
    can_fallback = allow_fallback and bool(s.LLM_FALLBACK_MODEL)
    try:
        # มีตัวสำรอง → ให้เวลาตัวหลักจำกัด ช้าเกินก็สลับ / ไม่มีตัวสำรอง (เช่น vision) → รอได้นานตามปกติ
        return await _post(s.LLM_BASE_URL, s.LLM_API_KEY.get_secret_value(), body,
                           timeout=s.LLM_PRIMARY_TIMEOUT if can_fallback else None)
    except LLMError as e:
        if not (can_fallback and e.status in (429, 500, 503, 504)):
            raise
        log.warning("LLM หลัก %s ล้มเหลว (%s) → ใช้ตัวสำรอง %s", body["model"], e.status, s.LLM_FALLBACK_MODEL)
    fallback = {**body, "model": s.LLM_FALLBACK_MODEL}
    return await _post(s.LLM_FALLBACK_BASE_URL, s.key_for(s.LLM_FALLBACK_BASE_URL, s.LLM_FALLBACK_API_KEY), fallback)


async def list_models() -> list[str]:
    s = get_settings()
    r = await get_client().get(f"{s.LLM_BASE_URL.rstrip('/')}/models",
                               headers={"Authorization": f"Bearer {s.LLM_API_KEY.get_secret_value()}"})
    if r.status_code != 200:
        raise LLMError(r.status_code, r.text[:300])
    return sorted(m["id"].removeprefix("models/") for m in r.json()["data"])
