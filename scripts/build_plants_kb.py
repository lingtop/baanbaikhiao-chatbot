"""แปลง data/plants.csv -> ไฟล์คลังความรู้ (markdown) สำหรับ RAG

ใช้งาน:  python scripts/build_plants_kb.py

ผลลัพธ์:
  data/knowledge_base/02_plants.md               รายละเอียดต้นไม้ทีละต้น (1 ต้น = 1 หัวข้อ ### = 1 chunk)
  data/knowledge_base/09_plant_recommendations.md  รายการสรุปสำหรับคำถามแนะนำ เช่น มือใหม่ + แสงน้อย

แก้ข้อมูลต้นไม้ที่ data/plants.csv เท่านั้น แล้วรันสคริปต์นี้ใหม่ ห้ามแก้ไฟล์ .md ที่สร้างขึ้นโดยตรง
"""

import csv
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CSV_PATH = ROOT / "data" / "plants.csv"
KB_DIR = ROOT / "data" / "knowledge_base"

CATEGORY_ORDER = [
    "ไม้ใบในร่ม",
    "ไม้แขวนและไม้เลื้อย",
    "ปาล์มและไม้ต้นในร่ม",
    "ไม้อวบน้ำ",
    "แคคตัส",
    "ไม้ดอก",
    "กล้วยไม้",
    "สับปะรดสีและทิลแลนเซีย",
    "เฟิร์น",
    "ไม้กินแมลง",
    "ผักสวนครัวและสมุนไพร",
]
DIFFICULTIES = {"ง่ายมาก", "ง่าย", "ปานกลาง", "ยาก"}
SHIP_VALUES_PREFIX = ("ได้", "ไม่ได้")

GENERATED_NOTICE = "> ไฟล์นี้สร้างอัตโนมัติจาก data/plants.csv ด้วย scripts/build_plants_kb.py — ห้ามแก้ไขโดยตรง"


def load_plants():
    with open(CSV_PATH, encoding="utf-8-sig", newline="") as f:
        plants = list(csv.DictReader(f))
    errors = []
    seen_ids = set()
    for i, p in enumerate(plants, start=2):  # บรรทัดที่ 1 คือ header
        if None in p or any(v is None for v in p.values()):
            errors.append(f"บรรทัด {i}: จำนวนคอลัมน์ไม่ถูกต้อง (อาจมีเครื่องหมาย , ในข้อความ)")
            continue
        if p["id"] in seen_ids:
            errors.append(f"บรรทัด {i}: id ซ้ำ {p['id']}")
        seen_ids.add(p["id"])
        if p["category"] not in CATEGORY_ORDER:
            errors.append(f"บรรทัด {i}: หมวดไม่รู้จัก '{p['category']}'")
        if p["difficulty"] not in DIFFICULTIES:
            errors.append(f"บรรทัด {i}: ระดับการดูแลไม่ถูกต้อง '{p['difficulty']}'")
        if not p["ship_upcountry"].startswith(SHIP_VALUES_PREFIX):
            errors.append(f"บรรทัด {i}: ค่า ship_upcountry ไม่ถูกต้อง '{p['ship_upcountry']}'")
        try:
            p["prices"] = parse_prices(p["sizes_prices"])
        except ValueError as e:
            errors.append(f"บรรทัด {i}: ราคาไม่ถูกต้อง ({e})")
    if errors:
        sys.exit("พบข้อผิดพลาดใน plants.csv:\n" + "\n".join(errors))
    return plants


def parse_prices(text):
    """'6 นิ้ว:350|10 นิ้ว:890' -> [('6 นิ้ว', 350), ('10 นิ้ว', 890)]"""
    result = []
    for part in text.split("|"):
        size, price = part.rsplit(":", 1)
        result.append((size.strip(), int(price)))
    return result


def format_prices(prices):
    return " / ".join(f"{size} {price:,} บาท" for size, price in prices)


def is_low_light(p):
    return "ทนแสงน้อย" in p["light"]


def is_available(p):
    return p["stock_status"].startswith("มีสินค้า")


def has_tag(p, tag):
    return tag in p["tags"].split("/")


