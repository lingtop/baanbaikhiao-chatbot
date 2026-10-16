"""RAG Server (:9621) — ค้นคลังความรู้ด้วย LightRAG (knowledge graph + vector) (สัปดาห์ 9)

รัน (จากโฟลเดอร์ rag/):  uv run uvicorn main:app --port 9621

ใช้แทน `lightrag-server` สำเร็จรูป เพราะ embedding อยู่ในเครื่อง (bge-m3) ซึ่ง lightrag-server ไม่มี binding ให้
และเพื่อให้ตอนค้นสลับ LLM ตัวสำรองได้เมื่อ Gemini ไม่ว่าง

โครงสร้าง:
  controllers/query_controller.py   POST /query, GET /health
  services/query_service.py         ค้นแล้วประกอบ context (ข้อความต้นฉบับก่อน ตามด้วย entity)
  services/rag_engine.py            ตั้งค่า LightRAG + LLM (มีตัวสำรอง) — ใช้ร่วมกับสคริปต์ index
  services/embedding_service.py     embedding bge-m3 ในเครื่องด้วย onnxruntime
  models/schemas.py                 รูปแบบ request / response
  scripts/                          index_kb.py (สร้างคลังความรู้), download_model.py (โหลดโมเดล)
  storage/                          bge-m3/ (โมเดล ไม่ขึ้น git) + lightrag/ (knowledge graph / vector DB ขึ้น git ใช้ตอน deploy)
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI

from controllers import query_controller
from services import embedding_service, rag_engine


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        embedding_service.embed(["warm up"])  # โหลดโมเดล embedding ตั้งแต่เปิด server ไม่ให้คำถามแรกช้า
    except RuntimeError as e:  # โหมด hf: API ยังไม่พร้อม → เปิด server ต่อ แล้วลองใหม่ตอนมีคำถาม
        print(f"embedding warm-up ไม่สำเร็จ: {e}", flush=True)
    rag_engine.set_primary_timeout(8)     # สกัด keyword ตอนค้น: Gemini ช้าเกิน 8 วินาที → สลับไป Groq
    app.state.rag = await rag_engine.make_rag(max_async=4)
    yield
    await app.state.rag.finalize_storages()


app = FastAPI(title="บ้านใบเขียว RAG", version="0.2.0", lifespan=lifespan)
app.include_router(query_controller.router)
