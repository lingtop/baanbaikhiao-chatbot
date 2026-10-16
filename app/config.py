"""ค่าตั้งของ Chat API อ่านจากไฟล์ .env ที่โฟลเดอร์โปรเจกต์ ผ่าน pydantic-settings (สัปดาห์ 7)

แก้ค่าที่ .env เท่านั้น ไม่ต้องแก้โค้ด เช่น สลับโมเดลหรือผู้ให้บริการ
"""

from functools import lru_cache
from pathlib import Path

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

ENV_FILE = Path(__file__).resolve().parents[1] / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ENV_FILE, env_file_encoding="utf-8", extra="ignore")

    # Chat LLM + Vision (OpenAI-compatible) — ค่าเริ่มต้นคือ Google AI Studio
    LLM_BASE_URL: str = "https://generativelanguage.googleapis.com/v1beta/openai"
    LLM_API_KEY: SecretStr = SecretStr("")
    LLM_MODEL: str = "gemini-3.1-flash-lite"
    VISION_MODEL: str = "gemini-3.1-flash-lite"
    LLM_TEMPERATURE: float = 0.2
    # ตัวหลักช้าเกินกี่วินาทีให้สลับไปตัวสำรอง (Gemini บางครั้งตอบช้า 10–25 วินาทีโดยไม่ error)
    LLM_PRIMARY_TIMEOUT: float = 10

    # ตัวสำรองเมื่อผู้ให้บริการหลักไม่ว่าง (429/5xx/ช้าเกิน) — ข้อความเท่านั้น ไม่ใช้กับรูปภาพ
    LLM_FALLBACK_BASE_URL: str = "https://api.groq.com/openai/v1"
    LLM_FALLBACK_MODEL: str = "openai/gpt-oss-120b"
    LLM_FALLBACK_API_KEY: SecretStr = SecretStr("")  # ว่าง = ใช้ GROQ_API_KEY
    GROQ_API_KEY: SecretStr = SecretStr("")

    # บริการในเครื่อง
    RAG_BASE_URL: str = "http://127.0.0.1:9621"
    RAG_MODE: str = "mix"
    GUARD_BASE_URL: str = "http://127.0.0.1:8001"

    # ข้อจำกัดการใช้งาน (OWASP LLM06)
    MAX_MESSAGE_CHARS: int = 1000
    MAX_IMAGE_MB: int = 5
    RATE_LIMIT_PER_MIN: int = 20

    def missing_keys(self) -> list[str]:
        """รายชื่อ API key ที่ยังไม่ได้ตั้งค่า ใช้แสดงใน /api/v1/health"""
        keys = {"LLM_API_KEY": self.LLM_API_KEY, "GROQ_API_KEY": self.GROQ_API_KEY}
        return [name for name, value in keys.items() if not value.get_secret_value()]

    def key_for(self, base_url: str, explicit: SecretStr | None = None) -> str:
        """เลือก API key ตามผู้ให้บริการของ URL (ใส่ key แยกได้ถ้าต้องการ)"""
        if explicit is not None and explicit.get_secret_value():
            return explicit.get_secret_value()
        if "groq.com" in base_url:
            return self.GROQ_API_KEY.get_secret_value()
        return self.LLM_API_KEY.get_secret_value()


@lru_cache
def get_settings() -> Settings:
    return Settings()
