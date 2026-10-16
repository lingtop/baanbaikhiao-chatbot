"""Embedding ในเครื่องด้วย bge-m3 (ONNX int8) — ฟรี ไม่มีโควต้า ไม่ต้องใช้อินเทอร์เน็ตหลังดาวน์โหลดครั้งแรก

ทำไมไม่ใช้ Gemini Embedding: free tier นับ 1 ข้อความ = 1 request (100/นาที, 1,000/วัน)
แต่การ index ครั้งเดียวต้อง embed ~800 ข้อความ (entity + relation + chunk) จึงชนโควต้าทุกครั้งที่ index ใหม่

ทำไมใช้ onnxruntime แทน sentence-transformers/torch: เครื่องพัฒนาเปิด Windows Smart App Control
ซึ่งบล็อก DLL ของ torch ส่วน onnxruntime (Microsoft เซ็นรับรอง) ใช้ได้

bge-m3: โมเดล embedding หลายภาษาของ BAAI รองรับภาษาไทย เวกเตอร์ 1024 มิติ ใช้เวกเตอร์ของ token [CLS] แล้ว normalize

EMBEDDING_PROVIDER=gemini (ใช้ตอน deploy บน Render free tier ที่มี RAM 512 MB — โหลด bge-m3 ไม่ได้):
  ใช้ gemini-embedding-001 (ตั้งให้ออก 1024 มิติ) ผ่าน API ด้วย key AI Studio ตัวเดิม — ตอนค้นใช้แค่ 1–2 ข้อความต่อคำถาม
  เวกเตอร์คนละแบบกับ bge-m3 จึงใช้คลังแยก storage/lightrag_gemini (index ครั้งเดียว ~900 ข้อความ เว้นจังหวะไม่เกินโควต้า 100/นาที)
  (เคยลอง bge-m3 ผ่าน Hugging Face Inference API แต่บัญชีฟรีไม่มีเครดิต → 402)
"""

import os
import time
from collections import deque
from functools import lru_cache
from pathlib import Path

import httpx
import numpy as np

REPO = "Xenova/bge-m3"
MODEL_DIR = Path(__file__).resolve().parents[1] / "storage" / "bge-m3"  # ดาวน์โหลดด้วย scripts/download_model.py
DIM = 1024
MAX_TOKENS = 512
PROVIDER = os.environ.get("EMBEDDING_PROVIDER", "local").lower()
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/openai/embeddings"
GEMINI_MODEL = "gemini-embedding-001"
GEMINI_PER_MIN = 90  # free tier นับ 1 ข้อความ = 1 request (100/นาที) — เผื่อไว้ 10
_sent: deque = deque()  # เวลาที่ส่งแต่ละข้อความ ภายใน 60 วินาทีล่าสุด


@lru_cache
def _load():
    import onnxruntime as ort
    from tokenizers import Tokenizer

    model_path = MODEL_DIR / "model_int8.onnx"
    if not model_path.exists():
        raise FileNotFoundError("ยังไม่มีโมเดล embedding — รัน `uv run python -m scripts.download_model` ในโฟลเดอร์ rag ก่อน")
    tok = Tokenizer.from_file(str(MODEL_DIR / "tokenizer.json"))
    tok.enable_truncation(MAX_TOKENS)
    tok.enable_padding(pad_id=tok.token_to_id("<pad>") or 1, pad_token="<pad>")
    opts = ort.SessionOptions()
    # วัดจริงบน Core Ultra 9 (P-core + E-core): 1 thread = 0.6 วิ/16 ข้อความ, 16 threads = 8 วิ — thread มากยิ่งช้า
    opts.intra_op_num_threads = int(os.environ.get("LOCAL_EMBED_THREADS", "1"))
    opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
    session = ort.InferenceSession(str(model_path), opts, providers=["CPUExecutionProvider"])
    return tok, session


def _wait_quota(n: int):
    while True:
        now = time.monotonic()
        while _sent and now - _sent[0] > 60:
            _sent.popleft()
        if len(_sent) + n <= GEMINI_PER_MIN:
            _sent.extend([now] * n)
            return
        time.sleep(60 - (now - _sent[0]) + 0.5)


def _embed_gemini(texts: list[str], batch_size: int = 16) -> np.ndarray:
    key = os.environ.get("EMBEDDING_API_KEY") or os.environ.get("LLM_BINDING_API_KEY", "")
    out = []
    for i in range(0, len(texts), batch_size):
        batch = texts[i:i + batch_size]
        for attempt in range(4):
            _wait_quota(len(batch))
            r = httpx.post(GEMINI_URL, timeout=60, headers={"Authorization": f"Bearer {key}"},
                           json={"model": GEMINI_MODEL, "input": batch, "dimensions": DIM})
            if r.status_code == 200:
                break
            if r.status_code not in (429, 500, 503, 504) or attempt == 3:
                raise RuntimeError(f"Gemini embedding {r.status_code}: {r.text[:200]}")
            time.sleep(15 * (attempt + 1))
        v = np.asarray([d["embedding"] for d in r.json()["data"]], dtype=np.float32)
        out.append(v / np.linalg.norm(v, axis=1, keepdims=True))  # ตัดเหลือ 1024 มิติแล้วต้อง normalize ใหม่
    return np.vstack(out)


def embed(texts: list[str], batch_size: int = 16) -> np.ndarray:
    if PROVIDER == "gemini":
        return _embed_gemini(texts, batch_size)
    tok, session = _load()
    input_names = {i.name for i in session.get_inputs()}
    out = []
    for i in range(0, len(texts), batch_size):
        enc = tok.encode_batch(texts[i:i + batch_size])
        feed = {
            "input_ids": np.array([e.ids for e in enc], dtype=np.int64),
            "attention_mask": np.array([e.attention_mask for e in enc], dtype=np.int64),
        }
        if "token_type_ids" in input_names:
            feed["token_type_ids"] = np.zeros_like(feed["input_ids"])
        hidden = session.run(None, feed)[0]  # (batch, seq, 1024)
        cls = hidden[:, 0, :]
        out.append(cls / np.linalg.norm(cls, axis=1, keepdims=True))
    return np.vstack(out).astype(np.float32)


if __name__ == "__main__":
    t = time.perf_counter()
    v = embed(["ลิ้นมังกร ทนแสงน้อย ดูแลง่าย", "ต้นไม้ที่ดูแลง่ายสำหรับห้องที่แดดส่องไม่ถึง", "ค่าส่งต่างจังหวัด 120 บาท"])
    print("shape", v.shape, f"{time.perf_counter() - t:.1f}s (รวมโหลดโมเดล)")
    print("ความคล้าย 0-1 (ควรสูง):", round(float(v[0] @ v[1]), 3), " 0-2 (ควรต่ำ):", round(float(v[0] @ v[2]), 3))
