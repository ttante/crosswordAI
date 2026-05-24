"""Local vector and hybrid retrieval primitives."""

from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass, field
from typing import Protocol

from crosswordai.ids import utc_now_iso
from crosswordai.sources import SourcePack


@dataclass(frozen=True, slots=True)
class EmbeddedDocument:
    id: str
    text: str
    metadata: dict[str, str]
    vector: tuple[float, ...]
    embedding_model_id: str
    embedding_model_version: str
    embedding_dimensions: int


@dataclass(frozen=True, slots=True)
class SearchResult:
    id: str
    text: str
    metadata: dict[str, str]
    score: float
    vector_score: float = 0.0
    lexical_score: float = 0.0


@dataclass(frozen=True, slots=True)
class EmbeddingModelInfo:
    id: str
    version: str
    dimensions: int


@dataclass(frozen=True, slots=True)
class SourceChunk:
    id: str
    source_document_id: str
    text: str
    taxonomy: str
    trust_score: float
    rights_risk: str
    metadata: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class RetrievalTrace:
    query: str
    embedding_model: EmbeddingModelInfo
    filters: dict[str, str]
    results: tuple[SearchResult, ...]
    created_at: str


class HybridVectorIndex(Protocol):
    embedding_info: EmbeddingModelInfo

    def add_chunk(self, chunk: SourceChunk) -> None:
        ...

    def search(
        self,
        query: str,
        *,
        limit: int = 5,
        filters: dict[str, str] | None = None,
    ) -> list[SearchResult]:
        ...


class HashingEmbeddingModel:
    """Deterministic local embedding adapter for tests and offline development."""

    def __init__(self, dimensions: int = 64, *, model_id: str = "hashing-local", version: str = "0.1.0") -> None:
        self.dimensions = dimensions
        self.model_id = model_id
        self.version = version

    @property
    def info(self) -> EmbeddingModelInfo:
        return EmbeddingModelInfo(self.model_id, self.version, self.dimensions)

    def embed(self, text: str) -> tuple[float, ...]:
        values = [0.0] * self.dimensions
        for token in _tokens(text):
            digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
            bucket = int.from_bytes(digest[:4], "big") % self.dimensions
            sign = 1.0 if digest[4] % 2 == 0 else -1.0
            values[bucket] += sign
        norm = math.sqrt(sum(value * value for value in values)) or 1.0
        return tuple(value / norm for value in values)


class InMemoryHybridIndex:
    def __init__(self, embedding_model: HashingEmbeddingModel | None = None) -> None:
        self.embedding_model = embedding_model or HashingEmbeddingModel()
        self.documents: dict[str, EmbeddedDocument] = {}
        self.traces: list[RetrievalTrace] = []

    @property
    def embedding_info(self) -> EmbeddingModelInfo:
        return self.embedding_model.info

    def add(self, *, id: str, text: str, metadata: dict[str, str] | None = None) -> None:
        self.documents[id] = EmbeddedDocument(
            id=id,
            text=text,
            metadata=metadata or {},
            vector=self.embedding_model.embed(text),
            embedding_model_id=self.embedding_info.id,
            embedding_model_version=self.embedding_info.version,
            embedding_dimensions=self.embedding_info.dimensions,
        )

    def add_chunk(self, chunk: SourceChunk) -> None:
        metadata = {
            **chunk.metadata,
            "source_document_id": chunk.source_document_id,
            "taxonomy": chunk.taxonomy,
            "trust_score": str(chunk.trust_score),
            "rights_risk": chunk.rights_risk,
        }
        self.add(id=chunk.id, text=chunk.text, metadata=metadata)

    def index_source_pack(self, source_pack: SourcePack, *, max_chars: int = 800) -> list[SourceChunk]:
        chunks = chunks_from_source_pack(source_pack, max_chars=max_chars)
        for chunk in chunks:
            self.add_chunk(chunk)
        return chunks

    def search(
        self,
        query: str,
        *,
        limit: int = 5,
        filters: dict[str, str] | None = None,
    ) -> list[SearchResult]:
        query_vector = self.embedding_model.embed(query)
        query_tokens = set(_tokens(query))
        results: list[SearchResult] = []
        for document in self.documents.values():
            if filters and any(document.metadata.get(key) != value for key, value in filters.items()):
                continue
            vector_score = _cosine(query_vector, document.vector)
            lexical_score = _jaccard(query_tokens, set(_tokens(document.text)))
            score = 0.7 * vector_score + 0.3 * lexical_score
            results.append(SearchResult(document.id, document.text, document.metadata, score, vector_score, lexical_score))
        ranked = sorted(results, key=lambda result: result.score, reverse=True)[:limit]
        self.traces.append(
            RetrievalTrace(
                query=query,
                embedding_model=self.embedding_info,
                filters=filters or {},
                results=tuple(ranked),
                created_at=utc_now_iso(),
            )
        )
        return ranked


