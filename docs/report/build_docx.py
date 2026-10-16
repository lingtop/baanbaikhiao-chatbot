"""สร้างเอกสาร Deliverable 2 (เอกสารการพัฒนาโครงงานและผลการทดสอบ) เป็นไฟล์ .docx

ใช้งาน:
  uv run --no-project --with pillow python docs/report/build_images.py      # สร้างภาพก่อน
  uv run --no-project --with python-docx python docs/report/build_docx.py   # สร้างเอกสาร

ข้อมูลต้นไม้ดึงจาก data/plants.csv โดยตรง แก้ราคาที่ CSV แล้วรันใหม่ได้เลย
"""

import csv
import json
import statistics
from collections import defaultdict
from pathlib import Path

from docx import Document
from docx.enum.section import WD_SECTION
from docx.enum.table import WD_TABLE_ALIGNMENT, WD_CELL_VERTICAL_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

ROOT = Path(__file__).resolve().parents[2]
IMG = Path(__file__).resolve().parent / "img"
OUT = ROOT / "docs" / "BaanBaiKhiao_Deliverable2.docx"

FONT = "Leelawadee UI"
GREEN = RGBColor(0x1F, 0x5E, 0x3B)
LEAF = RGBColor(0x3E, 0x8E, 0x5A)
MUTED = RGBColor(0x66, 0x75, 0x6B)
HEAD_FILL = "DCEBDF"
BORDER = "BFD3C4"
CONTENT_W = 15.9  # ความกว้างพื้นที่เนื้อหา (ซม.) บน A4 ขอบ 2.54

CATEGORY_ORDER = [
    "ไม้ใบในร่ม", "ไม้แขวนและไม้เลื้อย", "ปาล์มและไม้ต้นในร่ม", "ไม้อวบน้ำ", "แคคตัส", "ไม้ดอก",
    "กล้วยไม้", "สับปะรดสีและทิลแลนเซีย", "เฟิร์น", "ไม้กินแมลง", "ผักสวนครัวและสมุนไพร",
]


# ---------- helpers: font / paragraph / table ----------

def set_run_font(run, size=None, bold=None, color=None, italic=None):
    run.font.name = FONT
    rpr = run._element.get_or_add_rPr()
    rfonts = rpr.find(qn("w:rFonts"))
    if rfonts is None:
        rfonts = OxmlElement("w:rFonts")
        rpr.insert(0, rfonts)
    for attr in ("w:ascii", "w:hAnsi", "w:cs", "w:eastAsia"):
        rfonts.set(qn(attr), FONT)
    if size is not None:
        run.font.size = Pt(size)
        szcs = rpr.find(qn("w:szCs"))
        if szcs is None:
            szcs = OxmlElement("w:szCs")
            rpr.append(szcs)
        szcs.set(qn("w:val"), str(int(size * 2)))
    if bold is not None:
        run.bold = bold
        bcs = rpr.find(qn("w:bCs"))
        if bold and bcs is None:
            rpr.append(OxmlElement("w:bCs"))
    if italic is not None:
        run.italic = italic
    if color is not None:
        run.font.color.rgb = color


def style_font(style, size, bold=False, color=None):
    style.font.name = FONT
    style.font.size = Pt(size)
    style.font.bold = bold
    if color is not None:
        style.font.color.rgb = color
    rpr = style.element.get_or_add_rPr()
    rfonts = rpr.find(qn("w:rFonts"))
    if rfonts is None:
        rfonts = OxmlElement("w:rFonts")
        rpr.insert(0, rfonts)
    for attr in ("w:ascii", "w:hAnsi", "w:cs", "w:eastAsia"):
        rfonts.set(qn(attr), FONT)
    for theme_attr in ("w:asciiTheme", "w:hAnsiTheme", "w:cstheme", "w:eastAsiaTheme"):
        if rfonts.get(qn(theme_attr)) is not None:
            del rfonts.attrib[qn(theme_attr)]
    szcs = rpr.find(qn("w:szCs"))
    if szcs is None:
        szcs = OxmlElement("w:szCs")
        rpr.append(szcs)
    szcs.set(qn("w:val"), str(int(size * 2)))


def para(doc_or_cell, text="", size=None, bold=False, color=None, align=None, space_after=4, italic=False):
    p = doc_or_cell.add_paragraph()
    if text:
        set_run_font(p.add_run(text), size=size, bold=bold, color=color, italic=italic)
    p.paragraph_format.space_after = Pt(space_after)
    if align:
        p.alignment = align
    return p


def label_line(doc, label, value):
    p = doc.add_paragraph()
    set_run_font(p.add_run(f"{label}: "), bold=True)
    set_run_font(p.add_run(value))
    p.paragraph_format.space_after = Pt(3)
    return p


def bullet(doc, text, label=None, style="List Bullet"):
    p = doc.add_paragraph(style=style)
    if label:
        set_run_font(p.add_run(f"{label}: "), bold=True)
    set_run_font(p.add_run(text))
    p.paragraph_format.space_after = Pt(2)
    return p


def note(doc, text, keep=False):
    p = para(doc, text, size=9, color=MUTED, space_after=8)
    p.paragraph_format.keep_with_next = keep
    return p


def heading(doc, text, level):
    h = doc.add_heading(level=level)
    set_run_font(h.add_run(text))
    return h


def shade(cell, fill):
    tcpr = cell._element.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), fill)
    tcpr.append(shd)


def set_table_borders(table, color=BORDER, size=4, inner=True):
    tblpr = table._element.tblPr
    borders = OxmlElement("w:tblBorders")
    edges = ("top", "left", "bottom", "right", "insideH", "insideV") if inner else ()
    for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
        el = OxmlElement(f"w:{edge}")
        if edge in edges:
            el.set(qn("w:val"), "single")
            el.set(qn("w:sz"), str(size))
            el.set(qn("w:color"), color)
        else:
            el.set(qn("w:val"), "nil")
        borders.append(el)
    tblpr.append(borders)


def set_cell_margins(table, top=60, bottom=60, left=90, right=90):
    tblpr = table._element.tblPr
    mar = OxmlElement("w:tblCellMar")
    for side, val in (("top", top), ("left", left), ("bottom", bottom), ("right", right)):
        el = OxmlElement(f"w:{side}")
        el.set(qn("w:w"), str(val))
        el.set(qn("w:type"), "dxa")
        mar.append(el)
    tblpr.append(mar)


def fix_layout(table, widths_cm):
    table.autofit = False
    tblpr = table._element.tblPr
    layout = OxmlElement("w:tblLayout")
    layout.set(qn("w:type"), "fixed")
    tblpr.append(layout)
    grid = table._element.tblGrid
    for gc, w in zip(grid.findall(qn("w:gridCol")), widths_cm):
        gc.set(qn("w:w"), str(int(w * 567)))
    for row in table.rows:
        for cell, w in zip(row.cells, widths_cm):
            cell.width = Cm(w)


def repeat_header(row):
    trpr = row._tr.get_or_add_trPr()
    el = OxmlElement("w:tblHeader")
    el.set(qn("w:val"), "true")
    trpr.append(el)


def keep_rows(table, keep_all_up_to=16):
    """ห้ามแถวขาดข้ามหน้า และให้ตารางสั้นอยู่หน้าเดียวกัน (ตารางยาว: ยึดหัวตารางไว้กับ 2 แถวแรก)"""
    n = len(table.rows)
    for idx, row in enumerate(table.rows):
        trpr = row._tr.get_or_add_trPr()
        trpr.append(OxmlElement("w:cantSplit"))
        keep = idx < n - 1 if n <= keep_all_up_to else idx <= 2
        if keep:
            for cell in row.cells:
                for p in cell.paragraphs:
                    p.paragraph_format.keep_with_next = True


def cell_text(cell, text, size, bold=False, color=None, align=None):
    cell.text = ""
    lines = text if isinstance(text, list) else [text]
    first = cell.paragraphs[0]
    for i, line in enumerate(lines):
        p = first if i == 0 else cell.add_paragraph()
        p.paragraph_format.space_after = Pt(0)
        p.paragraph_format.space_before = Pt(0)
        p.paragraph_format.line_spacing = 1.1
        if align:
            p.alignment = align
        if isinstance(line, tuple):  # (ตัวหนา, ตัวปกติ)
            set_run_font(p.add_run(line[0]), size=size, bold=True, color=color)
            set_run_font(p.add_run(line[1]), size=size, color=color)
        else:
            set_run_font(p.add_run(line), size=size, bold=bold, color=color)
    cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.TOP


