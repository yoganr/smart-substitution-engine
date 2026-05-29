"""Seed the Milvus vector store with a sample product catalog.

Run from the repo's ai-service folder (Milvus must be reachable):

    cd ai-service
    python examples/seed_milvus.py

Honours the same SSE_* env vars as the service (SSE_MILVUS_URI, etc.).
After seeding, try POST /search/similar or browse the data in Attu
(http://localhost:8002).
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import Settings
from app.engine import build_engine
from app.schemas import IndexProduct

CATALOG = Path(__file__).parent / "sample_catalog.json"


async def main() -> None:
    settings = Settings()  # picks up SSE_* env / defaults (Milvus + embeddings on)
    engine = build_engine(settings)

    if not engine.retrieval.available:
        print(
            "[X] Milvus or the embedding model is unavailable.\n"
            f"    Milvus URI: {settings.milvus_uri} (SSE_ENABLE_MILVUS={settings.enable_milvus})\n"
            "    Start Milvus first, e.g.:\n"
            "      docker compose -f milvus-standalone-docker-compose.yml up -d\n"
            "    or bring up the whole stack from the repo root: docker compose up"
        )
        return

    products = [IndexProduct(**p) for p in json.loads(CATALOG.read_text(encoding="utf-8"))]
    indexed = await engine.retrieval.index_products(products)
    print(f"[OK] Indexed {indexed} products. Collection now holds {engine.retrieval.count()} rows.")
    print('     Try: POST /search/similar  {"name": "Chicken Breast 2kg", "top_k": 5}')


if __name__ == "__main__":
    asyncio.run(main())
