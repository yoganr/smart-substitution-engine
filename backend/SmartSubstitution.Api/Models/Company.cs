using MongoDB.Bson;
using MongoDB.Bson.Serialization.Attributes;

namespace SmartSubstitution.Api.Models;

public class Company
{
    [BsonId]
    [BsonRepresentation(BsonType.ObjectId)]
    public string? Id { get; set; }

    public string CompanyId { get; set; } = null!;
    public string Name { get; set; } = null!;
}
