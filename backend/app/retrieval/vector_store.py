from __future__ import annotations

from dataclasses import dataclass
from itertools import islice
from uuid import NAMESPACE_URL, UUID, uuid5
from typing import Any, Iterable

from qdrant_client import QdrantClient
from qdrant_client.http import models as qdrant_models


@dataclass(slots=True)
class VectorChunk:
    id: str | int
    vector: list[float]
    project_id: str
    document_id: str
    chunk_id: str
    source: str
    payload: dict[str, Any] | None = None


@dataclass(slots=True)
class SearchHit:
    id: str | int
    score: float
    payload: dict[str, Any]


class QdrantVectorStore:
    def __init__(self, *, client: QdrantClient | None = None) -> None:
        self.client = client or QdrantClient(
            url="http://localhost:6333",
        )

    def create_collection(self, name: str, vector_size: int) -> None:
        if self.client.collection_exists(collection_name=name):
            return

        self.client.create_collection(
            collection_name=name,
            vectors_config=qdrant_models.VectorParams(
                size=vector_size,
                distance=qdrant_models.Distance.COSINE,
            ),
        )

    def upsert_chunks(self, collection_name: str, chunks: list[VectorChunk], batch_size: int = 64) -> None:
        for batch in _batched(chunks, batch_size):
            points = [
                qdrant_models.PointStruct(
                    id=self._normalize_point_id(chunk.id),
                    vector=chunk.vector,
                    payload={
                        "project_id": chunk.project_id,
                        "document_id": chunk.document_id,
                        "chunk_id": chunk.chunk_id,
                        "source": chunk.source,
                        **(chunk.payload or {}),
                    },
                )
                for chunk in batch
            ]
            self.client.upsert(collection_name=collection_name, points=points)

    def search(
        self,
        collection_name: str,
        query_vector: list[float],
        top_k: int,
        filters: dict[str, Any] | None = None,
    ) -> list[SearchHit]:
        query_filter = self._build_filter(filters or {})
        results = self.client.query_points(
            collection_name=collection_name,
            query=query_vector,
            limit=top_k,
            query_filter=query_filter,
            with_payload=True,
        )

        return [
            SearchHit(
                id=result.id,
                score=float(result.score),
                payload=dict(result.payload or {}),
            )
            for result in results.points
        ]

    def _build_filter(self, filters: dict[str, Any]) -> qdrant_models.Filter | None:
        if not filters:
            return None

        must_conditions: list[qdrant_models.FieldCondition] = []
        for key, value in filters.items():
            must_conditions.append(
                qdrant_models.FieldCondition(
                    key=key,
                    match=qdrant_models.MatchValue(value=value),
                )
            )

        return qdrant_models.Filter(must=must_conditions)

    def _normalize_point_id(self, point_id: str | int) -> str | int:
        if isinstance(point_id, int):
            return point_id

        try:
            return str(UUID(point_id))
        except ValueError:
            return str(uuid5(NAMESPACE_URL, point_id))


def _batched(items: Iterable[VectorChunk], batch_size: int) -> Iterable[list[VectorChunk]]:
    iterator = iter(items)
    while batch := list(islice(iterator, batch_size)):
        yield batch