def table(doc, headers, rows, widths, size=9.5, center_cols=(), keep_all_up_to=16):
    t = doc.add_table(rows=1 + len(rows), cols=len(headers))
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    set_table_borders(t)
    set_cell_margins(t)
    fix_layout(t, widths)
    for i, h in enumerate(headers):
        c = t.rows[0].cells[i]
        cell_text(c, h, size, bold=True, color=GREEN)
        shade(c, HEAD_FILL)
    repeat_header(t.rows[0])
    for r, row in enumerate(rows, start=1):
        for i, val in enumerate(row):
            align = WD_ALIGN_PARAGRAPH.CENTER if i in center_cols else None
            cell_text(t.rows[r].cells[i], val, size, align=align)
    keep_rows(t, keep_all_up_to)
    doc.add_paragraph().paragraph_format.space_after = Pt(2)
    return t


def image(doc, path, width_cm, caption=None):
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.add_run().add_picture(str(path), width=Cm(width_cm))
    p.paragraph_format.space_after = Pt(2)
    if caption:
        para(doc, caption, size=9, color=MUTED, align=WD_ALIGN_PARAGRAPH.CENTER, space_after=10)


def add_page_number_footer(section, prefix):
    p = section.footer.paragraphs[0]
    p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    set_run_font(p.add_run(f"{prefix} · หน้า "), size=8.5, color=MUTED)
    run = p.add_run()
    set_run_font(run, size=8.5, color=MUTED)
    for kind, text in (("begin", None), (None, " PAGE "), ("end", None)):
        if kind:
            fld = OxmlElement("w:fldChar")
            fld.set(qn("w:fldCharType"), kind)
            run._element.append(fld)
        else:
            instr = OxmlElement("w:instrText")
            instr.set(qn("xml:space"), "preserve")
            instr.text = text
            run._element.append(instr)


def page_break(doc):
    doc.add_paragraph().add_run().add_break(WD_BREAK.PAGE)


# ---------- data ----------

