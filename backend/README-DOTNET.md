# .NET Backend — Day 1 Setup

## Create the project

```bash
dotnet new webapi -n SmartSubstitution.Api
cd SmartSubstitution.Api
dotnet add package MongoDB.Driver
dotnet add package Microsoft.AspNetCore.OpenApi
dotnet add package Swashbuckle.AspNetCore
```

## Critical rules

**MongoClient must be Singleton** (already in HACKATHON.md — double-check Program.cs):
```csharp
builder.Services.AddSingleton<IMongoClient>(sp => {
    var settings = sp.GetRequiredService<IOptions<MongoDbSettings>>().Value;
    return new MongoClient(settings.ConnectionString);
});
```
If registered as Scoped or Transient, Atlas M0 connection limit (500) is exhausted in ~5 requests.

**All MongoDB operations must use async API** — no `.ToList()`, no blocking calls:
```csharp
// Correct
var cursor = await collection.FindAsync(filter);
var docs = await cursor.ToListAsync();

// Wrong — blocks the thread pool
var docs = collection.Find(filter).ToList();
```

**Python service timeout: 30 seconds** (appsettings.json already set).
Ollama on CPU takes 8-25s; 5s will time out on every request.

**JSON deserialization: snake_case** (Python FastAPI sends snake_case):
```csharp
builder.Services.AddControllers().AddJsonOptions(opts => {
    opts.JsonSerializerOptions.PropertyNamingPolicy = JsonNamingPolicy.SnakeCaseLower;
});
// Same policy needed when deserializing Python responses in HttpClient calls:
var opts = new JsonSerializerOptions { PropertyNamingPolicy = JsonNamingPolicy.SnakeCaseLower };
var result = JsonSerializer.Deserialize<ReplacementResponse>(responseBody, opts);
```

## Day 1 checklist

- [ ] Create .NET Web API project (commands above)
- [ ] Provision MongoDB Atlas M0 — connection string → appsettings.Development.json (gitignored)
- [ ] Verify Atlas connection via GET /health (ping the database)
- [ ] Create DTOs and domain models (include dietary_tags, confidence_pct, confidence_label)
- [ ] Add Swagger / OpenAPI
- [ ] Confirm MongoClient is AddSingleton in Program.cs
- [ ] Confirm PythonAiService:TimeoutSeconds is 30

## Day 2 smoke test

Before building CRUD endpoints, call the Python stub:

```csharp
// Minimal smoke test in a test controller or xUnit test
var payload = new {
    company = new { id = "company_001", name = "Marco's Italian Kitchen" },
    requested_product = new {
        id = "product_001", name = "Chicken Breast 2kg",
        category_id = "cat_chicken", brand = "Brand A",
        unit = "kg", pack_size = 2, base_price = 10.0,
        dietary_tags = new[] { "halal" }
    },
    requested_quantity = 20,
    contract_items = new[] { new { product_id = "product_001", contract_price = 9.2, is_preferred = true } },
    candidate_products = new object[] { },
    max_results = 3,
    use_ai_explanation = false
};
// POST to http://localhost:8000/recommendations/replacements
// Verify response contains: replacements[], rejected_candidates[], confidence_pct, confidence_label
```

## Recommended indexes

```csharp
// Add after Atlas connection verified — in startup or a migration helper
var productCollection = db.GetCollection<Product>("products");
await productCollection.Indexes.CreateManyAsync(new[] {
    // Compound index for CandidateProductService query pattern
    new CreateIndexModel<Product>(
        Builders<Product>.IndexKeys.Ascending(p => p.CategoryId).Ascending(p => p.IsActive)
    ),
    new CreateIndexModel<Product>(
        Builders<Product>.IndexKeys.Ascending(p => p.IsActive)
    ),
});
var inventoryCollection = db.GetCollection<Inventory>("inventory");
await inventoryCollection.Indexes.CreateOneAsync(
    new CreateIndexModel<Inventory>(
        Builders<Inventory>.IndexKeys.Ascending(i => i.ProductId)
    )
);
```
