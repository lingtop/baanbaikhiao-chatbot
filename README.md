# บ้านใบเขียว AI — แชทบอทร้านต้นไม้

Final Project วิชา 06048308 Intelligent Chatbot Development · ข้อมูลร้านทั้งหมดเป็นข้อมูลจำลอง

แชทบอทตอบลูกค้าแทนร้านต้นไม้ "บ้านใบเขียว" ตอบจากคลังความรู้ของร้าน (ต้นไม้ 132 สายพันธุ์ บริการ นโยบาย)
วิเคราะห์รูปต้นไม้/สลิป/พัสดุเสียหาย และมีด่านตรวจความปลอดภัย 4 ชั้นทั้งขาเข้าและขาออก

## สถาปัตยกรรม

ระบบมี 3 บริการ แต่ละบริการจัดโค้ดแบบ **Model – Controller – Service** เหมือนกัน

```
Browser ──► app    Chat API :8000 (FastAPI)
              ├─► guard  Guard Service :8001 ── Blocklist → Business Rules → Prompt Guard 2 → Safety Classifier
              ├─► rag    RAG Server :9621 (LightRAG) ── knowledge graph + vector · embedding bge-m3 ในเครื่อง
              ├─► Vision ── Gemini 3.1 Flash Lite (รูป → JSON)
              └─► Chat LLM ── Gemini 3.1 Flash Lite (สำรอง: gpt-oss-120b บน Groq)
```

