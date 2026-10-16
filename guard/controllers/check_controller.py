"""Controller ของ Guard Service

POST /check    ตรวจข้อความทีละชั้น: ① Blocklist → ② Business Rules → ③ Prompt Guard 2 (ขาเข้า) → ④ Safety Classifier
GET  /health

Fail-closed: ถ้าตรวจด้วยโมเดลไม่ได้ ตอบ 502 ไม่ตอบว่า safe (สัปดาห์ 11)
"""

import logging
import time

import httpx
from fastapi import APIRouter
from fastapi.responses import JSONResponse

from guard.config import get_settings
from guard.models.schemas import CheckRequest, CheckResponse
from guard.services import classifier_service, rule_service

log = logging.getLogger("uvicorn.error")
router = APIRouter(tags=["guard"])
_client = httpx.AsyncClient()


def unsafe(req: CheckRequest, category: str, layer: str, categories: list[str] | None = None) -> CheckResponse:
    label, msg = rule_service.REFUSALS.get(category, rule_service.REFUSALS["UNSAFE"])
    log.info("unsafe direction=%s layer=%s category=%s", req.direction, layer, category)  # ไม่ log ข้อความ (PDPA)
    return CheckResponse(result="unsafe", direction=req.direction, layer=layer,
                         categories=categories or [category], label=label, msg=msg)


@router.get("/health")
async def health():
    return {"status": "ok"}


@router.post("/check", response_model=CheckResponse, response_model_exclude_none=True)
async def check(req: CheckRequest):
    t0 = time.perf_counter()

    # ① Blocklist
    if hit := rule_service.check_blocklist(req.message):
        return unsafe(req, hit, "blocklist")

    # ② Business Rules
    hit = rule_service.check_input_rules(req.message) if req.direction == "input" \
        else rule_service.check_output_rules(req.message, req.context)
    if hit:
        return unsafe(req, hit, "business_rules")

    try:
        # ③ Prompt Guard 2 — เฉพาะขาเข้า
        if req.direction == "input":
            score = await classifier_service.prompt_guard(_client, req.message)
            if score >= get_settings().INJECTION_THRESHOLD:
                return unsafe(req, "INJECTION", "prompt_guard", ["INJECTION"])

        # ④ Safety Classifier S1–S14
        cats = await classifier_service.safety(_client, req.message, req.direction)
        blocked = [c for c in cats if c in classifier_service.BLOCKED]
        if blocked:
            return unsafe(req, "UNSAFE", "safety_classifier", blocked)
    except classifier_service.ClassifierError as e:
        log.warning("guard unavailable: %s", e)
        return JSONResponse(status_code=502, content={"result": "error", "error": "guard_unavailable"})

    return CheckResponse(result="safe", direction=req.direction, msg=req.message,
                         elapsed=round(time.perf_counter() - t0, 2))
