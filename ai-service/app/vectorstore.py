"""Milvus vector store for product embeddings.

Wraps the pymilvus ``MilvusClient`` (2.6) with a small, robust API used by the
similarity layer (as an embedding cache) and by the ``/index`` + ``/search``
endpoints (catalog-wide ANN retrieval).

Design notes
------------
* Construction is guarded: if Milvus is unreachable the factory returns ``None``
  and the rest of the service degrades gracefully (in-process embeddings →
  lexical).  Individual calls are also defensive.
* Vectors are stored with ``COSINE`` metric, so a search "distance" is the
  cosine similarity in ``[-1, 1]`` (higher = more similar).
* ``dietary_tags`` are stored as a comma-joined string for simple round-tripping.
"""

from __future__ import annotations

import time
from typing import Optional, Sequence

from app.logging_config import get_logger

logger = get_logger(__name__)

_VECTOR_FIELD = "vector"


def _tags_to_str(tags: Optional[Sequence[str]]) -> str:
    return ",".join(t for t in (tags or []) if t)


def _tags_from_str(value: Optional[str]) -> list[str]:
    return [t for t in (value or "").split(",") if t]


class MilvusVectorStore:
    """Thin, defensive wrapper around a Milvus collection of product vectors."""

    def __init__(self, uri: str, collection: str, dim: int, token: str = "") -> None:
        from pymilvus import MilvusClient

        self.collection = collection
        self.dim = dim
        self._client = MilvusClient(uri=uri, token=token)
        # Force an actual connection so construction fails fast if Milvus is down.
        self._client.list_collections()
        self._ensure_collection()

    # -- schema / lifecycle ----------------------------------------------
    def _ensure_collection(self) -> None:
        from pymilvus import DataType, MilvusClient

        if self._client.has_collection(self.collection):
            self._client.load_collection(self.collection)
            return

        schema = MilvusClient.create_schema(auto_id=False, enable_dynamic_field=True)
        schema.add_field("id", DataType.VARCHAR, is_primary=True, max_length=128)
        schema.add_field(_VECTOR_FIELD, DataType.FLOAT_VECTOR, dim=self.dim)
        schema.add_field("name", DataType.VARCHAR, max_length=512)
        schema.add_field("category_id", DataType.VARCHAR, max_length=128)
        schema.add_field("is_active", DataType.BOOL)
        schema.add_field("dietary_tags", DataType.VARCHAR, max_length=512)

        index_params = self._client.prepare_index_params()
        index_params.add_index(
            field_name=_VECTOR_FIELD, index_type="AUTOINDEX", metric_type="COSINE"
        )
        self._client.create_collection(
            collection_name=self.collection, schema=schema, index_params=index_params
        )
        self._client.load_collection(self.collection)
        logger.info("Created Milvus collection '%s' (dim=%d).", self.collection, self.dim)

    # -- writes -----------------------------------------------------------
    def upsert(self, rows: list[dict]) -> int:
        """Upsert rows shaped like {id, vector, name, category_id, is_active, dietary_tags}."""
        if not rows:
            return 0
        data = [
            {
                "id": r["id"],
                _VECTOR_FIELD: r["vector"],
                "name": r.get("name", ""),
                "category_id": r.get("category_id", ""),
                "is_active": bool(r.get("is_active", True)),
                "dietary_tags": _tags_to_str(r.get("dietary_tags")),
            }
            for r in rows
        ]
        self._client.upsert(collection_name=self.collection, data=data)
        return len(data)

    def flush(self) -> None:
        """Seal inserted data so it becomes immediately searchable (read-after-write)."""
        self._client.flush(self.collection)

    # -- reads ------------------------------------------------------------
    def fetch_vectors(self, ids: Sequence[str]) -> dict[str, list[float]]:
        """Return cached vectors for the given ids (missing ids are omitted)."""
        ids = list(ids)
        if not ids:
            return {}
        rows = self._client.get(
            collection_name=self.collection, ids=ids, output_fields=[_VECTOR_FIELD]
        )
        return {r["id"]: r[_VECTOR_FIELD] for r in rows if _VECTOR_FIELD in r}

    def search(
        self,
        query_vector: Sequence[float],
        top_k: int = 5,
        *,
        exclude_ids: Optional[Sequence[str]] = None,
        active_only: bool = True,
        category_id: Optional[str] = None,
    ) -> list[dict]:
        """ANN-search the catalog. Returns [{product_id, name, category_id,
        is_active, dietary_tags, score}] sorted by descending similarity."""
        clauses: list[str] = []
        if active_only:
            clauses.append("is_active == true")
        if category_id:
            clauses.append(f'category_id == "{category_id}"')
        if exclude_ids:
            joined = ", ".join(f'"{i}"' for i in exclude_ids)
            clauses.append(f"id not in [{joined}]")
        expr = " and ".join(clauses)

        results = self._client.search(
            collection_name=self.collection,
            data=[list(query_vector)],
            limit=top_k,
            filter=expr,
            output_fields=["name", "category_id", "is_active", "dietary_tags"],
            search_params={"metric_type": "COSINE"},
            consistency_level="Strong",
        )
        hits = results[0] if results else []
        out: list[dict] = []
        for h in hits:
            entity = h.get("entity", {})
            out.append(
                {
                    "product_id": h.get("id"),
                    "name": entity.get("name", ""),
                    "category_id": entity.get("category_id", ""),
                    "is_active": entity.get("is_active", True),
                    "dietary_tags": _tags_from_str(entity.get("dietary_tags")),
                    "score": max(0.0, min(1.0, float(h.get("distance", 0.0)))),
                }
            )
        return out

    def count(self) -> int:
        try:
            stats = self._client.get_collection_stats(self.collection)
            return int(stats.get("row_count", 0))
        except Exception:  # pragma: no cover
            return 0


def build_vectorstore(settings, dim: Optional[int] = None) -> Optional[MilvusVectorStore]:
    """Construct the store, retrying briefly (Milvus can be slow to accept
    connections at startup). Returns ``None`` on failure → graceful fallback."""
    if not settings.enable_milvus:
        return None

    dim = dim or settings.embedding_dim
    last_err: Optional[Exception] = None
    for attempt in range(1, 4):
        try:
            store = MilvusVectorStore(
                uri=settings.milvus_uri,
                collection=settings.milvus_collection,
                dim=dim,
                token=settings.milvus_token,
            )
            logger.info(
                "Milvus connected (uri=%s, collection=%s, rows=%d).",
                settings.milvus_uri,
                settings.milvus_collection,
                store.count(),
            )
            return store
        except Exception as exc:  # pragma: no cover - depends on a live server
            last_err = exc
            time.sleep(2 * attempt)

    logger.warning(
        "Milvus unavailable at %s (%s); vector store disabled, using in-process embeddings.",
        settings.milvus_uri,
        last_err,
    )
    return None
