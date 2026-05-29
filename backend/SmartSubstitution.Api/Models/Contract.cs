using MongoDB.Bson;
using MongoDB.Bson.Serialization.Attributes;

namespace SmartSubstitution.Api.Models;

public class ContractItem
{
    public string ProductId { get; set; } = null!;
    public double ContractPrice { get; set; }
    public bool IsPreferred { get; set; }
}

public class Contract
{
    [BsonId]
    [BsonRepresentation(BsonType.ObjectId)]
    public string? Id { get; set; }

    public string ContractId { get; set; } = null!;
    public string CompanyId { get; set; } = null!;
    public List<ContractItem> Items { get; set; } = new();
}
