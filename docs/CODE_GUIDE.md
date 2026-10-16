# คู่มืออธิบายโค้ด — บ้านใบเขียว AI

> อธิบายทีละไฟล์ว่าบรรทัดไหนทำอะไร · กดลิงก์ในตารางเพื่อเปิดไฟล์ที่บรรทัดนั้นใน VS Code
> (เปิดไฟล์นี้แบบ Preview: คลิกขวาที่ไฟล์ → Open Preview หรือกด `Ctrl+Shift+V`)

---

## 0. อ่านจากตรงไหนก่อน

ถ้าเวลาน้อย อ่าน 5 ไฟล์นี้ตามลำดับก็เข้าใจทั้งระบบ:

1. [app/services/chat_service.py](../app/services/chat_service.py) — หัวใจของระบบ ลำดับ 5 ขั้นของ 1 ข้อความ
2. [app/controllers/chat_controller.py](../app/controllers/chat_controller.py) — ข้อความเข้ามาทางไหน ตรวจอะไรก่อน
3. [app/services/llm_service.py](../app/services/llm_service.py) — เรียก LLM ยังไง ตัวสำรองทำงานยังไง
4. [guard/controllers/check_controller.py](../guard/controllers/check_controller.py) — ด่านความปลอดภัย 4 ชั้น
5. [rag/services/query_service.py](../rag/services/query_service.py) — ค้นคลังความรู้แล้วได้อะไรกลับมา

### เส้นทางของ 1 ข้อความ

```
เบราว์เซอร์  chat.js send()
   │ POST /api/v1/chat/stream (ข้อความ + รูป)
   ▼
chat_controller.chat_stream()      ตรวจ input · rate limit · session
   ▼
chat_service.run()                 ★ คุมลำดับทั้งหมด ส่งสถานะทีละขั้นกลับไป
   ├─ ① guard_service.check(input)  ──HTTP──►  guard: check_controller.check()
   ├─ ② vision_service.analyze()    ──HTTP──►  Gemini (ถ้ามีรูป)
   ├─ ③ rag_service.retrieve()      ──HTTP──►  rag: query_controller → query_service
   ├─    order_service.as_context() (ถ้ามีเลขคำสั่งซื้อ)
   ├─ ④ llm_service.chat()          ──HTTP──►  Gemini (สำรอง Groq)
   └─ ⑤ guard_service.check(output) ──HTTP──►  guard
   ▼
chat.js renderAnswer()             แสดงคำตอบ + การ์ดสินค้า + เวลา
```

### หลักของ Model – Controller – Service

| ชั้น | ทำอะไร | ไม่ทำอะไร |
|---|---|---|
| **controller** | รับ HTTP request, ตรวจรูปแบบ input, เรียก service, แปลงผลเป็น response | ไม่มีตรรกะธุรกิจ |
| **service** | ตรรกะหลัก: ลำดับงาน, เรียก API ภายนอก, กฎของร้าน | ไม่รู้จัก HTTP request/response ของลูกค้า |
| **model** | โครงสร้างข้อมูล (schemas) และอ่านข้อมูลจากไฟล์ | ไม่มีตรรกะ |

---

## 1. Chat API — โฟลเดอร์ `app/` (พอร์ต 8000)

### 1.1 [app/main.py](../app/main.py) — จุดเริ่มต้น

