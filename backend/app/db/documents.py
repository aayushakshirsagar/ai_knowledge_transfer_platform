"""
DB helpers used by the ingestion orchestrator, built on the real
`Document` / `DocumentStatus` / `DocumentChunk` models in app/models/tables.py.
"""

from __future__ import annotations

from app.db.session import SessionLocal
from app.ingestion.interfaces import Chunk
from app.models.tables import Document, DocumentChunk, DocumentStatus


def get_document(document_id: int) -> Document:
    with SessionLocal() as session:
        document = session.get(Document, document_id)
        if document is None:
            raise ValueError(f"No document with id={document_id}")
        session.expunge(document)  # detach so it's usable after the session closes
        return document


def update_status(document_id: int, status: DocumentStatus) -> None:
    """
    Update documents.status. DocumentStatus only has four members - pending,
    parsed, embedded, failed - so the pipeline calls this exactly twice on
    success (parsed after parsing, embedded after the rest of the pipeline)
    and once on failure.

    NOTE: `Document` has no status_reason (or similar) column, so *why* a
    document failed is only captured in application logs right now (see
    orchestrator.py's logger.error calls), not queryable from the DB. If the
    admin console needs to surface the failure reason (the ticket's
    acceptance criteria mentions a "logged reason"), add a
    `status_reason: Mapped[str | None] = mapped_column(Text, nullable=True)`
    column to Document via an Alembic migration, and this function can set
    it - flagging this as a follow-up rather than guessing a column name.
    """
    with SessionLocal() as session:
        document = session.get(Document, document_id)
        if document is None:
            raise ValueError(f"No document with id={document_id}")
        document.status = status.value
        session.commit()


def replace_document_chunks(document_id: int, chunks: list[Chunk]) -> None:
    """
    Delete existing DocumentChunk rows for this document and reinsert.
    Paired with storage/qdrant_store.delete_document_points() - Postgres rows
    and Qdrant points are wiped and reinserted together so they can never
    drift out of sync. This, plus Chunk.vector_id being deterministic, is
    what satisfies the "reprocessing is idempotent" acceptance criterion.

    NOTE: DocumentChunk has no section_path column - Chunk.section_path
    (set by chunking/parsing) is used internally but not persisted here.
    token_count is also left null for now; Voyage doesn't return per-chunk
    token counts through embed_texts() as currently written, so this is a
    later enhancement if cost tracking needs it.
    """
    with SessionLocal() as session:
        session.query(DocumentChunk).filter(
            DocumentChunk.document_id == document_id
        ).delete()

        session.bulk_save_objects(
            [
                DocumentChunk(
                    document_id=c.document_id,
                    chunk_index=c.chunk_index,
                    chunk_text=c.text,
                    contextual_header=c.contextual_header,
                    vector_id=c.vector_id,
                )
                for c in chunks
            ]
        )
        session.commit()