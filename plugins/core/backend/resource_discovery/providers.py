"""Server-side dense embeddings and compatible/DashScope reranking protocols."""
import math

import httpx

from .catalog import digest
from .models import DiscoverySettings
from .repository import vector_literal


def embedding_identity(settings: DiscoverySettings) -> str:
    return digest({"endpoint": settings.embedding_url, "model": settings.embedding_model,
                   "dimensions": settings.embedding_dimensions, "send_dimensions": settings.embedding_send_dimensions,
                   "text_format": 2})


class EmbeddingClient:
    def __init__(self, settings: DiscoverySettings):
        self.settings = settings

    async def embed(self, texts: list[str]) -> list[list[float]]:
        settings = self.settings
        if not settings.embedding_url or not settings.embedding_model:
            raise ValueError("Configure embedding endpoint and model")
        if not texts:
            return []
        headers = {"authorization": "Bearer " + settings.embedding_api_key} if settings.embedding_api_key else {}
        body = {"model": settings.embedding_model, "input": texts, "encoding_format": "float"}
        if settings.embedding_send_dimensions:
            body["dimensions"] = settings.embedding_dimensions
        async with httpx.AsyncClient(timeout=settings.timeout_seconds, follow_redirects=False) as client:
            response = await client.post(settings.embedding_url, headers=headers, json=body)
            response.raise_for_status()
            if len(response.content) > 16 * 1024 * 1024:
                raise ValueError("Oversized embedding response")
            payload = response.json()
        rows = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(rows, list) or len(rows) != len(texts):
            raise ValueError("Invalid embedding response")
        if any(not isinstance(r, dict) or type(r.get("index")) is not int or not isinstance(r.get("embedding"), list) for r in rows):
            raise ValueError("Invalid embedding row")
        rows.sort(key=lambda row: row["index"])
        if [r["index"] for r in rows] != list(range(len(texts))):
            raise ValueError("Invalid embedding indexes")
        for row in rows:
            vector_literal(row["embedding"], settings.embedding_dimensions)
        return [row["embedding"] for row in rows]


class HttpReranker:
    def __init__(self, settings: DiscoverySettings):
        self.settings = settings

    async def rerank(self, question: str, texts: list[str]) -> list[int]:
        return await rerank(self.settings, question, texts)


async def rerank(settings: DiscoverySettings, question: str, texts: list[str]) -> list[int]:
    if not settings.rerank_url or not settings.rerank_model:
        raise ValueError("Reranker not configured")
    if not texts:
        return []
    headers = {"authorization": "Bearer " + settings.rerank_api_key} if settings.rerank_api_key else {}
    # Request all candidates; the engine applies its result limit after sorting.
    parameters = {"top_n": len(texts)}
    if settings.rerank_instruct:
        parameters["instruct"] = settings.rerank_instruct
    if settings.rerank_protocol == "dashscope":
        body = {"model": settings.rerank_model, "input": {"query": question, "documents": texts},
                "parameters": parameters}
    else:
        body = {"model": settings.rerank_model, "query": question, "documents": texts, **parameters}
    async with httpx.AsyncClient(timeout=settings.timeout_seconds, follow_redirects=False) as client:
        response = await client.post(settings.rerank_url, headers=headers, json=body)
        response.raise_for_status()
        if len(response.content) > 1024 * 1024:
            raise ValueError("Oversized rerank response")
        payload = response.json()
    if not isinstance(payload, dict) or payload.get("code"):
        # Do not expose provider messages, which can contain request text.
        raise ValueError("Invalid rerank response")
    output = payload.get("output") if settings.rerank_protocol == "dashscope" else payload
    rows = output.get("results") if isinstance(output, dict) else None
    if not isinstance(rows, list) or len(rows) != len(texts) or any(not isinstance(r, dict) or type(r.get("index")) is not int for r in rows):
        raise ValueError("Invalid rerank response")
    if sorted(r["index"] for r in rows) != list(range(len(texts))):
        raise ValueError("Invalid rerank indexes")
    if any(type(r.get("relevance_score")) not in (float, int) or not math.isfinite(r["relevance_score"]) for r in rows):
        raise ValueError("Invalid rerank scores")
    return [r["index"] for r in sorted(rows, key=lambda r: (-r["relevance_score"], r["index"]))]
