using MongoDB.Bson;
using MongoDB.Bson.Serialization.Attributes;

namespace SmartSubstitution.Api.Models;

public class RecommendationLog
{
    [BsonId]
    [BsonRepresentation(BsonType.ObjectId)]
    public string? Id { get; set; }

    public DateTime Timestamp { get; set; } = DateTime.UtcNow;
    public string CompanyId { get; set; } = null!;
    public string RequestedProductId { get; set; } = null!;
    public int ReplacementCount { get; set; }
    public string? TopProductId { get; set; }
    public int TopScore { get; set; }
    public long PythonResponseMs { get; set; }
}