| บรรทัด | ทำอะไร |
|---|---|
| [1–13](../app/main.py#L1) | คำอธิบายไฟล์ + วิธีรัน + โครงสร้างโฟลเดอร์ |
| [20](../app/main.py#L20) | import controller ทั้ง 4 ตัว |
| [24](../app/main.py#L24) | สร้างแอป FastAPI |
| [25](../app/main.py#L25) | ให้ไฟล์ใน `views/static/` (css, js) เปิดได้ที่ URL `/static/...` |
| [27–30](../app/main.py#L27) | ผูก controller เข้ากับแอป — URL ทั้งหมดมาจาก 4 บรรทัดนี้ |

### 1.2 [app/config.py](../app/config.py) — ค่าตั้งทั้งหมด

| บรรทัด | ทำอะไร |
|---|---|
| [12](../app/config.py#L12) | ตำแหน่งไฟล์ `.env` (โฟลเดอร์โปรเจกต์) |
| [15–16](../app/config.py#L15) | `Settings` สืบทอด `BaseSettings` ของ pydantic-settings → อ่านค่าจาก `.env` ให้อัตโนมัติ ชื่อตัวแปรตรงกับชื่อใน `.env` |
| [19–25](../app/config.py#L19) | LLM หลัก: URL, key, ชื่อโมเดล, temperature 0.2, รอได้ 10 วินาทีก่อนสลับตัวสำรอง |
| [28–31](../app/config.py#L28) | LLM สำรอง (Groq gpt-oss-120b) |
| [34–36](../app/config.py#L34) | URL ของ RAG และ Guard ที่รันในเครื่อง |
| [39–41](../app/config.py#L39) | ข้อจำกัด: ข้อความ 1,000 ตัวอักษร, รูป 5 MB, 20 ครั้ง/นาที |
| [43–46](../app/config.py#L43) | `missing_keys()` บอกว่ายังไม่ได้ใส่ key ตัวไหน (ใช้ใน `/health`) |
| [48–54](../app/config.py#L48) | `key_for()` เลือก key ตาม URL — ถ้าเป็น groq.com ใช้ GROQ key ไม่งั้นใช้ AI Studio key |
| [57–59](../app/config.py#L57) | `get_settings()` + `@lru_cache` = อ่าน `.env` ครั้งเดียวแล้วใช้ซ้ำ |

> **ที่ควรรู้:** `SecretStr` ทำให้ key ไม่โผล่ตอน print/log ต้องเรียก `.get_secret_value()` ถึงจะได้ค่าจริง

---

### 1.3 Controllers

#### [app/controllers/chat_controller.py](../app/controllers/chat_controller.py) — แชท

| บรรทัด | ทำอะไร |
|---|---|
| [18](../app/controllers/chat_controller.py#L18) | `router` กำหนด prefix `/api/v1/chat` — ทุก endpoint ในไฟล์ขึ้นต้นด้วยนี้ |
| [23–28](../app/controllers/chat_controller.py#L23) | `get_sid()` อ่าน session id จาก cookie ถ้ายังไม่มีสร้างใหม่ |
| [31–33](../app/controllers/chat_controller.py#L31) | `set_cookie()` ฝาก cookie `bbk_session` (httponly = JavaScript อ่านไม่ได้, อายุ 1 วัน) |
| [36–52](../app/controllers/chat_controller.py#L36) | `validate()` ตรวจ input: ความยาว (422), ชนิดไฟล์ (415), ขนาดรูป (413), ห้ามว่างทั้งคู่ (422) |
| [55–57](../app/controllers/chat_controller.py#L55) | `check_rate()` เกิน 20 ครั้ง/นาที → 429 |
| [62–75](../app/controllers/chat_controller.py#L62) | **`POST /stream`** (หน้าเว็บใช้) — ตรวจ → เรียก `chat_service.run()` |
| [68–70](../app/controllers/chat_controller.py#L68) | แปลงแต่ละ event เป็นรูปแบบ SSE: `data: {json}\n\n` |
| [72–73](../app/controllers/chat_controller.py#L72) | `StreamingResponse` ส่งทีละ event ไม่รอจนจบ (`no-cache` กันเบราว์เซอร์เก็บ) |
| [78–97](../app/controllers/chat_controller.py#L78) | **`POST ""`** (สคริปต์ทดสอบใช้) — รัน pipeline เดียวกัน แต่รวม event เป็น JSON ก้อนเดียว · error → 503 |
| [81](../app/controllers/chat_controller.py#L81) | รับ `session_id` จาก form ได้ (สคริปต์ทดสอบใช้ session ใหม่ทุกข้อ) |
| [100–105](../app/controllers/chat_controller.py#L100) | **`POST /reset`** ล้างประวัติแชทของ session |

> **อาจโดนถาม:** ทำไมมี 2 endpoint แชท? → `/stream` ให้หน้าเว็บแสดงสถานะทีละขั้นระหว่างรอ (UX) ส่วน `/chat` ให้สคริปต์ทดสอบได้ JSON ที่อ่านง่าย ทั้งสองเรียก `chat_service.run()` ตัวเดียวกัน ผลจึงเหมือนกัน

#### [app/controllers/order_controller.py](../app/controllers/order_controller.py) — คำสั่งซื้อ

| บรรทัด | ทำอะไร |
|---|---|
| [16–21](../app/controllers/order_controller.py#L16) | `POST /api/v1/orders/lookup` รับ `OrderLookupRequest` (pydantic ตรวจรูปแบบ `BK-xxxx` และเลข 4 หลักให้) → ไม่พบ/เบอร์ไม่ตรง = 404 |

#### [app/controllers/system_controller.py](../app/controllers/system_controller.py) — ระบบ

| บรรทัด | ทำอะไร |
|---|---|
| [16–31](../app/controllers/system_controller.py#L16) | `GET /api/v1/health` เช็ก RAG + Guard + key → `ok` เมื่อครบทุกส่วน ไม่งั้น `degraded` (หน้าเว็บใช้แสดงจุดเขียว/แดง) |
| [33–39](../app/controllers/system_controller.py#L33) | `GET /api/v1/models` รายชื่อโมเดลของผู้ให้บริการ (ตามสัปดาห์ 7) |

#### [app/controllers/page_controller.py](../app/controllers/page_controller.py) — หน้าเว็บ

| บรรทัด | ทำอะไร |
|---|---|
| [15](../app/controllers/page_controller.py#L15) | ตั้งโฟลเดอร์ template = `views/templates/` |
| [18–23](../app/controllers/page_controller.py#L18) | `GET /` ส่ง `index.html` พร้อมค่า `max_chars`, `max_image_mb` ไปใส่ในหน้า (Jinja2 `{{ }}`) |

---

### 1.4 Services

#### [app/services/chat_service.py](../app/services/chat_service.py) — ★ ลำดับ 5 ขั้น

![แผนภาพการทำงานของ run()](report/img/chat_flow.png)

> ภาพใหญ่: [docs/report/img/chat_flow.png](report/img/chat_flow.png) · แก้ภาพที่ [chat_flow.html](report/chat_flow.html)

| บรรทัด | ทำอะไร |
|---|---|
| [20](../app/services/chat_service.py#L20) | อ่าน system prompt จาก `prompts/chat_system.md` ครั้งเดียวตอนเริ่ม |
| [22–28](../app/services/chat_service.py#L22) | ชื่อแต่ละขั้นภาษาไทย (แสดงบนหน้าเว็บ) |
| [30–34](../app/services/chat_service.py#L30) | ปุ่มคำถามแนะนำตามชนิดรูป |
| [41–49](../app/services/chat_service.py#L41) | `build_user_content()` ประกอบข้อความให้ LLM: `<ข้อมูลร้าน>`, `<สถานะคำสั่งซื้อ>`, `<สิ่งที่เห็นในรูป>`, `<คำถามลูกค้า>` — ใส่แท็กแยกข้อมูลอ้างอิงออกจากคำถาม กัน prompt injection ที่ซ่อนในข้อมูล |
| [52](../app/services/chat_service.py#L52) | `run()` เป็น **async generator** — `yield` event ออกไปทีละตัวระหว่างทำงาน |
| [53–57](../app/services/chat_service.py#L53) | เก็บเวลาที่แต่ละขั้นใช้ (`timings`) |
| [60–71](../app/services/chat_service.py#L60) | **① Guard ขาเข้า** — ไม่ปลอดภัย → ส่งข้อความปฏิเสธแล้ว `return` ทันที (ไม่เรียก RAG/LLM เลย) |
| [73–82](../app/services/chat_service.py#L73) | **② Vision** — ทำเฉพาะเมื่อมีรูป · ได้ JSON แล้วแปลงเป็นข้อความสั้น (`seen`) |
| [84–90](../app/services/chat_service.py#L84) | **③ RAG** — query = คำถาม + `search_query` ที่ Vision สรุปจากรูป |
| [92–96](../app/services/chat_service.py#L92) | ถ้าข้อความมี `BK-xxxx` → ระบบค้นสถานะเอง ส่งให้ LLM เฉพาะสถานะ |
| [98–105](../app/services/chat_service.py#L98) | **④ LLM** — system prompt + ประวัติแชท + ข้อความที่ประกอบแล้ว |
| [107–112](../app/services/chat_service.py#L107) | **⑤ Guard ขาออก** — ส่ง `context` ไปด้วยเพื่อให้ Guard ตรวจว่าราคาในคำตอบมีในข้อมูลจริง |
| [114–117](../app/services/chat_service.py#L114) | คำตอบไม่ผ่าน → แสดงข้อความปฏิเสธแทน (ไม่บันทึกประวัติ) |
| [118–123](../app/services/chat_service.py#L118) | คำตอบผ่าน → บันทึกประวัติ + หาการ์ดสินค้า + แหล่งอ้างอิง |
| [125](../app/services/chat_service.py#L125) | event `done` พร้อมเวลารวม |
| [127–133](../app/services/chat_service.py#L127) | จับ error แต่ละแบบ → event `error` ภาษาไทย (**fail-closed**: พังขั้นไหนก็ไม่ตอบ) |

> **อาจโดนถาม (Q&A ข้อ 1):** "LLM ทำงานยังไงตั้งแต่ input ถึง output" → ไล่บรรทัด 60 → 125 ของไฟล์นี้

#### [app/services/llm_service.py](../app/services/llm_service.py) — เรียก LLM

| บรรทัด | ทำอะไร |
|---|---|
| [16](../app/services/llm_service.py#L16) | regex ลบบล็อก `<thought>`/`<think>` ที่บางโมเดลใส่มา |
| [19–27](../app/services/llm_service.py#L19) | แปลงรหัส error เป็นภาษาไทย (สัปดาห์ 7) |
| [30–34](../app/services/llm_service.py#L30) | `LLMError` เก็บรหัส status + ข้อความภาษาไทย |
| [37–39](../app/services/llm_service.py#L37) | `build_messages()` = `[system] + ประวัติ + [user]` รูปแบบมาตรฐาน OpenAI |
| [42–56](../app/services/llm_service.py#L42) | `_post()` ยิง `POST {base_url}/chat/completions` |
| [43–44](../app/services/llm_service.py#L43) | ถ้าเป็น gpt-oss (reasoning model) สั่ง `reasoning_effort: low` ให้คิดสั้นเพื่อตอบเร็ว |
| [49–54](../app/services/llm_service.py#L49) | timeout → 504, เชื่อมต่อไม่ได้ → 503, status ไม่ใช่ 200 → ส่งรหัสนั้นต่อ |
| [55–56](../app/services/llm_service.py#L55) | ดึงข้อความจาก `choices[0].message.content` |
| [59–84](../app/services/llm_service.py#L59) | **`chat()`** ฟังก์ชันที่ service อื่นเรียก |
| [66–73](../app/services/llm_service.py#L66) | สร้าง body: model, messages, temperature, max_tokens, (json_mode สำหรับ Vision) |
| [74–78](../app/services/llm_service.py#L74) | เรียกตัวหลัก โดยจำกัดเวลา 10 วินาทีถ้ามีตัวสำรอง |
| [79–82](../app/services/llm_service.py#L79) | ได้ 429/500/503/504 → log แล้วไปตัวสำรอง · error อื่น (เช่น 401 key ผิด) → ส่งต่อไม่สลับ |
| [83–84](../app/services/llm_service.py#L83) | เรียกตัวสำรอง (Groq gpt-oss-120b) ด้วย body เดิม เปลี่ยนแค่ชื่อโมเดล |
| [87–93](../app/services/llm_service.py#L87) | `list_models()` เรียก `GET /models` |

> **อาจโดนถาม (Q&A ข้อ 2):** ทำไมใช้ OpenAI-compatible → สลับ Gemini / Groq / LM Studio ได้ด้วยการแก้ `.env` 3 บรรทัด ไม่ต้องแก้โค้ด และทำตัวสำรองข้ามผู้ให้บริการได้ง่าย

#### [app/services/vision_service.py](../app/services/vision_service.py) — วิเคราะห์รูป

| บรรทัด | ทำอะไร |
|---|---|
| [15–17](../app/services/vision_service.py#L15) | prompt โหมดรูป, ชนิดไฟล์ที่รับ, regex ลบ ```` ``` ```` |
| [20–21](../app/services/vision_service.py#L20) | `to_data_url()` รูป → Base64 → `data:image/png;base64,....` (สัปดาห์ 10) |
| [24–33](../app/services/vision_service.py#L24) | `parse_json()` ลบ code fence แล้วแปลง JSON · ถ้ามีข้อความปน ดึงเฉพาะ `{...}` |
| [36–54](../app/services/vision_service.py#L36) | `analyze()` ส่ง content 2 ส่วน: ข้อความลูกค้า + `image_url` |
| [44–53](../app/services/vision_service.py#L44) | JSON เสีย → ลองใหม่อีก 1 ครั้ง |
| [46](../app/services/vision_service.py#L46) | `allow_fallback=False` เพราะตัวสำรองบน Groq ดูรูปไม่ได้ |
| [57–77](../app/services/vision_service.py#L57) | `describe()` JSON → ข้อความสั้น เช่น "สลิปโอนเงิน: ยอด 1,460 บาท, วันที่ ..." |

> **อาจโดนถาม (Q&A ข้อ 4):** "Vision ประมวลผลภาพยังไง" → รูป → Base64 (บรรทัด 20) → ส่งพร้อม prompt ที่บังคับให้ตอบเป็น JSON ([prompts/vision_system.md](../app/prompts/vision_system.md)) → แปลง JSON → ใช้ `search_query` ค้น RAG และใช้ `seen` ใส่ใน prompt ของ LLM

#### [app/services/rag_service.py](../app/services/rag_service.py) — เรียก RAG

| บรรทัด | ทำอะไร |
|---|---|
| [14–24](../app/services/rag_service.py#L14) | ชื่อไฟล์คลังความรู้ → ชื่อภาษาไทยที่แสดงเป็น "อ้างอิง" |
| [31–49](../app/services/rag_service.py#L31) | `retrieve()` ยิง `POST :9621/query` → ได้ context + รายชื่อไฟล์ที่มา |
| [36–43](../app/services/rag_service.py#L36) | เชื่อมต่อไม่ได้ / error / ได้ข้อมูลว่าง → `RAGError` (chat_service จะไม่ตอบ) |
| [52–58](../app/services/rag_service.py#L52) | `health()` สำหรับ `/api/v1/health` |

#### [app/services/guard_service.py](../app/services/guard_service.py) — เรียก Guard

| บรรทัด | ทำอะไร |
|---|---|
| [17–28](../app/services/guard_service.py#L17) | `check()` ยิง `POST :8001/check` → แปลงเป็น `GuardResult` |
| [22–25](../app/services/guard_service.py#L22) | เรียกไม่ได้ หรือ Guard ตอบ 502 → `GuardUnavailable` = **fail-closed** |

#### [app/services/product_service.py](../app/services/product_service.py) — การ์ดสินค้า

| บรรทัด | ทำอะไร |
|---|---|
| [9–13](../app/services/product_service.py#L9) | ไอคอนตามหมวดต้นไม้ |
| [20–47](../app/services/product_service.py#L20) | `find_products()` หาชื่อต้นไม้ที่อยู่ในคำตอบ |
| [28–31](../app/services/product_service.py#L28) | ต้องเจอราคาจริงจาก CSV ภายใน 160 ตัวอักษรหลังชื่อ ถึงจะแสดงการ์ด |
| [32](../app/services/product_service.py#L32) | แทนชื่อที่เจอแล้วด้วย □ — กัน "ลิ้นมังกร" ถูกจับซ้ำจาก "ลิ้นมังกรขอบทอง" |

> **ที่ควรรู้:** ราคาบนการ์ดมาจาก CSV ไม่ได้มาจาก LLM ถ้า LLM พูดราคาผิด การ์ดจะไม่ขึ้น

#### [app/services/order_service.py](../app/services/order_service.py) — คำสั่งซื้อ

| บรรทัด | ทำอะไร |
|---|---|
| [14–15](../app/services/order_service.py#L14) | regex จับ `BK-0002` และเบอร์ 4 ตัวท้าย ("เบอร์ท้าย 0002") |
| [18–23](../app/services/order_service.py#L18) | `lookup()` เบอร์ 4 ตัวท้ายต้องตรง → คืน `OrderStatus` (ไม่มีชื่อ/ที่อยู่/เบอร์) |
| [26–33](../app/services/order_service.py#L26) | `extract_from_text()` ดึงเลขคำสั่งซื้อ + เบอร์จากข้อความแชท |
| [36–48](../app/services/order_service.py#L36) | `as_context()` สร้างข้อความให้ LLM: ไม่มีเบอร์ → ให้ขอเบอร์ / เบอร์ผิด → บอกว่าตรวจไม่ได้ / ถูก → ให้เฉพาะสถานะ |

> **อาจโดนถาม (Q&A ข้อ 5):** least privilege — LLM ไม่เคยเห็นข้อมูลลูกค้า ต่อให้ถูก prompt injection ก็ไม่มีข้อมูลให้หลุด

#### [app/services/http_client.py](../app/services/http_client.py)

| บรรทัด | ทำอะไร |
|---|---|
| [8–12](../app/services/http_client.py#L8) | สร้าง `httpx.AsyncClient` ตัวเดียวใช้ทั้งแอป (connection pooling — ไม่ต้องเปิดการเชื่อมต่อใหม่ทุกครั้ง) |

---

### 1.5 Models

| ไฟล์ | บรรทัด | ทำอะไร |
|---|---|---|
| [schemas.py](../app/models/schemas.py) | [14](../app/models/schemas.py#L14) | `OrderLookupRequest` (pydantic) — ตรวจรูปแบบ `^BK-\d{4}$` อัตโนมัติ ผิด = 422 |
| | [22](../app/models/schemas.py#L22) | `GuardResult` — ผลจาก Guard: safe, หมวด, ข้อความปฏิเสธ, ชั้นที่จับ |
| | [32](../app/models/schemas.py#L32) | `RAGResult` — context + แหล่งอ้างอิง |
| | [39](../app/models/schemas.py#L39) | `OrderStatus` — เฉพาะข้อมูลที่ลูกค้าเห็นได้ |
| [plant_repository.py](../app/models/plant_repository.py) | [10–12](../app/models/plant_repository.py#L10) | แปลง `"6 นิ้ว:350\|10 นิ้ว:890"` → `[("6 นิ้ว",350), ("10 นิ้ว",890)]` |
| | [15–22](../app/models/plant_repository.py#L15) | อ่าน CSV ครั้งเดียว (`lru_cache`) เรียงชื่อยาวก่อน |
| [order_repository.py](../app/models/order_repository.py) | [14–20](../app/models/order_repository.py#L14) | อ่าน `orders_mock.json` · `find_by_id()` (ระบบจริงเปลี่ยนเป็นฐานข้อมูลที่ไฟล์นี้ไฟล์เดียว) |
| [session_store.py](../app/models/session_store.py) | [11–15](../app/models/session_store.py#L11) | เก็บประวัติ 6 รอบล่าสุดต่อ session ใน `deque(maxlen=12)` (เก่าสุดหลุดออกเอง) |
| | [26–29](../app/models/session_store.py#L26) | `append_turn()` บันทึกคำถาม + คำตอบ |
| | [36–45](../app/models/session_store.py#L36) | `allow_request()` rate limit แบบ sliding window: ลบเวลาที่เก่ากว่า 60 วินาที แล้วนับที่เหลือ |

> **อาจโดนถาม (Q&A ข้อ 6):** ผู้ใช้เพิ่ม 10 เท่า → `session_store` เก็บในหน่วยความจำของ server เครื่องเดียว ต้องย้ายไป Redis ถึงจะเพิ่ม server ได้ · และโควต้าฟรีของ Gemini (500/วัน) จะหมดก่อน

---

### 1.6 Views

#### [app/views/static/js/chat.js](../app/views/static/js/chat.js) — ฝั่งเบราว์เซอร์

| บรรทัด | ทำอะไร |
|---|---|
| [4–15](../app/views/static/js/chat.js#L4) | อ้างอิง element ในหน้า + ค่าคงที่ (ชนิดไฟล์, ลำดับขั้น) |
| [18–26](../app/views/static/js/chat.js#L18) | `renderMarkdown()` แปลง Markdown ด้วย marked แล้ว **DOMPurify ตัด HTML/สคริปต์อันตราย** ห้าม `<img>` `<a>` (OWASP LLM10) |
| [38–53](../app/views/static/js/chat.js#L38) | `setStatus()` / `checkHealth()` จุดสถานะเขียว/แดงที่หัวหน้าเว็บ |
| [56–74](../app/views/static/js/chat.js#L56) | `autoGrow()` ขยายช่องพิมพ์ + นับตัวอักษร · `setBusy()` ล็อกช่องพิมพ์และเปลี่ยนปุ่มส่งเป็น "หยุด" ระหว่างรอ |
| [77–104](../app/views/static/js/chat.js#L77) | แนบรูป: ตรวจชนิด/ขนาดฝั่งเบราว์เซอร์ก่อน (ตรวจซ้ำที่ server อีกรอบ) แสดงตัวอย่างรูป |
| [107–179](../app/views/static/js/chat.js#L107) | **`send()`** หัวใจฝั่งหน้าเว็บ |
| [113–128](../app/views/static/js/chat.js#L113) | แสดงข้อความ/รูปของลูกค้า + กล่องสถานะ 5 ขั้น (ขั้น Vision แสดงเฉพาะเมื่อมีรูป) |
| [135–142](../app/views/static/js/chat.js#L135) | ส่ง `FormData` (ข้อความ + รูป) ไป `/api/v1/chat/stream` · `AbortController` สำหรับปุ่มหยุด |
| [147–165](../app/views/static/js/chat.js#L147) | อ่าน SSE ทีละก้อน: แยกด้วย `\n\n` → ตัด `data: ` → JSON → ทำตาม `type` |
| [167–178](../app/views/static/js/chat.js#L167) | กดหยุด → "หยุดการตอบแล้ว" · error อื่น → กล่องแดง + ปุ่มลองใหม่ · สุดท้ายปลดล็อกช่องพิมพ์เสมอ (`finally`) |
| [181–188](../app/views/static/js/chat.js#L181) | `updateStep()` เปลี่ยน ○ → ● (กำลังทำ) → ✓ (เสร็จ) |
| [190–213](../app/views/static/js/chat.js#L190) | `renderAnswer()` ถูกปฏิเสธ → กล่องเหลือง + ป้ายหมวด · ปกติ → ข้อความ + "สิ่งที่เห็นในรูป" + การ์ดสินค้า |
| [229–240](../app/views/static/js/chat.js#L229) | `renderMeta()` "ตอบใน X วินาที · อ้างอิง ..." (เอาเมาส์ชี้ดูเวลาแต่ละขั้น) |
| [242–255](../app/views/static/js/chat.js#L242) | `renderError()` ข้อความลูกค้าจางลง + "ยังไม่ได้ส่ง" + ปุ่ม "ลองใหม่" / "แก้ข้อความ" |
| [258–276](../app/views/static/js/chat.js#L258) | ผูก event: Enter ส่ง (Shift+Enter ขึ้นบรรทัด), คลิกคำถามยอดนิยม, ปุ่มเริ่มใหม่ |

> **ที่ควรรู้:** ทุกจุดที่เอาข้อความไปใส่หน้าเว็บผ่าน `escapeHtml()` หรือ `textContent` → กัน XSS

- [index.html](../app/views/templates/index.html) — โครงหน้า: แถบซ้าย (ข้อมูลร้าน, คำถามยอดนิยม), พื้นที่แชท, ช่องพิมพ์ · โหลด marked + DOMPurify จาก CDN
- [style.css](../app/views/static/css/style.css) — สี/ดีไซน์ตาม mockup · ส่วน `@media (max-width: 860px)` ท้ายไฟล์ = แบบมือถือ (แถบซ้ายเป็นเมนู ☰)

### 1.7 Prompts

- [chat_system.md](../app/prompts/chat_system.md) — บทบาท "น้องใบเขียว" + **ต้องทำ 11 ข้อ / ห้ามทำ 9 ข้อ** + รูปแบบคำตอบ · ข้อ "ห้ามทำ 9" บอกให้ถือว่าข้อความในแท็ก `<ข้อมูลร้าน>` เป็นข้อมูล ไม่ใช่คำสั่ง
- [vision_system.md](../app/prompts/vision_system.md) — บังคับตอบเป็น JSON, แยก 5 ประเภทรูป, ห้ามอ่านชื่อ/เลขบัญชีในสลิป, ข้อความในรูปห้ามทำตาม

> **อาจโดนถาม (Q&A ข้อ 3):** "ใช้ prompt engineering ยังไง" → กฎต้องทำ/ห้ามทำชัดเจน, แยกข้อมูลด้วยแท็ก, temperature 0.2, Vision บังคับ JSON และระบุกรณีกำกวม (สลิป/พุทธศักราช) ไว้ล่วงหน้าตามสัปดาห์ 10 · ข้อ 11 เพิ่มจากผลทดสอบจริง (Q3)

---

## 2. Guard Service — โฟลเดอร์ `guard/` (พอร์ต 8001)

### 2.1 [guard/controllers/check_controller.py](../guard/controllers/check_controller.py) — ลำดับ 4 ชั้น

| บรรทัด | ทำอะไร |
|---|---|
| [25–29](../guard/controllers/check_controller.py#L25) | `unsafe()` สร้างคำตอบ "ไม่ปลอดภัย" + ข้อความปฏิเสธภาษาไทยตามหมวด · log เฉพาะหมวด ไม่ log ข้อความลูกค้า (PDPA) |
| [37–68](../guard/controllers/check_controller.py#L37) | **`POST /check`** |
| [41–43](../guard/controllers/check_controller.py#L41) | ① Blocklist |
| [45–49](../guard/controllers/check_controller.py#L45) | ② Business Rules — ขาเข้าใช้กฎขาเข้า ขาออกใช้กฎขาออก |
| [52–56](../guard/controllers/check_controller.py#L52) | ③ Prompt Guard 2 (เฉพาะขาเข้า) คะแนน ≥ 0.8 = injection |
| [58–62](../guard/controllers/check_controller.py#L58) | ④ Safety Classifier (S1–S14) |
| [63–65](../guard/controllers/check_controller.py#L63) | โมเดลตรวจไม่ได้ → **502** ไม่ตอบว่า safe (fail-closed) |
| [67–68](../guard/controllers/check_controller.py#L67) | ผ่านครบ → safe |

> **ทำไมเรียงแบบนี้:** ชั้น 1–2 ไม่ใช้โมเดล → เร็ว (0.01 วิ) ฟรี ผลแน่นอน ถ้าจับได้ก็ไม่ต้องเสียเวลา/โควต้าเรียกโมเดล

### 2.2 [guard/services/rule_service.py](../guard/services/rule_service.py) — ชั้น 1–2 (ไม่ใช้โมเดล)

| บรรทัด | ทำอะไร |
|---|---|
| [17–42](../guard/services/rule_service.py#L17) | ข้อความปฏิเสธ + ป้ายหมวดของแต่ละกรณี |
| [45–50](../guard/services/rule_service.py#L45) | `squash()` normalize ภาษาไทย (PyThaiNLP) แล้วลบช่องว่าง/เครื่องหมาย → "พ นั น" กลายเป็น "พนัน" |
| [53–61](../guard/services/rule_service.py#L53) | อ่าน `data/blocklist.txt` แล้วเทียบแบบ squash |
| [65–68](../guard/services/rule_service.py#L65) | regex คำเกี่ยวกับส่วนลด / การอ้างสิทธิ์ (เจ้าของ แอดมิน อนุมัติ) / ต่อราคา / เปอร์เซ็นต์ |
| [70–73](../guard/services/rule_service.py#L70) | regex เลขคำสั่งซื้อ / ข้อมูลส่วนตัว / ลูกค้าคนอื่น |
| [75–81](../guard/services/rule_service.py#L75) | regex prompt injection (ลืมคำสั่ง, system prompt, ตอนนี้คุณคือ..., DAN ฯลฯ) |
| [84–100](../guard/services/rule_service.py#L84) | **`check_input_rules()`** ตรวจตามลำดับ: injection → ส่วนลด (+อ้างสิทธิ์ หรือ % > 10) → ต่อราคา → ข้อมูลลูกค้า |
| [104–112](../guard/services/rule_service.py#L104) | regex จำนวนเงิน (ตัวเลข + "บาท"), เบอร์โทร, การรับปาก ("ยืนยันว่าได้รับเงินแล้ว") |
| [119–131](../guard/services/rule_service.py#L119) | `known_amounts()` รวบรวม**ราคาที่มีจริง**: ตัวเลขที่ตามด้วย "บาท" ในคลังความรู้ + ราคาใน CSV |
| [134–141](../guard/services/rule_service.py#L134) | ชื่อ/ที่อยู่ลูกค้าจำลอง ห้ามโผล่ในคำตอบ |
| [144–164](../guard/services/rule_service.py#L144) | `_computed()` ยอมให้ตัวเลขที่ "คำนวณจากตัวเลขในบรรทัดเดียวกัน" เช่น 35 × 5 = 175 แต่ตัวตั้งต้องมีราคาจริงอย่างน้อย 1 ตัว |
| [167–187](../guard/services/rule_service.py#L167) | **`check_output_rules()`** ตรวจคำตอบ: ข้อมูลลูกค้า → เบอร์โทรที่ไม่ใช่ของร้าน → รับปากเรื่องเงิน → ราคาที่ไม่มีจริง |
| [173–178](../guard/services/rule_service.py#L173) | ถ้ามี "ไม่"/"ยัง" อยู่ก่อนหน้า 15 ตัวอักษร ไม่นับเป็นการรับปาก (แก้ false positive ที่พบจริง) |

> **อาจโดนถาม (Q&A ข้อ 5):** Llama Guard จับเนื้อหาอันตรายทั่วไป แต่ไม่รู้กติการ้าน ("ลด 50%" ไม่ใช่เนื้อหาอันตราย) → ไฟล์นี้เติมส่วนที่ขาด · มี unit test 34 กรณีทั้ง "ต้องบล็อก" และ "ต้องผ่าน"

### 2.3 [guard/services/classifier_service.py](../guard/services/classifier_service.py) — ชั้น 3–4 (ใช้โมเดล)

| บรรทัด | ทำอะไร |
|---|---|
| [20–36](../guard/services/classifier_service.py#L20) | หมวด S1–S14 ตาม Llama Guard 4 |
| [39](../guard/services/classifier_service.py#L39) | บล็อกทุกหมวดยกเว้น S6 (คำแนะนำทางการแพทย์) — ให้ prompt ปฏิเสธสุภาพแทน เพราะลูกค้าถามได้ปกติ |
| [41–50](../guard/services/classifier_service.py#L41) | prompt ให้โมเดลจัดหมวด + บอกว่าคำถามซื้อของปกติ (ต้นไหนมีพิษ, ต้นไม้ตาย, ขอคืนเงิน) ถือว่าปลอดภัย กัน false positive |
| [57–70](../guard/services/classifier_service.py#L57) | `prompt_guard()` ส่งข้อความให้ Llama Prompt Guard 2 บน Groq → คืนคะแนน 0–1 |
| [73–84](../guard/services/classifier_service.py#L73) | `_classify()` เรียกโมเดลจัดหมวดแบบ JSON |
| [87–111](../guard/services/classifier_service.py#L87) | `safety()` ลองตัวหลัก (gpt-oss-20b บน Groq) → ล้มเหลวลองตัวสำรอง (Gemini) → ยังล้มเหลว = error (fail-closed) |

### 2.4 ไฟล์อื่นใน guard/

| ไฟล์ | ทำอะไร |
|---|---|
| [main.py](../guard/main.py) | สร้างแอป + CORS (อนุญาตเฉพาะ :8000) + ผูก controller |
| [config.py](../guard/config.py) | ค่าตั้งของ Guard (อ่าน `.env` ไฟล์เดียวกับ app) · `key_for()` เลือก key ตาม URL |
| [models/schemas.py](../guard/models/schemas.py) | `CheckRequest` (message ≤ 8,000 ตัวอักษร, direction input/output) · `CheckResponse` |
| [data/blocklist.txt](../guard/data/blocklist.txt) | คำต้องห้าม 1 บรรทัด/คำ (ไม่ใส่คำปกติอย่าง "แพง" กัน false positive) |
| [tests/test_rule_service.py](../guard/tests/test_rule_service.py) | unit test 34 กรณี — รัน `uv run pytest guard/tests -q` |

---

## 3. RAG Server — โฟลเดอร์ `rag/` (พอร์ต 9621)

### 3.1 [rag/services/query_service.py](../rag/services/query_service.py) — ค้นแล้วประกอบ context

| บรรทัด | ทำอะไร |
|---|---|
| [14–29](../rag/services/query_service.py#L14) | `build_context()` เรียง: **ข้อความต้นฉบับ (chunk) ก่อน** → สรุป entity 15 ตัว → ความสัมพันธ์ 10 ตัว · ต้นฉบับมาก่อนเพราะมีราคาตรงตัว |
| [32](../rag/services/query_service.py#L32) | `query()` เรียก `rag.aquery_data()` ของ LightRAG — คืนข้อมูลที่ค้นเจอโดยไม่ให้ LightRAG สร้างคำตอบเอง |

### 3.2 [rag/services/rag_engine.py](../rag/services/rag_engine.py) — ตั้งค่า LightRAG

| บรรทัด | ทำอะไร |
|---|---|
| [18–19](../rag/services/rag_engine.py#L18) | โหลด `rag/.env` (ต้องก่อน import LightRAG) |
| [27–33](../rag/services/rag_engine.py#L27) | ค่าตั้ง LLM หลัก/สำรอง และโฟลเดอร์เก็บคลัง (`storage/lightrag`) |
| [43–63](../rag/services/rag_engine.py#L43) | `set_min_interval()` + `_throttle()` ตอน index เว้นช่วง 4.5 วินาทีต่อครั้ง (โควต้า 15/นาที) · `set_primary_timeout()` ตอนค้นให้ตัวหลักรอได้ 8 วินาที |
| [66–106](../rag/services/rag_engine.py#L66) | **`llm_func()`** ฟังก์ชันที่ LightRAG เรียกเมื่อต้องใช้ LLM (สกัด entity ตอน index, สกัด keyword ตอนค้น) |
| [76–84](../rag/services/rag_engine.py#L76) | ลองครั้งคู่ = ตัวหลัก (Gemini) ครั้งคี่ = ตัวสำรอง (Groq) สลับกันจนสำเร็จ (สูงสุด 6 ครั้ง) |
| [98](../rag/services/rag_engine.py#L98) | ตัดบล็อก `<thought>` ทิ้ง |
| [109–111](../rag/services/rag_engine.py#L109) | `embed_func()` เรียก embedding ในเครื่องใน thread แยก |
| [114–132](../rag/services/rag_engine.py#L114) | **`make_rag()`** สร้าง LightRAG: chunk ~1,300 token, ปิด gleaning (ประหยัด LLM ครึ่งหนึ่ง), เปิด cache, ภาษาไทย |

### 3.3 [rag/services/embedding_service.py](../rag/services/embedding_service.py) — embedding ในเครื่อง

| บรรทัด | ทำอะไร |
|---|---|
| [1–10](../rag/services/embedding_service.py#L1) | เหตุผลที่ใช้ bge-m3 ในเครื่อง + onnxruntime |
| [24–40](../rag/services/embedding_service.py#L24) | `_load()` โหลด tokenizer + โมเดล ONNX ครั้งเดียว · ตัดข้อความที่ 512 token |
| [36–37](../rag/services/embedding_service.py#L36) | ใช้ 1 thread (วัดแล้วเร็วกว่า 16 thread 13 เท่าบน CPU นี้) |
| [43–58](../rag/services/embedding_service.py#L43) | `embed()` ข้อความ → token → โมเดล → เอาเวกเตอร์ของ token แรก ([CLS]) → normalize ยาว 1 → 1,024 มิติ |

> **อาจโดนถาม:** cosine similarity (สัปดาห์ 3) — เวกเตอร์ถูก normalize แล้ว ความคล้าย = dot product ทดสอบแล้ว "ลิ้นมังกร ทนแสงน้อย" กับ "ต้นไม้สำหรับห้องที่แดดส่องไม่ถึง" ได้ 0.61 กับ "ค่าส่งต่างจังหวัด" ได้แค่ 0.34

### 3.4 [rag/scripts/index_kb.py](../rag/scripts/index_kb.py) — สร้างคลังความรู้

| บรรทัด | ทำอะไร |
|---|---|
| [32–50](../rag/scripts/index_kb.py#L32) | `pack_sections()` ตัดตามหัวข้อ `##`/`###` (ข้อมูลต้นไม้ 1 ต้นไม่ถูกหั่น) แล้วรวมหัวข้อติดกันให้ ~900 token · ใส่ชื่อเอกสารหัว chunk |
| [53–64](../rag/scripts/index_kb.py#L53) | `reset_storage()` ลบคลังเดิมแต่**เก็บ LLM cache ไว้** → index ใหม่ไม่เสียโควต้าซ้ำ |
| [67–89](../rag/scripts/index_kb.py#L67) | `main()` นำเข้าทีละไฟล์ (`rag.ainsert`) แล้วสรุปจำนวนครั้งที่เรียก LLM + ไฟล์ที่ล้มเหลว |

### 3.5 ไฟล์อื่นใน rag/

| ไฟล์ | ทำอะไร |
|---|---|
| [main.py](../rag/main.py) | `lifespan` โหลดโมเดล embedding + LightRAG ตอนเปิด server (คำถามแรกจะไม่ช้า) · เก็บไว้ที่ `app.state.rag` |
| [controllers/query_controller.py](../rag/controllers/query_controller.py) | `POST /query` → query_service · error → 503 · `GET /health` |
| [models/schemas.py](../rag/models/schemas.py) | `QueryRequest` (mode: local/global/hybrid/naive/mix) · `QueryResponse` |
| [scripts/download_model.py](../rag/scripts/download_model.py) | โหลดโมเดล 568 MB แบ่ง 8 ส่วนพร้อมกัน (CDN จำกัดความเร็วต่อการเชื่อมต่อ) |

---

## 4. ข้อมูลและสคริปต์

| ไฟล์ | ทำอะไร |
|---|---|
| [data/plants.csv](../data/plants.csv) | ★ ข้อมูลต้นไม้ 132 สายพันธุ์ 13 คอลัมน์ — แก้ราคาที่นี่ที่เดียว |
| [data/orders_mock.json](../data/orders_mock.json) | คำสั่งซื้อจำลอง 5 รายการ |
| [data/knowledge_base/](../data/knowledge_base/) | คลังความรู้ 9 ไฟล์ (02 และ 09 สร้างจาก CSV ห้ามแก้ตรง) |
| [scripts/build_plants_kb.py](../scripts/build_plants_kb.py) | CSV → markdown · [load_plants() บรรทัด 40](../scripts/build_plants_kb.py#L40) ตรวจข้อมูลก่อน (id ซ้ำ, หมวดผิด, ราคาผิดรูปแบบ) · [บรรทัด 151](../scripts/build_plants_kb.py#L151) สร้างรายการแนะนำ (มือใหม่, แสงน้อย, ของขวัญ ...) |
| [scripts/check_keys.py](../scripts/check_keys.py) | ทดสอบว่า API key ใช้ได้และชื่อโมเดลถูก |

## 5. ชุดทดสอบ — `eval/`

| ไฟล์ | ทำอะไร |
|---|---|
| [cases.json](../eval/cases.json) | คำถาม 10 + ภาพ 5 + ความปลอดภัย 5 พร้อมเกณฑ์ผ่าน (`all` ต้องมีทุกคำ, `any` มีอย่างน้อย 1 คำ, `blocked` ต้องถูกบล็อกไหม) |
| [run_eval.py](../eval/run_eval.py) | [judge() บรรทัด 28](../eval/run_eval.py#L28) ตัดสินผ่าน/ไม่ผ่าน · [run_case() บรรทัด 47](../eval/run_eval.py#L47) ยิง `/api/v1/chat` ด้วย session ใหม่ · บันทึก `.json` + ตาราง `.md` ใน `eval/results/` |
| [compare.py](../eval/compare.py) | เทียบผล 2 รอบ (ผ่าน, เวลาเฉลี่ย/สูงสุด, คำทักทาย, ความยาว) |

---

## 6. คำศัพท์ที่เจอในโค้ด

| คำ | ความหมาย |
|---|---|
| `async` / `await` | ฟังก์ชันที่รอผลจากเน็ตได้โดยไม่บล็อกงานอื่น — server รับหลายคำขอพร้อมกันได้ |
| async generator (`yield` ใน `async def`) | ฟังก์ชันที่ส่งผลออกมาทีละชิ้นระหว่างทำงาน ([chat_service.run](../app/services/chat_service.py#L52)) |
| SSE (Server-Sent Events) | server ส่งข้อความทีละก้อนมาที่เบราว์เซอร์ในการเชื่อมต่อเดียว รูปแบบ `data: ...\n\n` |
| `APIRouter` | กลุ่ม endpoint ของ controller หนึ่งตัว แล้วไปผูกกับแอปใน `main.py` |
| pydantic `BaseModel` | ประกาศรูปแบบข้อมูล FastAPI ตรวจให้อัตโนมัติ ผิดรูปแบบตอบ 422 |
| `@dataclass` | class สำหรับเก็บข้อมูล เขียนสั้น |
| `@lru_cache` | จำผลลัพธ์ เรียกครั้งที่ 2 ไม่ต้องอ่านไฟล์ซ้ำ |
| regex | รูปแบบค้นหาข้อความ เช่น `BK-?\s?(\d{4})` = "BK" ตามด้วยเลข 4 หลัก |
| fail-closed | ระบบตรวจพัง = ไม่ตอบ (ปลอดภัยกว่าปล่อยผ่าน) |
| fallback | ตัวสำรองเมื่อตัวหลักล่ม |
| OpenAI-compatible | API รูปแบบเดียวกับ OpenAI (`/chat/completions`) ใช้ได้กับหลายเจ้า |

---

## 7. คำถาม Q&A รายบุคคล → เปิดไฟล์ไหนตอบ

| คำถาม (สัปดาห์ 1) | ไฟล์ที่ใช้ตอบ |
|---|---|
| 1. LLM ทำงานยังไงตั้งแต่ input ถึง output | [chat_service.py บรรทัด 60–125](../app/services/chat_service.py#L60) + [llm_service.py บรรทัด 59–84](../app/services/llm_service.py#L59) |
| 2. ทำไมออกแบบ API แบบนี้ มีทางเลือกอื่นไหม | แยก 3 บริการ ([app](../app/main.py), [guard](../guard/main.py), [rag](../rag/main.py)) · `/stream` vs `/chat` ([chat_controller.py](../app/controllers/chat_controller.py#L62)) · OpenAI-compatible ([llm_service.py](../app/services/llm_service.py#L42)) |
| 3. ใช้ prompt engineering ยังไง | [chat_system.md](../app/prompts/chat_system.md) · [vision_system.md](../app/prompts/vision_system.md) · แท็กแยกข้อมูล ([chat_service.py บรรทัด 41](../app/services/chat_service.py#L41)) |
| 4. Vision ประมวลผลภาพยังไง | [vision_service.py](../app/services/vision_service.py) ทั้งไฟล์ |
| 5. ป้องกันการใช้ผิดยังไง ควรเพิ่มอะไร | [check_controller.py](../guard/controllers/check_controller.py#L37) · [rule_service.py](../guard/services/rule_service.py) · [order_service.py](../app/services/order_service.py) (least privilege) · DOMPurify ([chat.js บรรทัด 21](../app/views/static/js/chat.js#L21)) · rate limit ([session_store.py บรรทัด 36](../app/models/session_store.py#L36)) · ควรเพิ่ม: ระบบยืนยันตัวตน, rate limit ต่อ IP, log ตรวจสอบย้อนหลัง |
| 6. ผู้ใช้เพิ่ม 10 เท่า อะไรพังก่อน | โควต้าฟรี Gemini (500/วัน) → จ่ายเงิน/เพิ่มตัวสำรอง · [session_store.py](../app/models/session_store.py) อยู่ในหน่วยความจำ → Redis · embedding รันบน CPU 1 thread → GPU หรือ API · LightRAG เก็บเป็นไฟล์ → ฐานข้อมูล vector จริง |
