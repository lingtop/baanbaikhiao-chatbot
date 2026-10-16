"""โครงสร้างข้อมูลที่ส่งต่อกันระหว่าง controller และ service

- Pydantic model: ตรวจรูปแบบข้อมูลที่รับเข้ามาทาง API อัตโนมัติ (ผิดรูปแบบ → 422)
- dataclass: ผลลัพธ์ภายในระบบ เช่น ผลตรวจ Guard, ผลค้น RAG
"""

from dataclasses import dataclass, field

from pydantic import BaseModel, Field


# ---------- รับเข้าทาง API ----------

class OrderLookupRequest(BaseModel):
    order_id: str = Field(pattern=r"^BK-\d{4}$", examples=["BK-0001"])
    phone_last4: str = Field(pattern=r"^\d{4}$", examples=["0001"])


# ---------- ผลลัพธ์ภายในระบบ ----------

@dataclass
class GuardResult:
    """ผลตรวจจาก Guard Service"""
    safe: bool
    categories: list[str] = field(default_factory=list)
    message: str = ""  # ข้อความปฏิเสธภาษาไทย (เมื่อไม่ปลอดภัย)
    layer: str = ""    # ชั้นที่ดักจับ: blocklist / business_rules / prompt_guard / safety_classifier
    label: str = ""    # ป้ายหมวดที่แสดงบนหน้าเว็บ เช่น "นโยบายส่วนลด"


@dataclass
class RAGResult:
    """ผลค้นคลังความรู้"""
    context: str
    sources: list[str] = field(default_factory=list)


@dataclass
class OrderStatus:
    """สถานะคำสั่งซื้อ — มีเฉพาะข้อมูลที่ลูกค้าเห็นได้ ไม่มีชื่อ ที่อยู่ เบอร์โทร"""
    order_id: str
    status: str
    status_date: str
    tracking: str | None = None
