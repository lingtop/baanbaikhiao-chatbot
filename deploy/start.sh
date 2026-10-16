#!/bin/sh
# เปิด 3 service ใน container เดียว (Render free tier ให้ 1 service = 1 พอร์ตสาธารณะ)
#   RAG :9621 และ Guard :8001 ฟังเฉพาะภายใน container (127.0.0.1) — คนภายนอกเรียกตรงไม่ได้
#   Chat API ฟังที่ $PORT ที่ Render กำหนด — เป็นทางเข้าเดียวของลูกค้า
set -e

# RAG ใช้ชื่อตัวแปรของ LightRAG — ส่งต่อจาก key ชุดเดียวกับ Chat API ไม่ต้องตั้งซ้ำบน Render
export LLM_BINDING_API_KEY="${LLM_BINDING_API_KEY:-$LLM_API_KEY}"
export INDEX_FALLBACK_API_KEY="${INDEX_FALLBACK_API_KEY:-$GROQ_API_KEY}"

cd /app/rag
/app/rag/.venv/bin/python -m uvicorn main:app --host 127.0.0.1 --port 9621 &

cd /app
/app/.venv/bin/python -m uvicorn guard.main:app --host 127.0.0.1 --port 8001 &

exec /app/.venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-10000}" --proxy-headers --forwarded-allow-ips="*"
