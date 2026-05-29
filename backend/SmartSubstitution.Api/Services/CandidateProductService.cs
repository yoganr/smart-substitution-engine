using Microsoft.Extensions.Options;
using MongoDB.Driver;
using SmartSubstitution.Api.Models;
using SmartSubstitution.Api.Settings;

namespace SmartSubstitution.Api.Services;

public class CandidateProductService
{
    private readonly IMongoCollection<Product> _products;
    private readonly IMongoCollection<Inventory> _inventory;

    public CandidateProductService(IMongoDatabase db)
    {
        _products = db.GetCollection<Product>("products");
        _inventory = db.GetCollection<Inventory>("inventory");
    }

    /// <summary>
    /// Returns active products in the same category that have sufficient stock.
    /// Price threshold filtering and allergen filtering are applied by the Python service.
    /// </summary>
    public async Task<List<(Product Product, int StockQuantity, double? ContractPrice)>> GetCandidatesAsync(
        string categoryId,
        string excludeProductId,
        List<ContractItem> contractItems,
        CancellationToken ct = default)
    {
        // Compound index on (category_id, is_active) covers this query
        var productFilter = Builders<Product>.Filter.And(
            Builders<Product>.Filter.Eq(p => p.CategoryId, categoryId),
            Builders<Product>.Filter.Eq(p => p.IsActive, true),
            Builders<Product>.Filter.Ne(p => p.ProductId, excludeProductId));

        var products = await _products.Find(productFilter).ToListAsync(ct);
        if (products.Count == 0) return new();

        var productIds = products.Select(p => p.ProductId).ToList();
        var inventoryFilter = Builders<Inventory>.Filter.In(i => i.ProductId, productIds);
        var inventories = await _inventory.Find(inventoryFilter).ToListAsync(ct);
        var stockMap = inventories.ToDictionary(i => i.ProductId, i => i.StockQuantity);

        var contractPriceMap = contractItems.ToDictionary(c => c.ProductId, c => c.ContractPrice);

        return products
            .Where(p => stockMap.TryGetValue(p.ProductId, out var stock) && stock > 0)
            .Select(p => (
                Product: p,
                StockQuantity: stockMap.GetValueOrDefault(p.ProductId, 0),
                ContractPrice: contractPriceMap.TryGetValue(p.ProductId, out var cp)
                    ? (double?)cp : null))
            .ToList();
    }
}
