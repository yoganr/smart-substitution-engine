using Microsoft.AspNetCore.Mvc;
using Microsoft.Extensions.Options;
using MongoDB.Driver;
using SmartSubstitution.Api.Dtos;
using SmartSubstitution.Api.Models;
using SmartSubstitution.Api.Settings;

namespace SmartSubstitution.Api.Services;

/// <summary>
/// Reads CatalogProduct documents from the local network MongoDB and maps
/// them to the DTOs the Python AI service expects.
///
/// Every query is scoped to a list of ContractNumbers — the catalogs the
/// requesting user has access to.
/// </summary>
public class LocalCatalogService
{
    private readonly IMongoClient                     _client;
    private readonly IMongoCollection<CatalogProduct> _collection;

    public LocalCatalogService(
        [FromKeyedServices("local")] IMongoClient client,
        IOptions<LocalMongoDbSettings> opts)
    {
        var s   = opts.Value;
        _client = client;
        _collection = client
            .GetDatabase(s.DatabaseName)
            .GetCollection<CatalogProduct>(s.CollectionName);
    }

    // ── Diagnostics ───────────────────────────────────────────────────────────

    public async Task<object> DiagnosticAsync(CancellationToken ct = default)
    {
        var dbList    = await _client.ListDatabaseNamesAsync(ct);
        var databases = await dbList.ToListAsync(ct);
        var db        = _collection.Database;
        var colList   = await db.ListCollectionNamesAsync(cancellationToken: ct);
        var collections = await colList.ToListAsync(ct);
        var count  = await _collection.CountDocumentsAsync(FilterDefinition<CatalogProduct>.Empty, cancellationToken: ct);
        var sample = await _collection.Find(FilterDefinition<CatalogProduct>.Empty).Limit(1).FirstOrDefaultAsync(ct);
        return new
        {
            configuredDatabase      = db.DatabaseNamespace.DatabaseName,
            configuredCollection    = _collection.CollectionNamespace.CollectionName,
            allDatabases            = databases,
            collectionsInDatabase   = collections,
            collectionDocumentCount = count,
            sampleItemNumber        = sample?.ItemNumber,
            sampleName              = sample?.Name,
            sampleContractNumber    = sample?.ContractNumber,
        };
    }

    // ── Queries ───────────────────────────────────────────────────────────────

    /// <summary>
    /// Exact lookup using the full composite key:
    /// ItemNumber + SellerAccountNumber + ContractNumber.
    /// This is the preferred lookup when all three identifiers are known.
    /// </summary>
    public Task<CatalogProduct?> GetByCompositeKeyAsync(
        string itemNumber,
        string sellerAccountNumber,
        string contractNumber,
        CancellationToken ct = default)
    {
        var filter = Builders<CatalogProduct>.Filter.And(
            Builders<CatalogProduct>.Filter.Eq(p => p.ItemNumber,          itemNumber),
            Builders<CatalogProduct>.Filter.Eq(p => p.SellerAccountNumber, sellerAccountNumber),
            Builders<CatalogProduct>.Filter.Eq(p => p.ContractNumber,      contractNumber));

        return _collection.Find(filter).FirstOrDefaultAsync(ct)!;
    }

    /// <summary>
    /// Lookup by ItemNumber only, optionally scoped to contract numbers.
    /// Used by the catalog browse endpoints when only the item number is known.
    /// </summary>
    public Task<CatalogProduct?> GetByItemNumberAsync(
        string itemNumber,
        List<string>? contractNumbers = null,
        CancellationToken ct = default)
    {
        var filter = Builders<CatalogProduct>.Filter.Eq(p => p.ItemNumber, itemNumber);
        if (contractNumbers is { Count: > 0 })
            filter &= Builders<CatalogProduct>.Filter.In(p => p.ContractNumber, contractNumbers);

        return _collection.Find(filter).FirstOrDefaultAsync(ct)!;
    }

