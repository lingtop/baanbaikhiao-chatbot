"""จุดเริ่มต้นของ Chat API (FastAPI :8000) — สร้างแอปแล้วผูก controller ทั้งหมด

รัน (จากโฟลเดอร์โปรเจกต์):  uv run uvicorn app.main:app --port 8000
แล้วเปิด http://localhost:8000
ต้องเปิด RAG Server (:9621) และ Guard Service (:8001) ก่อน — ดู README

โครงสร้าง:
  controllers/  รับ HTTP request → ตรวจ input → เรียก service → ส่ง response
  services/     ตรรกะหลัก: ลำดับการทำงาน, เรียก LLM / RAG / Guard
  models/       โครงสร้างข้อมูล + อ่านข้อมูลร้าน (ต้นไม้, คำสั่งซื้อ, session)
  views/        หน้าเว็บ (templates + static)
  prompts/      system prompt
"""

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.controllers import chat_controller, order_controller, page_controller, system_controller

VIEWS = Path(__file__).resolve().parent / "views"

app = FastAPI(title="บ้านใบเขียว AI", version="0.2.0")
app.mount("/static", StaticFiles(directory=VIEWS / "static"), name="static")

app.include_router(page_controller.router)
app.include_router(chat_controller.router)
app.include_router(order_controller.router)
app.include_router(system_controller.router)
