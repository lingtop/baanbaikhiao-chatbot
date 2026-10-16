"""ค้นคลังความรู้แล้วประกอบ context ให้ Chat LLM"""

import time

from lightrag import LightRAG, QueryParam

from models.schemas import QueryRequest, QueryResponse, Reference


class QueryError(Exception):
    pass


def build_context(data: dict) -> str:
    """เรียง context ให้ LLM: ข้อความต้นฉบับจากคลังความรู้ก่อน (ราคาตรงตัว) ตามด้วยสรุป entity/ความสัมพันธ์"""
    parts = []
    chunks = data.get("chunks") or []
    if chunks:
        parts.append("### ข้อความจากเอกสารของร้าน")
        parts += [f"[{c.get('file_path', '')}]\n{c.get('content', '').strip()}" for c in chunks]
    ents = data.get("entities") or []
    if ents:
        parts.append("### ข้อมูลสรุปที่เกี่ยวข้อง")
        parts += [f"- {e.get('entity_name')}: {(e.get('description') or '').strip()[:500]}" for e in ents[:15]]
    rels = data.get("relationships") or []
    if rels:
        parts.append("### ความสัมพันธ์")
        parts += [f"- {r.get('src_id')} → {r.get('tgt_id')}: {(r.get('description') or '').strip()[:300]}" for r in rels[:10]]
    return "\n\n".join(parts)


async def query(rag: LightRAG, req: QueryRequest) -> QueryResponse:
    t0 = time.perf_counter()
    param = QueryParam(mode=req.mode, top_k=req.top_k, chunk_top_k=req.chunk_top_k, enable_rerank=False)
    try:
        result = await rag.aquery_data(req.query, param=param)
    except Exception as e:  # noqa: BLE001
        raise QueryError(f"ค้นคลังความรู้ไม่สำเร็จ: {type(e).__name__}") from e
    if result.get("status") != "success":
        raise QueryError(result.get("message", "query failed"))
    data = result.get("data") or {}
    refs = [Reference(reference_id=r.get("reference_id"), file_path=r.get("file_path")) for r in data.get("references") or []]
    return QueryResponse(
        response=build_context(data),
        references=refs if req.include_references else [],
        elapsed=round(time.perf_counter() - t0, 2),
        counts={k: len(data.get(k) or []) for k in ("entities", "relationships", "chunks")},
    )
