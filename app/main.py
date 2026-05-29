"""FastAPI entry point for the Smart Substitution Engine AI service.

Run locally:
    uvicorn app.main:app --reload --port 8000

Then open http://localhost:8000/docs for interactive Swagger docs.
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse

from app import __version__
from app.config import get_settings
from app.engine import build_engine
from app.logging_config import configure_logging, get_logger
from app.providers import probe_ollama
from app.schemas import HealthResponse, ReplacementRequest, ReplacementResponse

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
    logger.info(
        "%s v%s ready (chat_model=%s, embedding_model=%s, embeddings=%s, llm=%s)",
        settings.service_name,
        __version__,
        settings.chat_model,
        settings.embedding_model,
        settings.enable_embeddings,
        settings.enable_llm_explanations,
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
async def health() -> HealthResponse:
    settings = get_settings()
    ollama = await probe_ollama(settings)
    return HealthResponse(service=settings.service_name, version=__version__, ollama=ollama)


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
