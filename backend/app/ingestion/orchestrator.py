"""
TICKET-020 - Orchestration pipeline.

Runs one documents.id from status=pending through to fully indexed in
Qdrant. DocumentStatus (app/models/tables.py) only has four members, which
maps exactly onto the ticket's described flow:

    pending -> [parse] -> parsed -> [chunk, headers, embed, index] -> embedded
                   \\_________________________________________________/
                                          -> failed (any stage)

Each teammate's function is imported below - swap the stub imports for the
real ones once app/ingestion/parsing.py (TICKET-017) and
app/ingestion/chunking.py (TICKET-018/019) exist. Their function signatures
are the contract (see interfaces.py). Nothing else in this file should need
to change.
"""

from __future__ import annotations

import logging

from app.db import documents as db
from app.embeddings import embed_chunks
from app.ingestion.interfaces import Chunk, ParsedDocument
from app.models.tables import DocumentStatus
from app.storage.qdrant_store import delete_document_points, upsert_chunks
from app.storage.s3_storage import S3StorageService

# --- Teammates' stages -------------------------------------------------
# Swap these for the real imports once TICKET-017/018/019 are merged, e.g.:
#   from app.ingestion.parsing import parse_document
#   from app.ingestion.chunking import chunk_document, add_contextual_headers
from app.ingestion.stubs import add_contextual_headers, chunk_document, parse_document

logger = logging.getLogger(__name__)

_s3_service = S3StorageService()


class PipelineError(Exception):
    """Wraps the underlying exception with which stage it happened in, so the
    failure gets a useful message in the application logs (Document has no
    status_reason column to persist this to - see db/documents.py)."""

    def __init__(self, stage: str, original: Exception):
        self.stage = stage
        self.original = original
        super().__init__(f"[{stage}] {original}")


def process_document(document_id: int) -> None:
    """
    Entry point called by worker.py for a single document. Never raises -
    all failures are caught, logged, and set status=failed so one bad
    document doesn't crash the batch job / worker loop.
    """
    try:
        document = db.get_document(document_id)
    except Exception as exc:
        # Can't even find the document row - nothing to update, just log and bail.
        logger.error("process_document: could not load document %s: %s", document_id, exc)
        return

    try:
        _run_pipeline(document_id, document.file_path)
    except PipelineError as exc:
        logger.error("Document %s failed at stage '%s': %s", document_id, exc.stage, exc.original)
        db.update_status(document_id, DocumentStatus.failed)
    except Exception as exc:  # belt and suspenders - truly unexpected errors
        logger.exception("Document %s failed with an unhandled error", document_id)
        db.update_status(document_id, DocumentStatus.failed)


def _run_pipeline(document_id: int, s3_key: str) -> None:
    # --- Stage: parse (TICKET-017) --------------------------------------
    try:
        file_bytes = _s3_service.download_bytes(s3_key)
        parsed: ParsedDocument = parse_document(document_id, file_bytes)
    except Exception as exc:
        raise PipelineError("parse", exc) from exc
    db.update_status(document_id, DocumentStatus.parsed)

    # --- Stage: chunk (TICKET-018) ---------------------------------------
    try:
        chunks: list[Chunk] = chunk_document(parsed)
        if not chunks:
            raise ValueError("chunking produced zero chunks")
    except Exception as exc:
        raise PipelineError("chunk", exc) from exc

    # --- Stage: contextual headers (TICKET-019) ---------------------------
    try:
        chunks = add_contextual_headers(parsed.full_text, chunks)
    except Exception as exc:
        raise PipelineError("contextual_headers", exc) from exc

    # --- Stage: embed (TICKET-020, this ticket) ----------------------------
    try:
        chunks = embed_chunks(chunks)
    except Exception as exc:
        raise PipelineError("embed", exc) from exc

    # --- Stage: index into Qdrant + Postgres (idempotent) -------------------
    try:
        # Delete-then-upsert (both Qdrant points and Postgres rows) is what
        # satisfies the "reprocessing is idempotent" acceptance criterion:
        # re-running this document never leaves duplicate/stale points behind,
        # regardless of whether the chunk count changed between runs.
        delete_document_points(document_id)
        upsert_chunks(chunks)
        db.replace_document_chunks(document_id, chunks)
    except Exception as exc:
        raise PipelineError("index", exc) from exc

    db.update_status(document_id, DocumentStatus.embedded)
    logger.info("Document %s embedded successfully (%d chunks)", document_id, len(chunks))