"""V11 Memory Search: Markdown-aware chunker.

Splits markdown files into chunks of ~400 tokens with 80-token overlap.
Preserves heading context so each chunk knows its nearest section.
"""

import hashlib
import re
from typing import List, NamedTuple


class Chunk(NamedTuple):
    text: str
    line_start: int
    line_end: int
    heading: str
    content_hash: str
    chunk_index: int


# Rough token estimation: 1 token ~= 4 chars (conservative for English text)
CHARS_PER_TOKEN = 4


def estimate_tokens(text: str) -> int:
    """Estimate token count from character count."""
    return len(text) // CHARS_PER_TOKEN


def content_hash(text: str) -> str:
    """SHA-256 hash of chunk text for cache deduplication. Truncated to 16 hex chars (64-bit prefix)."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def chunk_markdown(
    text: str,
    chunk_size_tokens: int = 400,
    overlap_tokens: int = 80,
) -> List[Chunk]:
    """Split markdown text into overlapping chunks.

    Strategy:
    1. Split on heading boundaries first (natural section breaks)
    2. If a section exceeds chunk_size, split on paragraph boundaries
    3. If a paragraph exceeds chunk_size, split on sentence boundaries
    4. Apply overlap between consecutive chunks
    """
    if not text.strip():
        return []

    lines = text.split("\n")
    sections = _split_into_sections(lines)

    chunks: List[Chunk] = []
    chunk_idx = 0
    max_chars = chunk_size_tokens * CHARS_PER_TOKEN
    overlap_chars = overlap_tokens * CHARS_PER_TOKEN

    for heading, section_lines, start_line in sections:
        section_text = "\n".join(section_lines)

        if estimate_tokens(section_text) <= chunk_size_tokens:
            # Section fits in one chunk
            if section_text.strip():
                chunks.append(Chunk(
                    text=section_text,
                    line_start=start_line,
                    line_end=start_line + len(section_lines) - 1,
                    heading=heading,
                    content_hash=content_hash(section_text),
                    chunk_index=chunk_idx,
                ))
                chunk_idx += 1
        else:
            # Section too large — split into paragraphs then chunks
            paragraphs = _split_paragraphs(section_lines, start_line)
            buffer = ""
            buffer_start = start_line
            buffer_end = start_line

            for para_text, para_start, para_end in paragraphs:
                candidate = (buffer + "\n\n" + para_text).strip() if buffer else para_text

                if estimate_tokens(candidate) <= chunk_size_tokens:
                    buffer = candidate
                    buffer_end = para_end
                    if not buffer.strip():
                        buffer_start = para_start
                else:
                    # Flush current buffer
                    if buffer.strip():
                        chunks.append(Chunk(
                            text=buffer,
                            line_start=buffer_start,
                            line_end=buffer_end,
                            heading=heading,
                            content_hash=content_hash(buffer),
                            chunk_index=chunk_idx,
                        ))
                        chunk_idx += 1

                    # Apply overlap: take last overlap_chars of buffer
                    if overlap_chars > 0 and buffer:
                        overlap_text = buffer[-overlap_chars:]
                        buffer = overlap_text + "\n\n" + para_text
                    else:
                        buffer = para_text
                    buffer_start = para_start
                    buffer_end = para_end

            # Flush remaining
            if buffer.strip():
                chunks.append(Chunk(
                    text=buffer,
                    line_start=buffer_start,
                    line_end=buffer_end,
                    heading=heading,
                    content_hash=content_hash(buffer),
                    chunk_index=chunk_idx,
                ))
                chunk_idx += 1

    return chunks


def _split_into_sections(lines: List[str]):
    """Split lines into (heading, lines, start_line) tuples by markdown headings."""
    sections = []
    current_heading = ""
    current_lines = []
    current_start = 1

    for i, line in enumerate(lines, 1):
        if re.match(r"^#{1,4}\s+", line):
            if current_lines:
                sections.append((current_heading, current_lines, current_start))
            current_heading = line.strip()
            current_lines = [line]
            current_start = i
        else:
            current_lines.append(line)

    if current_lines:
        sections.append((current_heading, current_lines, current_start))

    return sections


def _split_paragraphs(lines: List[str], start_line: int):
    """Split lines into (text, start, end) paragraph tuples."""
    paragraphs = []
    current = []
    para_start = start_line

    for i, line in enumerate(lines):
        line_num = start_line + i
        if line.strip() == "" and current:
            text = "\n".join(current)
            paragraphs.append((text, para_start, line_num - 1))
            current = []
            para_start = line_num + 1
        else:
            if not current:
                para_start = line_num
            current.append(line)

    if current:
        text = "\n".join(current)
        paragraphs.append((text, para_start, start_line + len(lines) - 1))

    return paragraphs
