"""ด่านที่ 1–2 ของ Guard: Blocklist และ Business Rules ของร้าน (ไม่เรียกโมเดล ผลแน่นอน เร็ว ฟรี)

ข้อจำกัดของตัวจัดหมวดแบบ Llama Guard (สัปดาห์ 11): ไม่รู้กติกาธุรกิจของร้าน
จึงไม่จับ "ขอส่วนลด 50%" หรือ "ขอที่อยู่ลูกค้าคนอื่น" — ชั้นนี้เติมส่วนที่ขาด
"""

import json
import re
from functools import lru_cache
from pathlib import Path

from pythainlp.util import normalize

ROOT = Path(__file__).resolve().parents[2]  # โฟลเดอร์โปรเจกต์

# ---------- ข้อความปฏิเสธตามหมวด ----------
REFUSALS = {
    "BLOCKLIST": ("ข้อความไม่เหมาะสม",
                  "ขออภัยค่ะ ไม่สามารถตอบข้อความนี้ได้ ยินดีช่วยเรื่องต้นไม้ ราคา และบริการของร้านค่ะ"),
    "BIZ_DISCOUNT": ("นโยบายส่วนลด",
                     "ขออภัยค่ะ แชทบอทให้หรือยืนยันส่วนลดนอกเหนือจากโปรโมชันของร้านไม่ได้ ส่วนลดที่ใช้ได้ตอนนี้มีดังนี้ค่ะ\n"
                     "- สมาชิก ลด 5% (เฉพาะต้นไม้)\n"
                     "- เดือนเกิด ลด 10% (ใช้ร่วมกับส่วนลดสมาชิกไม่ได้)\n"
                     "- Green October: ซื้อไม้ใบ 3 ต้นขึ้นไป แถมดินปลูก 5 ลิตร\n\n"
                     "ถ้าต้องการสอบถามเพิ่มเติม ติดต่อแอดมินได้ที่ LINE @baanbaikhiao ค่ะ"),
    "BIZ_PRIVACY": ("ความเป็นส่วนตัว",
                    "ขออภัยค่ะ ร้านไม่เปิดเผยข้อมูลของลูกค้าทุกกรณี (ชื่อ ที่อยู่ เบอร์โทร รายการสั่งซื้อ)\n\n"
                    "ถ้าต้องการเช็กสถานะคำสั่งซื้อของคุณเอง พิมพ์เลขคำสั่งซื้อพร้อมเบอร์โทร 4 ตัวท้ายที่ใช้สั่งซื้อ "
                    "เช่น \"เช็ก BK-0001 เบอร์ท้าย 1234\" ได้เลยค่ะ"),
    "INJECTION": ("คำสั่งที่ไม่อนุญาต",
                  "ขออภัยค่ะ น้องใบเขียวทำตามคำขอนี้ไม่ได้ ยินดีช่วยเรื่องต้นไม้ ราคา การจัดส่ง และบริการของร้านค่ะ"),
    "UNSAFE": ("เนื้อหาไม่เหมาะสม",
               "ขออภัยค่ะ ไม่สามารถช่วยเรื่องนี้ได้ ถ้ามีคำถามเรื่องต้นไม้หรือบริการของร้าน ยินดีช่วยค่ะ"),
    "PRICE_NOT_IN_KB": ("ตรวจสอบคำตอบ",
                        "ขออภัยค่ะ ระบบตรวจพบว่าคำตอบอาจมีราคาไม่ตรงกับข้อมูลของร้าน เพื่อความถูกต้อง "
                        "กรุณาถามใหม่อีกครั้ง หรือสอบถามแอดมินทาง LINE @baanbaikhiao ค่ะ"),
    "OUT_PII": ("ความเป็นส่วนตัว",
                "ขออภัยค่ะ คำตอบนี้มีข้อมูลที่เปิดเผยไม่ได้ กรุณาติดต่อแอดมินทาง LINE @baanbaikhiao ค่ะ"),
    "OUT_PROMISE": ("ตรวจสอบคำตอบ",
                    "ขออภัยค่ะ เรื่องนี้แชทบอทยืนยันแทนร้านไม่ได้ แอดมินจะเป็นผู้ตรวจสอบและยืนยันให้ "
                    "ติดต่อได้ที่ LINE @baanbaikhiao ค่ะ"),
}

# ---------- ด่าน 1: Blocklist ----------
_STRIP_RE = re.compile(r"[\s​‌‍﻿.,!?\-_*~'\"]+")


def squash(text: str) -> str:
    """ทำให้เป็นรูปมาตรฐานแล้วลบช่องว่าง/เครื่องหมาย เพื่อกันการเลี่ยงด้วยการเว้นวรรค (สัปดาห์ 11)"""
    return _STRIP_RE.sub("", normalize(text).lower())


