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

import threading
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
    """Thin, defensive wrapper around a Milvus collection of product vectors.

    The pymilvus gRPC channel is created once and held for the life of the
    process, and it does NOT self-heal: if Milvus restarts or the channel is
    closed while idle, every later RPC fails with "Cannot invoke RPC on closed
    channel!". Each public method therefore runs through :meth:`_call`, which
    transparently rebuilds the client and retries once on such an error.
    """

    def __init__(self, uri: str, collection: str, dim: int, token: str = "") -> None:
        self.collection = collection
        self.dim = dim
        self._uri = uri
        self._token = token
        self._lock = threading.Lock()
        self._gen = 0  # connection generation; bumped on every (re)connect
        self._connect()

    # -- connection management -------------------------------------------
    def _connect(self) -> None:
        """(Re)build the client and ensure the collection is ready. Raises if
        Milvus is unreachable so construction fails fast."""
        from pymilvus import MilvusClient

        self._client = MilvusClient(uri=self._uri, token=self._token)
        # Force an actual connection so a dead server surfaces immediately.
        self._client.list_collections()
        self._ensure_collection()

    def _reconnect(self, seen_gen: int) -> None:
        """Tear down a dead channel and reconnect, retrying briefly. ``seen_gen``
        is the connection generation the caller used; if another thread already
        reconnected we skip rebuilding the now-healthy client."""
        with self._lock:
            if self._gen != seen_gen:
                return  # another thread already reconnected
            try:
                self._client.close()
            except Exception:  # pragma: no cover - best-effort teardown
                pass
            last_err: Optional[Exception] = None
            for attempt in range(1, 4):
                try:
                    self._connect()
                    self._gen += 1
                    logger.info("Reconnected to Milvus at %s.", self._uri)
                    return
                except Exception as exc:  # pragma: no cover - needs a live server
                    last_err = exc
                    time.sleep(0.3 * attempt)
            raise RuntimeError(
                f"Milvus reconnect failed: {type(last_err).__name__}: {last_err}"
            )

    def _call(self, op, what: str):
        """Run a Milvus RPC; on ANY failure, rebuild the client once and retry.

        A Milvus restart closes the gRPC channel, and pymilvus does NOT recover
        it: its internal reconnect reuses the dead channel object, whose
        ``channel_ready_future`` never resolves, so it just times out with an
        empty-message ``grpc.FutureTimeoutError``. Only a brand-new client
        helps. Matching on the error message is therefore unreliable (that
        timeout carries no message), so we simply rebuild and retry once. Every
        op routed through here is idempotent, so the retry is safe."""
        gen = self._gen
        try:
            return op(self._client)
        except Exception as exc:
            logger.warning(
                "Milvus %s failed (%s: %s); rebuilding client and retrying.",
                what, type(exc).__name__, exc,
            )
            self._reconnect(gen)
            return op(self._client)

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
        self._call(lambda c: c.upsert(collection_name=self.collection, data=data), "upsert")
        return len(data)

    def flush(self) -> None:
        """Seal inserted data so it becomes immediately searchable (read-after-write)."""
        self._call(lambda c: c.flush(self.collection), "flush")

    # -- reads ------------------------------------------------------------
    def fetch_vectors(self, ids: Sequence[str]) -> dict[str, list[float]]:
        """Return cached vectors for the given ids (missing ids are omitted)."""
        ids = list(ids)
        if not ids:
            return {}
        rows = self._call(
            lambda c: c.get(
                collection_name=self.collection, ids=ids, output_fields=[_VECTOR_FIELD]
            ),
            "fetch_vectors",
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

        results = self._call(
            lambda c: c.search(
                collection_name=self.collection,
                data=[list(query_vector)],
                limit=top_k,
                filter=expr,
                output_fields=["name", "category_id", "is_active", "dietary_tags"],
                search_params={"metric_type": "COSINE"},
                consistency_level="Strong",
            ),
            "search",
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
            stats = self._call(
                lambda c: c.get_collection_stats(self.collection), "count"
            )
            return int(stats.get("row_count", 0))
        except Exception:  # pragma: no cover - reconnect also failed
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
