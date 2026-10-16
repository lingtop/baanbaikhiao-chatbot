"""ด่านที่ 3–4 ของ Guard: ใช้โมเดลจำแนกข้อความ

3. Prompt Guard 2 (Groq) — ให้คะแนนความน่าจะเป็น prompt injection / jailbreak (0–1) ใช้เฉพาะขาเข้า
4. Safety Classifier — จัดหมวดเนื้อหาอันตราย S1–S14 ตาม taxonomy ของ Llama Guard
   หลัก gpt-oss-20b (Groq) สำรอง Gemini 3.1 Flash Lite (AI Studio) — ฟรีทั้งคู่
   สลับเป็น Llama Guard ตัวจริงได้ที่ SAFETY_BASE_URL / SAFETY_MODEL ใน .env

ทั้งสองตัวถ้าเรียกไม่สำเร็จจะ raise ClassifierError → check_controller ตอบ 502 (fail-closed)
"""

import json
import re

import httpx

from guard.config import get_settings

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"

# หมวดของ Llama Guard 4 (MLCommons hazard taxonomy)
CATEGORIES = {
    "S1": "อาชญากรรมรุนแรง (ทำร้าย ฆ่า วางยาผู้อื่น ก่อการร้าย)",
    "S2": "อาชญากรรมไม่รุนแรง (ฉ้อโกง ขโมย แฮก ยาเสพติด)",
    "S3": "อาชญากรรมทางเพศ",
    "S4": "การแสวงประโยชน์ทางเพศจากเด็ก",
    "S5": "หมิ่นประมาท",
    "S6": "คำแนะนำเฉพาะทาง (การแพทย์ กฎหมาย การเงิน)",
    "S7": "ละเมิดความเป็นส่วนตัว",
    "S8": "ละเมิดทรัพย์สินทางปัญญา",
    "S9": "อาวุธทำลายล้างสูง",
    "S10": "ความเกลียดชัง",
    "S11": "ทำร้ายตัวเอง / ฆ่าตัวตาย",
    "S12": "เนื้อหาทางเพศ",
    "S13": "การเลือกตั้ง",
    "S14": "การใช้โค้ดในทางที่ผิด",
}
# S6 ไม่บล็อกที่ Guard — ให้ system prompt ตอบปฏิเสธสุภาพและแนะนำพบแพทย์แทน
# (เช่น "ว่านหางจระเข้รักษาโรคได้ไหม" เป็นคำถามปกติของลูกค้า ไม่ควรถูกตัดทิ้ง)
BLOCKED = set(CATEGORIES) - {"S6"}

SAFETY_PROMPT = (
    "You are a content-safety classifier for the chatbot of a Thai plant shop. "
    "Classify the {role} message below against these hazard categories:\n"
    + "\n".join(f"{k}: {v}" for k, v in CATEGORIES.items())
    + "\n\nNormal shopping questions are SAFE, including questions about plant prices, care, pests, "
    "whether a plant is toxic, dead plants, refunds, discounts, or complaints. "
    "Only flag a message if it seeks or provides genuinely harmful content.\n"
    'Reply with JSON only: {{"safe": true|false, "categories": ["S1", ...]}}\n\n'
    "<message>\n{message}\n</message>"
)


class ClassifierError(Exception):
    pass


async def prompt_guard(client: httpx.AsyncClient, text: str) -> float:
    s = get_settings()
    try:
        r = await client.post(GROQ_URL, timeout=15,
                              headers={"Authorization": f"Bearer {s.GROQ_API_KEY.get_secret_value()}"},
                              json={"model": s.PROMPT_GUARD_MODEL, "messages": [{"role": "user", "content": text}]})
    except httpx.HTTPError as e:
        raise ClassifierError(f"prompt guard: {e}") from e
    if r.status_code != 200:
        raise ClassifierError(f"prompt guard {r.status_code}: {r.text[:200]}")
    try:
        return float(r.json()["choices"][0]["message"]["content"].strip())
    except (ValueError, KeyError) as e:
        raise ClassifierError("prompt guard: unexpected response") from e


async def _classify(client: httpx.AsyncClient, base_url: str, model: str, prompt: str) -> str:
    s = get_settings()
    body = {"model": model, "temperature": 0, "max_tokens": 300,
            "response_format": {"type": "json_object"},
            "messages": [{"role": "user", "content": prompt}]}
    if model.startswith("openai/gpt-oss"):
        body["reasoning_effort"] = "low"  # คิดสั้น ๆ พอ ไม่ให้ช้า
    r = await client.post(f"{base_url.rstrip('/')}/chat/completions", timeout=30, json=body,
                          headers={"Authorization": f"Bearer {s.key_for(base_url)}"})
    if r.status_code != 200:
        raise ClassifierError(f"safety {model} {r.status_code}: {r.text[:200]}")
    return r.json()["choices"][0]["message"].get("content") or ""


async def safety(client: httpx.AsyncClient, text: str, direction: str) -> list[str]:
    """คืนรายการหมวดที่ผิด (ว่าง = ปลอดภัย)

    ลองตัวหลัก → ถ้าล้มเหลวลองตัวสำรอง (ต่างผู้ให้บริการ) → ถ้ายังล้มเหลว raise (fail-closed)
    """
    s = get_settings()
    role = "user" if direction == "input" else "assistant (chatbot answer)"
    prompt = SAFETY_PROMPT.format(role=role, message=text[:4000])
    errors = []
    for base_url, model in [(s.SAFETY_BASE_URL, s.SAFETY_MODEL), (s.SAFETY_FALLBACK_BASE_URL, s.SAFETY_FALLBACK_MODEL)]:
        try:
            content = await _classify(client, base_url, model, prompt)
            break
        except (ClassifierError, httpx.HTTPError) as e:
            errors.append(str(e)[:120])
    else:
        raise ClassifierError("safety: ทุกตัวล้มเหลว " + " | ".join(errors))
    m = re.search(r"\{.*\}", content, re.DOTALL)
    try:
        data = json.loads(m.group(0) if m else content)
    except json.JSONDecodeError as e:
        raise ClassifierError(f"safety: invalid JSON {content[:100]!r}") from e
    if data.get("safe", True):
        return []
    return [c for c in data.get("categories", []) if c in CATEGORIES]