@lru_cache
def blocklist() -> list[str]:
    lines = (Path(__file__).resolve().parents[1] / "data" / "blocklist.txt").read_text(encoding="utf-8").splitlines()
    return [squash(w) for w in lines if w.strip() and not w.startswith("#")]


def check_blocklist(text: str) -> str | None:
    s = squash(text)
    return "BLOCKLIST" if any(w in s for w in blocklist()) else None


# ---------- ด่าน 2: Business Rules (ขาเข้า) ----------
DISCOUNT_WORD = r"(ส่วนลด|ลดราคา|ลดให้|ลด\s*\d|ลดได้|โค้ด|คูปอง|discount|coupon|ของแถม|แถมฟรี|ฟรีค่า)"
AUTHORITY = r"(เจ้าของ|แอดมิน|ผู้จัดการ|พนักงาน|owner|admin|manager|อนุมัติ|อนุญาต|บอกแล้ว|บอกว่า|สัญญา|ยืนยัน)"
HAGGLE = r"(ต่อราคา|ลดหน่อย|ลดอีกได้|ลดราคาให้|ขอลดราคา)"
PERCENT = re.compile(r"(\d{1,3})\s*(%|เปอร์เซ็น|เปอร์|percent)")

ORDER_ID = r"BK-?\s?\d{4}"
PERSONAL = r"(ที่อยู่|address|ส่งไปที่ไหน|ส่งไปไหน|ชื่อผู้|ชื่อลูกค้า|ชื่อคนสั่ง|ใครสั่ง|เบอร์โทร(?!\s*\d)|เบอร์ติดต่อ|เบอร์ของ|เบอร์คน)"
OTHER_CUSTOMER = (r"(ลูกค้า(คน|ท่าน)อื่น|ข้อมูลลูกค้า|ลูกค้าที่(สั่ง|ซื้อ|มา)|คนที่สั่ง|คนที่ซื้อ|ออเดอร์ของคุณ\S+|"
                  r"คำสั่งซื้อของคุณ\S+|รายชื่อลูกค้า|ลูกค้าเมื่อวาน)")

INJECTION_PATTERNS = re.compile(
    r"(ลืม\S{0,6}(คำสั่ง|กฎ|ข้อกำหนด)|ไม่ต้อง(ทำตาม|สนใจ)\S{0,6}(คำสั่ง|กฎ)|ignore\s+(all\s+|the\s+|your\s+)?(previous|prior|above)|"
    r"system\s*prompt|ซิสเต็ม\s*พรอม|คำสั่งระบบ|พรอมต์ของคุณ|prompt\s+ของคุณ|เปลี่ยนบทบาท|สวมบทบาท|developer\s*mode|jailbreak|"
    r"\bDAN\b|ตอนนี้คุณ(คือ|เป็น)|คุณคือ(ผู้จัดการ|เจ้าของ|แอดมิน)|act\s+as|pretend\s+(to\s+be|you)|reveal\s+your|"
    r"แสดง(คำสั่ง|กฎ|prompt|พรอม)\S{0,10}(ทั้งหมด|ของคุณ|ออกมา)|พิมพ์(คำสั่ง|กฎ|prompt)\S{0,10}ออกมา)",
    re.IGNORECASE,
)


def check_input_rules(text: str) -> str | None:
    t = normalize(text)
    if INJECTION_PATTERNS.search(t):
        return "INJECTION"
    has_discount = re.search(DISCOUNT_WORD, t, re.IGNORECASE)
    if has_discount:
        if re.search(AUTHORITY, t, re.IGNORECASE):
            return "BIZ_DISCOUNT"
        if any(int(p.group(1)) > 10 for p in PERCENT.finditer(t)):
            return "BIZ_DISCOUNT"
    if re.search(HAGGLE, t):
        return "BIZ_DISCOUNT"
    if re.search(ORDER_ID, t, re.IGNORECASE) and re.search(PERSONAL, t, re.IGNORECASE):
        return "BIZ_PRIVACY"
    if re.search(OTHER_CUSTOMER, t):
        return "BIZ_PRIVACY"
    return None


