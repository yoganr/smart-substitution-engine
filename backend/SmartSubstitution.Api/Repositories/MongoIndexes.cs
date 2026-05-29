using MongoDB.Driver;
using SmartSubstitution.Api.Models;

namespace SmartSubstitution.Api.Repositories;

public static class MongoIndexes
{
    public static async Task EnsureIndexesAsync(IMongoDatabase db)
    {
        var products = db.GetCollection<Product>("products");
        await products.Indexes.CreateManyAsync(new[]
        {
            // Compound index for CandidateProductService query (category + active filter)
            new CreateIndexModel<Product>(
                Builders<Product>.IndexKeys
                    .Ascending(p => p.CategoryId)
                    .Ascending(p => p.IsActive)),
            new CreateIndexModel<Product>(
                Builders<Product>.IndexKeys.Ascending(p => p.ProductId),
                new CreateIndexOptions { Unique = true }),
        });

        var inventory = db.GetCollection<Inventory>("inventory");
        await inventory.Indexes.CreateOneAsync(
            new CreateIndexModel<Inventory>(
                Builders<Inventory>.IndexKeys.Ascending(i => i.ProductId),
                new CreateIndexOptions { Unique = true }));

        var contracts = db.GetCollection<Contract>("contracts");
        await contracts.Indexes.CreateOneAsync(
            new CreateIndexModel<Contract>(
                Builders<Contract>.IndexKeys.Ascending(c => c.CompanyId)));
    }
}
