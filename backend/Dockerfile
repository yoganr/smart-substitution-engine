# =============================================================================
# .NET 7 Web API — SmartSubstitution.Api (the C# backend / orchestrator).
#
# Receives a replacement request, reads the catalog from MongoDB, calls the
# Python AI service for ranking, logs the result. Built as part of the full
# stack in docker-compose.yml (service: backend).
#
#   docker compose build backend
#
# Connection strings / service URLs are injected by compose `environment:`
# (ASP.NET "__" nested-config convention), so no code or appsettings edits are
# needed to switch between local `dotnet run` and the container.
# =============================================================================

# ---- Stage 1: restore + publish ----
FROM mcr.microsoft.com/dotnet/sdk:7.0 AS build
WORKDIR /src

# Restore first so this layer is cached unless the .csproj changes.
COPY SmartSubstitution.Api/SmartSubstitution.Api.csproj SmartSubstitution.Api/
RUN dotnet restore SmartSubstitution.Api/SmartSubstitution.Api.csproj

# Copy the rest of the source and publish a trimmed Release build.
COPY SmartSubstitution.Api/ SmartSubstitution.Api/
RUN dotnet publish SmartSubstitution.Api/SmartSubstitution.Api.csproj \
      -c Release -o /app/publish /p:UseAppHost=false

# ---- Stage 2: slim runtime ----
FROM mcr.microsoft.com/dotnet/aspnet:7.0 AS runtime
WORKDIR /app

# curl is only needed for the container healthcheck (hits /health).
RUN apt-get update \
 && apt-get install -y --no-install-recommends curl \
 && rm -rf /var/lib/apt/lists/*

COPY --from=build /app/publish .

# Listen on 8080 inside the container (compose publishes it on host :5000).
ENV ASPNETCORE_URLS=http://+:8080 \
    ASPNETCORE_ENVIRONMENT=Production \
    DOTNET_RUNNING_IN_CONTAINER=true

EXPOSE 8080

HEALTHCHECK --interval=15s --timeout=5s --retries=10 --start-period=20s \
  CMD curl -f http://localhost:8080/health || exit 1

ENTRYPOINT ["dotnet", "SmartSubstitution.Api.dll"]