    /// <summary>
    /// Candidates in the same category, scoped to the user's contract numbers.
    /// Availability is read directly from the product's StockAreas field.
    /// When <paramref name="preferredPartType"/> is "CU" or "TU", only candidates
    /// available in that specific PartType are returned.
    /// </summary>
    public async Task<List<CatalogProduct>> GetCandidatesAsync(
        CatalogProduct requestedProduct,
        List<string> contractNumbers,
        string? preferredPartType = null,
        CancellationToken ct = default)
    {
        // ── Category filter ───────────────────────────────────────────────────
        FilterDefinition<CatalogProduct> categoryFilter;

        var hasPath = requestedProduct.CategoryPaths.Any(p => !string.IsNullOrWhiteSpace(p));
        if (hasPath)
        {
            var top = ExtractTopCategory(requestedProduct.CategoryPaths.First(p => !string.IsNullOrWhiteSpace(p)));
            categoryFilter = Builders<CatalogProduct>.Filter.Regex(
                p => p.CategoryPaths[-1], new MongoDB.Bson.BsonRegularExpression(top, "i"));
        }
        else if (requestedProduct.CatalogCategories.Count > 0)
        {
            var catId = requestedProduct.CatalogCategories.First();
            categoryFilter = Builders<CatalogProduct>.Filter.AnyEq(p => p.CatalogCategories, catId);
        }
        else
        {
            return new List<CatalogProduct>();
        }

        // ── Contract + active filter ──────────────────────────────────────────
        var filter = Builders<CatalogProduct>.Filter.And(
            categoryFilter,
            Builders<CatalogProduct>.Filter.In(p => p.ContractNumber, contractNumbers),
            Builders<CatalogProduct>.Filter.Ne(p => p.ItemNumber, requestedProduct.ItemNumber),
            Builders<CatalogProduct>.Filter.Eq(p => p.Expired, 0));

        var products = await _collection.Find(filter).Limit(50).ToListAsync(ct);

        return products.Where(p => preferredPartType switch
        {
            "CU" => p.IsCuAvailable,
            "TU" => p.IsTuAvailable,
            _    => p.IsAvailable,
        }).ToList();
    }

    /// <summary>Text search scoped to the user's contract numbers.</summary>
    public async Task<List<CatalogProduct>> SearchAsync(
        string query,
        List<string>? contractNumbers = null,
        int limit = 20,
        CancellationToken ct = default)
    {
        var textFilter = Builders<CatalogProduct>.Filter.Or(
            Builders<CatalogProduct>.Filter.Regex(p => p.Name, new MongoDB.Bson.BsonRegularExpression(query, "i")),
            Builders<CatalogProduct>.Filter.Regex(p => p.SearchData, new MongoDB.Bson.BsonRegularExpression(query, "i")));

        var filter = contractNumbers is { Count: > 0 }
            ? textFilter & Builders<CatalogProduct>.Filter.In(p => p.ContractNumber, contractNumbers)
            : textFilter;

        return await _collection.Find(filter).Limit(limit).ToListAsync(ct);
    }

    // ── Mapper ────────────────────────────────────────────────────────────────

    /// <summary>
    /// Maps to PythonCandidateProductDto.
    /// Since all candidates are already scoped to the user's contract numbers,
    /// pass the product's own unit price as the contractPrice so the Python
    /// scoring engine awards the contract-match bonus.
    /// </summary>
    public static PythonCandidateProductDto ToCandidate(CatalogProduct p, string? preferredPartType = null)
    {
        var (unit, unitPrice, packSize) = ResolveUnitPrice(p, preferredPartType);

        // StockAreas carries Available per PartType — no quantity exists.
        // Send a large proxy so the Python scorer awards full stock_availability points
        // when the candidate is available in the preferred PartType.
        var inStock = preferredPartType switch
        {
            "CU" => p.IsCuAvailable,
            "TU" => p.IsTuAvailable,
            _    => p.IsCuAvailable || p.IsTuAvailable,
        };

        return new PythonCandidateProductDto(
            Id:            p.ItemNumber,
            Name:          p.Name,
            CategoryId:    ResolveCategory(p),
            Brand:         p.SellerName,
            Unit:          unit,
            PackSize:      packSize,
            BasePrice:     unitPrice,
            StockQuantity: inStock ? 9999 : 0,
            ContractPrice: unitPrice,
            IsActive:      p.IsActive,
            DietaryTags:   new List<string>());
    }

