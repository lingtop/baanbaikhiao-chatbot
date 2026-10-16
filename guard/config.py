"""ค่าตั้งของ Guard Service อ่านจากไฟล์ .env ที่โฟลเดอร์โปรเจกต์ (ไฟล์เดียวกับ Chat API)"""

from functools import lru_cache
from pathlib import Path

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

ENV_FILE = Path(__file__).resolve().parents[1] / ".env"


class GuardSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ENV_FILE, env_file_encoding="utf-8", extra="ignore")

    GROQ_API_KEY: SecretStr = SecretStr("")
    LLM_API_KEY: SecretStr = SecretStr("")  # ใช้กับตัวสำรองบน AI Studio

    # ด่าน 3: Prompt Guard 2 บน Groq
    PROMPT_GUARD_MODEL: str = "meta-llama/llama-prompt-guard-2-86m"
    INJECTION_THRESHOLD: float = 0.8

    # ด่าน 4: Safety Classifier (S1–S14 แบบ Llama Guard)
    # หลัก gpt-oss-20b บน Groq (~1 วินาที แยกผู้ให้บริการจาก Chat LLM) · สำรอง Gemini 3.1 Flash Lite
    # (ทดลอง Gemma 4 แล้ว ปิดโหมดคิดไม่ได้ ใช้ 6–31 วินาทีต่อครั้ง ช้าเกินสำหรับด่านตรวจ)
    SAFETY_BASE_URL: str = "https://api.groq.com/openai/v1"
    SAFETY_API_KEY: SecretStr = SecretStr("")  # ว่าง = เลือก key ตาม URL
    SAFETY_MODEL: str = "openai/gpt-oss-20b"
    SAFETY_FALLBACK_BASE_URL: str = "https://generativelanguage.googleapis.com/v1beta/openai"
    SAFETY_FALLBACK_MODEL: str = "gemini-3.1-flash-lite"

    def key_for(self, base_url: str) -> str:
        if self.SAFETY_API_KEY.get_secret_value():
            return self.SAFETY_API_KEY.get_secret_value()
        if "groq.com" in base_url:
            return self.GROQ_API_KEY.get_secret_value()
        return self.LLM_API_KEY.get_secret_value()


@lru_cache
def get_settings() -> GuardSettings:
    return GuardSettings()
