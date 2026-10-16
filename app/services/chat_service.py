"""ลำดับการทำงานของ 1 ข้อความ: Guard ขาเข้า → Vision → RAG → LLM → Guard ขาออก

ฟังก์ชัน run() เป็น async generator ส่ง event ออกมาทีละขั้น ให้ chat_controller ส่งต่อเป็น SSE
หน้าเว็บจึงแสดงสถานะทีละขั้นได้ระหว่างรอ (สัปดาห์ 6: Visibility of system status)

ชนิดของ event:
  {"type": "status", "step": "...", "state": "running" | "done" | "skipped"}
  {"type": "answer", "text": "...", "blocked": bool, ...}
  {"type": "error", "message": "...", "code": "..."}
  {"type": "done", "timings": {...}, "total": วินาที}
"""

import time
from pathlib import Path

from app.models import session_store
from app.services import guard_service, order_service, product_service, rag_service, vision_service
from app.services.llm_service import LLMError, build_messages, chat

CHAT_PROMPT = (Path(__file__).resolve().parent.parent / "prompts" / "chat_system.md").read_text(encoding="utf-8")

STEPS = {
    "guard_in": "ตรวจความปลอดภัย",
    "vision": "วิเคราะห์รูปภาพ",
    "rag": "ค้นข้อมูลจากคลังความรู้ของร้าน",
    "llm": "เรียบเรียงคำตอบ",
    "guard_out": "ตรวจคำตอบก่อนส่ง",
}

SUGGESTIONS = {
    "plant_symptom": ["รากเน่าดูยังไง", "ดินแบบไหนระบายน้ำดี"],
    "payment_slip": ["แอดมินยืนยันกี่โมง", "เช็กสถานะคำสั่งซื้อ"],
    "damaged_parcel": ["เงื่อนไขการเคลม", "ติดต่อแอดมิน"],
}


def _status(step: str, state: str) -> dict:
    return {"type": "status", "step": step, "label": STEPS[step], "state": state}


def build_user_content(text: str, context: str, seen: str, order_ctx: str) -> str:
    """ประกอบข้อความที่ส่งให้ LLM — ข้อมูลอ้างอิงอยู่ในแท็ก แยกจากข้อความลูกค้าชัดเจน"""
    parts = [f"<ข้อมูลร้าน>\n{context}\n</ข้อมูลร้าน>"]
    if order_ctx:
        parts.append(f"<สถานะคำสั่งซื้อ>\n{order_ctx}\n</สถานะคำสั่งซื้อ>")
    if seen:
        parts.append(f"<สิ่งที่เห็นในรูป>\n{seen}\n</สิ่งที่เห็นในรูป>")
    parts.append(f"<คำถามลูกค้า>\n{text or '(ลูกค้าส่งรูปมาโดยไม่มีข้อความ)'}\n</คำถามลูกค้า>")
    return "\n\n".join(parts)


async def run(sid: str, text: str, image: bytes | None = None, mime: str = ""):
    timings: dict[str, float] = {}
    t_start = time.perf_counter()

    def mark(step, t0):
        timings[step] = round(time.perf_counter() - t0, 2)

    try:
        # 1) Guard ขาเข้า
        yield _status("guard_in", "running")
        t0 = time.perf_counter()
        g = await guard_service.check(text or "(รูปภาพ)", "input")
        mark("guard_in", t0)
        yield _status("guard_in", "done")
        if not g.safe:
            yield {"type": "answer", "text": g.message, "blocked": True, "label": g.label,
                   "categories": g.categories, "layer": g.layer, "products": [], "sources": [],
                   "suggestions": ["ติดต่อแอดมิน", "โปรโมชันเดือนนี้"]}
            yield {"type": "done", "timings": timings, "total": round(time.perf_counter() - t_start, 2)}
            return

        # 2) Vision (เฉพาะเมื่อมีรูป)
        seen, vision_result = "", None
        if image:
            yield _status("vision", "running")
            t0 = time.perf_counter()
            vision_result = await vision_service.analyze(image, mime, text)
            seen = vision_service.describe(vision_result)
            mark("vision", t0)
            yield {"type": "vision", "seen": seen, "kind": vision_result.get("type")}
            yield _status("vision", "done")

        # 3) RAG — ใช้คำถาม + สิ่งที่เห็นในรูป เป็น query
        yield _status("rag", "running")
        t0 = time.perf_counter()
        query = " ".join(x for x in [text, (vision_result or {}).get("search_query", "")] if x).strip()
        rag = await rag_service.retrieve(query or "ข้อมูลร้าน")
        mark("rag", t0)
        yield _status("rag", "done")

        # คำสั่งซื้อ: ระบบค้นเอง LLM เห็นเฉพาะสถานะ
        order_ctx = ""
        found = order_service.extract_from_text(text)
        if found:
            order_ctx = order_service.as_context(*found)

        # 4) LLM
        yield _status("llm", "running")
        t0 = time.perf_counter()
        user_content = build_user_content(text, rag.context, seen, order_ctx)
        messages = build_messages(CHAT_PROMPT, session_store.get_history(sid), user_content)
        answer = await chat(messages)
        mark("llm", t0)
        yield _status("llm", "done")

        # 5) Guard ขาออก
        yield _status("guard_out", "running")
        t0 = time.perf_counter()
        g_out = await guard_service.check(answer, "output", context=user_content)
        mark("guard_out", t0)
        yield _status("guard_out", "done")

        if not g_out.safe:
            yield {"type": "answer", "text": g_out.message, "blocked": True, "label": g_out.label,
                   "categories": g_out.categories, "layer": g_out.layer, "products": [],
                   "sources": rag.sources, "suggestions": ["ติดต่อแอดมิน"]}
        else:
            session_store.append_turn(sid, text or "(ส่งรูปภาพ)", answer)
            kind = (vision_result or {}).get("type", "")
            yield {"type": "answer", "text": answer, "blocked": False, "seen": seen,
                   "products": product_service.find_products(answer), "sources": rag.sources,
                   "suggestions": SUGGESTIONS.get(kind, [])}

        yield {"type": "done", "timings": timings, "total": round(time.perf_counter() - t_start, 2)}

    except guard_service.GuardUnavailable as e:
        yield {"type": "error", "code": "guard_unavailable",
               "message": f"{e} ข้อความของคุณยังไม่ถูกส่งให้ผู้ช่วยตอบ"}
    except rag_service.RAGError as e:
        yield {"type": "error", "code": "rag_unavailable", "message": f"{e} กรุณาลองใหม่อีกครั้ง"}
    except LLMError as e:
        yield {"type": "error", "code": f"llm_{e.status}", "message": str(e)}