def display_name(p):
    return f"{p['name_th']} ({p['name_en']})"


def plant_section(p):
    lines = [
        f"### {p['name_th']} ({p['name_en']})",
        f"- รหัสสินค้า: {p['id']}",
        f"- หมวด: {p['category']}",
        f"- ชื่อวิทยาศาสตร์: {p['scientific_name']}",
        f"- ราคา: {format_prices(p['prices'])}",
        f"- แสง: {p['light']}",
        f"- รดน้ำ: {p['water']}",
        f"- ระดับการดูแล: {p['difficulty']}",
        f"- เหมาะกับ: {p['tags'].replace('/', ', ')}",
        f"- สถานะสินค้า: {p['stock_status']}",
        f"- ส่งต่างจังหวัด: {p['ship_upcountry']}",
    ]
    if p["note"]:
        lines.append(f"- หมายเหตุ: {p['note']}")
    return "\n".join(lines)


def build_plants_md(plants):
    by_cat = defaultdict(list)
    for p in plants:
        by_cat[p["category"]].append(p)

    out = [
        "# รายการต้นไม้และราคา ร้านบ้านใบเขียว (อัปเดต ตุลาคม 2569)",
        "",
        GENERATED_NOTICE,
        "",
        f"ร้านมีต้นไม้ทั้งหมด {len(plants)} รายการ แบ่งเป็น {len(by_cat)} หมวด",
        "",
        "หมายเหตุทั่วไป:",
        "- ราคาเป็นราคาต้นไม้พร้อมกระถางพลาสติกสีดำ (กระถางเพาะ) ยังไม่รวมกระถางตกแต่ง ยกเว้นรายการที่ระบุว่าอยู่ในกระถางเซรามิก แจกัน หรือแผ่นไม้",
        "- ขนาด \"นิ้ว\" คือขนาดเส้นผ่านศูนย์กลางปากกระถาง",
        "- ต้นไม้ที่ไม่อยู่ในรายการนี้ถือว่าร้านไม่มีขาย",
        "",
    ]
    for cat in CATEGORY_ORDER:
        items = by_cat.get(cat, [])
        if not items:
            continue
        out.append(f"## หมวด{cat} ({len(items)} รายการ)")
        out.append("")
        for p in items:
            out.append(plant_section(p))
            out.append("")
    return "\n".join(out)


def name_list(plants):
    return "\n".join(
        f"- {display_name(p)} — {format_prices(p['prices'])}" for p in plants
    )


