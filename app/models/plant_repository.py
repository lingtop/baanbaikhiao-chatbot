"""อ่านข้อมูลต้นไม้จาก data/plants.csv (แหล่งข้อมูลต้นไม้เพียงแหล่งเดียวของร้าน)"""

import csv
from functools import lru_cache
from pathlib import Path

CSV_PATH = Path(__file__).resolve().parents[2] / "data" / "plants.csv"


def _parse_prices(text: str) -> list[tuple[str, int]]:
    """'6 นิ้ว:350|10 นิ้ว:890' → [('6 นิ้ว', 350), ('10 นิ้ว', 890)]"""
    return [(s.rsplit(":", 1)[0].strip(), int(s.rsplit(":", 1)[1])) for s in text.split("|")]


@lru_cache
def all_plants() -> list[dict]:
    """ต้นไม้ทั้งหมด เรียงชื่อยาวก่อน เพื่อให้ "ลิ้นมังกรขอบทอง" ไม่ถูกจับเป็น "ลิ้นมังกร" ตอนค้นชื่อในข้อความ"""
    with open(CSV_PATH, encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    for r in rows:
        r["prices"] = _parse_prices(r["sizes_prices"])
    return sorted(rows, key=lambda r: len(r["name_th"]), reverse=True)
