"""Deterministic Markdown chunking preserving page provenance."""
from dataclasses import dataclass

@dataclass(frozen=True)
class Chunk:
    source: str
    page: int
    ordinal: int
    text: str

def chunk_page(text: str, source: str, page: int, max_chars: int = 1600) -> list[Chunk]:
    if max_chars < 1:
        raise ValueError("max_chars must be positive")
    words = text.split()
    chunks: list[Chunk] = []
    current: list[str] = []
    size = 0
    for word in words:
        if current and size + len(word) + 1 > max_chars:
            chunks.append(Chunk(source, page, len(chunks), " ".join(current)))
            current, size = [], 0
        if len(word) > max_chars:
            if current:
                chunks.append(Chunk(source, page, len(chunks), " ".join(current)))
                current, size = [], 0
            for start in range(0, len(word), max_chars):
                chunks.append(Chunk(source, page, len(chunks), word[start:start + max_chars]))
            continue
        current.append(word)
        size += len(word) + (1 if len(current) > 1 else 0)
    if current:
        chunks.append(Chunk(source, page, len(chunks), " ".join(current)))
    return chunks
