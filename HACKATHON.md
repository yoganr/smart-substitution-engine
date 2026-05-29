# 3-Day Hackathon: AI Product Replacement Service

> **Team:** 2 engineers — Python AI Engineer + C# .NET Engineer  
> **Stack:** .NET 8 Web API · Python FastAPI · LangGraph · LangChain · Ollama · MongoDB Atlas

---

## Architecture

```
Client / Swagger
      │
      ▼
.NET Backend API ◄──────► MongoDB Atlas (cloud)
      │
      │  REST
      ▼
Python AI Recommendation Service
      │
      ▼
    Ollama
```

**Rules:**
- MongoDB Atlas is owned exclusively by the .NET backend
- The Python service receives all data from .NET and returns recommendations only
- Python never queries Atlas directly in the MVP

---

## Shared API Contract

### .NET → Python request

`POST /recommendations/replacements`

```json
{
  "company": {
    "id": "company_001",
    "name": "ABC Restaurant"
  },
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
    {
      "product_id": "product_001",
      "contract_price": 9.2,
      "is_preferred": true
    }
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

### Python → .NET response

```json
{
  "replacements": [
    {
      "product_id": "product_2033",
      "name": "Chicken Breast Premium 2kg",
      "final_score": 93,
      "score_breakdown": {
        "category_similarity": 30,
        "contract_match": 25,
        "price_similarity": 20,
        "stock_availability": 10,
        "unit_pack_similarity": 8
      },
      "explanation": "Strong replacement: same category, sufficient stock, similar contract price."
    }
  ]
}
```

---

## Person 1 — Python AI Engineer

### Owns
- Python FastAPI service
- LangGraph workflow
- LangChain + Ollama integration
- Deterministic scoring logic
- Replacement ranking
- AI-generated explanations
- Recommendation unit tests

### Endpoints

```
GET  /health
POST /recommendations/replacements
```

### LangGraph Workflow Nodes

```
validate_input
      │
apply_hard_filters
      │
score_candidates
      │
rank_replacements
      │
generate_ollama_explanations
      │
return_result
```

### Hard Filter Rules

| Filter | Rule |
|---|---|
| Active products only | `is_active == true` |
| Sufficient stock | `stock_quantity >= requested_quantity` |
| Compatible category | `category_id` matches or is compatible |
| Not same product | `id != requested_product.id` |
| Acceptable price | price increase within threshold |

### Scoring Breakdown

| Dimension | Max Points |
|---|---|
| Category similarity | 30 |
| Contract match | 25 |
| Price similarity | 20 |
| Stock availability | 10 |
| Unit / pack similarity | 8 |
| **Total** | **93+** |

### MVP Rule

> The LLM does **not** choose replacements.  
> Python picks winners via deterministic scoring.  
> Ollama only writes a short explanation **after** ranking is complete.  
> If Ollama fails, a template explanation is used as fallback.

---

### Day 1

- [ ] Create Python FastAPI project structure
- [ ] Define Pydantic schemas for input/output
- [ ] Build recommendation logic with mock JSON input
- [ ] Implement all hard filters
- [ ] Implement deterministic scoring

### Day 2

- [ ] Add LangGraph workflow (wire all nodes)
- [ ] Add LangChain + Ollama explanation node
- [ ] Add fallback template explanation if Ollama is unavailable
- [ ] Test end-to-end with a real JSON payload from .NET

### Day 3

- [ ] Tune scoring weights
- [ ] Write unit tests for key recommendation cases
- [ ] Finalize Swagger/OpenAPI docs
- [ ] Help .NET engineer wire up the integration

---

## Person 2 — C# .NET Backend Engineer

### Owns
- Main .NET Web API
- MongoDB Atlas (all reads and writes)
- CRUD endpoints
- Swagger documentation
- Seed data
- Calling Python AI service
- Saving recommendation logs
- Final demo endpoint

### Endpoints

```
GET    /health

POST   /companies
GET    /companies
GET    /companies/{id}

POST   /products
GET    /products
GET    /products/{id}
PATCH  /products/{id}

POST   /contracts
GET    /companies/{companyId}/contracts
POST   /contracts/{contractId}/items

POST   /inventory
PATCH  /inventory/{productId}
GET    /inventory/{productId}

