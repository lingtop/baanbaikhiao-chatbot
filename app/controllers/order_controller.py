"""Controller คำสั่งซื้อ

POST /api/v1/orders/lookup   {order_id, phone_last4} → สถานะจัดส่ง (ไม่มีข้อมูลส่วนตัว)
"""

from dataclasses import asdict

from fastapi import APIRouter, HTTPException

from app.models.schemas import OrderLookupRequest
from app.services import order_service

router = APIRouter(prefix="/api/v1/orders", tags=["orders"])


@router.post("/lookup")
async def order_lookup(body: OrderLookupRequest):
    r = order_service.lookup(body.order_id, body.phone_last4)
    if not r:
        raise HTTPException(404, "ไม่พบคำสั่งซื้อ หรือเบอร์โทรไม่ตรงกัน")
    return {k: v for k, v in asdict(r).items() if v is not None}
