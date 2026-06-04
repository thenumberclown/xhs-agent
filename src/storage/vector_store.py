"""Chroma vector store wrapper for copywriting examples."""

from __future__ import annotations

import logging
from typing import Optional

import chromadb
from chromadb.config import Settings as ChromaSettings

logger = logging.getLogger(__name__)


class VectorStore:
    """Vector store for semantic search over reference cases and generated copies."""

    COLLECTION_CASES = "reference_cases"
    COLLECTION_COPIES = "generated_copies"
    COLLECTION_NOVEL = "novel_knowledge"

    def __init__(
        self,
        host: str = "localhost",
        port: int = 8001,
        persist_dir: str | None = None,
    ) -> None:
        if persist_dir:
            # Local persistent mode (no server needed) — Chroma 0.5+ API
            import chromadb
            self._client: chromadb.ClientAPI = chromadb.PersistentClient(path=persist_dir)
        else:
            # Client-server mode
            self._client = chromadb.HttpClient(
                host=host,
                port=port,
                settings=ChromaSettings(anonymized_telemetry=False),
            )

        self._cases = self._client.get_or_create_collection(
            name=self.COLLECTION_CASES,
            metadata={"hnsw:space": "cosine"},
        )
        self._copies = self._client.get_or_create_collection(
            name=self.COLLECTION_COPIES,
            metadata={"hnsw:space": "cosine"},
        )
        self._novel = self._client.get_or_create_collection(
            name=self.COLLECTION_NOVEL,
            metadata={"hnsw:space": "cosine"},
        )

    # ─── Reference case operations ────────────────────────

    def add_case(
        self,
        doc_id: str,
        text: str,
        metadata: dict | None = None,
    ) -> None:
        """Index a reference case."""
        meta = metadata or {}
        self._cases.add(
            ids=[doc_id],
            documents=[text],
            metadatas=[meta],
        )
        logger.debug("Added case %s to vector store", doc_id)

    def add_copy(self, doc_id: str, text: str, metadata: dict | None = None) -> None:
        """Index a generated copy for similarity search."""
        meta = metadata or {}
        self._copies.add(
            ids=[doc_id],
            documents=[text],
            metadatas=[meta],
        )

    def search_similar_cases(
        self,
        query: str,
        n_results: int = 5,
        quality_label: str | None = None,
    ) -> list[dict]:
        """Find similar reference cases by semantic similarity."""
        where = None
        if quality_label:
            where = {"quality_label": quality_label}

        results = self._cases.query(
            query_texts=[query],
            n_results=n_results,
            where=where,
        )

        docs = []
        if results["ids"] and results["ids"][0]:
            for i, doc_id in enumerate(results["ids"][0]):
                docs.append({
                    "id": doc_id,
                    "text": results["documents"][0][i] if results["documents"] else "",
                    "metadata": results["metadatas"][0][i] if results["metadatas"] else {},
                    "distance": results["distances"][0][i] if results["distances"] else 0,
                })
        return docs

    def search_similar_copies(
        self,
        query: str,
        n_results: int = 5,
    ) -> list[dict]:
        """Find similar generated copies (for dedup check)."""
        results = self._copies.query(
            query_texts=[query],
            n_results=n_results,
        )

        docs = []
        if results["ids"] and results["ids"][0]:
            for i, doc_id in enumerate(results["ids"][0]):
                docs.append({
                    "id": doc_id,
                    "text": results["documents"][0][i] if results["documents"] else "",
                    "metadata": results["metadatas"][0][i] if results["metadatas"] else {},
                    "distance": results["distances"][0][i] if results["distances"] else 0,
                })
        return docs

    def count_cases(self) -> int:
        return self._cases.count()

    def count_copies(self) -> int:
        return self._copies.count()

    def count_novel(self) -> int:
        return self._novel.count()

    # ─── Novel knowledge operations ────────────────────────

    def add_novel_chunk(self, doc_id: str, text: str, metadata: dict | None = None) -> None:
        """Index a novel knowledge chunk in the dedicated novel collection."""
        meta = metadata or {}
        self._novel.add(
            ids=[doc_id],
            documents=[text],
            metadatas=[meta],
        )
        logger.debug("Added novel chunk %s", doc_id)

    def search_novel_chunks(
        self,
        query: str,
        n_results: int = 5,
        where: dict | None = None,
    ) -> list[dict]:
        """Search novel knowledge by semantic similarity."""
        results = self._novel.query(
            query_texts=[query],
            n_results=n_results,
            where=where,
        )

        docs = []
        if results["ids"] and results["ids"][0]:
            for i, doc_id in enumerate(results["ids"][0]):
                docs.append({
                    "id": doc_id,
                    "text": results["documents"][0][i] if results["documents"] else "",
                    "metadata": results["metadatas"][0][i] if results["metadatas"] else {},
                    "distance": results["distances"][0][i] if results["distances"] else 0,
                })
        return docs



# Singleton
_store: VectorStore | None = None


def get_vector_store() -> VectorStore:
    global _store
    if _store is None:
        from ..config import get_settings

        settings = get_settings()
        # Check if Chroma server is reachable via quick TCP check
        import socket
        server_available = False
        try:
            sock = socket.create_connection(
                (settings.chroma_host, settings.chroma_port), timeout=2.0
            )
            sock.close()
            server_available = True
        except OSError:
            pass

        if server_available:
            _store = VectorStore(host=settings.chroma_host, port=settings.chroma_port)
        else:
            persist_dir = str(settings.data_dir / "chroma")
            logger.info("Chroma server not available, using local mode at %s", persist_dir)
            _store = VectorStore(persist_dir=persist_dir)
    return _store
