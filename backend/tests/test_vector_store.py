from __future__ import annotations

from uuid import uuid4

import pytest
from qdrant_client import QdrantClient
from testcontainers.community.qdrant import QdrantContainer

from app.retrieval.vector_store import QdrantVectorStore, VectorChunk


@pytest.fixture(scope="module")
def qdrant_client() -> QdrantClient:
    with QdrantContainer() as container:
        client = container.get_client()
        yield client


def test_create_collection_is_idempotent(qdrant_client: QdrantClient) -> None:
    store = QdrantVectorStore(client=qdrant_client)
    collection_name = f"collection_{uuid4().hex}"

    store.create_collection(collection_name, vector_size=3)
    store.create_collection(collection_name, vector_size=3)

    assert qdrant_client.collection_exists(collection_name=collection_name)


def test_upsert_then_search_round_trip(qdrant_client: QdrantClient) -> None:
    store = QdrantVectorStore(client=qdrant_client)
    collection_name = f"collection_{uuid4().hex}"
    store.create_collection(collection_name, vector_size=3)

    chunk_one = VectorChunk(
        id="chunk-1",
        vector=[1.0, 0.0, 0.0],
        project_id="project-alpha",
        document_id="document-1",
        chunk_id="chunk-1",
        source="manual_upload",
    )
    chunk_two = VectorChunk(
        id="chunk-2",
        vector=[0.0, 1.0, 0.0],
        project_id="project-beta",
        document_id="document-2",
        chunk_id="chunk-2",
        source="manual_upload",
    )

    store.upsert_chunks(collection_name, [chunk_one, chunk_two], batch_size=1)

    results = store.search(
        collection_name,
        query_vector=[1.0, 0.0, 0.0],
        top_k=5,
        filters={"project_id": "project-alpha"},
    )

    assert len(results) == 1
    assert results[0].payload["project_id"] == "project-alpha"
    assert results[0].payload["document_id"] == "document-1"