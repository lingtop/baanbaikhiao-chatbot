"""เรียก Guard Service :8001 — ตรวจข้อความขาเข้าและขาออก (สัปดาห์ 11)

Fail-closed: ถ้าเรียก Guard ไม่ได้ ให้ถือว่า "ไม่ปลอดภัย" และไม่ตอบ ไม่ใช่ปล่อยผ่าน
"""

import httpx

from app.config import get_settings
from app.models.schemas import GuardResult
from app.services.http_client import get_client


class GuardUnavailable(Exception):
    pass


async def check(message: str, direction: str, context: str = "") -> GuardResult:
    s = get_settings()
    try:
        r = await get_client().post(f"{s.GUARD_BASE_URL.rstrip('/')}/check", timeout=30,
                                    json={"message": message, "direction": direction, "context": context})
    except httpx.HTTPError as e:
        raise GuardUnavailable("เชื่อมต่อระบบตรวจความปลอดภัยไม่ได้") from e
    if r.status_code != 200:
        raise GuardUnavailable(f"ระบบตรวจความปลอดภัยขัดข้อง (รหัส {r.status_code})")
    d = r.json()
    return GuardResult(safe=d["result"] == "safe", categories=d.get("categories", []),
                       message=d.get("msg", ""), layer=d.get("layer", ""), label=d.get("label", ""))


async def health() -> bool:
    s = get_settings()
    try:
        r = await get_client().get(f"{s.GUARD_BASE_URL.rstrip('/')}/health", timeout=5)
        return r.status_code == 200
    except httpx.HTTPError:
        return False
