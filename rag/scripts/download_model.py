"""ดาวน์โหลดโมเดล embedding (bge-m3 ONNX int8) มาไว้ที่ rag/storage/bge-m3/ ครั้งเดียว

แบ่งไฟล์เป็นหลายส่วนแล้วดาวน์โหลดพร้อมกัน เพราะ CDN จำกัดความเร็วต่อการเชื่อมต่อ
ใช้งาน (จากโฟลเดอร์ rag/):  uv run python -m scripts.download_model
"""

import concurrent.futures as cf
import sys
import time
from pathlib import Path

import httpx

REPO = "Xenova/bge-m3"
FILES = ["tokenizer.json", "onnx/model_int8.onnx"]
OUT = Path(__file__).resolve().parents[1] / "storage" / "bge-m3"
PARTS = 8


def url(f: str) -> str:
    return f"https://huggingface.co/{REPO}/resolve/main/{f}"


def fetch_range(u: str, start: int, end: int, dest: Path, progress: list, idx: int):
    for attempt in range(5):
        try:
            done = dest.stat().st_size if dest.exists() else 0
            if start + done > end:
                return
            headers = {"Range": f"bytes={start + done}-{end}"}
            with httpx.stream("GET", u, headers=headers, follow_redirects=True, timeout=60) as r:
                r.raise_for_status()
                with open(dest, "ab") as fh:
                    for chunk in r.iter_bytes(1 << 16):
                        fh.write(chunk)
                        progress[idx] += len(chunk)
            return
        except httpx.HTTPError as e:
            print(f"  part {idx} error {type(e).__name__} → retry", flush=True)
            time.sleep(3)
    raise RuntimeError(f"part {idx} failed")


def download(f: str):
    target = OUT / Path(f).name
    if target.exists():
        print(f"มีแล้ว: {target.name}")
        return
    head = httpx.head(url(f), follow_redirects=True, timeout=30)
    size = int(head.headers.get("content-length", 0))
    if size < 50_000_000:  # ไฟล์เล็ก โหลดตรง
        target.write_bytes(httpx.get(url(f), follow_redirects=True, timeout=120).content)
        print(f"ok {target.name} {size / 1e6:.1f} MB")
        return
    step = size // PARTS
    ranges = [(i * step, size - 1 if i == PARTS - 1 else (i + 1) * step - 1) for i in range(PARTS)]
    parts = [target.with_suffix(f".part{i}") for i in range(PARTS)]
    progress = [p.stat().st_size if p.exists() else 0 for p in parts]
    t0 = time.perf_counter()
    with cf.ThreadPoolExecutor(PARTS) as ex:
        futs = [ex.submit(fetch_range, url(f), s, e, parts[i], progress, i) for i, (s, e) in enumerate(ranges)]
        while not all(x.done() for x in futs):
            got = sum(progress)
            rate = got / max(1, time.perf_counter() - t0) / 1e6
            print(f"  {target.name}: {got / 1e6:.0f}/{size / 1e6:.0f} MB · {rate:.1f} MB/s", flush=True)
            time.sleep(15)
        for x in futs:
            x.result()
    with open(target, "wb") as out:
        for p in parts:
            out.write(p.read_bytes())
            p.unlink()
    assert target.stat().st_size == size, "ขนาดไฟล์ไม่ตรง"
    print(f"ok {target.name} {size / 1e6:.0f} MB ใน {time.perf_counter() - t0:.0f} วินาที")


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    for f in FILES:
        download(f)
    sys.exit(0)