    public static PythonProductDto ToRequestedProduct(CatalogProduct p, string? preferredPartType = null)
    {
        var (unit, unitPrice, packSize) = ResolveUnitPrice(p, preferredPartType);
        return new PythonProductDto(
            Id:          p.ItemNumber,
            Name:        p.Name,
            CategoryId:  ResolveCategory(p),
            Brand:       p.SellerName,
            Unit:        unit,
            PackSize:    packSize,
            BasePrice:   unitPrice,
            DietaryTags: new List<string>());
    }

    /// <summary>
    /// Returns (unit, unitPrice, packSize) for the Python AI scoring.
    /// CU = sold individually (NumberInUnit=1); TU = whole package (NumberInUnit>1).
    /// PackSize = NumberInUnit so the unit_pack_similarity scorer can compare
    /// ordering formats between the requested product and candidates.
    /// When preferredPartType is specified, that PartType's data is used first.
    /// </summary>
    private static (string unit, double unitPrice, double packSize) ResolveUnitPrice(
        CatalogProduct p, string? preferredPartType = null)
    {
        var cu = p.ConsumerUnit;
        var tu = p.TradeUnit;

        if (preferredPartType == "TU" && tu is not null)
            return (tu.Unit ?? p.MeasurementInfo?.MeasurementCode ?? "KG",
                    (double)tu.Price.UnitPriceDecimal,
                    ParseDouble(tu.NumberInUnit));

        if (preferredPartType == "CU" && cu is not null)
            return (cu.Unit ?? p.MeasurementInfo?.MeasurementCode ?? "KG",
                    (double)cu.Price.UnitPriceDecimal,
                    ParseDouble(cu.NumberInUnit));

        // No preference — default to CU then TU
        if (cu is not null)
            return (cu.Unit ?? p.MeasurementInfo?.MeasurementCode ?? "KG",
                    (double)cu.Price.UnitPriceDecimal,
                    ParseDouble(cu.NumberInUnit));

        if (tu is not null)
            return (tu.Unit ?? p.MeasurementInfo?.MeasurementCode ?? "KG",
                    (double)tu.Price.UnitPriceDecimal,
                    ParseDouble(tu.NumberInUnit));

        return (p.MeasurementInfo?.MeasurementCode ?? "KG", 0.0, 1.0);
    }

    // ── Helpers ───────────────────────────────────────────────────────────────

    public static string ResolveCategory(CatalogProduct p)
    {
        // Priority 1: human-readable CategoryPaths (e.g. "|-|Frukt|-|APPELSIN" → "Frukt")
        var path = p.CategoryPaths.FirstOrDefault(c => !string.IsNullOrWhiteSpace(c));
        if (!string.IsNullOrWhiteSpace(path)) return ExtractTopCategory(path);

        // Priority 2: product name — NEVER integer catalog category IDs like "9264".
        // The Python AI scoring uses bge-m3 embeddings on this field; an opaque integer
        // carries zero semantic signal, so the model treats every product in the same
        // broad catalog bucket as equally similar. Using the product name lets the
        // embedding model distinguish "appelsin" from "vanilje" and rank accordingly.
        return p.Name;
    }

    public static string ExtractTopCategory(string categoryPath)
    {
        if (string.IsNullOrWhiteSpace(categoryPath)) return categoryPath;
        return categoryPath
            .Split(new[] { "|-|", "|" }, StringSplitOptions.RemoveEmptyEntries)
            .FirstOrDefault(s => !string.IsNullOrWhiteSpace(s))
            ?? categoryPath;
    }

    private static double ParseDouble(string? s) =>
        double.TryParse(s, System.Globalization.NumberStyles.Number,
            System.Globalization.CultureInfo.InvariantCulture, out var v) ? v : 1.0;
}
