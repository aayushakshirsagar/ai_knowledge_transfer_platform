"""
Shared data contracts for the ingestion pipeline (TICKET-020).

Every stage's function should accept/return these dataclasses so the
orchestrator can wire them together without caring about each other's
internals. Share this file across the team so everyone agrees on the shape
of the data up front:

    ingestion.parsing.parse_document()            -> ParsedDocument   (TICKET-017, Aayusha)
    ingestion.chunking.chunk_document()           -> list[Chunk]        (TICKET-018, Swayam)
    ingestion.chunking.add_contextual_headers()   -> list[Chunk]         (TICKET-019, Swayam)
    embeddings.voyage_embedder.embed_chunks()     -> list[Chunk] w/ vector (TICKET-020, Aastha)
"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ParsedSection:
    """One structural unit of a parsed document (a heading section, a table, etc.)."""
    section_path: str          # e.g. "3. Architecture > 3.2 Storage"
    text: str
    tables: list[dict] = field(default_factory=list)
    image_captions: list[str] = field(default_factory=list)


@dataclass
class ParsedDocument:
    """Output of TICKET-017 (parsing)."""
    document_id: int                         # matches Document.id (int PK) in app/models/tables.py
    full_text: str                          # concatenated plain text, used for contextual headers
    sections: list[ParsedSection] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)   # source, author, page_count, etc.


@dataclass
class Chunk:
    """
    Flows through chunking -> contextual headers -> embedding -> qdrant upsert.
    Each stage fills in more fields; nothing is removed.
    """
    document_id: int                 # matches Document.id (int PK) in app/models/tables.py
    chunk_index: int                 # stable, deterministic ordinal within the document (0, 1, 2, ...)
    text: str                        # raw chunk text (TICKET-018 output). Maps to DocumentChunk.chunk_text
                                      # when persisted (see app/db/documents.py) - column is named
                                      # differently there, not "text".
    section_path: Optional[str] = None   # used internally during chunking/embedding; DocumentChunk has
                                          # no column for this, so it is NOT persisted to Postgres.
    contextual_header: Optional[str] = None   # 1-2 sentence header (TICKET-019 output)
    embedding: Optional[list[float]] = None   # filled in by embeddings/ (TICKET-020)
    metadata: dict = field(default_factory=dict)

    @property
    def embedding_text(self) -> str:
        """
        The actual string that gets embedded: header + chunk text.
        This is the point of contextual retrieval - keep it consistent
        between what gets embedded and what gets stored for display.
        """
        if self.contextual_header:
            return f"{self.contextual_header}\n\n{self.text}"
        return self.text

    @property
    def vector_id(self) -> str:
        """
        Deterministic point ID for Qdrant, derived from document_id + chunk_index.
        This is what makes reprocessing idempotent - re-upserting a chunk with the
        same document_id/chunk_index overwrites the same point instead of creating
        a duplicate. Requires chunk_index to be stable across re-runs (i.e. chunking
        must be deterministic for the same parsed input).
        """
        import uuid
        namespace = uuid.uuid5(uuid.NAMESPACE_DNS, "company-brain.chunks")
        return str(uuid.uuid5(namespace, f"{self.document_id}:{self.chunk_index}"))