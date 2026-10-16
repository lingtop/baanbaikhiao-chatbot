"""Guard Service (:8001) — ต่อยอดจาก Llama Guard Layer (สัปดาห์ 11, github.com/chacharin/llama-guard-layer)

ตรวจข้อความ 2 ครั้งต่อ 1 บทสนทนา: ขาเข้า (ก่อนเข้า RAG/LLM) และขาออก (ก่อนส่งคำตอบให้ลูกค้า)

รัน (จากโฟลเดอร์โปรเจกต์):  uv run uvicorn guard.main:app --port 8001

โครงสร้าง:
  controllers/check_controller.py   POST /check — ลำดับ 4 ชั้น + fail-closed
  services/rule_service.py          ชั้น 1–2: Blocklist + Business Rules (ไม่ใช้โมเดล)
  services/classifier_service.py    ชั้น 3–4: Prompt Guard 2 + Safety Classifier (ใช้โมเดล)
  models/schemas.py                 รูปแบบ request / response
  data/blocklist.txt                คำต้องห้าม
กติกาอยู่ในโค้ด ไม่อยู่ใน prompt — ผู้ใช้ล้วงกติกาออกจาก prompt ไม่ได้ (OWASP LLM08)
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from guard.controllers import check_controller

app = FastAPI(title="บ้านใบเขียว Guard Service", version="0.2.0")
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:8000", "http://127.0.0.1:8000"],
                   allow_methods=["POST", "GET"], allow_headers=["*"])
app.include_router(check_controller.router)
