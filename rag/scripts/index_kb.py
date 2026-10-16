"""นำคลังความรู้ (data/knowledge_base/*.md) เข้า LightRAG

ใช้งาน (จากโฟลเดอร์ rag/):
    uv run python -m scripts.index_kb            # index ไฟล์ที่ยังไม่เคย index
    uv run python -m scripts.index_kb --reset    # ลบคลังเดิมแล้ว index ใหม่ทั้งหมด (เก็บ LLM cache ไว้ ไม่เรียก LLM ซ้ำ)

ทำไมเขียนสคริปต์เองแทนการอัปโหลดผ่าน WebUI ของ LightRAG:
  1. โควต้าฟรีของ Gemini 3.1 Flash Lite คือ 15 ครั้ง/นาที — สคริปต์เว้นช่วงระหว่างการเรียก LLM
     และสลับไปตัวสำรองเมื่อเจอ 503 จึงไม่ล้มกลางทาง
  2. ตัดข้อความตามหัวข้อ markdown (## / ###) ไม่ให้ข้อมูลต้นไม้ 1 ต้นถูกหั่นกลางหัวข้อ
     แล้วรวมหัวข้อติดกันให้ได้ราว 900 token ต่อ chunk เพื่อประหยัดจำนวนครั้งที่เรียก LLM

หลัง index เสร็จ เปิดตัวค้นคืนด้วย:  uv run uvicorn main:app --port 9621
"""

import argparse
import asyncio
import os
import re
import shutil
import time

import tiktoken

from services import rag_engine as common

KB_DIR = common.HERE.parent / "data" / "knowledge_base"
SEPARATOR = "\n<<<CHUNK>>>\n"
CHUNK_TOKENS = int(os.environ.get("INDEX_CHUNK_TOKENS", "900"))


def pack_sections(text: str, enc) -> str:
    """ตัดตามหัวข้อ ## / ### แล้วรวมหัวข้อติดกันให้ไม่เกิน CHUNK_TOKENS ต่อ chunk

    ทุก chunk ขึ้นต้นด้วยชื่อเอกสาร (# ...) เพื่อให้ LLM รู้ว่าเป็นข้อมูลส่วนไหนของร้าน
    """
    title = text.splitlines()[0] if text.startswith("# ") else ""
    sections = re.split(r"\n(?=#{2,3} )", text)
    chunks, current, size = [], [], 0
    for sec in sections:
        n = len(enc.encode(sec))
        if current and size + n > CHUNK_TOKENS:
            chunks.append("\n".join(current))
            current, size = [], 0
        current.append(sec)
        size += n
    if current:
        chunks.append("\n".join(current))
    chunks = [c if c.startswith("# ") or not title else f"{title}\n{c}" for c in chunks]
    return SEPARATOR.join(chunks)


def reset_storage():
    wd = common.WORKING_DIR
    if not wd.exists():
        return
    # เก็บ cache ผลเรียก LLM ไว้ chunk ที่เคยสกัดแล้วจะไม่เรียก LLM ซ้ำ (ประหยัดโควต้า)
    cache = wd / "kv_store_llm_response_cache.json"
    saved = cache.read_bytes() if cache.exists() else None
    shutil.rmtree(wd)
    if saved:
        wd.mkdir()
        cache.write_bytes(saved)
    print("ลบคลังเดิมแล้ว" + (" (เก็บ LLM cache ไว้)" if saved else ""))


async def main(reset: bool):
    if reset:
        reset_storage()
    common.set_min_interval(float(os.environ.get("INDEX_MIN_INTERVAL_SEC", "4.5")))
    rag = await common.make_rag()

    enc = tiktoken.get_encoding("cl100k_base")
    files = sorted(KB_DIR.glob("*.md"))
    t0 = time.perf_counter()
    s = common.stats
    for i, f in enumerate(files, 1):
        packed = pack_sections(f.read_text(encoding="utf-8"), enc)
        print(f"[{i}/{len(files)}] {f.name}: {packed.count(SEPARATOR) + 1} chunk", flush=True)
        await rag.ainsert(packed, split_by_character=SEPARATOR.strip(), split_by_character_only=True,
                          ids=f"kb-{f.stem}", file_paths=f.name)
        print(f"      สะสม: เรียก LLM {s['llm_calls']} ครั้ง (ตัวสำรอง {s['fallback']}) · retry {s['retries']} · "
              f"{time.perf_counter() - t0:.0f} วินาที", flush=True)

    status = await rag.doc_status.get_all() if hasattr(rag.doc_status, "get_all") else {}
    failed = [k for k, v in (status or {}).items() if str(v.get("status", "")).lower().endswith("failed")]
    await rag.finalize_storages()
    print(f"เสร็จ: เรียก LLM {s['llm_calls']} ครั้ง ใช้เวลา {(time.perf_counter() - t0) / 60:.1f} นาที"
          + (f" · ล้มเหลว: {failed}" if failed else " · ทุกไฟล์สำเร็จ"))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--reset", action="store_true", help="ลบคลังเดิมแล้ว index ใหม่ทั้งหมด")
    asyncio.run(main(ap.parse_args().reset))
