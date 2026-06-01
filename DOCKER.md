# Running the AI Service with Docker

A self-contained stack: a Streamlit **UI**, the Python **AI service**, **Ollama**
(text gen), and a **Milvus** vector DB, wired together. One command brings up
everything; the only thing outside is the .NET backend (which calls
`http://localhost:8000`).

```
┌──────────────────────────────────────────────────────────────┐
│ docker compose                                                 │
│                                                                │
│   ui ──REST──► ai-service ──REST──► ollama   (qwen3.5:0.8b)    │
│   (Streamlit)  (FastAPI +  ──gRPC──► milvus ─► etcd + minio    │
│    :8501        bge-m3 CPU)            attu (UI :8002)         │
└──────────────────────────────────────────────────────────────┘
        ▲
        │ http://localhost:8000   (.NET backend on host)
```

| Service | Purpose | Host port |
|---|---|---|
| `ui` | Streamlit demo UI | 8501 |
| `ai-service` | FastAPI recommendation + search API | 8000 |
| `ollama` (+`ollama-init`) | LLM explanations (qwen3.5:0.8b) | — |
| `milvus` (+`etcd`,`minio`) | Vector DB for product embeddings | 19530 |
| `attu` | Milvus web UI | 8002 |

## Prerequisites
- Docker Engine + Compose v2 (`docker compose version`)
- ~8 GB free disk + ~6 GB RAM (Milvus + models), internet for the first run

## Start it

```bash
docker compose up --build
```

What happens on first start:
1. `etcd` + `minio` + `milvus` boot (Milvus is healthy in ~30–90s).
2. `ollama` boots; `ollama-init` pulls **qwen3.5:0.8b**, then exits.
3. `ai-service` builds, downloads **BAAI/bge-m3** (~2.3 GB) into a cache volume,
   loads it on CPU, and connects to Milvus.

> ⏳ The **first** start can take several minutes (image + model downloads).
> Subsequent starts are fast — models and vectors persist in named volumes. The
> `ai-service` health check has a 180s grace period for the first-run download.

Seed the vector DB with a sample catalog (optional, for `/search/similar`):

```bash
docker compose exec ai-service python examples/seed_milvus.py
```

Run detached: `docker compose up --build -d`

## Verify

Open the **demo UI** at <http://localhost:8501> — pick a scenario and click
"Find replacements". Or via the API:

```bash
# Health (also shows embedding backend/device, Ollama + Milvus status)
curl http://localhost:8000/health

# A real recommendation
curl -X POST http://localhost:8000/recommendations/replacements \
  -H "Content-Type: application/json" \
  -d @ai-service/examples/sample_request.json
```

- Demo UI: <http://localhost:8501>
- Swagger UI: <http://localhost:8000/docs>
- Milvus UI (Attu): <http://localhost:8002>

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
| Port 8000 already in use | Change the `ports` mapping to e.g. `9090:8000`. |
| Want a clean slate | `docker compose down -v` removes the cached models. |
