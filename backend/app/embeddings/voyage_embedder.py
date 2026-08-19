"""
TICKET-020 - Embedding stage (Voyage AI). This is the piece you own.

Takes contextualized chunks (text = contextual_header + chunk text, already
assembled by Chunk.embedding_text) and returns them with `.embedding` filled in.
"""

from __future__ import annotations

import logging
import time
from typing import Sequence

import voyageai

from app.core.settings import settings
from app.ingestion.interfaces import Chunk

logger = logging.getLogger(__name__)

# Voyage's API accepts batches of texts in one call. Keep batches well under
# their per-request token/size limits; 128 is a safe default for typical
# chunk sizes (a few hundred tokens each).
DEFAULT_BATCH_SIZE = 128

MAX_RETRIES = 3
RETRY_BACKOFF_SECONDS = 2  # exponential: 2s, 4s, 8s


class EmbeddingError(Exception):
    """Raised when embedding a batch fails after retries. Caught by the orchestrator
    to mark the document as failed without crashing the whole worker/batch job."""


def _get_client() -> voyageai.Client:
    if not settings.VOYAGE_API_KEY:
        raise EmbeddingError("VOYAGE_API_KEY is not set")
    return voyageai.Client(api_key=settings.VOYAGE_API_KEY)


def _batched(items: Sequence, size: int):
    for i in range(0, len(items), size):
        yield items[i : i + size]


def embed_texts(
    texts: list[str],
    input_type: str = "document",
    model: str | None = None,
    batch_size: int = DEFAULT_BATCH_SIZE,
) -> list[list[float]]:
    """
    Embed a list of raw strings, preserving order. Used directly for query-time
    embedding (input_type="query") as well as internally by embed_chunks().

    Raises EmbeddingError if a batch fails after retries - callers should let
    this propagate up to the orchestrator's per-document try/except so one
    document's failure doesn't kill the whole batch job.
    """
    if not texts:
        return []

    model = model or settings.voyage_model
    client = _get_client()
    all_embeddings: list[list[float]] = []

    for batch_num, batch in enumerate(_batched(texts, batch_size)):
        last_error: Exception | None = None
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                result = client.embed(batch, model=model, input_type=input_type)
                all_embeddings.extend(result.embeddings)
                break
            except Exception as exc:  # voyageai raises its own exception types;
                # catch broadly since network/rate-limit errors all need the same retry handling
                last_error = exc
                logger.warning(
                    "Voyage embed batch %d attempt %d/%d failed: %s",
                    batch_num, attempt, MAX_RETRIES, exc,
                )
                if attempt < MAX_RETRIES:
                    time.sleep(RETRY_BACKOFF_SECONDS * (2 ** (attempt - 1)))
        else:
            raise EmbeddingError(
                f"Failed to embed batch {batch_num} after {MAX_RETRIES} attempts: {last_error}"
            ) from last_error

    return all_embeddings


def embed_chunks(chunks: list[Chunk], model: str | None = None) -> list[Chunk]:
    """
    Embed a list of Chunk objects in place (mutates and returns the same list).
    Uses Chunk.embedding_text (header + text) as the input to Voyage, per the
    contextual retrieval technique - NOT the raw chunk text alone.
    """
    if not chunks:
        return chunks

    texts = [c.embedding_text for c in chunks]
    vectors = embed_texts(texts, input_type="document", model=model)

    if len(vectors) != len(chunks):
        # Should never happen if Voyage preserves order, but fail loudly rather
        # than silently mis-assigning vectors to the wrong chunk.
        raise EmbeddingError(
            f"Embedding count mismatch: got {len(vectors)} vectors for {len(chunks)} chunks"
        )

    for chunk, vector in zip(chunks, vectors):
        chunk.embedding = vector

    return chunks


def embed_query(text: str, model: str | None = None) -> list[float]:
    """Convenience helper for the retrieval side (app/retrieval/ - not this
    ticket, but it'll need query-time embedding with the matching model and
    input_type='query')."""
    return embed_texts([text], input_type="query", model=model)[0]