class PgVectorHybridIndex:
    """pgvector-backed retrieval adapter seam.

    SQL generation is testable without a live database. Runtime execution uses
    an optional psycopg dependency and a Postgres database with pgvector enabled.
    """

    def __init__(self, database_url: str, embedding_model: HashingEmbeddingModel | None = None) -> None:
        self.database_url = database_url
        self.embedding_model = embedding_model or HashingEmbeddingModel(dimensions=768)
        try:
            import psycopg  # type: ignore[import-not-found]
        except ModuleNotFoundError as exc:
            raise RuntimeError("PgVectorHybridIndex requires optional dependency 'psycopg'.") from exc
        self._psycopg = psycopg

    @property
    def embedding_info(self) -> EmbeddingModelInfo:
        return self.embedding_model.info

    def add_chunk(self, chunk: SourceChunk) -> None:
        vector = self.embedding_model.embed(chunk.text)
        with self._psycopg.connect(self.database_url) as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO source_chunk_embeddings (
                        id, source_document_id, chunk_text, taxonomy, trust_score, rights_risk,
                        embedding_model_id, embedding_model_version, embedding_dimensions, embedding, metadata
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        chunk.id,
                        chunk.source_document_id,
                        chunk.text,
                        chunk.taxonomy,
                        chunk.trust_score,
                        chunk.rights_risk,
                        self.embedding_info.id,
                        self.embedding_info.version,
                        self.embedding_info.dimensions,
                        list(vector),
                        json.dumps(chunk.metadata),
                    ),
                )

    def search(
        self,
        query: str,
        *,
        limit: int = 5,
        filters: dict[str, str] | None = None,
    ) -> list[SearchResult]:
        query_vector = self.embedding_model.embed(query)
        sql, params = self.build_search_query(
            query=query,
            query_vector=query_vector,
            embedding_info=self.embedding_info,
            limit=limit,
            filters=filters,
        )
        with self._psycopg.connect(self.database_url) as conn:
            with conn.cursor() as cursor:
                cursor.execute(sql, params)
                rows = cursor.fetchall()
        return [
            SearchResult(
                id=row[0],
                text=row[1],
                metadata=dict(row[2] or {}),
                score=float(row[3]),
                vector_score=float(row[4]),
                lexical_score=float(row[5]),
            )
            for row in rows
        ]

    @staticmethod
    def build_search_query(
        *,
        query: str,
        query_vector: tuple[float, ...],
        embedding_info: EmbeddingModelInfo,
        limit: int,
        filters: dict[str, str] | None = None,
    ) -> tuple[str, list[object]]:
        clauses = [
            "embedding_model_id = %s",
            "embedding_model_version = %s",
            "embedding_dimensions = %s",
        ]
        where_params: list[object] = [embedding_info.id, embedding_info.version, embedding_info.dimensions]
        filters = filters or {}
        if "taxonomy" in filters:
            clauses.append("taxonomy = %s")
            where_params.append(filters["taxonomy"])
        if "rights_risk" in filters:
            clauses.append("rights_risk = %s")
            where_params.append(filters["rights_risk"])
        where = " AND ".join(clauses)
        sql = f"""
            SELECT
                id,
                chunk_text,
                metadata,
                ((0.7 * (1 - (embedding <=> %s::vector))) +
                 (0.3 * ts_rank_cd(to_tsvector('english', chunk_text), plainto_tsquery('english', %s)))) AS score,
                (1 - (embedding <=> %s::vector)) AS vector_score,
                ts_rank_cd(to_tsvector('english', chunk_text), plainto_tsquery('english', %s)) AS lexical_score
            FROM source_chunk_embeddings
            WHERE {where}
            ORDER BY score DESC
            LIMIT %s
        """
        params: list[object] = [list(query_vector), query, list(query_vector), query]
        params.extend(where_params)
        params.append(limit)
        return sql, params


def trace_to_dict(trace: RetrievalTrace) -> dict[str, object]:
    return {
        "query": trace.query,
        "embedding_model": {
            "id": trace.embedding_model.id,
            "version": trace.embedding_model.version,
            "dimensions": trace.embedding_model.dimensions,
        },
        "filters": trace.filters,
        "created_at": trace.created_at,
        "results": [
            {
                "id": result.id,
                "score": result.score,
                "vector_score": result.vector_score,
                "lexical_score": result.lexical_score,
                "metadata": result.metadata,
            }
            for result in trace.results
        ],
    }


def chunks_from_source_pack(source_pack: SourcePack, *, max_chars: int = 800) -> list[SourceChunk]:
    documents = {document.id: document for document in source_pack.source_documents}
    chunks: list[SourceChunk] = []
    for snippet in source_pack.evidence_snippets:
        document = documents[snippet.source_document_id]
        for index, text in enumerate(chunk_text(snippet.snippet_text, max_chars=max_chars)):
            chunks.append(
                SourceChunk(
                    id=f"chunk_{snippet.id}_{index}",
                    source_document_id=document.id,
                    text=text,
                    taxonomy=source_pack.taxonomy,
                    trust_score=document.trust_score,
                    rights_risk=snippet.rights_risk,
                    metadata={
                        "source_pack_id": str(source_pack.id),
                        "evidence_snippet_id": snippet.id,
                        "source_type": document.source_type,
                        "title": document.title,
                    },
                )
            )
    return chunks


def chunk_text(text: str, *, max_chars: int = 800) -> list[str]:
    chunks: list[str] = []
    current = ""
    for paragraph in [part.strip() for part in text.split("\n\n") if part.strip()]:
        if current and len(current) + len(paragraph) + 2 > max_chars:
            chunks.append(current)
            current = paragraph
        else:
            current = paragraph if not current else f"{current}\n\n{paragraph}"
    if current:
        chunks.append(current)
    return chunks


def _tokens(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


def _cosine(left: tuple[float, ...], right: tuple[float, ...]) -> float:
    return sum(a * b for a, b in zip(left, right, strict=True))


def _jaccard(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)
