"""Controller ของ RAG Server

POST /query    {query, mode, top_k, chunk_top_k} → {response: context, references, elapsed, counts}
GET  /health
"""

from fastapi import APIRouter, HTTPException, Request

from models.schemas import QueryRequest, QueryResponse
from services import query_service

router = APIRouter(tags=["rag"])


@router.get("/health")
async def health(request: Request):
    return {"status": "ok" if getattr(request.app.state, "rag", None) else "starting"}


@router.post("/query", response_model=QueryResponse)
async def query(req: QueryRequest, request: Request):
    try:
        return await query_service.query(request.app.state.rag, req)
    except query_service.QueryError as e:
        raise HTTPException(503, str(e)) from e
