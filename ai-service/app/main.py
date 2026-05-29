import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException

from .config import settings
from .pipeline import recommendation_pipeline
from .schemas import ReplacementRequest, ReplacementResponse

logger = logging.getLogger(__name__)


async def _warm_up_ollama() -> None:
    """Load Ollama model into memory before first real request."""
    from langchain_ollama import ChatOllama

    retries = 3
    for attempt in range(1, retries + 1):
        try:
            llm = ChatOllama(
                model=settings.ollama_model,
                base_url=settings.ollama_base_url,
                num_ctx=4096,
            )
            await llm.ainvoke("warmup")
            logger.info("Ollama warm-up complete (model: %s)", settings.ollama_model)
            return
        except Exception as e:
            if attempt < retries:
                logger.warning("Ollama warm-up attempt %d failed: %s — retrying in 2s", attempt, e)
                await asyncio.sleep(2)
            else:
                logger.warning(
                    "Ollama warm-up failed after %d attempts: %s — template fallback will be used",
                    retries,
                    e,
                )


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Warm up Ollama on startup so first real request isn't cold
    asyncio.create_task(_warm_up_ollama())
    yield


app = FastAPI(
    title="Smart Substitution Engine — AI Recommendation Service",
    version="1.0.0",
    lifespan=lifespan,
)


@app.get("/health")
async def health():
    return {"status": "ok", "ollama_model": settings.ollama_model}


@app.post("/recommendations/replacements", response_model=ReplacementResponse)
async def get_replacements(request: ReplacementRequest) -> ReplacementResponse:
    try:
        initial_state = {
            "request": request,
            "candidates": [],
            "rejected": [],
            "scored": [],
            "replacements": [],
            "no_candidates_reason": None,
        }
        result = await recommendation_pipeline.ainvoke(initial_state)
    except Exception as e:
        logger.exception("Pipeline error processing recommendation request: %s", e)
        raise HTTPException(status_code=500, detail=f"Recommendation pipeline error: {e}")

    return ReplacementResponse(
        replacements=result.get("replacements", []),
        rejected_candidates=result.get("rejected", []),
        no_candidates_reason=result.get("no_candidates_reason"),
    )
