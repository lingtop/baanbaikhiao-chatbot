# บ้านใบเขียว AI — image เดียวรัน Chat API + Guard + RAG (สัปดาห์ 10: FastAPI + Docker + Render)
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

RUN pip install --no-cache-dir uv==0.12.3

WORKDIR /app

# ติดตั้ง dependency ก่อนคัดลอกโค้ด เพื่อให้ build ครั้งถัดไปใช้ cache ได้
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY rag/pyproject.toml rag/uv.lock rag/
RUN cd rag && uv sync --frozen --no-install-project

# โค้ด + ข้อมูลร้าน + คลังที่ index แล้ว (ไม่มีโมเดล bge-m3 — ตอน deploy ใช้ Hugging Face Inference API แทน)
COPY app app
COPY guard guard
COPY data data
COPY rag rag
COPY deploy/rag.env rag/.env
COPY deploy/start.sh /start.sh
RUN chmod +x /start.sh

EXPOSE 10000
CMD ["/start.sh"]
