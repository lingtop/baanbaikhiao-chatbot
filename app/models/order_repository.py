"""อ่านข้อมูลคำสั่งซื้อจาก data/orders_mock.json (ข้อมูลจำลอง)

ในระบบจริงส่วนนี้จะต่อฐานข้อมูล — service ที่เรียกใช้ไม่ต้องแก้
"""

import json
from functools import lru_cache
from pathlib import Path

PATH = Path(__file__).resolve().parents[2] / "data" / "orders_mock.json"


@lru_cache
def _orders() -> dict[str, dict]:
    return {o["order_id"]: o for o in json.loads(PATH.read_text(encoding="utf-8"))["orders"]}


def find_by_id(order_id: str) -> dict | None:
    return _orders().get(order_id.upper().replace(" ", ""))
