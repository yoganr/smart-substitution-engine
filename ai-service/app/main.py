"""FastAPI entry point for the Smart Substitution Engine AI service.

Run locally:
    uvicorn app.main:app --reload --port 8000

Then open http://localhost:8000/docs for interactive Swagger docs.
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import RedirectResponse

from app import __version__
from app.config import get_settings
from app.engine import build_engine
from app.logging_config import configure_logging, get_logger
from app.providers import probe_ollama
from app.schemas import (
    HealthResponse,
    IndexProductsRequest,
    IndexProductsResponse,
    ReplacementRequest,
    ReplacementResponse,
    SearchSimilarRequest,
    SearchSimilarResponse,
)

logger = get_logger(__name__)

DESCRIPTION = """
AI-powered **product replacement** service for the Smart Substitution Engine.

When a requested product is out of stock, this service ranks the best alternative
products for a given company using a **deterministic scoring model** and writes a
short, human-friendly explanation with a local **Ollama** LLM.

**Scoring dimensions** (max 93 points):

| Dimension | Max |
|---|---|
| Category similarity | 30 |
| Contract match | 25 |
| Price similarity | 20 |
| Stock availability | 10 |
| Unit / pack similarity | 8 |

The LLM **never** chooses replacements — Python ranks them deterministically and
Ollama only explains the result *after* ranking. If Ollama is unavailable, a
deterministic template explanation is used instead.
"""


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    settings = get_settings()
    app.state.settings = settings
    app.state.engine = build_engine(settings)
    engine = app.state.engine
    logger.info(
        "%s v%s ready (chat_model=%s, embeddings=%s:%s on %s, llm=%s, milvus=%s)",
        settings.service_name,
        __version__,
        settings.chat_model,
        settings.embedding_backend,
        settings.embedding_model,
        engine.similarity.embedding_device or "n/a",
        settings.enable_llm_explanations,
        "up" if engine.similarity.uses_milvus else "off",
    )
    yield
    logger.info("Shutting down %s.", settings.service_name)


app = FastAPI(
    title="Smart Substitution Engine — AI Service",
    version=__version__,
    description=DESCRIPTION,
    lifespan=lifespan,
    contact={"name": "Python AI Engineer"},
    openapi_tags=[
        {"name": "system", "description": "Health and diagnostics."},
        {"name": "recommendations", "description": "Replacement recommendations."},
        {"name": "vector-search", "description": "Milvus-backed catalog indexing + similarity search."},
    ],
)


@app.get("/", include_in_schema=False)
async def root() -> RedirectResponse:
    return RedirectResponse(url="/docs")


@app.get(
    "/health",
    response_model=HealthResponse,
    tags=["system"],
    summary="Service + Ollama health check",
)
async def health(http_request: Request) -> HealthResponse:
    settings = get_settings()
    ollama = await probe_ollama(settings)
    engine = getattr(http_request.app.state, "engine", None)
    embeddings = {
        "backend": settings.embedding_backend,
        "model": settings.embedding_model,
        "enabled": settings.enable_embeddings,
        "available": bool(engine and engine.similarity.uses_embeddings),
        "device": engine.similarity.embedding_device if engine else None,
    }
    available = bool(engine and engine.similarity.uses_milvus)
    vector_store = {
        "backend": "milvus",
        "enabled": settings.enable_milvus,
        "available": available,
        "uri": settings.milvus_uri,
        "collection": settings.milvus_collection,
        "indexed_products": engine.retrieval.count() if available else 0,
    }
    return HealthResponse(
        service=settings.service_name,
        version=__version__,
        ollama=ollama,
        embeddings=embeddings,
        vector_store=vector_store,
    )


@app.post(
    "/index/products",
    response_model=IndexProductsResponse,
    tags=["vector-search"],
    summary="Index products into the Milvus vector store",
)
async def index_products(
    request: IndexProductsRequest, http_request: Request
) -> IndexProductsResponse:
    retrieval = http_request.app.state.engine.retrieval
    if not retrieval.available:
        raise HTTPException(status_code=503, detail="Vector store/embeddings unavailable.")
    try:
        indexed = await retrieval.index_products(request.products)
    except Exception as exc:  # pragma: no cover - live-server failure path
        raise HTTPException(status_code=502, detail=f"Indexing failed: {exc}") from exc
    return IndexProductsResponse(
        indexed=indexed,
        collection=get_settings().milvus_collection,
        total_in_collection=retrieval.count(),
    )


@app.post(
    "/search/similar",
    response_model=SearchSimilarResponse,
    tags=["vector-search"],
    summary="Find catalog products most similar to a query (vector ANN search)",
)
async def search_similar(
    request: SearchSimilarRequest, http_request: Request
) -> SearchSimilarResponse:
    retrieval = http_request.app.state.engine.retrieval
    if not retrieval.available:
        raise HTTPException(status_code=503, detail="Vector store/embeddings unavailable.")
    try:
        hits = await retrieval.search_similar(
            name=request.name,
            category_id=request.category_id,
            product_id=request.product_id,
            top_k=request.top_k,
            exclude_ids=request.exclude_ids,
            active_only=request.active_only,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:  # pragma: no cover - live-server failure path
        raise HTTPException(status_code=502, detail=f"Search failed: {exc}") from exc
    return SearchSimilarResponse(count=len(hits), results=hits)


@app.post(
    "/recommendations/replacements",
    response_model=ReplacementResponse,
    tags=["recommendations"],
    summary="Rank replacement products for an out-of-stock item",
    response_description="Ranked replacements with score breakdowns and explanations.",
)
async def recommend_replacements(
    request: ReplacementRequest, http_request: Request
) -> ReplacementResponse:
    engine = http_request.app.state.engine
    return await engine.recommend(request)
