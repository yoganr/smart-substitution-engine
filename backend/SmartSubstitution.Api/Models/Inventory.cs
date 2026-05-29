using MongoDB.Bson;
using MongoDB.Bson.Serialization.Attributes;

namespace SmartSubstitution.Api.Models;

public class Inventory
{
    [BsonId]
    [BsonRepresentation(BsonType.ObjectId)]
    public string? Id { get; set; }

    public string ProductId { get; set; } = null!;
    public int StockQuantity { get; set; }
    public DateTime UpdatedAt { get; set; } = DateTime.UtcNow;
}
