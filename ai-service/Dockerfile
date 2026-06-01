# =============================================================================
# Python AI Recommendation Service — multi-stage image (CPU PyTorch)
#
#   Embeddings : sentence-transformers + BAAI/bge-m3  (runs in-container, CPU)
#   Generation : Ollama qwen3.5:0.8b                  (separate container)
#
# Build (lean, downloads bge-m3 to a volume at runtime):
#   docker build -t sse-ai .
# Build a fully self-contained/offline image (bakes bge-m3 in, ~+2.3GB):
#   docker build --build-arg PRELOAD_EMBEDDING_MODEL=true -t sse-ai .
# =============================================================================

# ---- Stage 1: build a virtualenv with all dependencies ----
FROM python:3.12-slim AS builder

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY requirements.txt .
# Install the CPU-only PyTorch wheel first so sentence-transformers does not
# drag in the multi-GB CUDA build.
RUN pip install --upgrade pip \
 && pip install torch --index-url https://download.pytorch.org/whl/cpu \
 && pip install -r requirements.txt


# ---- Stage 2: slim runtime ----
FROM python:3.12-slim AS runtime

# libgomp1 is required by the PyTorch CPU wheel; ca-certificates for HF downloads.
RUN apt-get update \
 && apt-get install -y --no-install-recommends libgomp1 ca-certificates \
 && rm -rf /var/lib/apt/lists/*

COPY --from=builder /opt/venv /opt/venv

ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    HF_HOME=/cache/huggingface \
    SSE_OLLAMA_BASE_URL=http://ollama:11434 \
    SSE_EMBEDDING_DEVICE=cpu

WORKDIR /app
COPY app ./app
COPY examples ./examples

# Non-root user; ensure the HF cache dir is writable.
RUN useradd -m -u 10001 appuser \
 && mkdir -p /cache/huggingface \
 && chown -R appuser:appuser /cache /app
USER appuser

# Optionally bake the embedding model into the image for offline/self-contained
# use. Default OFF -> the model downloads once into the mounted cache volume.
ARG PRELOAD_EMBEDDING_MODEL=false
ARG SSE_EMBEDDING_MODEL=BAAI/bge-m3
RUN if [ "$PRELOAD_EMBEDDING_MODEL" = "true" ]; then \
      echo "Pre-downloading ${SSE_EMBEDDING_MODEL} ..." \
   && python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('${SSE_EMBEDDING_MODEL}')"; \
    fi

EXPOSE 8080

# Single worker: the embedding model loads once at startup (avoids N copies in RAM).
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080", "--workers", "1"]
