"""Embedding ในเครื่องด้วย bge-m3 (ONNX int8) — ฟรี ไม่มีโควต้า ไม่ต้องใช้อินเทอร์เน็ตหลังดาวน์โหลดครั้งแรก

ทำไมไม่ใช้ Gemini Embedding: free tier นับ 1 ข้อความ = 1 request (100/นาที, 1,000/วัน)
แต่การ index ครั้งเดียวต้อง embed ~800 ข้อความ (entity + relation + chunk) จึงชนโควต้าทุกครั้งที่ index ใหม่

ทำไมใช้ onnxruntime แทน sentence-transformers/torch: เครื่องพัฒนาเปิด Windows Smart App Control
ซึ่งบล็อก DLL ของ torch ส่วน onnxruntime (Microsoft เซ็นรับรอง) ใช้ได้

bge-m3: โมเดล embedding หลายภาษาของ BAAI รองรับภาษาไทย เวกเตอร์ 1024 มิติ ใช้เวกเตอร์ของ token [CLS] แล้ว normalize

EMBEDDING_PROVIDER=hf (ใช้ตอน deploy บน Render free tier ที่มี RAM 512 MB):
  ไม่โหลดโมเดลในเครื่อง (ประหยัด ~1.2 GB) แต่ส่งข้อความไปให้ Hugging Face Inference API คำนวณด้วย bge-m3 ตัวเดียวกัน
  เวกเตอร์จึงเข้ากับคลังที่ index ไว้แล้ว ไม่ต้อง index ใหม่ — ตอนค้นใช้แค่ 1–2 ข้อความต่อคำถาม
"""

import os
import time
from functools import lru_cache
from pathlib import Path

import httpx
import numpy as np

REPO = "Xenova/bge-m3"
MODEL_DIR = Path(__file__).resolve().parents[1] / "storage" / "bge-m3"  # ดาวน์โหลดด้วย scripts/download_model.py
DIM = 1024
MAX_TOKENS = 512
PROVIDER = os.environ.get("EMBEDDING_PROVIDER", "local").lower()
HF_URL = os.environ.get("HF_EMBEDDING_URL",
                        "https://router.huggingface.co/hf-inference/models/BAAI/bge-m3/pipeline/feature-extraction")


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


def _embed_hf(texts: list[str], batch_size: int = 16) -> np.ndarray:
    token = os.environ.get("HF_TOKEN", "")
    if not token:
        raise RuntimeError("EMBEDDING_PROVIDER=hf แต่ยังไม่ได้ตั้งค่า HF_TOKEN")
    out = []
    for i in range(0, len(texts), batch_size):
        for attempt in range(3):
            r = httpx.post(HF_URL, json={"inputs": texts[i:i + batch_size]}, timeout=60,
                           headers={"Authorization": f"Bearer {token}"})
            if r.status_code == 200:
                break
            if r.status_code not in (429, 500, 502, 503, 504) or attempt == 2:
                raise RuntimeError(f"HF embedding {r.status_code}: {r.text[:200]}")
            time.sleep(2 * (attempt + 1))  # โมเดลกำลังโหลด / ไม่ว่าง → รอแล้วลองใหม่
        v = np.asarray(r.json(), dtype=np.float32)
        out.append(v / np.linalg.norm(v, axis=1, keepdims=True))
    return np.vstack(out)


def embed(texts: list[str], batch_size: int = 16) -> np.ndarray:
    if PROVIDER == "hf":
        return _embed_hf(texts, batch_size)
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
    import time
    t = time.perf_counter()
    v = embed(["ลิ้นมังกร ทนแสงน้อย ดูแลง่าย", "ต้นไม้ที่ดูแลง่ายสำหรับห้องที่แดดส่องไม่ถึง", "ค่าส่งต่างจังหวัด 120 บาท"])
    print("shape", v.shape, f"{time.perf_counter() - t:.1f}s (รวมโหลดโมเดล)")
    print("ความคล้าย 0-1 (ควรสูง):", round(float(v[0] @ v[1]), 3), " 0-2 (ควรต่ำ):", round(float(v[0] @ v[2]), 3))
