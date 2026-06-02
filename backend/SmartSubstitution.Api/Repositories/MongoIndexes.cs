using MongoDB.Driver;
using SmartSubstitution.Api.Models;

namespace SmartSubstitution.Api.Repositories;

public static class MongoIndexes
{
    public static async Task EnsureIndexesAsync(IMongoDatabase db)
    {
        var logs = db.GetCollection<RecommendationLog>("recommendation_logs");
        await logs.Indexes.CreateManyAsync(new[]
        {
            new CreateIndexModel<RecommendationLog>(
                Builders<RecommendationLog>.IndexKeys
                    .Ascending(l => l.ItemNumber)
                    .Ascending(l => l.SellerAccountNumber)
                    .Ascending(l => l.ContractNumber)),
            new CreateIndexModel<RecommendationLog>(
                Builders<RecommendationLog>.IndexKeys.Ascending(l => l.CreatedAt)),
        });
    }
}