POST   /recommendations/replacements
GET    /recommendations/logs
```

### MongoDB Atlas Collections

```
companies
products
contracts
inventory
recommendation_logs
```

> Collections are auto-created on first insert — no manual schema creation needed.

### Atlas Setup (do before Day 1 coding)

1. Sign up at [cloud.mongodb.com](https://cloud.mongodb.com)
2. Create a free **M0 cluster** (Shared, free tier)
3. **Database Access** → create a DB user with username + password
4. **Network Access** → add `0.0.0.0/0` (allow all IPs — fine for hackathon)
5. **Connect** → **Connect your application** → copy the connection string:

```
mongodb+srv://<username>:<password>@<cluster>.mongodb.net/<dbname>?retryWrites=true&w=majority
```

### Configuration

**`appsettings.json`** (safe to commit — no real credentials):
```json
{
  "MongoDB": {
    "ConnectionString": "",
    "DatabaseName": "hackathon_db"
  },
  "PythonAiService": {
    "BaseUrl": "http://localhost:8000"
  }
}
```

**`appsettings.Development.json`** (add to `.gitignore` — real credentials go here):
```json
{
  "MongoDB": {
    "ConnectionString": "mongodb+srv://hackathon_user:YOUR_PASSWORD@cluster0.xxxxx.mongodb.net/?retryWrites=true&w=majority",
    "DatabaseName": "hackathon_db"
  }
}
```

### Settings Model

```csharp
// MongoDbSettings.cs
public class MongoDbSettings
{
    public string ConnectionString { get; set; } = null!;
    public string DatabaseName { get; set; } = null!;
}
```

### Service Registration

```csharp
// Program.cs
builder.Services.Configure<MongoDbSettings>(
    builder.Configuration.GetSection("MongoDB"));

builder.Services.AddSingleton<IMongoClient>(sp =>
{
    var settings = sp.GetRequiredService<IOptions<MongoDbSettings>>().Value;
    return new MongoClient(settings.ConnectionString);
});

builder.Services.AddScoped<IMongoDatabase>(sp =>
{
    var settings = sp.GetRequiredService<IOptions<MongoDbSettings>>().Value;
    var client = sp.GetRequiredService<IMongoClient>();
    return client.GetDatabase(settings.DatabaseName);
});
```

**NuGet package required:**
```
MongoDB.Driver
```

### Recommended Indexes

```csharp
Builders<Product>.IndexKeys.Ascending(p => p.CategoryId)
Builders<Product>.IndexKeys.Ascending(p => p.IsActive)
Builders<Inventory>.IndexKeys.Ascending(i => i.ProductId)
Builders<Contract>.IndexKeys.Ascending(c => c.CompanyId)
```

### Recommendation Flow

When client calls `POST /recommendations/replacements`:

```
1. Load company from Atlas
2. Load requested product from Atlas
3. Check inventory in Atlas
4. If product is in stock → return { replacement_needed: false }
5. If out of stock → query candidate products from Atlas (same category, active, in stock)
6. Load company contract items from Atlas
7. POST prepared payload to Python AI service
8. Receive ranked replacements from Python
9. Save recommendation log to Atlas
10. Return final response to client
```

---

### Day 1

- [ ] Create .NET Web API project
- [ ] **Provision MongoDB Atlas M0 cluster**
- [ ] **Add connection string to `appsettings.Development.json`**
- [ ] Verify Atlas connection via `/health` endpoint (ping the database)
- [ ] Create DTOs and domain models
- [ ] Add Swagger / OpenAPI
- [ ] Confirm both engineers can connect to the shared Atlas cluster

### Day 2

- [ ] Build all CRUD endpoints
- [ ] Write and run seed data script
- [ ] Add MongoDB indexes
- [ ] Build `CandidateProductService` — queries Atlas for eligible replacements
- [ ] Stub out Python service client (HttpClient wrapper)

### Day 3

- [ ] Wire up full recommendation flow end-to-end
- [ ] Implement `recommendation_logs` collection write
- [ ] Add error handling for Python service unavailability (timeout, circuit-breaker)
- [ ] Final Swagger cleanup and endpoint descriptions
- [ ] Prepare demo scenario with seed data

---

## Responsibility Matrix

| Area | Python Engineer | .NET Engineer |
|---|---|---|
| FastAPI service | ✅ | |
| LangGraph / LangChain | ✅ | |
| Ollama integration | ✅ | |
| Scoring & ranking | ✅ | |
| AI explanations | ✅ | |
| Recommendation tests | ✅ | |
| .NET Web API | | ✅ |
| MongoDB Atlas | | ✅ |
| CRUD endpoints | | ✅ |
| Swagger docs | | ✅ |
| Seed data | | ✅ |
| Python service client | | ✅ |
| Recommendation logs | | ✅ |
| Demo scenario | | ✅ |

---

## Why MongoDB Atlas vs Local

| | Local MongoDB | MongoDB Atlas |
|---|---|---|
| Setup | Install + run locally | Sign up, create free cluster |
| Connection string | `mongodb://localhost:27017` | `mongodb+srv://user:pass@cluster.mongodb.net/db` |
| Shared between both engineers | ❌ (each has own local data) | ✅ (one cloud instance) |
| Data survives restarts | Depends on local config | ✅ Always persistent |
| Cost | Free | Free (M0 tier) |
| Day 3 integration testing | Risky — data divergence | ✅ Both hit same data |

> **Biggest hackathon win:** both engineers share one Atlas cluster, so seed data seeded by the .NET engineer is immediately available when testing the Python integration on Day 3.