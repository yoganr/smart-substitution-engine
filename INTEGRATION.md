# .NET ↔ Python AI Service — Integration Guide

This is everything the **C# .NET engineer** needs to call the Python AI
Recommendation Service. The Python side is done, tested, and live-verified.

> TL;DR: `POST http://localhost:8000/recommendations/replacements` with the JSON
> below, deserialize the response, save it to `recommendation_logs`, return it to
> the client. The Python service is **stateless** — it never touches MongoDB.

---

## 1. Run the Python service (one command)

**Easiest — Docker (brings up the AI service + Ollama together):**

```bash
docker compose up --build      # serves on http://localhost:8000
```

**Or local Python** (on the AI engineer's machine or yours):

```powershell
# Ollama must be running (it powers the text explanations)
ollama serve            # if not already running

python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

- Swagger UI: <http://localhost:8000/docs>
- Health (also reports Ollama status): `GET http://localhost:8000/health`

Point your .NET config at it:

```jsonc
// appsettings.json
{
  "PythonAiService": { "BaseUrl": "http://localhost:8000" }
}
```

If the AI service runs on another laptop, use that machine's LAN IP, e.g.
`http://192.168.1.42:8000`.

---

## 2. The contract (verified against the live service)

### Request — `POST /recommendations/replacements`

```json
{
  "company": { "id": "company_001", "name": "ABC Restaurant" },
  "requested_product": {
    "id": "product_001",
    "name": "Chicken Breast 2kg",
    "category_id": "cat_chicken",
    "brand": "Brand A",
    "unit": "kg",
    "pack_size": 2,
    "base_price": 10.0
  },
  "requested_quantity": 20,
  "contract_items": [
    { "product_id": "product_001", "contract_price": 9.2, "is_preferred": true }
  ],
  "candidate_products": [
    {
      "id": "product_2033",
      "name": "Chicken Breast Premium 2kg",
      "category_id": "cat_chicken",
      "brand": "Brand B",
      "unit": "kg",
      "pack_size": 2,
      "base_price": 10.5,
      "stock_quantity": 150,
      "contract_price": 9.5
    }
  ],
  "max_results": 3,
  "use_ai_explanation": true
}
```

**Field notes**
- `contract_items` / `candidate_products` may be empty arrays.
- `contract_price`, `brand`, `unit`, `pack_size` are optional (nullable).
- `is_active` on a candidate defaults to `true` if omitted.
- `requested_quantity` must be `> 0`, `max_results >= 1` (else HTTP 422).
- Set `use_ai_explanation: false` to skip the LLM and get instant deterministic
  template explanations (useful for fast demos / when Ollama is off).

### Response

```json
{
  "replacements": [
    {
      "product_id": "product_2033",
      "name": "Chicken Breast Premium 2kg",
      "final_score": 83,
      "score_breakdown": {
        "category_similarity": 30,
        "contract_match": 18,
        "price_similarity": 17,
        "stock_availability": 10,
        "unit_pack_similarity": 8
      },
      "explanation": "Chicken Breast Premium 2kg is under contract and matches the category with sufficient stock and a minimal price difference.",
      "brand": "Brand B",
      "unit": "kg",
      "pack_size": 2.0,
      "base_price": 10.5,
      "contract_price": 9.5,
      "effective_price": 9.5,
      "stock_quantity": 150.0,
      "is_under_contract": true,
      "is_preferred": false,
      "explanation_source": "ollama"
    }
  ],
  "requested_product_id": "product_001",
  "replacement_needed": true,
  "candidates_evaluated": 4,
  "candidates_rejected": 0,
  "warnings": []
}
```

- `final_score` always equals the sum of `score_breakdown` (0–93).
- `explanation_source` is `"ollama"` when the LLM wrote it, `"template"` when it
  fell back (Ollama down / disabled). Either way `explanation` is always present.
- The fields after `explanation` are **additive diagnostics** — handy for logs,
  safe to ignore. `System.Text.Json` drops unknown fields by default, so your
  DTO only needs the fields you care about.

---

## 3. Drop-in C# client (.NET 8)

All JSON is `snake_case`. .NET 8 has a built-in policy for that
(`JsonNamingPolicy.SnakeCaseLower`) so **no `[JsonPropertyName]` attributes are
needed** — property names map automatically.

### 3a. DTOs — `AiContracts.cs`

```csharp
namespace Hackathon.Api.AiService;

// ---- Request ----
public record AiCompany(string Id, string Name);

public record AiRequestedProduct(
    string Id,
    string Name,
    string CategoryId,
    double BasePrice,
    string? Brand = null,
    string? Unit = null,
    double? PackSize = null);

public record AiContractItem(
    string ProductId,
    double? ContractPrice = null,
    bool IsPreferred = false);

public record AiCandidateProduct(
    string Id,
    string Name,
    string CategoryId,
    double BasePrice,
    double StockQuantity,
    string? Brand = null,
    string? Unit = null,
    double? PackSize = null,
    double? ContractPrice = null,
    bool IsActive = true);

public record AiReplacementRequest(
    AiCompany Company,
    AiRequestedProduct RequestedProduct,
    double RequestedQuantity,
    IReadOnlyList<AiContractItem> ContractItems,
    IReadOnlyList<AiCandidateProduct> CandidateProducts,
    int MaxResults = 3,
    bool UseAiExplanation = true);

// ---- Response ----
public record AiScoreBreakdown(
    int CategorySimilarity,
    int ContractMatch,
    int PriceSimilarity,
    int StockAvailability,
    int UnitPackSimilarity);

public record AiReplacement(
    string ProductId,
    string Name,
    int FinalScore,
    AiScoreBreakdown ScoreBreakdown,
    string Explanation,
    bool IsUnderContract = false,
    bool IsPreferred = false,
    double? EffectivePrice = null,
    string ExplanationSource = "template");

public record AiReplacementResponse(
    IReadOnlyList<AiReplacement> Replacements,
    string? RequestedProductId = null,
    bool ReplacementNeeded = true,
    int CandidatesEvaluated = 0,
    int CandidatesRejected = 0,
    IReadOnlyList<string>? Warnings = null);
```

### 3b. Typed HttpClient — `AiRecommendationClient.cs`

```csharp
using System.Net.Http.Json;
using System.Text.Json;

namespace Hackathon.Api.AiService;

public interface IAiRecommendationClient
{
    Task<AiReplacementResponse?> GetReplacementsAsync(
        AiReplacementRequest request, CancellationToken ct = default);
}

public sealed class AiRecommendationClient : IAiRecommendationClient
{
    private static readonly JsonSerializerOptions Json = new()
    {
        PropertyNamingPolicy = JsonNamingPolicy.SnakeCaseLower,   // .NET 8+
        PropertyNameCaseInsensitive = true,
        DefaultIgnoreCondition =
            System.Text.Json.Serialization.JsonIgnoreCondition.WhenWritingNull,
    };

    private readonly HttpClient _http;
    private readonly ILogger<AiRecommendationClient> _logger;

    public AiRecommendationClient(HttpClient http, ILogger<AiRecommendationClient> logger)
    {
        _http = http;
        _logger = logger;
    }

    public async Task<AiReplacementResponse?> GetReplacementsAsync(
        AiReplacementRequest request, CancellationToken ct = default)
    {
        try
        {
            using var resp = await _http.PostAsJsonAsync(
                "/recommendations/replacements", request, Json, ct);
            resp.EnsureSuccessStatusCode();
            return await resp.Content.ReadFromJsonAsync<AiReplacementResponse>(Json, ct);
        }
        catch (Exception ex) when (ex is HttpRequestException or TaskCanceledException)
        {
            // Graceful degradation: Python/Ollama down or slow -> no recommendation.
            _logger.LogWarning(ex, "AI recommendation service unavailable.");
            return null;
        }
    }
}
```

### 3c. Register it — `Program.cs`

```csharp
builder.Services.AddHttpClient<IAiRecommendationClient, AiRecommendationClient>(client =>
{
    var baseUrl = builder.Configuration["PythonAiService:BaseUrl"]
                  ?? "http://localhost:8000";
    client.BaseAddress = new Uri(baseUrl);
    client.Timeout = TimeSpan.FromSeconds(60); // LLM explanations can take a few seconds
});
```

> Optional resilience (Day 3 "circuit breaker" task): add the
> `Microsoft.Extensions.Http.Resilience` NuGet package and chain
> `.AddStandardResilienceHandler()` after `AddHttpClient`. The `try/catch` above
> already prevents a Python outage from breaking your endpoint.

---

## 4. Wire it into the recommendation flow

This is step 5–10 of the flow in `HACKATHON.md`. After you've loaded the
out-of-stock product and queried candidate products from Atlas:

```csharp
app.MapPost("/recommendations/replacements", async (
    ReplacementQuery query,                  // { companyId, productId, quantity }
    IMongoDatabase db,
    IAiRecommendationClient ai,
    CancellationToken ct) =>
{
    // 1–6. Load from Atlas (company, product, inventory, candidates, contracts).
    var company  = await LoadCompanyAsync(db, query.CompanyId, ct);
    var product  = await LoadProductAsync(db, query.ProductId, ct);
    var inventory = await LoadInventoryAsync(db, query.ProductId, ct);

    // Short-circuit: still in stock -> no replacement needed.
    if (inventory is not null && inventory.StockQuantity >= query.Quantity)
        return Results.Ok(new { replacement_needed = false });

    var candidates = await LoadEligibleCandidatesAsync(   // same category, active, in stock
        db, product.CategoryId, query.ProductId, query.Quantity, ct);
    var contractItems = await LoadCompanyContractItemsAsync(db, query.CompanyId, ct);

    // 7. Build the payload and call Python.
    var aiRequest = new AiReplacementRequest(
        Company: new AiCompany(company.Id, company.Name),
        RequestedProduct: new AiRequestedProduct(
            product.Id, product.Name, product.CategoryId, product.BasePrice,
            product.Brand, product.Unit, product.PackSize),
        RequestedQuantity: query.Quantity,
        ContractItems: contractItems
            .Select(c => new AiContractItem(c.ProductId, c.ContractPrice, c.IsPreferred))
            .ToList(),
        CandidateProducts: candidates
            .Select(c => new AiCandidateProduct(
                c.Id, c.Name, c.CategoryId, c.BasePrice, c.StockQuantity,
                c.Brand, c.Unit, c.PackSize, c.ContractPrice, c.IsActive))
            .ToList(),
        MaxResults: 3,
        UseAiExplanation: true);

    var result = await ai.GetReplacementsAsync(aiRequest, ct);
    if (result is null)
        return Results.Problem("AI recommendation service is unavailable.", statusCode: 503);

    // 9. Save the recommendation log to Atlas.
    await db.GetCollection<RecommendationLog>("recommendation_logs").InsertOneAsync(
        new RecommendationLog
        {
            CompanyId = company.Id,
            RequestedProductId = product.Id,
            RequestedQuantity = query.Quantity,
            Replacements = result.Replacements,
            CreatedAt = DateTime.UtcNow,
        }, cancellationToken: ct);

    // 10. Return to the client.
    return Results.Ok(result);
});
```

---

## 5. Quick manual test (no .NET needed)

```powershell
# from the repo root
curl -X POST http://localhost:8000/recommendations/replacements `
  -H "Content-Type: application/json" `
  -d "@examples/sample_request.json"
```

A ready-made payload lives at [`examples/sample_request.json`](examples/sample_request.json).

---

## 6. Contract checklist (so both sides stay in sync)

| Concern | Agreement |
|---|---|
| Endpoint | `POST /recommendations/replacements` |
| JSON casing | `snake_case` (use `JsonNamingPolicy.SnakeCaseLower`) |
| Who owns MongoDB | **.NET only** — Python receives all data in the request |
| Who picks winners | **Python** (deterministic scoring); LLM only explains |
| `final_score` range | 0–93, equals sum of `score_breakdown` |
| Python down? | Client returns `null` → .NET responds 503 (no crash) |
| Ollama down? | Python still returns scored results with template explanations |
| Unknown JSON fields | Safely ignored by `System.Text.Json` |

Ping the AI engineer if you need extra fields on the candidate payload — adding
optional fields is backward-compatible on both sides.