| ชั้น | หน้าที่ |
|---|---|
| **controllers/** | รับ HTTP request → ตรวจ input → เรียก service → ส่ง response (ไม่มีตรรกะธุรกิจ) |
| **services/** | ตรรกะหลัก: ลำดับการทำงาน, เรียก LLM / RAG / Guard, กฎของร้าน |
| **models/** | โครงสร้างข้อมูล (schemas) และส่วนอ่านข้อมูล (ต้นไม้, คำสั่งซื้อ, session) |
| **views/** | หน้าเว็บ (เฉพาะ app) |

## โครงสร้างไฟล์

```
chatbot/
├── app/                         ← Chat API :8000
│   ├── main.py                  สร้างแอป + ผูก controller
│   ├── config.py                ค่าตั้งจาก .env
│   ├── controllers/
│   │   ├── page_controller.py   GET /                       หน้าเว็บ
│   │   ├── chat_controller.py   POST /api/v1/chat[/stream|/reset]
│   │   ├── order_controller.py  POST /api/v1/orders/lookup
│   │   └── system_controller.py GET  /api/v1/health, /api/v1/models
│   ├── services/
│   │   ├── chat_service.py      ★ ลำดับ Guard → Vision → RAG → LLM → Guard + จับเวลา
│   │   ├── llm_service.py       เรียก LLM แบบ OpenAI-compatible + ตัวสำรอง + แปล error เป็นภาษาไทย
│   │   ├── vision_service.py    รูป → Base64 → JSON
│   │   ├── rag_service.py       เรียก RAG Server
│   │   ├── guard_service.py     เรียก Guard Service (fail-closed)
│   │   ├── product_service.py   การ์ดสินค้า (ราคาจาก CSV)
│   │   ├── order_service.py     สถานะคำสั่งซื้อ (LLM ไม่เห็นข้อมูลลูกค้า)
│   │   └── http_client.py       HTTP client ที่ใช้ร่วมกัน
│   ├── models/
│   │   ├── schemas.py           GuardResult, RAGResult, OrderStatus, OrderLookupRequest
│   │   ├── plant_repository.py  อ่าน data/plants.csv
│   │   ├── order_repository.py  อ่าน data/orders_mock.json
│   │   └── session_store.py     ประวัติแชท + rate limit
│   ├── views/templates/index.html, views/static/{css,js}/
│   └── prompts/                 chat_system.md, vision_system.md
│
├── guard/                       ← Guard Service :8001
│   ├── main.py, config.py
│   ├── controllers/check_controller.py   POST /check (ลำดับ 4 ชั้น + fail-closed)
│   ├── services/rule_service.py          ชั้น 1–2 Blocklist + Business Rules (ไม่ใช้โมเดล)
│   ├── services/classifier_service.py    ชั้น 3–4 Prompt Guard 2 + Safety Classifier
│   ├── models/schemas.py                 CheckRequest, CheckResponse
│   ├── data/blocklist.txt
│   └── tests/test_rule_service.py        34 กรณี
│
├── rag/                         ← RAG Server :9621 (โปรเจกต์ uv แยก)
│   ├── main.py
│   ├── controllers/query_controller.py   POST /query, GET /health
│   ├── services/query_service.py         ค้นแล้วประกอบ context
│   ├── services/rag_engine.py            ตั้งค่า LightRAG + LLM ตัวสำรอง (ใช้ร่วมกับสคริปต์ index)
│   ├── services/embedding_service.py     bge-m3 ด้วย onnxruntime
│   ├── models/schemas.py                 QueryRequest, QueryResponse
│   ├── scripts/index_kb.py, download_model.py
│   └── storage/                          โมเดล + knowledge graph (ระบบสร้างเอง ไม่ขึ้น git)
│
├── data/                        ← ข้อมูลร้าน
│   ├── plants.csv               ★ ข้อมูลต้นไม้แหล่งเดียว
│   ├── orders_mock.json         คำสั่งซื้อจำลอง
│   └── knowledge_base/*.md      คลังความรู้ 9 ไฟล์ (02, 09 สร้างจาก CSV)
├── scripts/                     build_plants_kb.py, check_keys.py
├── eval/                        ชุดทดสอบ 10/5/5 + ผลลัพธ์
├── docs/                        เอกสารโครงงาน
├── start.ps1                    เปิดทั้ง 3 บริการ
└── .env                         API key (ไม่ขึ้น git)
```

## ติดตั้ง (Windows / PowerShell)

ต้องมี [uv](https://docs.astral.sh/uv/) · API key ฟรี 2 ตัว: [Google AI Studio](https://aistudio.google.com/apikey) และ [Groq](https://console.groq.com/keys)

```powershell
uv sync                                      # ติดตั้ง Chat API + Guard
Copy-Item .env.example .env                  # ใส่ LLM_API_KEY และ GROQ_API_KEY
cd rag; uv sync
Copy-Item .env.example .env                  # ใส่ key AI Studio ใน LLM_BINDING_API_KEY และ Groq ใน INDEX_FALLBACK_API_KEY
uv run python -m scripts.download_model      # โหลดโมเดล embedding bge-m3 (ONNX int8, 568 MB) ครั้งเดียว
uv run python -m scripts.index_kb            # index คลังความรู้ครั้งแรก (~10–40 นาที ตามความว่างของ Gemini)
cd ..
```

ถ้าแก้ข้อมูลต้นไม้: แก้ `data/plants.csv` → `uv run python scripts/build_plants_kb.py` → `cd rag; uv run python -m scripts.index_kb --reset`

## รัน

```powershell
.\start.ps1        # เปิด RAG :9621, Guard :8001, Chat API :8000 แล้วเปิดเบราว์เซอร์
```

หรือเปิดทีละตัว 3 หน้าต่าง (ใช้ `python -m uvicorn` เพราะ Smart App Control อาจบล็อก `uvicorn.exe`):

```powershell
cd rag; uv run python -m uvicorn main:app --port 9621
uv run python -m uvicorn guard.main:app --port 8001
uv run python -m uvicorn app.main:app --port 8000
```

ตรวจสถานะ: http://localhost:8000/api/v1/health · เอกสาร API อัตโนมัติ: http://localhost:8000/docs

## ทดสอบ

```powershell
uv run pytest guard/tests -q            # กฎของ Guard (ไม่ใช้โควต้า API)
uv run python eval/run_eval.py          # ชุดทดสอบ 10 คำถาม / 5 ภาพ / 5 ความปลอดภัย → eval/results/
uv run python eval/compare.py baseline after   # เทียบผลก่อน-หลังปรับปรุง
uv run python scripts/check_keys.py     # ทดสอบ API key และชื่อโมเดล
```

ภาพทดสอบอยู่ที่ `eval/images/` (สลิปเป็นสลิปจำลอง `slip_mock.html`)

## API

| Method | Path | Controller | หน้าที่ |
|---|---|---|---|
| GET | `/` | page | หน้าแชท |
| GET | `/api/v1/health` | system | สถานะ API, RAG, Guard, API key |
| GET | `/api/v1/models` | system | รายชื่อโมเดลของผู้ให้บริการ |
| POST | `/api/v1/chat/stream` | chat | แชทจากหน้าเว็บ (form: `message`, `image?`) → SSE |
| POST | `/api/v1/chat` | chat | แชทแบบรอคำตอบเต็ม (ใช้ทดสอบ) → JSON |
| POST | `/api/v1/chat/reset` | chat | ล้างประวัติแชทของ session |
| POST | `/api/v1/orders/lookup` | order | `{order_id, phone_last4}` → สถานะจัดส่ง |
| POST | `:8001/check` | guard | `{message, direction, context?}` → `{result, layer, categories, msg}` |
| POST | `:9621/query` | rag | `{query, mode}` → `{response: context, references}` |

## ปัญหาที่พบจริงระหว่างพัฒนา

| ปัญหา | วิธีแก้ |
|---|---|
| Gemini ตอบ 503 "high demand" บ่อย หรือช้า 10–25 วินาที | Chat LLM / ตัวสกัด keyword สลับไป gpt-oss-120b บน Groq อัตโนมัติ |
| Gemma 4 ปิดโหมดคิดไม่ได้ (6–180 วินาที) และใส่ `<thought>` ที่มีข้อความซ้ำ | ไม่ใช้เป็นตัวหลัก · ตัด `<thought>` ทิ้งถ้าใช้ |
| Gemini Embedding ฟรีนับ 1 ข้อความ = 1 request (1,000/วัน) แต่ index ครั้งเดียวใช้ ~800 | embedding ในเครื่องด้วย bge-m3 |
| Windows Smart App Control บล็อก DLL ของ torch, mmh3, hf_xet และ `uvicorn.exe` | ใช้ onnxruntime + tokenizers โดยตรง · ดาวน์โหลดผ่าน HTTP แบ่งหลายส่วน · รันด้วย `python -m uvicorn` |
| onnxruntime ช้าลงเมื่อใช้หลาย thread บน CPU แบบ P-core/E-core | ตั้ง 1 thread (เร็วขึ้น 13 เท่า) |

## โควต้าฟรีที่ต้องระวัง

Gemini 3.1 Flash Lite: 15 ครั้ง/นาที, 500 ครั้ง/วัน — 1 ข้อความใช้ ~2–3 ครั้ง (LLM + keyword ของ RAG + รูป)
Safety classifier อยู่บน Groq จึงไม่กินโควต้านี้ · ถ้า Gemini ไม่ว่าง แชทจะสลับไป gpt-oss-120b บน Groq อัตโนมัติ
