using MongoDB.Bson;
using MongoDB.Bson.Serialization.Attributes;

namespace SmartSubstitution.Api.Models;

public class Product
{
    [BsonId]
    [BsonRepresentation(BsonType.ObjectId)]
    public string? Id { get; set; }

    public string ProductId { get; set; } = null!;
    public string Name { get; set; } = null!;
    public string CategoryId { get; set; } = null!;
    public string Brand { get; set; } = null!;
    public string Unit { get; set; } = null!;
    public double PackSize { get; set; }
    public double BasePrice { get; set; }
    public bool IsActive { get; set; } = true;
    public List<string> DietaryTags { get; set; } = new();
}
