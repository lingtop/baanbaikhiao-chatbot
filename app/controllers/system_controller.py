"""Controller ระบบ

GET /api/v1/health   สถานะของ API, RAG, Guard และ API key
GET /api/v1/models   รายชื่อโมเดลที่ผู้ให้บริการเปิดให้ใช้ (สัปดาห์ 7)
"""

from fastapi import APIRouter, HTTPException

from app.config import get_settings
from app.services import guard_service, rag_service
from app.services.llm_service import LLMError, list_models

router = APIRouter(prefix="/api/v1", tags=["system"])


@router.get("/health")
async def health():
    s = get_settings()
    components = {
        "api": True,
        "rag": await rag_service.health(),
        "guard": await guard_service.health(),
        "llm_key": "LLM_API_KEY" not in s.missing_keys(),
    }
    return {
        "status": "ok" if all(components.values()) else "degraded",
        "components": components,
        "llm_model": s.LLM_MODEL,
        "missing_keys": s.missing_keys(),
    }


@router.get("/models")
async def models():
    try:
        return {"models": await list_models()}
    except LLMError as e:
        raise HTTPException(e.status, str(e))
