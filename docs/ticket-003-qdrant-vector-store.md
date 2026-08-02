# TICKET-003: Qdrant Vector Store Client Wrapper

## Purpose

This ticket adds the retrieval storage layer for Company Brain. The code in `backend/app/retrieval/vector_store.py` is responsible for writing document chunk embeddings into Qdrant and reading them back during search.

There is no HTTP endpoint for this ticket. It is a backend library/service component, so the success check is the test suite, not a browser URL.

## What the code does

- Creates a Qdrant collection if it does not already exist.
- Upserts chunk vectors in batches.
- Stores metadata with each chunk:
  - `project_id`
  - `document_id`
  - `chunk_id`
  - `source`
- Searches by query vector.
- Supports metadata filtering, at minimum by `project_id`.

## Files added or updated

- `backend/app/retrieval/vector_store.py`
- `backend/app/retrieval/__init__.py`
- `backend/tests/test_vector_store.py`
- `backend/tests/conftest.py`
- `backend/pyproject.toml`
- `backend/uv.lock`

## How to verify the ticket

Run these commands from the backend folder:

```powershell
cd "C:\knowledge tranfer\ai_knowledge_transfer_platform\backend"
uv sync
uv run pytest tests/test_vector_store.py
```

Expected result:

- `test_create_collection_is_idempotent` passes.
- `test_upsert_then_search_round_trip` passes.
- The search result should return the stored `project_id` payload when the filter is applied.

## Optional local smoke check

If you want to inspect the wrapper manually, you can run a short Python snippet from the backend folder after `uv sync`:

```powershell
uv run python -c "from app.retrieval.vector_store import QdrantVectorStore; print(QdrantVectorStore)"
```

That confirms the module imports correctly in the project environment.

## Notes

- This ticket depends on Docker because the integration test launches a local Qdrant container.
- The wrapper is meant to be used later by ingestion and retrieval code once document parsing and embeddings are connected.
- If you want an HTTP endpoint later, that should be added in a separate API ticket that calls this wrapper.
