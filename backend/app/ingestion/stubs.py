"""
Temporary stand-ins for TICKET-017 (parsing) and TICKET-018/019
(chunking + contextual headers) so you can run and test the embedding stage
and the orchestrator end-to-end right now, without waiting on Aayusha/Swayam.

DELETE THIS FILE once app/ingestion/parsing.py and app/ingestion/chunking.py
(the real implementations) exist, and swap the imports in orchestrator.py.
"""

from __future__ import annotations

from app.ingestion.interfaces import Chunk, ParsedDocument, ParsedSection


def parse_document(document_id: int, file_bytes: bytes, filename: str = "") -> ParsedDocument:
    """Fake parser: treats the file as plain text (decode + ignore layout)."""
    text = file_bytes.decode("utf-8", errors="ignore")
    return ParsedDocument(
        document_id=document_id,
        full_text=text,
        sections=[ParsedSection(section_path="body", text=text)],
    )


def chunk_document(parsed: ParsedDocument, chunk_size: int = 1000) -> list[Chunk]:
    """Fake chunker: fixed-size character windows. Real TICKET-018 chunker
    should be structure-aware (headings/sections), but this is enough to
    exercise the pipeline."""
    text = parsed.full_text
    chunks = []
    for i, start in enumerate(range(0, len(text), chunk_size)):
        chunk_text = text[start : start + chunk_size]
        if not chunk_text.strip():
            continue
        chunks.append(
            Chunk(
                document_id=parsed.document_id,
                chunk_index=i,
                text=chunk_text,
                section_path="body",
            )
        )
    return chunks


def add_contextual_headers(full_text: str, chunks: list[Chunk]) -> list[Chunk]:
    """Fake header generator: real TICKET-019 calls an LLM (Haiku) with the
    full doc + chunk to produce a 1-2 sentence header. Stub just tags the
    chunk index so it's obviously not the real thing."""
    for c in chunks:
        c.contextual_header = f"Chunk {c.chunk_index + 1} of document."
    return chunks