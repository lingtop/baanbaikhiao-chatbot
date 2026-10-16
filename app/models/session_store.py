"""เก็บประวัติแชทและนับจำนวนคำขอต่อ session (สัปดาห์ 6: session cookie + conversation store)

เก็บในหน่วยความจำ — รีสตาร์ต server แล้วประวัติหาย (พอสำหรับต้นแบบ)
ถ้าขยายระบบ ควรย้ายไป Redis เพื่อให้หลาย server ใช้ข้อมูลร่วมกัน
"""

import secrets
import time
from collections import defaultdict, deque

MAX_TURNS = 6  # จำย้อนหลัง 6 รอบ (12 ข้อความ) พอให้ถามต่อเนื่องได้ และไม่เปลือง token
COOKIE_NAME = "bbk_session"

_history: dict[str, deque] = defaultdict(lambda: deque(maxlen=MAX_TURNS * 2))
_requests: dict[str, deque] = defaultdict(deque)


def new_session_id() -> str:
    return secrets.token_urlsafe(16)


def get_history(sid: str) -> list[dict]:
    return list(_history[sid])


def append_turn(sid: str, user_text: str, answer: str) -> None:
    """บันทึกเฉพาะคำตอบที่ผ่าน Guard ขาออกแล้ว"""
    _history[sid].append({"role": "user", "content": user_text})
    _history[sid].append({"role": "assistant", "content": answer})


def reset(sid: str) -> None:
    _history.pop(sid, None)


def allow_request(sid: str, limit_per_min: int) -> bool:
    """rate limit แบบ sliding window 60 วินาที (OWASP LLM06)"""
    now = time.monotonic()
    q = _requests[sid]
    while q and now - q[0] > 60:
        q.popleft()
    if len(q) >= limit_per_min:
        return False
    q.append(now)
    return True
