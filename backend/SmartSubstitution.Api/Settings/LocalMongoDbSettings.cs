namespace SmartSubstitution.Api.Settings;

public class LocalMongoDbSettings
{
    public string ConnectionString { get; set; } = null!;
    public string DatabaseName { get; set; } = null!;
    public string CollectionName { get; set; } = "Items";
}
