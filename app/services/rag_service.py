"""ค้นคลังความรู้ผ่าน RAG Server :9621 (LightRAG — สัปดาห์ 9)

RAG Server คืนเฉพาะข้อมูลที่ค้นเจอ ไม่สร้างคำตอบเอง
เพราะเราต้องการคุม system prompt (กฎต้องทำ/ห้ามทำ) และแนบรูปภาพใน llm_service ของเราเอง
"""

import httpx

from app.config import get_settings
from app.models.schemas import RAGResult
from app.services.http_client import get_client

# ชื่อไฟล์คลังความรู้ → ชื่อที่แสดงให้ลูกค้าเห็นเป็น "แหล่งอ้างอิง"
SOURCE_LABELS = {
    "01_shop_info.md": "ข้อมูลร้าน",
    "02_plants.md": "รายการต้นไม้และราคา",
    "03_pots_supplies.md": "กระถางและอุปกรณ์",
    "04_services.md": "บริการของร้าน",
    "05_shipping_payment.md": "การจัดส่งและชำระเงิน",
    "06_policies_promotions.md": "นโยบายและโปรโมชัน",
    "07_plant_care_guide.md": "คู่มือดูแลต้นไม้",
    "08_faq.md": "คำถามที่พบบ่อย",
    "09_plant_recommendations.md": "รายการแนะนำต้นไม้",
}


class RAGError(Exception):
    pass


async def retrieve(query: str, mode: str | None = None) -> RAGResult:
    s = get_settings()
    body = {"query": query, "mode": mode or s.RAG_MODE, "include_references": True, "top_k": 20, "chunk_top_k": 8}
    try:
        r = await get_client().post(f"{s.RAG_BASE_URL.rstrip('/')}/query", json=body, timeout=90)
    except httpx.HTTPError as e:
        raise RAGError("เชื่อมต่อคลังความรู้ไม่ได้") from e
    if r.status_code != 200:
        raise RAGError(f"คลังความรู้ตอบผิดพลาด (รหัส {r.status_code})")
    data = r.json()
    context = data.get("response") or ""
    if not context.strip():
        raise RAGError("คลังความรู้ไม่คืนข้อมูล")
    sources = []
    for ref in data.get("references") or []:
        name = SOURCE_LABELS.get((ref.get("file_path") or "").replace("\\", "/").split("/")[-1])
        if name and name not in sources:
            sources.append(name)
    return RAGResult(context=context, sources=sources)


async def health() -> bool:
    s = get_settings()
    try:
        r = await get_client().get(f"{s.RAG_BASE_URL.rstrip('/')}/health", timeout=5)
        return r.status_code == 200
    except httpx.HTTPError:
        return False
