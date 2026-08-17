"""Bridge between structure-aware chunking and the Qdrant vector store.

Takes the :class:`Chunk` objects produced by :mod:`app.ingestion.chunking`,
embeds their bodies with Voyage AI, and upserts them into Qdrant together
with document/section metadata so retrieval can filter and cite accurately.
"""

from __future__ import annotations

import logging
from typing import Sequence
from uuid import NAMESPACE_URL, uuid5

import requests

from app.core.settings import settings
from app.ingestion.chunking import Chunk
from app.retrieval.vector_store import QdrantVectorStore, VectorChunk

logger = logging.getLogger(__name__)

VOYAGE_EMBEDDINGS_URL = "https://api.voyageai.com/v1/embeddings"
VOYAGE_MODEL = "voyage-3-large"
VOYAGE_VECTOR_SIZE = 1024
VOYAGE_BATCH_SIZE = 128

DEFAULT_COLLECTION = "document_chunks"


def embed_texts(
    texts: Sequence[str],
    *,
    api_key: str | None = None,
    model: str = VOYAGE_MODEL,
    batch_size: int = VOYAGE_BATCH_SIZE,
) -> list[list[float]]:
    """Embed a list of texts using the Voyage AI embeddings API."""
    api_key = api_key or settings.VOYAGE_API_KEY
    if not api_key:
        raise RuntimeError("VOYAGE_API_KEY is required to generate embeddings")

    embeddings: list[list[float]] = []
    for start in range(0, len(texts), batch_size):
        batch = list(texts[start : start + batch_size])
        response = requests.post(
            VOYAGE_EMBEDDINGS_URL,
            headers={"Authorization": f"Bearer {api_key}"},
            json={"model": model, "input": batch, "input_type": "document"},
            timeout=120,
        )
        response.raise_for_status()
        data = response.json()["data"]
        data.sort(key=lambda item: item["index"])
        embeddings.extend(item["embedding"] for item in data)
    return embeddings


def _section_name(chunk: Chunk) -> str:
    if chunk.own_heading:
        return chunk.own_heading[1]
    if chunk.ancestor_headings:
        return chunk.ancestor_headings[-1][1]
    return ""


def chunk_to_vector_chunk(
    chunk: Chunk,
    vector: list[float],
    *,
    project_id: str,
    document_id: str,
    source: str,
) -> VectorChunk:
    """Convert a chunked document into a Qdrant point with rich metadata."""
    payload: dict = {
        "document_name": chunk.document_title or "untitled",
        "section_name": _section_name(chunk),
        "chunk_type": chunk.chunk_type,
        "token_count": chunk.token_count,
        "body": chunk.body,
    }
    if chunk.start_line is not None:
        payload["start_line"] = chunk.start_line
    if chunk.end_line is not None:
        payload["end_line"] = chunk.end_line
    if chunk.ancestor_headings:
        payload["ancestor_headings"] = [
            f"{level}: {title}" for level, title in chunk.ancestor_headings
        ]

    point_id = uuid5(
        NAMESPACE_URL,
        f"{project_id}:{document_id}:{chunk.chunk_id}",
    )
    return VectorChunk(
        id=str(point_id),
        vector=vector,
        project_id=project_id,
        document_id=document_id,
        chunk_id=chunk.chunk_id,
        source=source,
        payload=payload,
    )


def index_document_chunks(
    chunks: Sequence[Chunk],
    *,
    project_id: str,
    document_id: str,
    source: str,
    collection_name: str = DEFAULT_COLLECTION,
    vector_size: int = VOYAGE_VECTOR_SIZE,
    store: QdrantVectorStore | None = None,
    api_key: str | None = None,
) -> list[str]:
    """Embed chunks and upsert them into Qdrant.

    Returns the Qdrant point ids written so callers can persist them (e.g. as
    ``document_chunks.vector_id``). Reprocessing the same document is
    idempotent because point ids are derived deterministically from the
    project, document and chunk ids.
    """
    store = store or QdrantVectorStore()
    store.create_collection(collection_name, vector_size=vector_size)

    vectors = embed_texts([c.body for c in chunks], api_key=api_key)
    points = [
        chunk_to_vector_chunk(
            chunk,
            vector,
            project_id=project_id,
            document_id=document_id,
            source=source,
        )
        for chunk, vector in zip(chunks, vectors, strict=True)
    ]
    store.upsert_chunks(collection_name, points)

    return [str(point.id) for point in points]
