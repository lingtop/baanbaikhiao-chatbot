"""เทียบผลทดสอบ 2 รอบ (ก่อน-หลังปรับปรุง)

ใช้งาน:  uv run python eval/compare.py baseline after
ผลลัพธ์: พิมพ์ตารางเทียบ และบันทึก eval/results/compare_<a>_vs_<b>.md
"""

import json
import statistics
import sys
from pathlib import Path

RES = Path(__file__).resolve().parent / "results"
GREETING = "สวัสดีค่ะ"


def load(tag: str) -> dict:
    path = sorted(RES.glob(f"*_{tag}.json"))[-1]
    return {r["id"]: r for r in json.loads(path.read_text(encoding="utf-8")) if not r.get("skipped")}


def metrics(rows: dict) -> dict:
    answered = [r for r in rows.values() if not r["result"].get("blocked") and r["result"].get("answer")]
    times = [r["result"].get("total", r["result"]["wall_time"]) for r in rows.values()]
    llm_times = [r["result"].get("timings", {}).get("llm", 0) for r in answered]
    return {
        "ผ่าน": f"{sum(r['pass'] for r in rows.values())}/{len(rows)}",
        "เวลาตอบเฉลี่ย (วิ)": round(statistics.mean(times), 2),
        "เวลาตอบสูงสุด (วิ)": round(max(times), 2),
        "เวลา LLM เฉลี่ย (วิ)": round(statistics.mean(llm_times), 2) if llm_times else 0,
        "คำตอบขึ้นต้นด้วยการทักทาย": sum(r["result"]["answer"].startswith(GREETING) for r in answered),
        "คำลงท้ายซ้อน 'นะคะค่ะ'": sum("นะคะค่ะ" in r["result"]["answer"] for r in answered),
        "ความยาวคำตอบเฉลี่ย (ตัวอักษร)": round(statistics.mean(len(r["result"]["answer"]) for r in answered)) if answered else 0,
    }


def main(a: str, b: str):
    ra, rb = load(a), load(b)
    ids = [i for i in ra if i in rb]
    ra, rb = {i: ra[i] for i in ids}, {i: rb[i] for i in ids}
    ma, mb = metrics(ra), metrics(rb)
    lines = [f"# เปรียบเทียบผลทดสอบ: {a} → {b} ({len(ids)} ข้อที่รันทั้งสองรอบ)", "",
             f"| ตัวชี้วัด | {a} | {b} |", "|---|---|---|"]
    lines += [f"| {k} | {ma[k]} | {mb[k]} |" for k in ma]
    lines += ["", "## รายข้อ", "", f"| ข้อ | {a} | เวลา | {b} | เวลา |", "|---|---|---|---|---|"]
    for i in ids:
        x, y = ra[i], rb[i]
        lines.append(f"| {i} | {'ผ่าน' if x['pass'] else 'ไม่ผ่าน'} | {x['result'].get('total')} | "
                     f"{'ผ่าน' if y['pass'] else 'ไม่ผ่าน'} | {y['result'].get('total')} |")
    out = RES / f"compare_{a}_vs_{b}.md"
    out.write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))
    print(f"\nบันทึกที่ {out.relative_to(RES.parent.parent)}")


if __name__ == "__main__":
    main(*(sys.argv[1:3] if len(sys.argv) >= 3 else ("baseline", "after")))
