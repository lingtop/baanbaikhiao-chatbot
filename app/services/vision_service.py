"""วิเคราะห์รูปภาพด้วย Vision LLM (สัปดาห์ 10)

ภาพ → Base64 data URL → ส่งใน content แบบ image_url → โมเดลตอบเป็น JSON
แยก system prompt ของโหมดวิเคราะห์ภาพไว้ใน prompts/vision_system.md
"""

import base64
import json
import re
from pathlib import Path

from app.config import get_settings
from app.services.llm_service import LLMError, build_messages, chat

PROMPT = (Path(__file__).resolve().parent.parent / "prompts" / "vision_system.md").read_text(encoding="utf-8")
ALLOWED_TYPES = {"image/jpeg", "image/png", "image/webp"}
FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)


def to_data_url(data: bytes, mime: str) -> str:
    return f"data:{mime};base64,{base64.b64encode(data).decode()}"


def parse_json(text: str) -> dict:
    """โมเดลบางครั้งตอบ JSON ปนข้อความหรือ code fence (ปัญหาที่พบจริงในสัปดาห์ 10)"""
    cleaned = FENCE_RE.sub("", text.strip())
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if not m:
            raise
        return json.loads(m.group(0))


async def analyze(image: bytes, mime: str, user_text: str) -> dict:
    s = get_settings()
    content = [
        {"type": "text", "text": f"ข้อความของลูกค้า: {user_text or '(ไม่มีข้อความ)'}"},
        {"type": "image_url", "image_url": {"url": to_data_url(image, mime)}},
    ]
    messages = build_messages(PROMPT, [], content)
    last_error = None
    for _ in range(2):  # ถ้า JSON เสีย ลองใหม่อีก 1 ครั้ง
        text = await chat(messages, model=s.VISION_MODEL, temperature=0, json_mode=True, max_tokens=700,
                          allow_fallback=False)  # ตัวสำรองบน Groq ดูรูปไม่ได้
        try:
            result = parse_json(text)
            result.setdefault("seen", [])
            result.setdefault("type", "other")
            return result
        except json.JSONDecodeError as e:
            last_error = e
    raise LLMError(502, f"vision JSON parse failed: {last_error}")


def describe(result: dict) -> str:
    """แปลงผล JSON เป็นข้อความสั้นสำหรับแนบเข้า prompt ของ Chat LLM และแสดงบนหน้าเว็บ"""
    parts = []
    slip = result.get("slip") or {}
    if result.get("type") == "payment_slip" and slip:
        amount = slip.get("amount")
        if isinstance(amount, (int, float)):
            amount = f"{amount:,.0f}" if float(amount).is_integer() else f"{amount:,.2f}"
        parts.append("สลิปโอนเงิน: " + ", ".join(
            x for x in [f"ยอด {amount} บาท" if amount else None,
                        f"วันที่ {slip['date']}" if slip.get("date") else None,
                        f"เวลา {slip['time']}" if slip.get("time") else None,
                        f"ธนาคาร {slip['bank']}" if slip.get("bank") else None] if x))
    else:
        if result.get("plant_guess"):
            parts.append(f"น่าจะเป็น: {result['plant_guess']}")
        parts += result.get("seen") or []
        parts += [f"อาการ: {x}" for x in result.get("symptoms") or []]
    if result.get("confidence") == "low":
        parts.append("(ความมั่นใจต่ำ — รูปอาจไม่ชัด)")
    return " · ".join(parts)
