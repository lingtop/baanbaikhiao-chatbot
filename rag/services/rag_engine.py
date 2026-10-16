"""แกนของ RAG — ใช้ร่วมกันระหว่าง scripts/index_kb.py (สร้างคลังความรู้) และ main.py (ค้นคืน :9621)

- llm_func: เรียก LLM แบบ OpenAI-compatible เว้นช่วงตามโควต้า และสลับไปตัวสำรองเมื่อตัวหลักไม่ว่าง
- embed_func: embedding ในเครื่อง (bge-m3 ONNX) — ดู services/embedding_service.py
- make_rag: สร้าง LightRAG ด้วยค่าเดียวกันทั้งตอน index และตอนค้น (embedding ต้องตรงกัน)
"""

import asyncio
import os
import re
import time
from pathlib import Path

import httpx
import numpy as np
from dotenv import load_dotenv

HERE = Path(__file__).resolve().parents[1]  # โฟลเดอร์ rag/
load_dotenv(HERE / ".env")

from lightrag import LightRAG  # noqa: E402  (ต้อง import หลัง load_dotenv)
from lightrag.kg.shared_storage import initialize_pipeline_status  # noqa: E402
from lightrag.utils import EmbeddingFunc  # noqa: E402

from services import embedding_service as local_embed  # noqa: E402

LLM_HOST = os.environ["LLM_BINDING_HOST"].rstrip("/")
LLM_KEY = os.environ["LLM_BINDING_API_KEY"]
LLM_MODEL = os.environ["LLM_MODEL"]
FALLBACK_MODEL = os.environ.get("INDEX_FALLBACK_MODEL", "")
FALLBACK_HOST = os.environ.get("INDEX_FALLBACK_HOST", LLM_HOST).rstrip("/")
FALLBACK_KEY = os.environ.get("INDEX_FALLBACK_API_KEY", "") or LLM_KEY
WORKING_DIR = HERE / os.environ.get("WORKING_DIR", "./storage/lightrag")

THOUGHT_RE = re.compile(r"<(thought|think)>.*?</\1>", re.DOTALL)
stats = {"llm_calls": 0, "retries": 0, "fallback": 0}
_min_interval = 0.0
_primary_timeout = 150.0
_last_call = 0.0
_lock = asyncio.Lock()


def set_min_interval(seconds: float):
    """ตอน index เรียก LLM ต่อเนื่องจึงต้องเว้นช่วง (Flash Lite ฟรี 15 ครั้ง/นาที) ตอนค้นไม่ต้อง"""
    global _min_interval
    _min_interval = seconds


def set_primary_timeout(seconds: float):
    """ตอนค้น (มีลูกค้ารอ) ให้ตัวหลักตอบภายในเวลาสั้น ช้าเกินก็สลับไปตัวสำรอง"""
    global _primary_timeout
    _primary_timeout = seconds


async def _throttle():
    global _last_call
    if _min_interval <= 0:
        return
    async with _lock:
        wait = _min_interval - (time.monotonic() - _last_call)
        if wait > 0:
            await asyncio.sleep(wait)
        _last_call = time.monotonic()


async def llm_func(prompt, system_prompt=None, history_messages=None, keyword_extraction=False, **kwargs):
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.extend(history_messages or [])
    messages.append({"role": "user", "content": prompt})
    body = {"messages": messages, "temperature": 0}
    if keyword_extraction:
        body["response_format"] = {"type": "json_object"}

    for attempt in range(6):
        # สลับระหว่างตัวหลัก (Flash Lite) กับตัวสำรอง (gpt-oss-120b บน Groq) เมื่อเจอ 503 แทนการรอเฉย ๆ
        # (เคยลอง Gemma 4 เป็นตัวสำรอง แต่คิดนานเกิน 180 วินาทีกับ prompt สกัด entity จน timeout)
        use_fallback = attempt % 2 == 1 and FALLBACK_MODEL
        model = FALLBACK_MODEL if use_fallback else LLM_MODEL
        host, key = (FALLBACK_HOST, FALLBACK_KEY) if use_fallback else (LLM_HOST, LLM_KEY)
        payload = {**body, "model": model}
        if model.startswith("openai/gpt-oss"):
            payload["reasoning_effort"] = "low"
        await _throttle()
        try:
            async with httpx.AsyncClient(timeout=150 if use_fallback else _primary_timeout) as client:
                r = await client.post(f"{host}/chat/completions", json=payload,
                                      headers={"Authorization": f"Bearer {key}"})
        except httpx.HTTPError as e:
            stats["retries"] += 1
            print(f"  LLM {model} เชื่อมต่อไม่ได้ ({type(e).__name__}) → ลองใหม่", flush=True)
            continue
        if r.status_code == 200:
            stats["llm_calls"] += 1
            stats["fallback"] += int(bool(use_fallback))
            text = r.json()["choices"][0]["message"].get("content") or ""
            return THOUGHT_RE.sub("", text).strip()
        if r.status_code in (429, 500, 503):
            stats["retries"] += 1
            delay = 0 if attempt == 0 else 5 * attempt
            print(f"  LLM {model} {r.status_code} → ลองใหม่{f' (รอ {delay} วินาที)' if delay else ''}", flush=True)
            await asyncio.sleep(delay)
            continue
        raise RuntimeError(f"LLM error {r.status_code}: {r.text[:300]}")
    raise RuntimeError("LLM ล้มเหลวหลังลองใหม่ 6 ครั้ง (อาจหมดโควต้ารายวัน)")


async def embed_func(texts: list[str]) -> np.ndarray:
    # รันโมเดลใน thread แยก ไม่ให้บล็อก event loop
    return await asyncio.to_thread(local_embed.embed, texts)


async def make_rag(max_async: int = 1) -> LightRAG:
    rag = LightRAG(
        working_dir=str(WORKING_DIR),
        llm_model_func=llm_func,
        llm_model_name=LLM_MODEL,
        llm_model_max_async=max_async,
        embedding_func=EmbeddingFunc(embedding_dim=local_embed.DIM, func=embed_func, max_token_size=local_embed.MAX_TOKENS,
                                     model_name=f"local:{local_embed.REPO}"),
        embedding_batch_num=16,
        embedding_func_max_async=1,
        default_embedding_timeout=300,
        chunk_token_size=int(os.environ.get("INDEX_CHUNK_TOKENS", "900")) + 400,
        entity_extract_max_gleaning=0,  # ปิดรอบสกัดซ้ำ ลดจำนวนครั้งที่เรียก LLM ลงครึ่งหนึ่ง
        enable_llm_cache=True,
        addon_params={"language": "Thai"},
    )
    await rag.initialize_storages()
    await initialize_pipeline_status()
    return rag
