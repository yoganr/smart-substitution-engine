using MongoDB.Bson;
using MongoDB.Bson.Serialization.Attributes;

namespace SmartSubstitution.Api.Models;

public class RecommendationLog
{
    [BsonId]
    [BsonRepresentation(BsonType.ObjectId)]
    public string? Id { get; set; }

    public string ItemNumber { get; set; } = null!;
    public string SellerAccountNumber { get; set; } = null!;
    public string ContractNumber { get; set; } = null!;
    public List<string> ContractNumbers { get; set; } = new();
    public int ReplacementCount { get; set; }
    public string? TopProductId { get; set; }
    public int TopScore { get; set; }
    public long PythonResponseMs { get; set; }
    public DateTime CreatedAt { get; set; } = DateTime.UtcNow;
}
