"""โครงสร้างข้อมูลของ Guard Service"""

from typing import Literal

from pydantic import BaseModel, Field


class CheckRequest(BaseModel):
    message: str = Field(min_length=1, max_length=8000)
    direction: Literal["input", "output"]
    context: str = Field("", max_length=60000)  # ขาออก: ข้อมูลร้านที่ส่งให้ LLM ใช้ตรวจราคา


class CheckResponse(BaseModel):
    result: Literal["safe", "unsafe"]
    direction: Literal["input", "output"]
    layer: str = ""            # blocklist / business_rules / prompt_guard / safety_classifier
    categories: list[str] = []
    label: str = ""            # ป้ายหมวดภาษาไทย เช่น "นโยบายส่วนลด"
    msg: str                   # safe = ข้อความเดิม · unsafe = ข้อความปฏิเสธภาษาไทย
    elapsed: float | None = None
