# Running the AI Service with Docker

A self-contained stack: the Python AI service **and** Ollama, wired together.
One command brings up everything; the only thing outside is the .NET backend
(which just calls `http://localhost:8000`).

```
┌─────────────────────────────────────────────┐
│ docker compose                                │
│                                               │
│   ai-service  ──REST──►  ollama               │
│   (FastAPI +             (qwen3.5:0.8b)        │
│    bge-m3 on CPU)                             │
└─────────────────────────────────────────────┘
        ▲
        │ http://localhost:8000
   .NET backend (on host)
```

## Prerequisites
- Docker Engine + Compose v2 (`docker compose version`)
- ~6 GB free disk (images + model weights), internet for the first run

## Start it

```bash
docker compose up --build
```

What happens on first start:
1. `ollama` container boots.
2. `ollama-init` pulls **qwen3.5:0.8b** into a persistent volume, then exits.
3. `ai-service` builds, then downloads **BAAI/bge-m3** (~2.3 GB) into a cache
   volume and loads it on CPU.

> ⏳ The **first** start can take several minutes (model downloads). Subsequent
> starts are fast — both models are cached in named volumes. The `ai-service`
> health check has a 180s grace period to cover the first-run download.

Run detached: `docker compose up --build -d`

## Verify

```bash
# Health (also shows embedding backend/device and Ollama status)
curl http://localhost:8000/health

# A real recommendation
curl -X POST http://localhost:8000/recommendations/replacements \
  -H "Content-Type: application/json" \
  -d @ai-service/examples/sample_request.json
```

Swagger UI: <http://localhost:8000/docs>

## Everyday commands

```bash
docker compose logs -f ai-service      # follow the service logs
docker compose ps                      # status + health
docker compose down                    # stop (keeps model volumes)
docker compose down -v                 # stop AND delete cached models
docker compose build ai-service        # rebuild after code changes
docker compose up -d --no-deps ai-service   # restart just the AI service
```

## Connecting the .NET backend

- **.NET running on the host** → use `http://localhost:8000` (default in
  `appsettings.json`). Nothing else to do.
- **.NET also in Docker** → put it on the same compose network and call
  `http://ai-service:8000`, or from a separate compose use
  `http://host.docker.internal:8000`.

## Configuration

All `SSE_*` settings (see [`.env.example`](.env.example)) can be set under the
`ai-service.environment` block in [`docker-compose.yml`](docker-compose.yml).
Useful ones:

| Variable | In compose | Effect |
|---|---|---|
| `SSE_ENABLE_LLM_EXPLANATIONS` | `false` | Skip Ollama → instant template explanations |
| `SSE_ENABLE_EMBEDDINGS` | `false` | Skip bge-m3 → lexical similarity (no 2.3 GB download) |
| `SSE_CHAT_MODEL` | e.g. `llama3.2` | Different Ollama model (update `ollama-init` to pull it) |

## Offline / fully self-contained image

Bake the embedding model into the image (no runtime download, larger image):

```bash
docker build --build-arg PRELOAD_EMBEDDING_MODEL=true -t sse-ai:offline .
```
Then run without the `hf-cache` volume so the baked-in weights are used.

## GPU (optional)

The default image uses **CPU PyTorch** for portability. For GPU embeddings:
1. Build against a CUDA torch wheel (change the torch install line in the
   `Dockerfile` to a CUDA index URL).
2. Add a GPU reservation to `ai-service` (see the commented block at the bottom
   of `docker-compose.yml`) and set `SSE_EMBEDDING_DEVICE=cuda`.
3. Requires the NVIDIA Container Toolkit on the host.

## Troubleshooting

| Symptom | Fix |
|---|---|
| `ai-service` unhealthy on first run | Still downloading bge-m3 — watch `docker compose logs -f ai-service`; it recovers when the load finishes. |
| Explanations are templates, not LLM | `qwen3.5:0.8b` not pulled yet — check `docker compose logs ollama-init`. |
| Port 8000 already in use | Change the `ports` mapping to e.g. `8080:8000`. |
| Want a clean slate | `docker compose down -v` removes the cached models. |
