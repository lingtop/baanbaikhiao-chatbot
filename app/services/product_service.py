"""การ์ดสินค้าในคำตอบ — ดึงจาก data/plants.csv โดยตรง ไม่ให้ LLM สร้างเอง

แสดงการ์ดเฉพาะต้นไม้ที่คำตอบ "พูดถึงชื่อและราคาตรงกับ CSV" เท่านั้น
ราคาบนการ์ดจึงมาจากแหล่งข้อมูลจริงเสมอ
"""

from app.models import plant_repository

CATEGORY_ICON = {
    "ไม้ใบในร่ม": "🪴", "ไม้แขวนและไม้เลื้อย": "🍃", "ปาล์มและไม้ต้นในร่ม": "🌴", "ไม้อวบน้ำ": "🌵",
    "แคคตัส": "🌵", "ไม้ดอก": "🌸", "กล้วยไม้": "🌺", "สับปะรดสีและทิลแลนเซีย": "🌿", "เฟิร์น": "🌿",
    "ไม้กินแมลง": "🪰", "ผักสวนครัวและสมุนไพร": "🌱",
}


def _price_in_text(price: int, text: str) -> bool:
    return f"{price:,}" in text or str(price) in text


def find_products(answer: str, limit: int = 4) -> list[dict]:
    text = answer
    found = []
    for p in plant_repository.all_plants():
        name = p["name_th"]
        idx = text.find(name)
        if idx < 0:
            continue
        window = text[idx: idx + len(name) + 160]  # ราคาต้องอยู่ใกล้ชื่อต้นไม้
        prices = [(size, pr) for size, pr in p["prices"] if _price_in_text(pr, window)]
        if not prices:
            continue
        text = text[:idx] + "□" * len(name) + text[idx + len(name):]  # กันชื่อสั้นจับซ้ำ
        found.append({
            "id": p["id"],
            "name": name,
            "name_en": p["name_en"],
            "icon": CATEGORY_ICON.get(p["category"], "🪴"),
            "difficulty": p["difficulty"],
            "tag": p["tags"].split("/")[0],
            "stock": p["stock_status"],
            "prices": [{"size": s, "price": pr} for s, pr in prices],
            "pos": idx,
        })
    found.sort(key=lambda x: x["pos"])
    for f in found:
        f.pop("pos")
    return found[:limit]
