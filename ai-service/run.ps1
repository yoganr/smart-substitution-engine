# Run the Smart Substitution Engine AI service.
#   ./run.ps1            -> starts on port 8080 with auto-reload
#   ./run.ps1 -Port 8080 -> custom port
param(
    [int]$Port = 8080,
    [switch]$NoReload
)

$ErrorActionPreference = "Stop"

# Warn if Ollama is not reachable (the service still runs with template fallback).
try {
    Invoke-RestMethod -Uri "http://localhost:11434/api/tags" -TimeoutSec 3 | Out-Null
    Write-Host "Ollama is reachable." -ForegroundColor Green
} catch {
    Write-Host "WARNING: Ollama not reachable at localhost:11434 — explanations will use the template fallback." -ForegroundColor Yellow
}

$reload = if ($NoReload) { "" } else { "--reload" }
Write-Host "Starting service on http://localhost:$Port (Swagger: /docs)" -ForegroundColor Cyan
python -m uvicorn app.main:app --host 0.0.0.0 --port $Port $reload
