"""ตรวจสถานะคำสั่งซื้อ

สิทธิ์น้อยที่สุด (least privilege — สัปดาห์ 11):
- LLM ไม่เคยเห็นข้อมูลคำสั่งซื้อ service นี้เป็นคนค้นเอง
- ต้องมีเลขคำสั่งซื้อ + เบอร์โทร 4 ตัวท้ายที่ตรงกัน
- คืนเฉพาะสถานะการจัดส่ง ไม่คืนชื่อ ที่อยู่ เบอร์โทร
"""

import re

from app.models import order_repository
from app.models.schemas import OrderStatus

ORDER_RE = re.compile(r"\bBK-?\s?(\d{4})\b", re.IGNORECASE)
LAST4_RE = re.compile(r"(?:เบอร์|โทร|ท้าย|last4|phone)\D{0,12}(\d{4})\b", re.IGNORECASE)


def lookup(order_id: str, phone_last4: str) -> OrderStatus | None:
    order = order_repository.find_by_id(order_id)
    if not order or order["phone"][-4:] != phone_last4:
        return None
    return OrderStatus(order_id=order["order_id"], status=order["status"],
                       status_date=order["status_date"], tracking=order.get("tracking"))


def extract_from_text(text: str) -> tuple[str, str] | None:
    """ดึงเลขคำสั่งซื้อและเบอร์ 4 ตัวท้ายจากข้อความแชท เช่น 'เช็ก BK-0002 เบอร์ท้าย 0002'"""
    m = ORDER_RE.search(text)
    if not m:
        return None
    rest = text[m.end():] + " " + text[:m.start()]
    p = LAST4_RE.search(rest)
    return (f"BK-{m.group(1)}", p.group(1) if p else "")


def as_context(order_id: str, last4: str) -> str:
    """ข้อความที่แนบให้ LLM — มีเฉพาะสถานะ"""
    if not last4:
        return (f"ลูกค้าถามถึงคำสั่งซื้อ {order_id} แต่ยังไม่ได้ให้เบอร์โทร 4 ตัวท้าย "
                "ให้ขอเบอร์โทร 4 ตัวท้ายที่ใช้สั่งซื้อก่อน ห้ามบอกข้อมูลใด ๆ ของคำสั่งซื้อนี้")
    r = lookup(order_id, last4)
    if not r:
        return (f"ตรวจสอบคำสั่งซื้อ {order_id} ไม่ผ่าน (ไม่พบ หรือเบอร์ไม่ตรง) "
                "ให้แจ้งว่าตรวจสอบไม่ได้ และแนะนำติดต่อแอดมิน ห้ามบอกว่าข้อมูลส่วนไหนผิด")
    s = f"คำสั่งซื้อ {r.order_id}: สถานะ {r.status} (อัปเดต {r.status_date})"
    if r.tracking:
        s += f" เลขพัสดุ {r.tracking}"
    return s
