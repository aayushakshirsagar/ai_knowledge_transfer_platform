"""Structure-aware document chunking.

Chunks a :class:`DocTree` (built by :mod:`app.ingestion.document_parser`) with
a subtree strategy. A whole section subtree is kept together whenever it fits
the token budget. Tables and ``<img>`` blocks are always isolated into their
own chunks and are never cut in the middle. Oversized plain prose falls back
to line/sentence/word splitting.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from app.ingestion.document_parser import BlockNode, DocTree, SectionNode, build_document_tree

DEFAULT_MAX_TOKENS = 1200

_SENTENCE_RE = re.compile(r"(?<=[.!?])\s+")


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


@dataclass
class Chunk:
    """A structure-aware, context-tagged slice of a document."""

    chunk_id: str
    chunk_type: str
    body: str
    token_count: int
    ancestor_headings: tuple[tuple[int, str], ...]
    own_heading: tuple[int, str] | None
    start_line: int | None
    end_line: int | None
    document_title: str


@dataclass
class SplitResult:
    document: DocTree
    chunks: list[Chunk]


@dataclass
class _Draft:
    blocks: list[BlockNode]
    section: SectionNode
    whole_subtree: bool = False


# ---------------------------------------------------------------------------
# Token counting
# ---------------------------------------------------------------------------


def count_tokens(text: str) -> int:
    """Approximate token count (UTF-8 bytes / 3, as in tiktoken's heuristic)."""
    return len(text.encode("utf-8")) // 3


# ---------------------------------------------------------------------------
# Chunking
# ---------------------------------------------------------------------------


def _any_isolated(section: SectionNode) -> bool:
    return any(b.isolated for b in section.blocks) or any(
        _any_isolated(c) for c in section.children
    )


def _section_tokens(section: SectionNode) -> int:
    total = sum(count_tokens(b.text) for b in section.blocks)
    if section.level:
        total += count_tokens("#" * section.level + " " + section.title)
    total += sum(_section_tokens(c) for c in section.children)
    return total


def _render_section(section: SectionNode) -> str:
    parts: list[str] = []
    if section.level:
        parts.append("#" * section.level + " " + section.title)
    for block in section.blocks:
        if block.text:
            parts.append(block.text)
    for child in section.children:
        parts.append(_render_section(child))
    return "\n\n".join(part for part in parts if part)


def _hard_slice(text: str, max_tokens: int) -> list[str]:
    step = max(max_tokens * 3, 1)
    return [text[i : i + step] for i in range(0, len(text), step)]


def _split_long_text(text: str, max_tokens: int, regex: str) -> list[str]:
    out: list[str] = []
    current = ""
    for part in re.split(regex, text):
        if not part:
            continue
        if count_tokens(part) > max_tokens:
            if current:
                out.append(current)
                current = ""
            out.extend(_hard_slice(part, max_tokens))
            continue
        candidate = f"{current} {part}".strip()
        if count_tokens(candidate) <= max_tokens:
            current = candidate
        else:
            if current:
                out.append(current)
            current = part
    if current:
        out.append(current)
    return out


def _split_long_line(line: str, max_tokens: int) -> list[str]:
    if count_tokens(line) <= max_tokens:
        return [line]
    out: list[str] = []
    current = ""
    for sentence in re.split(_SENTENCE_RE, line):
        if not sentence:
            continue
        if count_tokens(sentence) > max_tokens:
            if current:
                out.append(current)
                current = ""
            out.extend(_split_long_text(sentence, max_tokens, regex=r"\s+"))
            continue
        candidate = f"{current} {sentence}".strip()
        if count_tokens(candidate) <= max_tokens:
            current = candidate
        else:
            if current:
                out.append(current)
            current = sentence
    if current:
        out.append(current)
    return out


def _fallback_split_text(text: str, max_tokens: int) -> list[str]:
    pieces: list[str] = []
    for line in text.split("\n"):
        line = line.strip()
        if line:
            pieces.extend(_split_long_line(line, max_tokens))
    return pieces


def _fallback_split_block(block: BlockNode, max_tokens: int) -> list[BlockNode]:
    return [
        BlockNode(kind=block.kind, text=piece, isolated=block.isolated)
        for piece in _fallback_split_text(block.text, max_tokens)
    ]


def _pack_blocks(blocks: list[BlockNode], max_tokens: int) -> list[list[BlockNode]]:
    groups: list[list[BlockNode]] = []
    current: list[BlockNode] = []
    current_size = 0
    for block in blocks:
        size = count_tokens(block.text)
        if size > max_tokens:
            if current:
                groups.append(current)
                current, current_size = [], 0
            groups.extend([frag] for frag in _fallback_split_block(block, max_tokens))
            continue
        if current and current_size + size > max_tokens:
            groups.append(current)
            current, current_size = [], 0
        current.append(block)
        current_size += size
    if current:
        groups.append(current)
    return groups


def _split_section(section: SectionNode, max_tokens: int) -> list[_Draft]:
    drafts: list[_Draft] = []
    isolated = [b for b in section.blocks if b.isolated]
    normal = [b for b in section.blocks if not b.isolated]

    for block in isolated:
        drafts.append(_Draft(blocks=[block], section=section))

    if normal or section.children:
        if not isolated and not any(_any_isolated(c) for c in section.children):
            if _section_tokens(section) <= max_tokens:
                drafts.append(_Draft(blocks=[], section=section, whole_subtree=True))
                return drafts
        for group in _pack_blocks(normal, max_tokens):
            drafts.append(_Draft(blocks=group, section=section))
        for child in section.children:
            drafts.extend(_split_section(child, max_tokens))
    return drafts


def _collect_lines(section: SectionNode) -> list[int]:
    lines = [b.start_line for b in section.blocks if b.start_line is not None]
    for child in section.children:
        lines.extend(_collect_lines(child))
    return lines


def chunk_document_tree(
    tree: DocTree,
    *,
    max_tokens: int = DEFAULT_MAX_TOKENS,
) -> list[Chunk]:
    """Split a :class:`DocTree` into chunks using the subtree strategy."""
    if max_tokens <= 0:
        raise ValueError("max_tokens must be positive")

    chunks: list[Chunk] = []
    for index, draft in enumerate(_split_section(tree.root, max_tokens), start=1):
        if draft.whole_subtree:
            body = _render_section(draft.section)
            chunk_type = "section"
            lines = _collect_lines(draft.section)
        else:
            body = "\n\n".join(b.text for b in draft.blocks if b.text)
            chunk_type = draft.blocks[0].kind if len(draft.blocks) == 1 else "section"
            lines = [b.start_line for b in draft.blocks if b.start_line is not None]

        own_heading = draft.section.path[-1] if draft.section.path else None
        heading_key = (
            f"{own_heading[1].replace(' ', '_')}-{own_heading[0]}"
            if own_heading
            else "root"
        )
        chunks.append(
            Chunk(
                chunk_id=f"{tree.title or 'document'}-{heading_key}-{index:04d}",
                chunk_type=chunk_type,
                body=body,
                token_count=count_tokens(body),
                ancestor_headings=draft.section.path[:-1],
                own_heading=own_heading,
                start_line=min(lines) if lines else None,
                end_line=max(lines) if lines else None,
                document_title=tree.title or "",
            )
        )
    return chunks


def chunk_document(
    file_path: str | Path,
    *,
    document_title: str | None = None,
    max_tokens: int = DEFAULT_MAX_TOKENS,
) -> SplitResult:
    """Parse a PDF/DOCX into a document tree and chunk it end to end."""
    tree = build_document_tree(file_path, document_title=document_title)
    chunks = chunk_document_tree(tree, max_tokens=max_tokens)
    return SplitResult(document=tree, chunks=chunks)
