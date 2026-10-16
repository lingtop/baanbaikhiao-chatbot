"""รันชุดทดสอบ 10 คำถาม / 5 ภาพ / 5 กรณีความปลอดภัย ผ่าน POST /api/v1/chat แล้วบันทึกผล

ใช้งาน (เปิดระบบทั้ง 3 บริการก่อน):
    uv run python eval/run_eval.py                 # รันทั้งหมด
    uv run python eval/run_eval.py --only Q1,S4    # รันบางข้อ
    uv run python eval/run_eval.py --tag before    # ตั้งชื่อรอบ ใช้เทียบก่อน-หลังปรับปรุง

ผลลัพธ์: eval/results/<เวลา>_<tag>.json และ .md (ตารางพร้อมวางในรายงาน)
แต่ละข้อใช้ session ใหม่ เพื่อไม่ให้ประวัติแชทของข้อก่อนหน้ามีผล
เว้นช่วงระหว่างข้อ เพราะโควต้าฟรีของ Gemini 3.1 Flash Lite = 15 ครั้ง/นาที
"""

import argparse
import json
import mimetypes
import secrets
import time
from datetime import datetime
from pathlib import Path

import httpx

HERE = Path(__file__).resolve().parent
API = "http://127.0.0.1:8000/api/v1/chat"
PAUSE_SEC = 12


def judge(check: dict, res: dict) -> tuple[bool, str]:
    if "error" in res:
        return False, f"error: {res['error']}"
    answer = res.get("answer") or ""
    reasons = []
    if "blocked" in check and bool(res.get("blocked")) != check["blocked"]:
        reasons.append(f"blocked={res.get('blocked')} (คาดหวัง {check['blocked']})")
    for w in check.get("all", []):
        if w not in answer:
            reasons.append(f"ไม่มี '{w}'")
    for group in check.get("any", []):
        if not any(w in answer for w in group):
            reasons.append(f"ไม่มีคำใดใน {group}")
    for w in check.get("none", []):
        if w in answer:
            reasons.append(f"มี '{w}' ซึ่งไม่ควรมี")
    return not reasons, "; ".join(reasons)


def run_case(client: httpx.Client, message: str, image: Path | None) -> dict:
    data = {"message": message, "session_id": "eval-" + secrets.token_hex(6)}
    files = None
    if image:
        mime = mimetypes.guess_type(image.name)[0] or "image/jpeg"
        files = {"image": (image.name, image.read_bytes(), mime)}
    t = time.perf_counter()
    r = client.post(API, data=data, files=files, timeout=180)
    wall = round(time.perf_counter() - t, 2)
    try:
        body = r.json()
    except ValueError:
        body = {"error": f"HTTP {r.status_code}"}
    if r.status_code != 200:
        body = {"error": body.get("message") or body.get("detail") or f"HTTP {r.status_code}"}
    body["wall_time"] = wall
    return body


def md_cell(s: str) -> str:
    return (s or "").replace("|", "\\|").replace("\n", " ").strip()


