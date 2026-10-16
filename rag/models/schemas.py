"""โครงสร้างข้อมูลของ RAG Server"""

from typing import Literal

from pydantic import BaseModel, Field


class QueryRequest(BaseModel):
    query: str = Field(min_length=1, max_length=4000)
    mode: Literal["local", "global", "hybrid", "naive", "mix"] = "mix"
    include_references: bool = True
    top_k: int = Field(20, ge=1, le=60)
    chunk_top_k: int = Field(8, ge=1, le=30)


class Reference(BaseModel):
    reference_id: str | None = None
    file_path: str | None = None


class QueryResponse(BaseModel):
    response: str                  # context ที่ส่งให้ Chat LLM
    references: list[Reference]    # ไฟล์ที่ข้อมูลมาจาก (ใช้แสดงแหล่งอ้างอิง)
    elapsed: float
    counts: dict[str, int]         # จำนวน entity / ความสัมพันธ์ / chunk ที่ค้นเจอ
