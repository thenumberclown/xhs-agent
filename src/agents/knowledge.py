"""RAG Knowledge Base — ingest novel content for retrieval-augmented copy generation.

Ingests:
- All chapter files (*.md)
- Setting documents (角色清单, 大纲, etc.)
- Existing promotional material

All content is chunked and indexed in Chroma for semantic retrieval.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Optional

from ..storage.vector_store import get_vector_store, VectorStore

logger = logging.getLogger(__name__)

# ─── Constants ───────────────────────────────────────────────

CHUNK_SIZE = 500          # Characters per chunk
CHUNK_OVERLAP = 100       # Overlap between chunks

NOVEL_COLLECTION = "novel_knowledge"


class NovelKnowledgeBase:
    """Indexes and retrieves novel content for copy generation."""

    def __init__(self, vector_store: VectorStore | None = None) -> None:
        self.vs = vector_store or get_vector_store()
        self._collection_name = NOVEL_COLLECTION

    # ─── Ingestion ────────────────────────────────────────

    def ingest_chapter(self, filepath: Path) -> int:
        """Ingest a single chapter file. Returns number of chunks added."""
        content = filepath.read_text(encoding="utf-8")
        title = filepath.stem

        # Extract chapter number if present
        chapter_num = None
        match = re.search(r"第(\d+)章", title)
        if match:
            chapter_num = int(match.group(1))

        chunks = self._chunk_text(content)
        for i, chunk in enumerate(chunks):
            chunk_id = f"ch{chapter_num or filepath.stem}_{i}"
            meta = {
                "source": str(filepath),
                "title": title,
                "chapter_num": chapter_num,
                "chunk_index": i,
                "chunk_type": "chapter",
                "total_chunks": len(chunks),
            }
            self.vs.add_novel_chunk(
                doc_id=chunk_id,
                text=chunk,
                metadata=meta,
            )

        logger.info("Ingested %s: %d chunks", title, len(chunks))
        return len(chunks)

    def ingest_directory(self, dirpath: Path, pattern: str = "*.md") -> int:
        """Ingest all matching files in a directory. Returns total chunks."""
        files = sorted(dirpath.glob(pattern))
        total = 0
        for fp in files:
            try:
                total += self.ingest_chapter(fp)
            except Exception as e:
                logger.error("Failed to ingest %s: %s", fp, e)
        logger.info("Ingested %d files, %d total chunks", len(files), total)
        return total

    def ingest_settings(self, filepath: Path) -> int:
        """Ingest a setting/reference document."""
        content = filepath.read_text(encoding="utf-8")
        name = filepath.stem

        chunks = self._chunk_text(content)
        for i, chunk in enumerate(chunks):
            chunk_id = f"setting_{name}_{i}"
            meta = {
                "source": str(filepath),
                "title": name,
                "chunk_index": i,
                "chunk_type": "setting",
            }
            self.vs.add_novel_chunk(
                doc_id=chunk_id,
                text=chunk,
                metadata=meta,
            )

        logger.info("Ingested setting %s: %d chunks", name, len(chunks))
        return len(chunks)

    def ingest_promo_material(self, filepath: Path) -> int:
        """Ingest existing promotional copy for style reference."""
        content = filepath.read_text(encoding="utf-8")

        # Split by section markers (### headers)
        sections = re.split(r"\n###?\s+", content)
        count = 0
        for i, section in enumerate(sections):
            if len(section.strip()) < 20:
                continue
            chunk_id = f"promo_{i}"
            meta = {
                "source": str(filepath),
                "chunk_type": "promo",
                "chunk_index": i,
            }
            self.vs.add_novel_chunk(
                doc_id=chunk_id,
                text=section.strip(),
                metadata=meta,
            )
            count += 1

        logger.info("Ingested promo material: %d sections", count)
        return count

    # ─── Retrieval ────────────────────────────────────────

    def retrieve_context(
        self,
        query: str,
        n_results: int = 10,
        chunk_type: str | None = None,
    ) -> list[dict]:
        """Retrieve relevant novel content for a query.

        Args:
            query: Search query (e.g., chapter title, character name, concept)
            n_results: Number of results
            chunk_type: Filter by type ("chapter", "setting", "promo")

        Returns:
            List of {"text": ..., "metadata": {...}, "distance": ...}
        """
        where = None
        if chunk_type:
            where = {"chunk_type": chunk_type}

        results = self.vs.search_novel_chunks(
            query=query,
            n_results=n_results,
        )

        # Manual filter if needed
        if where:
            filtered = []
            for r in results:
                meta = r.get("metadata", {})
                if meta.get("chunk_type") == where.get("chunk_type"):
                    filtered.append(r)
            return filtered[:n_results]

        return results[:n_results]

    def retrieve_for_chapter(self, chapter_title: str, n_results: int = 5) -> list[dict]:
        """Retrieve content relevant to a specific chapter."""
        return self.retrieve_context(
            query=chapter_title,
            n_results=n_results,
            chunk_type="chapter",
        )

    def retrieve_style_reference(self, platform: str = "xiaohongshu") -> list[dict]:
        """Retrieve existing promo material for style reference."""
        query = f"{platform} 种草笔记 推文"
        return self.retrieve_context(
            query=query,
            n_results=5,
            chunk_type="promo",
        )

    def format_context(self, results: list[dict], max_chars: int = 2000) -> str:
        """Format retrieved context for inclusion in prompts."""
        lines = []
        total = 0
        for r in results:
            text = r.get("text", "")
            meta = r.get("metadata", {})
            source = meta.get("title", meta.get("source", "unknown"))
            line = f"[{source}] {text[:300]}"
            if total + len(line) > max_chars:
                break
            lines.append(line)
            total += len(line)
        return "\n\n".join(lines)

    # ─── Helpers ──────────────────────────────────────────

    def _chunk_text(self, text: str) -> list[str]:
        """Split text into overlapping chunks."""
        chunks = []
        start = 0
        while start < len(text):
            end = start + CHUNK_SIZE
            chunk = text[start:end]
            if chunk.strip():
                chunks.append(chunk.strip())
            start += (CHUNK_SIZE - CHUNK_OVERLAP)
        return chunks

    @property
    def stats(self) -> dict:
        """Get ingestion statistics."""
        try:
            count = self.vs.count_cases()
            return {"total_chunks": count, "collection": self._collection_name}
        except Exception:
            return {"total_chunks": 0, "collection": self._collection_name}