def write_markdown(results: list[dict], path: Path):
    lines = [f"# ผลการทดสอบ ({path.stem})", ""]
    for group, title, cols in [("questions", "ชุดคำถามทดสอบ 10 ข้อ", "คำถาม"),
                               ("images", "ชุดภาพทดสอบ 5 ภาพ", "ภาพ"),
                               ("safety", "ชุดทดสอบความปลอดภัย 5 กรณี", "ข้อความทดสอบ")]:
        rows = [r for r in results if r["group"] == group]
        if not rows:
            continue
        done = [r for r in rows if not r.get("skipped")]
        lines += [f"## {title} — ผ่าน {sum(r['pass'] for r in done)}/{len(rows)}", "",
                  f"| ข้อ | {cols} | คาดหวัง | ผลตอบจริง | ผ่าน/ไม่ผ่าน | เวลา (วิ) |", "|---|---|---|---|---|---|"]
        for r in rows:
            if r.get("skipped"):
                lines.append(f"| {r['id']} | {md_cell(r.get('file') or r['message'])} | {md_cell(r['expected'])} | (ไม่มีไฟล์ภาพ) | – | – |")
                continue
            res = r["result"]
            ans = res.get("answer") or res.get("error") or ""
            if res.get("blocked"):
                ans = f"[ปฏิเสธโดย {res.get('layer')} {','.join(res.get('categories') or [])}] {ans}"
            subject = r["message"] if group != "images" else f"{r['file']} + \"{r['message']}\""
            lines.append(f"| {r['id']} | {md_cell(subject)} | {md_cell(r['expected'])} | {md_cell(ans)} | "
                         f"{'ผ่าน' if r['pass'] else 'ไม่ผ่าน'} | {res.get('total', res['wall_time'])} |")
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def merge_into(tag: str, results: list[dict], order: list[str]):
    """แทนผลข้อที่รันใหม่ลงในไฟล์ผลล่าสุดของ tag (เช่น after) โดยเรียงตามลำดับใน cases.json"""
    files = sorted((HERE / "results").glob(f"*_{tag}.json"))
    if not files:
        print(f"ไม่พบไฟล์ผล *_{tag}.json")
        return
    old = {r["id"]: r for r in json.loads(files[-1].read_text(encoding="utf-8"))}
    old.update({r["id"]: r for r in results if not r.get("skipped")})
    merged = [old[i] for i in order if i in old]
    files[-1].write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")
    write_markdown(merged, files[-1].with_suffix(".md"))
    print(f"รวมผลเข้า {files[-1].name} แล้ว")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="", help="รายการ id คั่นด้วย , เช่น Q1,I3,S4")
    ap.add_argument("--tag", default="run")
    ap.add_argument("--pause", type=int, default=PAUSE_SEC)
    ap.add_argument("--merge-into", default="", help="รวมผลเข้าไฟล์ผลล่าสุดของ tag นี้ เช่น after")
    args = ap.parse_args()
    only = {x.strip() for x in args.only.split(",") if x.strip()}

    cases = json.loads((HERE / "cases.json").read_text(encoding="utf-8"))
    plan = [("questions", c) for c in cases["questions"]] + [("images", c) for c in cases["images"]] + \
           [("safety", c) for c in cases["safety"]]
    full_plan = plan
    if only:
        plan = [(g, c) for g, c in plan if c["id"] in only]

    results = []
    with httpx.Client() as client:
        for i, (group, c) in enumerate(plan):
            image = HERE / c["file"] if c.get("file") else None
            if image and not image.exists():
                print(f"{c['id']}: ข้าม — ไม่พบไฟล์ {image.relative_to(HERE)}")
                results.append({**c, "group": group, "skipped": True})
                continue
            res = run_case(client, c["message"], image)
            ok, why = judge(c["check"], res)
            results.append({**c, "group": group, "result": res, "pass": ok, "why": why})
            mark = "ผ่าน" if ok else "ไม่ผ่าน"
            print(f"{c['id']:4} {mark:7} {res.get('total', res['wall_time']):5}s  {(res.get('answer') or res.get('error') or '')[:70]!r}"
                  + (f"  ← {why}" if why else ""))
            if i < len(plan) - 1:
                time.sleep(args.pause)

    out_dir = HERE / "results"
    out_dir.mkdir(exist_ok=True)
    stem = f"{datetime.now():%Y%m%d_%H%M}_{args.tag}"
    (out_dir / f"{stem}.json").write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")

    write_markdown(results, out_dir / f"{stem}.md")
    if args.merge_into:
        merge_into(args.merge_into, results, [c["id"] for _, c in full_plan])
    passed = sum(1 for r in results if r.get("pass"))
    print(f"\nสรุป: ผ่าน {passed}/{len(results)} · บันทึกที่ eval/results/{stem}.md")


if __name__ == "__main__":
    main()
