"""HTTP client ตัวเดียวที่ทุก service ใช้ร่วมกัน (ใช้การเชื่อมต่อซ้ำ — connection pooling)"""

import httpx

_client: httpx.AsyncClient | None = None


def get_client() -> httpx.AsyncClient:
    global _client
    if _client is None:
        _client = httpx.AsyncClient(timeout=httpx.Timeout(60, connect=10))
    return _client
