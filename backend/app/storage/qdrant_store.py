"""
Thin Qdrant wrapper used by the ingestion orchestrator (TICKET-020) and,
later, by app/retrieval/ for querying.

Assumes TICKET-003 already provisioned the Qdrant collection (name, vector
size = 1024 for voyage-3, distance metric). This module just needs to
upsert/delete points for a given document, using the deterministic
Chunk.vector_id so reprocessing is idempotent.

NOTE: if app/storage/ already has a Qdrant client set up (from TICKET-003),
merge this into that existing file instead of creating a second client.
"""

from __future__ import annotations

from qdrant_client import QdrantClient
from qdrant_client.http import models as qmodels

from app.core.settings import settings
from app.ingestion.interfaces import Chunk

_client: QdrantClient | None = None


def _get_client() -> QdrantClient:
    global _client
    if _client is None:
        _client = QdrantClient(url=settings.QDRANT_URL, api_key=settings.QDRANT_API_KEY or None)
    return _client


def delete_document_points(document_id: int) -> None:
    """
    Delete all existing Qdrant points for this document before reinserting.
    This is the idempotency guarantee required by the ticket: even if chunk
    boundaries changed between runs (different chunk_index count), stale
    points from a previous run won't linger.
    """
    _get_client().delete(
        collection_name=settings.qdrant_collection,
        points_selector=qmodels.FilterSelector(
            filter=qmodels.Filter(
                must=[
                    qmodels.FieldCondition(
                        key="document_id",
                        match=qmodels.MatchValue(value=document_id),
                    )
                ]
            )
        ),
    )


def upsert_chunks(chunks: list[Chunk]) -> list[str]:
    """
    Upsert embedded chunks into Qdrant. Each point ID is deterministic
    (Chunk.vector_id), so calling this twice with the same document_id/
    chunk_index combos overwrites rather than duplicates - this is a second
    layer of idempotency on top of delete_document_points(), in case delete
    and upsert race with a concurrent read.

    Returns the list of point IDs used, in the same order as `chunks`, so the
    caller can store them in document_chunks.vector_id.
    """
    if not chunks:
        return []

    for c in chunks:
        if c.embedding is None:
            raise ValueError(f"Chunk {c.chunk_index} of document {c.document_id} has no embedding")

    points = [
        qmodels.PointStruct(
            id=chunk.vector_id,
            vector=chunk.embedding,
            payload={
                "document_id": chunk.document_id,
                "chunk_index": chunk.chunk_index,
                "section_path": chunk.section_path,
                "text": chunk.text,
                "contextual_header": chunk.contextual_header,
                **chunk.metadata,
            },
        )
        for chunk in chunks
    ]

    _get_client().upsert(collection_name=settings.qdrant_collection, points=points, wait=True)

    return [chunk.vector_id for chunk in chunks]