def build_recommendations_md(plants):
    available = [p for p in plants if is_available(p)]
    sections = [
        (
            "ต้นไม้สำหรับมือใหม่ (ดูแลง่าย)",
            [p for p in available if p["difficulty"] in ("ง่ายมาก",)],
            "ระดับการดูแล \"ง่ายมาก\" ทนทาน รดน้ำไม่บ่อย",
        ),
        (
            "ต้นไม้ทนแสงน้อย (ห้องคอนโด ห้องที่ไม่มีหน้าต่าง ออฟฟิศ)",
            [p for p in available if is_low_light(p)],
            "อยู่ได้ในที่แสงน้อยหรือใต้แสงไฟ แต่ทุกต้นจะโตดีขึ้นถ้าได้แสงสว่างมากขึ้น",
        ),
        (
            "ต้นไม้สำหรับมือใหม่ที่ทนแสงน้อย (คอนโด ห้องนอน ออฟฟิศ)",
            [p for p in available if p["difficulty"] in ("ง่ายมาก", "ง่าย") and is_low_light(p)],
            "ตัวเลือกที่ดีที่สุดสำหรับคนไม่มีเวลาและห้องไม่ค่อยมีแดด",
        ),
        (
            "ต้นไม้ที่ต้องดูแลมาก (เหมาะกับผู้มีประสบการณ์)",
            [p for p in available if p["difficulty"] == "ยาก"],
            "ต้องการการดูแลเรื่องแสง ความชื้น หรือคุณภาพน้ำเป็นพิเศษ",
        ),
        ("ไม้มงคล", [p for p in available if has_tag(p, "ไม้มงคล")], ""),
        ("ต้นไม้แนะนำเป็นของขวัญ", [p for p in available if has_tag(p, "ของขวัญ")], ""),
        (
            "ต้นไม้ขนาดเล็กสำหรับวางโต๊ะทำงาน",
            [p for p in available if has_tag(p, "โต๊ะทำงาน")],
            "",
        ),
        (
            "ต้นไม้สำหรับระเบียงที่มีแดดจัด",
            [p for p in available if "แดดจัด" in p["light"] and has_tag(p, "ระเบียง")],
            "",
        ),
        ("ไม้ดอกหอมและไม้หอม", [p for p in available if has_tag(p, "ไม้ดอกหอม") or has_tag(p, "ไม้หอม")], ""),
        ("ต้นไม้ที่ช่วยเพิ่มความสดชื่นในห้อง", [p for p in available if has_tag(p, "ไม้ฟอกอากาศ")],
         "เป็นไม้ใบที่นิยมวางในห้อง ร้านไม่ได้รับรองผลการฟอกอากาศในเชิงวิทยาศาสตร์"),
        ("ต้นไม้ราคาไม่เกิน 100 บาท", [p for p in available if min(pr for _, pr in p["prices"]) <= 100], ""),
    ]

    unavailable = [p for p in plants if not is_available(p)]
    not_upcountry = [p for p in plants if p["ship_upcountry"] != "ได้"]

    out = [
        "# รายการแนะนำต้นไม้ตามความต้องการ ร้านบ้านใบเขียว",
        "",
        GENERATED_NOTICE,
        "",
        "รายการด้านล่างนับเฉพาะต้นไม้ที่มีสินค้าพร้อมขาย (ยกเว้นหัวข้อที่ระบุ) รายละเอียดเต็มของแต่ละต้นอยู่ในรายการต้นไม้และราคา",
        "",
    ]
    for title, items, desc in sections:
        out.append(f"## {title} ({len(items)} รายการ)")
        if desc:
            out.append(desc)
        out.append(name_list(items))
        out.append("")

    out.append(f"## ต้นไม้ที่มีสถานะพิเศษ: สินค้าหมด / ตามฤดูกาล / ต้องสั่งจอง / มีบางขนาด ({len(unavailable)} รายการ)")
    out.extend(f"- {display_name(p)} — {p['stock_status']}" for p in unavailable)
    out.append("")
    out.append(f"## ต้นไม้ที่ส่งต่างจังหวัดไม่ได้ หรือส่งได้บางขนาด ({len(not_upcountry)} รายการ)")
    out.extend(f"- {display_name(p)} — {p['ship_upcountry']}" for p in not_upcountry)
    out.append("")
    out.append("## ต้นไม้ที่ร้านไม่มีขาย")
    out.append(
        "- ต้นไม้ที่ไม่อยู่ในรายการต้นไม้และราคาถือว่าร้านไม่มีขาย เช่น มอนสเตอร่าด่าง (Thai Constellation / Albo), บอนไซ, ไม้ผล, ไม้ยืนต้นขนาดใหญ่สำหรับปลูกลงดิน"
    )
    out.append("")
    return "\n".join(out)


def main():
    plants = load_plants()
    KB_DIR.mkdir(exist_ok=True)
    (KB_DIR / "02_plants.md").write_text(build_plants_md(plants), encoding="utf-8")
    (KB_DIR / "09_plant_recommendations.md").write_text(
        build_recommendations_md(plants), encoding="utf-8"
    )

    by_cat = defaultdict(int)
    for p in plants:
        by_cat[p["category"]] += 1
    print(f"สร้างคลังความรู้ต้นไม้สำเร็จ: {len(plants)} รายการ")
    for cat in CATEGORY_ORDER:
        print(f"  {cat}: {by_cat[cat]}")
    print(f"  ทนแสงน้อย: {sum(is_low_light(p) for p in plants)}")
    print(f"  ไม่พร้อมขาย: {sum(not is_available(p) for p in plants)}")


if __name__ == "__main__":
    main()