def load_plants():
    with open(ROOT / "data" / "plants.csv", encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    for r in rows:
        r["prices"] = [(s.rsplit(":", 1)[0], int(s.rsplit(":", 1)[1])) for s in r["sizes_prices"].split("|")]
    return rows


def price_text(prices):
    return " / ".join(f"{s} {p:,}" for s, p in prices)


# ---------- ผลทดสอบจริง (eval/results) ----------

CASES = json.loads((ROOT / "eval" / "cases.json").read_text(encoding="utf-8"))
LAYER_NAMES = {"business_rules": "Business Rules", "blocklist": "Blocklist", "prompt_guard": "Prompt Guard 2",
               "safety_classifier": "Safety Classifier"}


def load_eval(tag: str) -> dict:
    files = sorted((ROOT / "eval" / "results").glob(f"*_{tag}.json"))
    if not files:
        return {}
    return {r["id"]: r for r in json.loads(files[-1].read_text(encoding="utf-8")) if not r.get("skipped")}


def short(text: str, n: int = 170) -> str:
    text = " ".join((text or "").replace("**", "").split())
    return text if len(text) <= n else text[: n - 1].rstrip() + "…"


def eval_row(results: dict, case: dict, subject: str) -> list:
    r = results.get(case["id"])
    if not r:
        return [case["id"], subject, case["expected"], "รอภาพทดสอบ", "–", "–"]
    res = r["result"]
    return [case["id"], subject, case["expected"], short(res.get("answer", "")),
            "ผ่าน" if r["pass"] else "ไม่ผ่าน", str(res.get("total", res.get("wall_time")))]


def eval_metrics(results: dict, ids) -> dict:
    rows = [results[i] for i in ids if i in results]
    answered = [r for r in rows if not r["result"].get("blocked")]
    times = [r["result"].get("total", 0) for r in rows]
    return {
        "pass": f"{sum(r['pass'] for r in rows)}/{len(rows)}",
        "avg": round(statistics.mean(times), 2),
        "max": round(max(times), 2),
        "greet": sum(r["result"]["answer"].startswith("สวัสดีค่ะ") for r in answered),
        "double": sum("นะคะค่ะ" in r["result"]["answer"] for r in answered),
        "length": round(statistics.mean(len(r["result"]["answer"]) for r in answered)),
    }


# ---------- document ----------

def build():
    plants = load_plants()
    by_cat = defaultdict(list)
    for p in plants:
        by_cat[p["category"]].append(p)

    doc = Document()
    sec = doc.sections[0]
    sec.page_width, sec.page_height = Cm(21.0), Cm(29.7)
    sec.left_margin = sec.right_margin = Cm(2.54)
    sec.top_margin = sec.bottom_margin = Cm(2.3)

    normal = doc.styles["Normal"]
    style_font(normal, 10.5)
    normal.paragraph_format.line_spacing = 1.2
    normal.paragraph_format.space_after = Pt(4)
    style_font(doc.styles["Heading 1"], 17, bold=True, color=GREEN)
    doc.styles["Heading 1"].paragraph_format.space_before = Pt(16)
    doc.styles["Heading 1"].paragraph_format.space_after = Pt(6)
    style_font(doc.styles["Heading 2"], 13, bold=True, color=LEAF)
    doc.styles["Heading 2"].paragraph_format.space_before = Pt(12)
    doc.styles["Heading 2"].paragraph_format.space_after = Pt(4)
    style_font(doc.styles["Heading 3"], 11, bold=True, color=GREEN)
    doc.styles["Heading 3"].paragraph_format.space_before = Pt(8)
    doc.styles["Heading 3"].paragraph_format.space_after = Pt(3)
    for name in ("List Bullet", "List Number"):
        style_font(doc.styles[name], 10.5)
    add_page_number_footer(sec, "บ้านใบเขียว AI")

    # ----- หัวเอกสาร -----
    para(doc, "บ้านใบเขียว AI", size=30, bold=True, color=GREEN, space_after=2)
    para(doc, "เอกสารการพัฒนาโครงงานและผลการทดสอบ", size=15, bold=True, space_after=2)
    para(doc, "วิชา 06048308 Intelligent Chatbot Development · Final Project", size=10, color=MUTED, space_after=2)
    para(doc, "ฉบับรายงานความก้าวหน้า · ปรับปรุงล่าสุด 10 ต.ค. 2569 · ระบบต้นแบบทำงานได้ครบทุกส่วนแล้ว · "
              "ผลทดสอบเป็นผลจริงจากระบบ (ชุดภาพทดสอบยังรอภาพถ่ายจริง 4 ภาพ)", size=9.5, color=MUTED, space_after=6)

    # ----- 1 -----
    heading(doc, "1. ชื่อโครงงานและผู้พัฒนา", 1)
    label_line(doc, "ชื่อโครงงาน", "บ้านใบเขียว AI — แชทบอทตอบลูกค้าแทนร้านต้นไม้บ้านใบเขียว")
    label_line(doc, "รูปแบบงาน", "งานเดี่ยว")
    label_line(doc, "ผู้พัฒนา", "[ชื่อ-สกุล] (รหัสนักศึกษา [รหัสนักศึกษา])")
    label_line(doc, "Source code", "https://github.com/lingtop/baanbaikhiao-chatbot")
    label_line(doc, "ลิงก์ทดลองใช้", "https://baanbaikhiao.onrender.com (Docker บน Render free tier — ไม่มีผู้ใช้ 15 นาทีระบบจะพัก เปิดครั้งแรกรอประมาณ 1 นาที)")
    label_line(doc, "การใช้ AI ช่วยพัฒนา", "ใช้ Claude Code ช่วยเขียนโค้ด จัดทำข้อมูลจำลอง และร่างเอกสาร "
               "ผู้พัฒนาเป็นผู้กำหนดแนวทาง ตรวจสอบ และทดสอบทุกส่วน")

    # ----- 2 -----
    heading(doc, "2. ข้อมูลของธุรกิจ", 1)
    label_line(doc, "ชื่อธุรกิจ", "บ้านใบเขียว (Baan Bai Khiao Plant Shop) — ข้อมูลธุรกิจทั้งหมดเป็นข้อมูลจำลองสำหรับโครงงาน")
    label_line(doc, "รายละเอียด", "ร้านขายต้นไม้ในร่ม ไม้อวบน้ำ แคคตัส กล้วยไม้ กระถาง ดิน ปุ๋ย และอุปกรณ์ปลูก "
               "หน้าร้าน 1 สาขาในกรุงเทพฯ และขายออนไลน์ผ่านแชท มีบริการเปลี่ยนกระถาง รับฝากเลี้ยงต้นไม้ "
               "ห่อของขวัญ Workshop สวนขวด จัดสวนระเบียง และจัดส่งทั่วประเทศ ลูกค้าส่งรูปต้นไม้ให้ช่วยดูอาการได้ฟรี")
    label_line(doc, "เวลาทำการ", "ทุกวัน 09:00–19:00 น. ไม่มีวันหยุดประจำสัปดาห์ · ปิด 13–15 เม.ย. และ 31 ธ.ค.–1 ม.ค. · "
               "แอดมินตอบแชทและตรวจสลิป 09:00–18:00 น. · แชทบอทตอบได้ 24 ชั่วโมง")
    label_line(doc, "ช่องทางติดต่อ", "โทร 02-000-0000 · LINE OA @baanbaikhiao · แชทบนเว็บไซต์ (ข้อมูลจำลอง)")
    label_line(doc, "ขนาดข้อมูล", f"ต้นไม้ {len(plants)} สายพันธุ์ใน {len(by_cat)} หมวด · กระถาง/ดิน/ปุ๋ย/อุปกรณ์ 19 รายการ · "
               "บริการ 6 รายการ · นโยบาย 10 ข้อ · คู่มือแก้อาการต้นไม้ 12 อาการ")

    heading(doc, "2.1 กลุ่มเป้าหมาย", 2)
    table(doc, ["กลุ่ม", "ลักษณะ", "สิ่งที่มักถาม"], [
        ["คนทำงานอยู่คอนโด/หอพัก", "พื้นที่จำกัด แสงน้อย ไม่ค่อยมีเวลา", "ต้นไม้อะไรทนแสงน้อย รดน้ำไม่บ่อย"],
        ["มือใหม่หัดปลูก", "ยังไม่มีความรู้เรื่องการดูแล", "ทำไมใบเหลือง ต้องรดน้ำบ่อยแค่ไหน"],
        ["คนรักต้นไม้/นักสะสม", "มีประสบการณ์ อยากได้พันธุ์แปลก", "มีต้นนี้ไหม ดูแลยากไหม ใช้น้ำแบบไหน"],
        ["คนซื้อเป็นของขวัญ", "ขึ้นบ้านใหม่ เปิดร้าน วันเกิด", "ไม้มงคล ห่อของขวัญ ส่งถึงผู้รับได้ไหม"],
        ["ลูกค้าต่างจังหวัด", "สั่งออนไลน์", "ส่งต่างจังหวัดได้ไหม ต้นไม้เสียหายทำอย่างไร"],
        ["คนเดินทางบ่อย", "ไม่อยู่บ้านหลายวัน", "ฝากเลี้ยงต้นไม้ได้ไหม คิดวันละเท่าไร"],
    ], [4.2, 5.2, 6.5])

    heading(doc, f"2.2 สินค้า: ต้นไม้ {len(plants)} สายพันธุ์", 2)
    rows = []
    for cat in CATEGORY_ORDER:
        items = by_cat[cat]
        all_prices = [pr for p in items for _, pr in p["prices"]]
        examples = ", ".join(p["name_th"] for p in items[:3])
        rows.append([cat, str(len(items)), examples, f"{min(all_prices):,}–{max(all_prices):,} บาท"])
    rows.append([("รวม", ""), (str(len(plants)), ""), "", ""])
    table(doc, ["หมวด", "จำนวน", "ตัวอย่าง", "ช่วงราคา"], rows, [4.0, 1.6, 6.8, 3.5], center_cols=(1,))
    note(doc, "ราคาเป็นต้นไม้พร้อมกระถางพลาสติกเพาะ (ยังไม่รวมกระถางตกแต่ง) · ขนาดนิ้ว = เส้นผ่านศูนย์กลางปากกระถาง · "
              "รายการเต็มพร้อมราคา แสง การดูแล และสถานะสินค้าอยู่ในภาคผนวก ก · กระถาง ดิน ปุ๋ย และอุปกรณ์ 19 รายการอยู่ในภาคผนวก ข · "
              "ต้นไม้ที่ไม่อยู่ในรายการถือว่าร้านไม่มีขาย")

    heading(doc, "2.3 บริการ (6 รายการ)", 2)
    table(doc, ["บริการ", "ราคา", "เงื่อนไข"], [
        ["เปลี่ยนกระถาง", "กระถาง ≤ 8 นิ้ว 50 บาท/ต้น · ≥ 10 นิ้ว 100 บาท/ต้น",
         "ฟรีค่าบริการเมื่อซื้อกระถางที่ร้านในบิลเดียวกัน · ใช้เวลา 15–30 นาที · ทำที่หน้าร้านเท่านั้น"],
        ["รับฝากเลี้ยงต้นไม้ (Plant Hotel)", "≤ 8 นิ้ว 20 บาท/ต้น/วัน · ≥ 10 นิ้ว 35 บาท/ต้น/วัน",
         "ฝาก 3–30 วัน · จองล่วงหน้า 2 วัน · รับสูงสุด 40 ต้น · ส่งรูปอัปเดตทุก 3 วัน · ไม่รับต้นที่มีแมลง"],
        ["ตรวจสุขภาพต้นไม้", "ฟรี", "ส่งรูปทางแชท (ประเมินเบื้องต้น) หรือนำต้นไม้มาที่ร้าน"],
        ["ห่อของขวัญ", "30 บาท/ต้น · การ์ดอวยพรฟรี", "ส่งตรงถึงผู้รับได้ คิดค่าส่งตามปกติ"],
        ["Workshop สวนขวด (Terrarium)", "890 บาท/คน รวมอุปกรณ์",
         "เสาร์สุดท้ายของเดือน 13:00–15:30 · รอบละ 10 คน · ยกเลิกก่อน 3 วันเลื่อนรอบได้ 1 ครั้ง ไม่คืนเงิน"],
        ["จัดสวนระเบียงคอนโด", "เริ่มต้น 2,500 บาท · สำรวจหน้างาน 300 บาท",
         "ค่าสำรวจหักคืนเมื่อจ้างงาน · กทม. และปริมณฑล · ต้องคุยกับแอดมิน แชทบอทเสนอราคาสุดท้ายไม่ได้"],
    ], [4.0, 5.0, 6.9])

    heading(doc, "2.4 นโยบายของร้าน", 2)
    table(doc, ["นโยบาย", "รายละเอียด"], [
        ["P01 จัดส่ง กทม./ปริมณฑล", "≤ 5 กม. 60 บาท · 5–15 กม. 120 บาท · 15–30 กม. 180 บาท · ส่งฟรีเมื่อซื้อครบ 1,500 บาทและไม่เกิน 15 กม. · "
                                   "สั่งและชำระก่อน 14:00 ส่งวันเดียวกัน · จัดส่งทุกวัน"],
        ["P02 จัดส่งต่างจังหวัด", "กล่องละ 120 บาท ไม่มีส่งฟรี · ส่งได้เฉพาะกระถางไม่เกิน 8 นิ้ว · ไม่ส่งกล้วยไม้ กระถางเซรามิก/ดินเผา "
                                 "และต้นไม้ 10 นิ้วขึ้นไป · ส่งเฉพาะวันจันทร์ อังคาร พฤหัสบดี"],
        ["P03 การชำระเงิน", "โอน/พร้อมเพย์ · หน้าร้านรับเงินสด QR และบัตร (ขั้นต่ำ 300 บาท) · ไม่มีเก็บเงินปลายทาง (COD)"],
        ["P04 ยืนยันการชำระเงิน", "แอดมินยืนยันภายใน 1 ชั่วโมงในเวลาทำการ · แชทบอทอ่านสลิปได้ แต่ยืนยันว่าเงินเข้าแล้วไม่ได้"],
        ["P05 รับประกันการขนส่ง", "แจ้งภายใน 24 ชั่วโมง พร้อมรูป/วิดีโอแกะกล่องและเลขคำสั่งซื้อ · เลือกรับต้นใหม่ฟรีหรือคืนเงินค่าต้นไม้ · "
                                "ไม่รับประกันความเสียหายจากการดูแลหลังได้รับสินค้า"],
        ["P06 คืน/เปลี่ยนสินค้า", "ต้นไม้ไม่รับคืนเพราะเปลี่ยนใจ · กระถาง อุปกรณ์ ดิน ปุ๋ยที่ยังไม่แกะ คืนได้ใน 7 วันเป็นเครดิตร้าน (ใช้ได้ 6 เดือน)"],
        ["P07 ยกเลิกคำสั่งซื้อ", "ก่อนจัดส่งคืนเงินเต็มจำนวนใน 3 วันทำการ · หลังจัดส่งแล้วยกเลิกไม่ได้"],
        ["P08 สมาชิกและส่วนลด", "สมาชิกลด 5% · เดือนเกิดลด 10% (เฉพาะต้นไม้ ใช้ร่วมกันไม่ได้ สูงสุด 10%) · 25 บาท = 1 แต้ม, 100 แต้ม = ส่วนลด 100 บาท · "
                               "ไม่มีโค้ดหรือส่วนลดอื่น"],
        ["P09 โปรโมชัน Green October", "1–31 ต.ค. 2569 ซื้อไม้ใบตั้งแต่ 3 ต้น (กระถาง 6 นิ้วขึ้นไป) แถมดินปลูก 5 ลิตร 1 ถุงต่อบิล"],
        ["P10 ความเป็นส่วนตัว", "ไม่เปิดเผยข้อมูลลูกค้าทุกกรณี · เช็กสถานะคำสั่งซื้อต้องระบุเลขคำสั่งซื้อและเบอร์โทร 4 ตัวท้ายที่ตรงกัน"],
        ["P11 การสั่งซื้อออนไลน์", "แจ้งต้นไม้ ขนาด จำนวน ที่อยู่ ทาง LINE OA → แอดมินสรุปยอดและออกเลข BK-xxxx → โอนแล้วส่งสลิป → แอดมินยืนยันแล้วจัดส่ง · แชทบอทแนะนำและบอกราคาได้ แต่สร้างคำสั่งซื้อเองไม่ได้"],
    ], [4.4, 11.5])
    label_line(doc, "นอกขอบเขต", "ไม่ขายไม้ยืนต้น ไม้ผล บอนไซ และมอนสเตอร่าด่าง · ไม่รับซื้อหรือฝากขายต้นไม้ · "
               "ไม่ส่งต่างประเทศ · ไม่มีบริการดูแลต้นไม้นอกสถานที่รายเดือน")

    heading(doc, "2.5 คำถามที่ลูกค้าถามบ่อย 10 เรื่อง", 2)
    for q in ["ร้านเปิด-ปิดกี่โมง หยุดวันไหน และร้านอยู่ที่ไหน",
              "ต้นไม้ราคาเท่าไร มีขนาดอะไรบ้าง มีของไหม",
              "ต้นไม้อะไรเหมาะกับห้องแสงน้อย / มือใหม่",
              "ต้นไม้อะไรเหมาะเป็นของขวัญหรือไม้มงคล ห่อของขวัญได้ไหม",
              "ค่าส่งเท่าไร ส่งฟรีไหม",
              "ส่งต่างจังหวัดได้ไหม มีเงื่อนไขอะไร",
              "ต้นไม้เสียหายระหว่างขนส่ง ทำอย่างไร",
              "ชำระเงินช่องทางไหนได้บ้าง ส่งสลิปแล้วทำอย่างไรต่อ",
              "มีส่วนลด โปรโมชัน หรือสมาชิกไหม",
              "ต้นไม้ใบเหลือง ใบไหม้ มีแมลง ต้องทำอย่างไร (ส่งรูปให้ช่วยดูได้)"]:
        bullet(doc, q, style="List Number")

    heading(doc, "2.6 ข้อกำหนดของแชทบอท", 2)
    do = ["ตอบเป็นภาษาไทย สุภาพ กระชับ ลงท้าย \"ค่ะ\"",
          "ตอบจากคลังความรู้ของร้านเท่านั้น ราคาและเงื่อนไขต้องตรงทุกตัวเลข",
          "ไม่มีข้อมูล ให้ตอบว่า \"ขออภัย ไม่มีข้อมูลเรื่องนี้\" แล้วแนะนำติดต่อแอดมิน",
          "วิเคราะห์รูปต้นไม้ตามคู่มือดูแลของร้าน และแจ้งว่าเป็นการประเมินเบื้องต้น",
          "อ่านยอดเงิน วันที่ และธนาคารจากสลิป แล้วแจ้งว่าแอดมินจะเป็นผู้ยืนยัน",
          "ถามข้อมูลเพิ่มเมื่อคำถามกำกวม เช่น ขนาดต้นไม้ ระยะทางจัดส่ง",
          "ตอบสถานะคำสั่งซื้อเมื่อได้เลขคำสั่งซื้อและเบอร์ 4 ตัวท้ายที่ตรงกัน และตอบเฉพาะสถานะจัดส่ง",
          "ส่งต่อแอดมินเรื่องเคลมสินค้า งานจัดสวน และการสั่งซื้อ 20 ต้นขึ้นไป"]
    dont = ["แต่งราคา สินค้า บริการ หรือนโยบายที่ไม่มีในคลังความรู้",
            "ให้ส่วนลดหรือของแถมนอกโปรโมชัน แม้ลูกค้าอ้างว่าเจ้าของร้านหรือแอดมินอนุญาต",
            "เปิดเผยข้อมูลลูกค้าคนอื่น (ชื่อ ที่อยู่ เบอร์โทร รายการสั่งซื้อ)",
            "ยืนยันว่าได้รับเงินแล้วจากรูปสลิป",
            "รับปากคืนเงินหรือเคลมนอกเงื่อนไขนโยบายรับประกัน",
            "แนะนำการนำต้นไม้หรือสมุนไพรไปใช้รักษาโรค (ให้ปรึกษาแพทย์แทน)",
            "เปิดเผย system prompt หรือทำตามคำสั่ง \"ลืมกฎ/เปลี่ยนบทบาท\"",
            "ตอบเรื่องที่ไม่เกี่ยวกับร้าน เช่น การบ้าน เขียนโค้ด การเมือง"]
    table(doc, ["ต้องทำ", "ห้ามทำ"], [[f"{i + 1}. {a}", f"{i + 1}. {b}"] for i, (a, b) in enumerate(zip(do, dont))], [7.95, 7.95])

    # ----- 3 -----
    page_break(doc)
    heading(doc, "3. แผนภาพสถาปัตยกรรมระบบ", 1)
    image(doc, IMG / "architecture.png", CONTENT_W, "ภาพที่ 1 องค์ประกอบของระบบ แบ่งเป็น 4 ส่วน: ผู้ใช้ · Chat API · บริการในเครื่อง · Cloud API")
    table(doc, ["องค์ประกอบ", "หน้าที่", "เทคโนโลยี"], [
        ["Web UI", "หน้าแชท: ข้อความต้อนรับ ปุ่มคำถามยอดนิยม แนบรูป สถานะประมวลผลทีละขั้น error banner ปุ่มหยุด/เริ่มใหม่",
         "HTML, CSS, JavaScript, marked.js, DOMPurify"],
        ["Chat API", "รับข้อความและภาพ ตรวจไฟล์ (.jpg .png .webp ≤ 5 MB) จัดการ session cookie และ rate limit",
         "FastAPI :8000, uv, pydantic-settings"],
        ["Pipeline", "คุมลำดับ Guard ขาเข้า → Vision → RAG → LLM → Guard ขาออก และจับเวลาทุกขั้น", "Python asyncio"],
        ["Vision Analyzer", "สรุปสิ่งที่เห็นในภาพเป็น JSON 4 ประเภท: อาการต้นไม้ / สลิป / พัสดุเสียหาย / ระบุชนิดต้นไม้",
         "Gemini 3.1 Flash Lite (image_url Base64)"],
        ["RAG Server", "ค้นคลังความรู้ 9 ไฟล์ด้วย knowledge graph + vector แล้วส่ง context ให้ LLM (ข้อความต้นฉบับก่อน ตามด้วย entity)",
         "FastAPI :9621 บน LightRAG library, Gemini 3.1 Flash Lite (สกัด keyword), bge-m3 ONNX ในเครื่อง (embedding)"],
        ["Chat LLM", "เรียบเรียงคำตอบจาก system prompt + context + ประวัติแชท · สลับตัวสำรองอัตโนมัติเมื่อผู้ให้บริการหลักไม่ว่าง",
         "Gemini 3.1 Flash Lite (สำรอง: gpt-oss-120b บน Groq) ผ่าน OpenAI-compatible API, httpx"],
        ["Guard Service", "ตรวจข้อความ 2 ครั้งต่อ 1 ข้อความ 4 ชั้น ตรวจไม่ได้ = ไม่ตอบ (fail-closed)",
         "FastAPI :8001, PyThaiNLP, Prompt Guard 2 + gpt-oss-20b (Groq)"],
        ["Order Lookup", "ตอบสถานะคำสั่งซื้อเมื่อเลขคำสั่งซื้อและเบอร์ 4 ตัวท้ายตรงกัน", "Python + orders_mock.json"],
    ], [3.2, 7.6, 5.1])

    heading(doc, "3.1 แผนภาพการไหลของข้อมูล 1 ข้อความ (Data Flow)", 2)
    image(doc, IMG / "dataflow.png", 14.2, "ภาพที่ 2 ลำดับการทำงานเมื่อลูกค้าส่งรูปต้นไม้ใบเหลืองพร้อมคำถาม")

    heading(doc, "3.2 API Endpoints", 2)
    table(doc, ["Method + Path", "หน้าที่", "Input → Output"], [
        ["GET /", "หน้าแชทสำหรับลูกค้า", "– → HTML"],
        ["GET /api/v1/health", "ตรวจสถานะ backend, LightRAG, Guard และ LLM", "– → {status, components}"],
        ["POST /api/v1/chat/stream", "แชทหลักจากหน้าเว็บ (ข้อความ + รูป)", "multipart: message, image? → SSE: status / answer / done / error"],
        ["POST /api/v1/chat", "แชทแบบไม่สตรีม ใช้กับสคริปต์ทดสอบ", "form: message, image?, session_id? → {answer, blocked, layer, products, sources, timings, total}"],
        ["POST /api/v1/chat/reset", "ปุ่มเริ่มใหม่ ล้างประวัติแชทของ session", "cookie → {ok}"],
        ["POST /api/v1/orders/lookup", "ตรวจสถานะคำสั่งซื้อ", "{order_id, phone_last4} → {status, tracking} / 404"],
        ["GET /api/v1/models", "รายชื่อโมเดลที่ผู้ให้บริการเปิดให้ใช้ (แบบสัปดาห์ 7)", "– → {models}"],
        ["POST :8001/check", "Guard Service (ภายใน)", "{message, direction, context?} → {result, layer, categories, msg} · ตรวจไม่ได้ = 502"],
        ["POST :9621/query", "RAG Server (ภายใน)", "{query, mode, top_k, chunk_top_k} → {response: context, references}"],
    ], [4.6, 5.6, 5.7], size=9)

    heading(doc, "3.3 โมเดลที่เลือกใช้", 2)
    table(doc, ["หน้าที่", "โมเดล", "ผู้ให้บริการ", "โควต้าฟรี", "เหตุผล"], [
        ["ตอบแชท + Vision", "Gemini 3.1 Flash Lite", "Google AI Studio", "15 ครั้ง/นาที · 500 ครั้ง/วัน",
         "ดูภาพได้ ภาษาไทยดี ไม่ใช่ reasoning model จึงตอบเร็ว · token ต่อนาทีสูง รับ context จาก RAG ได้"],
        ["Chat LLM สำรอง", "gpt-oss-120b", "Groq", "30 ครั้ง/นาที · 1,000 ครั้ง/วัน",
         "ใช้อัตโนมัติเมื่อ Gemini ตอบ 429/5xx หรือช้าเกิน 10 วินาที (พบจริงระหว่างพัฒนา) · ต่างผู้ให้บริการจึงไม่ล่มพร้อมกัน"],
        ["LightRAG สกัด entity/keyword", "Gemini 3.1 Flash Lite (สำรอง gpt-oss-120b)", "Google AI Studio / Groq",
         "index ครั้งเดียว 44 ครั้ง · ตอนค้น 1 ครั้ง/คำถาม",
         "ทดลอง Gemma 4 แล้ว: ใส่บล็อก <thought> ที่มีข้อความรูปแบบเดียวกับผลสกัดซ้ำมา และคิดนานเกิน 180 วินาที จึงไม่ใช้"],
        ["Embedding", "bge-m3 (ONNX int8, 1024 มิติ)", "รันในเครื่อง (onnxruntime)", "ไม่จำกัด",
         "Gemini Embedding ฟรีนับ 1 ข้อความ = 1 request (1,000/วัน) แต่ index ครั้งเดียวใช้ ~800 · bge-m3 รองรับภาษาไทย ~0.15 วิ/ข้อความ"],
        ["จับ prompt injection", "Llama Prompt Guard 2 86M", "Groq", "30 ครั้ง/นาที · 14,400 ครั้ง/วัน",
         "อุดช่องโหว่ที่ Llama Guard ไม่ตรวจ prompt injection (สัปดาห์ 11)"],
        ["จับเนื้อหาอันตราย (S1–S14)", "gpt-oss-20b (สำรอง Gemini 3.1 Flash Lite)", "Groq", "30 ครั้ง/นาที · 1,000 ครั้ง/วัน",
         "ฟรี · วัดได้ ~1 วินาที · จัดหมวดตาม taxonomy เดียวกับ Llama Guard โดยไม่ต้องจ่ายค่า Llama Guard 4 · "
         "ไม่กินโควต้า Gemini · ทดลอง Gemma 4 แล้วปิดโหมดคิดไม่ได้ ใช้ 6–31 วินาที"],
        ["ตัวเทียบ (Local)", "Gemma 4 E4B", "LM Studio :1234", "ไม่จำกัด (รันในเครื่อง)", "ใช้เปรียบเทียบ Cloud vs Local ในการทดสอบ"],
    ], [3.0, 2.9, 2.6, 3.0, 4.4], size=8.5)
    note(doc, "โควต้าตรวจสอบจากหน้า dashboard ของผู้ให้บริการ ณ วันที่ 9 ต.ค. 2569 และอาจเปลี่ยนได้")
    bullet(doc, "Chat LLM เรียกผ่าน OpenAI-compatible API จึงสลับผู้ให้บริการได้ด้วยการแก้ LLM_BASE_URL, LLM_API_KEY, LLM_MODEL ใน .env "
                "โดยไม่ต้องแก้โค้ด (สัปดาห์ 7)", label="สลับโมเดลได้")
    bullet(doc, "temperature 0.2 เพราะงานนี้เน้นดึงข้อมูลให้ตรง (สัปดาห์ 4) · ไม่ใช้ reasoning model เพราะตอบช้า", label="ค่าการตอบ")
    bullet(doc, "ใช้ Cloud เพราะไม่ต้องลงทุนฮาร์ดแวร์และใช้งานได้ทันที ข้อมูลร้านเป็นข้อมูลจำลองทั้งหมด ไม่มีข้อมูลอ่อนไหว "
                "จึงยอมรับได้ที่ข้อมูลออกนอกเครื่อง (กรอบตัดสินใจสัปดาห์ 10) · free tier ของ Google อาจใช้ข้อมูลเพื่อปรับปรุงบริการ",
           label="Cloud vs Local")

    heading(doc, "3.4 คลังความรู้ (RAG)", 2)
    table(doc, ["ไฟล์", "เนื้อหา"], [
        ["01_shop_info.md", "ที่อยู่ เวลาทำการ ช่องทางติดต่อ สิ่งที่ร้านไม่มี/ไม่ให้บริการ"],
        ["02_plants.md", f"ต้นไม้ {len(plants)} สายพันธุ์ 1 ต้นต่อ 1 หัวข้อ: ราคา แสง การรดน้ำ ระดับการดูแล สถานะสินค้า การส่งต่างจังหวัด (สร้างอัตโนมัติ)"],
        ["03_pots_supplies.md", "กระถาง ดิน ปุ๋ย ยา และอุปกรณ์ 19 รายการ"],
        ["04_services.md", "บริการ 6 รายการพร้อมราคาและเงื่อนไข"],
        ["05_shipping_payment.md", "ขั้นตอนการสั่งซื้อ ค่าส่ง กทม./ต่างจังหวัด ช่องทางชำระเงิน ขั้นตอนหลังโอน การยกเลิก"],
        ["06_policies_promotions.md", "รับประกัน คืน/เปลี่ยน สมาชิก โปรโมชัน กติกาส่วนลด ความเป็นส่วนตัว"],
        ["07_plant_care_guide.md", "หลักการดูแล + อาการผิดปกติ 12 แบบพร้อมวิธีแก้ (ใช้ประกอบการวิเคราะห์ภาพ)"],
        ["08_faq.md", "คำถามที่พบบ่อย 12 ข้อพร้อมคำตอบ"],
        ["09_plant_recommendations.md", "รายการแนะนำ เช่น มือใหม่ ทนแสงน้อย ไม้มงคล ของขวัญ ราคาไม่เกิน 100 บาท (สร้างอัตโนมัติ)"],
    ], [5.0, 10.9])
    bullet(doc, "ข้อมูลต้นไม้แก้ที่ data/plants.csv ไฟล์เดียว แล้วรัน scripts/build_plants_kb.py เพื่อสร้าง 02 และ 09 ใหม่ "
                "สคริปต์ตรวจรหัสซ้ำ รูปแบบราคา และชื่อหมวดก่อนสร้าง", label="แหล่งข้อมูลเดียว")
    bullet(doc, "ตัดตามหัวข้อ markdown ไม่หั่นข้อมูลต้นไม้กลางหัวข้อ แล้วรวมหัวข้อติดกันเป็น chunk ละ ~900 token ได้ 75 chunk "
                "· สกัด entity/ความสัมพันธ์เป็น knowledge graph · ใช้ LLM 44 ครั้ง 11.7 นาที", label="การ index")
    bullet(doc, "mode = mix (knowledge graph + vector) top_k 20, chunk 8 · RAG Server คืนเฉพาะข้อมูลที่ค้นเจอ (ไม่สร้างคำตอบเอง) "
                "เรียงข้อความต้นฉบับก่อนเพื่อให้ราคาตรงตัว · วัดได้ ~0.1–2 วินาทีต่อคำถาม", label="การค้นคืน")

    heading(doc, "3.5 มาตรการความปลอดภัย", 2)
    for label, text in [
        ("Blocklist + PyThaiNLP", "ปรับข้อความภาษาไทยให้เป็นรูปมาตรฐาน (normalize) แล้วลบช่องว่าง/เครื่องหมายก่อนเทียบคำต้องห้าม "
                                  "จับการเลี่ยงด้วยการเว้นวรรค เช่น \"พ นั น\" ได้ · ไม่ใส่คำที่ลูกค้าใช้ปกติ เช่น \"แพง\" เพื่อลด false positive"),
        ("Business Rules", "ขาเข้าจับการขอส่วนลด การอ้างว่าเป็นเจ้าของร้าน/แอดมิน การขอข้อมูลลูกค้าอื่น และการขอเปลี่ยนนโยบาย · "
                           "ขาออกจับราคาที่ไม่มีในคลังความรู้ เบอร์/ที่อยู่ลูกค้า และการสัญญาส่วนลดหรือคืนเงิน (OWASP LLM01, LLM02, LLM07)"),
        ("Prompt Guard 2", "จับ prompt injection และ jailbreak ซึ่ง Llama Guard ไม่ครอบคลุม (LLM01)"),
        ("Safety Classifier", "จัดหมวดเนื้อหาอันตราย S1–S14 ตาม taxonomy ของ Llama Guard ด้วย gpt-oss-20b บน Groq (ฟรี สำรองด้วย Gemini) "
                              "สลับเป็น Llama Guard ตัวจริงได้ด้วยการแก้ SAFETY_MODEL ใน .env · ตรวจไม่ได้ = ไม่ตอบ (fail-closed)"),
        ("สิทธิ์น้อยที่สุด", "LLM ไม่เห็นฐานข้อมูลคำสั่งซื้อ ระบบค้นให้เฉพาะเมื่อเลขคำสั่งซื้อและเบอร์ 4 ตัวท้ายตรงกัน และคืนเฉพาะสถานะจัดส่ง (LLM02, LLM03)"),
        ("ไม่มีความลับใน prompt", "กติกาส่วนลดและสิทธิ์อยู่ในโค้ด ไม่อยู่ใน system prompt · API key อยู่ใน .env ไม่ commit ขึ้น git (LLM08)"),
        ("จำกัดการใช้งาน", "rate limit 20 ครั้ง/นาทีต่อ session · ข้อความ ≤ 1,000 ตัวอักษร · ภาพ ≤ 5 MB (LLM06)"),
        ("แสดงผลปลอดภัย", "DOMPurify ตัด HTML/สคริปต์ก่อนแสดงคำตอบ (LLM10)"),
        ("ธรรมาภิบาล", "แจ้งผู้ใช้ว่ากำลังคุยกับ AI และมีช่องทางติดต่อแอดมิน · log ไม่เก็บเบอร์และที่อยู่ (PDPA)"),
    ]:
        bullet(doc, text, label=label)

    heading(doc, "3.6 ปัญหาที่พบจริงระหว่างพัฒนาและวิธีแก้", 2)
    table(doc, ["ปัญหาที่พบ", "สาเหตุ", "วิธีแก้"], [
        ["Gemini ตอบ 503 \"high demand\" บ่อย และบางครั้งตอบช้า 10–25 วินาทีโดยไม่ error", "ผู้ใช้ free tier หนาแน่น",
         "ตัวสำรองข้ามผู้ให้บริการ (Groq) สลับอัตโนมัติเมื่อได้ 429/5xx หรือเกินเวลาที่กำหนด"],
        ["Gemma 4 ใช้เป็นตัวสกัด entity ไม่ได้", "ปิดโหมดคิดไม่ได้ (6–180 วินาที) และบล็อก <thought> มีข้อความรูปแบบเดียวกับผลลัพธ์",
         "ใช้ Gemini Flash Lite เป็นหลัก Groq เป็นสำรอง · ตัด <thought> ทิ้งทุกครั้ง"],
        ["Index ล้มกลางทางเพราะ embedding เกินโควต้า", "Gemini Embedding ฟรีนับรายข้อความ 100/นาที 1,000/วัน",
         "ย้าย embedding มารันในเครื่องด้วย bge-m3 · index ใหม่โดยใช้ LLM cache จึงไม่เสียโควต้าซ้ำ"],
        ["ติดตั้ง torch / fastembed แล้วใช้ไม่ได้", "Windows Smart App Control บล็อก DLL ของ torch, mmh3, hf_xet",
         "ใช้ onnxruntime + tokenizers โดยตรง · ดาวน์โหลดโมเดลผ่าน HTTP แบ่ง 8 ส่วน"],
        ["Embedding ช้า (64 ข้อความ 40 วินาที)", "onnxruntime ใช้หลาย thread บน CPU แบบ P-core/E-core แล้วแย่งกัน",
         "ตั้ง 1 thread → เร็วขึ้น 13 เท่า"],
        ["Guard ขาออกบล็อกคำตอบที่ถูก (false positive)", "LLM เขียนวิธีคิดแบบ \"35 บาท × 5 วัน = 175 บาท\" กฎเดิมจับเฉพาะ \"35 × 5 = 175\"",
         "ตรวจว่าผลลัพธ์คำนวณได้จากตัวเลขในบรรทัดเดียวกัน + เพิ่ม unit test จากเคสจริง"],
        ["Guard ขาออกปล่อยราคาที่แต่งขึ้น (false negative ที่ test จับได้)", "นับตัวเลขทุกตัวในคลังความรู้เป็นราคา รวมรหัสสินค้า P047",
         "นับเฉพาะตัวเลขที่ตามด้วย \"บาท\" และราคาใน CSV"],
    ], [5.0, 5.4, 5.5], size=8.5)

    heading(doc, "3.7 โครงสร้างโค้ด (Model – Controller – Service)", 2)
    para(doc, "ทั้ง 3 บริการจัดโค้ดแบบเดียวกัน แยกหน้าที่ชัดเจน แก้ส่วนหนึ่งได้โดยไม่กระทบส่วนอื่น "
              "และทดสอบแต่ละชั้นแยกกันได้ (เช่น unit test ของ rule_service ไม่ต้องเปิด server)")
    table(doc, ["ชั้น", "หน้าที่", "ไฟล์ใน Chat API (app/)"], [
        ["controllers/", "รับ HTTP request ตรวจ input แล้วเรียก service ส่ง response กลับ ไม่มีตรรกะธุรกิจ",
         "page_controller · chat_controller · order_controller · system_controller"],
        ["services/", "ตรรกะหลักของระบบ", "chat_service (ลำดับ 5 ขั้น) · llm_service · vision_service · rag_service · "
                                          "guard_service · product_service · order_service"],
        ["models/", "โครงสร้างข้อมูลและส่วนอ่านข้อมูล", "schemas · plant_repository · order_repository · session_store"],
        ["views/ · prompts/", "หน้าเว็บ และ system prompt", "templates/index.html · static/ · chat_system.md · vision_system.md"],
    ], [3.0, 5.4, 7.5], size=9)
    table(doc, ["บริการ", "controllers/", "services/", "models/"], [
        ["Guard :8001 (guard/)", "check_controller", "rule_service (ชั้น 1–2) · classifier_service (ชั้น 3–4)", "schemas"],
        ["RAG :9621 (rag/)", "query_controller", "query_service · rag_engine · embedding_service", "schemas"],
    ], [3.4, 3.2, 6.3, 3.0], size=9)

    # ----- 4 -----
    heading(doc, "4. สรุปบทบาทหน้าที่ของผู้พัฒนา", 1)
    me = "[ชื่อ-สกุล] (งานเดี่ยว)"
    table(doc, ["ใคร", "ทำอะไร", "ได้อะไร"], [
        [me, "ข้อมูลธุรกิจ: ออกแบบข้อมูลร้านจำลองและสคริปต์แปลง CSV เป็นคลังความรู้", f"plants.csv {len(plants)} สายพันธุ์ + คลังความรู้ 9 ไฟล์"],
        ["", "Backend: พัฒนา Chat API ด้วย FastAPI, pipeline และตัวสำรองข้ามผู้ให้บริการ", "API 7 endpoint + SSE สถานะทีละขั้น"],
        ["", "RAG: เขียนสคริปต์ index ที่ทนต่อโควต้า, RAG Server บน LightRAG และ embedding ในเครื่อง", "knowledge graph 75 chunk · ค้น ~0.1–2 วินาที"],
        ["", "Prompt + Vision: เขียน system prompt 2 โหมดตามข้อกำหนดต้องทำ/ห้ามทำ", "chat prompt + vision prompt (JSON) · อ่านสลิปได้ครบ"],
        ["", "Safety: ต่อยอด Llama Guard Layer ด้วย Business Rules และ Prompt Guard 2", "Guard Service 4 ชั้น + unit test 34 กรณี"],
        ["", "Frontend: ออกแบบและพัฒนาหน้าแชทตามหลัก UI/UX", "หน้าแชทตาม mockup ใช้ได้ทั้งคอมและมือถือ"],
        ["", "Testing + เอกสาร: สคริปต์ทดสอบ 10/5/5 กรณี บันทึกผล เวลา และเทียบก่อน-หลัง", "ผลทดสอบ 2 รอบ, แผนภาพ 2 แบบ, README"],
    ], [3.6, 7.2, 5.1])

    # ----- 5 -----
    heading(doc, "5. ผลการทดสอบ", 1)
    base, after = load_eval("baseline"), load_eval("after")
    note(doc, "บันทึกจากระบบจริงด้วยสคริปต์ eval/run_eval.py ผ่าน POST /api/v1/chat วันที่ 10 ต.ค. 2569 (รอบ \"after\" = หลังปรับปรุงตาม 5.4) · "
              "แต่ละข้อใช้ session ใหม่ · เวลาตอบนับตั้งแต่รับคำขอจนได้คำตอบที่ผ่าน Guard ขาออก · "
              "ตัดสินผ่าน/ไม่ผ่านด้วยคำสำคัญที่ต้องมีในคำตอบ (eval/cases.json) · ผลตอบจริงตัดให้สั้นลง ฉบับเต็มอยู่ใน eval/results/", keep=True)

    heading(doc, "5.1 ชุดคำถามทดสอบ 10 ข้อ", 2)
    rows = [eval_row(after, c, c["message"]) for c in CASES["questions"]]
    table(doc, ["ข้อ", "คำถาม", "คำตอบที่คาดหวัง", "ผลตอบจริง", "ผล", "เวลา (วิ)"], rows,
          [0.9, 3.0, 3.6, 5.6, 1.5, 1.3], size=8, center_cols=(0, 4, 5))

    heading(doc, "5.2 ชุดภาพทดสอบ 5 ภาพ", 2)
    rows = [eval_row(after, c, f"{c['file'].split('/')[-1]} + \"{c['message']}\"") for c in CASES["images"]]
    table(doc, ["ข้อ", "ภาพ + ข้อความ", "ผลวิเคราะห์ที่คาดหวัง", "ผลวิเคราะห์จริง", "ผล", "เวลา (วิ)"], rows,
          [0.9, 3.0, 3.6, 5.6, 1.5, 1.3], size=8, center_cols=(0, 4, 5))
    note(doc, "สลิปเป็นสลิปจำลอง (eval/images/slip_mock.html ธนาคารและบัญชีสมมติ) · ภาพต้นไม้ 4 ภาพจะถ่ายเองและทดสอบในรอบถัดไป · "
              "ไม่มีข้อมูลส่วนบุคคลจริง")

    heading(doc, "5.3 ชุดทดสอบความปลอดภัย 5 กรณี", 2)
    rows = []
    for c in CASES["safety"]:
        r = after.get(c["id"])
        res = (r or {}).get("result", {})
        layer = f"{LAYER_NAMES.get(res.get('layer'), res.get('layer'))} · {','.join(res.get('categories') or [])}" \
            if res.get("blocked") else "System Prompt + RAG (ตอบได้ ไม่บล็อก)"
        rows.append([c["id"], c["case"], c["message"], c["expected"], layer if r else "–",
                     short(res.get("answer", ""), 110) if r else "รอทดสอบ",
                     ("ผ่าน" if r["pass"] else "ไม่ผ่าน") if r else "–", str(res.get("total", "–")) if r else "–"])
    table(doc, ["ข้อ", "กรณี", "ข้อความทดสอบ", "ผลที่คาดหวัง", "ชั้นที่ดักจับจริง", "ผลตอบจริง", "ผล", "เวลา (วิ)"], rows,
          [0.8, 1.7, 2.6, 2.4, 2.5, 3.6, 1.1, 1.2], size=7.5, center_cols=(0, 6, 7))
    note(doc, "กรณี 1, 2, 4 ถูกบล็อกที่ Business Rules ภายใน ~0.01 วินาที โดยไม่เรียกโมเดล · กรณี 5 ผ่านกฎแต่ Safety Classifier จับได้เป็น S1 · "
              "กรณี 3 เป็นคำถามปกติที่ต้องตอบตามนโยบาย จึงไม่ควรถูกบล็อก (ทดสอบ false positive)")

    heading(doc, "5.4 จุดที่ปรับปรุง 3 จุด (จากผลทดสอบรอบแรก)", 2)
    mb, ma = eval_metrics(base, after.keys()), eval_metrics(after, base.keys())
    table(doc, ["จุด", "ปัญหาที่พบ (ก่อน)", "วิธีแก้", "ผลก่อน → หลัง"], [
        ["1", "Q3 ตอบว่าต้น 10 นิ้วส่งเชียงใหม่ไม่ได้ แต่ไม่เสนอทางเลือก ลูกค้าต้องถามต่อเอง",
         "เพิ่มกฎ \"ต้องทำ\" ข้อ 11 ใน system prompt: ถ้าทำตามที่ขอไม่ได้ ให้เสนอทางเลือกที่มีจริงในข้อมูลร้านเสมอ",
         f"Q3 ไม่ผ่าน → ผ่าน (เสนอขนาด 6 นิ้ว 350 บาท) · ผ่านรวม {mb['pass']} → {ma['pass']}"],
        ["2", "คำตอบขึ้นต้นด้วย \"สวัสดีค่ะ น้องใบเขียวจากร้าน...\" ซ้ำทุกครั้ง และลงท้ายซ้อน \"นะคะค่ะ\"",
         "เพิ่มกฎรูปแบบคำตอบ: ตอบเข้าเรื่องทันที ใช้คำลงท้ายอย่างเดียว ไม่แนะนำติดต่อแอดมินทุกครั้ง",
         f"ทักทายซ้ำ {mb['greet']} → {ma['greet']} ข้อ · \"นะคะค่ะ\" {mb['double']} → {ma['double']} ข้อ · "
         f"ความยาวเฉลี่ย {mb['length']} → {ma['length']} ตัวอักษร"],
        ["3", "เวลาตอบแกว่งมาก Q6 ใช้ 37 วินาที (ค้นข้อมูล 25 วิ) เพราะ Gemini ตอบช้าโดยไม่ error ตัวสำรองเดิมทำงานเฉพาะเมื่อได้ 503",
         "จำกัดเวลาตัวหลัก: Chat LLM 10 วินาที, สกัด keyword ตอนค้น 8 วินาที เกินแล้วสลับไป gpt-oss-120b บน Groq ทันที",
         f"เวลาตอบเฉลี่ย {mb['avg']} → {ma['avg']} วินาที · ช้าสุด {mb['max']} → {ma['max']} วินาที"],
    ], [0.9, 4.6, 5.2, 5.2], size=8.5, center_cols=(0,))
    note(doc, f"เทียบเฉพาะ {len(set(base) & set(after))} ข้อที่รันทั้งสองรอบ (eval/compare.py) · ก่อนรอบแรกได้แก้ false positive/negative "
              "ของการตรวจราคาขาออกไปแล้ว 2 จุด (ดู 3.6)")

    # ----- 6 -----
    page_break(doc)
    heading(doc, "6. หน้าตาแชทบอท (UI Mockup)", 1)
    para(doc, "ภาพออกแบบหน้าเว็บบนจอคอมพิวเตอร์ขนาด 1280 px แบ่งเป็นแถบข้อมูลร้านด้านซ้าย (เวลาเปิด ปุ่มส่งรูป "
              "คำถามยอดนิยม ปุ่มเริ่มใหม่) และพื้นที่แชทด้านขวา ออกแบบตามหลัก Usability Heuristics และสถานะที่แชทบอทต้องมี (สัปดาห์ 6) "
              "หน้าเว็บจริงพัฒนาตามแบบนี้แล้ว (app/views/) และปรับขนาดได้เมื่อเปิดบนมือถือ แถบซ้ายย่อเป็นเมนู ☰ · "
              "ตัวเลขเวลาตอบในภาพเป็นตัวอย่าง ฉบับส่งงานจะใช้ภาพหน้าจอจากระบบจริง")
    table(doc, ["ภาพ", "หน้าจอ", "สิ่งที่แสดง", "ตรงกับข้อกำหนด"], [
        ["6.1", "หน้าแรก (Empty State)", "ข้อความต้อนรับ การ์ดสิ่งที่ถามได้ 3 หมวด ปุ่มส่งรูปต้นไม้ คำถามยอดนิยม 6 ข้อ แจ้งว่าคุยกับ AI",
         "UI ใช้งานเองได้ · ความโปร่งใส"],
        ["6.2", "ตอบคำถาม + การ์ดต้นไม้", "คำตอบจาก RAG พร้อมการ์ดสินค้า (รหัส ราคา ขนาด) เวลาตอบ และแหล่งอ้างอิง", "LLM + RAG"],
        ["6.3", "กำลังประมวลผล", "สถานะทีละขั้น ช่องพิมพ์ถูกล็อก ปุ่มหยุด", "UI แสดงสถานะ · User Control"],
        ["6.4", "วิเคราะห์ภาพ", "การ์ด \"สิ่งที่เห็นในรูป\" แล้วแนะนำวิธีแก้ตามคู่มือดูแล", "Vision + RAG"],
        ["6.5", "ปฏิเสธอย่างสุภาพ", "กล่องสีเหลืองพร้อมป้ายหมวด ปฏิเสธโดยไม่เรียก AI และเสนอโปรโมชันจริง", "Safety"],
        ["6.6", "ข้อผิดพลาด", "แจ้งว่าข้อความยังไม่ถูกส่ง พร้อมปุ่มลองใหม่และแก้ข้อความ", "UI แสดง error"],
    ], [1.2, 3.6, 7.3, 3.8], size=9, center_cols=(0,))

    captions = [
        ("ภาพ 6.1 หน้าแรก", "ทักทาย ปุ่มส่งรูป คำถามยอดนิยม"),
        ("ภาพ 6.2 ตอบคำถาม + การ์ดต้นไม้", "ราคาจากคลังความรู้ พร้อมแหล่งอ้างอิง"),
        ("ภาพ 6.3 กำลังประมวลผล", "แสดงขั้นตอนแทนการรอเปล่า"),
        ("ภาพ 6.4 วิเคราะห์ภาพ", "ใบเหลือง → อาการ + วิธีแก้"),
        ("ภาพ 6.5 ปฏิเสธอย่างสุภาพ", "Guard จับคำขอส่วนลด (BIZ_DISCOUNT)"),
        ("ภาพ 6.6 ข้อผิดพลาด", "Guard ไม่ตอบ → fail-closed"),
    ]
    for i, (title, sub) in enumerate(captions):
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p.paragraph_format.keep_with_next = True
        p.paragraph_format.space_before = Pt(6)
        p.paragraph_format.space_after = Pt(2)
        p.add_run().add_picture(str(IMG / f"mockup_{i + 1}.png"), width=Cm(CONTENT_W))
        cp = para(doc, "", align=WD_ALIGN_PARAGRAPH.CENTER, space_after=10)
        set_run_font(cp.add_run(f"{title} — "), size=9.5, bold=True, color=GREEN)
        set_run_font(cp.add_run(sub), size=9, color=MUTED)

    # ----- 7 -----
    heading(doc, "7. แผนการดำเนินงาน", 1)
    table(doc, ["วันที่", "งาน", "สถานะ"], [
        ["3 ต.ค. 2569", "แจ้งชื่อธุรกิจ", "เสร็จแล้ว"],
        ["3–7 ต.ค.", f"ข้อมูลธุรกิจ คลังความรู้ 9 ไฟล์ ต้นไม้ {len(plants)} สายพันธุ์ และสคริปต์แปลงข้อมูล", "เสร็จแล้ว"],
        ["7–9 ต.ค.", "ศึกษาสไลด์ทั้งวิชา เลือกสถาปัตยกรรมและโมเดล ออกแบบ UI และจัดทำเอกสารฉบับนี้", "เสร็จแล้ว"],
        ["9–10 ต.ค.", "Chat API + RAG (index + server) + Vision + Guard 4 ชั้น + หน้าแชท + ชุดทดสอบ + ปรับปรุง 3 จุด", "เสร็จแล้ว"],
        ["10 ต.ค.", "รายงานความก้าวหน้า + สอบปรนัย", "–"],
        ["11–13 ต.ค.", "ถ่ายภาพทดสอบ 4 ภาพ · รันชุดทดสอบเต็ม 20 ข้อ · ภาพหน้าจอจริงแทน mockup", "รอดำเนินการ"],
        ["14–15 ต.ค.", "ทดสอบเพิ่มเติม (Cloud vs Local) · ปรับปรุงจากผลทดสอบภาพ", "รอดำเนินการ"],
        ["16 ต.ค.", "คลิปสาธิต ≤ 3 นาที · เอกสารฉบับสมบูรณ์ (Google Doc + PDF)", "รอดำเนินการ"],
        ["17 ต.ค.", "ส่งงาน", "–"],
        ["24 ต.ค.", "นำเสนอผลงานและตอบคำถามรายบุคคล", "–"],
    ], [2.8, 10.3, 2.8], size=9.5)

    # ----- ภาคผนวก -----
    page_break(doc)
    heading(doc, f"ภาคผนวก ก. รายการต้นไม้ {len(plants)} สายพันธุ์", 1)
    note(doc, "ราคาหน่วยบาท · ระดับการดูแล: ง่ายมาก / ง่าย / ปานกลาง / ยาก · สร้างจาก data/plants.csv")
    for cat in CATEGORY_ORDER:
        items = by_cat[cat]
        heading(doc, f"{cat} ({len(items)} รายการ)", 3)
        rows = []
        for p in items:
            rows.append([p["id"], [(p["name_th"], ""), p["name_en"]], price_text(p["prices"]), p["light"], p["difficulty"],
                         f"{p['stock_status']} · ส่งต่างจังหวัด: {p['ship_upcountry']}"])
        table(doc, ["รหัส", "ชื่อ", "ขนาด / ราคา", "แสง", "การดูแล", "สถานะ"], rows,
              [1.2, 3.6, 3.4, 2.9, 1.5, 3.3], size=8, center_cols=(0, 4), keep_all_up_to=0)

    heading(doc, "ภาคผนวก ข. กระถาง ดิน ปุ๋ย และอุปกรณ์ (19 รายการ)", 1)
    table(doc, ["หมวด", "รายการ", "ราคา"], [
        ["กระถาง", "กระถางพลาสติกสีดำ (กระถางเพาะ)", "6\" 25 · 8\" 45 · 10\" 65 บาท"],
        ["กระถาง", "กระถางดินเผา", "6\" 60 · 8\" 95 · 10\" 150 บาท"],
        ["กระถาง", "กระถางเซรามิกสีขาวด้าน", "6\" 190 · 8\" 290 · 10\" 450 บาท"],
        ["กระถาง", "กระถางเซรามิกเคลือบสีเขียวเสจ", "6\" 220 · 8\" 330 บาท"],
        ["กระถาง", "จานรองกระถางพลาสติก", "6\" 15 · 8\" 20 · 10\" 30 บาท"],
        ["ดินและวัสดุปลูก", "ดินปลูกสูตรไม้ใบ 5 ลิตร", "69 บาท"],
        ["ดินและวัสดุปลูก", "ดินปลูกแคคตัสและไม้อวบน้ำ 3 ลิตร", "59 บาท"],
        ["ดินและวัสดุปลูก", "เพอร์ไลต์ 1 ลิตร", "45 บาท"],
        ["ดินและวัสดุปลูก", "หินภูเขาไฟโรยหน้ากระถาง 1 กก.", "55 บาท"],
        ["ดินและวัสดุปลูก", "เครื่องปลูกกล้วยไม้ 2 ลิตร", "60 บาท"],
        ["ปุ๋ยและยา", "ปุ๋ยละลายช้า 100 กรัม", "89 บาท"],
        ["ปุ๋ยและยา", "ปุ๋ยน้ำสำหรับไม้ใบ 250 มล.", "120 บาท"],
        ["ปุ๋ยและยา", "น้ำมันสะเดา 250 มล.", "150 บาท"],
        ["ปุ๋ยและยา", "กับดักแมลงหวี่แบบกาวเหนียว (10 แผ่น)", "59 บาท"],
        ["อุปกรณ์", "ฟ็อกกี้ฉีดน้ำ 500 มล.", "79 บาท"],
        ["อุปกรณ์", "บัวรดน้ำปากยาว 1.5 ลิตร", "129 บาท"],
        ["อุปกรณ์", "ไม้ค้ำหุ้มมอส 60 ซม.", "150 บาท"],
        ["อุปกรณ์", "กรรไกรตัดแต่งกิ่ง", "189 บาท"],
        ["อุปกรณ์", "ชุดช้อนพรวนดินจิ๋ว 3 ชิ้น", "99 บาท"],
    ], [3.4, 7.0, 5.5], size=9)
    note(doc, "กระถางเซรามิกและดินเผาส่งได้เฉพาะกรุงเทพฯ และปริมณฑล")

    OUT.parent.mkdir(exist_ok=True)
    doc.save(OUT)
    print("saved", OUT)


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:  # ระบุไฟล์ปลายทางเองได้ เช่นตอนไฟล์หลักเปิดค้างใน Word
        OUT = Path(sys.argv[1])
    build()