# ---------- Business Rules (ขาออก) ----------
AMOUNT_RE = re.compile(r"(\d[\d,]*(?:\.\d+)?)\s*(?:บาท|฿)")
NUMBER_RE = re.compile(r"\d[\d,]*(?:\.\d+)?")
PHONE_RE = re.compile(r"(?<!\d)0\d{1,2}[-\s]?\d{3}[-\s]?\d{3,4}(?!\d)")
SHOP_PHONES = {"020000000"}
PROMISE_RE = re.compile(
    r"((?<!ไม่)(?<!ไม่ได้)ยืนยัน(ว่า)?\S{0,4}(ได้รับ|เงินเข้า|ชำระ)\S{0,6}(แล้ว|เรียบร้อย)|"
    r"(?<!ไม่)ได้รับเงิน\S{0,4}(แล้ว|เรียบร้อย)|"
    r"ลดให้\s*\d+\s*%)"
)


def _num(s: str) -> float:
    return float(s.replace(",", ""))


@lru_cache
def known_amounts() -> frozenset[float]:
    """จำนวนเงินทุกตัวในคลังความรู้ (ตัวเลขที่ตามด้วย "บาท") = ราคาที่บอทพูดได้

    นับเฉพาะตัวเลขที่เป็นจำนวนเงิน ไม่นับตัวเลขอื่น เช่น รหัสสินค้า P047 — ไม่งั้น "47 บาท" ที่แต่งขึ้นจะผ่าน
    """
    nums = set()
    for f in (ROOT / "data" / "knowledge_base").glob("*.md"):
        nums.update(_num(n) for n in AMOUNT_RE.findall(f.read_text(encoding="utf-8")))
    # ราคาต้นไม้ใน CSV อยู่ในรูป "6 นิ้ว:350" ไม่มีคำว่าบาท
    csv_text = (ROOT / "data" / "plants.csv").read_text(encoding="utf-8")
    nums.update(_num(n) for n in re.findall(r":(\d+)(?=[|,])", csv_text))
    return frozenset(nums)


@lru_cache
def customer_strings() -> tuple[str, ...]:
    """ชื่อ/ที่อยู่ลูกค้าในข้อมูลจำลอง — ห้ามโผล่ในคำตอบ"""
    data = json.loads((ROOT / "data" / "orders_mock.json").read_text(encoding="utf-8"))
    out = []
    for o in data["orders"]:
        out += [o["customer_name"], o["address"][:12]]
    return tuple(out)


def _computed(line: str, allowed: set[float]) -> set[float]:
    """ตัวเลขที่เป็นผลคำนวณจากตัวเลขอื่นในบรรทัดเดียวกัน (ยอมให้ถ้าคิดถูก)

    LLM เขียนวิธีคิดได้หลายแบบ เช่น "35 × 5 = 175" หรือ "35 บาท/วัน × 5 วัน = 175 บาท"
    จึงไม่จับรูปแบบตายตัว แต่ลองบวก/ลบ/คูณตัวเลขทุกคู่ (และ a×b+c) ในบรรทัด
    ตัวตั้งที่เป็นราคาต้องเป็นราคาที่มีอยู่จริง ผลลัพธ์จึงไม่ใช่ตัวเลขที่แต่งขึ้นลอย ๆ
    """
    nums = [_num(n) for n in NUMBER_RE.findall(line)]
    results = set()
    for i, a in enumerate(nums):
        for j, b in enumerate(nums):
            if i == j:
                continue
            results |= {a * b, a + b, a - b}
            for k, c in enumerate(nums):
                if k not in (i, j):
                    results |= {a * b + c, a * b - c}
    # ตัวเลขที่ใช้คำนวณต้องมาจากข้อมูลจริงอย่างน้อยหนึ่งตัว (กันการอ้างผลคำนวณจากตัวเลขที่แต่งเอง)
    if not any(n in allowed for n in nums):
        return set()
    return {round(r, 2) for r in results}


def check_output_rules(answer: str, context: str = "") -> str | None:
    if any(s in answer for s in customer_strings()):
        return "OUT_PII"
    for p in PHONE_RE.findall(answer):
        if re.sub(r"\D", "", p) not in SHOP_PHONES:
            return "OUT_PII"
    for m in PROMISE_RE.finditer(answer):
        # ภาษาไทยมักวางคำปฏิเสธไว้ก่อนหน้า เช่น "ยังยืนยันไม่ได้ว่าได้รับเงินแล้ว" — ไม่นับเป็นการรับปาก
        before = answer[max(0, m.start() - 15):m.start()]
        if "ไม่" in before or "ยัง" in before:
            continue
        return "OUT_PROMISE"
    allowed = set(known_amounts()) | {_num(n) for n in AMOUNT_RE.findall(context)}
    for line in answer.splitlines():
        unknown = [_num(a) for a in AMOUNT_RE.findall(line) if _num(a) not in allowed]
        if not unknown:
            continue
        computed = _computed(line, allowed)
        if any(round(v, 2) not in computed for v in unknown):
            return "PRICE_NOT_IN_KB"
    return None
