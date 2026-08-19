"""
Integration test for app.embeddings.voyage_embedder - hits the real Voyage AI API.

Requires VOYAGE_API_KEY to be set in the environment / .env. If it's not set,
the whole module is skipped (not failed) so the rest of the suite and
teammates without a key aren't blocked.

Run just this file:
    uv run pytest tests/test_embeddings.py -v

Run the whole suite:
    uv run pytest
"""

from __future__ import annotations

import pytest

from app.core.settings import settings
from app.embeddings import embed_texts

pytestmark = pytest.mark.skipif(
    not settings.VOYAGE_API_KEY,
    reason="VOYAGE_API_KEY not set - skipping live Voyage API call",
)


def test_embed_texts_returns_one_vector_per_input():
    texts = [
        "Contextual retrieval prepends a short header to each chunk before embedding.",
        "The project timeline slipped by two weeks due to a vendor delay.",
    ]

    vectors = embed_texts(texts)

    assert len(vectors) == len(texts)


def test_embed_texts_vectors_have_consistent_dimension():
    texts = ["short text", "a slightly longer piece of text to embed"]

    vectors = embed_texts(texts)

    # voyage-3 outputs 1024-dim vectors - if this ever changes, the model
    # was swapped and DEFAULT_BATCH_SIZE / Qdrant collection config need
    # updating too, not just this assertion.
    assert len(vectors[0]) == 1024
    assert len(vectors[0]) == len(vectors[1])


def test_embed_texts_empty_input_returns_empty_list():
    # Should short-circuit without making an API call at all.
    assert embed_texts([]) == []