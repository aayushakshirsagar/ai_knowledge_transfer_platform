# TICKET-020 — Embedding & Indexing Pipeline

**Status:** Embedding stage implemented and tested. Blocked on TICKET-017 (parsing) and TICKET-018/019 (chunking + contextual headers) for full end-to-end use — currently runs against stub implementations.

**Owner:** Aastha (embedding + orchestration + worker)
**Depends on:** TICKET-002 (schema), TICKET-003 (Qdrant), TICKET-017 (parsing — Aayusha), TICKET-018/019 (chunking + contextual headers — Swayam)

---

## What this does

Wires together: **parse → chunk → contextual headers → Voyage AI embed → Qdrant upsert**, triggered by a Redis queue job and updating `documents.status` along the way. This is the background job that turns an uploaded file into searchable vectors.

```
Document (status=pending)
        │
        ▼
   [parse]  ──────────────► status = parsed
        │
        ▼
   [chunk]
        │
        ▼
   [contextual headers]
        │
        ▼
   [embed — Voyage AI]
        │
        ▼
   [Qdrant upsert + document_chunks rows]  ───► status = embedded
        │
        └── any stage fails ──────────────────► status = failed
```

Only two status transitions happen on the success path (`parsed`, then `embedded`) — `DocumentStatus` in `app/models/tables.py` has just four members (`pending`, `parsed`, `embedded`, `failed`), no intermediate states.

## Where the code lives

```
backend/
├── app/
│   ├── worker.py                    # entry point — Redis consumer
│   ├── embeddings/
│   │   ├── __init__.py                # re-exports embed_chunks / embed_texts / embed_query
│   │   └── voyage_embedder.py           # Voyage AI calls (batching, retries)
│   ├── storage/
│   │   ├── s3_storage.py                # existing S3 service + download_bytes() (added)
│   │   └── qdrant_store.py                # Qdrant upsert/delete, idempotent point IDs
│   ├── db/
│   │   └── documents.py                    # get_document / update_status / replace_document_chunks
│   └── ingestion/
│       ├── interfaces.py                    # shared ParsedDocument / Chunk contracts
│       ├── orchestrator.py                   # wires every stage together
│       ├── stubs.py                           # temporary fake parse/chunk/header fns
│       ├── parsing.py                          # ← TICKET-017 (Aayusha) lands here
│       └── chunking.py                          # ← TICKET-018/019 (Swayam) lands here
└── tests/
    └── test_embeddings.py            # live Voyage API test (skips without a key)
```

## Setup

```bash
cd backend
uv add voyageai qdrant-client   # only new deps this ticket introduces
```

Requires a Voyage AI key (free tier is enough for dev/testing) from
[dashboard.voyageai.com](https://dashboard.voyageai.com), placed in
`ai_knowledge_transfer_platform/infra/.env`:

```
VOYAGE_API_KEY=pa-xxxxxxxxxxxx
```

`app/core/settings.py` loads `.env` relative to wherever the process is run
from (`../infra/.env` from `backend/`) — keep the key there, not in
`backend/.env`, or `settings.VOYAGE_API_KEY` will silently come back empty.

## Testing

**Embedding module only** (no DB/Redis/Qdrant needed):

```bash
uv run pytest tests/test_embeddings.py -v
```

Skips automatically if `VOYAGE_API_KEY` isn't set — this is expected in CI
or for teammates without a key, not a failure.

**Full pipeline**, once Postgres/Redis/Qdrant are running and migrations
are applied:

1. Upload a document through `/ingestion/upload` (or the FastAPI `/docs` UI) — this creates the `Document` row and pushes the job onto `document_parse_queue` automatically.
2. Run the worker: `uv run python -m app.worker`
3. Confirm `documents.status` reaches `embedded`, `document_chunks` rows exist with `vector_id` set, and the same count of points exist in the Qdrant `document_chunks` collection.
4. Re-upload/re-enqueue the same document and confirm the chunk/point counts don't change — this verifies idempotent reprocessing (an explicit acceptance criterion).

## Known gaps / follow-ups (flagged, not fixed here — need a team decision)

- **No failure-reason column.** `Document` has no `status_reason` (or similar) field, so *why* a document failed only reaches application logs (`orchestrator.py`), not the DB — the admin console can see `status=failed` but not the reason without checking logs. Needs an Alembic migration if that needs to be queryable.
- **`token_count`** on `DocumentChunk` is left `null` — Voyage's per-chunk token usage isn't parsed out yet. Only worth wiring up if/when cost tracking is needed.
- **Qdrant collection** (name `document_chunks`, vector size 1024 for `voyage-3`) needs to exist before this pipeline can index anything — that's TICKET-003's responsibility.

## Once TICKET-017 / TICKET-018 / TICKET-019 land

Swap the stub import at the top of `app/ingestion/orchestrator.py`:

```python
# from app.ingestion.stubs import parse_document, chunk_document, add_contextual_headers
from app.ingestion.parsing import parse_document
from app.ingestion.chunking import chunk_document, add_contextual_headers
```

As long as their functions return `ParsedDocument` / `list[Chunk]` matching
`app/ingestion/interfaces.py`, nothing else in the pipeline changes.
