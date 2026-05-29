# --- Python AI Recommendation Service ---
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY examples ./examples

EXPOSE 8000

# Reach a host-machine Ollama from inside the container by default.
ENV SSE_OLLAMA_BASE_URL=http://host.docker.internal:11434

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
